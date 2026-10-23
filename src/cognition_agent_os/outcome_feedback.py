"""Two-attempt, multi-capability LOCAL outcome feedback on the original ledger.

The verified objective is *independent local evidence*, not the user's real
business outcome. A separate owner/outcome acceptance gate remains required.
No model self-approval, arbitrary Python execution, external writes or grants.
Registered capabilities: goal_case (JSON/CSV), record_reconciliation (CSV).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

from .ledger import connect, create_task, event, current_guard
from .source import safe_fixture
from .goal_loop import validate_goal
from .reconciliation import validate_reconciliation, propose_reconciliation
from .goal_audit import audit_goal
from .reconciliation_oracle import audit_stored_report, sql_audit
from .bounded_outcome_oracle import record_from_bytes, assess_local_record

_ACTIVE = "FEEDBACK_ACTIVE"
_READY = "FEEDBACK_EVIDENCE_READY"
_STOP = "FEEDBACK_STOPPED"
_UNVERIFIABLE = "FEEDBACK_UNVERIFIABLE"
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_MAX_AGE = 86400


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _paths(spec: dict) -> tuple[str, ...]:
    if not isinstance(spec, dict):
        raise ValueError("INVALID_CAPABILITY")
    if spec.get("kind") == "goal_case":
        validate_goal(spec)
        return (spec["input"],)
    if spec.get("kind") == "record_reconciliation":
        validate_reconciliation(spec)
        # Semantic key manifests require independent owner review. Restrict
        # this slice to the same source-only mechanical inference contract.
        if "relationship_contract" in spec:
            raise ValueError("PINNED_RELATIONSHIP_NOT_ADMITTED")
        return (spec["reference"], spec["observed"])
    raise ValueError("UNREGISTERED_CAPABILITY")


def _pins(spec: dict, fixtures: Path) -> dict[str, str]:
    paths = _paths(spec)
    return {name: hashlib.sha256(safe_fixture(fixtures,name)).hexdigest()
            for name in paths}


def _ensure(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS evidence_feedback_attempts(
        root_task_id TEXT NOT NULL REFERENCES tasks(task_id),
        ordinal INTEGER NOT NULL CHECK(ordinal IN (0,1)),
        child_task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id),
        PRIMARY KEY(root_task_id,ordinal))""")
    db.execute("""CREATE TABLE IF NOT EXISTS evidence_feedback_cursor(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        last_task_id TEXT NOT NULL)""")
    db.execute("INSERT OR IGNORE INTO evidence_feedback_cursor VALUES(1,'')")


