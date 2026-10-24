"""Durable OT13 owner-goal drift signals, on the single existing task ledger.

No additional scheduler, authorizer, model self-grading or autonomous external
effects. The Host observes actual root/descendant work under one SQLite lock and
records a signal ONCE per changed evidence fingerprint. This allows a later
authorized planning step to consume a durable objective-level blocker instead
of mistaking successful subtasks for a finished owner goal.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .goal_fidelity import check_goal_fidelity
from .ledger import connect, current_guard, event, require_initialized_ledger

MAX_ROOTS_PER_TICK = 16
MAX_DESCENDANTS_PER_ROOT = 64
_ALERT_STATES = frozenset({
    "GOAL_IDENTITY_UNVERIFIABLE",
    "REPEATED_CANDIDATE_UNVERIFIED",
    "OWNER_GOAL_BLOCKED_WITHOUT_RESULT",
    "NO_ADMITTED_CHILD",
    "EVIDENCE_RESEARCH_ONLY_NOT_OWNER_RESULT",
    "LOCAL_WORK_NOT_OWNER_RESULT",
    "COMPONENT_RESULT_NOT_OWNER_RESULT",
    "OWNER_OUTCOME_NOT_INDEPENDENTLY_ESTABLISHED",
})


def _ensure(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS owner_goal_drift_cursor(
      singleton INTEGER PRIMARY KEY CHECK(singleton=1),
      last_root_id TEXT NOT NULL)""")
    db.execute("INSERT OR IGNORE INTO owner_goal_drift_cursor VALUES(1,'')")
    db.execute("""CREATE TABLE IF NOT EXISTS owner_goal_drift_seen(
      root_task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
      observation_sha256 TEXT NOT NULL,
      fidelity_state TEXT NOT NULL)""")


def _descendants(db: sqlite3.Connection, root_id: str) -> tuple[list[dict], bool]:
    queue = [root_id]
    seen = {root_id}
    result = []
    while queue:
        current = queue.pop(0)
        rows = db.execute(
            "SELECT task_id,parent_task,state,source_spec,goal_rev,grant_rev, "
            "state_version,artifact_hash,error_code,decision "
            "FROM tasks WHERE parent_task=? ORDER BY task_id LIMIT ?",
            (current, MAX_DESCENDANTS_PER_ROOT + 1),
        ).fetchall()
        if len(rows) > MAX_DESCENDANTS_PER_ROOT:
            return result, False
        for row in rows:
            if row["task_id"] in seen or len(result) >= MAX_DESCENDANTS_PER_ROOT:
                return result, False
            seen.add(row["task_id"])
            result.append(dict(row))
            queue.append(row["task_id"])
    return result, True


