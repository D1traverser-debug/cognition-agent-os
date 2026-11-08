import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from measure_native_execution_boundary import judge


class NativeBoundaryOracleTests(unittest.TestCase):
    def setUp(self):
        self.cases = {"allowed": {"exitCode": 0, "bytes_match": True},
                      "readonly": {"exitCode": 73, "unchanged": True},
                      "sibling": {"exitCode": 73, "unchanged": True},
                      "symlink": {"exitCode": 73, "unchanged": True}}

    def test_positive_with_independent_readback_is_scoped(self):
        result = judge(self.cases)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["product_ready"])
        self.assertEqual(result["goal_alignment_and_revocation"], "NOT_TESTED")

    def test_denial_from_a_broken_executor_cannot_pass(self):
        self.cases["allowed"] = {"exitCode": 1, "bytes_match": False}
        self.assertEqual(judge(self.cases)["status"], "FAIL")

    def test_error_after_an_effect_is_not_a_safe_refusal(self):
        for name in ("readonly", "sibling", "symlink"):
            cases = copy.deepcopy(self.cases)
            cases[name]["unchanged"] = False
            self.assertEqual(judge(cases)["status"], "FAIL", name)

    def test_generic_error_or_timeout_is_not_a_permission_denial(self):
        for code in (0, 1, -9, 124):
            cases = copy.deepcopy(self.cases)
            cases["sibling"]["exitCode"] = code
            self.assertEqual(judge(cases)["status"], "FAIL", code)

    def test_missing_symlink_is_explicitly_untested(self):
        del self.cases["symlink"]
        self.assertEqual(judge(self.cases)["symlink_boundary"], "NOT_TESTED")


if __name__ == "__main__":
    unittest.main()
