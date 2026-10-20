"""P6: bounded sandbox enactment and independent readback of P5 goal candidates.

No fixture/source overwrite, external effect, model self-approval or business
VERIFIED. A write is scoped to workspace/sandbox/<task_id>.candidate only.
SQLite authority, task state and events remain the sole durable control owner.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from .ledger import connect, create_task, event
from .goal_audit import audit_goal, _constraints
from .diagnostics import record_audit_failure, reject_review_if_untrusted
from .goal_loop import validate_goal
from .source import safe_fixture

MAX_STAGE_BYTES=128*1024
MAX_REPLANS=2


def _result(task_id: str, status: str, **fields) -> dict:
    return {"task_id":task_id, "status":status, "sandbox_only":True,
            "business_outcome_verified":False, **fields}


def _atomic_stage(workspace: Path, task_id: str, candidate: bytes) -> str:
    """Create-once file effect, then actual readback. Reconcile unknown ACK."""
    if not workspace.is_dir() or workspace.is_symlink():
        raise OSError("Workspace must be pre-created regular directory")
    dest=workspace/"sandbox"
    if dest.is_symlink():
        raise OSError("Sandbox directory may not be symlink")
    dest.mkdir(exist_ok=True)
    filename=dest/(task_id+".candidate")
    try:
        fd=os.open(str(filename),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        if filename.is_symlink() or not filename.is_file() or filename.read_bytes()!=candidate:
            raise OSError("Existing sandbox outcome differs from immutable intent")
    else:
        with os.fdopen(fd,"wb") as out:
            out.write(candidate)
            out.flush()
            os.fsync(out.fileno())
    real=filename.read_bytes()
    if real!=candidate:
        raise OSError("Stage was not read back as written")
    return hashlib.sha256(real).hexdigest()


def _depth(db: sqlite3.Connection, task: sqlite3.Row) -> int:
    depth=0
    parent=task["parent_task"]
    seen={task["task_id"]}
    while parent is not None:
        if parent in seen or depth>=MAX_REPLANS+1:
            return MAX_REPLANS+1
        seen.add(parent)
        row=db.execute("SELECT parent_task FROM tasks WHERE task_id=?",(parent,)).fetchone()
        if row is None: return MAX_REPLANS+1
        depth+=1
        parent=row["parent_task"]
    return depth


def _followup_on_stale_source(db: sqlite3.Connection, task: sqlite3.Row,
                              reason: str) -> dict:
    if _depth(db,task)>=MAX_REPLANS:
        db.execute("""UPDATE tasks SET state='UNKNOWN',error_code='REPLAN_BUDGET_EXHAUSTED',
                     state_version=state_version+1 WHERE task_id=?""",(task["task_id"],))
        event(db,task["task_id"],"SANDBOX_REPLAN_EXHAUSTED",{"reason":reason})
        return _result(task["task_id"],"REPLAN_EXHAUSTED",reason=reason)
    spec=json.loads(task["source_spec"])
    validate_goal(spec)
    child_id=create_task(db,spec,parent=task["task_id"],commit=False)
    db.execute("""UPDATE tasks SET state='NEEDS_REPLAN',error_code=?,
               state_version=state_version+1 WHERE task_id=?""",(reason,task["task_id"]))
    event(db,task["task_id"],"SANDBOX_REPLAN",{"reason":reason,"child_id":child_id})
    return _result(task["task_id"],"REPLAN_QUEUED",next_task_id=child_id,reason=reason)


def stage_one(db_path: Path, workspace: Path, fixtures: Path, task_id: str,
              *, fault_after_effect: bool=False) -> dict:
    """Audit, then re-admit under BEGIN IMMEDIATE; inspect real file effect.

    Fault hook simulates a killed worker after the sandbox file is written but
    before SQLite commit. Retry reconciles identical immutable file.
    """
    from .conformance import capability_disabled
    if capability_disabled(db_path):
        return _result(task_id,"CAPABILITY_DISABLED",
                       reason="CONFORMANCE_INTEGRITY_CIRCUIT_OPEN")
    observed=audit_goal(db_path,workspace,fixtures,task_id)
    if observed["status"]=="CANDIDATE_MECHANICALLY_VALID":
        # Review the rest of the runtime BEFORE taking a new local effect.
        # Stale input cases below need replanning rather than a new write.
        from .conformance import effect_preflight
        preflight=effect_preflight(db_path,workspace,fixtures)
        if not preflight["admitted"]:
            return _result(task_id,"PREFLIGHT_BLOCKED",
                           reason=preflight["reason"],
                           preflight_status=preflight["status"],
                           capacity_reached=preflight["eligible"] is not None and
                           preflight["eligible"]>preflight["checked"])
    if observed["status"] not in ("CANDIDATE_MECHANICALLY_VALID",
                                  "SOURCE_CHANGED_SINCE_PROPOSAL"):
        response=reject_review_if_untrusted(db_path,workspace,fixtures,task_id)
        return _result(task_id,response["status"],
                       reason=response.get("reason"),
                       next_action=response.get("next_action"),
                       diagnosis=response.get("diagnosis"))
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        task=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        # The same write lock fences a circuit trip from concurrently
        # authorizing another sandbox file effect after a critical breach.
        guard_exists=db.execute("""SELECT 1 FROM sqlite_master
              WHERE type='table' AND name='conformance_capability_guard'""").fetchone()
        if guard_exists:
            blocked=db.execute("""SELECT disabled FROM conformance_capability_guard
                          WHERE kind='goal_sandbox_stage'""").fetchone()
            if blocked and blocked[0]:
                db.commit()
                return _result(task_id,"CAPABILITY_DISABLED",
                               reason="CONFORMANCE_INTEGRITY_CIRCUIT_OPEN")
        if not task or task["state"]!="NEEDS_REVIEW":
            db.commit()
            return _result(task_id,"NOT_PENDING_REVIEW")
        if (not owner or not owner["write_allowed"] or task["goal_rev"]!=owner["goal_rev"]
                or task["grant_rev"]!=owner["grant_rev"]):
            db.commit()
            return _result(task_id,"AUTHORITY_BLOCKED")
        # Re-run the independent full audit under lock; acquisition and task
        # authority can change between the initial check and commit.
        audit=audit_goal(db_path,workspace,fixtures,task_id)
        if audit["status"]=="SOURCE_CHANGED_SINCE_PROPOSAL":
            result=_followup_on_stale_source(db,task,"SOURCE_CHANGED_SINCE_PROPOSAL")
            db.commit()
            return result
        if audit["status"]!="CANDIDATE_MECHANICALLY_VALID":
            if audit["status"] in {
                "STALE_AUTHORITY","ARTIFACT_UNAVAILABLE","ARTIFACT_HASH_MISMATCH",
                "ARTIFACT_IDENTITY_MISMATCH","INVALID_PROPOSAL",
                "CANDIDATE_HASH_MISMATCH","CANDIDATE_CONSTRAINTS_FAILED",
                "AUDIT_UNVERIFIABLE","NOT_GOAL_CASE","UNSAFE_WORKSPACE"
            }:
                diagnosed=record_audit_failure(db,task,audit["status"])
                db.commit()
                return _result(task_id,"NOT_ADMITTED",reason=audit["status"],
                               diagnosis=diagnosed["diagnosis"],
                               next_action=diagnosed["next_action"])
            event(db,task_id,"SANDBOX_REFUSED",{"reason":audit["status"]})
            db.commit()
            return _result(task_id,"NOT_ADMITTED",reason=audit["status"])
        path=workspace/"artifacts"/(task_id+".json")
        record=json.loads(path.read_bytes())
        spec=json.loads(task["source_spec"])
        validate_goal(spec)
        original=safe_fixture(fixtures,spec["input"])
        candidate=record["candidate_text"].encode("utf-8")
        if (len(candidate)>MAX_STAGE_BYTES or
                hashlib.sha256(original).hexdigest()!=record["source_sha256"] or
                hashlib.sha256(candidate).hexdigest()!=record["candidate_sha256"] or
                not _constraints(spec,original,candidate)):
            event(db,task_id,"SANDBOX_REFUSED",{"reason":"EFFECT_PRECHECK_FAILED"})
            db.commit()
            return _result(task_id,"NOT_ADMITTED",reason="EFFECT_PRECHECK_FAILED")
        # Deliberately no calls to a model or anything that can mutate sources.
        try:
            effect_sha=_atomic_stage(workspace,task_id,candidate)
        except (OSError,ValueError):
            attempts=db.execute("SELECT COUNT(*) FROM events WHERE task_id=? AND kind=?", (task_id,"SANDBOX_EFFECT_UNCERTAIN")).fetchone()[0]+1
            event(db,task_id,"SANDBOX_EFFECT_UNCERTAIN",{"reason":"WRITE_OR_READBACK_UNCERTAIN","attempt":attempts})
            if attempts>=3:
                db.execute("UPDATE tasks SET state=?,error_code=?,state_version=state_version+1 WHERE task_id=?", ("UNKNOWN","SANDBOX_EFFECT_RETRY_EXHAUSTED",task_id))
            else:
                db.execute("UPDATE tasks SET due_at=? WHERE task_id=?",
                           (time.time()+60*attempts,task_id))
            db.commit()
            return _result(task_id,"EFFECT_RETRY_EXHAUSTED" if attempts>=3 else "EFFECT_UNKNOWN",reason="WRITE_OR_READBACK_UNCERTAIN",attempt=attempts)
        if fault_after_effect:
            os._exit(81)
        # Still inside exclusive ledger transaction, but fixture is NOT locked:
        # if original changed during file effect, retain a truthful UNKNOWN.
        latest=safe_fixture(fixtures,spec["input"])
        if hashlib.sha256(latest).hexdigest()!=record["source_sha256"]:
            db.execute("""UPDATE tasks SET state='UNKNOWN',error_code='SOURCE_CHANGED_DURING_EFFECT',
                          state_version=state_version+1 WHERE task_id=?""",(task_id,))
            event(db,task_id,"SANDBOX_EFFECT_UNCERTAIN",
                  {"reason":"SOURCE_CHANGED_DURING_EFFECT","effect_sha256":effect_sha})
            db.commit()
            return _result(task_id,"EFFECT_UNKNOWN",reason="SOURCE_CHANGED_DURING_EFFECT")
        if effect_sha!=record["candidate_sha256"]:
            db.commit()
            return _result(task_id,"EFFECT_UNKNOWN",reason="SANDBOX_HASH_MISMATCH")
        db.execute("""UPDATE tasks SET state='SANDBOX_VERIFIED',
                     decision='ISOLATED_CANDIDATE_READBACK_OK',error_code=NULL,
                     state_version=state_version+1 WHERE task_id=?""",(task_id,))
        event(db,task_id,"SANDBOX_EFFECT_VERIFIED",
              {"effect_sha256":effect_sha,"scope":"isolated_workspace_only"})
        db.commit()
        return _result(task_id,"SANDBOX_VERIFIED",effect_sha256=effect_sha,
                       source_untouched=True)
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def advance_due_reviews(db_path: Path, workspace: Path, fixtures: Path,
                        *, max_reviews: int=8) -> list[dict]:
    """Bounded host step; no hidden loop or unbounded new job creation."""
    if not 1<=max_reviews<=16:raise ValueError("Review batch outside bound")
    from .conformance import capability_disabled
    if capability_disabled(db_path):
        return []
    db=connect(db_path)
    try:
        rows=db.execute("""SELECT task_id FROM tasks
           WHERE state='NEEDS_REVIEW' AND due_at<=?
             AND CASE WHEN json_valid(source_spec)
                      THEN json_extract(source_spec,'$.kind') ELSE NULL END='goal_case'
           ORDER BY due_at,created_at,task_id LIMIT ?""",
           (time.time(),max_reviews)).fetchall()
        ids=[row["task_id"] for row in rows]
    finally:
        db.close()
    return [stage_one(db_path,workspace,fixtures,task_id) for task_id in ids]
