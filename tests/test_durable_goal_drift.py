"""OT13: real-ledger goal drift observations, no second scheduler or authority."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.goal_drift import observe_owner_goal_drift
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import (
    connect, initialize, create_task, alter_authority, LedgerNotConfigured,
)


class DurableOwnerGoalDriftTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "ledger.sqlite"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.sources = self.root / "source"
        self.sources.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)

    def seed(self, state="DECOMPOSED", goal="Investigate a novel workflow.",
             child=None, kind="open_goal"):
        with closing(connect(self.db)) as db:
            tid = create_task(db, {"kind": kind, "goal": goal})
            db.execute("UPDATE tasks SET state=? WHERE task_id=?", (state, tid))
            if child is not None:
                cid = create_task(db, child, parent=tid, commit=False)
                db.execute("UPDATE tasks SET state='NEEDS_REVIEW' WHERE task_id=?",
                           (cid,))
            db.commit()
        return tid

    def events(self, tid):
        with closing(connect(self.db)) as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT details FROM events WHERE task_id=? AND "
                "kind='OWNER_GOAL_DRIFT_SIGNAL' ORDER BY event_id", (tid,))]

    def test_research_only_is_not_silently_counted_as_owner_success(self):
        tid = self.seed(child={"kind": "investigate_goal",
                               "question": "What is an applicable method?",
                               "scope": "LOCAL_EVIDENCE_ONLY"})
        found = observe_owner_goal_drift(self.db)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["fidelity_state"],
                         "EVIDENCE_RESEARCH_ONLY_NOT_OWNER_RESULT")
        self.assertFalse(found[0]["owner_outcome_verified"])
        self.assertFalse(found[0]["automatically_approved"])
        self.assertEqual(len(self.events(tid)), 1)
        self.assertNotIn("Investigate a novel workflow.",
                         json.dumps(self.events(tid)))

    def test_restart_and_no_change_are_idempotent(self):
        tid = self.seed(state="UNKNOWN")
        first = observe_owner_goal_drift(self.db)
        self.assertEqual(first[0]["fidelity_state"],
                         "OWNER_GOAL_BLOCKED_WITHOUT_RESULT")
        self.assertEqual(observe_owner_goal_drift(self.db), [])
        self.assertEqual(len(self.events(tid)), 1)

    def test_changed_local_evidence_generates_new_signal_once(self):
        tid = self.seed(child={"kind": "investigate_goal",
                               "question": "What is relevant?", "scope": "LOCAL_EVIDENCE_ONLY"})
        first = observe_owner_goal_drift(self.db)
        self.assertEqual(len(first), 1)
        with closing(connect(self.db)) as db:
            db.execute("UPDATE tasks SET state='VERIFIED' WHERE parent_task=?", (tid,))
            db.commit()
        second = observe_owner_goal_drift(self.db)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["observation_sha256"],
                            second[0]["observation_sha256"])
        self.assertEqual(observe_owner_goal_drift(self.db), [])
        self.assertEqual(len(self.events(tid)), 2)

    def test_revocation_fences_drift_writes_and_keeps_other_goals_safe(self):
        tid = self.seed(state="UNKNOWN")
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        response = observe_owner_goal_drift(self.db)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["status"], "NOT_ADMITTED")
        self.assertEqual(self.events(tid), [])

    def test_missing_database_is_not_silently_created_by_drift_observer(self):
        missing = self.root / "not-provisioned.sqlite"
        with self.assertRaises(LedgerNotConfigured):
            observe_owner_goal_drift(missing)
        self.assertFalse(missing.exists())

    def test_non_owner_fixture_jobs_do_not_become_spurious_owner_alerts(self):
        tid = self.seed(state="UNKNOWN", kind="fixture")
        self.assertEqual(observe_owner_goal_drift(self.db), [])
        self.assertEqual(self.events(tid), [])

    def test_fair_scan_reaches_owner_root_beyond_unrelated_jobs(self):
        with closing(connect(self.db)) as db:
            for idx in range(25):
                create_task(db, {"kind": "fixture", "goal": "non-owner %d" % idx})
        target = self.seed(state="UNKNOWN")
        all_results = []
        for _ in range(12):
            all_results.extend(observe_owner_goal_drift(self.db, limit=4))
        self.assertEqual(len(self.events(target)), 1, all_results)

    def test_real_host_tick_emits_durable_signal_without_manual_observation(self):
        with closing(connect(self.db)) as db:
            tid = create_task(db, {
                "kind": "open_goal",
                "goal": "Investigate what should be done with a new system failure."})
        # There are no local source files; the executor cannot manufacture a
        # research success. Host independently records the owner-level blockage.
        one = run_tick(self.db, self.workspace, self.sources, max_jobs=1)
        self.assertEqual(one["tasks"][0]["status"], "UNKNOWN", one)
        self.assertEqual(len(one["owner_goal_drift"]), 1, one)
        self.assertEqual(one["owner_goal_drift"][0]["root_task_id"], tid)
        two = run_tick(self.db, self.workspace, self.sources, max_jobs=1)
        self.assertEqual(two["owner_goal_drift"], [], two)
        self.assertEqual(len(self.events(tid)), 1)


if __name__ == "__main__":
    unittest.main()
