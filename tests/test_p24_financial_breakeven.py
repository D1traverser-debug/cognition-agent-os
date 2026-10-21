"""P24 preregistered third-party finance algorithm: pin, oracle, scope."""
from __future__ import annotations
import json
import math
import unittest
from unittest.mock import patch
from scripts import verify_p24_financial_breakeven as p24

FAKE_SOURCE=(
    b"from typing import Any\n"
    b"from collections.abc import Callable\n"
    b"class SensitivityAnalyzer:\n"
    b"    def __init__(self, base_model: Any):\n"
    b"        self.base_model = base_model\n"
    b"        self.base_output = None\n"
    b"        self.sensitivity_results = {}\n"
    b"    def breakeven_analysis(self, variable_name: str, variable_update: Callable, output_func: Callable,\n"
    b"                           target_value: float, min_search: float, max_search: float,\n"
    b"                           tolerance: float = 0.01) -> float:\n"
    b"        low = min_search\n"
    b"        high = max_search\n"
    b"        while (high - low) > tolerance:\n"
    b"            mid = (low + high) / 2\n"
    b"            variable_update(mid)\n"
    b"            output = output_func()\n"
    b"            if abs(output - target_value) < tolerance:\n"
    b"                return mid\n"
    b"            elif output < target_value:\n"
    b"                low = mid\n"
    b"            else:\n"
    b"                high = mid\n"
    b"        return (low + high) / 2\n"
)

class FrozenOutsideFinanceTests(unittest.TestCase):
    def test_verified_external_provenance_and_case_partition(self):
        self.assertEqual(p24.UPSTREAM_REPOSITORY,"anthropics/claude-cookbooks")
        self.assertEqual(p24.UPSTREAM_COMMIT,"a162e0184e71b60290808a43961a6cbc8060123c")
        self.assertEqual(p24.UPSTREAM_GIT_BLOB,"9674aad2e435917e60969d5b6daa816ccf7dc5b3")
        self.assertEqual(p24.ISSUE,"https://github.com/anthropics/claude-cookbooks/issues/931")
        self.assertIn(p24.UPSTREAM_COMMIT,p24.source_url())
        self.assertNotIn("/main/",p24.source_url())
        self.assertEqual(len(p24.PUBLIC),4)
        self.assertEqual(len(p24.HIDDEN),12)
        self.assertLess(len(p24.GOAL.encode()),1200)
        self.assertNotEqual(json.dumps(p24.HIDDEN,sort_keys=True),
                            json.dumps(p24.PUBLIC,sort_keys=True))

    def test_analytic_independent_gold_for_bracketed_cases(self):
        for row in p24.PUBLIC+p24.HIDDEN:
            inp=row["input"]
            self.assertEqual(row["expected"],
                             {"target_met":True,"inside_bounds":True})
            low,high=inp["low"],inp["high"]
            offset,scale,target=inp["offset"],inp["scale"],inp["target"]
            if inp["form"]=="linear":
                self.assertNotEqual(scale,0)
                root=(target-offset)/scale
            else:
                self.assertEqual(inp["form"],"quadratic")
                self.assertNotEqual(scale,0)
                squared=(target-offset)/scale
                self.assertGreaterEqual(squared,0)
                root=math.sqrt(squared)
                if high<=0:root=-root
            with self.subTest(row=row):
                self.assertGreaterEqual(root,low-1e-9)
                self.assertLessEqual(root,high+1e-9)
                output=(offset+scale*root
                        if inp["form"]=="linear" else offset+scale*root*root)
                self.assertAlmostEqual(output,target,places=6)
        # Frozen original is proven wrong for decreasing linear and nonlinear.
        flags=[]
        for row in p24.PUBLIC:
            inp=row["input"]
            lo,hi=inp["low"],inp["high"]
            for _ in range(50):
                if hi-lo<=inp["tolerance"]:
                    break
                mid=(lo+hi)/2
                val=(inp["offset"]+inp["scale"]*mid if inp["form"]=="linear"
                     else inp["offset"]+inp["scale"]*mid*mid)
                if abs(val-inp["target"]) < inp["tolerance"]:
                    lo=hi=mid
                    break
                if val<inp["target"]:
                    lo=mid
                else:
                    hi=mid
            ans=(lo+hi)/2
            v=(inp["offset"]+inp["scale"]*ans if inp["form"]=="linear"
               else inp["offset"]+inp["scale"]*ans*ans)
            threshold=max(0.15,abs(inp["scale"])*inp["tolerance"]
                          *max(1,abs(inp["low"]),abs(inp["high"])))
            flags.append(abs(v-inp["target"])<=threshold)
        self.assertEqual(flags,[False,True,False,True])

    def test_original_bytes_only_two_method_extraction(self):
        sha=p24.git_blob_sha1(FAKE_SOURCE)
        with patch.object(p24,"UPSTREAM_GIT_BLOB",sha):
            fragment=p24.extract_unmodified_methods(FAKE_SOURCE)
            self.assertIn("def __init__",fragment)
            self.assertIn("def breakeven_analysis(",fragment)
            self.assertIn("elif output < target_value:",fragment)
            case=p24.make_case(FAKE_SOURCE)
            self.assertEqual(case["candidate_format"],"exact_replace")
            self.assertEqual(case["public"],p24.PUBLIC)
            self.assertEqual(case["hidden"],p24.HIDDEN)
            self.assertEqual(case["goal_statement"],p24.GOAL)
            self.assertTrue(case["source"].startswith(p24.PREFIX))
            self.assertTrue(case["source"].endswith(p24.ADAPTER))
            self.assertEqual(len(p24.manifest(FAKE_SOURCE)),64)
            with self.assertRaises(ValueError):
                p24.extract_unmodified_methods(FAKE_SOURCE+b"# mutation\n")

    def test_method_body_only_scope_and_untrusted_source_injection_rejected(self):
        with patch.object(p24,"UPSTREAM_GIT_BLOB",p24.git_blob_sha1(FAKE_SOURCE)):
            original=p24.make_case(FAKE_SOURCE)["source"]
            modified=original.replace("elif output < target_value:",
                                      "elif output > target_value:")
            self.assertTrue(p24.preserves_scope(modified.encode(),FAKE_SOURCE))
            self.assertFalse(p24.preserves_scope(original.encode(),FAKE_SOURCE))
            self.assertFalse(p24.preserves_scope(
                modified.replace("self.base_model = base_model",
                                 "self.base_model = None").encode(),FAKE_SOURCE))
            self.assertFalse(p24.preserves_scope(
                (modified+"# appended attacker code").encode(),FAKE_SOURCE))
            self.assertFalse(p24.preserves_scope(
                modified.replace("\n\n"+"def calculate(data):",
                                 "\nimport os\n\n"+"def calculate(data):").encode(),FAKE_SOURCE))
            self.assertFalse(p24.preserves_scope(b"\xff\xfe",FAKE_SOURCE))

    def test_reject_missing_or_duplicate_original_methods(self):
        missing=b"class SensitivityAnalyzer:\n    pass\n"
        with patch.object(p24,"UPSTREAM_GIT_BLOB",p24.git_blob_sha1(missing)):
            with self.assertRaises(ValueError):
                p24.extract_unmodified_methods(missing)
        duplicate=FAKE_SOURCE+FAKE_SOURCE
        with patch.object(p24,"UPSTREAM_GIT_BLOB",p24.git_blob_sha1(duplicate)):
            with self.assertRaises((ValueError,SyntaxError)):
                p24.extract_unmodified_methods(duplicate)

if __name__=="__main__":
    unittest.main()
