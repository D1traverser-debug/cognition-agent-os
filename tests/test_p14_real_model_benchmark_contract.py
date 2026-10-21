"""P14 benchmark contract tests. NEVER substitute a fake model for CI proof."""
from __future__ import annotations
import hashlib
import json
import unittest
from unittest.mock import patch

from scripts.verify_actual_local_model import CASES,MODEL


class RealModelBenchmarkContractTests(unittest.TestCase):
    def test_fixed_benchmark_is_not_model_supplied_gold(self):
        self.assertEqual(MODEL,"qwen2.5-coder:0.5b")
        self.assertEqual(len(CASES),2)
        self.assertEqual(len({x["name"] for x in CASES}),2)
        for case in CASES:
            self.assertEqual(len(case["public"]),2)
            self.assertEqual(len(case["hidden"]),2)
            self.assertNotEqual(case["public"],case["hidden"])
            exposed=json.dumps(case["public"],sort_keys=True)
            # Hidden cases are NOT part of public prompt, even by value.
            for test in case["hidden"]:
                self.assertNotIn(json.dumps(test["input"],sort_keys=True),exposed)
            self.assertLess(len(case["source"].encode()),16384)

    def test_model_output_schema_allows_only_approved_source_paths(self):
        from cognition_agent_os.repo_repair import _candidate_from_model
        from cognition_agent_os import local_model
        source={"main.py":b"print(1)\\n",
                "calculator.py":b"def calculate(x):\\n    return 0\\n"}
        spec={"files":list(source),"goal_statement":
              "Given an input number, produce the next number as total."}
        visible=json.dumps([{"input":{"x":3},"expected":{"total":4}}]).encode()
        requests=[]
        def fake_local_request(method,path,payload,timeout):
            requests.append((method,path,payload))
            if path=="/api/tags":
                return {"models":[{"name":"installed:local"}]}
            self.assertEqual(payload["format"]["type"],"object")
            self.assertEqual(payload["format"]["required"],["changes"])
            self.assertFalse(payload["format"]["additionalProperties"])
            item=payload["format"]["properties"]["changes"]["items"]
            self.assertEqual(item["required"],["path","content"])
            self.assertFalse(item["additionalProperties"])
            self.assertEqual(item["properties"]["path"]["enum"],list(source))
            self.assertNotIn("secret.json",payload["prompt"])
            return {"done":True,"response":json.dumps({"changes":[{
                "path":"calculator.py",
                "content":"def calculate(x):\\n    return {'total': x + 1}\\n"
            }]})}
        with patch.object(local_model,"_request",side_effect=fake_local_request):
            result=_candidate_from_model(
                spec,source,visible,"installed:local")
            changed=_candidate_from_model(
                spec,source,visible,"installed:local",
                feedback={"latest_rejection":{
                    "reason":"MODEL_REPEATED_PRIOR_HYPOTHESIS",
                    "must_propose_different_full_source":True}})
        self.assertTrue(result.startswith(b'{"changes"'))
        self.assertEqual(changed,result)  # Fake response only; real model is unmocked in CI.
        self.assertEqual([x[1] for x in requests],
                         ["/api/tags","/api/generate","/api/tags","/api/generate"])
        self.assertEqual(requests[1][2]["options"]["temperature"],0)
        self.assertEqual(requests[3][2]["options"]["temperature"],0.35)
        self.assertIn("latest_rejection",requests[3][2]["prompt"])
        for index in (1,3):
            prompt=json.loads(requests[index][2]["prompt"])
            self.assertEqual(prompt["goal_statement"],spec["goal_statement"])
            self.assertNotIn("sealed",requests[index][2]["prompt"])
        self.assertIn("goal",json.loads(requests[1][2]["prompt"])["task"])

    def test_explicit_goal_statement_is_bounded_and_non_authoritative(self):
        from cognition_agent_os.container_lab import validate_task_spec
        contract={"kind":"repo_container_repair",
                  "files":["main.py","worker.py"],"entrypoint":"main.py",
                  "candidate":"candidate.json","visible":"public.json",
                  "holdout":"sealed.json","holdout_sha256":"a"*64}
        self.assertEqual(validate_task_spec(contract),contract)
        statement="Count unique values strictly above threshold, once each."
        with_goal={**contract,"goal_statement":statement}
        self.assertEqual(validate_task_spec(with_goal),with_goal)
        for invalid in ("", "  ", "a"*1201, "\\x00bad", 21, None):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                validate_task_spec({**contract,"goal_statement":invalid})
        with self.assertRaises(ValueError):
            validate_task_spec({**with_goal,"privileged_code":True})
        # These two independent candidate semantics agree on public
        # inputs with no threshold equality, yet diverge at the boundary.
        public={"values":[2,8,8],"threshold":3}
        above=lambda d:len({x for x in d["values"] if x>d["threshold"]})
        above_or_equal=lambda d:len({x for x in d["values"] if x>=d["threshold"]})
        self.assertEqual(above(public),above_or_equal(public))
        counterexample={"values":[3,3,8],"threshold":3}
        self.assertNotEqual(above(counterexample),above_or_equal(counterexample))

    def test_invoice_expected_reference_uses_subtract_discount(self):
        case=CASES[0]
        def correct(d):
            return {"total":sum(item["price"]*item["qty"] for item in d["items"])
                    -d["discount"]+d["postage"]}
        for row in case["public"]+case["hidden"]:
            self.assertEqual(correct(row["input"]),row["expected"])
        self.assertIn("+ data['discount']",case["source"])

    def test_distinct_threshold_requires_strict_greater_comparison(self):
        case=CASES[1]
        def correct(d):
            return {"count":len({n for n in d["values"] if n>d["threshold"]})}
        for row in case["public"]+case["hidden"]:
            self.assertEqual(correct(row["input"]),row["expected"])
        self.assertIn("n >= data['threshold']",case["source"])


if __name__=="__main__":
    unittest.main()
