"""Bounded local host tick. A host must actually invoke this; no hidden daemon/cloud."""
from __future__ import annotations

import sqlite3
from contextlib import closing
import time
from pathlib import Path

from .ledger import connect
from .runner import run_once
from .watch import poll_due_watches
from .sandbox_effect import advance_due_reviews
from .diagnostics import recover_due_unknowns, recover_research_transport
from .repair_oracle import review_due_repairs
from .conformance import inspect_conformance, effect_preflight
from .local_retry import schedule_failed_local_evidence


class HostNotConfigured(RuntimeError):
    """Scheduled work refuses to mint a new write authority on first run."""


def _admit_existing_ledger(path: Path) -> None:
    """Tick must use a pre-existing initialized DB created through explicit seeding."""
    if not path.is_file() or path.is_symlink():
        raise HostNotConfigured("No regular initialized SQLite DB; seed explicitly before enabling a host")
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            authority = db.execute(
                "SELECT goal_rev,grant_rev,write_allowed FROM authority WHERE singleton=1"
            ).fetchone()
            db.execute("SELECT task_id FROM tasks LIMIT 1").fetchall()
        if authority is None:
            raise HostNotConfigured("Authority row missing")
    except (sqlite3.Error, OSError) as exc:
        raise HostNotConfigured("Task authority DB unavailable or uninitialized") from exc


