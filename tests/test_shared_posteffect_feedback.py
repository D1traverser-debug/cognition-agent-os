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

    def test_first_staged_mechanically_valid_wrong_target_selects_alternative(self):
        # Executing a structurally correct proposal does not establish
        # the precommitted exact target if it preserves extra fields.
        (self.fx/"first.json").write_text('{"id":"A","department":"north"}')
        tid=self.register()
        self.tick()
        first_effect=self.tick()
        self.assertEqual(self.children(tid)[0]["state"],"SANDBOX_VERIFIED",
                         first_effect)
        self.assertEqual(len(self.children(tid)),2)
        self.assertNotEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        next_effect=self.tick()
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY",
                         next_effect)
        self.assertEqual(len(self.children(tid)),2)

    def test_noop_still_verifies_actual_existing_record_without_writing(self):
        (self.fx/"first.json").write_text('{"id":"A","owner":"ops"}')
        tid=self.register()
        self.tick()
        self.tick()
        self.assertEqual(self.children(tid)[0]["state"],"VERIFIED")
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertFalse((self.work/"sandbox").exists())

    def test_source_mutation_after_staged_effect_revokes_readback(self):
        tid=self.register()
        for _ in range(3):self.tick()
        self.assertEqual(self.row(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        (self.fx/"second.csv").write_text("id\\nB\\n".replace("\\n","\n"))
        with closing(connect(self.db)) as db:
            result=verify_feedback_root(db,db.execute(
                "SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone(),
                self.db,self.work,self.fx)
        self.assertFalse(result["valid"],result)

    def test_scope_is_explicit_and_cannot_self_authorize_external_action(self):
        for scope in ("PRODUCTION_WRITE","NETWORK_MUTATION","LOCAL_SANDBOX_ONLY"):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    register_evidence_goal(self.db,self.fx,goal_id="deny",
                        objective="no external effect",alternatives=self.methods(),
                        acceptance=_ACCEPT,execution_scope=scope)
        with self.assertRaises(ValueError):
            register_evidence_goal(self.db,self.fx,goal_id="deny",
                objective="no acceptance",alternatives=self.methods(),
                execution_scope=_EFFECT)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],0)

    def test_separate_owner_blackbox_rechecks_executed_file_without_planner_status(self):
        # The evaluator is implemented outside src/cognition_agent_os, gets
        # only precommitted owner target and actual staged bytes, not a plan,
        # controller state, receipt or self-grader output.
        root=Path(__file__).resolve().parents[1]
        sys.path.insert(0,str(root/"evaluation"))
        from owner_outcome_oracle import evaluate_shared_record_goal
        inputs=self.methods()
        original_csv=(self.fx/"second.csv").read_bytes()
        frozen={"schema_version":1,"goal_id":"owner-held-posteffect",
                "canonical_record":_ACCEPT["target_record"],
                "source_sha256":{
                    "json_keys":hashlib.sha256((self.fx/"first.json").read_bytes()).hexdigest(),
                    "csv_columns":hashlib.sha256(original_csv).hexdigest()},
                "allowed_effect":"LOCAL_CANDIDATE_ONLY"}
        tid=self.register()
        for _ in range(3):self.tick()
        child=self.children(tid)[-1]["task_id"]
        effect=(self.work/"sandbox"/(child+".candidate")).read_bytes()
        result=evaluate_shared_record_goal(
            frozen,"csv_columns",original_csv,effect)
        self.assertEqual(result["status"],"SYNTHETIC_SHARED_GOAL_MET",result)
        self.assertFalse(result["business_outcome_verified"])
        self.assertEqual(evaluate_shared_record_goal(
            frozen,"csv_columns",original_csv,b"id,owner\\nB,ops\\n".replace(b"\\n",b"\n"))
                         ["status"],"NOT_ACCEPTED")

    def test_effect_swap_after_receipt_review_cannot_be_accepted(self):
        # A race after the trusted stage checker returns must not promote
        # semantically equivalent but unreceipted bytes.
        from unittest.mock import patch
        from cognition_agent_os.outcome_feedback import _outcome
        from cognition_agent_os.conformance import _verify_staged
        tid=self.register()
        self.tick()
        self.tick()
        self.tick(control=False)
        child=self.row(self.children(tid)[-1]["task_id"])
        self.assertEqual(child["state"],"SANDBOX_VERIFIED")
        staged=self.work/"sandbox"/(child["task_id"]+".candidate")
        before=staged.read_bytes()
        self.assertIn(b"\\n",before)
        method=json.loads(self.row(tid)["source_spec"])["alternatives"][1]

        def swap_after_valid_receipt(db,row,workspace,fixtures):
            verdict=_verify_staged(db,row,workspace,fixtures)
            self.assertEqual(verdict,"MECHANICALLY_VALID")
            staged.write_bytes(before.replace(b"\\n",b"\\r\\n"))
            return verdict

        with patch("cognition_agent_os.conformance._verify_staged",
                   side_effect=swap_after_valid_receipt):
            with closing(connect(self.db)) as db:
                observed=_outcome(child,method,self.db,self.work,self.fx,
                                  _ACCEPT,require_staged=True,verifier_db=db)
        self.assertEqual(observed,"INCONCLUSIVE")
        self.assertNotEqual(staged.read_bytes(),before)

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
