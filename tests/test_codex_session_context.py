"""Independent process tests for real Codex lifecycle rehydration (no hook simulation of effects)."""
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import alter_authority, connect, create_task, initialize

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts" / "codex_session_context.py"


class CodexSessionContext(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.db = self.tmp / "state.sqlite"
        self.ws = self.tmp / "workspace"
        self.fixtures = self.tmp / "fixtures"
        self.ws.mkdir()
        self.fixtures.mkdir()
        (self.fixtures / "settings.json").write_text(
            '{"timeout":7}\n', encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)

    def _run(self, *, cwd=None, with_database=True, vars=None):
        environ = dict(os.environ)
        environ.pop("COGNITION_AGENT_OS_DB", None)
        environ.pop("COGNITION_AGENT_OS_WORKSPACE", None)
        environ.pop("COGNITION_AGENT_OS_FIXTURES", None)
        if with_database:
            environ.update({
                "COGNITION_AGENT_OS_DB": str(self.db),
                "COGNITION_AGENT_OS_WORKSPACE": str(self.ws),
                "COGNITION_AGENT_OS_FIXTURES": str(self.fixtures),
            })
        environ.update(vars or {})
        p = subprocess.run(
            [sys.executable, str(HOOK)],
            cwd=ROOT, input=json.dumps({"cwd": str(cwd or ROOT), "source": "startup"}),
            text=True, capture_output=True, env=environ, timeout=8)
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(
            result["hookSpecificOutput"]["hookEventName"], "SessionStart")
        msg = result["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(msg.startswith("Read-only project state observation"), msg)
        return json.loads(msg.partition(": ")[-1])

    def test_missing_source_never_invents_owner_goal(self):
        result = self._run(with_database=False)
        self.assertEqual(result["status"], "NO_LOCAL_LEDGER_CONFIGURED")
        self.assertFalse(result["original_goal_verified"])
        self.assertNotIn("original_goal", result)

    def test_cold_restart_resumes_exact_original_goal_without_new_ledger(self):
        goal = "Compare actual.csv with baseline.csv and report differences."
        with closing(connect(self.db)) as db:
            root = create_task(db, {"kind":"open_goal", "goal":goal})
            pre = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        first = self._run()
        second = self._run()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "READY_TO_TICK")
        self.assertEqual(first["root_task_id"], root)
        self.assertEqual(first["original_goal"], goal)
        self.assertTrue(first["original_goal_verified"])
        self.assertFalse(first["business_outcome_verified"])
        self.assertEqual(first["next_task_id"], root)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events").fetchone()[0], pre)

    def test_revocation_cannot_be_laundered_into_session_permission(self):
        with closing(connect(self.db)) as db:
            create_task(db, {"kind":"open_goal",
                             "goal":"Compare actual.csv with baseline.csv and report differences."})
            alter_authority(db, revoke=True)
        state = self._run()
        self.assertEqual(state["status"], "AUTHORITY_REVOKED")
        self.assertNotIn("next_task_id", state)
        self.assertFalse(state["business_outcome_verified"])

    def test_real_source_and_output_replay_after_effect(self):
        goal = ("Please ensure a sandbox draft of settings.json has owner "
                "equal to ops, preserving the existing timeout.")
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "open_goal", "goal": goal})
        run_tick(self.db, self.ws, self.fixtures,
                 max_jobs=2, auto_stage_goals=True)
        verified = self._run()
        self.assertEqual(verified["status"], "LOCAL_OWNER_RESULT_VERIFIED", verified)
        self.assertTrue(verified["local_owner_outcome_verified"])
        self.assertFalse(verified["business_outcome_verified"])
        # Current output must be read again; a historical success is not authority.
        files = list((self.ws / "sandbox").glob("*.candidate"))
        self.assertEqual(len(files), 1)
        files[0].write_text('{"timeout":7,"owner":"tampered"}\n', encoding="utf-8")
        invalid = self._run()
        self.assertFalse(invalid["local_owner_outcome_verified"])
        self.assertNotEqual(invalid["status"], "LOCAL_OWNER_RESULT_VERIFIED")
        self.assertNotIn("next_task_id", invalid)

    def test_wrong_checkout_never_receives_private_owner_context(self):
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "open_goal",
                             "goal": "Compare actual.csv with baseline.csv and report differences."})
        state = self._run(cwd=self.tmp)
        self.assertEqual(state["status"], "HOOK_OUTSIDE_REPOSITORY")
        self.assertNotIn("original_goal", state)

    def test_hook_lifecycle_registration_and_entry_path(self):
        config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        events = config["hooks"]["SessionStart"]
        self.assertEqual(len(events), 1)
        self.assertIn("compact", events[0]["matcher"])
        self.assertIn("resume", events[0]["matcher"])
        self.assertEqual(len(events[0]["hooks"]), 1)
        self.assertIn("codex_session_context.py", events[0]["hooks"][0]["command"])
