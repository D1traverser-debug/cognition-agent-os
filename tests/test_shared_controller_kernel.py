"""Architecture-level conformance for the ONE durable controller kernel.

Test invariants across both existing adapter interfaces, not their summaries.
"""
from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cognition_agent_os.ledger import (
    connect, create_task, initialize, alter_authority,
)
from cognition_agent_os.control_kernel import drive_active_controller
from cognition_agent_os.outcome_feedback import _ensure as feedback_setup
from cognition_agent_os.bounded_goal_control import _ensure as legacy_setup


class AuthoritativeKernelInvariants(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db_path=Path(t.name)/"ledger.sqlite"
        with closing(connect(self.db_path)) as db:
            initialize(db)

    def roots(self, n, state="FEEDBACK_ACTIVE"):
        ids=[]
        with closing(connect(self.db_path)) as db:
            for i in range(n):
                tid=create_task(
                    db, {"kind":"fixture", "old":f"a{i}", "new":f"b{i}"})
                db.execute("UPDATE tasks SET state=? WHERE task_id=?",
                           (state,tid))
                ids.append(tid)
            db.commit()
        return ids

    def tick(self, *, limit=4, state="FEEDBACK_ACTIVE", step=None,
             on_denied=None):
        family=("evidence_feedback_cursor" if state=="FEEDBACK_ACTIVE"
                else "bounded_control_scan_cursor")
        setup=feedback_setup if state=="FEEDBACK_ACTIVE" else legacy_setup
        return drive_active_controller(
            self.db_path, active_state=state, cursor_table=family,
            limit=limit, setup=setup, step=step,
            on_denied=on_denied or (lambda db,root,reason:
                {"status":"DENIED","reason":reason}))

    def test_round_robin_advances_all_authorized_roots(self):
        roots=self.roots(5)
        visited=[]
        def consume(db,root):
            visited.append(root["task_id"])
            db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",
                       (root["task_id"],))
            return {"status":"CONTROLLED_LOCAL_STEP","task_id":root["task_id"]}
        a=self.tick(limit=2,step=consume)
        b=self.tick(limit=2,step=consume)
        c=self.tick(limit=2,step=consume)
        self.assertEqual([len(a),len(b),len(c)],[2,2,1])
        self.assertEqual(set(visited),set(roots))
        self.assertEqual(len(visited),5)

    def test_uncommitted_child_rolls_back_with_failed_transition(self):
        root=self.roots(1)[0]
        def broken(db,task):
            create_task(
                db,{"kind":"fixture","old":"orphan","new":"orphan2"},
                parent=task["task_id"],commit=False)
            raise RuntimeError("crash before completed receipt")
        with self.assertRaisesRegex(RuntimeError,"crash"):
            self.tick(step=broken)
        with closing(connect(self.db_path)) as db:
            root_state=db.execute(
                "SELECT state FROM tasks WHERE task_id=?",(root,)
            ).fetchone()[0]
            children=db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",(root,)
            ).fetchone()[0]
        self.assertEqual(root_state,"FEEDBACK_ACTIVE")
        self.assertEqual(children,0)

    def test_authority_revoke_cannot_be_overridden_by_adapter(self):
        self.roots(1)
        with closing(connect(self.db_path)) as db:
            alter_authority(db,revoke=True)
        def executable(*_args):
            self.fail("revoked grant reached executable domain callback")
        seen=[]
        def denied(db,root,reason):
            self.assertIn("REVOK",reason.upper())
            seen.append(root["task_id"])
            return {"status":"DENIED"}
        self.assertEqual(self.tick(step=executable,on_denied=denied)[0]["status"],
                         "DENIED")
        self.assertEqual(len(seen),1)

    def test_family_cursor_contract_not_inferred_from_untrusted_inputs(self):
        def step(*_args):
            raise AssertionError("invalid family must not execute callback")
        for state,cursor in (
            ("FEEDBACK_ACTIVE","bounded_control_scan_cursor"),
            ("FEEDBACK_ACTIVE","evidence_feedback_cursor;DROP TABLE tasks"),
            ("CUSTOM_ACTIVE","evidence_feedback_cursor"),
        ):
            with self.subTest(state=state,cursor=cursor):
                with self.assertRaises(ValueError):
                    drive_active_controller(
                        self.db_path, active_state=state,
                        cursor_table=cursor,limit=1,
                        setup=feedback_setup,step=step,
                        on_denied=lambda *_: {"status":"DENIED"})

    def test_both_legacy_and_feedback_adapters_share_one_kernel(self):
        import inspect
        from cognition_agent_os.bounded_goal_control import advance_local_goals
        from cognition_agent_os.outcome_feedback import advance_evidence_goals
        for fn in (advance_local_goals,advance_evidence_goals):
            code=inspect.getsource(fn)
            self.assertIn("drive_active_controller(",code)
            self.assertNotIn("BEGIN IMMEDIATE",code)
        # Both families route through the same grant/cursor/transaction core.
        from cognition_agent_os import control_kernel
        self.assertIn("current_guard(",inspect.getsource(
            control_kernel.drive_active_controller))
        self.assertIn("BEGIN IMMEDIATE",inspect.getsource(
            control_kernel.drive_active_controller))


if __name__=="__main__":
    unittest.main()
