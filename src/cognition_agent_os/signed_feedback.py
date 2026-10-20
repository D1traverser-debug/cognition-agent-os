"""Durable, bounded external review feedback in the ONE SQLite ledger.

The only source of new 'external' outcome evidence is P10.7 signature,
scope, and current held-out readback verification; a model cannot supply a
verdict. Import is a single-claim transaction under the original authority.
The receipt is historical provenance, NOT production approval or a theorem
that a reviewer's business judgement was correct.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .ledger import connect,event
from .outcome_attestation import verify_signed_outcome,_strict_json,_read,MAX_STATEMENT,MAX_SIGNATURE

TABLE="""CREATE TABLE IF NOT EXISTS signed_outcome_feedback(
    task_id TEXT PRIMARY KEY,
    verdict TEXT NOT NULL CHECK(verdict IN ('DOMAIN_ACCEPTED','DOMAIN_REJECTED')),
    statement_sha256 TEXT NOT NULL,
    signature_sha256 TEXT NOT NULL,
    trusted_signers_sha256 TEXT NOT NULL,
    reviewer_principal TEXT NOT NULL,
    original_source_sha256 TEXT NOT NULL,
    public_cases_sha256 TEXT NOT NULL,
    holdout_sha256 TEXT NOT NULL,
    candidate_sha256 TEXT NOT NULL,
    operator_mechanism TEXT NOT NULL,
    observed_at REAL NOT NULL
)"""

def _no(reason:str,**kw):
    return {"status":reason,"production_write_authorized":False,
            "external_business_truth_proven":False,**kw}


def record_signed_feedback(db_path:Path,workspace:Path,fixtures:Path,
                           statement_file:Path,signature_file:Path,
                           allowed_signers:Path,expected_allowed_sha256:str,
                           *,expected_principal:str)->dict:
    """Explicit import: no auto-approval, no new grant, no original mutation.

    Rechecks after acquiring SQLite's IMMEDIATE lock. One task may carry
    exactly one signed outcome; conflicts never replace earlier decisions.
    """
    checked=verify_signed_outcome(
        db_path,workspace,fixtures,statement_file,signature_file,
        allowed_signers,expected_allowed_sha256,expected_principal=expected_principal)
    if checked["status"]!="SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED":
        return _no("SIGNED_OUTCOME_REFUSED",reason=checked.get("reason",checked["status"]))
    try:
        source=_read(statement_file,MAX_STATEMENT)
        signature=_read(signature_file,MAX_SIGNATURE)
        statement=_strict_json(source)
        db=connect(db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",(statement["task_id"],)).fetchone()
            if (not authority or not row or not authority["write_allowed"]
                or authority["grant_rev"]!=row["grant_rev"]
                or authority["goal_rev"]!=row["goal_rev"]):
                db.commit()
                return _no("SIGNED_FEEDBACK_AUTHORITY_BLOCKED")
            # Verify the signature and original bytes AGAIN while this DB
            # transaction fences task/authority changes. Filesystem change
            # after this check is still possible without OS-level isolation.
            fresh=verify_signed_outcome(
                db_path,workspace,fixtures,statement_file,signature_file,
                allowed_signers,expected_allowed_sha256,
                expected_principal=expected_principal)
            if (fresh["status"]!="SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED" or
                fresh["statement_sha256"]!=hashlib.sha256(source).hexdigest()
                or fresh["candidate_sha256"]!=statement["candidate_sha256"]):
                db.commit()
                return _no("SIGNED_FEEDBACK_CHANGED_DURING_IMPORT")
            artifact_path=workspace/"artifacts"/(statement["task_id"]+".json")
            if artifact_path.is_symlink() or not artifact_path.is_file() or artifact_path.stat().st_size>32000:
                db.commit()
                return _no("SIGNED_FEEDBACK_ARTIFACT_MISSING")
            artifact=json.loads(artifact_path.read_bytes())
            if (artifact.get("task_id")!=statement["task_id"] or
                artifact.get("selected",{}).get("candidate_sha256")!=statement["candidate_sha256"]):
                db.commit()
                return _no("SIGNED_FEEDBACK_ARTIFACT_CHANGED")
            mechanism=artifact.get("selected",{}).get("mechanism")
            sh=artifact.get("source_sha256")
            vh=artifact.get("visible_sha256")
            if (not isinstance(mechanism,str) or not 1<=len(mechanism)<=100
                or any(not isinstance(h,str) or len(h)!=64 for h in (sh,vh))):
                db.commit()
                return _no("SIGNED_FEEDBACK_PROVENANCE_MISSING")
            receipt=(
                statement["task_id"],statement["outcome"],
                hashlib.sha256(source).hexdigest(),hashlib.sha256(signature).hexdigest(),
                expected_allowed_sha256,expected_principal,sh,vh,
                statement["holdout_sha256"],statement["candidate_sha256"],
                mechanism
            )
            db.execute(TABLE)
            previous=db.execute("""SELECT task_id,verdict,statement_sha256,
                signature_sha256,trusted_signers_sha256,reviewer_principal,
                original_source_sha256,public_cases_sha256,holdout_sha256,
                candidate_sha256,operator_mechanism
                FROM signed_outcome_feedback WHERE task_id=?""",
                (statement["task_id"],)).fetchone()
            if previous:
                if tuple(previous)!=receipt:
                    db.commit()
                    return _no("SIGNED_FEEDBACK_CONFLICT")
                db.commit()
                return _no("SIGNED_FEEDBACK_ALREADY_RECORDED",
                           task_id=statement["task_id"],signed_outcome=statement["outcome"])
            db.execute("""INSERT INTO signed_outcome_feedback(
                task_id,verdict,statement_sha256,signature_sha256,
                trusted_signers_sha256,reviewer_principal,original_source_sha256,
                public_cases_sha256,holdout_sha256,candidate_sha256,
                operator_mechanism,observed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(*receipt,time.time()))
            event(db,statement["task_id"],"EXTERNAL_SIGNED_OUTCOME_RECORDED",{
                "verdict":statement["outcome"],
                "statement_sha256":receipt[2],"signature_sha256":receipt[3],
                "trusted_signers_sha256":receipt[4],
                "candidate_sha256":receipt[9],
                "reviewer_principal":expected_principal,
                "task_source":"ORIGINAL_SIGNED_PATCH_EVIDENCE",
                "production_write_authorized":False,
                "domain_truth_proven":False})
            db.commit()
            return _no("SIGNED_FEEDBACK_RECORDED",task_id=statement["task_id"],
                       signed_outcome=statement["outcome"],
                       repeated_method_blocked=statement["outcome"]=="DOMAIN_REJECTED")
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
    except (sqlite3.Error,KeyError,ValueError,TypeError,OSError):
        return _no("SIGNED_FEEDBACK_UNAVAILABLE")


def previously_signed_rejected(db:sqlite3.Connection,*,original_sha256:str,
                                visible_sha256:str,holdout_sha256:str,
                                candidate_sha256:str,mechanism:str)->bool:
    """Historical signed negative experience, not the reviewer's gold labels.

    The table is created only by explicit signature import. If table is
    absent, ordinary code-repair path is unaffected. This does not allow
    unsigned or synthetic JSON event entries to masquerade as review.
    """
    table=db.execute("""SELECT 1 FROM sqlite_master
                        WHERE type='table' AND name='signed_outcome_feedback'""").fetchone()
    if not table:return False
    return db.execute("""SELECT 1 FROM signed_outcome_feedback
        WHERE verdict='DOMAIN_REJECTED'
          AND original_source_sha256=? AND public_cases_sha256=?
          AND holdout_sha256=? AND candidate_sha256=?
          AND operator_mechanism=? LIMIT 1""",
        (original_sha256,visible_sha256,holdout_sha256,candidate_sha256,
         mechanism)).fetchone() is not None
