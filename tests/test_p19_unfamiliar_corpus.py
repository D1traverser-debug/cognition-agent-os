"""P19 prospective (before inference) task contract tests, no mock quality claims."""
from __future__ import annotations

import hashlib
import json
import unittest

from cognition_agent_os.container_lab import validate_task_spec,cases_from_bytes
from scripts.verify_actual_local_model import CASES as P14_CASES
from scripts.verify_p19_unfamiliar_model import CASES


def independent_dv_oracle(data):
    # Separate test-author calculation, not copied from the broken source.
    groups={}
    for event in data["records"]:
        key=(event["suite"],event["test"])
        if key not in groups or event["attempt"]>groups[key]["attempt"]:
            groups[key]=event
    latest_failures=sorted(
        suite+"/"+test for (suite,test),event in groups.items()
        if event["result"]!="PASS")
    return {"passed":len(groups)-len(latest_failures),
            "failed":len(latest_failures),"latest_failures":latest_failures}


def independent_interval_oracle(data):
    intervals=sorted((left,right) for left,right in data["intervals"]
                     if right>left)
    merged=[]
    for left,right in intervals:
        if merged and left<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
        else:
            merged.append((left,right))
    return {"covered":sum(right-left for left,right in merged)}


class UnfamiliarCorpusContract(unittest.TestCase):
    def test_prospective_manifest_has_distinct_task_families_and_fresh_digest(self):
        self.assertEqual(len(CASES),2)
        self.assertEqual({c["name"] for c in CASES},{
            "dv_latest_retry_per_test","half_open_interval_union"})
        self.assertTrue({c["name"] for c in CASES}.isdisjoint(
            {c["name"] for c in P14_CASES}))
        self.assertNotEqual(
            hashlib.sha256(json.dumps(CASES,sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(P14_CASES,sort_keys=True).encode()).hexdigest())

    def test_agent_authored_gold_matches_separate_independent_oracle(self):
        oracles={
            "dv_latest_retry_per_test":independent_dv_oracle,
            "half_open_interval_union":independent_interval_oracle}
        for case in CASES:
            self.assertGreaterEqual(len(case["public"]),2)
            self.assertGreaterEqual(len(case["hidden"]),3)
            self.assertNotEqual(case["public"],case["hidden"])
            for row in case["public"]+case["hidden"]:
                self.assertEqual(oracles[case["name"]](row["input"]),
                                 row["expected"])
            public_serialized=json.dumps(case["public"],sort_keys=True)
            for row in case["hidden"]:
                self.assertNotIn(json.dumps(row["input"],sort_keys=True),
                                 public_serialized)
            self.assertEqual(len(cases_from_bytes(
                json.dumps(case["public"]).encode())),len(case["public"]))
            self.assertEqual(len(cases_from_bytes(
                json.dumps(case["hidden"]).encode())),len(case["hidden"]))

    def test_goals_are_valid_task_data_not_new_write_authority(self):
        for case in CASES:
            holdout=json.dumps(case["hidden"],sort_keys=True).encode()
            spec={"kind":"repo_container_repair",
                  "files":["main.py","calculator.py"],"entrypoint":"main.py",
                  "candidate":"seed.json","visible":"visible.json",
                  "holdout":"sealed.json",
                  "holdout_sha256":hashlib.sha256(holdout).hexdigest(),
                  "goal_statement":case["goal_statement"]}
            self.assertEqual(validate_task_spec(spec),spec)
            self.assertNotIn("hidden",case["goal_statement"].lower())
            self.assertNotIn("import",case["goal_statement"].lower())
            self.assertNotIn("subprocess",case["source"])
            self.assertNotIn("os.system",case["source"])
            self.assertLess(len(case["source"].encode()),16384)

    def test_broken_source_and_hidden_reference_are_not_model_correct_patches(self):
        self.assertIn("if key not in latest",CASES[0]["source"])
        self.assertIn("sum(end-start",CASES[1]["source"])
        # First PUBLIC counterexample contradicts buggy source in each
        # case; Docker integration will independently execute this.
        self.assertEqual(CASES[0]["public"][0]["expected"]["passed"],1)
        self.assertEqual(CASES[1]["public"][0]["expected"]["covered"],4)


if __name__=="__main__":
    unittest.main()
