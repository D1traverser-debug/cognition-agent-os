"""Native decision loop must be able to repair a failed method, not only swap families.

This intentionally drives original Host/SQLite entry and checks the independent
worker result; a planner's text is never counted as outcome verification.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision,
)


class NativeSameMethodCorrection(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.db = self.home / "ledger.sqlite"
        self.workspace = self.home / "workspace"
        self.sources = self.home / "sources"
        self.workspace.mkdir()
        self.sources.mkdir()
        (self.sources / "handoff.json").write_text(
            '{"retain":"immutable"}\n', encoding="utf-8")
        (self.sources / "reference.csv").write_text(
            "id,count\nA,8\n", encoding="utf-8")
        (self.sources / "observed.csv").write_text(
            "id,count\nA,6\n", encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
        self.root = register_native_goal(
            self.db, "Correct a failed local JSON handoff proposal while "
            "preserving the original source and independently check the "
            "result; never modify production.")
        self.originals = {x.name: x.read_bytes() for x in self.sources.iterdir()}

    def view(self):
        return inspect_native_goal(
            self.db, self.workspace, self.sources, self.root)

    def structure(self, field, equals):
        return {"kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "handoff.json"}],
                "requirements": [{"field": field, "equals": equals}]}

    def compare(self):
        return {"kind": "goal_intent", "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": "reference.csv"},
                    {"role": "observed", "path": "observed.csv"}]}

    def choice(self, method):
        state = self.view()
        previous = state["decisions"][-1]["task_id"] if state["decisions"] else None
        return {
            "selected_intent": method,
            "alternative_intent": self.compare(),
            "decision_reason": "Correct previous failed evidence proposal using unchanged originals.",
            "alternative_reason": "CSV reconciliation cannot correct a JSON conformance conflict.",
            "expected_evidence": "Recheck immutable on-disk proposal with the existing Host oracle.",
            "observation_sha256": state["observation_sha256"],
            "decision_basis": {
                "source_refs": [
                    {"path": x.name,
                     "sha256": hashlib.sha256(x.read_bytes()).hexdigest()}
                    for x in sorted(self.sources.iterdir())],
                "previous_result_task_id": previous,
                "challenge": "The same objective may remain unable to satisfy all owner clauses.",
                "falsifier": "Fresh independent Host check rejects the corrected candidate.",
                "uncertainty": "Even a repaired local artifact does not prove the owner outcome.",
            }
        }

    def failed_initial_method(self):
        first = admit_native_decision(
            self.db, self.workspace, self.sources, self.root,
            self.choice(self.structure("retain", "overwrite")))
        observed = run_tick(self.db, self.workspace, self.sources, max_jobs=1)
        self.assertEqual(observed["tasks"][0]["task_id"], first["child_task_id"])
        self.assertEqual(observed["tasks"][0]["status"], "UNKNOWN")
        state = self.view()
        self.assertEqual(state["decisions"][-1]["error_code"], "NO_SAFE_GOAL_PLAN")
        return first

    def test_worker_failure_reopens_method_from_real_ledger_and_cold_resume(self):
        original = self.failed_initial_method()
        with closing(connect(self.db)) as db:
            row = db.execute(
                "SELECT event_id FROM events WHERE task_id=? "
                "AND kind='NATIVE_DECISION_ADMITTED'", (self.root,)).fetchone()
        state = self.view()
        reentry = state["causal_reentry"]
        self.assertEqual(reentry["observed_cause"], "WORKER_REPORTED_FAILURE")
        self.assertEqual(reentry["reopened_decision_event_ids"],
                         [row["event_id"]])
        self.assertEqual(reentry["affected_child_task_ids"],
                         [original["child_task_id"]])
        self.assertFalse(reentry["root_cause_semantically_verified"])
        self.assertFalse(reentry["owner_outcome_verified"])
        self.assertFalse(reentry["authorizes_action"])
        self.assertEqual(inspect_native_goal(
            self.db, self.workspace, self.sources, self.root)["causal_reentry"],
                         reentry)
        # An approved *changed* plan can still repair the real failure;
        # completing it clears only the active re-entry signal.
        admit_native_decision(
            self.db, self.workspace, self.sources, self.root,
            self.choice(self.structure("audit", "confirmed")))
        run_tick(self.db, self.workspace, self.sources, max_jobs=1)
        self.assertNotIn("causal_reentry", self.view())
        self.assertFalse(self.view()["owner_outcome_verified"])

    def test_failed_method_may_be_corrected_without_invented_new_source(self):
        first = self.failed_initial_method()
        correction = admit_native_decision(
            self.db, self.workspace, self.sources, self.root,
            self.choice(self.structure("audit", "confirmed")))
        self.assertNotEqual(correction["child_task_id"], first["child_task_id"])
        outcome = run_tick(self.db, self.workspace, self.sources, max_jobs=1)
        self.assertEqual(outcome["tasks"][0]["task_id"], correction["child_task_id"])
        self.assertEqual(outcome["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertEqual(self.view()["decisions"][-1]["mechanical_verdict"],
                         "CANDIDATE_MECHANICALLY_VALID")
        self.assertEqual(self.view()["decision_count"], 2)
        self.assertFalse(self.view()["owner_outcome_verified"])
        self.assertEqual(
            {x.name: x.read_bytes() for x in self.sources.iterdir()},
            self.originals)

    def test_one_host_trigger_repairs_failed_method_with_verified_feedback(self):
        """Actual first Worker refusal is the reason to switch a typed plan.

        A deterministic fake model only supplies candidate JSON, never an
        execution or a success verdict. The same SQLite admission and Worker
        must reject the conflicting source edit, then execute a materially
        changed same-capability plan during the original authorized tick.
        """
        from unittest.mock import patch
        proposed = []
        def source_model(method, endpoint, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            self.assertEqual(method, "POST")
            state = self.view()
            count = len(state["decisions"])
            proposed.append(count)
            self.assertIn(self.root, self.view()["root_task_id"])
            method_intent = (
                self.structure("retain", "overwrite") if count == 0
                else self.structure("audit", "confirmed"))
            return {"done": True,
                    "response": json.dumps(self.choice(method_intent))}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=source_model):
            tick = run_tick(
                self.db, self.workspace, self.sources, max_jobs=2,
                planner_mode="ollama-local", local_model="installed:test",
                auto_native_cognition=True)
        self.assertEqual(proposed, [0, 1], tick)
        self.assertEqual(
            [x["status"] for x in tick["tasks"]],
            ["UNKNOWN", "NEEDS_REVIEW"], tick)
        self.assertEqual(
            [x["status"] for x in tick["native_cognition"]],
            ["NATIVE_METHOD_ENQUEUED", "NATIVE_METHOD_ENQUEUED"], tick)
        state = self.view()
        self.assertEqual(state["decision_count"], 2, state)
        self.assertEqual(state["decisions"][0]["error_code"],
                         "NO_SAFE_GOAL_PLAN", state)
        self.assertEqual(state["decisions"][1]["mechanical_verdict"],
                         "CANDIDATE_MECHANICALLY_VALID", state)
        self.assertIs(state["owner_outcome_verified"], False)
        self.assertEqual(
            {x.name: x.read_bytes() for x in self.sources.iterdir()},
            self.originals)

    def test_identical_retry_after_failure_is_not_a_correction(self):
        self.failed_initial_method()
        with self.assertRaisesRegex(
                ValueError, "REPEATED_NATIVE_METHOD_WITHOUT_NEW_EVIDENCE"):
            admit_native_decision(
                self.db, self.workspace, self.sources, self.root,
                self.choice(self.structure("retain", "overwrite")))
        self.assertEqual(self.view()["decision_count"], 1)

    def test_successful_method_cannot_be_repeated_without_new_evidence(self):
        done = admit_native_decision(
            self.db, self.workspace, self.sources, self.root,
            self.choice(self.structure("audit", "confirmed")))
        observed = run_tick(self.db, self.workspace, self.sources, max_jobs=1)
        self.assertEqual(observed["tasks"][0]["task_id"], done["child_task_id"])
        self.assertEqual(observed["tasks"][0]["status"], "NEEDS_REVIEW")
        with self.assertRaisesRegex(
                ValueError, "REPEATED_NATIVE_METHOD_WITHOUT_NEW_EVIDENCE"):
            admit_native_decision(
                self.db, self.workspace, self.sources, self.root,
                self.choice(self.structure("other", "confirmed")))
        self.assertEqual(self.view()["decision_count"], 1)


if __name__ == "__main__":
    unittest.main()