def register_evidence_goal(db_path: Path, fixtures: Path, *, goal_id: str,
                           objective: str, alternatives: list[dict]) -> str:
    """Explicit opt-in with two immutable source-pinned existing capabilities."""
    if (not isinstance(goal_id,str) or not _ID.fullmatch(goal_id)
        or not isinstance(objective,str) or not 1<=len(objective)<=256
        or not isinstance(alternatives,list) or len(alternatives)!=2):
        raise ValueError("INVALID_FEEDBACK_CONTRACT")
    if not db_path.is_file() or db_path.is_symlink():
        raise ValueError("LEDGER_MUST_EXIST")
    methods=[]
    for spec in alternatives:
        pins=_pins(spec,fixtures)
        methods.append({"task_spec":spec,"source_sha256":pins})
    if methods[0] == methods[1]:
        raise ValueError("DUPLICATE_METHOD")
    contract={"kind":"outcome_feedback_controller","version":1,
              "goal_id":goal_id,"objective":objective,
              "outcome_requirement":"INDEPENDENT_LOCAL_EVIDENCE",
              "alternatives":methods,"max_attempts":2,
              "allowed_effect":"LOCAL_EVIDENCE_ONLY"}
    if len(json.dumps(contract,ensure_ascii=False).encode())>16384:
        raise ValueError("FEEDBACK_CONTRACT_EXCEEDS_BOUND")
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if not authority or not authority["write_allowed"]:
            raise PermissionError("CURRENT_WRITE_GRANT_REQUIRED")
        _ensure(db)
        root_id=create_task(db,contract,commit=False)
        db.execute("UPDATE tasks SET state=? WHERE task_id=?",(_ACTIVE,root_id))
        root=db.execute("SELECT * FROM tasks WHERE task_id=?",(root_id,)).fetchone()
        event(db,root_id,"FEEDBACK_REGISTERED",{
            "root_task_id":root_id,"contract_sha256":_digest(contract),
            "created_at":root["created_at"],"goal_rev":root["goal_rev"],
            "grant_rev":root["grant_rev"],
            "business_outcome_verified":False})
        db.commit()
        return root_id
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _verify(db:sqlite3.Connection, root:sqlite3.Row) -> tuple[bool,str,dict | None,list]:
    """Replay registration + every admitted child against immutable receipts."""
    try:
        contract=json.loads(root["source_spec"])
        if (not isinstance(contract,dict)
            or set(contract)!={"kind","version","goal_id","objective",
                                "outcome_requirement","alternatives",
                                "max_attempts","allowed_effect"}
            or contract["kind"]!="outcome_feedback_controller"
            or type(contract["version"]) is not int or contract["version"]!=1
            or contract["outcome_requirement"]!="INDEPENDENT_LOCAL_EVIDENCE"
            or contract["allowed_effect"]!="LOCAL_EVIDENCE_ONLY"
            or type(contract["max_attempts"]) is not int or contract["max_attempts"]!=2
            or not isinstance(contract["goal_id"],str)
            or not _ID.fullmatch(contract["goal_id"])
            or not isinstance(contract["objective"],str)
            or not 1<=len(contract["objective"])<=256
            or not isinstance(contract["alternatives"],list)
            or len(contract["alternatives"])!=2
            or root["parent_task"] is not None
            or root["claim_token"] is not None):
            return False,"INVALID_FEEDBACK_CONTRACT",None,[]
        for m in contract["alternatives"]:
            if not isinstance(m,dict) or set(m)!={"task_spec","source_sha256"}:
                return False,"INVALID_FEEDBACK_METHOD",None,[]
            paths=_paths(m["task_spec"])
            if (not isinstance(m["source_sha256"],dict)
                or set(m["source_sha256"]) != set(paths)
                or any(not isinstance(v,str)
                       or not re.fullmatch(r"[0-9a-f]{64}",v)
                       for v in m["source_sha256"].values())):
                return False,"INVALID_SOURCE_PINS",None,[]
        receipts=db.execute("""SELECT details FROM events
            WHERE task_id=? AND kind='FEEDBACK_REGISTERED'""",
            (root["task_id"],)).fetchall()
        expected={"root_task_id":root["task_id"],
                  "contract_sha256":_digest(contract),
                  "created_at":root["created_at"],"goal_rev":root["goal_rev"],
                  "grant_rev":root["grant_rev"],"business_outcome_verified":False}
        if len(receipts)!=1 or json.loads(receipts[0]["details"])!=expected:
            return False,"REGISTRATION_RECEIPT_INVALID",None,[]
        attempts=db.execute("""SELECT ordinal,child_task_id
            FROM evidence_feedback_attempts WHERE root_task_id=?
            ORDER BY ordinal""",(root["task_id"],)).fetchall()
        children=db.execute("SELECT * FROM tasks WHERE parent_task=?",
                            (root["task_id"],)).fetchall()
        events=db.execute("""SELECT details FROM events
            WHERE task_id=? AND kind='FEEDBACK_ADMITTED'
            ORDER BY event_id""",(root["task_id"],)).fetchall()
        count=len(attempts)
        if (count>2 or len(children)!=count or len(events)!=count
            or [a["ordinal"] for a in attempts]!=list(range(count))):
            return False,"FEEDBACK_LINEAGE_CARDINALITY",None,[]
        by_id={r["task_id"]:r for r in children}
        if len(by_id)!=count:
            return False,"FEEDBACK_LINEAGE_CARDINALITY",None,[]
        for n,attempt in enumerate(attempts):
            child=by_id.get(attempt["child_task_id"])
            method=contract["alternatives"][n]
            admission=json.loads(events[n]["details"])
            if (child is None or child["parent_task"]!=root["task_id"]
                or child["goal_rev"]!=root["goal_rev"]
                or child["grant_rev"]!=root["grant_rev"]
                or json.loads(child["source_spec"])!=method["task_spec"]
                or admission!={"ordinal":n,
                               "child_task_id":attempt["child_task_id"],
                               "method_sha256":_digest(method),
                               "business_outcome_verified":False}):
                return False,"FEEDBACK_LINEAGE_MISMATCH",None,[]
        return True,"REGISTERED",contract,attempts
    except (sqlite3.Error,ValueError,TypeError,KeyError,IndexError,UnicodeError):
        return False,"FEEDBACK_RECHECK_UNAVAILABLE",None,[]


