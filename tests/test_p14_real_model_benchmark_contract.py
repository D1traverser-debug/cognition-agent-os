"""P14 benchmark contract tests. NEVER substitute a fake model for CI proof."""
from __future__ import annotations
import hashlib
import json
import unittest

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
