"""End-to-end SAME GOAL must be checked from the actual staged effect.

Tests deliberately use the existing host/worker/ledger/sandbox/reviewer rather
than a test-only controller or asserted planner result.  No production writes.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.host import run_tick
from cognition_agent_os.outcome_feedback import register_evidence_goal, verify_feedback_root

_EFFECT = "LOCAL_SANDBOX_POSTCONDITION"
_ACCEPT = {"kind":"exact_record_postcondition","identity_fields":["id"],
           "target_record":{"id":"A","owner":"ops"}}


class PostEffectFeedback(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.db=root/"ledger.db"
        self.work=root/"workspace"
        self.work.mkdir()
        self.fx=root/"source"
        self.fx.mkdir()
        (self.fx/"first.json").write_text('{"id":"A","owner":"wrong"}')
        (self.fx/"second.csv").write_text("id\nA\n")
        with closing(connect(self.db)) as db:
            initialize(db)

    def methods(self):
        return [
            {"kind":"goal_case","goal_type":"json_keys","input":"first.json",
             "desired":{"owner":"ops"}},
            {"kind":"goal_case","goal_type":"csv_columns","input":"second.csv",
             "desired":{"owner":"ops"}},
        ]

    def register(self, **kw):
        return register_evidence_goal(
            self.db,self.fx,goal_id="actual-effect-goal",
            objective="Stage record A with owner ops and verify actual staged bytes",
            alternatives=self.methods(),acceptance=_ACCEPT,
            execution_scope=_EFFECT,**kw)

    def tick(self, *, stage=True, control=True):
        return run_tick(self.db,self.work,self.fx,max_jobs=4,
                        auto_local_goal_control=control,
                        auto_stage_goals=stage)

    def children(self, tid):
        with closing(connect(self.db)) as db:
            return [dict(x) for x in db.execute(
                "SELECT * FROM tasks WHERE parent_task=? ORDER BY created_at,task_id",
                (tid,)).fetchall()]

    def row(self, tid):
        with closing(connect(self.db)) as db:
            return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())

    def test_real_posteffect_readback_then_distinct_fallback(self):
        tid=self.register()
        self.tick()           # first method admitted
        first=self.tick()     # first source conflicts; alternate admitted
        self.assertEqual(first["tasks"][0]["reason"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual(len(self.children(tid)),2)
        second=self.tick()    # candidate staged in SAME host tick
        children=self.children(tid)
        self.assertEqual(children[-1]["state"],"SANDBOX_VERIFIED",second)
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        physical=self.work/"sandbox"/(children[-1]["task_id"]+".candidate")
        self.assertTrue(physical.is_file())
        self.assertIn(b"A,ops",physical.read_bytes())
        self.assertEqual(self.row(tid)["error_code"],"SHARED_SANDBOX_POSTCONDITION_MET")
        self.assertFalse(second["semantic_outcome_verified"])
        with closing(connect(self.db)) as db:
            verified=verify_feedback_root(db,db.execute("SELECT * FROM tasks WHERE task_id=?",
                                                    (tid,)).fetchone(),self.db,self.work,self.fx)
        self.assertTrue(verified["valid"],verified)
        self.assertEqual((self.fx/"second.csv").read_text(),"id\nA\n")

    def test_proposal_alone_cannot_finish_when_staging_not_opted_in(self):
        tid=self.register()
        self.tick(stage=False)
        self.tick(stage=False)
        third=self.tick(stage=False)
        self.assertEqual(third["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_ACTIVE")
        self.assertFalse((self.work/"sandbox").exists())
        self.tick(stage=True)
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")

    def test_corrupted_posteffect_bytes_refuse_root_acceptance(self):
        tid=self.register()
        for _ in range(3):self.tick()
        child=self.children(tid)[-1]["task_id"]
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        (self.work/"sandbox"/(child+".candidate")).write_bytes(b"id,owner\nA,wrong\n")
        with closing(connect(self.db)) as db:
            report=verify_feedback_root(db,db.execute(
                "SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone(),
                self.db,self.work,self.fx)
        self.assertFalse(report["valid"],report)

    def test_stale_or_revoked_effect_never_completes(self):
        tid=self.register()
        self.tick(stage=False)             # first admitted
        self.tick(stage=False)             # second admitted
        self.tick(stage=False)             # second candidate not yet staged
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        self.tick(stage=True)
        self.assertNotEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertFalse((self.work/"sandbox").exists())

    def test_existing_production_path_is_unmodified(self):
        tid=self.register()
        for _ in range(3):self.tick()
        assert (self.fx/"first.json").read_text()=='{"id":"A","owner":"wrong"}'
        self.assertEqual((self.fx/"second.csv").read_text(),"id\nA\n")
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")

    def test_cold_process_execution_and_optin_contract(self):
        spec={"goal_id":"cold-posteffect","objective":"staged A owner ops",
              "alternatives":self.methods(),"acceptance":_ACCEPT,
              "execution_scope":_EFFECT}
        specfile=self.fx.parent/"intake.json"
        specfile.write_text(json.dumps(spec))
        common=[sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(self.db),"--workspace",str(self.work),
                "--fixtures",str(self.fx)]
        seed=subprocess.run(common+["seed-evidence-feedback","--spec",str(specfile)],
                            capture_output=True,text=True,check=True)
        tid=json.loads(seed.stdout)["task_id"]
        for _ in range(3):
            subprocess.run(common+["host-tick","--auto-local-goal-control",
                                    "--auto-stage-goals","--max-jobs","4"],
                           capture_output=True,text=True,check=True)
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertEqual(len(self.children(tid)),2)

    def test_v2_legacy_semantics_unchanged(self):
        tid=register_evidence_goal(self.db,self.fx,goal_id="legacy-v2",
            objective="Only local candidate evidence",alternatives=self.methods(),
            acceptance=_ACCEPT)
        for _ in range(3):
            self.tick(stage=False)
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertFalse((self.work/"sandbox").exists())
        self.assertEqual(json.loads(self.row(tid)["source_spec"])["version"],2)

if __name__=="__main__":
    unittest.main()