def _admit(db:sqlite3.Connection, root:sqlite3.Row,
           contract:dict, ordinal:int,fixtures:Path) -> dict:
    method=contract["alternatives"][ordinal]
    try:
        pinned_now=_pins(method["task_spec"],fixtures)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        return _finish(db,root,_UNVERIFIABLE,"SOURCE_UNAVAILABLE_AT_ADMISSION")
    if pinned_now!=method["source_sha256"]:
        return _finish(db,root,_UNVERIFIABLE,"SOURCE_PIN_DRIFT")
    child_id=create_task(db,method["task_spec"],parent=root["task_id"],commit=False)
    db.execute("""INSERT INTO evidence_feedback_attempts(
        root_task_id,ordinal,child_task_id) VALUES(?,?,?)""",
        (root["task_id"],ordinal,child_id))
    event(db,root["task_id"],"FEEDBACK_ADMITTED",{
        "ordinal":ordinal,"child_task_id":child_id,
        "method_sha256":_digest(method),"business_outcome_verified":False})
    return {"root_task_id":root["task_id"],"status":"FEEDBACK_ADMITTED",
            "child_task_id":child_id,"ordinal":ordinal,
            "business_outcome_verified":False}


def _finish(db, root, state, reason, *, child_id=None) -> dict:
    db.execute("""UPDATE tasks SET state=?,error_code=?,
        state_version=state_version+1 WHERE task_id=?""",
        (state,reason,root["task_id"]))
    if state in (_STOP,_UNVERIFIABLE):
        for child in db.execute("""SELECT task_id FROM tasks
                 WHERE parent_task=? AND state IN ('PENDING','RUNNING')""",
                 (root["task_id"],)).fetchall():
            db.execute("""UPDATE tasks SET state='BLOCKED',
                error_code='FEEDBACK_CONTROLLER_CLOSED',
                claim_token=NULL,lease_until=NULL,
                state_version=state_version+1 WHERE task_id=?""",
                (child["task_id"],))
            event(db,child["task_id"],"FEEDBACK_CHILD_FENCED",
                  {"root_task_id":root["task_id"]})
    event(db,root["task_id"],"FEEDBACK_OBSERVED",{
        "state":state,"reason":reason,"child_task_id":child_id,
        "business_outcome_verified":False,"authorizes_external_effect":False})
    return {"root_task_id":root["task_id"],"status":state,
            "reason":reason,"business_outcome_verified":False}


def _outcome(child,method,db_path:Path,workspace:Path,fixtures:Path) -> str:
    """Return SATISFIED / UNSATISFIED / WAITING / INCONCLUSIVE.

    Audit failures are NOT automatically treated as negative outcome: missing,
    changed or forged evidence is an inconclusive blocker, not permission to
    retry a second capability.
    """
    spec=method["task_spec"]
    if _pins(spec,fixtures)!=method["source_sha256"]:
        return "INCONCLUSIVE"
    state=child["state"]
    if state in ("PENDING","RUNNING"):
        return "WAITING"
    kind=spec["kind"]
    if state=="NEEDS_REVIEW":
        if kind=="goal_case":
            r=audit_goal(db_path,workspace,fixtures,child["task_id"])
            return ("SATISFIED" if r["status"]=="CANDIDATE_MECHANICALLY_VALID"
                    else "INCONCLUSIVE")
        if kind=="record_reconciliation":
            r=audit_stored_report(db_path,workspace,fixtures,child["task_id"])
            return ("SATISFIED" if r["status"]=="REPORT_MECHANICALLY_VERIFIED"
                    else "INCONCLUSIVE")
    if state=="VERIFIED":
        from .conformance import _verify_consistent
        return ("SATISFIED" if _verify_consistent(child,fixtures)=="MECHANICALLY_VALID"
                else "INCONCLUSIVE")
    if state=="UNKNOWN" and kind=="goal_case" and child["error_code"]=="NO_SAFE_GOAL_PLAN":
        raw=safe_fixture(fixtures,spec["input"])
        old=record_from_bytes(spec["goal_type"],raw)
        merged={**old,**spec["desired"]}
        result=assess_local_record(
            kind=spec["goal_type"],original=raw,
            current_sha256=method["source_sha256"][spec["input"]],
            pinned_sha256=method["source_sha256"][spec["input"]],
            target=merged,candidate=None)
        return ("UNSATISFIED" if result["verdict"]=="PRESERVATION_CONFLICT"
                else "INCONCLUSIVE")
    if (state=="UNKNOWN" and kind=="record_reconciliation"
        and child["error_code"]=="JOIN_KEY_AMBIGUOUS"):
        left=safe_fixture(fixtures,spec["reference"])
        right=safe_fixture(fixtures,spec["observed"])
        proposed=propose_reconciliation(spec,left,right)
        verified=sql_audit(spec,left,right,proposed)
        return ("UNSATISFIED" if proposed["status"]=="INSUFFICIENT_KEY_EVIDENCE"
                and verified["agreement"] else "INCONCLUSIVE")
    return "INCONCLUSIVE"


