"""Opt-in, two-attempt LOCAL controller, inside the existing SQLite authority.

This is a bounded *candidate* selection loop, not external business autonomy.
An authorized caller must register two prevalidated different local methods
for one pinned goal. No LLM, user data mutation, external connectors, or
recursive task submission. A failed first attempt advances ONLY on an
independent, reproducible preservation-conflict verdict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from .bounded_outcome_oracle import assess_local_record, record_from_bytes
from .goal_audit import audit_goal
from .goal_loop import validate_goal
from .ledger import connect, create_task, current_guard, event
from .source import safe_fixture

_ID=re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_ACTIVE="CONTROL_ACTIVE"
_MET="CONTROL_CANDIDATE_MATCHED"
_STOP="CONTROL_STOPPED"
_UNVERIFIABLE="CONTROL_UNVERIFIABLE"
MAX_CONTROL_AGE_SECONDS=24*60*60


def _ensure(db:sqlite3.Connection)->None:
    db.execute("""CREATE TABLE IF NOT EXISTS bounded_goal_attempts(
        root_task_id TEXT NOT NULL REFERENCES tasks(task_id),
        ordinal INTEGER NOT NULL CHECK(ordinal IN (0,1)),
        child_task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id),
        PRIMARY KEY(root_task_id,ordinal))""")
    db.execute("""CREATE TABLE IF NOT EXISTS bounded_control_scan_cursor(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        last_task_id TEXT NOT NULL)""")
    db.execute("INSERT OR IGNORE INTO bounded_control_scan_cursor VALUES(1,'')")
    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_control_state_id ON tasks(state,task_id)")


def _contract(goal_id:str,target:dict,alternatives:list,fixtures:Path)->dict:
    if (not isinstance(goal_id,str) or not _ID.fullmatch(goal_id)
        or not isinstance(target,dict) or not 1<=len(target)<=16
        or not isinstance(alternatives,list) or len(alternatives)!=2):
        raise ValueError("INVALID_CONTROL_CONTRACT")
    if any(not isinstance(k,str)
           or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}",k)
           or not isinstance(v,str) or len(v)>256
           for k,v in target.items()):
        raise ValueError("INVALID_TARGET")
    # The reference oracle validates the exact canonical record independently.
    packed=[]
    types=set()
    paths=set()
    for spec in alternatives:
        validate_goal(spec)
        kind=spec["goal_type"]
        name=spec["input"]
        if kind in types or name in paths:
            raise ValueError("DUPLICATE_CONTROL_METHOD")
        types.add(kind)
        paths.add(name)
        if (not set(spec["desired"])<=set(target)
            or any(target[k]!=v for k,v in spec["desired"].items())
            or not spec["desired"]):
            raise ValueError("GOAL_POSTCONDITION_MISMATCH")
        raw=safe_fixture(fixtures,name)
        original=record_from_bytes(kind,raw)
        if (set(original)|set(spec["desired"])!=set(target)
            or any(k not in target for k in original)):
            raise ValueError("SOURCE_NOT_SAME_GOAL")
        # Only explicitly requested fields may conflict. A changed identity
        # field would make this a DIFFERENT owner goal, not a fallback.
        if any(k not in spec["desired"] and target[k]!=v
               for k,v in original.items()):
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        packed.append({"task_spec":spec,"input_sha256":hashlib.sha256(raw).hexdigest()})
    if types!={"json_keys","csv_columns"}:
        raise ValueError("UNREGISTERED_METHOD_PAIR")
    spec={"kind":"bounded_local_controller","schema_version":1,
          "goal_id":goal_id,"target":target,"alternatives":packed,
          "max_attempts":2,"allowed_effect":"LOCAL_CANDIDATE_ONLY"}
    if len(json.dumps(spec,ensure_ascii=False).encode("utf-8"))>16384:
        raise ValueError("CONTROL_CONTRACT_TOO_LARGE")
    return spec


def register_local_goal(db_path:Path,fixtures:Path,*,goal_id:str,target:dict,
                        alternatives:list[dict])->str:
    """One explicit, authorized registration. Never updates any grant."""
    spec=_contract(goal_id,target,alternatives,fixtures)
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if authority is None or not authority["write_allowed"]:
            raise ValueError("NO_CURRENT_LOCAL_GRANT")
        _ensure(db)
        tid=create_task(db,spec,commit=False)
        db.execute("UPDATE tasks SET state=? WHERE task_id=?",(_ACTIVE,tid))
        registered=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
        # Independently replayable, durable intake anchor. This detects
        # single-record corruption, not a privileged writer forging BOTH
        # the contract and its same-database receipt.
        canonical=json.dumps(spec,sort_keys=True,ensure_ascii=False,
                             separators=(",",":")).encode("utf-8")
        event(db,tid,"BOUNDED_CONTROLLER_REGISTERED",{
            "goal_id":goal_id,"methods":2,"max_attempts":2,
            "root_task_id":tid,"goal_rev":registered["goal_rev"],
            "grant_rev":registered["grant_rev"],
            "registered_created_at":registered["created_at"],
            "contract_sha256":hashlib.sha256(canonical).hexdigest(),
            "max_age_seconds":MAX_CONTROL_AGE_SECONDS,
            "business_outcome_verified":False,"owner_approval_inferred":False})
        db.commit()
        return tid
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _finish(db,root_id:str,state:str,reason:str,details:dict|None=None)->dict:
    db.execute("UPDATE tasks SET state=?,error_code=?,state_version=state_version+1 WHERE task_id=?",
               (state,reason,root_id))
    # A stopped root must not leave a dormant admitted child that can later
    # be claimed independently. Fence any outstanding local child in the
    # same authority transaction. A competing lease can no longer finalize.
    if state in (_STOP,_UNVERIFIABLE):
        active=db.execute("""SELECT task_id FROM tasks WHERE parent_task=?
                 AND state IN ('PENDING','RUNNING')""",(root_id,)).fetchall()
        for pending in active:
            db.execute("""UPDATE tasks SET state='BLOCKED',
                error_code='CONTROLLER_CLOSED',claim_token=NULL,
                lease_until=NULL,state_version=state_version+1
                WHERE task_id=?""",(pending["task_id"],))
            event(db,pending["task_id"],"BOUNDED_CONTROLLER_CHILD_FENCED",{
                "root_task_id":root_id,"reason":reason})
    event(db,root_id,"BOUNDED_CONTROLLER_DECIDED",{
        "state":state,"reason":reason,
        "business_outcome_verified":False,"authorizes_mutation":False,
        **(details or {})})
    return {"root_task_id":root_id,"status":state,"reason":reason,
            "business_outcome_verified":False}


def _admit(db,root,contract,ordinal:int,fixtures:Path)->dict:
    candidate=contract["alternatives"][ordinal]
    spec=candidate["task_spec"]
    original=safe_fixture(fixtures,spec["input"])
    if hashlib.sha256(original).hexdigest()!=candidate["input_sha256"]:
        return _finish(db,root["task_id"],_UNVERIFIABLE,"SOURCE_CHANGED")
    child=create_task(db,spec,parent=root["task_id"],commit=False)
    db.execute("""INSERT INTO bounded_goal_attempts(root_task_id,ordinal,child_task_id)
                  VALUES(?,?,?)""",(root["task_id"],ordinal,child))
    event(db,root["task_id"],"BOUNDED_CONTROLLER_ADMITTED",{
        "ordinal":ordinal,"child_task_id":child,
        "goal_rev":root["goal_rev"],"grant_rev":root["grant_rev"],
        "method":spec["goal_type"],"input_sha256":candidate["input_sha256"],
        "business_outcome_verified":False})
    return {"root_task_id":root["task_id"],"status":"ADMITTED_LOCAL_ATTEMPT",
            "ordinal":ordinal,"child_task_id":child,
            "business_outcome_verified":False}


def _observe(db,root,contract,attempt,db_path:Path,workspace:Path,fixtures:Path)->dict:
    ordinal=attempt["ordinal"]
    child=db.execute("SELECT * FROM tasks WHERE task_id=?",
                     (attempt["child_task_id"],)).fetchone()
    if (child is None or child["parent_task"]!=root["task_id"]
        or child["goal_rev"]!=root["goal_rev"]
        or child["grant_rev"]!=root["grant_rev"]):
        return _finish(db,root["task_id"],_UNVERIFIABLE,"ATTEMPT_PROVENANCE_BROKEN")
    bound=contract["alternatives"][ordinal]
    spec=bound["task_spec"]
    if json.loads(child["source_spec"])!=spec:
        return _finish(db,root["task_id"],_UNVERIFIABLE,"ATTEMPT_CHANGED")
    if child["state"] in ("PENDING","RUNNING"):
        return {"root_task_id":root["task_id"],"status":"AWAITING_CHILD",
                "ordinal":ordinal,"business_outcome_verified":False}
    raw=safe_fixture(fixtures,spec["input"])
    source_hash=hashlib.sha256(raw).hexdigest()
    if source_hash!=bound["input_sha256"]:
        return _finish(db,root["task_id"],_UNVERIFIABLE,"SOURCE_CHANGED")
    candidate=None
    if child["state"]=="NEEDS_REVIEW":
        independent=audit_goal(db_path,workspace,fixtures,child["task_id"])
        if independent["status"]!="CANDIDATE_MECHANICALLY_VALID":
            return _finish(db,root["task_id"],_UNVERIFIABLE,
                           "LOCAL_ARTIFACT_NOT_INDEPENDENTLY_VALID")
        artifact=workspace/"artifacts"/(child["task_id"]+".json")
        if artifact.is_symlink():
            return _finish(db,root["task_id"],_UNVERIFIABLE,"UNSAFE_ARTIFACT")
        checked_bytes=artifact.read_bytes()
        if hashlib.sha256(checked_bytes).hexdigest()!=child["artifact_hash"]:
            return _finish(db,root["task_id"],_UNVERIFIABLE,"ARTIFACT_CHANGED_AFTER_AUDIT")
        doc=json.loads(checked_bytes)
        candidate=doc["candidate_text"].encode("utf-8")
    elif child["state"]=="VERIFIED" and child["decision"]=="GOAL_ALREADY_SATISFIED":
        candidate=raw
    elif child["state"]!="UNKNOWN" or child["error_code"]!="NO_SAFE_GOAL_PLAN":
        return _finish(db,root["task_id"],_UNVERIFIABLE,"NON_ELIGIBLE_CHILD_STATE")
    verdict=assess_local_record(kind=spec["goal_type"],original=raw,
                                current_sha256=source_hash,
                                pinned_sha256=bound["input_sha256"],
                                target=contract["target"],candidate=candidate)
    if verdict["verdict"]=="LOCAL_CANDIDATE_TARGET_MET" and candidate is not None:
        return _finish(db,root["task_id"],_MET,"PINNED_LOCAL_POSTCONDITION",
                       {"ordinal":ordinal,"child_task_id":child["task_id"],
                        "candidate_sha256":verdict["candidate_sha256"]})
    if verdict["verdict"]=="PRESERVATION_CONFLICT":
        if ordinal==0:
            return _admit(db,root,contract,1,fixtures)
        return _finish(db,root["task_id"],_STOP,"EXHAUSTED_SAFE_ALTERNATIVES")
    return _finish(db,root["task_id"],_UNVERIFIABLE,
                   "INDEPENDENT_ORACLE_"+verdict["verdict"])


def advance_local_goals(db_path:Path,workspace:Path,fixtures:Path,
                        *,limit:int=4)->list[dict]:
    """Opt-in legacy local-goal policy on the SHARED admission/lease kernel."""
    if not 1<=limit<=8:
        raise ValueError("CONTROL_LIMIT")
    from .control_kernel import drive_active_controller

    def on_denied(db,root,reason):
        return _finish(db,root["task_id"],_STOP,reason)

    def transition(db,root):
        from .bounded_control_audit import verify_registered_control
        registered=verify_registered_control(db,root)
        if not registered["valid"]:
            return _finish(db,root["task_id"],_UNVERIFIABLE,
                           "REGISTRATION_PROOF_INVALID",
                           {"intake_reason":registered["reason"]})
        if (root["created_at"]>time.time()+300 or
            time.time()-root["created_at"]>MAX_CONTROL_AGE_SECONDS):
            return _finish(db,root["task_id"],_STOP,
                           "LOCAL_CONTROL_TIME_BUDGET_EXHAUSTED")
        contract=json.loads(root["source_spec"])
        attempts=db.execute("""SELECT ordinal,child_task_id
            FROM bounded_goal_attempts WHERE root_task_id=?
            ORDER BY ordinal""",(root["task_id"],)).fetchall()
        if not attempts:
            return _admit(db,root,contract,0,fixtures)
        if (len(attempts)>2 or
            [a["ordinal"] for a in attempts]!=list(range(len(attempts)))):
            return _finish(db,root["task_id"],_UNVERIFIABLE,
                           "BROKEN_ATTEMPT_LINEAGE")
        return _observe(db,root,contract,attempts[-1],
                        db_path,workspace,fixtures)

    return drive_active_controller(
        db_path,active_state=_ACTIVE,
        cursor_table="bounded_control_scan_cursor",limit=limit,
        setup=_ensure,step=transition,on_denied=on_denied)
