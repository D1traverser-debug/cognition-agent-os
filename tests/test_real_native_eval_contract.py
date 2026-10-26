"""Offline checks for the separate REAL-MODEL native vs incumbent evaluation.

These tests only protect benchmark labels and setup. They DO NOT count as
model-performance evidence; that requires the opt-in real inference job.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest


def load_benchmark():
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_real_native_goal.py"
    spec = importlib.util.spec_from_file_location("real_native_eval_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeRealModelEvalContract(unittest.TestCase):
    def test_independent_hidden_labels_and_both_success_failure_owner_cases(self):
        benchmark = load_benchmark()
        cases = benchmark.CASES
        self.assertGreaterEqual(len(cases), 4)
        self.assertEqual(len({x["id"] for x in cases}), len(cases))
        self.assertTrue(any(x["must_complete_local_owner"] for x in cases))
        self.assertTrue(any(not x["must_complete_local_owner"] for x in cases))
        self.assertTrue(any(x["target"] is None for x in cases))
        for case in cases:
            self.assertTrue(case["goal"])
            self.assertTrue(case["files"])
            self.assertTrue(all(name.split(".")[-1] in
                                ("md", "txt", "csv", "json")
                                for name in case["files"]))
            self.assertNotIn("selected_intent", case)
            self.assertNotIn("decision_basis", case)

    def test_incumbent_receives_same_fixtures_without_mutating_sources(self):
        benchmark = load_benchmark()
        with tempfile.TemporaryDirectory() as td:
            result = benchmark._baseline_trial(
                benchmark.CASES[0], Path(td))
            self.assertTrue(result["source_preserved"], result)
            self.assertFalse(result["external_business_result_verified"])
            self.assertNotIn("model_trace_actual_not_mocked", result)


if __name__ == "__main__":
    unittest.main()
