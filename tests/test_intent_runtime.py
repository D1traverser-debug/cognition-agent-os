"""P9 typed goal-plan admission, durable child integrity and cross-family outcomes."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,create_task,initialize,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.host import run_tick
from cognition_agent_os.intent_planner import compile_intent,IntentError
from cognition_agent_os.intent_runtime import audit_intent_plan

ROOT=Path(__file__).resolve().parents[1]


class IntentRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.fixtures=self.root/"fixtures";self.fixtures.mkdir()
        self.workspace=self.root/"workspace";self.workspace.mkdir()
        self.db_path=self.root/"state.sqlite"
        db=connect(self.db_path);initialize(db);db.close()

    def structured(self):
        return {"kind":"goal_intent","objective":"ensure_structure",
                "resources":[{"role":"input","path":"settings.json"}],
                "requirements":[{"field":"owner","equals":"ops"},
                                {"field":"retry","equals":3}]}

    def comparison(self):
        return {"kind":"goal_intent","objective":"compare_records",
                "resources":[{"role":"reference","path":"old.csv"},
                             {"role":"observed","path":"new.csv"}]}

    def seed(self,spec):
        db=connect(self.db_path)
        try:return create_task(db,spec)
        finally:db.close()

    def task(self,tid):
        db=connect(self.db_path)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:db.close()

    def test_invalid_intent_after_goal_rotation_must_report_blocked(self):
        from cognition_agent_os import intent_runtime
        tid=self.seed(self.structured())
        def rotate(*args,**kwargs):
            db=connect(self.db_path)
            try:alter_authority(db,goal_change=True)
            finally:db.close()
            raise IntentError("Injected malformed intent")
        with patch.object(intent_runtime,"compile_intent",side_effect=rotate):
            result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["reason"],"STALE_GOAL")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")

    def test_json_intent_generates_child_and_actual_sandbox(self):
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        tid=self.seed(self.structured())
        tick=run_tick(self.db_path,self.workspace,self.fixtures,auto_stage_goals=True)
        self.assertEqual(tick["tasks"][0]["status"],"DECOMPOSED")
        self.assertEqual(tick["tasks"][1]["status"],"NEEDS_REVIEW")
        cid=tick["tasks"][0]["child_task_id"]
        self.assertEqual(self.task(tid)["state"],"DECOMPOSED")
        self.assertEqual(self.task(cid)["parent_task"],tid)
        self.assertEqual(self.task(cid)["state"],"SANDBOX_VERIFIED")
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        actual=json.loads((self.workspace/"sandbox"/(cid+".candidate")).read_text())
        self.assertEqual(actual,{"critical":"keep","owner":"ops","retry":3})
        self.assertEqual(self.fixtures.joinpath("settings.json").read_text(),'{"critical":"keep"}')
        self.assertFalse(tick["semantic_outcome_verified"])

    def test_comparison_intent_generates_full_sql_verifiable_report(self):
        self.fixtures.joinpath("old.csv").write_text("invoice_id,amount\nI1,100\nI2,200\n")
        self.fixtures.joinpath("new.csv").write_text("invoice_id,amount\nI1,101\nI2,200\n")
        tid=self.seed(self.comparison())
        first=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(first["status"],"DECOMPOSED")
        child=first["child_task_id"]
        second=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(second["status"],"NEEDS_REVIEW")
        self.assertEqual(second["selected_key"],"invoice_id")
        self.assertEqual(second["discrepancies_count"],1)
        from cognition_agent_os.reconciliation_oracle import audit_stored_report
        self.assertEqual(audit_stored_report(self.db_path,self.workspace,self.fixtures,child)["status"],
                         "REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        self.assertEqual(self.task(child)["state"],"NEEDS_REVIEW")

    def test_composed_comparison_uses_reviewer_pinned_key_and_sql(self):
        self.fixtures.joinpath("old.csv").write_text(
            "primary_id,alternate_id,amount\nA,Z,100\nB,Y,200\n")
        self.fixtures.joinpath("new.csv").write_text(
            "primary_id,alternate_id,amount\nA,Z,101\nB,Y,200\n")
        manifest={
            "schema_version":1,"contract_kind":"record_relationship",
            "reference":"old.csv","observed":"new.csv",
            "join_key":"primary_id",
            "justification":"Independently reviewed primary record identifier association."
        }
        raw=(json.dumps(manifest,sort_keys=True)+"\n").encode()
        self.fixtures.joinpath("linkage.json").write_bytes(raw)
        intent={**self.comparison(),"relationship_contract":{
            "path":"linkage.json","expected_sha256":hashlib.sha256(raw).hexdigest()}}
        tid=self.seed(intent)
        first=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(first["status"],"DECOMPOSED")
        child=first["child_task_id"]
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        self.assertEqual(result["selected_key"],"primary_id")
        from cognition_agent_os.reconciliation_oracle import audit_stored_report
        self.assertEqual(
            audit_stored_report(self.db_path,self.workspace,self.fixtures,child)["status"],
            "REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual(self.task(child)["state"],"NEEDS_REVIEW")

    def test_composed_intent_rejects_self_claimed_trust_without_digest(self):
        bad={**self.comparison(),"relationship_contract":{
            "path":"linkage.json","key":"primary_id"}}
        with self.assertRaises(IntentError):
            compile_intent(bad)

    def test_unknown_intent_never_executes_and_never_creates_child(self):
        spec={**self.comparison(),"objective":"execute_shell"}
        with self.assertRaises(IntentError):
            compile_intent(spec)
        tid=self.seed(spec)
        result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"INTENT_NOT_ADMITTED")
        self.assertFalse((self.workspace/"artifacts").exists())
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"UNVERIFIABLE")

    def test_duplicate_roles_and_untrusted_extensions_rejected(self):
        for bad in [
            {**self.comparison(),"resources":[{"role":"reference","path":"a.csv"},
                                            {"role":"reference","path":"b.csv"}]},
            {**self.structured(),"permissions":"allow_any_shell"},
            {**self.structured(),"requirements":[{"field":"owner","equals":"a"},
                                                {"field":"owner","equals":"b"}]},
            {**self.comparison(),"resources":[{"role":"reference","path":"../etc/passwd"},
                                            {"role":"observed","path":"new.csv"}]},
            {**self.structured(),"requirements":[{"field":"bad field","equals":"x"}]},
            {**self.structured(),"requirements":[{"field":"allowed","equals":["run shell"]}]},
            {**self.structured(),"resources":[{"role":"input","path":":/absolute"}]},
            {**self.comparison(),"requirements":[]}
        ]:
            with self.subTest(value=bad),self.assertRaises(IntentError):
                compile_intent(bad)

    def test_authority_revoked_after_goal_enqueued_blocks_decomposition(self):
        tid=self.seed(self.structured())
        db=connect(self.db_path);alter_authority(db,revoke=True);db.close()
        outcome=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(outcome["status"],"BLOCKED")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")
        db=connect(self.db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],1)
        db.close()

    def test_goal_revision_invalidates_plan(self):
        tid=self.seed(self.comparison())
        db=connect(self.db_path);alter_authority(db,goal_change=True);db.close()
        outcome=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(outcome["status"],"BLOCKED")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")

    def test_no_nested_intents_even_under_claim(self):
        parent=self.seed(self.structured())
        db=connect(self.db_path)
        child=create_task(db,self.comparison(),parent=parent)
        db.execute("UPDATE tasks SET state='UNKNOWN' WHERE task_id=?",(parent,))
        db.commit();db.close()
        result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"INTENT_RECURSION_REFUSED")
        self.assertEqual(self.task(child)["state"],"UNKNOWN")

    def test_plan_receipt_falsification_cannot_forge_validity(self):
        tid=self.seed(self.structured())
        self.assertEqual(run_once(self.db_path,self.workspace,self.fixtures)["status"],"DECOMPOSED")
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        db=connect(self.db_path)
        child=db.execute("SELECT task_id FROM tasks WHERE parent_task=?",(tid,)).fetchone()[0]
        db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                   (json.dumps({"kind":"fixture","old":"x","new":"y"}),child))
        db.commit();db.close()
        self.assertEqual(audit_intent_plan(self.db_path,tid)["reason"],
                         "CHILD_TASK_IDENTITY_MISMATCH")

    def test_cli_seeds_one_intent_and_audits_without_second_db(self):
        spec=self.structured()
        manifest=self.root/"intent.json"
        manifest.write_text(json.dumps(spec))
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        common=[sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(self.db_path),"--workspace",str(self.workspace),
                "--fixtures",str(self.fixtures)]
        def cli(args):
            return subprocess.run(common+args,env=env,capture_output=True,text=True,timeout=12)
        first=cli(["seed-intent","--spec",str(manifest)])
        self.assertEqual(first.returncode,0,first.stderr)
        tid=json.loads(first.stdout)["task_id"]
        self.assertEqual(cli(["worker-once"]).returncode,0)
        checked=cli(["intent-audit","--task-id",tid])
        self.assertEqual(checked.returncode,0,checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["status"],"PLAN_MECHANICALLY_VALID")
        d=connect(self.db_path)
        self.assertEqual(d.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],2)
        d.close()


if __name__=="__main__":
    unittest.main()
