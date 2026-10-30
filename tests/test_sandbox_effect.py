"""P6 sandbox outcome acceptance tests; never write original fixture sources."""
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
from cognition_agent_os.sandbox_effect import stage_one, advance_due_reviews
from cognition_agent_os.host import run_tick

ROOT=Path(__file__).resolve().parents[1]


class SandboxEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.fx=self.home/"fixtures";self.fx.mkdir()
        self.out=self.home/"work";self.out.mkdir()
        self.db=self.home/"state.sqlite"
        connection=connect(self.db);initialize(connection);connection.close()

    def make(self,kind="json_keys",desired=None):
        desired=desired or ({"owner":"ops"} if kind=="json_keys" else {"pass":"NOT_RUN"})
        name="config.json" if kind=="json_keys" else "report.csv"
        before=b'{"port":8080}\n' if kind=="json_keys" else b'case,cycles\nA,10\nB,20\n'
        (self.fx/name).write_bytes(before)
        db=connect(self.db)
        task_id=create_task(db,{"kind":"goal_case","goal_type":kind,
                                "input":name,"desired":desired})
        db.close()
        self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"NEEDS_REVIEW")
        return task_id,name,before

    def task(self,tid):
        db=connect(self.db)
        try:
            return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally: db.close()

    def events(self,tid):
        db=connect(self.db)
        try:
            return [dict(r) for r in db.execute("SELECT * FROM events WHERE task_id=?",(tid,))]
        finally:db.close()

    def test_json_sandbox_actual_effect_readback_and_source_unchanged(self):
        tid,name,before=self.make()
        first=stage_one(self.db,self.out,self.fx,tid)
        self.assertEqual(first["status"],"SANDBOX_VERIFIED")
        self.assertFalse(first["business_outcome_verified"])
        self.assertTrue(first["source_untouched"])
        self.assertEqual((self.fx/name).read_bytes(),before)
        raw=(self.out/"sandbox"/(tid+".candidate")).read_bytes()
        self.assertEqual(json.loads(raw),{"port":8080,"owner":"ops"})
        self.assertEqual(self.task(tid)["state"],"SANDBOX_VERIFIED")
        self.assertEqual(len([e for e in self.events(tid) if e["kind"]=="SANDBOX_EFFECT_VERIFIED"]),1)
        self.assertEqual(stage_one(self.db,self.out,self.fx,tid)["status"],"NOT_ADMITTED")

    def test_csv_actual_effect_and_preservation(self):
        tid,name,before=self.make(kind="csv_columns")
        r=stage_one(self.db,self.out,self.fx,tid)
        self.assertEqual(r["status"],"SANDBOX_VERIFIED")
        self.assertEqual((self.fx/name).read_bytes(),before)
        self.assertEqual((self.out/"sandbox"/(tid+".candidate")).read_text(),
                         "case,cycles,pass\nA,10,NOT_RUN\nB,20,NOT_RUN\n")

    def test_source_drift_replans_in_same_ledger_then_executes_new_plan(self):
        tid,name,_=self.make()
        (self.fx/name).write_text('{"port":8080,"external":true}')
        result=stage_one(self.db,self.out,self.fx,tid)
        self.assertEqual(result["status"],"REPLAN_QUEUED")
        child=result["next_task_id"]
        self.assertEqual(self.task(tid)["state"],"NEEDS_REPLAN")
        self.assertEqual(self.task(child)["parent_task"],tid)
        self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(stage_one(self.db,self.out,self.fx,child)["status"],"SANDBOX_VERIFIED")
        self.assertTrue(json.loads((self.out/"sandbox"/(child+".candidate")).read_text())["external"])

    def test_bounded_replans_end_in_unknown_not_infinite_loop(self):
        parent,src,_=self.make()
        for i in range(2):
            (self.fx/src).write_text(json.dumps({"port":8080,"epoch":i}))
            r=stage_one(self.db,self.out,self.fx,parent)
            self.assertEqual(r["status"],"REPLAN_QUEUED")
            parent=r["next_task_id"]
            self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"NEEDS_REVIEW")
        (self.fx/src).write_text(json.dumps({"port":8080,"epoch":99}))
        r=stage_one(self.db,self.out,self.fx,parent)
        self.assertEqual(r["status"],"REPLAN_EXHAUSTED")
        self.assertEqual(self.task(parent)["state"],"UNKNOWN")
        self.assertEqual(self.task(parent)["error_code"],"REPLAN_BUDGET_EXHAUSTED")
        self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"IDLE")

    def test_grant_revocation_refuses_sandbox_effect(self):
        tid,name,_=self.make()
        db=connect(self.db);alter_authority(db,revoke=True);db.close()
        self.assertEqual(stage_one(self.db,self.out,self.fx,tid)["status"],"NOT_ADMITTED")
        self.assertFalse((self.out/"sandbox"/(tid+".candidate")).exists())

    def test_goal_revision_refuses_sandbox_effect(self):
        tid,name,_=self.make()
        db=connect(self.db);alter_authority(db,goal_change=True);db.close()
        self.assertEqual(stage_one(self.db,self.out,self.fx,tid)["status"],"NOT_ADMITTED")
        self.assertFalse((self.out/"sandbox"/(tid+".candidate")).exists())

    def test_existing_unexpected_stage_file_refused(self):
        tid,_,_=self.make()
        dest=self.out/"sandbox";dest.mkdir()
        (dest/(tid+".candidate")).write_text("TAMPER")
        r=stage_one(self.db,self.out,self.fx,tid)
        self.assertEqual(r["status"],"EFFECT_UNKNOWN")
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")
        self.assertEqual((dest/(tid+".candidate")).read_text(),"TAMPER")

    def test_repeated_sandbox_failure_has_finite_retry_budget(self):
        tid,_,_=self.make()
        folder=self.out/"sandbox"
        folder.mkdir()
        (folder/(tid+".candidate")).write_text("MISMATCH")
        results=[stage_one(self.db,self.out,self.fx,tid) for _ in range(3)]
        self.assertEqual([v["status"] for v in results],
                         ["EFFECT_UNKNOWN","EFFECT_UNKNOWN","EFFECT_RETRY_EXHAUSTED"])
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        self.assertEqual(self.task(tid)["error_code"],"SANDBOX_EFFECT_RETRY_EXHAUSTED")
        self.assertEqual(stage_one(self.db,self.out,self.fx,tid)["status"],"NOT_ADMITTED")
        self.assertEqual((folder/(tid+".candidate")).read_text(),"MISMATCH")

    def test_compromised_candidate_hash_or_source_rejected(self):
        tid,name,_=self.make()
        path=self.out/"artifacts"/(tid+".json")
        before=path.read_bytes()
        path.write_bytes(before+b"x")
        self.assertEqual(stage_one(self.db,self.out,self.fx,tid)["status"],"NOT_ADMITTED")
        self.assertFalse((self.out/"sandbox"/(tid+".candidate")).exists())

    def test_reconcile_crash_between_stage_file_and_db_commit(self):
        tid,name,_=self.make()
        code=("from pathlib import Path;from cognition_agent_os.sandbox_effect import stage_one;"
              "stage_one(Path(%r),Path(%r),Path(%r),%r,fault_after_effect=True)" %
              (str(self.db),str(self.out),str(self.fx),tid))
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        p=subprocess.run([sys.executable,"-c",code],env=env,text=True,
                         capture_output=True,timeout=15)
        self.assertEqual(p.returncode,81,p.stderr)
        staged=(self.out/"sandbox"/(tid+".candidate")).read_bytes()
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")
        recovered=stage_one(self.db,self.out,self.fx,tid)
        self.assertEqual(recovered["status"],"SANDBOX_VERIFIED")
        self.assertEqual(staged,(self.out/"sandbox"/(tid+".candidate")).read_bytes())
        self.assertEqual(len([e for e in self.events(tid) if e["kind"]=="SANDBOX_EFFECT_VERIFIED"]),1)

    def test_two_independent_stagers_only_one_effect(self):
        tid,_,_=self.make()
        code=("from pathlib import Path;from cognition_agent_os.sandbox_effect import stage_one;"
              "import json;print(json.dumps(stage_one(Path(%r),Path(%r),Path(%r),%r)))" %
              (str(self.db),str(self.out),str(self.fx),tid))
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        processes=[subprocess.Popen([sys.executable,"-c",code],env=env,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        results=[]
        for p in processes:
            stdout,stderr=p.communicate(timeout=20)
            self.assertEqual(p.returncode,0,stderr)
            results.append(json.loads(stdout))
        statuses=[result["status"] for result in results]
        self.assertEqual(statuses.count("SANDBOX_VERIFIED"),1,results)
        losers=[item for item in results if item["status"]!="SANDBOX_VERIFIED"]
        self.assertEqual(len(losers),1,results)
        self.assertIn(losers[0]["status"],
                      {"NOT_ADMITTED","NOT_PENDING_REVIEW","PREFLIGHT_BLOCKED"},
                      results)
        if losers[0]["status"]=="PREFLIGHT_BLOCKED":
            # Another process changing the ledger during preflight is a
            # safely rejected effect, not a second accepted sandbox write.
            self.assertEqual(losers[0]["reason"],"PREFLIGHT_NOT_SATISFIED")
            self.assertIn(losers[0]["preflight_status"],
                          {"CONCURRENT_CONFORMANCE_STATE_CHANGED",
                           "EVIDENCE_INSUFFICIENT"},results)
        self.assertEqual(self.task(tid)["state"],"SANDBOX_VERIFIED",results)
        self.assertEqual(len([e for e in self.events(tid)
                              if e["kind"]=="SANDBOX_EFFECT_VERIFIED"]),1,results)

    def test_auto_stage_opt_in_off_is_no_op(self):
        tid,_,_=self.make()
        tick=run_tick(self.db,self.out,self.fx)
        self.assertEqual(tick["sandbox_reviews"],[])
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")
        enabled=run_tick(self.db,self.out,self.fx,auto_stage_goals=True)
        self.assertEqual(enabled["sandbox_reviews"][0]["status"],"SANDBOX_VERIFIED")

    def test_host_creates_proposal_then_stages_same_tick_opt_in(self):
        self.fx.joinpath("config.json").write_text("{}")
        db=connect(self.db)
        tid=create_task(db,{"kind":"goal_case","goal_type":"json_keys",
                            "input":"config.json","desired":{"owner":"ops"}})
        db.close()
        tick=run_tick(self.db,self.out,self.fx,auto_stage_goals=True)
        self.assertEqual(tick["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(tick["sandbox_reviews"][0]["status"],"SANDBOX_VERIFIED")
        self.assertEqual(self.task(tid)["state"],"SANDBOX_VERIFIED")

    def test_cli_stage_sandbox_one_task(self):
        tid,_,_=self.make()
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        cmd=[sys.executable,"-m","cognition_agent_os.cli","--db",str(self.db),
             "--workspace",str(self.out),"--fixtures",str(self.fx),
             "goal-stage-sandbox","--task-id",tid]
        p=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"],"SANDBOX_VERIFIED")

    def test_unsafe_workspace_symlink_cannot_stage(self):
        tid,_,_=self.make()
        destination=self.out/"sandbox";target=self.home/"outside";target.mkdir()
        try:destination.symlink_to(target,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest("symlink not available")
        self.assertEqual(stage_one(self.db,self.out,self.fx,tid)["status"],"EFFECT_UNKNOWN")
        self.assertEqual(list(target.iterdir()),[])


if __name__=="__main__":
    unittest.main()
