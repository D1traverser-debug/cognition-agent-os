"""P8 unknown-record reconciliation with independent executable SQL oracle.

Generated rows were not pre-written as expected outputs; a regression suite
cannot claim independently validated business semantics or open-world planning.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,initialize,create_task,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.host import run_tick
from cognition_agent_os.reconciliation import (
    validate_reconciliation,propose_reconciliation,hypothesis_keys,parse_table,
    ReconciliationError
)
from cognition_agent_os.reconciliation_oracle import sql_audit,audit_stored_report

ROOT=Path(__file__).resolve().parents[1]


def csv_bytes(fields,records):
    buffer=io.StringIO(newline="")
    writer=csv.writer(buffer,lineterminator="\n")
    writer.writerow(fields)
    for row in records:writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.fixtures=self.root/"fixtures";self.fixtures.mkdir()
        self.workspace=self.root/"workspace";self.workspace.mkdir()
        self.db=self.root/"state.sqlite"
        d=connect(self.db);initialize(d);d.close()
        self.spec={"kind":"record_reconciliation",
                   "reference":"expect.csv","observed":"actual.csv",
                   "objective":"identify_discrepancies"}

    def setup_pair(self,fields,expected,actual):
        self.fixtures.joinpath("expect.csv").write_bytes(csv_bytes(fields,expected))
        self.fixtures.joinpath("actual.csv").write_bytes(csv_bytes(fields,actual))
        db=connect(self.db)
        tid=create_task(db,self.spec)
        db.close()
        return tid

    def task(self,tid):
        db=connect(self.db)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:db.close()

    def audit(self,tid):
        return audit_stored_report(self.db,self.workspace,self.fixtures,tid)

    def report(self,tid):
        return json.loads((self.workspace/"artifacts"/(tid+".json")).read_text())

    def test_dv_generated_unseen_cases_identify_exact_changes(self):
        rng=random.Random(78153)
        fields=["test_id","status","cycles"]
        src=[[f"T{n:04d}",rng.choice(["PASS","PASS","FAIL"]),str(rng.randint(100,9999))]
             for n in range(36)]
        obs=[r[:] for r in src]
        del obs[4]
        obs[11][1]="ERROR"  # shifts after the earlier deletion
        obs[17][2]="99999"
        obs.append(["T9999","PASS","1"])
        rng.shuffle(obs)
        tid=self.setup_pair(fields,src,obs)
        result=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        self.assertEqual(result["selected_key"],"test_id")
        self.assertEqual(result["discrepancies_count"],4)
        report=self.report(tid)["proposal"]
        observed={ (d["kind"],d["key"],d.get("field")) for d in report["discrepancies"] }
        self.assertEqual(observed,{
            ("missing_observed",src[4][0],None),
            ("field_mismatch",src[12][0],"status"),
            ("field_mismatch",src[18][0],"cycles"),
            ("unexpected_observed","T9999",None)})
        self.assertEqual(self.audit(tid)["status"],"REPORT_MECHANICALLY_VERIFIED")
        self.assertFalse(self.audit(tid)["business_outcome_verified"])
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")

    def test_financial_generated_unseen_invoices(self):
        rng=random.Random(1020)
        fields=["invoice_id","currency","amount","owner"]
        src=[[f"INV_{i:05d}","CNY",f"{rng.randint(1000,99999)/100:.2f}","vendor"]
             for i in range(43)]
        obs=[r[:] for r in src]
        obs[6][2]="0.00"
        obs[22][3]="unknown"
        obs.pop(37)
        rng.shuffle(obs)
        tid=self.setup_pair(fields,src,obs)
        result=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        self.assertEqual(result["selected_key"],"invoice_id")
        self.assertEqual(result["discrepancies_count"],3)
        output=self.report(tid)["proposal"]
        self.assertEqual({d["kind"] for d in output["discrepancies"]},
                         {"field_mismatch","missing_observed"})
        self.assertEqual(self.audit(tid)["status"],"REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual((self.fixtures/"expect.csv").read_bytes(),csv_bytes(fields,src))

    def test_consistent_sources_have_no_discrepancy_artifact(self):
        rows=[["X1","PASS","10"],["X2","FAIL","21"]]
        tid=self.setup_pair(["test_id","status","cycles"],rows,list(reversed(rows)))
        result=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"VERIFIED")
        self.assertEqual(result["decision"],"RECORD_SETS_CONSISTENT")
        self.assertFalse((self.workspace/"artifacts").exists())
        self.assertEqual(self.task(tid)["state"],"VERIFIED")
        self.assertFalse(result["business_outcome_verified"])

    def test_two_id_candidates_equally_plausible_abstain(self):
        fields=["primary_id","alternate_id","value"]
        src=[["a1","b1","10"],["a2","b2","20"]]
        tid=self.setup_pair(fields,src,src)
        r=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"JOIN_KEY_AMBIGUOUS")
        self.assertFalse((self.workspace/"artifacts").exists())

    def test_duplicate_stable_id_never_falls_back_to_unique_amount(self):
        fields=["invoice_id","amount"]
        left=csv_bytes(fields,[["DUP","10"],["DUP","11"]])
        right=csv_bytes(fields,[["DUP","10"],["OTHER","11"]])
        prediction=propose_reconciliation(self.spec,left,right)
        self.assertEqual(prediction["status"],"INSUFFICIENT_KEY_EVIDENCE")
        self.assertIsNone(prediction["selected_key"])
        self.assertTrue(sql_audit(self.spec,left,right,prediction)["agreement"])
        invented=json.loads(json.dumps(prediction))
        invented["status"]="CONSISTENT"
        invented["selected_key"]="amount"
        invented["discrepancies"]=[]
        self.assertFalse(sql_audit(self.spec,left,right,invented)["agreement"])

    def test_missing_input_unknown_does_not_invent_source(self):
        d=connect(self.db);tid=create_task(d,self.spec);d.close()
        r=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"RECONCILIATION_UNVERIFIABLE")
        self.assertFalse((self.workspace/"artifacts").exists())

    def test_sql_checker_rejects_incomplete_or_wrong_report(self):
        fields=["test_id","result"]
        a=csv_bytes(fields,[["X","PASS"],["Y","PASS"]])
        b=csv_bytes(fields,[["X","FAIL"],["Y","PASS"]])
        candidate=propose_reconciliation(self.spec,a,b)
        self.assertTrue(sql_audit(self.spec,a,b,candidate)["agreement"])
        wrong=json.loads(json.dumps(candidate))
        wrong["discrepancies"]=[]
        self.assertFalse(sql_audit(self.spec,a,b,wrong)["agreement"])
        wrong=json.loads(json.dumps(candidate))
        wrong["selected_key"]="result"
        self.assertFalse(sql_audit(self.spec,a,b,wrong)["agreement"])

    def test_sql_checker_detects_manipulated_row_details(self):
        fields=["invoice_id","amount"]
        a=csv_bytes(fields,[["a","100"],["b","200"]])
        b=csv_bytes(fields,[["a","99"],["b","200"]])
        candidate=propose_reconciliation(self.spec,a,b)
        self.assertTrue(sql_audit(self.spec,a,b,candidate)["agreement"])
        wrong=json.loads(json.dumps(candidate))
        wrong["discrepancies"][0]["observed"]="100"
        self.assertFalse(sql_audit(self.spec,a,b,wrong)["agreement"])

    def test_bad_headers_duplicate_ids_and_ragged_csv_fail_closed(self):
        data=[
          (b'test_id,test_id\nX,Y\n',b'test_id,value\nX,Y\n'),
          (b'test_id,value\nX,10\nX,11\n',b'test_id,value\nX,10\n'),
          (b'test_id,value\nX,10\n',b'test_id,value\nX,10,unexpected\n')
        ]
        for left,right in data:
            with self.subTest(left=left):
                self.fixtures.joinpath("expect.csv").write_bytes(left)
                self.fixtures.joinpath("actual.csv").write_bytes(right)
                d=connect(self.db);tid=create_task(d,self.spec);d.close()
                output=run_once(self.db,self.workspace,self.fixtures)
                self.assertEqual(output["status"],"UNKNOWN")
                self.assertFalse((self.workspace/"artifacts"/(tid+".json")).exists())

    def test_source_modified_after_report_is_unverifiable(self):
        fields=["invoice_id","amount"]
        tid=self.setup_pair(fields,[["X","10"]],[["X","11"]])
        self.assertEqual(run_once(self.db,self.workspace,self.fixtures)["status"],"NEEDS_REVIEW")
        self.fixtures.joinpath("actual.csv").write_bytes(csv_bytes(fields,[["X","12"]]))
        self.assertEqual(self.audit(tid)["reason"],"SOURCE_HAS_CHANGED")

    def test_artifact_tamper_is_unverifiable(self):
        tid=self.setup_pair(["test_id","result"],[["X","PASS"]],[["X","FAIL"]])
        run_once(self.db,self.workspace,self.fixtures)
        artifact=self.workspace/"artifacts"/(tid+".json")
        artifact.write_bytes(artifact.read_bytes()+b"X")
        self.assertEqual(self.audit(tid)["reason"],"ARTIFACT_HASH_MISMATCH")

    def test_actual_oracle_disagreement_refuses_task(self):
        tid=self.setup_pair(["test_id","status"],[["X","PASS"]],[["X","FAIL"]])
        with patch("cognition_agent_os.reconciliation_oracle.sql_audit",
                   return_value={"agreement":False}):
            r=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"RECONCILIATION_UNVERIFIABLE")
        self.assertFalse((self.workspace/"artifacts").exists())

    def test_write_revocation_before_processing_refuses_report(self):
        tid=self.setup_pair(["invoice_id","amount"],[["X","100"]],[["X","200"]])
        d=connect(self.db);alter_authority(d,revoke=True);d.close()
        result=run_once(self.db,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse((self.workspace/"artifacts").exists())

    def test_goal_change_before_processing_refuses_source_read(self):
        tid=self.setup_pair(["test_id","status"],[["X","PASS"]],[["X","FAIL"]])
        d=connect(self.db);alter_authority(d,goal_change=True);d.close()
        self.assertEqual(run_once(self.db,self.workspace,self.fixtures)["status"],"BLOCKED")

    def test_intake_rejects_remote_urls_and_identical_sources(self):
        for bad in ("../secrets.csv","https://site/a.csv","a/b.csv","", "C:\\secrets.csv"):
            s={**self.spec,"reference":bad}
            with self.subTest(path=bad),self.assertRaises(ReconciliationError):
                validate_reconciliation(s)
        with self.assertRaises(ReconciliationError):
            validate_reconciliation({**self.spec,"observed":"expect.csv"})

    def test_cli_intake_worker_and_sql_audit(self):
        self.fixtures.joinpath("expect.csv").write_text("invoice_id,amount\nX,10\n")
        self.fixtures.joinpath("actual.csv").write_text("invoice_id,amount\nX,11\n")
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        base=[sys.executable,"-m","cognition_agent_os.cli","--db",str(self.db),
              "--workspace",str(self.workspace),"--fixtures",str(self.fixtures)]
        def call(tail):
            return subprocess.run(base+tail,text=True,capture_output=True,timeout=15,env=env)
        created=call(["seed-reconciliation","--reference","expect.csv","--observed","actual.csv"])
        self.assertEqual(created.returncode,0,created.stderr)
        tid=json.loads(created.stdout)["task_id"]
        out=call(["worker-once"])
        self.assertEqual(json.loads(out.stdout)["status"],"NEEDS_REVIEW")
        audit=call(["reconciliation-audit","--task-id",tid])
        self.assertEqual(audit.returncode,0,audit.stderr)
        self.assertEqual(json.loads(audit.stdout)["status"],"REPORT_MECHANICALLY_VERIFIED")

    def test_host_uses_existing_ledger_for_reconciliation(self):
        tid=self.setup_pair(["test_id","status"],[["x","PASS"]],[["x","FAIL"]])
        result=run_tick(self.db,self.workspace,self.fixtures)
        self.assertEqual(result["processed"],1)
        self.assertEqual(result["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")

    def test_ambiguous_non_identifier_candidates_fail_closed(self):
        fields=["field_a","field_b","note"]
        rows=[["a","b","foo"],["c","d","bar"]]
        a=csv_bytes(fields,rows)
        report=propose_reconciliation(self.spec,a,a)
        self.assertEqual(report["status"],"INSUFFICIENT_KEY_EVIDENCE")
        self.assertTrue(sql_audit(self.spec,a,a,report)["agreement"])

    def test_randomized_unseen_domains_full_oracle_agreement(self):
        rng=random.Random(20261020)
        for trial in range(15):
            name="case_id" if trial%2==0 else "invoice_id"
            fields=[name,"value","status"]
            base=[[f"Q{j:04d}",str(rng.randrange(1000000)),
                   rng.choice(["OPEN","CLOSED"])] for j in range(25)]
            seen=[row[:] for row in base]
            changed=rng.randrange(25)
            seen[changed][1]=str(int(seen[changed][1])+1)
            rng.shuffle(seen)
            aa=csv_bytes(fields,base);bb=csv_bytes(fields,seen)
            p=propose_reconciliation(self.spec,aa,bb)
            self.assertEqual(p["selected_key"],name)
            self.assertEqual(p["status"],"DISCREPANCIES_FOUND")
            self.assertTrue(sql_audit(self.spec,aa,bb,p)["agreement"])
            self.assertEqual(len(p["discrepancies"]),1)


if __name__=="__main__":
    unittest.main()
