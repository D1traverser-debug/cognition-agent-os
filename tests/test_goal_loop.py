"""P5 opt-in goal loop: evidence, alternatives, bounded action, independent mechanics.

These tests prove code mechanics for two goal families, NOT open-world planning
or domain semantic approval.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,initialize,create_task,alter_authority
from cognition_agent_os.runner import run_once,verify_artifact
from cognition_agent_os.goal_loop import plan_goal, validate_goal, GoalError, _check_candidate

ROOT=Path(__file__).resolve().parents[1]


class GoalLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.fx=self.home/"fixtures"
        self.fx.mkdir()
        self.out=self.home/"workspace"
        self.dbpath=self.home/"state.sqlite"
        db=connect(self.dbpath)
        initialize(db)
        db.close()

    def seed(self, kind, source, desired):
        spec={"kind":"goal_case","goal_type":kind,"input":source,"desired":desired}
        db=connect(self.dbpath)
        try:
            return create_task(db,validate_goal(spec))
        finally:
            db.close()

    def record(self, tid):
        db=connect(self.dbpath)
        try:
            return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:
            db.close()

    def artifact(self, tid):
        return json.loads((self.out/"artifacts"/(tid+".json")).read_text(encoding="utf-8"))

    def child(self, mode="worker-once",fail_at=None):
        args=[sys.executable,"-m","cognition_agent_os.cli","--db",str(self.dbpath),
              "--workspace",str(self.out),"--fixtures",str(self.fx),mode]
        if fail_at:args.extend(["--fail-at",fail_at])
        env=os.environ.copy()
        env["PYTHONPATH"]=str(ROOT/"src")
        return subprocess.run(args,env=env,capture_output=True,text=True,timeout=15)

    def test_json_missing_key_to_non_destructive_candidate(self):
        (self.fx/"settings.json").write_text('{"port": 1234, "debug": false}')
        tid=self.seed("json_keys","settings.json",{"port":1234,"owner":"ops"})
        out=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual(out["status"],"NEEDS_REVIEW")
        self.assertEqual(out["decision"],"ADD_MISSING_JSON_KEYS")
        artifact=self.artifact(tid)
        self.assertEqual(json.loads(artifact["candidate_text"]),{"port":1234,"owner":"ops","debug":False})
        self.assertEqual(json.loads((self.fx/"settings.json").read_text()),{"port":1234,"debug":False})
        self.assertEqual(artifact["checker"],"MECHANICAL_CONSTRAINTS_ONLY")
        self.assertEqual(artifact["status"],"PROPOSAL_NOT_APPROVED")
        self.assertTrue(verify_artifact(self.out,self.record(tid)))
        self.assertEqual(self.record(tid)["state"],"NEEDS_REVIEW")
        self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"IDLE")

    def test_csv_missing_column_to_non_destructive_candidate(self):
        (self.fx/"metrics.csv").write_text("case,cycles\nA,10\nB,20\n")
        tid=self.seed("csv_columns","metrics.csv",{"passed":"NOT_RUN"})
        result=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        self.assertEqual(self.artifact(tid)["candidate_text"],"case,cycles,passed\nA,10,NOT_RUN\nB,20,NOT_RUN\n")
        self.assertEqual((self.fx/"metrics.csv").read_text(),"case,cycles\nA,10\nB,20\n")

    def test_two_families_true_noop_verify_without_artifact(self):
        (self.fx/"settings.json").write_text('{"owner":"ops","port":1234}')
        (self.fx/"metrics.csv").write_text("case,passed\nA,YES\n")
        self.seed("json_keys","settings.json",{"owner":"ops"})
        self.seed("csv_columns","metrics.csv",{"passed":"NO"})
        first=run_once(self.dbpath,self.out,self.fx)
        second=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual([first["decision"],second["decision"]],["GOAL_ALREADY_SATISFIED"]*2)
        self.assertFalse((self.out/"artifacts").exists())

    def test_conflicting_value_is_unknown_not_auto_overwritten(self):
        (self.fx/"settings.json").write_text('{"port":8080, "owner":"ops"}')
        tid=self.seed("json_keys","settings.json",{"port":443})
        result=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual(len(result["hypotheses"]),3)
        self.assertEqual(self.record(tid)["error_code"],"NO_SAFE_GOAL_PLAN")
        self.assertFalse((self.out/"artifacts").exists())

    def test_source_missing_invalid_duplicate_json_is_unknown(self):
        (self.fx/"duplicate.json").write_text('{"port":1234,"port":2222}')
        (self.fx/"broken.csv").write_text("case,case\nA,10\n")
        for kind,path,desired in [
            ("json_keys","missing.json",{"port":1234}),
            ("json_keys","duplicate.json",{"port":1234}),
            ("csv_columns","broken.csv",{"passed":"NO"})
        ]:
            self.seed(kind,path,desired)
            self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"UNKNOWN")

    def test_cannot_overwrite_existing_source_fields(self):
        s={"kind":"goal_case","goal_type":"json_keys","input":"data.json","desired":{"id":10}}
        parsed={"id":9}
        self.assertFalse(_check_candidate("json_keys",parsed,s["desired"],b'{"id":10}'))
        self.assertFalse(_check_candidate("json_keys",{"id":10,"raw":"x"},s["desired"],b'{"id":10}'))

    def test_goal_change_before_run_is_blocked(self):
        (self.fx/"settings.json").write_text("{}")
        tid=self.seed("json_keys","settings.json",{"owner":"ops"})
        db=connect(self.dbpath);alter_authority(db,goal_change=True);db.close()
        self.assertEqual(run_once(self.dbpath,self.out,self.fx)["status"],"BLOCKED")
        self.assertFalse((self.out/"artifacts").exists())

    def test_write_revoke_blocks_change_but_noop_allowed(self):
        (self.fx/"settings.json").write_text('{"owner":"ops"}')
        self.seed("json_keys","settings.json",{"new":"x"})
        self.seed("json_keys","settings.json",{"owner":"ops"})
        db=connect(self.dbpath);alter_authority(db,revoke=True);db.close()
        a=run_once(self.dbpath,self.out,self.fx)
        b=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual((a["status"],b["status"]),("BLOCKED","VERIFIED"))
        self.assertFalse((self.out/"artifacts").exists())

    def test_source_changes_after_plan_before_commit_fail_closed(self):
        (self.fx/"settings.json").write_text("{}")
        self.seed("json_keys","settings.json",{"k":"x"})
        import cognition_agent_os.goal_loop as gl
        real=gl._check_candidate
        def mutate_on_check(kind,parsed,desired,content):
            if not (self.fx/"settings.json").read_text().startswith('{"other"'):
                (self.fx/"settings.json").write_text('{"other":"external"}')
            return real(kind,parsed,desired,content)
        with patch.object(gl,"_check_candidate",side_effect=mutate_on_check):
            result=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"GOAL_CANDIDATE_OR_INPUT_CONFLICT")
        self.assertFalse((self.out/"artifacts").exists())

    def test_crash_during_artifact_write_recovered_idempotently(self):
        (self.fx/"settings.json").write_text("{}")
        tid=self.seed("json_keys","settings.json",{"owner":"ops"})
        p=self.child(fail_at="after_artifact_before_commit")
        self.assertEqual(p.returncode,79,p.stderr)
        previous=(self.out/"artifacts"/(tid+".json")).read_bytes()
        db=connect(self.dbpath)
        db.execute("UPDATE tasks SET lease_until=0 WHERE task_id=?",(tid,))
        db.commit();db.close()
        q=self.child()
        self.assertEqual(q.returncode,0,q.stderr)
        self.assertEqual(json.loads(q.stdout)["status"],"NEEDS_REVIEW")
        self.assertEqual(previous,(self.out/"artifacts"/(tid+".json")).read_bytes())
        self.assertEqual(len(list((self.out/"artifacts").glob("*.json"))),1)

    def test_artifact_tamper_on_retry_unknown(self):
        (self.fx/"settings.json").write_text("{}")
        tid=self.seed("json_keys","settings.json",{"owner":"ops"})
        self.assertEqual(self.child(fail_at="after_artifact_before_commit").returncode,79)
        (self.out/"artifacts"/(tid+".json")).write_text("malicious")
        db=connect(self.dbpath);db.execute("UPDATE tasks SET lease_until=0 WHERE task_id=?",(tid,));db.commit();db.close()
        r=run_once(self.dbpath,self.out,self.fx)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"GOAL_CANDIDATE_OR_INPUT_CONFLICT")

    def test_two_independent_workers_one_artifact(self):
        (self.fx/"settings.json").write_text("{}")
        self.seed("json_keys","settings.json",{"owner":"ops"})
        args=[sys.executable,"-m","cognition_agent_os.cli","--db",str(self.dbpath),
              "--workspace",str(self.out),"--fixtures",str(self.fx),"worker-once"]
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        ps=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,text=True)
            for _ in range(2)]
        outputs=[]
        for proc in ps:
            stdout,stderr=proc.communicate(timeout=15)
            self.assertEqual(proc.returncode,0,stderr)
            outputs.append(json.loads(stdout)["status"])
        self.assertEqual(sorted(outputs),["IDLE","NEEDS_REVIEW"])

    def test_bad_goal_rejected_on_intake(self):
        cases=[
            {"kind":"goal_case","goal_type":"exec_shell","input":"x","desired":{"k":1}},
            {"kind":"goal_case","goal_type":"json_keys","input":"x","desired":{"bad key":1}},
            {"kind":"goal_case","goal_type":"json_keys","input":"x","desired":{"a":[]}},
            {"kind":"goal_case","goal_type":"csv_columns","input":"x","desired":{"col":None}},
        ]
        for spec in cases:
            with self.subTest(spec=spec),self.assertRaises(GoalError):
                validate_goal(spec)

    def test_host_tick_runs_goal_under_existing_authority(self):
        from cognition_agent_os.host import run_tick
        (self.fx/"settings.json").write_text("{}")
        tid=self.seed("json_keys","settings.json",{"owner":"ops"})
        result=run_tick(self.dbpath,self.out,self.fx)
        self.assertEqual(result["processed"],1)
        self.assertEqual(result["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(self.record(tid)["state"],"NEEDS_REVIEW")

    def test_explicit_cli_goal_seeds_and_runs(self):
        (self.fx/"settings.json").write_text("{}")
        contract={"kind":"goal_case","goal_type":"json_keys","input":"settings.json",
                  "desired":{"owner":"ops"}}
        file=self.home/"goal.json"
        file.write_text(json.dumps(contract))
        args=[sys.executable,"-m","cognition_agent_os.cli",
              "--db",str(self.dbpath),"--workspace",str(self.out),
              "--fixtures",str(self.fx),"seed-goal","--spec",str(file)]
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        p=subprocess.run(args,capture_output=True,text=True,env=env,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)["state"],"PENDING")
        self.assertEqual(self.child().returncode,0)


if __name__=="__main__":
    unittest.main()
