"""Regression tests for systemic fail-closed governance.

These tests target concrete P10 prior fail-open paths, not a new demo
domain: dependency fanout overflow and effects before integrity inspection.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from cognition_agent_os.conformance import (
    capability_disabled, effect_preflight, inspect_conformance,
)
from cognition_agent_os.ledger import connect, create_task, initialize
from cognition_agent_os.runner import run_once
from cognition_agent_os.sandbox_effect import stage_one
from cognition_agent_os.host import run_tick


class GovernanceFailClosedTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home=Path(tmp.name)
        self.fx=self.home/"fixtures"; self.fx.mkdir()
        self.out=self.home/"workspace"; self.out.mkdir()
        self.dbpath=self.home/"state.sqlite"
        db=connect(self.dbpath); initialize(db); db.close()

    def _spec(self,name="config.json"):
        return {"kind":"goal_case","goal_type":"json_keys",
                "input":name,"desired":{"owner":"ops"}}

    def _seed(self, name="config.json", *, parent=None):
        db=connect(self.dbpath)
        try: return create_task(db,self._spec(name),parent=parent)
        finally: db.close()

    def _record(self,tid):
        db=connect(self.dbpath)
        try:
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
            return dict(row)
        finally:db.close()

    def _grant(self):
        db=connect(self.dbpath)
        try:return dict(db.execute("SELECT * FROM authority WHERE singleton=1").fetchone())
        finally:db.close()

    def _events(self,tid,kind):
        db=connect(self.dbpath)
        try:return [dict(r) for r in db.execute(
            "SELECT * FROM events WHERE task_id=? AND kind=?",(tid,kind))]
        finally:db.close()

    def _staged(self,name="config.json"):
        self.fx.joinpath(name).write_text("{}")
        tid=self._seed(name)
        self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(stage_one(self.dbpath,self.out,self.fx,tid)["status"],"SANDBOX_VERIFIED")
        return tid

    def test_unbounded_lineage_revokes_write_grant_and_blocks_new_effect(self):
        self.fx.joinpath("config.json").write_text("{}")
        db=connect(self.dbpath)
        root=create_task(db,{"kind":"goal_intent","objective":"ensure_structure",
             "resources":[{"role":"input","path":"config.json"}],
             "requirements":[{"field":"owner","equals":"ops"}]})
        # Invalid DECOMPOSED parent also has >256 descendants.
        for i in range(259):
            create_task(db,self._spec(),parent=root,commit=False)
        db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",(root,))
        db.commit();db.close()
        result=inspect_conformance(self.dbpath,self.out,self.fx,
                                   enforce=True,max_cases=1)
        self.assertEqual(result["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(result["emergency_stops"],[root])
        self.assertEqual(result["findings"][0]["enforcement"],"EMERGENCY_STOP")
        self.assertEqual(self._record(root)["state"],"UNKNOWN")
        self.assertEqual(self._grant()["write_allowed"],0)
        self.assertTrue(capability_disabled(self.dbpath))
        self.assertEqual(len(self._events(root,"CONFORMANCE_EMERGENCY_STOP")),1)
        second=inspect_conformance(self.dbpath,self.out,self.fx,enforce=True,max_cases=1)
        self.assertEqual(second["emergency_stops"],[])
        self.assertEqual(len(self._events(root,"CONFORMANCE_EMERGENCY_STOP")),1)
        # Previously issued descendants are not falsely called reviewed, but
        # no valid write grant exists for any of them.
        due=run_once(self.dbpath,self.out,self.fx)
        self.assertIn(due["status"],("BLOCKED","UNKNOWN","IDLE"))
        self.assertEqual(self._grant()["write_allowed"],0)

    def test_dependency_cycle_emergency_stop_without_recursive_overflow(self):
        self.fx.joinpath("config.json").write_text("{}")
        db=connect(self.dbpath)
        root=create_task(db,{"kind":"goal_intent","objective":"ensure_structure",
             "resources":[{"role":"input","path":"config.json"}],
             "requirements":[{"field":"owner","equals":"ops"}]})
        child=create_task(db,self._spec(),parent=root)
        db.execute("UPDATE tasks SET parent_task=?,state='DECOMPOSED' WHERE task_id=?",
                   (child,root))
        db.commit();db.close()
        report=inspect_conformance(self.dbpath,self.out,self.fx,enforce=True,max_cases=1)
        self.assertEqual(report["emergency_stops"],[root])
        self.assertEqual(self._grant()["write_allowed"],0)
        self.assertTrue(capability_disabled(self.dbpath))

    def test_host_preflight_detects_previous_tamper_before_new_stage(self):
        old=self._staged("old.json")
        oldpath=self.out/"sandbox"/(old+".candidate")
        oldpath.write_text("FORGED")
        self.fx.joinpath("new.json").write_text("{}")
        new=self._seed("new.json")
        tick=run_tick(self.dbpath,self.out,self.fx,auto_stage_goals=True)
        self.assertFalse(tick["preflight"]["admitted"])
        self.assertEqual(tick["preflight"]["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(self._record(old)["state"],"UNKNOWN")
        self.assertEqual(self._record(new)["state"],"NEEDS_REVIEW")
        self.assertFalse((self.out/"sandbox"/(new+".candidate")).exists())
        self.assertTrue(capability_disabled(self.dbpath))

    def test_manual_stage_cannot_bypass_previous_tampered_receipt(self):
        old=self._staged("old.json")
        db=connect(self.dbpath)
        db.execute("UPDATE events SET details=? WHERE task_id=? AND kind=?",
                   ('{"scope":"isolated_workspace_only","effect_sha256":"forged"}',
                    old,"SANDBOX_EFFECT_VERIFIED"))
        db.commit();db.close()
        self.fx.joinpath("new.json").write_text("{}")
        new=self._seed("new.json")
        self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"NEEDS_REVIEW")
        result=stage_one(self.dbpath,self.out,self.fx,new)
        self.assertEqual(result["status"],"PREFLIGHT_BLOCKED")
        self.assertEqual(result["preflight_status"],"CONFORMANCE_VIOLATIONS")
        self.assertTrue(capability_disabled(self.dbpath))
        self.assertFalse((self.out/"sandbox"/(new+".candidate")).exists())

    def test_unscanned_claims_block_effects_instead_of_claiming_full_coverage(self):
        self.fx.joinpath("stable.json").write_text('{"owner":"ops"}')
        db=connect(self.dbpath)
        for i in range(513):
            create_task(db,self._spec("stable.json"),commit=False)
        db.execute("""UPDATE tasks SET state='VERIFIED',
                 decision='GOAL_ALREADY_SATISFIED' WHERE state='PENDING'""")
        db.commit();db.close()
        self.fx.joinpath("fresh.json").write_text("{}")
        new=self._seed("fresh.json")
        self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"NEEDS_REVIEW")
        result=stage_one(self.dbpath,self.out,self.fx,new)
        self.assertEqual(result["status"],"PREFLIGHT_BLOCKED")
        self.assertTrue(result["capacity_reached"])
        self.assertFalse((self.out/"sandbox"/(new+".candidate")).exists())
        self.assertFalse(capability_disabled(self.dbpath))
        self.assertEqual(self._grant()["write_allowed"],1)

    def test_normal_source_drift_is_not_a_forged_effect(self):
        self.fx.joinpath("config.json").write_text("{}")
        tid=self._seed()
        self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"NEEDS_REVIEW")
        self.fx.joinpath("config.json").write_text('{"outside":"changed"}')
        audit=effect_preflight(self.dbpath,self.out,self.fx)
        self.assertEqual(audit["status"],"EVIDENCE_INSUFFICIENT")
        self.assertTrue(audit["admitted"])
        self.assertFalse(capability_disabled(self.dbpath))
        nextstep=stage_one(self.dbpath,self.out,self.fx,tid)
        self.assertEqual(nextstep["status"],"REPLAN_QUEUED")
        self.assertEqual(self._grant()["write_allowed"],1)
        self.assertFalse((self.out/"sandbox"/(tid+".candidate")).exists())


if __name__=="__main__":
    unittest.main()
