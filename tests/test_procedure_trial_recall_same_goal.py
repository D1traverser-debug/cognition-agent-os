"""Regression: repeated identical owner goals cannot starve distinct verified experience."""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.native_local_planner import advance_native_adaptive_once
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome
from cognition_agent_os.procedure_evidence import inspect_cross_root_procedure_trials


class DuplicateHistoryRecallTests(unittest.TestCase):
    def test_identical_finished_goals_do_not_hide_distinct_verified_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db = base / "ledger.sqlite"
            inputs = base / "fixtures"
            workspace = base / "workspace"
            inputs.mkdir()
            workspace.mkdir()
            (inputs / "reference.csv").write_text("id,qty\nA,7\n", encoding="utf-8")
            (inputs / "observed.csv").write_text("id,qty\nA,5\n", encoding="utf-8")
            with closing(connect(db)) as con:
                initialize(con)

            earlier_goal = (
                "Compare reference.csv with observed.csv and report differences.")
            current_goal = (
                "Compare reference.csv against observed.csv and report differences.")

            def execute_goal(goal):
                root = register_native_goal(db, goal)
                admitted = advance_native_adaptive_once(
                    db, workspace, inputs, root, model=None)
                self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED", admitted)
                tick = run_tick(db, workspace, inputs, max_jobs=1)
                self.assertEqual(tick["tasks"][0]["task_id"], admitted["child_task_id"])
                observed = inspect_owner_local_outcome(db, workspace, inputs, root)
                self.assertTrue(observed["local_owner_outcome_verified"], observed)
                return root

            earlier = execute_goal(earlier_goal)
            for _ in range(3):
                execute_goal(current_goal)
            current = register_native_goal(db, current_goal)
            with (patch("cognition_agent_os.procedure_evidence._MAX_ROOT_SCAN", 1),
                  patch("cognition_agent_os.procedure_evidence._MAX_TOTAL_ROOT_SCAN", 2)):
                evidence = inspect_cross_root_procedure_trials(
                    db, workspace, inputs, current,
                    eligible_objectives=("compare_records",))
            self.assertEqual(
                {x["source_root_id"] for x in evidence["items"]},
                {earlier}, evidence)
            self.assertEqual(evidence["source_roots_scanned"], 1, evidence)
            self.assertFalse(evidence["source_root_scan_truncated"], evidence)
            self.assertFalse(evidence["any_general_method_transfer_verified"])
            self.assertFalse(evidence["authorizes_action"])
