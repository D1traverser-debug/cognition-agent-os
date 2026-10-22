"""Host tests exercise real subprocess startup, persisted DB, and overdue jobs."""
from __future__ import annotations

import json
from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from cognition_agent_os.host import HostNotConfigured, run_tick
from cognition_agent_os.ledger import alter_authority, connect, create_task, initialize
from cognition_agent_os.runner import verify_artifact

ROOT = Path(__file__).resolve().parents[1]


class LocalHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.fixtures = self.base / "fixtures"
        self.fixtures.mkdir()
        (self.fixtures / "old.txt").write_text("old\n")
        (self.fixtures / "new.txt").write_text("new\n")
        self.db = self.base / "state.sqlite"
        self.workspace = self.base / "output"

    def seed(self, *, old="old.txt", new="new.txt", interval=0, due_at=None):
        db = connect(self.db)
        try:
            initialize(db)
            return create_task(db, {"kind":"fixture", "old":old, "new":new},
                               interval_seconds=interval, due_at=due_at)
        finally:
            db.close()

    def test_goal_progress_tracks_unrelated_roots_without_claiming_success(self):
        from cognition_agent_os.host import _goal_progress
        with closing(connect(self.db)) as db:
            initialize(db)
            root_a=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"})
            root_b=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"})
            child=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"},parent=root_a)
            db.execute("UPDATE tasks SET state='NEEDS_REVIEW' WHERE task_id=?",(child,))
            db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",(root_b,))
            db.commit()
        report=_goal_progress(self.db)
        self.assertEqual(len(report["goals"]),2)
        by_root={g["root_task_id"]:g for g in report["goals"]}
        self.assertEqual(by_root[root_a]["runnable"],1)
        self.assertEqual(by_root[root_a]["awaiting_review"],1)
        self.assertEqual(by_root[root_a]["next_control_action"],"CONTINUE_ADMITTED_WORK")
        self.assertEqual(by_root[root_b]["next_control_action"],"DIAGNOSE_BLOCKER")
        self.assertFalse(report["semantic_outcome_verified"])
        with closing(connect(self.db)) as db:
            db.execute("UPDATE authority SET grant_rev=grant_rev+1")
            db.commit()
        revoked=_goal_progress(self.db)
        self.assertTrue(all(g["next_control_action"]=="REAUTHORIZE_OR_SUPERSEDE"
                            for g in revoked["goals"]))

    def test_host_prioritizes_current_goal_over_older_stale_task(self):
        with closing(connect(self.db)) as db:
            initialize(db)
            stale=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"},
                              due_at=1)
            db.execute("UPDATE authority SET goal_rev=goal_rev+1")
            valid=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"},
                              due_at=2)
            db.commit()
        first=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(first["tasks"][0]["task_id"],valid,first)
        self.assertEqual(first["tasks"][0]["status"],"NEEDS_REVIEW",first)
        second=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(second["tasks"][0]["task_id"],stale,second)
        self.assertEqual(second["tasks"][0]["status"],"BLOCKED",second)

    def cli(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run([
            sys.executable, "-m", "cognition_agent_os.cli",
            "--db", str(self.db), "--workspace", str(self.workspace),
            "--fixtures", str(self.fixtures), "host-tick", "--max-jobs", "16"
        ], capture_output=True, text=True, timeout=20, env=env)

    def test_unseeded_host_does_not_create_write_authority(self):
        with self.assertRaises(HostNotConfigured):
            run_tick(self.db, self.workspace, self.fixtures)
        self.assertFalse(self.db.exists())

    def test_subprocess_tick_processes_and_restart_does_not_replay(self):
        first = self.seed()
        second = self.seed(old="old.txt", new="old.txt")
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["processed"], 2)
        self.assertEqual({x["status"] for x in report["tasks"]}, {"VERIFIED", "NEEDS_REVIEW"})
        restarted = self.cli()
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertEqual(json.loads(restarted.stdout)["status"], "IDLE")
        db = connect(self.db)
        try:
            rows = {r["task_id"]: dict(r) for r in db.execute("SELECT * FROM tasks")}
            self.assertEqual(rows[first]["state"], "NEEDS_REVIEW")
            self.assertTrue(verify_artifact(self.workspace, rows[first]))
            self.assertEqual(rows[second]["state"], "VERIFIED")
            obs = db.execute("SELECT * FROM host_ticks").fetchone()
            self.assertEqual((obs["ticks"], obs["processed_total"]), (2,2))
        finally:
            db.close()

    def test_missed_tick_runs_overdue_recurrence_once(self):
        self.seed(old="old.txt", new="old.txt", interval=3600)
        self.assertEqual(run_tick(self.db, self.workspace, self.fixtures)["processed"], 1)
        db = connect(self.db)
        try:
            pending = db.execute("SELECT task_id FROM tasks WHERE state='PENDING'").fetchone()["task_id"]
            db.execute("UPDATE tasks SET due_at=? WHERE task_id=?", (time.time()-7200, pending))
            db.commit()
        finally:
            db.close()
        self.assertEqual(self.cli().returncode, 0)
        db = connect(self.db)
        try:
            rows = [dict(r) for r in db.execute("SELECT * FROM tasks")]
            self.assertEqual(len(rows), 3)
            self.assertEqual(sum(r["state"] == "VERIFIED" for r in rows), 2)
            future = [r for r in rows if r["state"] == "PENDING"]
            self.assertEqual(len(future), 1)
            self.assertGreater(future[0]["due_at"], time.time())
        finally:
            db.close()

    def test_revoked_write_is_not_reenabled_by_host(self):
        self.seed()
        db = connect(self.db)
        alter_authority(db, revoke=True)
        db.close()
        result = run_tick(self.db, self.workspace, self.fixtures)
        self.assertEqual(result["tasks"][0]["status"], "BLOCKED")
        self.assertFalse((self.workspace / "artifacts").exists())

    def test_bounded_work_does_not_drop_remainder(self):
        self.seed(); self.seed(); self.seed()
        first = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual((first["processed"], first["capacity_reached"]), (1,True))
        second = run_tick(self.db, self.workspace, self.fixtures, max_jobs=2)
        self.assertEqual(second["processed"], 2)
        self.assertEqual(run_tick(self.db, self.workspace, self.fixtures)["status"], "IDLE")

    def test_config_is_fail_closed(self):
        self.seed()
        for bound in [0, 65]:
            with self.assertRaises(ValueError):
                run_tick(self.db, self.workspace, self.fixtures, max_jobs=bound)


if __name__ == "__main__":
    unittest.main()
