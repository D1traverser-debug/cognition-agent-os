"""Read-only independent reviewer-signed repair outcome verification.

External OpenSSH Ed25519/RSA keys are held by the reviewer, NEVER by the
Agent. Verifier accepts an independently pinned allowed_signers file.
It executes ssh-keygen -Y verify with fixed namespace (NO shell), then
rechecks current source, existing SQLite authority, sealed holdout and the
exact already-staged patch using the separate repair oracle.

An accepted signature is evidence of what the key holder asserted, NOT
semantic truth, write authority, or permission to release production code.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

from .repair_oracle import audit_patch

MAX_STATEMENT=8192
MAX_SIGNATURE=8192
MAX_SIGNERS=8192
SHA=re.compile(r"[0-9a-f]{64}\Z")
TASK_ID=re.compile(r"[0-9a-f]{32}\Z")
PRINCIPAL=re.compile(r"[a-zA-Z0-9_.@-]{3,120}\Z")
NAMESPACE="cognition-agent-os-outcome-v1"
KEYS=frozenset((
    "schema_version","purpose","reviewer_principal","task_id",
    "goal_rev","grant_rev","source_spec_sha256","proposal_sha256",
    "candidate_sha256","holdout_sha256","outcome","rationale"
))


class AttestationError(ValueError):
    pass


def _read(path: Path, limit: int) -> bytes:
    # Fail closed on symlinks even if they resolve to regular files.
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise AttestationError("Attestation evidence missing, linked, or too large")
    data=path.read_bytes()
    if not data or len(data)>limit:
        raise AttestationError("Attestation evidence empty or too large")
    return data


def _strict_json(data: bytes)->dict:
    def unique(items):
        output={}
        for name,value in items:
            if name in output:raise AttestationError("Duplicate signed JSON field")
            output[name]=value
        return output
    try:
        obj=json.loads(data,object_pairs_hook=unique)
    except (UnicodeError,ValueError,TypeError) as exc:
        raise AttestationError("Invalid signed statement") from exc
    if not isinstance(obj,dict) or set(obj)!=KEYS:
        raise AttestationError("Signed statement schema mismatch")
    if (type(obj["schema_version"]) is not int or obj["schema_version"]!=1
        or obj["purpose"]!="repair_lab_outcome"
        or not isinstance(obj["reviewer_principal"],str)
        or not PRINCIPAL.fullmatch(obj["reviewer_principal"])
        or not isinstance(obj["task_id"],str) or not TASK_ID.fullmatch(obj["task_id"])
        or type(obj["goal_rev"]) is not int or obj["goal_rev"]<1
        or type(obj["grant_rev"]) is not int or obj["grant_rev"]<1
        or obj["outcome"] not in ("DOMAIN_ACCEPTED","DOMAIN_REJECTED")
        or type(obj["rationale"]) is not str
        or not 15<=len(obj["rationale"])<=500):
        raise AttestationError("Invalid signed review statement values")
    for name in ("source_spec_sha256","proposal_sha256",
                 "candidate_sha256","holdout_sha256"):
        if type(obj[name]) is not str or not SHA.fullmatch(obj[name]):
            raise AttestationError("Malformed signed source fingerprint")
    return obj


def _failure(reason:str,**fields)->dict:
    return {"status":"UNVERIFIABLE","reason":reason,
            "external_business_outcome_verified":False,
            "production_write_authorized":False,
            "key_holder_identity_authenticated":False,**fields}


def verify_signed_outcome(db_path:Path, workspace:Path, fixtures:Path,
                          statement_file:Path, signature_file:Path,
                          allowed_signers:Path, expected_allowed_sha256:str,
                          *, expected_principal:str)->dict:
    """No ledger mutations, no public API, no private-key use, no model call."""
    if (not isinstance(expected_allowed_sha256,str) or
        not SHA.fullmatch(expected_allowed_sha256)):
        return _failure("NO_OUT_OF_BAND_TRUST_ANCHOR")
    if (not isinstance(expected_principal,str) or
        not PRINCIPAL.fullmatch(expected_principal)):
        return _failure("INVALID_REVIEWER_PRINCIPAL")
    if not db_path.is_file() or db_path.is_symlink() or workspace.is_symlink():
        return _failure("LOCAL_AUTHORITY_UNAVAILABLE")
    try:
        body=_read(statement_file,MAX_STATEMENT)
        sig=_read(signature_file,MAX_SIGNATURE)
        allowed=_read(allowed_signers,MAX_SIGNERS)
        if hashlib.sha256(allowed).hexdigest()!=expected_allowed_sha256:
            return _failure("TRUSTED_PUBLIC_KEY_MISMATCH")
        statement=_strict_json(body)
        if statement["reviewer_principal"]!=expected_principal:
            return _failure("REVIEWER_PRINCIPAL_MISMATCH")
        if b"-----BEGIN SSH SIGNATURE-----" not in sig or b"-----END SSH SIGNATURE-----" not in sig:
            return _failure("NOT_AN_OPENSSH_SIGNATURE")
        binary=shutil.which("ssh-keygen")
        if not binary:
            return _failure("SYSTEM_SIGNATURE_VERIFIER_NOT_INSTALLED")
        # Bound subprocess CPU wall time; no shell expansion, no network.
        checked=subprocess.run([
            binary,"-Y","verify","-f",str(allowed_signers),
            "-I",expected_principal,"-n",NAMESPACE,"-s",str(signature_file)
        ],input=body,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
           timeout=8,check=False)
        if checked.returncode!=0:
            return _failure("REVIEWER_SIGNATURE_INVALID")
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",
                           (statement["task_id"],)).fetchone()
            if row is None:
                return _failure("SIGNED_TASK_NOT_FOUND")
            if row["state"]!="REPAIR_LAB_VERIFIED":
                return _failure("SIGNED_RESULT_NOT_IN_VERIFIED_LAB")
            if (statement["goal_rev"]!=row["goal_rev"]
                or statement["grant_rev"]!=row["grant_rev"]
                or statement["source_spec_sha256"]!=hashlib.sha256(
                    row["source_spec"].encode()).hexdigest()
                or statement["proposal_sha256"]!=row["artifact_hash"]):
                return _failure("SIGNED_TASK_SCOPE_MISMATCH")
            try:
                spec=json.loads(row["source_spec"])
            except (ValueError,TypeError):
                return _failure("SIGNED_TASK_SPEC_INVALID")
            if (not isinstance(spec,dict)
                or spec.get("kind")!="pure_code_repair"
                or statement["holdout_sha256"]!=spec.get("holdout_sha256")):
                return _failure("SIGNED_HOLDOUT_SCOPE_MISMATCH")
        current=audit_patch(db_path,workspace,fixtures,statement["task_id"],
                            reveal_holdout=True,require_staged=True)
        if (current.get("status")!="HOLDOUT_ACCEPTED" or
            statement["candidate_sha256"]!=current.get("candidate_sha256")):
            return _failure("SIGNED_CANDIDATE_OR_CURRENT_EVIDENCE_MISMATCH")
        return {
            "status":"SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED",
            "signed_outcome":statement["outcome"],
            "reviewer_principal":expected_principal,
            "task_id":statement["task_id"],
            "statement_sha256":hashlib.sha256(body).hexdigest(),
            "trusted_signers_sha256":expected_allowed_sha256,
            "candidate_sha256":statement["candidate_sha256"],
            "source_and_holdout_rechecked":True,
            "external_business_outcome_verified":False,
            "key_holder_identity_authenticated":False,
            "reviewer_key_possession_verified":True,
            "production_write_authorized":False
        }
    except (AttestationError,OSError,sqlite3.Error,subprocess.TimeoutExpired,
            ValueError,TypeError,KeyError):
        return _failure("ATTESTATION_EVIDENCE_UNAVAILABLE")
