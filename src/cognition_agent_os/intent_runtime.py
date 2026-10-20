"""P9 durable intent decomposition in the original SQLite task/grant ledger.

No second agent state. No recursive plan execution. Compiled steps are a
trusted static capability map, not model-authored executable instructions.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .ledger import connect, create_task, current_guard, event, finalize
from .intent_planner import compile_intent, IntentError


def run_intent(db: sqlite3.Connection, task: dict) -> dict:
    tid=task["task_id"]
    try:
        plan=compile_intent(json.loads(task["source_spec"]))
    except (IntentError,TypeError,KeyError,ValueError):
        finalize(db,task,"UNKNOWN",error_code="INTENT_NOT_ADMITTED")
        return {"task_id":tid,"status":"UNKNOWN","reason":"INTENT_NOT_ADMITTED"}
    if task["parent_task"] is not None:
        finalize(db,task,"UNKNOWN",error_code="INTENT_RECURSION_REFUSED")
        return {"task_id":tid,"status":"UNKNOWN","reason":"INTENT_RECURSION_REFUSED"}
    db.execute("BEGIN IMMEDIATE")
    try:
        claimed=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
        if (not claimed or claimed["state"]!="RUNNING"
                or claimed["claim_token"]!=task["claim_token"]):
            db.commit()
            return {"task_id":tid,"status":"STALE_WORKER"}
        allowed,reason=current_guard(db,task,needs_write=True)
        if not allowed:
            db.execute("""UPDATE tasks SET state='BLOCKED',error_code=?,
                       state_version=state_version+1,lease_until=NULL,claim_token=NULL
                       WHERE task_id=?""",(reason,tid))
            event(db,tid,"INTENT_BLOCKED",{"reason":reason})
            db.commit()
            return {"task_id":tid,"status":"BLOCKED","reason":reason}
        child=create_task(db,plan["child_source_spec"],parent=tid,commit=False)
        db.execute("""UPDATE tasks SET state='DECOMPOSED',decision=?,
                   error_code=NULL,state_version=state_version+1,
                   lease_until=NULL,claim_token=NULL WHERE task_id=?""",
                   ("REGISTERED_CAPABILITY_PLAN",tid))
        event(db,tid,"INTENT_DECOMPOSED",{"child_task_id":child,"plan":plan,
                                         "semantic_approval":False})
        db.commit()
        return {"task_id":tid,"status":"DECOMPOSED",
                "child_task_id":child,"capability":plan["capability"],
                "plan_sha256":plan["plan_sha256"],
                "business_outcome_verified":False}
    except BaseException:
        db.rollback()
        raise


def audit_intent_plan(db_path: Path, task_id: str) -> dict:
    """Read-only recomputation of a persisted intent decomposition receipt."""
    import re
    fail={"task_id":task_id,"status":"UNVERIFIABLE",
          "business_outcome_verified":False}
    if not isinstance(task_id,str) or not re.fullmatch("[a-f0-9]{32}",task_id):
        return {**fail,"reason":"INVALID_TASK_ID"}
    if not db_path.is_file() or db_path.is_symlink():
        return {**fail,"reason":"MISSING_LEDGER"}
    try:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True)) as db:
            db.row_factory=sqlite3.Row
            parent=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            rows=db.execute("""SELECT details FROM events WHERE task_id=?
                               AND kind='INTENT_DECOMPOSED'""",(task_id,)).fetchall()
            if not parent or parent["state"]!="DECOMPOSED" or len(rows)!=1:
                return {**fail,"reason":"PLAN_EVENT_UNAVAILABLE"}
            stored=json.loads(rows[0]["details"])
            if set(stored)!={"child_task_id","plan","semantic_approval"} or stored["semantic_approval"] is not False:
                return {**fail,"reason":"INVALID_PLAN_RECEIPT"}
            plan=compile_intent(json.loads(parent["source_spec"]))
            if stored["plan"]!=plan:
                return {**fail,"reason":"PLAN_DIGEST_OR_DECOMPOSITION_MISMATCH"}
            child=db.execute("SELECT * FROM tasks WHERE task_id=?",
                             (stored["child_task_id"],)).fetchone()
            other=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",(task_id,)).fetchone()[0]
            if (not child or other!=1 or child["parent_task"]!=task_id or
                    json.loads(child["source_spec"])!=plan["child_source_spec"] or
                    child["goal_rev"]!=parent["goal_rev"] or
                    child["grant_rev"]!=parent["grant_rev"]):
                return {**fail,"reason":"CHILD_TASK_IDENTITY_MISMATCH"}
            return {"task_id":task_id,"status":"PLAN_MECHANICALLY_VALID",
                    "plan_sha256":plan["plan_sha256"],
                    "child_task_id":child["task_id"],
                    "business_outcome_verified":False,
                    "authorizes_production_mutation":False}
    except (sqlite3.Error,ValueError,TypeError,KeyError,OSError,IntentError):
        return {**fail,"reason":"AUDIT_INPUT_UNAVAILABLE"}
