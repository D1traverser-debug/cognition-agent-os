"""Evidence-gated local task edges inside the ONE authoritative SQLite ledger.

This is NOT a second planner/controller, approval source or external action.
A successor is a pre-registered, immutable local proposal. Independent source
readback is required both before its release and immediately before execution.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

from .ledger import connect, event, require_initialized_ledger

_TABLE = """
CREATE TABLE IF NOT EXISTS task_dependencies(
  task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
  predecessor_task TEXT NOT NULL REFERENCES tasks(task_id),
  evidence_kind TEXT NOT NULL,
  released_at REAL
)
"""
_ALLOWED_PREDECESSORS = {
    "goal_case": ("goal_case", "CANDIDATE_MECHANICALLY_VALID"),
    "record_reconciliation": ("record_reconciliation", "REPORT_MECHANICALLY_VERIFIED"),
    "investigate_goal": ("investigate_goal", "SOURCE_GROUNDED_UNREVIEWED"),
}
_ALLOWED_FOLLOWERS = {"goal_case", "record_reconciliation"}


def _table_exists(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                      "AND name='task_dependencies'").fetchone() is not None


def register_local_dependency(db_path: Path, predecessor: str, successor: str) -> None:
    """Bind two existing local tasks; never mint authority or execute either."""
    require_initialized_ledger(db_path)
    if (not isinstance(predecessor,str) or not isinstance(successor,str)
        or predecessor==successor or len(predecessor)!=32 or len(successor)!=32):
        raise ValueError("INVALID_DEPENDENCY_IDS")
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            rows=db.execute(
                "SELECT * FROM tasks WHERE task_id IN (?,?)",
                (predecessor,successor)).fetchall()
            by_id={r["task_id"]:r for r in rows}
            if len(by_id)!=2:
                raise ValueError("UNKNOWN_TASK_EDGE")
            first,second=by_id[predecessor],by_id[successor]
            source=json.loads(first["source_spec"])
            target=json.loads(second["source_spec"])
            authority=db.execute(
                "SELECT * FROM authority WHERE singleton=1").fetchone()
            if (not isinstance(source,dict) or not isinstance(target,dict)
                or source.get("kind") not in _ALLOWED_PREDECESSORS
                or target.get("kind") not in _ALLOWED_FOLLOWERS
                or first["state"]!="PENDING" or second["state"]!="PENDING"
                or first["created_at"]>=second["created_at"]
                or first["goal_rev"]!=second["goal_rev"]
                or first["grant_rev"]!=second["grant_rev"]
                or authority is None or authority["write_allowed"]!=1
                or first["goal_rev"]!=authority["goal_rev"]
                or first["grant_rev"]!=authority["grant_rev"]
                or first["parent_task"]!=second["parent_task"]):
                raise ValueError("UNAUTHORIZED_OR_UNSUPPORTED_EDGE")
            from .goal_loop import validate_goal
            from .investigation import validate_investigation
            from .reconciliation import validate_reconciliation
            validators={"goal_case":validate_goal,
                "investigate_goal":validate_investigation,
                "record_reconciliation":validate_reconciliation}
            validators[source["kind"]](source)
            validators[target["kind"]](target)
            db.execute(_TABLE)
            if db.execute(
                "SELECT 1 FROM task_dependencies WHERE task_id IN (?,?)",
                (predecessor,successor)).fetchone():
                raise ValueError("DUPLICATE_OR_CYCLIC_EDGE")
            db.execute(
                "INSERT INTO task_dependencies(task_id,predecessor_task,evidence_kind)"
                " VALUES(?,?,?)",(successor,predecessor,source["kind"]))
            event(db,successor,"LOCAL_DEPENDENCY_REGISTERED",{
                "predecessor_task":predecessor,
                "evidence_kind":source["kind"],
                "owner_outcome_verified":False})
            db.commit()
        except BaseException:
            db.rollback()
            raise


def _independent_proof(db_path:Path, workspace:Path, fixtures:Path,
                       predecessor:str, kind:str) -> bool:
    try:
        if kind=="goal_case":
            from .goal_audit import audit_goal
            result=audit_goal(db_path,workspace,fixtures,predecessor)
        elif kind=="investigate_goal":
            from .investigation import audit_investigation
            result=audit_investigation(db_path,workspace,fixtures,predecessor)
        elif kind=="record_reconciliation":
            from .reconciliation_oracle import audit_stored_report
            result=audit_stored_report(db_path,workspace,fixtures,predecessor)
        else:
            return False
        return result.get("status")==_ALLOWED_PREDECESSORS[kind][1]
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error):
        return False


def dependency_admitted(db:sqlite3.Connection,db_path:Path,
                        task:dict,workspace:Path,fixtures:Path) -> tuple[bool,str|None]:
    """Recheck real grant + independent proof before local successor dispatch."""
    if not _table_exists(db):
        return True,None
    row=db.execute(
        "SELECT predecessor_task,evidence_kind,released_at "
        "FROM task_dependencies WHERE task_id=?",(task["task_id"],)).fetchone()
    if row is None:
        return True,None
    from .ledger import current_guard
    allowed, reason=current_guard(db,task,needs_write=True)
    if not allowed:
        return False,reason
    if row["released_at"] is None:
        return False,"PREDECESSOR_NOT_RELEASED"
    if not _independent_proof(
            db_path,workspace,fixtures,row["predecessor_task"],row["evidence_kind"]):
        return False,"PREDECESSOR_EVIDENCE_CHANGED"
    return True,None


def advance_pending_local_dependencies(db_path:Path,workspace:Path,
                                       fixtures:Path,*,limit:int=8)->list[dict]:
    """Release only a mechanically supported bounded local successor.

    Called by the existing Host before draining work. Failed evidence never
    authorizes an alternative effect. The worker independently rechecks it.
    """
    if not 1<=limit<=16:
        raise ValueError("INVALID_DEPENDENCY_LIMIT")
    require_initialized_ledger(db_path)
    with closing(connect(db_path)) as db:
        if not _table_exists(db):
            return []
        pending=db.execute(
            "SELECT d.task_id FROM task_dependencies d "
            "JOIN tasks t ON t.task_id=d.task_id "
            "WHERE d.released_at IS NULL AND t.state='PENDING' "
            "ORDER BY d.rowid LIMIT ?",(limit,)).fetchall()
    observations=[]
    for ref in pending:
        successor=ref["task_id"]
        with closing(connect(db_path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                edge=db.execute(
                    "SELECT * FROM task_dependencies WHERE task_id=?",
                    (successor,)).fetchone()
                if edge is None or edge["released_at"] is not None:
                    db.commit()
                    continue
                before=db.execute(
                    "SELECT * FROM tasks WHERE task_id=?",
                    (edge["predecessor_task"],)).fetchone()
                after=db.execute(
                    "SELECT * FROM tasks WHERE task_id=?",
                    (successor,)).fetchone()
                auth=db.execute(
                    "SELECT * FROM authority WHERE singleton=1").fetchone()
                if before is None or after is None or auth is None:
                    db.commit()
                    observations.append({"task_id":successor,
                                         "status":"DEPENDENCY_UNVERIFIABLE"})
                    continue
                current=(auth["write_allowed"]==1
                         and before["goal_rev"]==after["goal_rev"]==auth["goal_rev"]
                         and before["grant_rev"]==after["grant_rev"]==auth["grant_rev"])
                if not current or after["state"]!="PENDING":
                    db.commit()
                    observations.append({"task_id":successor,
                                         "status":"DEPENDENCY_NOT_AUTHORIZED"})
                    continue
                def fail_to_replan(reason):
                    # Keep the original task, grant, and unexecuted scope;
                    # the successor cannot silently disappear in PENDING.
                    db.execute(
                        "UPDATE tasks SET state='NEEDS_REPLAN',"
                        "error_code=?,state_version=state_version+1 "
                        "WHERE task_id=? AND state='PENDING'",
                        (reason,successor))
                    event(db,successor,"LOCAL_DEPENDENCY_REPLAN_REQUIRED",{
                        "predecessor_task":before["task_id"],
                        "reason":reason,"owner_outcome_verified":False})
                    db.commit()
                    return {"task_id":successor,"status":"DEPENDENCY_REPLAN_REQUIRED",
                            "reason":reason}
                if before["state"] in ("UNKNOWN","BLOCKED","NEEDS_REPLAN"):
                    observations.append(fail_to_replan("PREDECESSOR_NOT_VERIFIED"))
                    continue
                if before["state"] not in ("NEEDS_REVIEW","VERIFIED"):
                    db.commit()
                    observations.append({"task_id":successor,
                                         "status":"AWAITING_INDEPENDENT_EVIDENCE"})
                    continue
                if not _independent_proof(db_path,workspace,fixtures,
                                          before["task_id"],edge["evidence_kind"]):
                    observations.append(fail_to_replan(
                        "PREDECESSOR_EVIDENCE_UNVERIFIABLE"))
                    continue
                db.execute(
                    "UPDATE task_dependencies SET released_at=? "
                    "WHERE task_id=? AND released_at IS NULL",
                    (time.time(),successor))
                event(db,successor,"LOCAL_DEPENDENCY_RELEASED",{
                    "predecessor_task":before["task_id"],
                    "mechanical_evidence_only":True,
                    "owner_outcome_verified":False})
                db.commit()
                observations.append({"task_id":successor,
                                     "status":"DEPENDENCY_RELEASED_LOCAL_ONLY"})
            except BaseException:
                db.rollback()
                raise
    return observations
