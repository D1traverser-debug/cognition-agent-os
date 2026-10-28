"""Adversarial source-integrity and evidence-scope checks."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_ci_checkout_source import expected_sha, verify_checkout
from verify_ci_merge_source import verify_merge_source
from verify_ci_evidence_scope import (CORE, OPTIONAL, classify_needs,
    native_experiment_admission, _native_cases, _codex_pretool)


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


    def test_preaction_rejects_repeat_even_with_green_previous_ci(self):
        """A bare PR opt-in never silently reruns a known 0/2 model experiment."""
        def unexpected_source(*_args):
            self.fail("No revalidation reason: must reject before source or model I/O")
        with self.assertRaisesRegex(ValueError, "REUSE_PRIOR_NATIVE_EVIDENCE"):
            native_experiment_admission("[run-real-native-schema]",
                                        unexpected_source)
        with self.assertRaisesRegex(ValueError, "EXPLICIT_OPT_IN"):
            native_experiment_admission("", unexpected_source)
        with self.assertRaisesRegex(ValueError, "REUSE_PRIOR_NATIVE_EVIDENCE"):
            native_experiment_admission(
                "[run-real-native-schema][native-retest:changed-model-method]"
                "[native-retest:new-owner-cases]", unexpected_source)

    def test_preaction_retest_requires_real_executable_change_not_words(self):
        source = "def plan():\n    return 'first'\n"
        changed = "def plan():\n    return 'corrected'\n"
        from verify_ci_evidence_scope import PRIOR_NATIVE_EXPERIMENT_SHA
        def reader(path, revision):
            if path.endswith("native_local_planner.py"):
                return source if revision != "HEAD" else changed
            return "def noop():\n    return None\n"
        body = "[run-real-native-schema][native-retest:changed-model-method]"
        allowed = native_experiment_admission(body, reader)
        self.assertEqual(allowed["status"],
                         "NEW_NATIVE_EXPERIMENT_PROBE_ADMISSIBLE_NOT_VALIDATED")
        self.assertEqual(allowed["changed_executable_or_owner_case_sources"],
                         ["src/cognition_agent_os/native_local_planner.py"])
        self.assertFalse(allowed["real_model_ran"])
        def prose_only(path, revision):
            return ("# another research note\n" if revision == "HEAD" else
                    "# prior note\n") + source
        with self.assertRaisesRegex(ValueError, "NO_FRESH_COMMIT_DELTA"):
            native_experiment_admission(body, prose_only)


    def test_preaction_old_retest_reason_cannot_run_again_after_unrelated_commit(self):
        """A legitimate earlier delta cannot license infinite repeat inference."""
        from verify_ci_evidence_scope import PRIOR_NATIVE_EXPERIMENT_SHA
        old = "def plan():\n    return 1\n"
        changed = "def plan():\n    return 2\n"
        def reader(path, revision):
            if path.endswith("native_local_planner.py"):
                return old if revision == PRIOR_NATIVE_EXPERIMENT_SHA else changed
            return old
        with self.assertRaisesRegex(ValueError, "NO_FRESH_COMMIT_DELTA"):
            native_experiment_admission(
                "[run-real-native-schema][native-retest:changed-model-method]",
                reader)

    def test_preaction_new_cases_need_changed_owner_goals_or_hidden_labels(self):
        old = "CASES = [{'id':'a','goal':'do x','files':{'a.csv':'v'},'target':'ensure_structure'}]\n"
        new = old.replace("'do x'", "'do y'")
        body = "[run-real-native-schema][native-retest:new-owner-cases]"
        def reads(path, revision):
            return old if revision != "HEAD" else new
        self.assertNotEqual(_native_cases(old), _native_cases(new))
        self.assertEqual(native_experiment_admission(body, reads)
                         ["changed_executable_or_owner_case_sources"],
                         ["scripts/measure_real_native_goal.py"])
        with self.assertRaisesRegex(ValueError, "NO_FRESH_COMMIT_DELTA"):
            native_experiment_admission(
                body, lambda _p, rev: old + ("\n# new comment" if rev == "HEAD" else ""))

    def test_codex_pretool_denies_unfounded_experiment_mutation_only(self):
        """The actual Codex tool event contract gets a real denial JSON."""
        from unittest.mock import patch
        import contextlib
        import io
        import json
        event = {"hook_event_name": "PreToolUse",
                 "tool_name": "mcp__GitHub__update_pull_request",
                 "tool_input": {"repository_full_name":
                                "D1traverser-debug/cognition-agent-os",
                                "pr_number": 50,
                                "body": "[run-real-native-schema]"}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             contextlib.redirect_stdout(output):
            self.assertEqual(_codex_pretool(), 0)
        blocked = json.loads(output.getvalue())
        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")
        event["tool_input"]["repository_full_name"] = "someone-else/project"
        event["tool_input"]["body"] = "[run-real-native-schema]"
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             contextlib.redirect_stdout(output := io.StringIO()):
            self.assertEqual(_codex_pretool(), 0)
        self.assertEqual(output.getvalue(), "")
        event["tool_name"] = "mcp__GitHub__update_issue"
        event["tool_input"]["repository_full_name"] = "D1traverser-debug/cognition-agent-os"
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             contextlib.redirect_stdout(output := io.StringIO()):
            self.assertEqual(_codex_pretool(), 0)
        self.assertEqual(output.getvalue(), "")
        event["tool_name"] = "mcp__GitHub__update_pull_request"
        event["tool_input"]["pr_number"] = 51
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             contextlib.redirect_stdout(output := io.StringIO()):
            self.assertEqual(_codex_pretool(), 0)
        self.assertEqual(output.getvalue(), "")

        event["tool_input"]["body"] = "Routine owner goal update, no experiment."
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             contextlib.redirect_stdout(output := io.StringIO()):
            self.assertEqual(_codex_pretool(), 0)
        self.assertEqual(output.getvalue(), "")

    def test_workflow_checks_research_reuse_before_downloading_model(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  experimental_real_native_cognition:",1)[1].split(
            "\n  experimental_live_open_goal_method:",1)[0]
        self.assertLess(job.index("--native-experiment-preflight"),
                        job.index("ollama pull"))
        self.assertIn("fetch-depth: 0", job)
        import json
        hook = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertIn("PreToolUse", hook["hooks"])
        self.assertIn("--codex-pretool",
                      hook["hooks"]["PreToolUse"][0]["hooks"][0]["command"])

    def test_real_inference_opt_in_requires_trusted_same_repo_source(self):
        """PR body alone must not allow outsiders to trigger model downloads."""
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  experimental_real_native_cognition:", 1)[1].split(
            "\n  experimental_live_open_goal_method:", 1)[0]
        self.assertIn("[run-real-native-schema]", job)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            job)
        self.assertIn("OLLAMA_NO_CLOUD: '1'", job)
        self.assertIn("python scripts/measure_real_native_goal.py", job)

    def test_every_ollama_download_job_is_bound_to_this_repository_pr(self):
        """No PR body from a fork may opt into downloading model weights.

        Test the whole workflow rather than a named model experiment. This
        also protects future model jobs added after today's repair.
        """
        import re
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        boundaries = list(re.finditer(r"(?m)^  ([a-z][a-z0-9_]*):\s*$", workflow))
        guarded = []
        for position, match in enumerate(boundaries):
            section = workflow[match.end():(
                boundaries[position + 1].start()
                if position + 1 < len(boundaries) else len(workflow))]
            if "ollama pull" not in section:
                continue
            if_lines = [line.strip() for line in section.splitlines()
                        if line.startswith("    if: ")]
            self.assertEqual(len(if_lines), 1, match.group(1))
            self.assertIn("github.event_name == 'pull_request'",
                          if_lines[0], match.group(1))
            self.assertIn(
                "github.event.pull_request.head.repo.full_name == github.repository",
                if_lines[0], match.group(1))
            guarded.append(match.group(1))
        self.assertGreaterEqual(len(guarded), 6, guarded)

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
                self.assertIn("fetch-depth: 2", pre)
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