def _select_roots(db: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Fair bounded root scan; unrelated roots cannot permanently starve goals."""
    cursor = db.execute(
        "SELECT last_root_id FROM owner_goal_drift_cursor WHERE singleton=1"
    ).fetchone()["last_root_id"]
    rows = list(db.execute(
        "SELECT * FROM tasks WHERE parent_task IS NULL AND task_id>? "
        "ORDER BY task_id LIMIT ?", (cursor, limit)
    ).fetchall())
    if len(rows) < limit:
        rows += list(db.execute(
            "SELECT * FROM tasks WHERE parent_task IS NULL AND task_id<=? "
            "ORDER BY task_id LIMIT ?", (cursor, limit - len(rows))
        ).fetchall())
    if rows:
        db.execute(
            "UPDATE owner_goal_drift_cursor SET last_root_id=? WHERE singleton=1",
            (rows[-1]["task_id"],)
        )
    return rows


def _lineage_evidence_epoch(db: sqlite3.Connection, task_ids: list[str]) -> int:
    """Changed ledger receipts must invalidate a stale observation fingerprint.

    Drift signals themselves are excluded: observing a goal must never
    recursively create 'new evidence' on its next unchanged Host tick.
    """
    if not task_ids:
        return 0
    placeholders = ",".join("?" for _ in task_ids)
    row = db.execute(
        "SELECT COALESCE(MAX(event_id), 0) FROM events "
        "WHERE kind!='OWNER_GOAL_DRIFT_SIGNAL' AND task_id IN ("
        + placeholders + ")", task_ids
    ).fetchone()
    return int(row[0])


def _task_evidence_snapshot(task: dict | sqlite3.Row) -> tuple:
    """Stable, content-free identity of all persisted task outcome fields."""
    raw = task["source_spec"]
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    return (
        task["task_id"], task["state"], task["state_version"],
        task["goal_rev"], task["grant_rev"],
        hashlib.sha256(raw_bytes).hexdigest(),
        task["artifact_hash"], task["error_code"], task["decision"],
    )


def observe_owner_goal_drift(db_path: Path, *, limit: int = 8) -> list[dict]:
    """One event on changed goal-level blockage, never on mere local success.

    Only original open_goal roots are monitored. Unknown/unsupported domain
    roots are NOT quietly reinterpreted as owner goals. No source content,
    model completions or private objective strings enter event details.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_ROOTS_PER_TICK:
        raise ValueError("INVALID_GOAL_DRIFT_SCAN_LIMIT")
    # Observing a goal may not implicitly create a new authority database.
    require_initialized_ledger(db_path)
    results = []
    db = connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            _ensure(db)
            for root in _select_roots(db, limit):
                try:
                    source = json.loads(root["source_spec"])
                except (ValueError, TypeError):
                    continue
                if (not isinstance(source, dict)
                    or source.get("kind") != "open_goal"):
                    continue
                root_id = root["task_id"]
                descendants, complete = _descendants(db, root_id)
                allowed, reason = current_guard(db, dict(root), needs_write=True)
                if not allowed:
                    results.append({
                        "root_task_id": root_id, "status": "NOT_ADMITTED",
                        "reason": reason, "owner_outcome_verified": False,
                    })
                    continue
                result = check_goal_fidelity(dict(root), descendants)
                if not complete:
                    result["fidelity_state"] = "GOAL_LINEAGE_INCOMPLETE"
                    result["next_goal_action"] = "INSPECT_COMPLETE_LINEAGE"
                state = result["fidelity_state"]
                fingerprint = hashlib.sha256(json.dumps({
                    "root_task": _task_evidence_snapshot(root),
                    "descendants": sorted(
                        _task_evidence_snapshot(d) for d in descendants),
                    "lineage_receipt_epoch": _lineage_evidence_epoch(
                        db, [root_id] + [d["task_id"] for d in descendants]),
                    "state": state,
                }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                old = db.execute(
                    "SELECT observation_sha256 FROM owner_goal_drift_seen "
                    "WHERE root_task_id=?", (root_id,)
                ).fetchone()
                if old is not None and old["observation_sha256"] == fingerprint:
                    continue
                db.execute("""INSERT INTO owner_goal_drift_seen(
                    root_task_id,observation_sha256,fidelity_state)
                    VALUES(?,?,?) ON CONFLICT(root_task_id) DO UPDATE SET
                    observation_sha256=excluded.observation_sha256,
                    fidelity_state=excluded.fidelity_state""",
                    (root_id, fingerprint, state))
                if state not in _ALERT_STATES and state != "GOAL_LINEAGE_INCOMPLETE":
                    continue
                details = {
                    "root_contract_sha256": result["root_contract_digest"],
                    "observation_sha256": fingerprint,
                    "fidelity_state": state,
                    "next_goal_action": result["next_goal_action"],
                    "owner_outcome_verified": False,
                    "automatically_approved": False,
                    "source_content_recorded": False,
                }
                event(db, root_id, "OWNER_GOAL_DRIFT_SIGNAL", details)
                results.append({
                    "root_task_id": root_id, "status": "DRIFT_SIGNAL_RECORDED",
                    **details,
                })
            db.commit()
        except BaseException:
            db.rollback()
            raise
        return results
    finally:
        db.close()
