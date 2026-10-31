"""P11 unseen two-file, coupled functional repair through real SQLite/CLI.

All test data are local temp files. The Agent never executes imported user
source; independent holdout remains sealed until a frozen candidate exists.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,initialize,create_task,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.pipeline_repair import validate_pipeline,propose_pipeline
from cognition_agent_os.pipeline_oracle import audit_pipeline,review_pipeline
from cognition_agent_os.conformance import inspect_conformance,capability_disabled,REPAIR_LAB_CAPABILITY
from cognition_agent_os.host import run_tick

ROOT=Path(__file__).resolve().parents[1]


class CoupledRepairTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.ws=self.root/"workspace";self.ws.mkdir()
        self.dbpath=self.root/"agent.sqlite"
        db=connect(self.dbpath);initialize(db);db.close()
        self.src_a=b"def net(total, consumed):\n    return total + consumed\n"
        self.src_b=b"def scale(net_value, multiplier):\n    return net_value + multiplier\n"
        self.visible=[
            {"args":[9,4,3],"expected":15},
            {"args":[12,2,2],"expected":20},
            {"args":[5,5,7],"expected":0},
            {"args":[-3,2,4],"expected":-20},
            {"args":[10,3,0],"expected":0}
        ]
        self.hidden=[
            {"args":[200,79,4],"expected":484},
            {"args":[-20,-40,6],"expected":120},
            {"args":[33,12,0],"expected":0},
            {"args":[3,8,9],"expected":-45}
        ]
        self.fx.joinpath("net.py").write_bytes(self.src_a)
        self.fx.joinpath("scale.py").write_bytes(self.src_b)
        self.fx.joinpath("public.json").write_bytes(json.dumps(self.visible).encode())
        self.hidden_bytes=json.dumps(self.hidden).encode()
        self.fx.joinpath("secret.json").write_bytes(self.hidden_bytes)
        self.spec={"kind":"pipeline_code_repair",
                   "stages":[{"source":"net.py","function":"net"},
                             {"source":"scale.py","function":"scale"}],
                   "visible":"public.json","holdout":"secret.json",
                   "holdout_sha256":hashlib.sha256(self.hidden_bytes).hexdigest()}

    def seed(self, *, parent=None):
        db=connect(self.dbpath)
        tid=create_task(db,self.spec,parent=parent)
        db.close()
        return tid

    def state(self,tid):
        db=connect(self.dbpath)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:db.close()

    def prepare(self, *, parent=None):
        tid=self.seed(parent=parent)
        outcome=run_once(self.dbpath,self.ws,self.fx)
        self.assertEqual(outcome["status"],"NEEDS_REVIEW",outcome)
        self.assertFalse(outcome["holdout_seen_by_planner"])
        return tid

    def test_pipeline_failure_after_goal_rotation_must_not_claim_unknown(self):
        from cognition_agent_os import pipeline_repair
        tid=self.seed()
        def rotate(*args,**kwargs):
            db=connect(self.dbpath)
            try:alter_authority(db,goal_change=True)
            finally:db.close()
            raise ValueError("Injected candidate proposal failure")
        with patch.object(pipeline_repair,"propose_pipeline",side_effect=rotate):
            result=run_once(self.dbpath,self.ws,self.fx)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["reason"],"STALE_GOAL")
        self.assertEqual(self.state(tid)["state"],"BLOCKED")

    def test_coupled_real_two_source_repair_and_hidden_independent_review(self):
        tid=self.prepare()
        item=json.loads((self.ws/"artifacts"/(tid+".json")).read_text())
        self.assertEqual(item["selected"]["changes"],["Add->Sub","Add->Mult"])
        self.assertEqual(item["holdout_status"],"SEALED_NOT_READ_BY_PROPOSER")
        self.assertEqual(audit_pipeline(self.dbpath,self.ws,self.fx,tid)["status"],
                         "VISIBLE_PIPELINE_VERIFIED")
        done=review_pipeline(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(done["status"],"REPAIR_LAB_VERIFIED",done)
        self.assertEqual(done["holdout_passes"],len(self.hidden))
        self.assertEqual(self.state(tid)["state"],"REPAIR_LAB_VERIFIED")
        self.assertEqual((self.ws/"pipeline_lab"/tid/"net.py").read_text(),
                         "def net(total, consumed):\n    return total - consumed\n")
        self.assertEqual((self.ws/"pipeline_lab"/tid/"scale.py").read_text(),
                         "def scale(net_value, multiplier):\n    return net_value * multiplier\n")
        self.assertEqual(self.fx.joinpath("net.py").read_bytes(),self.src_a)
        self.assertEqual(self.fx.joinpath("scale.py").read_bytes(),self.src_b)
        self.assertEqual(audit_pipeline(self.dbpath,self.ws,self.fx,tid,
                         hidden=True,staged=True)["status"],"HOLDOUT_ACCEPTED")
        report=inspect_conformance(self.dbpath,self.ws,self.fx)
        self.assertEqual(report["mechanically_valid"],1)

    def test_retry_after_artifact_drift_runs_conformance_before_early_audit(self):
        from cognition_agent_os import pipeline_oracle as oracle,conformance
        tid=self.prepare()
        artifact=self.ws/"artifacts"/(tid+".json")
        original=artifact.read_bytes()
        real_audit=oracle.audit_pipeline
        real_preflight=conformance.effect_preflight
        mutated=False
        preflight_calls=0

        def mutate_after_final_audit(*args,**kwargs):
            nonlocal mutated
            result=real_audit(*args,**kwargs)
            if kwargs.get("hidden") is True and not mutated:
                self.assertEqual(result["status"],"HOLDOUT_ACCEPTED")
                artifact.write_bytes(original+b" ")
                mutated=True
            return result

        def preflight(*args,**kwargs):
            nonlocal preflight_calls
            preflight_calls+=1
            if preflight_calls==1:
                return {"admitted":True}
            return real_preflight(*args,**kwargs)

        with (
            patch.object(oracle,"audit_pipeline",side_effect=mutate_after_final_audit),
            patch.object(conformance,"effect_preflight",side_effect=preflight),
        ):
            first=review_pipeline(self.dbpath,self.ws,self.fx,tid)
            self.assertEqual(first.get("reason"),"ARTIFACT_CHANGED_AFTER_AUDIT",first)
            self.assertEqual(self.state(tid)["state"],"NEEDS_REVIEW")
            second=review_pipeline(self.dbpath,self.ws,self.fx,tid)

        self.assertEqual(preflight_calls,2)
        self.assertEqual(self.state(tid)["state"],"UNKNOWN")
        self.assertEqual(self.state(tid)["error_code"],
                         "CONFORMANCE_PROPOSAL_HASH_CHANGED")

    def test_artifact_changed_after_final_holdout_audit_is_not_staged(self):
        from cognition_agent_os import pipeline_oracle as oracle
        tid=self.prepare()
        artifact=self.ws/"artifacts"/(tid+".json")
        original=artifact.read_bytes()
        real_audit=oracle.audit_pipeline
        calls=0
        def mutate_after_final_audit(*args,**kwargs):
            nonlocal calls
            result=real_audit(*args,**kwargs)
            if kwargs.get("hidden") is True:
                self.assertEqual(result["status"],"HOLDOUT_ACCEPTED")
                artifact.write_bytes(original+b"\n")
            return result
        with patch.object(oracle,"audit_pipeline",side_effect=mutate_after_final_audit):
            result=review_pipeline(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"NOT_ADMITTED",result)
        self.assertEqual(result["reason"],"ARTIFACT_CHANGED_AFTER_AUDIT")
        self.assertFalse((self.ws/"pipeline_lab"/tid).exists())
        self.assertEqual(self.state(tid)["state"],"NEEDS_REVIEW")

    def test_sealed_counterexample_rejects_public_fit_without_stage(self):
        # A hidden independent source may refute the public-selected
        # hypothesis; the code proposer must not inspect the hidden cases.
        bad=[{"args":[200,79,4],"expected":999},
             {"args":[-20,-40,6],"expected":120}]
        data=json.dumps(bad).encode()
        self.fx.joinpath("secret.json").write_bytes(data)
        self.spec["holdout_sha256"]=hashlib.sha256(data).hexdigest()
        tid=self.prepare()
        result=review_pipeline(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"HOLDOUT_REFUTED",result)
        self.assertEqual(self.state(tid)["state"],"UNKNOWN")
        self.assertFalse((self.ws/"pipeline_lab").exists())

    def test_planner_attempt_to_read_hidden_file_is_trapped(self):
        from cognition_agent_os import pipeline_repair
        original=pipeline_repair.safe_fixture
        names=[]
        def limited(root,name):
            names.append(name)
            if name=="secret.json":
                raise AssertionError("Hidden gold leaked into coupled proposal")
            return original(root,name)
        with patch.object(pipeline_repair,"safe_fixture",side_effect=limited):
            self.prepare()
        self.assertEqual(set(names),{"net.py","scale.py","public.json"})

    def test_ambiguous_public_data_causes_abstention(self):
        loose=[{"args":[10,10,0],"expected":0},
               {"args":[12,12,0],"expected":0}]
        self.fx.joinpath("public.json").write_bytes(json.dumps(loose).encode())
        tid=self.seed()
        result=run_once(self.dbpath,self.ws,self.fx)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"NO_UNIQUE_CROSS_FILE_SOLUTION")
        self.assertFalse((self.ws/"artifacts"/(tid+".json")).exists())

    def test_file_path_import_and_arbitrary_source_execution_forbidden(self):
        import cognition_agent_os.repair_search as base
        for candidate in ("../secrets.py","/tmp/test.py","os.py/whatever","C:bad.py"):
            variant=json.loads(json.dumps(self.spec))
            variant["stages"][0]["source"]=candidate
            with self.subTest(candidate=candidate),self.assertRaises(base.RepairError):
                validate_pipeline(variant)
        bad=b"import os\ndef net(total, consumed):\n    return os.system('echo bad')\n"
        self.fx.joinpath("net.py").write_bytes(bad)
        tid=self.seed()
        result=run_once(self.dbpath,self.ws,self.fx)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertFalse((self.ws/"pipeline_lab").exists())

    def test_revoked_authority_blocks_cross_file_stage(self):
        tid=self.prepare()
        db=connect(self.dbpath);alter_authority(db,revoke=True);db.close()
        self.assertNotEqual(review_pipeline(self.dbpath,self.ws,self.fx,tid)["status"],
                            "REPAIR_LAB_VERIFIED")
        self.assertFalse((self.ws/"pipeline_lab").exists())

    def test_blocked_ancestor_cannot_authorize_pipeline_lab_stage(self):
        """A frozen two-file proposal loses write authority with its root."""
        db=connect(self.dbpath)
        try:
            root=create_task(db,self.spec,due_at=9999999999)
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",(root,))
            db.commit()
        finally:
            db.close()
        tid=self.prepare(parent=root)
        db=connect(self.dbpath)
        try:
            db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",(root,))
            db.commit()
        finally:
            db.close()
        observed=review_pipeline(self.dbpath,self.ws,self.fx,tid)
        self.assertNotEqual(observed["status"],"REPAIR_LAB_VERIFIED",observed)
        self.assertFalse((self.ws/"pipeline_lab"/tid/"net.py").exists())
        self.assertFalse((self.ws/"pipeline_lab"/tid/"scale.py").exists())

    def test_staged_file_tampering_invalidates_prior_success(self):
        tid=self.prepare()
        self.assertEqual(review_pipeline(self.dbpath,self.ws,self.fx,tid)["status"],
                         "REPAIR_LAB_VERIFIED")
        (self.ws/"pipeline_lab"/tid/"net.py").write_bytes(b"forged")
        found=inspect_conformance(self.dbpath,self.ws,self.fx,enforce=True)
        self.assertEqual(found["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(self.state(tid)["state"],"UNKNOWN")

    def test_opt_in_windows_compatible_host_tick_completes_coupled_review(self):
        tid=self.seed()
        result=run_tick(self.dbpath,self.ws,self.fx,auto_stage_goals=True)
        self.assertEqual(result["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(result["repair_lab_reviews"][0]["status"],"REPAIR_LAB_VERIFIED")
        self.assertEqual(self.state(tid)["state"],"REPAIR_LAB_VERIFIED")

    def test_default_host_never_reads_holdout_or_stages_repair(self):
        tid=self.seed()
        result=run_tick(self.dbpath,self.ws,self.fx)
        self.assertEqual(result["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(result["repair_lab_reviews"],[])
        self.assertFalse((self.ws/"pipeline_lab").exists())

    def test_tampered_verified_pipeline_opens_existing_capability_breaker(self):
        tid=self.prepare()
        self.assertEqual(review_pipeline(self.dbpath,self.ws,self.fx,tid)["status"],
                         "REPAIR_LAB_VERIFIED")
        (self.ws/"pipeline_lab"/tid/"scale.py").write_bytes(b"forged")
        inspect_conformance(self.dbpath,self.ws,self.fx,enforce=True)
        self.assertTrue(capability_disabled(self.dbpath,REPAIR_LAB_CAPABILITY))
        nxt=self.seed()
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(review_pipeline(self.dbpath,self.ws,self.fx,nxt)["status"],
                         "CAPABILITY_DISABLED")

    def test_post_effect_original_source_mutation_never_records_success(self):
        tid=self.prepare()
        from cognition_agent_os import pipeline_oracle as oracle
        real_stage=oracle._stage
        def stage_then_change(workspace,task_id,names,patches):
            real_stage(workspace,task_id,names,patches)
            self.fx.joinpath("net.py").write_bytes(
                b"def net(total, consumed):\\n    return total * consumed\\n")
        with patch.object(oracle,"_stage",side_effect=stage_then_change):
            result=review_pipeline(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"POST_EFFECT_REJECTED",result)
        self.assertEqual(self.state(tid)["state"],"UNKNOWN")
        db=connect(self.dbpath)
        events=db.execute("""SELECT kind FROM events WHERE task_id=?
                AND kind='PIPELINE_HOLDOUT_ACCEPTED'""",(tid,)).fetchall()
        self.assertEqual(events,[])
        db.close()

    def test_cli_real_queue_worker_audit_and_review_without_cloud(self):
        fixture=self.root/"task.json"
        fixture.write_bytes(json.dumps(self.spec).encode())
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        cmd=[sys.executable,"-m","cognition_agent_os.cli",
             "--db",str(self.dbpath),"--workspace",str(self.ws),
             "--fixtures",str(self.fx)]
        def call(args):
            return subprocess.run(cmd+args,env=env,capture_output=True,
                                  text=True,timeout=25)
        seeded=call(["seed-pipeline-repair","--spec",str(fixture)])
        self.assertEqual(seeded.returncode,0,seeded.stderr)
        tid=json.loads(seeded.stdout)["task_id"]
        result=call(["worker-once"])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"],"NEEDS_REVIEW")
        independent=call(["pipeline-audit","--task-id",tid])
        self.assertEqual(independent.returncode,0,independent.stderr)
        self.assertEqual(json.loads(independent.stdout)["status"],"VISIBLE_PIPELINE_VERIFIED")
        accepted=call(["pipeline-review","--task-id",tid])
        self.assertEqual(accepted.returncode,0,accepted.stderr)
        self.assertEqual(json.loads(accepted.stdout)["status"],"REPAIR_LAB_VERIFIED")


if __name__=="__main__":
    unittest.main()
