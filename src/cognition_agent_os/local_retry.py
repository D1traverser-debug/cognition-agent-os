"""One bounded, durable follow-up for failed local mechanical evidence.

Never assumes semantic success, retries remote effects, or creates new authority.
A retry is a same-capability re-execution, NOT general-purpose replanning.
"""
from __future__ import annotations
import json
from pathlib import Path

from .ledger import connect, create_task, event
from .goal_audit import audit_goal
from .reconciliation_oracle import audit_stored_report


def schedule_failed_local_evidence(db_path: Path, workspace: Path, fixtures: Path,
                                   *, limit: int = 4) -> list[dict]:
    if not 1 <= limit <= 8:
        raise ValueError("Invalid retry budget")
    db=connect(db_path)
    scheduled=[]
    try:
        rows=db.execute("""SELECT child.*,parent.source_spec AS root_spec,
                                  parent.state AS root_state,
                                  parent.parent_task AS root_parent
                     FROM tasks child JOIN tasks parent ON child.parent_task=parent.task_id
                     WHERE child.state='NEEDS_REVIEW'
                     ORDER BY child.created_at,child.task_id LIMIT 64""").fetchall()
        for row in rows:
            if len(scheduled)>=limit:break
            if row["root_parent"] is not None or row["root_state"]!="DECOMPOSED":continue
            try:
                root=json.loads(row["root_spec"])
                spec=json.loads(row["source_spec"])
            except (ValueError,TypeError):continue
            if root.get("kind")!="goal_intent":continue
            # A retry root must not retry again; linkage lives in events.
            if db.execute("SELECT 1 FROM events WHERE task_id=? AND kind IN ('RETRY_ROOT_FROM_FAILED','BOUNDED_LOCAL_RETRY') LIMIT 1",
                          (row["parent_task"],)).fetchone():
                continue
            kind=spec.get("kind")
            if kind=="goal_case":
                verdict=audit_goal(db_path,workspace,fixtures,row["task_id"])["status"]
                valid=verdict=="CANDIDATE_MECHANICALLY_VALID"
            elif kind=="record_reconciliation":
                verdict=audit_stored_report(db_path,workspace,fixtures,row["task_id"])["status"]
                valid=verdict=="REPORT_MECHANICALLY_VERIFIED"
            else:continue
            if valid:continue
            db.execute("BEGIN IMMEDIATE")
            try:
                authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
                parent=db.execute("SELECT * FROM tasks WHERE task_id=?",(row["parent_task"],)).fetchone()
                current=db.execute("SELECT * FROM tasks WHERE task_id=?",(row["task_id"],)).fetchone()
                siblings=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",(row["parent_task"],)).fetchone()[0]
                if (not authority or not authority["write_allowed"] or not parent or not current
                    or parent["state"]!="DECOMPOSED" or current["state"]!="NEEDS_REVIEW"
                    or parent["goal_rev"]!=authority["goal_rev"]
                    or parent["grant_rev"]!=authority["grant_rev"]
                    or current["goal_rev"]!=authority["goal_rev"]
                    or current["grant_rev"]!=authority["grant_rev"]
                    or siblings!=1 or db.execute(
                        "SELECT 1 FROM events WHERE task_id=? AND kind='BOUNDED_LOCAL_RETRY' LIMIT 1",
                        (row["parent_task"],)).fetchone()):
                    db.commit()
                    continue
                # Keep exactly one child per intent root. The next Host tick
                # decomposes a new authorized root using the registered planner.
                new_id=create_task(db,root,commit=False)
                event(db,new_id,"RETRY_ROOT_FROM_FAILED",{
                    "original_root":row["parent_task"],
                    "failed_task_id":row["task_id"],"max_attempts":1})
                event(db,row["parent_task"],"BOUNDED_LOCAL_RETRY",{
                    "failed_task_id":row["task_id"],"retry_root_id":new_id,
                    "verdict":verdict,"max_retry_roots":1,
                    "semantic_outcome_verified":False})
                db.commit()
                scheduled.append({"failed_task_id":row["task_id"],"retry_root_id":new_id,
                                  "reason":verdict,"business_outcome_verified":False})
            except BaseException:
                db.rollback()
                raise
        return scheduled
    finally:
        db.close()
