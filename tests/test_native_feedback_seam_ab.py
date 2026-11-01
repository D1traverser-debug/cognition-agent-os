"""Negative controls for the real-Host A/B outcome oracle (not model mocks)."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] /
          "scripts" / "verify_native_feedback_seam_ab.py")
spec = importlib.util.spec_from_file_location("native_feedback_seam_ab", SCRIPT)
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


class NativeFeedbackABOracleTests(unittest.TestCase):
    def observed(self, case):
        revoked = case == "revoked_before_execution"
        return {
            "case": case,
            "local_owner_outcome_verified": not revoked,
            "business_outcome_verified": False,
            "outcome_scope": None,
            "child_count": 0 if revoked else 1,
            "tick_processed": [0, 0] if revoked else [1, 0],
            "source_unchanged": True,
            "semantic_outcome_verified": False,
        }

    def test_positive_and_refusal_baselines(self):
        for case in ab.SCENARIOS:
            with self.subTest(case=case):
                self.assertTrue(ab._oracle(self.observed(case), case))

    def test_false_success_or_unearned_semantics_fail(self):
        for case in ab.SCENARIOS:
            for key in ("business_outcome_verified",
                        "semantic_outcome_verified"):
                observation = self.observed(case)
                observation[key] = True
                self.assertFalse(ab._oracle(observation, case))

    def test_missing_effect_or_duplicate_child_rejected(self):
        for case in ("exact_csv", "exact_json"):
            for n in (0, 2):
                observation = self.observed(case)
                observation["child_count"] = n
                self.assertFalse(ab._oracle(observation, case))

    def test_revoked_grant_cannot_have_an_effect(self):
        for key, value in (
            ("child_count", 1),
            ("tick_processed", [1, 0]),
            ("local_owner_outcome_verified", True),
        ):
            observation = self.observed("revoked_before_execution")
            observation[key] = value
            self.assertFalse(ab._oracle(
                observation, "revoked_before_execution"))

    def test_source_mutation_always_fails(self):
        for case in ab.SCENARIOS:
            observation = self.observed(case)
            observation["source_unchanged"] = False
            self.assertFalse(ab._oracle(observation, case))


if __name__ == "__main__":
    unittest.main()