def _record_tick(path: Path, *, processed: int, finished_at: float) -> None:
    """Single bounded local witness, not a proof of an OS scheduler."""
    db = connect(path)
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS host_ticks (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            last_finished_at REAL NOT NULL,
            ticks INTEGER NOT NULL,
            processed_total INTEGER NOT NULL
        )""")
        db.execute("""INSERT INTO host_ticks(singleton,last_finished_at,ticks,processed_total)
            VALUES (1, ?, 1, ?)
            ON CONFLICT(singleton) DO UPDATE SET
              last_finished_at=excluded.last_finished_at,
              ticks=ticks+1, processed_total=processed_total+excluded.processed_total""",
                   (finished_at, processed))
        db.commit()
    finally:
        db.close()


def _pending_research_actions(path: Path, workspace: Path, *, limit: int = 16) -> list[dict]:
    """Only project review suggestions with a live grant and intact artifact."""
    import hashlib
    import json
    if not 1 <= limit <= 64:
        raise ValueError("Research projection limit out of bounds")
    from .runner import verify_artifact
    with closing(sqlite3.connect(path.resolve(strict=True).as_uri()+"?mode=ro",
                                 uri=True, timeout=5)) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute("""SELECT t.*,e.details FROM tasks t
            JOIN events e ON e.task_id=t.task_id
            JOIN authority a ON a.singleton=1
            WHERE t.state='NEEDS_REVIEW'
              AND t.goal_rev=a.goal_rev AND t.grant_rev=a.grant_rev
              AND a.write_allowed=1
              AND e.kind='RESEARCH_NEXT_ACTION_IDENTIFIED'
            ORDER BY e.event_id DESC LIMIT ?""",(min(max(limit*8,64),512),)).fetchall()
    items=[]
    for row in rows:
        try:
            receipt=json.loads(row["details"])
            task_id=row["task_id"]
            if receipt.get("authorized") is not False or not verify_artifact(workspace,dict(row)):
                continue
            artifact=workspace/"artifacts"/(task_id+".json")
            if artifact.is_symlink():
                continue
            raw=artifact.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=receipt.get("artifact_sha256"):
                continue
            payload=json.loads(raw)
            if (payload.get("next_research_action")!=receipt.get("action")
                or payload.get("reason")!=receipt.get("reason")
                or payload.get("next_action_authorized") is not False):
                continue
            items.append({"task_id":task_id,"next_research_action":receipt["action"],
                          "reason":receipt["reason"],"action_authorized":False})
            if len(items)>=limit:
                break
        except (ValueError,TypeError,KeyError,OSError,UnicodeError):
            continue
    return items



def _goal_progress(path: Path, workspace: Path | None = None,
                   fixtures: Path | None = None, *, max_tasks: int = 512) -> dict:
    """Cross-capability goal lineage, with no inferred semantic success.

    A deterministic observation of the ONE task ledger, not a planner,
    authorization authority, or business-outcome oracle.
    """
    with closing(sqlite3.connect(path.resolve(strict=True).as_uri()+"?mode=ro",
                                 uri=True, timeout=5)) as db:
        db.row_factory=sqlite3.Row
        authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        count=db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        rows=db.execute("""SELECT task_id,parent_task,state,goal_rev,grant_rev,
                                  due_at,error_code,source_spec FROM tasks
                           ORDER BY created_at,task_id LIMIT ?""",
                        (max_tasks,)).fetchall()
    by_id={row["task_id"]:row for row in rows}
    roots={}
    for row in rows:
        visited=set()
        node=row
        while node["parent_task"] in by_id and node["task_id"] not in visited:
            visited.add(node["task_id"])
            node=by_id[node["parent_task"]]
        root_id=node["task_id"]
        group=roots.setdefault(root_id,{"root_task_id":root_id,"states":{},
                                       "runnable":0,"awaiting_review":0,
                                       "blocked":0,"unknown":0,
                                       "stale_authority":0,
                                       "independent_checks":[],
                                       "failed_independent_checks":0})
        if (workspace is not None and fixtures is not None
            and row["state"]=="NEEDS_REVIEW"):
            try:
                import json
                kind=json.loads(row["source_spec"]).get("kind")
                if kind=="goal_case":
                    from .goal_audit import audit_goal
                    audit=audit_goal(path,workspace,fixtures,row["task_id"])
                    check=audit["status"]=="CANDIDATE_MECHANICALLY_VALID"
                elif kind=="record_reconciliation":
                    from .reconciliation_oracle import audit_stored_report
                    audit=audit_stored_report(path,workspace,fixtures,row["task_id"])
                    check=audit["status"]=="REPORT_MECHANICALLY_VERIFIED"
                else:
                    kind=None
                if kind is not None:
                    if not check:
                        group["failed_independent_checks"]+=1
                    group["independent_checks"].append({
                        "task_id":row["task_id"],"capability":kind,
                        "mechanically_verified":check,
                        "verdict":audit["status"],
                        "business_outcome_verified":False})
            except (ValueError,TypeError,KeyError,OSError):
                group["failed_independent_checks"]+=1
                group["independent_checks"].append({
                    "task_id":row["task_id"],
                    "mechanically_verified":False,
                    "verdict":"INDEPENDENT_CHECK_UNAVAILABLE",
                    "business_outcome_verified":False})
        state=row["state"]
        group["states"][state]=group["states"].get(state,0)+1
        valid=bool(authority and row["goal_rev"]==authority["goal_rev"]
                   and row["grant_rev"]==authority["grant_rev"]
                   and authority["write_allowed"]==1)
        if not valid:
            group["stale_authority"]+=1
        elif state in ("PENDING","RUNNING"):
            group["runnable"]+=1
        elif state in ("NEEDS_REVIEW","RESEARCH_NEEDED","NEEDS_REPLAN"):
            group["awaiting_review"]+=1
        elif state=="BLOCKED":
            group["blocked"]+=1
        elif state=="UNKNOWN":
            group["unknown"]+=1
    summary=[]
    for root_id in sorted(roots):
        item=roots[root_id]
        item["next_control_action"]=(
            "REAUTHORIZE_OR_SUPERSEDE" if item["stale_authority"] else
            "CONTINUE_ADMITTED_WORK" if item["runnable"] else
            "REPLAN_AFTER_FAILED_INDEPENDENT_CHECK" if item["failed_independent_checks"] else
            "REVIEW_UNRESOLVED_EVIDENCE" if item["awaiting_review"] else
            "DIAGNOSE_BLOCKER" if item["blocked"] or item["unknown"] else
            "REQUIRE_INDEPENDENT_OUTCOME_CHECK")
        item["semantic_outcome_verified"]=False
        summary.append(item)
    return {"goals":summary,"scanned_tasks":len(rows),
            "truncated":count>max_tasks,
            "semantic_outcome_verified":False}


def run_tick(db_path: Path, workspace: Path, fixture_root: Path, *, max_jobs: int = 16,
             planner_mode: str = "deterministic", local_model: str | None = None,
             auto_stage_goals: bool = False, auto_review_repos: bool = False,
             auto_local_goal_control: bool = False) -> dict:
    """Drain a bounded set of due jobs. Reruns/reboots reuse the same local DB.

    Scheduling is external (Windows Task Scheduler, cron, systemd); missed ticks
    are reconciled by the existing due_at query on next invocation. A recurring
    task intentionally schedules the next job relative to successful completion,
    rather than fabricating execution for each missed wall-clock interval.
    """
    if auto_review_repos and not auto_stage_goals:
        raise ValueError("Repo code review needs both explicit host opt-in flags")
    if not 1 <= max_jobs <= 64:
        raise ValueError("max_jobs must be between 1 and 64")
    if planner_mode not in ("deterministic", "ollama-local"):
        raise ValueError("Unsupported planner mode")
    _admit_existing_ledger(db_path)
    # Prior-success evidence is assessed before an opted-in sandbox write.
    # A partial/broken sweep blocks new effects, not ordinary read-only work.
    preflight = (effect_preflight(db_path,workspace,fixture_root)
                 if auto_stage_goals else None)
    # Capture source head before draining newly issued immutable evidence tasks.
    watches = poll_due_watches(db_path)
    results = []
    for _ in range(max_jobs):
        result = run_once(db_path, workspace, fixture_root,
                          planner_mode=planner_mode, local_model=local_model)
        if result["status"] == "IDLE":
            break
        results.append(result)
    # Optional sandbox-only follow-up: requires an explicit host flag.
    # At most max_jobs reviews in this tick; no external source mutation.
    reviews = (advance_due_reviews(db_path,workspace,fixture_root,max_reviews=min(max_jobs,8))
               if auto_stage_goals and preflight["admitted"] else [])
    # Already-UNKNOWN evidence tasks can be reconsidered only after a fresh
    # local source is available. New children remain in the same ledger and
    # are intentionally processed by a subsequent tick, not a recursive loop.
    repair_reviews = (review_due_repairs(db_path,workspace,fixture_root,
                                         limit=min(max_jobs,4),
                                         allow_repo_execution=auto_review_repos)
                      if auto_stage_goals and preflight["admitted"] else [])
    recoveries = (recover_due_unknowns(db_path,fixture_root)
                  if auto_stage_goals else [])
    # Read-only research transport recovery has its own finite attempt budget.
    recoveries.extend(recover_research_transport(db_path))
    # A failed independent LOCAL review may schedule one authorized same-capability
    # follow-up for the next host tick, never a recursive/remote retry.
    local_retries = schedule_failed_local_evidence(db_path,workspace,fixture_root,
                                                    limit=min(max_jobs,4))
    # Independent conformance is a default post-tick enforcement path.
    # It quarantines only confirmed mechanical contradictions, never
    # interprets missing semantic evidence as a proven code compromise.
    conformance = inspect_conformance(db_path,workspace,fixture_root,
                                     enforce=True,max_cases=min(max_jobs,16))
    # Explicit opt-in only. A separate bounded controller may enqueue a
    # LOCAL candidate for the NEXT tick, after ordinary evidence enforcement.
    # It cannot grant permissions or claim an external business outcome.
    if auto_local_goal_control:
        from .bounded_goal_control import advance_local_goals
        controlled=advance_local_goals(db_path,workspace,fixture_root,
                                       limit=min(max_jobs,4))
        # Reuse the SAME opt-in, task ledger and host; only capability-specific
        # independent verdict adapters differ. No second scheduler or grant.
        from .outcome_feedback import advance_evidence_goals
        controlled.extend(advance_evidence_goals(
            db_path,workspace,fixture_root,limit=min(max_jobs,4)))
    else:
        controlled=[]
    _record_tick(db_path, processed=len(results), finished_at=time.time())
    return {"status": "PROCESSED" if results or reviews or repair_reviews or recoveries or local_retries or conformance["quarantined"] or controlled or any(w["status"] != "NOT_DUE" for w in watches) else "IDLE",
            "watch_observations": watches,
            "sandbox_reviews": reviews,
            "repair_lab_reviews": repair_reviews,
            "diagnostic_followups": recoveries,
            "local_evidence_retries": local_retries,
            "pending_research_actions": _pending_research_actions(db_path,workspace),
            "local_goal_control": controlled,
            "goal_progress": _goal_progress(db_path,workspace,fixture_root),
            "conformance": conformance,
            "preflight": preflight,
            "processed": len(results), "capacity_reached": len(results) == max_jobs,
            "tasks": results, "semantic_outcome_verified": False,
            "note": "Local tick observed; OS scheduling and semantic outcomes not thereby proved"}