def verify_feedback_root(db:sqlite3.Connection,root:sqlite3.Row,
                         db_path:Path,workspace:Path,fixtures:Path) -> dict:
    valid,reason,contract,attempts=_verify(db,root)
    if not valid:
        return {"valid":False,"reason":reason}
    if root["state"]==_READY:
        if not attempts:
            return {"valid":False,"reason":"NO_ACCEPTED_ATTEMPT"}
        last=attempts[-1]
        child=db.execute("SELECT * FROM tasks WHERE task_id=?",
                         (last["child_task_id"],)).fetchone()
        receipts=db.execute("""SELECT details FROM events
            WHERE task_id=? AND kind='FEEDBACK_OBSERVED' ORDER BY event_id""",
            (root["task_id"],)).fetchall()
        accepted={"state":_READY,"reason":"INDEPENDENT_LOCAL_EVIDENCE",
                  "child_task_id":last["child_task_id"],
                  "business_outcome_verified":False,"authorizes_external_effect":False}
        if not receipts or json.loads(receipts[-1]["details"])!=accepted:
            return {"valid":False,"reason":"ACCEPTANCE_RECEIPT_INVALID"}
        try:
            if _outcome(child,contract["alternatives"][last["ordinal"]],
                        db_path,workspace,fixtures)!="SATISFIED":
                return {"valid":False,"reason":"ACCEPTED_OUTCOME_NO_LONGER_VERIFIABLE"}
        except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,UnicodeError):
            return {"valid":False,"reason":"OUTCOME_RECHECK_UNAVAILABLE"}
    return {"valid":True,"reason":"INDEPENDENT_LOCAL_MECHANICAL_EVIDENCE"}


def advance_evidence_goals(db_path:Path,workspace:Path,fixtures:Path,
                           *,limit:int=4)->list[dict]:
    """Multi-domain adapter: shared scan/grant/transaction, typed evidence."""
    if not 1<=limit<=8:
        raise ValueError("INVALID_FEEDBACK_LIMIT")
    from .control_kernel import drive_active_controller

    def on_denied(db,root,reason):
        return _finish(db,root,_STOP,reason)

    def transition(db,root):
        valid,reason,contract,attempts=_verify(db,root)
        if not valid:
            return _finish(db,root,_UNVERIFIABLE,reason)
        if (root["created_at"]>time.time()+300 or
            time.time()-root["created_at"]>_MAX_AGE):
            return _finish(db,root,_STOP,"TIME_BUDGET_EXHAUSTED")
        if not attempts:
            return _admit(db,root,contract,0,fixtures)
        last=attempts[-1]
        child=db.execute("SELECT * FROM tasks WHERE task_id=?",
                         (last["child_task_id"],)).fetchone()
        try:
            verdict=_outcome(child,contract["alternatives"][last["ordinal"]],
                             db_path,workspace,fixtures)
        except (OSError,ValueError,TypeError,KeyError,
                sqlite3.Error,UnicodeError):
            verdict="INCONCLUSIVE"
        if verdict=="WAITING":
            return {"root_task_id":root["task_id"],"status":"AWAITING_CHILD"}
        if verdict=="SATISFIED":
            return _finish(db,root,_READY,"INDEPENDENT_LOCAL_EVIDENCE",
                           child_id=child["task_id"])
        if verdict=="UNSATISFIED" and last["ordinal"]==0:
            return _admit(db,root,contract,1,fixtures)
        if verdict=="UNSATISFIED":
            return _finish(db,root,_STOP,"EXHAUSTED_SAFE_ALTERNATIVES",
                           child_id=child["task_id"])
        return _finish(db,root,_UNVERIFIABLE,
                       "INDEPENDENT_OUTCOME_INCONCLUSIVE",
                       child_id=child["task_id"])

    return drive_active_controller(
        db_path,active_state=_ACTIVE,
        cursor_table="evidence_feedback_cursor",limit=limit,
        setup=_ensure,step=transition,on_denied=on_denied)
