"""Cold chat/session recovery from the same real open_goal task ledger.

An original owner goal MUST remain discoverable without a second manual
continuity-registration step. All positive claims are independent local
readbacks; the command never creates a task or grants permission.
"""
from contextlib import closing, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.cli import main
from cognition_agent_os.continuity import resume_goal
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority


class OpenGoalColdResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.db = self.home / "state.sqlite"
        self.workspace = self.home / "workspace"
        self.workspace.mkdir()
        self.fixtures = self.home / "fixtures"
        self.fixtures.mkdir()
        (self.fixtures / "settings.json").write_text(
            '{"timeout":7}\\n', encoding="utf-8")
        (self.fixtures / "baseline.csv").write_text(
            "id,amount\\nA,4\\n", encoding="utf-8")
        (self.fixtures / "actual.csv").write_text(
            "id,amount\\nA,6\\n", encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)

    def seed(self, goal):
        with closing(connect(self.db)) as db:
            return create_task(db, {"kind": "open_goal", "goal": goal})

    def recover(self):
        return resume_goal(
            self.db, workspace=self.workspace, fixtures=self.fixtures)

    def test_original_goal_survives_without_second_continuity_registration(self):
        raw = "Please ensure a sandbox draft of settings.json has owner equal to ops."
        tid = self.seed(raw)
        first = self.recover()
        self.assertEqual(first["status"], "READY_TO_TICK", first)
        self.assertEqual(first["root_task_id"], tid)
        self.assertEqual(first["original_goal"], raw)
        self.assertEqual(first["next_task_id"], tid)
        self.assertFalse(first["business_outcome_verified"])
        self.assertEqual(self.recover(), first)

    def test_actual_host_effect_and_independent_verdict_survive_restart(self):
        raw = ("Please ensure a sandbox draft of settings.json has owner equal "
               "to ops, preserving the existing timeout.")
        tid = self.seed(raw)
        result = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=2,
            auto_stage_goals=True)
        self.assertEqual(result["goal_progress"]["goals"][0]
                         ["local_owner_result"]["status"],
                         "LOCAL_OWNER_RESULT_VERIFIED")
        resumed = self.recover()
        self.assertEqual(resumed["status"], "LOCAL_OWNER_RESULT_VERIFIED", resumed)
        self.assertEqual(resumed["root_task_id"], tid)
        self.assertEqual(resumed["original_goal"], raw)
        self.assertNotIn("next_task_id", resumed)
        self.assertFalse(resumed["business_outcome_verified"])
        self.assertEqual(self.recover(), resumed)

    def test_actual_source_change_cancels_derived_success(self):
        self.seed("Compare baseline.csv with actual.csv and report differences.")
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=2)
        self.assertEqual(self.recover()["status"], "LOCAL_OWNER_RESULT_VERIFIED")
        (self.fixtures / "actual.csv").write_text(
            "id,amount\\nA,100\\n", encoding="utf-8")
        state = self.recover()
        self.assertNotEqual(state["status"], "LOCAL_OWNER_RESULT_VERIFIED", state)
        self.assertNotIn("next_task_id", state)
        self.assertFalse(state["local_owner_outcome_verified"])

    def test_revocation_blocks_recovery_without_losing_original_goal(self):
        self.seed("Compare baseline.csv with actual.csv and report differences.")
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        found = self.recover()
        self.assertEqual(found["status"], "AUTHORITY_REVOKED", found)
        self.assertNotIn("next_task_id", found)
        self.assertFalse(found["business_outcome_verified"])

    def test_two_open_owner_roots_are_ambiguous_not_latest_wins(self):
        self.seed("Compare baseline.csv with actual.csv and report differences.")
        self.seed("Please ensure a sandbox draft of settings.json has owner equal to ops.")
        state = self.recover()
        self.assertEqual(state["status"], "AMBIGUOUS_OPEN_OWNER_GOALS", state)
        self.assertNotIn("next_task_id", state)

    def test_cli_goal_resume_is_a_real_cross_process_entry(self):
        goal = "Compare baseline.csv with actual.csv and report differences."
        root = self.seed(goal)
        stream = StringIO()
        with redirect_stdout(stream):
            code = main(["--db", str(self.db),
                         "--workspace", str(self.workspace),
                         "--fixtures", str(self.fixtures), "goal-resume"])
        self.assertEqual(code, 0, stream.getvalue())
        state = json.loads(stream.getvalue())
        self.assertEqual(state["root_task_id"], root)
        self.assertEqual(state["original_goal"], goal)

    def test_no_open_goal_does_not_invent_implicit_owner_authority(self):
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "fixture", "old": "a", "new": "b"})
        self.assertEqual(self.recover()["status"], "NO_DURABLE_GOAL")

    def test_missing_db_is_never_implicitly_initialized(self):
        missing = self.home / "missing.sqlite"
        self.assertEqual(
            resume_goal(missing, workspace=self.workspace, fixtures=self.fixtures)
            ["status"], "LEDGER_NOT_INITIALIZED")
        self.assertFalse(missing.exists())
