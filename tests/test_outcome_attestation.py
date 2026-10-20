"""Live OS public-key signature tests, not mocked reviewer authorization.

Ephemeral independent ssh-keygen Ed25519 signer is owned by test harness,
never passed to the Agent. This only proves a cryptographic boundary
works on the runner; it is NOT a real human/domain reviewer attestation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from cognition_agent_os.ledger import connect,create_task,initialize
from cognition_agent_os.runner import run_once
from cognition_agent_os.repair_oracle import review_patch
from cognition_agent_os.outcome_attestation import (
    verify_signed_outcome,NAMESPACE
)

ROOT=Path(__file__).resolve().parents[1]
SSH=shutil.which("ssh-keygen")


@unittest.skipUnless(SSH,"OpenSSH required for native OS attestation integration")
class NativeSignedOutcomeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.fx=self.base/"fixtures";self.fx.mkdir()
        self.work=self.base/"workspace";self.work.mkdir()
        self.trust=self.base/"external_reviewer";self.trust.mkdir()
        self.dbpath=self.base/"state.sqlite"
        db=connect(self.dbpath);initialize(db);db.close()
        self.private=self.trust/"reviewer_private"
        p=subprocess.run([SSH,"-q","-t","ed25519","-N","","-f",str(self.private)],
                         capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)
        self.principal="reviewer@example.com"
        self.allowed=self.trust/"allowed_signers"
        self.allowed.write_bytes((self.principal+" "+
            self.private.with_suffix(".pub").read_text(encoding="utf-8").strip()+"\n"
        ).encode("utf-8"))
        self.pinned=hashlib.sha256(self.allowed.read_bytes()).hexdigest()
        self.fx.joinpath("rule.py").write_bytes(
            b"def condition(x, bound):\n    return x > bound\n")
        public=[{"args":[5,5],"expected":True},
                {"args":[6,5],"expected":True},
                {"args":[4,5],"expected":False}]
        sealed=[{"args":[7,7],"expected":True},
                {"args":[0,9],"expected":False},
                {"args":[15,8],"expected":True}]
        self.fx.joinpath("public.json").write_bytes(json.dumps(public).encode())
        self.hidden=json.dumps(sealed).encode()
        self.fx.joinpath("holdout.json").write_bytes(self.hidden)
        self.spec={"kind":"pure_code_repair","source":"rule.py",
            "function":"condition","visible":"public.json",
            "holdout":"holdout.json",
            "holdout_sha256":hashlib.sha256(self.hidden).hexdigest()}
        db=connect(self.dbpath)
        self.tid=create_task(db,self.spec)
        db.close()
        self.assertEqual(run_once(self.dbpath,self.work,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(review_patch(self.dbpath,self.work,self.fx,self.tid)["status"],
                         "REPAIR_LAB_VERIFIED")
        self.statement_file=self.trust/"outcome.json"
        self.sig=self.trust/"outcome.json.sig"

    def task(self):
        db=connect(self.dbpath)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",
                                  (self.tid,)).fetchone())
        finally:db.close()

    def statement(self,**changes):
        task=self.task()
        doc=json.loads((self.work/"artifacts"/(self.tid+".json")).read_text())
        now=int(time.time())
        payload={
            "schema_version":1,"purpose":"repair_lab_outcome",
            "reviewer_principal":self.principal,
            "task_id":self.tid,
            "goal_rev":task["goal_rev"],"grant_rev":task["grant_rev"],
            "source_spec_sha256":hashlib.sha256(
                task["source_spec"].encode()).hexdigest(),
            "proposal_sha256":task["artifact_hash"],
            "candidate_sha256":doc["selected"]["candidate_sha256"],
            "holdout_sha256":self.spec["holdout_sha256"],
            "outcome":"DOMAIN_ACCEPTED",
            "rationale":"Ephemeral test-reviewer evidence for limited AST code repair.",
            "issued_at":now-10,"expires_at":now+3600
        }
        payload.update(changes)
        return payload

    def sign(self,content:dict|None=None):
        if content is None:content=self.statement()
        self.statement_file.write_bytes(
            (json.dumps(content,sort_keys=True,separators=(",",":"))+"\n").encode())
        if self.sig.exists():self.sig.unlink()
        signed=subprocess.run([SSH,"-Y","sign","-f",str(self.private),
                               "-n",NAMESPACE,str(self.statement_file)],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(signed.returncode,0,signed.stderr)
        self.assertTrue(self.sig.exists())
        return content

    def audit(self,**kwargs):
        return verify_signed_outcome(
            self.dbpath,self.work,self.fx,self.statement_file,self.sig,
            self.allowed,self.pinned,expected_principal=self.principal,**kwargs)

    def test_signed_acceptance_checks_actual_lab_but_grants_no_authority(self):
        before=self.task()
        self.sign()
        verified=self.audit()
        self.assertEqual(verified["status"],"SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED",
                         verified)
        self.assertEqual(verified["signed_outcome"],"DOMAIN_ACCEPTED")
        self.assertTrue(verified["reviewer_key_possession_verified"])
        self.assertFalse(verified["key_holder_identity_authenticated"])
        self.assertFalse(verified["production_write_authorized"])
        self.assertFalse(verified["external_business_outcome_verified"])
        self.assertEqual(self.task(),before)

    def test_cryptographically_authentic_rejection_is_not_approval(self):
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        verified=self.audit()
        self.assertEqual(verified["status"],"SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED")
        self.assertEqual(verified["signed_outcome"],"DOMAIN_REJECTED")
        self.assertFalse(verified["production_write_authorized"])

    def test_forged_verdict_from_agent_without_private_key_is_rejected(self):
        doc=self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        doc["outcome"]="DOMAIN_ACCEPTED"
        self.statement_file.write_bytes(json.dumps(doc,sort_keys=True).encode())
        result=self.audit()
        self.assertEqual(result["status"],"UNVERIFIABLE")
        self.assertEqual(result["reason"],"REVIEWER_SIGNATURE_INVALID")

    def test_valid_signature_for_wrong_task_revision_or_candidate_fails_scope(self):
        for field,value,reason in [
            ("task_id","f"*32,"SIGNED_TASK_NOT_FOUND"),
            ("goal_rev",99,"SIGNED_TASK_SCOPE_MISMATCH"),
            ("grant_rev",99,"SIGNED_TASK_SCOPE_MISMATCH"),
            ("proposal_sha256","0"*64,"SIGNED_TASK_SCOPE_MISMATCH"),
            ("source_spec_sha256","0"*64,"SIGNED_TASK_SCOPE_MISMATCH"),
            ("candidate_sha256","0"*64,"SIGNED_CANDIDATE_OR_CURRENT_EVIDENCE_MISMATCH"),
            ("holdout_sha256","0"*64,"SIGNED_HOLDOUT_SCOPE_MISMATCH")
        ]:
            with self.subTest(field=field):
                self.sign(self.statement(**{field:value}))
                self.assertEqual(self.audit()["reason"],reason)

    def test_replaced_public_key_anchor_or_wrong_principal_never_accepts(self):
        self.sign()
        old=self.pinned
        self.pinned="a"*64
        self.assertEqual(self.audit()["reason"],"TRUSTED_PUBLIC_KEY_MISMATCH")
        self.pinned=old
        result=verify_signed_outcome(
            self.dbpath,self.work,self.fx,self.statement_file,self.sig,
            self.allowed,self.pinned,expected_principal="fake@example.com")
        self.assertEqual(result["reason"],"REVIEWER_PRINCIPAL_MISMATCH")
        # Merely changing allowed_signers is not sufficient when the
        # independently supplied expected digest remains pinned.
        self.allowed.write_bytes(self.allowed.read_bytes()+b"# attempt\n")
        self.assertEqual(self.audit()["reason"],"TRUSTED_PUBLIC_KEY_MISMATCH")

    def test_acceptance_revoked_by_artifact_or_holdout_mutation(self):
        self.sign()
        self.assertEqual(self.audit()["status"],"SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED")
        self.fx.joinpath("holdout.json").write_bytes(b"[]")
        self.assertEqual(self.audit()["reason"],"SIGNED_CANDIDATE_OR_CURRENT_EVIDENCE_MISMATCH")
        self.fx.joinpath("holdout.json").write_bytes(self.hidden)
        path=self.work/"repair_lab"/(self.tid+".py")
        path.write_text("def condition(x): return -1\n")
        self.assertEqual(self.audit()["reason"],"SIGNED_CANDIDATE_OR_CURRENT_EVIDENCE_MISMATCH")

    def test_expiry_future_signature_and_duplicate_keys_rejected(self):
        now=int(time.time())
        for time_mod in (
            {"issued_at":now-7200,"expires_at":now-1},
            {"issued_at":now+1000,"expires_at":now+3600},
            {"issued_at":now-5,"expires_at":now+50*86400},
        ):
            with self.subTest(time_mod=time_mod):
                self.sign(self.statement(**time_mod))
                self.assertEqual(self.audit()["status"],"UNVERIFIABLE")
        self.sign()
        body=self.statement_file.read_text().replace(
            '"schema_version":1,','"schema_version":1,"schema_version":1,')
        self.statement_file.write_text(body)
        self.assertEqual(self.audit()["status"],"UNVERIFIABLE")

    def test_reviewer_public_root_cannot_be_inside_agent_writable_workspace(self):
        self.sign()
        imported=self.work/"allowed_signers"
        imported.write_bytes(self.allowed.read_bytes())
        result=verify_signed_outcome(
            self.dbpath,self.work,self.fx,self.statement_file,self.sig,
            imported,hashlib.sha256(imported.read_bytes()).hexdigest(),
            expected_principal=self.principal)
        self.assertEqual(result["reason"],"TRUST_ANCHOR_INSIDE_AGENT_CONTROL")

    def test_cli_is_read_only_and_never_seeds_new_authority(self):
        self.sign()
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        args=[sys.executable,"-m","cognition_agent_os.cli",
              "--db",str(self.dbpath),"--workspace",str(self.work),
              "--fixtures",str(self.fx),"attestation-audit",
              "--statement",str(self.statement_file),
              "--signature",str(self.sig),
              "--allowed-signers",str(self.allowed),
              "--expected-allowed-sha256",self.pinned,
              "--principal",self.principal]
        r=subprocess.run(args,capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"],
                         "SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED")
        missing=self.base/"missing.sqlite"
        other=args[:]
        other[other.index("--db")+1]=str(missing)
        r=subprocess.run(other,capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(r.returncode,4,r.stderr)
        self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
