"""P9: out-of-band pinned relationship input vs heuristic key guesses."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.runner import run_once
from cognition_agent_os.semantic_contract import load_pinned_relationship
from cognition_agent_os.reconciliation import (
    validate_reconciliation,propose_reconciliation,ReconciliationError
)
from cognition_agent_os.reconciliation_oracle import sql_audit,audit_stored_report

ROOT=Path(__file__).resolve().parents[1]


class PinnedContractTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.ws=self.root/"workspace";self.ws.mkdir()
        self.db=self.root/"ledger.sqlite"
        c=connect(self.db);initialize(c);c.close()
        self.reference=self.fx/"expect.csv"
        self.observed=self.fx/"actual.csv"
        self.reference.write_text("primary_id,alternate_id,amount\nA1,Z1,100\nA2,Z2,200\n")
        self.observed.write_text("primary_id,alternate_id,amount\nA1,Z1,101\nA2,Z2,200\n")
        self.spec={"kind":"record_reconciliation","reference":"expect.csv",
                   "observed":"actual.csv","objective":"identify_discrepancies"}

    def pin(self, *, key="primary_id",scope_reference="expect.csv"):
        obj={"schema_version":1,"contract_kind":"record_relationship",
             "reference":scope_reference,"observed":"actual.csv",
             "join_key":key,"justification":"The external reviewer declares the stable row identity."}
        raw=(json.dumps(obj,sort_keys=True)+"\n").encode()
        self.fx.joinpath("relationship.json").write_bytes(raw)
        return {**self.spec,"relationship_contract":{
            "path":"relationship.json",
            "expected_sha256":hashlib.sha256(raw).hexdigest()
        }}

    def seed(self,spec):
        c=connect(self.db)
        try:return create_task(c,spec)
        finally:c.close()

    def test_unpinned_ambiguous_guess_refuses_to_choose(self):
        data_a=self.reference.read_bytes();data_b=self.observed.read_bytes()
        p=propose_reconciliation(self.spec,data_a,data_b)
        self.assertEqual(p["status"],"INSUFFICIENT_KEY_EVIDENCE")
        self.assertTrue(sql_audit(self.spec,data_a,data_b,p)["agreement"])

    def test_caller_pinned_join_resolves_tie_but_stays_provisional(self):
        spec=self.pin()
        tid=self.seed(spec)
        r=run_once(self.db,self.ws,self.fx)
        self.assertEqual(r["status"],"NEEDS_REVIEW",r)
        self.assertEqual(r["selected_key"],"primary_id")
        self.assertEqual(r["discrepancies_count"],1)
        candidate=json.loads((self.ws/"artifacts"/(tid+".json")).read_text())
        self.assertEqual(candidate["proposal"]["relationship_contract_sha256"],
                         spec["relationship_contract"]["expected_sha256"])
        audited=audit_stored_report(self.db,self.ws,self.fx,tid)
        self.assertEqual(audited["status"],"REPORT_MECHANICALLY_VERIFIED")
        self.assertFalse(audited["business_outcome_verified"])
        self.assertFalse(audited["authorizes_mutation"])

    def test_wrong_contract_file_hash_refused_even_when_key_plausible(self):
        spec=self.pin()
        spec["relationship_contract"]["expected_sha256"]="f"*64
        with self.assertRaises(ReconciliationError):
            load_pinned_relationship(spec,self.fx)
        tid=self.seed(spec)
        r=run_once(self.db,self.ws,self.fx)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertFalse((self.ws/"artifacts").exists())

    def test_contract_scope_mismatch_refused(self):
        spec=self.pin(scope_reference="other.csv")
        tid=self.seed(spec)
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"UNKNOWN")

    def test_contract_changed_after_report_breaks_independent_audit(self):
        spec=self.pin()
        tid=self.seed(spec)
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        p=self.fx/"relationship.json"
        p.write_text(p.read_text()+"\n")
        report=audit_stored_report(self.db,self.ws,self.fx,tid)
        self.assertEqual(report["status"],"UNVERIFIABLE")
        self.assertEqual(report["reason"],"EVIDENCE_RECHECK_UNAVAILABLE")

    def test_unpinned_model_cannot_claim_pinned_key(self):
        spec=self.pin()
        left=self.reference.read_bytes();right=self.observed.read_bytes()
        with self.assertRaises(ReconciliationError):
            propose_reconciliation(spec,left,right)
        p=propose_reconciliation(self.spec,left,right)
        p["status"]="DISCREPANCIES_FOUND"
        p["selected_key"]="primary_id"
        p["discrepancies"]=[]
        p["relationship_contract_sha256"]=spec["relationship_contract"]["expected_sha256"]
        self.assertFalse(sql_audit(spec,left,right,p)["agreement"])

    def test_pinned_key_not_unique_cannot_force_join(self):
        spec=self.pin()
        self.reference.write_text("primary_id,alternate_id,amount\nDUP,Z1,100\nDUP,Z2,200\n")
        tid=self.seed(spec)
        r=run_once(self.db,self.ws,self.fx)
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertEqual(r["reason"],"JOIN_KEY_AMBIGUOUS")

    def test_pinned_key_missing_in_one_file_cannot_force_join(self):
        spec=self.pin()
        self.observed.write_text("alternate_id,amount\nZ1,101\nZ2,200\n")
        tid=self.seed(spec)
        r=run_once(self.db,self.ws,self.fx)
        self.assertEqual(r["status"],"UNKNOWN")

    def test_same_data_contract_key_changes_cannot_be_swapped(self):
        spec=self.pin(key="primary_id")
        first=load_pinned_relationship(spec,self.fx)
        spec2=self.pin(key="alternate_id")
        second=load_pinned_relationship(spec2,self.fx)
        self.assertNotEqual(first["digest"],second["digest"])
        with self.assertRaises(ReconciliationError):
            load_pinned_relationship(spec,self.fx)

    def test_external_sha_must_be_supplied_at_cli_not_self_derived(self):
        spec=self.pin()
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        base=[sys.executable,"-m","cognition_agent_os.cli",
              "--db",str(self.db),"--workspace",str(self.ws),"--fixtures",str(self.fx)]
        def cli(args):
            return subprocess.run(base+args,env=env,capture_output=True,text=True,timeout=12)
        incomplete=cli(["seed-reconciliation","--reference","expect.csv",
                        "--observed","actual.csv","--relationship-contract","relationship.json"])
        self.assertNotEqual(incomplete.returncode,0)
        correct=cli(["seed-reconciliation","--reference","expect.csv",
                     "--observed","actual.csv","--relationship-contract","relationship.json",
                     "--expected-contract-sha256",spec["relationship_contract"]["expected_sha256"]])
        self.assertEqual(correct.returncode,0,correct.stderr)
        child=json.loads(correct.stdout)["task_id"]
        r=cli(["worker-once"])
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"],"NEEDS_REVIEW")
        result=cli(["reconciliation-audit","--task-id",child])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"],"REPORT_MECHANICALLY_VERIFIED")


if __name__=="__main__":
    unittest.main()
