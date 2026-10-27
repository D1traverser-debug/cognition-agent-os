"""Adversarial source-integrity and evidence-scope checks."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_ci_checkout_source import expected_sha, verify_checkout
from verify_ci_merge_source import verify_merge_source
from verify_ci_evidence_scope import CORE, OPTIONAL, classify_needs


class CISourceAndScopeTests(unittest.TestCase):
    a = "a" * 40
    b = "b" * 40

    def test_pr_checks_actual_head_not_merge_or_cached_ci_association(self):
        self.assertEqual(expected_sha({"pull_request": {"head": {"sha": self.a}}},
                                      self.b), self.a)
        with self.assertRaisesRegex(ValueError, "CI_TESTED_WRONG_TREE"):
            verify_checkout(self.a, self.b)
        self.assertEqual(verify_checkout(self.a, self.a)["source_sha_observed"],
                         self.a)

    def test_push_checks_actual_checkout_and_unknown_event_fails_closed(self):
        self.assertEqual(expected_sha({}, self.b), self.b)
        with self.assertRaises(ValueError):
            expected_sha({"pull_request": {"head": {}}}, self.b)
        with self.assertRaises(ValueError):
            verify_checkout(self.a, "HEAD")

    def test_missing_or_skipped_core_job_never_passes(self):
        good = {name: {"result": "success"} for name in (*CORE, *OPTIONAL)}
        receipt, ok = classify_needs(good)
        self.assertTrue(ok)
        self.assertFalse(receipt["product_ready"])
        self.assertEqual(receipt["owner_original_goal_verification"],
                         "NOT_TESTED_BY_GITHUB_CI")
        del good[CORE[0]]
        with self.assertRaisesRegex(ValueError, "Missing job"):
            classify_needs(good)
        good[CORE[0]] = {"result": "skipped"}
        receipt, ok = classify_needs(good)
        self.assertFalse(ok)
        self.assertEqual(receipt["core_blockers"][CORE[0]], "skipped")

    def test_optional_skips_reported_and_cannot_claim_business_success(self):
        jobs = {name: {"result": "success"} for name in CORE}
        jobs.update({name: {"result": "skipped"} for name in OPTIONAL})
        receipt, ok = classify_needs(jobs)
        self.assertTrue(ok)
        self.assertEqual(len(receipt["optional_skipped"]), len(OPTIONAL))
        self.assertFalse(receipt["product_ready"])
        self.assertEqual(receipt["status"], "ENGINEERING_GATES_PASSED")
        jobs[OPTIONAL[0]] = {"result": "failure"}
        receipt, ok = classify_needs(jobs)
        self.assertTrue(ok)  # The failed experiment separately makes workflow red.
        self.assertEqual(receipt["optional_jobs"][OPTIONAL[0]], "failure")

    def test_merge_parents_and_actual_merge_sha_must_match_originals(self):
        merge = "c" * 40
        event = {"pull_request": {"head": {"sha": self.a},
                                  "base": {"sha": self.b}}}
        evidence = verify_merge_source(event, "pull_request", merge,
                                       merge, (merge, self.b, self.a))
        self.assertEqual(evidence["scope"], "PR_SYNTHETIC_MERGE")
        self.assertEqual(evidence["base_parent"], self.b)
        self.assertEqual(evidence["head_parent"], self.a)
        with self.assertRaisesRegex(ValueError, "CI_MERGE_PARENT_MISMATCH"):
            verify_merge_source(event, "pull_request", merge,
                                merge, (merge, self.a, self.b))
        with self.assertRaisesRegex(ValueError, "CI_TESTED_WRONG_MERGE"):
            verify_merge_source(event, "pull_request", merge,
                                self.a, (self.a, self.b, self.a))
        with self.assertRaisesRegex(ValueError, "CI_MERGE_PARENT_MISMATCH"):
            verify_merge_source(event, "pull_request", merge,
                                merge, (merge, self.b, self.b))

    def test_push_no_merge_is_labelled_not_impersonated(self):
        actual = self.a
        evidence = verify_merge_source({}, "push", actual, actual,
                                       (actual, self.b))
        self.assertEqual(evidence["scope"], "NON_PR_EXACT_SOURCE_NOT_MERGE")
        with self.assertRaisesRegex(ValueError, "CI_TESTED_WRONG_MERGE"):
            verify_merge_source({}, "push", actual, self.b,
                                (self.b, self.a))

    def test_actual_workflow_pins_every_checkout_and_emits_receipt(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        blocks = workflow.split("      - uses: actions/checkout@")[1:]
        self.assertGreaterEqual(len(blocks), 20)
        merge_blocks = []
        for block in blocks:
            pre = block.split("      - name:", 1)[0]
            if "python scripts/verify_ci_merge_source.py" in block:
                merge_blocks.append(block)
                self.assertNotIn("ref: ${{ github.event.pull_request.head.sha", pre)
                continue
            self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", pre)
            self.assertIn("python scripts/verify_ci_checkout_source.py", block.split("      - name:", 2)[1])
        self.assertEqual(len(merge_blocks), 1)
        self.assertIn("pr_merge_compatibility:", workflow)
        self.assertIn("ci_evidence_scope:", workflow)
        self.assertIn("python scripts/verify_ci_evidence_scope.py", workflow)
        self.assertIn("if: ${{ always() }}", workflow)


if __name__ == "__main__":
    unittest.main()
