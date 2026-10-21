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
EVIDENCED_STATES=("NEEDS_REVIEW","DECOMPOSED","SANDBOX_VERIFIED","VERIFIED","REPAIR_LAB_VERIFIED")
MAX_SCAN=512
MAX_DEPENDENCIES=256

SANDBOX_CAPABILITY="goal_sandbox_stage"
REPAIR_LAB_CAPABILITY="pure_code_repair_lab"
CRITICAL_REPAIR_LAB_BREACHES=frozenset((
    "STAGED_PATCH_DIFFERS","STAGED_PATCH_MISSING",
    "ACCEPTANCE_RECEIPT_MISMATCH","ACCEPTANCE_RECEIPT_MISSING",
    "ARTIFACT_HASH_MISMATCH","NON_MINIMAL_SOURCE_PATCH",
    "STAGED_PATCH_MISMATCH","PIPELINE_RECEIPT_MISSING",
    "PIPELINE_RECEIPT_CONFLICT","PROPOSAL_HASH_CHANGED",
    "STAGED_REPO_PATCH_MISMATCH","REPO_RECEIPT_MISSING",
    "REPO_RECEIPT_CONFLICT"
))
CRITICAL_SANDBOX_BREACHES=frozenset((
    "STAGED_ARTIFACT_HASH_MISMATCH","STAGED_EFFECT_BYTES_MISMATCH",
    "FALSE_EFFECT_RECEIPT","MISSING_OR_REPEATED_EFFECT_RECEIPT",
    "CANDIDATE_HASH_MISMATCH","STAGED_CONSTRAINTS_FAILED"
))


