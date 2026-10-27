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
MAX_LEDGER_EVENTS_PER_GOAL = 4096
_ALERT_STATES = frozenset({
    "GOAL_IDENTITY_UNVERIFIABLE",
    "REPEATED_CANDIDATE_UNVERIFIED",
    "OWNER_GOAL_BLOCKED_WITHOUT_RESULT",
    "NO_ADMITTED_CHILD",
    "EVIDENCE_RESEARCH_ONLY_NOT_OWNER_RESULT",
    "LOCAL_WORK_NOT_OWNER_RESULT",
    "COMPONENT_RESULT_NOT_OWNER_RESULT",
    "OWNER_OUTCOME_NOT_INDEPENDENTLY_ESTABLISHED",
    "OWNER_POSTCONDITION_REGRESSED",
    "NATIVE_OWNER_SOURCE_CHANGED",
    "NATIVE_OWNER_EVIDENCE_UNVERIFIABLE",
    "NATIVE_METHOD_BUDGET_EXHAUSTED",
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


def _lineage_evidence_fingerprint(
    db: sqlite3.Connection, task_ids: list[str]
) -> tuple[str, bool]:
    """Hash SEMANTIC evidence transitions, not append-only event IDs.

    Two identical receipts for the same task/event kind convey no new
    observation. A→B→A *does* convey a reversal; it must be retained.
    Observation events produced by this very function never feed back into
    its fingerprint. Oversized evidence must fail closed as incomplete.
    """
    if not task_ids:
        return hashlib.sha256(b"[]").hexdigest(), True
    placeholders = ",".join("?" for _ in task_ids)
    rows = db.execute(
        "SELECT task_id,kind,details FROM events "
        "WHERE kind NOT IN ('OWNER_GOAL_DRIFT_SIGNAL', "
        "'OWNER_GOAL_LOCAL_RESULT_OBSERVED') AND task_id IN ("
        + placeholders + ") ORDER BY event_id LIMIT ?",
        [*task_ids, MAX_LEDGER_EVENTS_PER_GOAL + 1],
    ).fetchall()
    complete = len(rows) <= MAX_LEDGER_EVENTS_PER_GOAL
    last_by_topic = {}
    semantic = []
    for row in rows[:MAX_LEDGER_EVENTS_PER_GOAL]:
        topic = (row["task_id"], row["kind"])
        body = row["details"]
        if last_by_topic.get(topic) == body:
            continue
        last_by_topic[topic] = body
        semantic.append((topic[0], topic[1], body))
    digest = hashlib.sha256(json.dumps(
        semantic, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return digest, complete


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


def observe_owner_goal_drift(db_path: Path, *, limit: int = 8,
                             workspace: Path | None = None,
                             fixtures: Path | None = None) -> list[dict]:
    """One event on changed goal-level blockage, never on mere local success.

    Only original open_goal/native_goal roots are monitored. Unknown
    domain roots are NOT quietly reinterpreted as owner goals. No source content,
    model completions or private objective strings enter event details.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_ROOTS_PER_TICK:
        raise ValueError("INVALID_GOAL_DRIFT_SCAN_LIMIT")
    if (workspace is None) != (fixtures is None):
        raise ValueError("OWNER_OUTCOME_REQUIRES_BOTH_SOURCE_AND_WORKSPACE")
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
                    or source.get("kind") not in ("open_goal", "native_goal")):
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
                evidence_sha, receipts_complete = _lineage_evidence_fingerprint(
                    db, [root_id] + [d["task_id"] for d in descendants])
                if not complete or not receipts_complete:
                    result["fidelity_state"] = "GOAL_LINEAGE_INCOMPLETE"
                    result["next_goal_action"] = "INSPECT_COMPLETE_LINEAGE"
                owner_local = None
                native_observation = None
                if (complete and receipts_complete
                    and workspace is not None and fixtures is not None):
                    if source["kind"] == "open_goal":
                        from .owner_postcondition import inspect_owner_local_outcome
                        owner_local = inspect_owner_local_outcome(
                            db_path, workspace, fixtures, root_id)
                        if owner_local["local_owner_outcome_verified"]:
                            result["fidelity_state"] = "LOCAL_OWNER_RESULT_VERIFIED"
                            result["next_goal_action"] = "MAINTAIN_INDEPENDENT_READBACK"
                    else:
                        from .native_decision import inspect_native_goal
                        native_observation = inspect_native_goal(
                            db_path, workspace, fixtures, root_id)
                        native_status = native_observation["status"]
                        if native_status == "NATIVE_SOURCE_UNAVAILABLE":
                            result["fidelity_state"] = "NATIVE_OWNER_SOURCE_UNAVAILABLE"
                            result["next_goal_action"] = "RESTORE_SOURCE_MANIFEST_BEFORE_NEXT_METHOD"
                        elif native_status == "NATIVE_SOURCE_CHANGED":
                            result["fidelity_state"] = "NATIVE_OWNER_SOURCE_CHANGED"
                            result["next_goal_action"] = "REVALIDATE_SOURCE_BEFORE_NEXT_METHOD"
                        elif native_status in ("NATIVE_EVIDENCE_UNVERIFIABLE",
                                               "NATIVE_GOAL_UNVERIFIABLE"):
                            result["fidelity_state"] = "NATIVE_OWNER_EVIDENCE_UNVERIFIABLE"
                            result["next_goal_action"] = "RECHECK_ORIGINAL_GOAL_AND_RESULT"
                        elif native_status == "NATIVE_DECISION_BUDGET_EXHAUSTED":
                            result["fidelity_state"] = "NATIVE_METHOD_BUDGET_EXHAUSTED"
                            result["next_goal_action"] = "REASSESS_METHODS_VS_ORIGINAL_GOAL"
                old = db.execute(
                    "SELECT observation_sha256,fidelity_state FROM owner_goal_drift_seen "
                    "WHERE root_task_id=?", (root_id,)
                ).fetchone()
                if (owner_local is not None and
                    not owner_local["local_owner_outcome_verified"] and
                    old is not None and
                    old["fidelity_state"] in (
                        "LOCAL_OWNER_RESULT_VERIFIED",
                        "OWNER_POSTCONDITION_REGRESSED")):
                    result["fidelity_state"] = "OWNER_POSTCONDITION_REGRESSED"
                    result["next_goal_action"] = "REASSESS_OWNER_RESULT_WITH_CURRENT_EVIDENCE"
                state = result["fidelity_state"]
                fingerprint = hashlib.sha256(json.dumps({
                    "root_task": _task_evidence_snapshot(root),
                    "descendants": sorted(
                        _task_evidence_snapshot(d) for d in descendants),
                    "lineage_semantic_receipts_sha256": evidence_sha,
                    "lineage_receipts_complete": receipts_complete,
                    "state": state,
                    "native_decision_observation": ({
                        "status": native_observation["status"],
                        "observation_sha256": native_observation.get(
                            "observation_sha256"),
                        "reason": native_observation.get("reason"),
                        "owner_outcome_verified": False,
                    } if native_observation is not None else None),
                    "independent_local_outcome": ({
                        "status": owner_local["status"],
                        "reason": owner_local.get("reason"),
                        "evidence_sha256": owner_local.get("evidence_sha256"),
                        "local_owner_outcome_verified":
                            owner_local["local_owner_outcome_verified"],
                    } if owner_local is not None else None),
                }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if old is not None and old["observation_sha256"] == fingerprint:
                    continue
                db.execute("""INSERT INTO owner_goal_drift_seen(
                    root_task_id,observation_sha256,fidelity_state)
                    VALUES(?,?,?) ON CONFLICT(root_task_id) DO UPDATE SET
                    observation_sha256=excluded.observation_sha256,
                    fidelity_state=excluded.fidelity_state""",
                    (root_id, fingerprint, state))
                if state == "LOCAL_OWNER_RESULT_VERIFIED":
                    details = {
                        "root_contract_sha256": result["root_contract_digest"],
                        "observation_sha256": fingerprint,
                        "local_outcome_scope": owner_local["outcome_scope"],
                        "evidence_sha256": owner_local["evidence_sha256"],
                        "local_owner_outcome_verified": True,
                        "business_outcome_verified": False,
                        "real_external_outcome_verified": False,
                    }
                    event(db, root_id, "OWNER_GOAL_LOCAL_RESULT_OBSERVED", details)
                    results.append({
                        "root_task_id": root_id,
                        "status": "LOCAL_OWNER_RESULT_OBSERVED",
                        **details,
                    })
                    continue
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
