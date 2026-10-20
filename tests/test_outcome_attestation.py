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
        from cognition_agent_os.signed_feedback import bind_owner_review_trust
        bound=bind_owner_review_trust(
            self.dbpath,self.work,self.fx,self.allowed,self.pinned,
            expected_principal=self.principal)
        self.assertEqual(bound["status"],"OWNER_TRUST_BOUND",bound)

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

    def test_unsigned_subject_matches_real_lab_but_cannot_self_approve(self):
        from cognition_agent_os.outcome_attestation import prepare_unsigned_outcome
        draft=prepare_unsigned_outcome(self.dbpath,self.work,self.fx,self.tid,
                                       reviewer_principal=self.principal)
        self.assertEqual(draft["status"],"UNSIGNED_REVIEW_SUBJECT",draft)
        self.assertFalse(draft["gold_answers_exported"])
        self.assertFalse(draft["private_key_used"])
        self.assertEqual(draft["statement"]["outcome"],"REVIEW_REQUIRED")
        self.assertEqual(draft["statement"]["candidate_sha256"],
                         self.statement()["candidate_sha256"])
        # A candidate proposing 'REVIEW_REQUIRED' has no accepted signature,
        # even if an external test signer signs this unreviewed draft.
        self.sign(draft["statement"])
        self.assertEqual(self.audit()["status"],"UNVERIFIABLE")
        self.assertEqual(self.task()["state"],"REPAIR_LAB_VERIFIED")
        # Only a reviewer may change the verdict and sign externally.
        attested=dict(draft["statement"])
        attested["outcome"]="DOMAIN_REJECTED"
        attested["rationale"]="Independent evidence from test reviewer found an unrelated behavior."
        self.sign(attested)
        self.assertEqual(self.audit()["signed_outcome"],"DOMAIN_REJECTED")

    def test_unsigned_cli_does_not_create_signature_or_change_ledger(self):
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        args=[sys.executable,"-m","cognition_agent_os.cli",
              "--db",str(self.dbpath),"--workspace",str(self.work),
              "--fixtures",str(self.fx),
              "attestation-subject","--task-id",self.tid,"--principal",self.principal]
        before=self.task()
        r=subprocess.run(args,capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        result=json.loads(r.stdout)
        self.assertEqual(result["status"],"UNSIGNED_REVIEW_SUBJECT")
        self.assertEqual(result["statement"]["task_id"],self.tid)
        self.assertFalse(self.sig.exists())
        self.assertEqual(self.task(),before)

    def test_signed_feedback_requires_prebound_operator_trust_root(self):
        from cognition_agent_os.signed_feedback import (
            record_signed_feedback,bind_owner_review_trust)
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        db=connect(self.dbpath)
        db.execute("DELETE FROM owner_outcome_trust")
        db.commit();db.close()
        outcome=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,self.pinned,
              expected_principal=self.principal)
        self.assertEqual(outcome["status"],"SIGNED_FEEDBACK_UNBOUND_TRUST_ROOT")
        db=connect(self.dbpath)
        self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='signed_outcome_feedback'").fetchone())
        db.close()
        bound=bind_owner_review_trust(
            self.dbpath,self.work,self.fx,self.allowed,self.pinned,
            expected_principal=self.principal)
        self.assertEqual(bound["status"],"OWNER_TRUST_BOUND")

    def test_owner_trust_cannot_be_replaced_by_other_signed_self_claim(self):
        from cognition_agent_os.signed_feedback import (
            record_signed_feedback,bind_owner_review_trust)
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        other=self.trust/"new_allowed"
        other.write_bytes(self.allowed.read_bytes()+b"# extra signer\n")
        replacement=hashlib.sha256(other.read_bytes()).hexdigest()
        changed=bind_owner_review_trust(
            self.dbpath,self.work,self.fx,other,replacement,
            expected_principal=self.principal)
        self.assertEqual(changed["status"],"OWNER_TRUST_IMMUTABLE_CONFLICT")
        impostor=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,other,replacement,
              expected_principal=self.principal)
        self.assertEqual(impostor["status"],"SIGNED_FEEDBACK_UNBOUND_TRUST_ROOT")
        db=connect(self.dbpath)
        first=db.execute("SELECT trusted_signers_sha256 FROM owner_outcome_trust").fetchone()
        self.assertEqual(first[0],self.pinned)
        db.close()

    def test_owner_trust_binding_refuses_missing_uninitialized_authority(self):
        from cognition_agent_os.signed_feedback import bind_owner_review_trust
        missing=self.base/"unseeded.sqlite"
        missing.write_bytes(b"")
        outcome=bind_owner_review_trust(
            missing,self.work,self.fx,self.allowed,self.pinned,
            expected_principal=self.principal)
        self.assertEqual(outcome["status"],"AUTHORITY_NOT_INITIALIZED")
        self.assertEqual(missing.stat().st_size,0)

    def _record_negative_for_historical_tests(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        outcome=record_signed_feedback(
            self.dbpath,self.work,self.fx,self.statement_file,self.sig,
            self.allowed,self.pinned,expected_principal=self.principal)
        self.assertEqual(outcome["status"],"SIGNED_FEEDBACK_RECORDED",outcome)

    def _repeat_exact_task(self):
        db=connect(self.dbpath)
        tid=create_task(db,self.spec)
        db.close()
        result=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(result["task_id"],tid)
        return tid,result

    def test_forged_db_feedback_signature_does_not_reject_method_as_authentic(self):
        self._record_negative_for_historical_tests()
        db=connect(self.dbpath)
        db.execute("UPDATE signed_outcome_feedback SET signed_signature=?",
                   (b"-----BEGIN SSH SIGNATURE-----\\nFAKE\\n-----END SSH SIGNATURE-----",))
        db.commit();db.close()
        tid,result=self._repeat_exact_task()
        self.assertEqual(result["reason"],"SIGNED_FEEDBACK_PROOF_UNVERIFIABLE")
        self.assertTrue(result["untrusted_memory_did_not_change_method"])
        self.assertFalse((self.work/"artifacts"/(tid+".json")).exists())

    def test_forged_db_feedback_hash_cannot_self_certify_signature(self):
        self._record_negative_for_historical_tests()
        forged=b"-----BEGIN SSH SIGNATURE-----\\nFAKE\\n-----END SSH SIGNATURE-----"
        db=connect(self.dbpath)
        db.execute("""UPDATE signed_outcome_feedback
                   SET signed_signature=?,signature_sha256=?""",
                   (forged,hashlib.sha256(forged).hexdigest()))
        db.commit();db.close()
        tid,result=self._repeat_exact_task()
        self.assertEqual(result["reason"],"SIGNED_FEEDBACK_PROOF_UNVERIFIABLE")
        self.assertFalse((self.work/"artifacts"/(tid+".json")).exists())

    def test_signed_feedback_laundered_to_wrong_visible_scope_is_refused(self):
        self._record_negative_for_historical_tests()
        public=json.loads((self.fx/"public.json").read_text())
        public.append({"args":[12,12],"expected":True})
        data=json.dumps(public).encode()
        (self.fx/"public.json").write_bytes(data)
        db=connect(self.dbpath)
        db.execute("""UPDATE signed_outcome_feedback SET public_cases_sha256=?""",
                   (hashlib.sha256(data).hexdigest(),))
        db.commit();db.close()
        tid,result=self._repeat_exact_task()
        self.assertEqual(result["reason"],"SIGNED_FEEDBACK_PROOF_UNVERIFIABLE")
        self.assertFalse((self.work/"artifacts"/(tid+".json")).exists())

    def test_external_trust_key_mutation_prevents_feedback_use(self):
        self._record_negative_for_historical_tests()
        self.allowed.write_bytes(self.allowed.read_bytes()+b"# changed externally\\n")
        _,result=self._repeat_exact_task()
        self.assertEqual(result["reason"],"SIGNED_FEEDBACK_PROOF_UNVERIFIABLE")

    def test_negative_method_proof_never_reads_sealed_gold_in_planner(self):
        from unittest.mock import patch
        from cognition_agent_os import repair_search as planner
        self._record_negative_for_historical_tests()
        real=planner.safe_fixture
        seen=[]
        def safe_only_public(root,name):
            seen.append(name)
            if name=="holdout.json":
                raise AssertionError("Planner is reading sealed gold")
            return real(root,name)
        with patch.object(planner,"safe_fixture",side_effect=safe_only_public):
            _,result=self._repeat_exact_task()
        self.assertEqual(result["reason"],"SIGNED_REVIEW_PREVIOUSLY_REJECTED")
        self.assertEqual(set(seen),{"rule.py","public.json"})

    def test_signed_rejection_persists_and_blocks_repeated_method(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        first=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,self.pinned,
              expected_principal=self.principal)
        self.assertEqual(first["status"],"SIGNED_FEEDBACK_RECORDED",first)
        self.assertTrue(first["repeated_method_blocked"])
        self.assertFalse(first["production_write_authorized"])
        self.assertEqual(self.task()["state"],"REPAIR_LAB_VERIFIED")
        db=connect(self.dbpath)
        repeated=create_task(db,self.spec)
        db.close()
        result=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(result["task_id"],repeated)
        self.assertEqual(result["reason"],"SIGNED_REVIEW_PREVIOUSLY_REJECTED")
        self.assertFalse((self.work/"artifacts"/(repeated+".json")).exists())
        second=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,self.pinned,
              expected_principal=self.principal)
        self.assertEqual(second["status"],"SIGNED_FEEDBACK_ALREADY_RECORDED")
        db=connect(self.dbpath)
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM signed_outcome_feedback").fetchone()[0],1)
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM events WHERE kind='EXTERNAL_SIGNED_OUTCOME_RECORDED'"
        ).fetchone()[0],1)
        db.close()

    def test_signed_acceptance_does_not_block_or_auto_deploy(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        self.sign(self.statement(outcome="DOMAIN_ACCEPTED"))
        output=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,self.pinned,
              expected_principal=self.principal)
        self.assertEqual(output["status"],"SIGNED_FEEDBACK_RECORDED")
        self.assertFalse(output["repeated_method_blocked"])
        self.assertFalse(output["production_write_authorized"])
        db=connect(self.dbpath)
        new=create_task(db,self.spec)
        db.close()
        retry=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(retry["task_id"],new)
        self.assertEqual(retry["status"],"NEEDS_REVIEW")
        self.assertEqual(self.task()["state"],"REPAIR_LAB_VERIFIED")
        self.assertFalse((self.work/"repair_lab"/(new+".py")).exists())

    def test_conflicting_signed_verdict_cannot_replace_persisted_review(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        params=[self.dbpath,self.work,self.fx,self.statement_file,
                self.sig,self.allowed,self.pinned]
        self.assertEqual(record_signed_feedback(*params,
            expected_principal=self.principal)["status"],"SIGNED_FEEDBACK_RECORDED")
        self.sign(self.statement(outcome="DOMAIN_ACCEPTED"))
        self.assertEqual(record_signed_feedback(*params,
            expected_principal=self.principal)["status"],"SIGNED_FEEDBACK_CONFLICT")
        db=connect(self.dbpath)
        row=db.execute("SELECT verdict FROM signed_outcome_feedback").fetchone()
        self.assertEqual(row[0],"DOMAIN_REJECTED")
        db.close()

    def test_forged_unsigned_event_never_blocks_a_new_method(self):
        from cognition_agent_os.ledger import event
        db=connect(self.dbpath)
        event(db,self.tid,"EXTERNAL_SIGNED_OUTCOME_RECORDED",{
            "verdict":"DOMAIN_REJECTED","statement_sha256":"0"*64,
            "production_write_authorized":False})
        new=create_task(db,self.spec)
        db.close()
        result=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(result["task_id"],new)
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        self.assertNotEqual(result.get("reason"),"SIGNED_REVIEW_PREVIOUSLY_REJECTED")

    def test_invalid_signature_and_replaced_trust_root_leave_no_feedback(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        wrong=json.loads(self.statement_file.read_text())
        wrong["outcome"]="DOMAIN_ACCEPTED"
        self.statement_file.write_text(json.dumps(wrong))
        output=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,self.pinned,
              expected_principal=self.principal)
        self.assertEqual(output["status"],"SIGNED_OUTCOME_REFUSED")
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        output=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,"f"*64,
              expected_principal=self.principal)
        self.assertEqual(output["status"],"SIGNED_OUTCOME_REFUSED")
        db=connect(self.dbpath)
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='signed_outcome_feedback'").fetchone()
        self.assertIsNone(exists)
        db.close()

    def test_revoke_authority_blocks_signed_feedback_import(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        from cognition_agent_os.ledger import alter_authority
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        db=connect(self.dbpath)
        alter_authority(db,revoke=True)
        db.close()
        outcome=record_signed_feedback(self.dbpath,self.work,self.fx,
              self.statement_file,self.sig,self.allowed,self.pinned,
              expected_principal=self.principal)
        self.assertEqual(outcome["status"],"SIGNED_FEEDBACK_AUTHORITY_BLOCKED")
        self.assertFalse(outcome["production_write_authorized"])

    def test_signed_rejection_exact_scope_allows_changed_public_evidence(self):
        from cognition_agent_os.signed_feedback import record_signed_feedback
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        self.assertEqual(record_signed_feedback(
            self.dbpath,self.work,self.fx,self.statement_file,self.sig,
            self.allowed,self.pinned,expected_principal=self.principal)["status"],
            "SIGNED_FEEDBACK_RECORDED")
        public=json.loads((self.fx/"public.json").read_text())
        public.append({"args":[10,10],"expected":True})
        (self.fx/"public.json").write_text(json.dumps(public))
        db=connect(self.dbpath)
        new=create_task(db,self.spec)
        db.close()
        result=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(result["task_id"],new)
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        self.assertEqual(result["mechanism"],"Gt->GtE")

    def test_attestation_record_cli_reuses_existing_ledger(self):
        self.sign(self.statement(outcome="DOMAIN_REJECTED"))
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        cmd=[sys.executable,"-m","cognition_agent_os.cli",
            "--db",str(self.dbpath),"--workspace",str(self.work),
            "--fixtures",str(self.fx),"attestation-record",
            "--statement",str(self.statement_file),
            "--signature",str(self.sig),
            "--allowed-signers",str(self.allowed),
            "--expected-allowed-sha256",self.pinned,
            "--principal",self.principal]
        first=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=20)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads(first.stdout)["status"],"SIGNED_FEEDBACK_RECORDED")
        duplicate=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=20)
        self.assertEqual(duplicate.returncode,0,duplicate.stderr)
        self.assertEqual(json.loads(duplicate.stdout)["status"],
                         "SIGNED_FEEDBACK_ALREADY_RECORDED")
        changed=list(cmd)
        changed[changed.index("--expected-allowed-sha256")+1]="0"*64
        bad=subprocess.run(changed,env=env,text=True,capture_output=True,timeout=20)
        self.assertEqual(bad.returncode,4,bad.stderr)

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
