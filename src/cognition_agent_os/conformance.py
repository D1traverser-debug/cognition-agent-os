"""P10: self-observing mechanical conformance gate for the ONE task ledger.

This module independently re-opens recorded evidence; it does not trust
task.state, developer docs, CI badges or a proposed planner verdict as proof.
On a live host its bounded sweep *enforces* fail-closed quarantine inside
the existing SQLite authority. The read-only inspection does not mutate DB.
It is NOT a semantic oracle, an OS-scheduler proof or release approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from .source import safe_fixture
from .goal_audit import audit_goal, _constraints
from .reconciliation_oracle import audit_stored_report
from .intent_runtime import audit_intent_plan
from .runner import verify_artifact
from .ledger import event, connect

TASK_ID=re.compile(r"[0-9a-f]{32}\Z")
EVIDENCED_STATES=("NEEDS_REVIEW","DECOMPOSED","SANDBOX_VERIFIED","VERIFIED")
MAX_SCAN=512
MAX_DEPENDENCIES=256


def _blocked(code: str, **kw) -> dict:
    return {"status":code,"mechanical_conformance":False,
            "external_semantic_evidence":"NOT_OBSERVED",
            "unattended_windows_host_evidence":"NOT_OBSERVED",
            "production_mutation_authorized":False,**kw}


def _immutable_bytes(path: Path, maximum: int=150_000) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum:
        raise ValueError("Missing, unsafe, or excessive evidence")
    raw=path.read_bytes()
    if len(raw)>maximum:raise ValueError("Evidence size changed")
    return raw


def _verify_staged(db, row: sqlite3.Row, workspace: Path, fixtures: Path) -> str:
    task_id=row["task_id"]
    if not TASK_ID.fullmatch(task_id):
        return "INVALID_TASK_ID"
    try:
        spec=json.loads(row["source_spec"])
        if not isinstance(spec,dict) or spec.get("kind")!="goal_case":
            return "INVALID_STAGED_SOURCE_SPEC"
        if workspace.is_symlink() or (workspace/"artifacts").is_symlink() or (workspace/"sandbox").is_symlink():
            return "UNSAFE_WORKSPACE"
        raw=_immutable_bytes(workspace/"artifacts"/(task_id+".json"))
        if not isinstance(row["artifact_hash"],str) or hashlib.sha256(raw).hexdigest()!=row["artifact_hash"]:
            return "STAGED_ARTIFACT_HASH_MISMATCH"
        obj=json.loads(raw)
        if (not isinstance(obj,dict) or obj.get("task_id")!=task_id
            or obj.get("goal_spec")!=spec or obj.get("goal_rev")!=row["goal_rev"]
            or obj.get("status")!="PROPOSAL_NOT_APPROVED"
            or not isinstance(obj.get("candidate_text"),str)):
            return "STAGED_ARTIFACT_IDENTITY_MISMATCH"
        candidate=obj["candidate_text"].encode("utf-8")
        if (len(candidate)>131072 or
            hashlib.sha256(candidate).hexdigest()!=obj.get("candidate_sha256")):
            return "CANDIDATE_HASH_MISMATCH"
        staged=_immutable_bytes(workspace/"sandbox"/(task_id+".candidate"),131072)
        if staged!=candidate:
            return "STAGED_EFFECT_BYTES_MISMATCH"
        src=safe_fixture(fixtures,spec["input"])
        if hashlib.sha256(src).hexdigest()!=obj.get("source_sha256"):
            return "SOURCE_CHANGED_SINCE_EFFECT"
        # Distinct constraint implementation from the candidate builder.
        from .goal_audit import _parse_json, _parse_csv
        if spec["goal_type"]=="json_keys":
            _parse_json(src)
        elif spec["goal_type"]=="csv_columns":
            _parse_csv(src)
        else:
            return "UNSUPPORTED_STAGED_GOAL"
        if not _constraints(spec,src,candidate):
            return "STAGED_CONSTRAINTS_FAILED"
        receipts=db.execute("""SELECT details FROM events WHERE task_id=?
              AND kind='SANDBOX_EFFECT_VERIFIED'""",(task_id,)).fetchall()
        if len(receipts)!=1:
            return "MISSING_OR_REPEATED_EFFECT_RECEIPT"
        receipt=json.loads(receipts[0][0])
        if (not isinstance(receipt,dict) or
            receipt.get("scope")!="isolated_workspace_only" or
            receipt.get("effect_sha256")!=hashlib.sha256(staged).hexdigest()):
            return "FALSE_EFFECT_RECEIPT"
        return "MECHANICALLY_VALID"
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,sqlite3.Error):
        return "STAGED_EVIDENCE_UNAVAILABLE"


def _verify_consistent(row: sqlite3.Row, fixtures: Path) -> str:
    try:
        spec=json.loads(row["source_spec"])
        if not isinstance(spec,dict):return "INVALID_SUCCESS_SPEC"
        if row["decision"]=="GOAL_ALREADY_SATISFIED" and spec.get("kind")=="goal_case":
            from .goal_loop import validate_goal, plan_goal
            validate_goal(spec)
            result=plan_goal(spec,safe_fixture(fixtures,spec["input"]))
            return ("MECHANICALLY_VALID" if result["selection"] and
                    result["selection"]["action"]=="NO_OP" else
                    "NO_LONGER_SATISFIES_GOAL")
        if (row["decision"]=="RECORD_SETS_CONSISTENT"
            and spec.get("kind")=="record_reconciliation"):
            from .reconciliation import validate_reconciliation, propose_reconciliation
            from .semantic_contract import load_pinned_relationship
            from .reconciliation_oracle import sql_audit
            validate_reconciliation(spec)
            left=safe_fixture(fixtures,spec["reference"])
            right=safe_fixture(fixtures,spec["observed"])
            pinned=load_pinned_relationship(spec,fixtures)
            candidate=propose_reconciliation(spec,left,right,pinned=pinned)
            valid=sql_audit(spec,left,right,candidate,pinned=pinned)["agreement"]
            return ("MECHANICALLY_VALID" if valid and
                    candidate["status"]=="CONSISTENT" else
                    "NO_LONGER_CONSISTENT")
        # Historical fixture/source diff VERIFIED requires a distinct origin
        # proof and is not automatically upgraded based on its state label.
        return "NO_INDEPENDENT_OUTCOME_RECHECK"
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):
        return "SUCCESS_EVIDENCE_UNAVAILABLE"


def _check_one(db, row: sqlite3.Row, db_path: Path,
               workspace: Path, fixtures: Path) -> dict:
    tid=row["task_id"]
    try:
        spec=json.loads(row["source_spec"])
        kind=spec.get("kind") if isinstance(spec,dict) else None
        state=row["state"]
        if state=="SANDBOX_VERIFIED":
            proof=_verify_staged(db,row,workspace,fixtures)
        elif state=="DECOMPOSED":
            result=audit_intent_plan(db_path,tid)
            proof=("MECHANICALLY_VALID" if result["status"]=="PLAN_MECHANICALLY_VALID"
                   else result.get("reason","PLAN_AUDIT_FAILED"))
        elif state=="NEEDS_REVIEW":
            if kind=="goal_case":
                r=audit_goal(db_path,workspace,fixtures,tid)
                proof=("MECHANICALLY_VALID" if r["mechanical_audit"]
                       else r["status"])
            elif kind=="record_reconciliation":
                r=audit_stored_report(db_path,workspace,fixtures,tid)
                proof=("MECHANICALLY_VALID" if r["status"]=="REPORT_MECHANICALLY_VERIFIED"
                       else r.get("reason","REPORT_AUDIT_FAILED"))
            elif kind in ("fixture","github"):
                proof=("MECHANICALLY_VALID" if verify_artifact(workspace,dict(row))
                       else "PROPOSAL_ARTIFACT_INVALID")
            else:
                proof="UNREGISTERED_REVIEW_FAMILY"
        elif state=="VERIFIED":
            proof=_verify_consistent(row,fixtures)
        else:
            proof="UNSUPPORTED_EVIDENCE_STATE"
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error):
        proof="EVIDENCE_RECHECK_UNAVAILABLE"
    unproven={"NO_INDEPENDENT_OUTCOME_RECHECK","SUCCESS_EVIDENCE_UNAVAILABLE",
              "EVIDENCE_RECHECK_UNAVAILABLE"}
    return {"task_id":tid,"state_at_observation":row["state"],
            "proof":proof,"mechanical_conformance":proof=="MECHANICALLY_VALID",
            "disposition":("PASS" if proof=="MECHANICALLY_VALID" else
                           "INSUFFICIENT_EVIDENCE" if proof in unproven else
                           "CONFIRMED_INCONSISTENCY")}


def _descendants(db, task_id: str) -> list[str]:
    """Bounded dependent-task transitive closure; reject oversized fanout."""
    seen={task_id}
    pending=[task_id]
    others=[]
    while pending:
        ancestor=pending.pop(0)
        rows=db.execute("SELECT task_id FROM tasks WHERE parent_task=? ORDER BY task_id",
                        (ancestor,)).fetchall()
        for row in rows:
            child=row[0]
            if child in seen:raise ValueError("Cyclic task ancestry")
            seen.add(child)
            others.append(child)
            if len(others)>MAX_DEPENDENCIES:
                raise ValueError("Too many dependent tasks")
            pending.append(child)
    return others


def _quarantine(db, row: sqlite3.Row, reason: str) -> list[str]:
    """No effect on original source; revoke only *derived state claims*."""
    tid=row["task_id"]
    descendants=_descendants(db,tid)
    for dependent_id in descendants:
        dep=db.execute("SELECT state FROM tasks WHERE task_id=?",(dependent_id,)).fetchone()
        if dep and dep[0] not in ("UNKNOWN","BLOCKED"):
            state="UNKNOWN" if dep[0] in ("VERIFIED","SANDBOX_VERIFIED","NEEDS_REVIEW") else "BLOCKED"
            db.execute("""UPDATE tasks SET state=?,error_code=?,
                         lease_until=NULL,claim_token=NULL,
                         state_version=state_version+1 WHERE task_id=?""",
                       (state,"UPSTREAM_CONFORMANCE_VIOLATION",dependent_id))
            event(db,dependent_id,"CONFORMANCE_DEPENDENCY_BLOCKED",{"root":tid,"cause":reason})
    db.execute("""UPDATE tasks SET state='UNKNOWN',error_code=?,
                 lease_until=NULL,claim_token=NULL,state_version=state_version+1
                 WHERE task_id=? AND state=?""",
               ("CONFORMANCE_"+reason,tid,row["state"]))
    event(db,tid,"CONFORMANCE_VIOLATION",{
        "observation":reason,
        "dependent_tasks_quarantined":descendants,
        "repair_applied":"REVOKE_FALSE_STATE_CLAIM",
        "root_cause_proven":False,
        "external_semantic_outcome_proven":False})
    return descendants


def inspect_conformance(db_path: Path, workspace: Path, fixtures: Path,
                        *, enforce: bool=False, max_cases: int=64) -> dict:
    """No DB creation on read-only path, no external writes on enforce.

    Enforced scans keep a durable cursor IN the same SQLite ledger so
    the first N bad tasks never permanently mask later ones. A partial scan
    NEVER claims complete coverage. A successful scan NEVER proves domain
    semantics, physical scheduling, or production release acceptance.
    """
    if not isinstance(max_cases,int) or not 1<=max_cases<=MAX_SCAN:
        raise ValueError("Conformance budget out of bounds")
    if not db_path.is_file() or db_path.is_symlink():
        return _blocked("NOT_CONFIGURED",checked=0,findings=[])
    if workspace.is_symlink():
        return _blocked("UNSAFE_WORKSPACE",checked=0,findings=[])
    if enforce:
        db=connect(db_path)
    else:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        db=sqlite3.connect(uri,uri=True,timeout=5)
        db.row_factory=sqlite3.Row
    try:
        if enforce:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS conformance_scan (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                last_task_id TEXT NOT NULL)""")
            db.execute("INSERT OR IGNORE INTO conformance_scan VALUES(1,'')")
            last=db.execute("SELECT last_task_id FROM conformance_scan WHERE singleton=1").fetchone()[0]
        else:
            last=""
        total=db.execute("""SELECT COUNT(*) FROM tasks
                    WHERE state IN ('NEEDS_REVIEW','DECOMPOSED','SANDBOX_VERIFIED','VERIFIED')""").fetchone()[0]
        selected=db.execute("""SELECT * FROM tasks
                 WHERE state IN ('NEEDS_REVIEW','DECOMPOSED','SANDBOX_VERIFIED','VERIFIED')
                   AND task_id>? ORDER BY task_id LIMIT ?""",(last,max_cases)).fetchall()
        if enforce and len(selected)<max_cases and last:
            selected+=db.execute("""SELECT * FROM tasks
                 WHERE state IN ('NEEDS_REVIEW','DECOMPOSED','SANDBOX_VERIFIED','VERIFIED')
                   AND task_id<=? ORDER BY task_id LIMIT ?""",
                 (last,max_cases-len(selected))).fetchall()
        findings=[]
        quarantined=[]
        for row in selected:
            # A previously assessed parent may have quarantined this child in
            # the same transaction. Never act on a stale snapshot of its state.
            current=db.execute("SELECT state FROM tasks WHERE task_id=?",
                               (row["task_id"],)).fetchone()
            if not current or current[0]!=row["state"]:
                findings.append({"task_id":row["task_id"],
                                 "state_at_observation":row["state"],
                                 "proof":"ALREADY_TRANSITIONED",
                                 "mechanical_conformance":False,
                                 "disposition":"SKIPPED_DUE_TO_PRIOR_REMEDIATION"})
                continue
            finding=_check_one(db,row,db_path,workspace,fixtures)
            findings.append(finding)
            if enforce and finding["disposition"]=="CONFIRMED_INCONSISTENCY":
                try:
                    descendants=_quarantine(db,row,finding["proof"])
                except ValueError:
                    # Cannot determine whole blast radius safely; never
                    # pretend remediation was successful or hide the blocker.
                    findings[-1]["enforcement"]="DEPENDENCY_BUDGET_BLOCKED"
                else:
                    quarantined.append({"task_id":row["task_id"],
                                        "reason":finding["proof"],
                                        "descendants":len(descendants)})
                    findings[-1]["enforcement"]="QUARANTINED"
        if enforce:
            next_cursor=selected[-1]["task_id"] if selected else ""
            db.execute("UPDATE conformance_scan SET last_task_id=? WHERE singleton=1",
                       (next_cursor,))
            db.commit()
        status=("CONFORMANCE_VIOLATIONS" if any(
                    f.get("disposition")=="CONFIRMED_INCONSISTENCY" for f in findings)
                else "EVIDENCE_INSUFFICIENT" if any(
                    not f["mechanical_conformance"] for f in findings)
                else "PARTIAL_EVIDENCE" if total>len(selected)
                else "MECHANICAL_EVIDENCE_OBSERVED" if total else "NO_RUNTIME_EVIDENCE")
        # An unobserved host or third-party semantic result is never upgraded
        # merely because task state, a local CI run, or this checker says PASS.
        return {
            "status":status,"checked":len(selected),"eligible":total,
            "exhaustive":total<=len(selected),
            "mechanically_valid":sum(f["mechanical_conformance"] for f in findings),
            "findings":findings,"quarantined":quarantined,
            "external_semantic_evidence":"NOT_OBSERVED",
            "unattended_windows_host_evidence":"NOT_OBSERVED",
            "production_mutation_authorized":False,
            "release_gate":"BLOCKED_AWAITING_INDEPENDENT_OUTCOME_AND_HOST_PROOF"
        }
    except (sqlite3.Error,OSError) as exc:
        if enforce:db.rollback()
        return _blocked("EVIDENCE_UNAVAILABLE",checked=0,findings=[],
                        diagnostic=type(exc).__name__)
    finally:
        db.close()