def capability_disabled(db_path: Path, kind: str=SANDBOX_CAPABILITY) -> bool:
    """Persistent fail-closed state in the existing ledger, never self-reset."""
    if not db_path.is_file() or db_path.is_symlink():
        return True
    try:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
            exists=db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='conformance_capability_guard'""").fetchone()
            if not exists:
                return False
            row=db.execute("""SELECT disabled FROM conformance_capability_guard
                               WHERE kind=?""",(kind,)).fetchone()
            return bool(row and row[0])
    except (sqlite3.Error,OSError):
        return True


def _trip_critical_guard(db, task_id: str, reason: str,
                         *, kind: str=SANDBOX_CAPABILITY) -> bool:
    """Independently confirmed integrity breaches disable only own effect family."""
    allowed=(CRITICAL_SANDBOX_BREACHES if kind==SANDBOX_CAPABILITY else
             CRITICAL_REPAIR_LAB_BREACHES if kind==REPAIR_LAB_CAPABILITY else ())
    if reason not in allowed:
        return False
    db.execute("""INSERT OR IGNORE INTO conformance_capability_guard
                  (kind,disabled,reason,trigger_task)
                  VALUES (?,1,?,?)""",(kind,reason,task_id))
    changed=db.execute("SELECT changes()").fetchone()[0]>0
    if changed:
        event(db,task_id,"CONFORMANCE_CAPABILITY_DISABLED",{
            "capability":kind,"reason":reason,
            "policy":"NO_AUTOMATIC_REENABLE_WITHOUT_SEPARATE_ACCEPTANCE"})
    return changed


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
        elif state=="REPAIR_LAB_VERIFIED":
            if kind=="repo_container_repair":
                from .repo_repair import audit_repo
                report=audit_repo(db_path,workspace,fixtures,tid,require_staged=True)
            elif kind=="pipeline_code_repair":
                from .pipeline_oracle import audit_pipeline
                report=audit_pipeline(db_path,workspace,fixtures,tid,
                                     hidden=True,staged=True)
            else:
                from .repair_oracle import audit_patch
                report=audit_patch(db_path,workspace,fixtures,tid,
                                   reveal_holdout=True,require_staged=True)
            proof=("MECHANICALLY_VALID" if report["status"]=="HOLDOUT_ACCEPTED"
                   else report.get("reason",report["status"]))
        elif state=="DECOMPOSED":
            result=audit_intent_plan(db_path,tid)
            proof=("MECHANICALLY_VALID" if result["status"]=="PLAN_MECHANICALLY_VALID"
                   else result.get("reason","PLAN_AUDIT_FAILED"))
        elif state=="NEEDS_REVIEW":
            if kind=="repo_container_repair":
                from .repo_repair import audit_repo
                report=audit_repo(db_path,workspace,fixtures,tid)
                proof=("MECHANICALLY_VALID" if report["status"]=="REPO_BYTES_MECHANICALLY_VALID"
                       else report.get("reason",report["status"]))
            elif kind=="pipeline_code_repair":
                from .pipeline_oracle import audit_pipeline
                report=audit_pipeline(db_path,workspace,fixtures,tid)
                proof=("MECHANICALLY_VALID" if
                       report["status"]=="VISIBLE_PIPELINE_VERIFIED"
                       else report.get("reason",report["status"]))
            elif kind=="pure_code_repair":
                from .repair_oracle import audit_patch
                report=audit_patch(db_path,workspace,fixtures,tid)
                proof=("MECHANICALLY_VALID" if
                       report["status"]=="VISIBLE_PATCH_MECHANICALLY_VALID"
                       else report.get("reason",report["status"]))
            elif kind=="goal_case":
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
              "HOLDOUT_UNVERIFIABLE","HOLDOUT_PIN_MISMATCH",
              "EVIDENCE_RECHECK_UNAVAILABLE",
              "SOURCE_CHANGED_SINCE_PROPOSAL","SOURCE_HAS_CHANGED"}
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


def _quarantine(db, row: sqlite3.Row, reason: str,
                *, independently_proven_descendants: list[str] | None=None) -> list[str]:
    """Revoke derived claims; expanded closures require two agreeing oracles."""
    tid=row["task_id"]
    descendants=(_descendants(db,tid) if independently_proven_descendants is None
                 else independently_proven_descendants)
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
    if row["state"]=="SANDBOX_VERIFIED":
        _trip_critical_guard(db,tid,reason)
    elif row["state"]=="REPAIR_LAB_VERIFIED":
        _trip_critical_guard(db,tid,reason,kind=REPAIR_LAB_CAPABILITY)
    event(db,tid,"CONFORMANCE_VIOLATION",{
        "observation":reason,
        "dependent_tasks_quarantined":descendants,
        "repair_applied":"REVOKE_FALSE_STATE_CLAIM",
        "root_cause_proven":False,
        "external_semantic_outcome_proven":False})
    return descendants


def _emergency_dependency_stop(db, row: sqlite3.Row, reason: str) -> None:
    """A partial dependency closure is NOT acceptable as containment.

    Revoke the ledger-wide write grant and open the sandbox circuit in the
    *same* transaction. Pending descendants remain recorded for later
    diagnosis, but none can receive authorized write effects. This does not
    guess or silently truncate a large/cyclic dependency graph.
    """
    tid=row["task_id"]
    db.execute("""UPDATE authority SET write_allowed=0,grant_rev=grant_rev+1
                  WHERE singleton=1 AND write_allowed!=0""")
    db.execute("""UPDATE tasks SET state='UNKNOWN',error_code=?,
        lease_until=NULL,claim_token=NULL,state_version=state_version+1
        WHERE task_id=? AND state=?""",
        ("CONFORMANCE_DEPENDENCY_GRAPH_UNBOUNDED",tid,row["state"]))
    db.execute("""INSERT OR IGNORE INTO conformance_capability_guard
          (kind,disabled,reason,trigger_task) VALUES (?,1,?,?)""",
          (SANDBOX_CAPABILITY,"DEPENDENCY_GRAPH_UNBOUNDED",tid))
    event(db,tid,"CONFORMANCE_EMERGENCY_STOP",{
        "observation":reason,
        "failure_family":"DEPENDENCY_GRAPH_UNBOUNDED",
        "alternative_hypotheses":[
            "A task may have excessive legitimate fan-out",
            "A corrupted or cyclic dependency graph may have enlarged scope"
        ],
        "unreviewed_descendants_may_exist":True,
        "response":"REVOKED_LEDGER_WRITE_GRANT_AND_DISABLED_SANDBOX",
        "root_cause_proven":False,
        "requires_independent_recovery_acceptance":True})


def effect_preflight(db_path: Path, workspace: Path, fixtures: Path) -> dict:
    """Run full bounded pre-effect verification; partial coverage blocks writes."""
    result=inspect_conformance(db_path,workspace,fixtures,enforce=True,
                               max_cases=MAX_SCAN)
    # Confirmed but fully quarantined *non-critical* bad records need not
    # starve unrelated legitimate tasks. Uncontained faults, emergency stop,
    # and integrity-circuit trips are never admitted.
    all_contradictions_contained=all(
        finding.get("disposition")!="CONFIRMED_INCONSISTENCY" or
        finding.get("enforcement")=="QUARANTINED"
        for finding in result.get("findings",[]))
    safe=(result.get("exhaustive") is True and
          result["status"] in ("NO_RUNTIME_EVIDENCE",
                               "MECHANICAL_EVIDENCE_OBSERVED",
                               "EVIDENCE_INSUFFICIENT",
                               "CONFORMANCE_VIOLATIONS") and
          all_contradictions_contained and
          not result.get("emergency_stops") and
          not result.get("capability_circuit_open",True))
    return {"admitted":bool(safe),
            "contained_noncritical_violations":bool(result.get("quarantined")),
            "reason":"PREFLIGHT_ACCEPTED" if safe else "PREFLIGHT_NOT_SATISFIED",
            "checked":result.get("checked",0),
            "eligible":result.get("eligible"),
            "status":result["status"],
            "capability_circuit_open":result.get("capability_circuit_open",True),
            "quarantined":len(result.get("quarantined",[])),
            "emergency_stops":len(result.get("emergency_stops",[]))}


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
            db.execute("""CREATE TABLE IF NOT EXISTS conformance_capability_guard (
                 kind TEXT PRIMARY KEY, disabled INTEGER NOT NULL,
                 reason TEXT NOT NULL, trigger_task TEXT NOT NULL)""")
            db.execute("INSERT OR IGNORE INTO conformance_scan VALUES(1,'')")
            last=db.execute("SELECT last_task_id FROM conformance_scan WHERE singleton=1").fetchone()[0]
        else:
            last=""
        total=db.execute("""SELECT COUNT(*) FROM tasks
                    WHERE state IN ('NEEDS_REVIEW','DECOMPOSED','SANDBOX_VERIFIED','VERIFIED','REPAIR_LAB_VERIFIED')""").fetchone()[0]
        selected=db.execute("""SELECT * FROM tasks
                 WHERE state IN ('NEEDS_REVIEW','DECOMPOSED','SANDBOX_VERIFIED','VERIFIED','REPAIR_LAB_VERIFIED')
                   AND task_id>? ORDER BY task_id LIMIT ?""",(last,max_cases)).fetchall()
        if enforce and len(selected)<max_cases and last:
            selected+=db.execute("""SELECT * FROM tasks
                 WHERE state IN ('NEEDS_REVIEW','DECOMPOSED','SANDBOX_VERIFIED','VERIFIED','REPAIR_LAB_VERIFIED')
                   AND task_id<=? ORDER BY task_id LIMIT ?""",
                 (last,max_cases-len(selected))).fetchall()
        findings=[]
        quarantined=[]
        emergency_stops=[]
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
                    # Two competing structural causes were previously collapsed
                    # into an unconditional global stop. Rerun an independently
                    # implemented, bounded causal experiment under the SAME
                    # SQLite write lock, before deciding the remediation scope.
                    from .graph_experiment import (
                        investigate_dependency_graph, verify_local_quarantine)
                    try:
                        proof=investigate_dependency_graph(db,row["task_id"])
                    except (ValueError,sqlite3.Error,OSError):
                        proof={"status":"UNVERIFIABLE",
                               "action":"GLOBAL_FAIL_CLOSED",
                               "reason":"GRAPH_ORACLE_EXECUTION_FAILED",
                               "hypotheses":[]}
                    evidence={k:v for k,v in proof.items() if k!="descendants"}
                    event(db,row["task_id"],"CONFORMANCE_GRAPH_EXPERIMENT",evidence)
                    if proof["action"]=="COMPLETE_LOCAL_QUARANTINE":
                        descendants=_quarantine(
                            db,row,finding["proof"],
                            independently_proven_descendants=proof["descendants"])
                        readback=verify_local_quarantine(
                            db,row["task_id"],descendants)
                        if readback["accepted"]:
                            event(db,row["task_id"],"CONFORMANCE_REPAIR_ACCEPTED",{
                                "method":"INDEPENDENT_GRAPH_FULL_CLOSURE",
                                "post_effect":readback,
                                "source_graph_sha256":proof["snapshot_sha256"],
                                "semantic_root_cause_proven":False})
                            quarantined.append({
                                "task_id":row["task_id"],"reason":finding["proof"],
                                "descendants":len(descendants),
                                "repair_strategy":"INDEPENDENTLY_VERIFIED_FULL_CLOSURE"})
                            findings[-1]["enforcement"]="QUARANTINED"
                            findings[-1]["causal_experiment"]="ACYCLIC_HIGH_FANOUT_PROVEN"
                        else:
                            # The plan and actual SQLite result disagree.
                            # No local repair acceptance or global grant
                            # restoration may follow a failed independent read.
                            _emergency_dependency_stop(db,row,finding["proof"])
                            event(db,row["task_id"],"CONFORMANCE_REPAIR_REJECTED",readback)
                            emergency_stops.append(row["task_id"])
                            findings[-1]["enforcement"]="EMERGENCY_STOP"
                            findings[-1]["causal_experiment"]="POST_EFFECT_REJECTION"
                    else:
                        _emergency_dependency_stop(db,row,finding["proof"])
                        emergency_stops.append(row["task_id"])
                        findings[-1]["enforcement"]="EMERGENCY_STOP"
                        findings[-1]["causal_experiment"]=proof["status"]
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
            "emergency_stops":emergency_stops,
            "capability_circuit_open": bool(db.execute(
                """SELECT disabled FROM conformance_capability_guard
                   WHERE kind=?""",(SANDBOX_CAPABILITY,)).fetchone()[0])
                if enforce and db.execute(
                    """SELECT 1 FROM conformance_capability_guard WHERE kind=?""",
                    (SANDBOX_CAPABILITY,)).fetchone() else
                capability_disabled(db_path,SANDBOX_CAPABILITY),
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
