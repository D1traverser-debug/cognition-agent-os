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
                {"files":list(source)},source,visible,"installed:local")
            changed=_candidate_from_model(
                {"files":list(source)},source,visible,"installed:local",
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
