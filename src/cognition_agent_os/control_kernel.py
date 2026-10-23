"""Shared, bounded and durable control-loop admission kernel.

This is the ONE host-side scan/transaction/grant/fairness implementation for
all opt-in local goal controllers. Domain adapters supply only typed proposal,
independent evidence, and legal transition policy. No model/tool can set grant.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from .ledger import connect, current_guard

# Fixed names, not strings read from an untrusted task or model.
_FAMILIES = frozenset({
    ("CONTROL_ACTIVE", "bounded_control_scan_cursor"),
    ("FEEDBACK_ACTIVE", "evidence_feedback_cursor"),
})


def drive_active_controller(
    db_path: Path, *,
    active_state: str,
    cursor_table: str,
    limit: int,
    setup: Callable[[sqlite3.Connection], None],
    step: Callable[[sqlite3.Connection, sqlite3.Row, bool, str], dict],
) -> list[dict]:
    """Execute at most one legal root transition per selected goal and tick.

    A durable cursor prevents first-N active roots from starving later roots.
    Each transition and its admission/event writes share a single IMMEDIATE
    transaction. A callback error rolls back its entire transition; it cannot
    leave an orphan admitted child. The previous finished roots remain durable.
    """
    if (type(limit) is not int or not 1 <= limit <= 8 or
        (active_state, cursor_table) not in _FAMILIES or
        not callable(setup) or not callable(step)):
        raise ValueError("INVALID_CONTROLLER_KERNEL_CONTRACT")
    db = connect(db_path)
    outcomes: list[dict] = []
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            setup(db)
            cursor_row = db.execute(
                f"SELECT last_task_id FROM {cursor_table} "
                "WHERE singleton=1").fetchone()
            if cursor_row is None:
                raise ValueError("CONTROL_CURSOR_NOT_CONFIGURED")
            cursor = cursor_row["last_task_id"]
            ids = [r["task_id"] for r in db.execute(
                """SELECT task_id FROM tasks WHERE state=? AND task_id>?
                   ORDER BY task_id LIMIT ?""",
                (active_state, cursor, limit)).fetchall()]
            if len(ids) < limit:
                ids.extend(r["task_id"] for r in db.execute(
                    """SELECT task_id FROM tasks WHERE state=? AND task_id<=?
                       ORDER BY task_id LIMIT ?""",
                    (active_state, cursor, limit-len(ids))).fetchall())
            if ids:
                db.execute(
                    f"UPDATE {cursor_table} SET last_task_id=? "
                    "WHERE singleton=1", (ids[-1],))
            db.commit()
        except BaseException:
            db.rollback()
            raise

        for task_id in ids:
            db.execute("BEGIN IMMEDIATE")
            try:
                root = db.execute(
                    "SELECT * FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()
                # Another actor may have changed its state between scan/step.
                if root is None or root["state"] != active_state:
                    db.commit()
                    continue
                allowed, reason = current_guard(db, dict(root), needs_write=True)
                result = step(db, root, allowed, reason)
                if not isinstance(result, dict) or not isinstance(
                    result.get("status"), str
                ):
                    raise ValueError("INVALID_CONTROLLER_TRANSITION_RESULT")
                db.commit()
                if result["status"] != "AWAITING_CHILD":
                    outcomes.append(result)
            except BaseException:
                db.rollback()
                raise
        return outcomes
    finally:
        db.close()
