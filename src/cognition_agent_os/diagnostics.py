"""P7 bounded diagnostic routing using existing authoritative task/event ledger.

This is evidence-driven *mechanical* diagnosis with competing hypotheses,
not a claim to infer true causal explanations or to approve business actions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .ledger import connect, create_task, event
from .goal_loop import plan_goal, validate_goal, GoalError
from .source import safe_fixture
from .goal_audit import audit_goal

READ_RETRY_SECONDS = 900
MAX_RECOVERY_PER_TICK = 4
MAX_REPLAN_DEPTH = 2

AUDIT_FAILURES = frozenset({
    "STALE_AUTHORITY", "ARTIFACT_UNAVAILABLE", "ARTIFACT_HASH_MISMATCH",
    "ARTIFACT_IDENTITY_MISMATCH", "INVALID_PROPOSAL",
    "CANDIDATE_HASH_MISMATCH", "CANDIDATE_CONSTRAINTS_FAILED",
    "AUDIT_UNVERIFIABLE", "NOT_GOAL_CASE", "UNSAFE_WORKSPACE"
})


def _classify_audit(reason: str) -> tuple[str, str, str]:
    if reason == "STALE_AUTHORITY":
        return "AUTHORITY_INVALID", "STOP_UNTIL_EXPLICIT_REAUTHORIZATION", "BLOCKED"
    if reason in {
        "ARTIFACT_HASH_MISMATCH", "ARTIFACT_IDENTITY_MISMATCH",
        "CANDIDATE_HASH_MISMATCH", "CANDIDATE_CONSTRAINTS_FAILED",
        "INVALID_PROPOSAL"
    }:
        return "UNTRUSTED_CANDIDATE", "ISOLATE_REJECTED_CANDIDATE", "UNKNOWN"
    return "MISSING_OR_UNRELIABLE_EVIDENCE", "REQUIRE_NEW_VALID_EVIDENCE", "UNKNOWN"


def record_audit_failure(db: sqlite3.Connection, task: sqlite3.Row,
                         reason: str, *, error_prefix: str="AUDIT") -> dict:
    """Caller holds BEGIN IMMEDIATE and has independently reaudited reason."""
    if reason not in AUDIT_FAILURES:
        raise ValueError("Unrecognized audit failure")
    group, action, state = _classify_audit(reason)
    db.execute("""UPDATE tasks SET state=?,error_code=?,state_version=state_version+1,
               lease_until=NULL,claim_token=NULL WHERE task_id=? AND state='NEEDS_REVIEW'""",
               (state,error_prefix+"_"+reason,task["task_id"]))
    event(db,task["task_id"],"DIAGNOSIS_RECORDED",{
        "observation":reason,
        "candidate_explanations":[
            "Candidate or original artifact may be corrupted",
            "Original evidence, state or authority may have changed"
        ],
        "evidence_class":group,
        "next_action":action,
        "causal_root_proven":False
    })
    return {"task_id":task["task_id"],"status":"NOT_ADMITTED",
            "reason":reason,"diagnosis":group,"next_action":action,
            "business_outcome_verified":False}


def reject_review_if_untrusted(db_path: Path, workspace: Path,
                               fixtures: Path, task_id: str) -> dict:
    """Freshly re-evaluate in write lock; stale preaudit cannot close good work."""
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        task=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        if not task:
            db.commit()
            return {"task_id":task_id,"status":"NOT_ADMITTED",
                    "reason":"TASK_NOT_FOUND"}
        if task["state"]!="NEEDS_REVIEW":
            # The shared conformance sweep may have diagnosed and quarantined
            # this task earlier in the same admission path. Return that durable
            # diagnosis rather than losing it behind a generic not-pending reply.
            recorded=db.execute("""SELECT details FROM events
                WHERE task_id=? AND kind='DIAGNOSIS_RECORDED'
                ORDER BY event_id DESC LIMIT 1""",(task_id,)).fetchone()
            if recorded:
                details=json.loads(recorded["details"])
                db.commit()
                return {"task_id":task_id,"status":"NOT_ADMITTED",
                        "reason":details.get("observation"),
                        "diagnosis":details.get("evidence_class"),
                        "next_action":details.get("next_action"),
                        "business_outcome_verified":False}
            db.commit()
            return {"task_id":task_id,"status":"NOT_ADMITTED",
                    "reason":"TASK_NOT_PENDING_REVIEW"}
        actual=audit_goal(db_path,workspace,fixtures,task_id)
        if actual["status"]=="CANDIDATE_MECHANICALLY_VALID" or actual["status"]=="SOURCE_CHANGED_SINCE_PROPOSAL":
            db.commit()
            return {"task_id":task_id,"status":"RECHECK_REQUIRED","reason":actual["status"]}
        if actual["status"] not in AUDIT_FAILURES:
            db.commit()
            return {"task_id":task_id,"status":"NOT_ADMITTED","reason":actual["status"]}
        response=record_audit_failure(db,task,actual["status"])
        db.commit()
        return response
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _lineage_depth(db: sqlite3.Connection, task: sqlite3.Row) -> int:
    seen={task["task_id"]}
    depth=0
    parent=task["parent_task"]
    while parent is not None:
        if parent in seen or depth>MAX_REPLAN_DEPTH:
            return MAX_REPLAN_DEPTH+1
        seen.add(parent)
        item=db.execute("SELECT parent_task FROM tasks WHERE task_id=?",(parent,)).fetchone()
        if not item:
            return MAX_REPLAN_DEPTH+1
        depth+=1
        parent=item["parent_task"]
    return depth


def recover_one_unknown(db_path: Path, fixture_root: Path, task_id: str,
                        *, now: float | None=None) -> dict:
    """Recover only newly adequate evidence for a bounded declarative goal.

    Never rerun an invalid candidate blindly; re-derive a NEW immutable child
    after re-reading a currently valid local source. At most two child replans.
    """
    now=time.time() if now is None else now
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        task=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        if (not task or task["state"]!="UNKNOWN"
            or task["error_code"]!="GOAL_EVIDENCE_UNAVAILABLE" or task["due_at"]>now):
            db.commit()
            return {"task_id":task_id,"status":"NOT_DUE_OR_UNSUPPORTED"}
        owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if (not owner or not owner["write_allowed"] or
            task["goal_rev"]!=owner["goal_rev"] or task["grant_rev"]!=owner["grant_rev"]):
            db.execute("UPDATE tasks SET state=?,error_code=?,state_version=state_version+1 WHERE task_id=?",
                       ("BLOCKED","STALE_RECOVERY_AUTHORITY",task_id))
            event(db,task_id,"DIAGNOSIS_BLOCKED",{"reason":"STALE_RECOVERY_AUTHORITY"})
            db.commit()
            return {"task_id":task_id,"status":"BLOCKED"}
        try:
            spec=validate_goal(json.loads(task["source_spec"]))
            first=safe_fixture(fixture_root,spec["input"])
            second=safe_fixture(fixture_root,spec["input"])
            if first!=second: raise GoalError("Unstable source")
            plan=plan_goal(spec,first)
        except (GoalError,ValueError,KeyError,TypeError,OSError) as exc:
            db.execute("UPDATE tasks SET due_at=? WHERE task_id=?",
                       (now+READ_RETRY_SECONDS,task_id))
            # Record one bounded diagnosis per tick, never a fabricated source.
            event(db,task_id,"DIAGNOSIS_EVIDENCE_STILL_MISSING",
                  {"evidence_kind":type(exc).__name__,"next_action":"RECHECK_AFTER_COOLDOWN"})
            db.commit()
            return {"task_id":task_id,"status":"EVIDENCE_PENDING",
                    "next_check_at":now+READ_RETRY_SECONDS}
        if plan["selection"] is None:
            db.execute("""UPDATE tasks SET state=?,error_code=?,state_version=state_version+1
                          WHERE task_id=?""",
                       ("UNKNOWN","NO_SAFE_GOAL_PLAN",task_id))
            event(db,task_id,"DIAGNOSIS_RECORDED",{
                "evidence_sha256":hashlib.sha256(first).hexdigest(),
                "next_action":"REQUIRE_NEW_AUTHORIZED_DECISION",
                "causal_root_proven":False})
            db.commit()
            return {"task_id":task_id,"status":"NO_SAFE_GOAL_PLAN"}
        if _lineage_depth(db,task)>=MAX_REPLAN_DEPTH:
            db.execute("""UPDATE tasks SET error_code=?,state_version=state_version+1
                          WHERE task_id=?""",
                       ("REPLAN_BUDGET_EXHAUSTED",task_id))
            event(db,task_id,"DIAGNOSIS_REPLAN_EXHAUSTED",{})
            db.commit()
            return {"task_id":task_id,"status":"REPLAN_EXHAUSTED"}
        child=create_task(db,spec,parent=task_id,commit=False)
        db.execute("""UPDATE tasks SET state=?,error_code=?,state_version=state_version+1
                      WHERE task_id=?""",
                   ("NEEDS_REPLAN","EVIDENCE_NOW_AVAILABLE",task_id))
        event(db,task_id,"DIAGNOSIS_REPLAN",{
            "evidence_sha256":hashlib.sha256(first).hexdigest(),
            "next_task_id":child,
            "next_action":"REBUILD_CANDIDATE_FROM_NEW_EVIDENCE",
            "causal_root_proven":False
        })
        db.commit()
        return {"task_id":task_id,"status":"REPLAN_QUEUED","next_task_id":child}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def recover_due_unknowns(db_path: Path, fixtures: Path,
                         *, max_cases: int=MAX_RECOVERY_PER_TICK) -> list[dict]:
    if not 1<=max_cases<=MAX_RECOVERY_PER_TICK:
        raise ValueError("Recovery batch out of bounds")
    db=connect(db_path)
    try:
        rows=db.execute("""SELECT task_id FROM tasks
              WHERE state='UNKNOWN' AND error_code='GOAL_EVIDENCE_UNAVAILABLE'
              AND due_at<=? ORDER BY due_at,created_at LIMIT ?""",
              (time.time(),max_cases)).fetchall()
        ids=[r["task_id"] for r in rows]
    finally:
        db.close()
    return [recover_one_unknown(db_path,fixtures,tid) for tid in ids]

# Research retries share the existing task ledger and host, not a second scheduler.
RESEARCH_RETRY_SECONDS = 300
MAX_RESEARCH_RETRIES = 2

def recover_research_transport(db_path: Path, *, now: float | None = None,
                               max_cases: int = 4) -> list[dict]:
    """Bounded, cooldown-gated requeue of strictly read-only GitHub transport errors.

    No other UNKNOWN cause is retried. Existing task ID/lineage is preserved;
    authority revisions and parent state are rechecked under the same write lock.
    """
    if not 1 <= max_cases <= 4:
        raise ValueError("Recovery batch out of bounds")
    now = time.time() if now is None else now
    db = connect(db_path)
    outcomes = []
    try:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("""SELECT * FROM tasks WHERE state='UNKNOWN'
            AND error_code='RESEARCH_TRANSPORT_UNAVAILABLE' AND due_at<=?
            ORDER BY due_at,created_at LIMIT ?""", (now,max_cases)).fetchall()
        owner = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        for row in rows:
            tid=row["task_id"]
            try:
                spec=json.loads(row["source_spec"])
            except (ValueError,TypeError):
                spec={}
            parent=db.execute("SELECT * FROM tasks WHERE task_id=?",
                              (row["parent_task"],)).fetchone()
            safe=(spec.get("kind")=="research_assessment"
                  and isinstance(spec.get("sources"),list)
                  and len(spec["sources"])==2
                  and all(isinstance(s,dict) and s.get("kind")=="github"
                          for s in spec["sources"])
                  and parent is not None and parent["state"]=="NEEDS_REVIEW"
                  and owner is not None and owner["write_allowed"]==1
                  and row["goal_rev"]==owner["goal_rev"]
                  and row["grant_rev"]==owner["grant_rev"]
                  and row["goal_rev"]==parent["goal_rev"]
                  and row["grant_rev"]==parent["grant_rev"])
            attempts=db.execute("""SELECT COUNT(*) FROM events WHERE task_id=?
                                   AND kind='RESEARCH_TRANSPORT_RETRY_QUEUED'""",
                                (tid,)).fetchone()[0]
            if not safe or attempts>=MAX_RESEARCH_RETRIES:
                if attempts>=MAX_RESEARCH_RETRIES:
                    db.execute("UPDATE tasks SET error_code='RESEARCH_RETRY_EXHAUSTED',state_version=state_version+1 WHERE task_id=?", (tid,))
                    event(db,tid,"RESEARCH_TRANSPORT_RETRY_EXHAUSTED",{"attempts":attempts})
                else:
                    # Invalid lineage/authorization must not be re-scanned as a
                    # recoverable network error on every unattended host tick.
                    reason = ("STALE_RECOVERY_AUTHORITY"
                              if owner is None or owner["write_allowed"]!=1
                              or row["goal_rev"]!=owner["goal_rev"]
                              or row["grant_rev"]!=owner["grant_rev"]
                              else "RESEARCH_RETRY_LINEAGE_INVALID")
                    db.execute("""UPDATE tasks SET state='BLOCKED',error_code=?,
                        state_version=state_version+1 WHERE task_id=?""", (reason,tid))
                    event(db,tid,"RESEARCH_TRANSPORT_RETRY_BLOCKED",
                          {"reason":reason})
                outcomes.append({"task_id":tid,"status":"RETRY_NOT_ADMITTED"})
                continue
            # No side effect in the failed attempt: no artifact, no provider write.
            db.execute("""UPDATE tasks SET state='PENDING',error_code=NULL,
                due_at=?,state_version=state_version+1
                WHERE task_id=? AND state='UNKNOWN'""",
                (now+RESEARCH_RETRY_SECONDS,tid))
            event(db,tid,"RESEARCH_TRANSPORT_RETRY_QUEUED",
                  {"attempt":attempts+1,"next_check_at":now+RESEARCH_RETRY_SECONDS})
            outcomes.append({"task_id":tid,"status":"RETRY_QUEUED",
                             "attempt":attempts+1})
        db.commit()
        return outcomes
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
