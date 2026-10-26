"""Original-owner LOCAL result verification for current native/MCP entrypoint.

Tests are independent of model text assertions and don't claim business effects.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision)
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome


class NativeOwnerAcceptance(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.db = root / "authority.sqlite"
        self.workspace = root / "workspace"
        self.fixtures = root / "sources"
        self.workspace.mkdir()
        self.fixtures.mkdir()
        (self.fixtures / "baseline.csv").write_text(
            "id,amount\nA,4\nB,5\n", encoding="utf-8")
        (self.fixtures / "actual.csv").write_text(
            "id,amount\nA,6\nB,5\n", encoding="utf-8")
        (self.fixtures / "handoff.json").write_text(
            '{"owner":"unknown"}\n', encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)

    def run_case(self, goal):
        root = register_native_goal(self.db, goal)
        state = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        fingerprints = [{
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        } for path in sorted(self.fixtures.iterdir())]
        candidate = {
            "selected_intent": {
                "kind": "goal_intent", "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": "baseline.csv"},
                    {"role": "observed", "path": "actual.csv"}],
            },
            "alternative_intent": {
                "kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "handoff.json"}],
                "requirements": [{"field": "owner", "equals": "ops"}],
            },
            "decision_reason":
                "Original named CSV evidence is directly comparable.",
            "alternative_reason":
                "A JSON formatting method cannot establish the CSV discrepancy.",
            "expected_evidence":
                "Independently recalculated and immutable local CSV comparison.",
            "observation_sha256": state["observation_sha256"],
            "decision_basis": {
                "source_refs": fingerprints,
                "previous_result_task_id": None,
                "challenge": "The two original files may not have a reliable join key.",
                "falsifier": "Recomputed source differences disagree with the artifact.",
                "uncertainty": "A report cannot prove production stock correctness.",
            },
        }
        initial = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertFalse(initial["local_owner_outcome_verified"])
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root, candidate)
        result = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(result["tasks"][0]["status"], "NEEDS_REVIEW", result)
        self.assertEqual(result["tasks"][0]["task_id"], admitted["child_task_id"])
        return root, admitted

    def test_full_named_goal_is_independently_satisfied_then_revocable(self):
        root, admitted = self.run_case(
            "Compare baseline.csv with actual.csv and report differences.")
        verdict = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertEqual(verdict["status"], "LOCAL_OWNER_RESULT_VERIFIED", verdict)
        self.assertEqual(verdict["evidence_task_id"], admitted["child_task_id"])
        self.assertTrue(verdict["local_owner_outcome_verified"])
        self.assertFalse(verdict["business_outcome_verified"])
        self.assertFalse(verdict["real_external_outcome_verified"])
        (self.fixtures / "actual.csv").write_text(
            "id,amount\nA,999\nB,5\n", encoding="utf-8")
        changed = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertFalse(changed["local_owner_outcome_verified"], changed)
        (self.fixtures / "actual.csv").write_text(
            "id,amount\nA,6\nB,5\n", encoding="utf-8")
        restored = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertTrue(restored["local_owner_outcome_verified"], restored)
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        revoked = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertFalse(revoked["local_owner_outcome_verified"], revoked)

    def test_unrequested_extra_deliverable_is_not_silently_dropped(self):
        root, _ = self.run_case(
            "Compare baseline.csv with actual.csv and report differences "
            "and publish the finding to a third party.")
        verdict = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertFalse(verdict["local_owner_outcome_verified"], verdict)
        self.assertEqual(verdict["reason"],
                         "OWNER_OBLIGATION_COVERAGE_INCOMPLETE", verdict)

    def test_unrelated_competitor_cannot_turn_local_technical_pass_to_business_pass(self):
        root, _ = self.run_case(
            "Resolve the real inventory shortage, notify warehouse operations, "
            "and compare baseline.csv with actual.csv and report differences.")
        result = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root)
        self.assertFalse(result["local_owner_outcome_verified"], result)
        self.assertFalse(result["business_outcome_verified"], result)


if __name__ == "__main__":
    unittest.main()
