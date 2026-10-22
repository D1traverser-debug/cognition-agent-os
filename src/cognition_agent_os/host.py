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


def run_tick(db_path: Path, workspace: Path, fixture_root: Path, *, max_jobs: int = 16,
             planner_mode: str = "deterministic", local_model: str | None = None,
             auto_stage_goals: bool = False, auto_review_repos: bool = False) -> dict:
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
    # Independent conformance is a default post-tick enforcement path.
    # It quarantines only confirmed mechanical contradictions, never
    # interprets missing semantic evidence as a proven code compromise.
    conformance = inspect_conformance(db_path,workspace,fixture_root,
                                     enforce=True,max_cases=min(max_jobs,16))
    _record_tick(db_path, processed=len(results), finished_at=time.time())
    return {"status": "PROCESSED" if results or reviews or repair_reviews or recoveries or conformance["quarantined"] or any(w["status"] != "NOT_DUE" for w in watches) else "IDLE",
            "watch_observations": watches,
            "sandbox_reviews": reviews,
            "repair_lab_reviews": repair_reviews,
            "diagnostic_followups": recoveries,
            "conformance": conformance,
            "preflight": preflight,
            "processed": len(results), "capacity_reached": len(results) == max_jobs,
            "tasks": results, "semantic_outcome_verified": False,
            "note": "Local tick observed; OS scheduling and semantic outcomes not thereby proved"}
