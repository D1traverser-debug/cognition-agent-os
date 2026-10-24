"""Single authoritative durable task and grant ledger, for one local machine."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=20000")
    return db


class LedgerNotConfigured(RuntimeError):
    """Execution cannot mint an authority or modify an uninitialized ledger."""


def require_initialized_ledger(path: Path) -> None:
    """Read-only admission for every operational entrypoint, not just the host.

    Intentionally does not call connect() or initialize(): both can create or
    modify SQLite storage. A provisioned but revoked ledger remains valid for
    non-mutating processing, whereas partial/corrupt authority must fail closed.
    """
    from contextlib import closing

    if not path.is_file() or path.is_symlink():
        raise LedgerNotConfigured("Ledger is not initialized or configured")
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            grant = db.execute(
                "SELECT goal_rev,grant_rev,write_allowed "
                "FROM authority WHERE singleton=1"
            ).fetchone()
            db.execute("SELECT task_id FROM tasks LIMIT 1").fetchone()
            if (grant is None
                or any(type(value) is not int for value in grant)
                or grant[0] < 1 or grant[1] < 1
                or grant[2] not in (0, 1)):
                raise LedgerNotConfigured("Ledger authority is not initialized")
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise LedgerNotConfigured("Ledger is not initialized or configured") from exc


def initialize(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS authority (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), goal_rev INTEGER NOT NULL,
      grant_rev INTEGER NOT NULL, write_allowed INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks (
      task_id TEXT PRIMARY KEY, state TEXT NOT NULL, state_version INTEGER NOT NULL,
      goal_rev INTEGER NOT NULL, grant_rev INTEGER NOT NULL, due_at REAL NOT NULL,
      interval_seconds INTEGER NOT NULL, source_spec TEXT NOT NULL, lease_until REAL,
      claim_token TEXT, decision TEXT, artifact_hash TEXT, error_code TEXT,
      created_at REAL NOT NULL, parent_task TEXT);
    CREATE TABLE IF NOT EXISTS events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
      kind TEXT NOT NULL, details TEXT NOT NULL, happened_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_tasks_parent_task ON tasks(parent_task);
    CREATE TABLE IF NOT EXISTS knowledge_dependencies(
       task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
       evidence_path TEXT NOT NULL,
       evidence_sha256 TEXT NOT NULL,
       source_id TEXT NOT NULL);
    """)
    db.execute("INSERT OR IGNORE INTO authority VALUES(1,1,1,1)")
    db.commit()


def event(db: sqlite3.Connection, task_id: str, kind: str, details: dict | None = None) -> None:
    db.execute("INSERT INTO events(task_id,kind,details,happened_at) VALUES(?,?,?,?)",
               (task_id, kind, json.dumps(details or {}, sort_keys=True), time.time()))


def create_task(db: sqlite3.Connection, spec: dict, *, interval_seconds: int = 0, due_at: float | None = None,
                parent: str | None = None, commit: bool = True) -> str:
    if interval_seconds < 0:
        raise ValueError("Negative recurrence interval")
    row = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
    tid = uuid.uuid4().hex
    db.execute("""INSERT INTO tasks(task_id,state,state_version,goal_rev,grant_rev,due_at,interval_seconds,
              source_spec,created_at,parent_task) VALUES(?, 'PENDING',0,?,?,?,?,?,?,?)""",
               (tid, row["goal_rev"], row["grant_rev"], time.time() if due_at is None else due_at,
                interval_seconds, json.dumps(spec, sort_keys=True), time.time(), parent))
    event(db, tid, "ENQUEUED", {"parent": parent})
    if commit:
        db.commit()
    return tid


def claim_one(db: sqlite3.Connection, *, now: float | None = None, lease_seconds: int = 40) -> dict | None:
    now = time.time() if now is None else now
    db.execute("BEGIN IMMEDIATE")
    try:
        # Admit useful work first: stale-goal tasks are still eventually
        # claimed and fenced, but cannot consume the last slot ahead of
        # legitimate work from the current goal revision.
        row = db.execute("""SELECT t.* FROM tasks t
                       JOIN authority a ON a.singleton=1
                       WHERE t.due_at<=? AND
                       (t.state='PENDING' OR (t.state='RUNNING' AND t.lease_until<=?))
                       ORDER BY CASE WHEN t.goal_rev=a.goal_rev THEN 0 ELSE 1 END,
                                t.due_at,t.created_at,t.task_id LIMIT 1""",
                         (now, now)).fetchone()
        if row is None:
            db.commit()
            return None
        token = uuid.uuid4().hex
        db.execute("""UPDATE tasks SET state='RUNNING',claim_token=?,lease_until=?,state_version=state_version+1
                    WHERE task_id=?""", (token, now+lease_seconds, row["task_id"]))
        event(db, row["task_id"], "CLAIMED", {"new_token": token, "prior_state": row["state"]})
        # Capture THIS claim's token/version while our IMMEDIATE write lock
        # still excludes competing lease owners. After COMMIT, an expired
        # lease can legitimately be taken over before this worker returns.
        # A post-commit SELECT would then hand the first worker the second
        # worker's claim token. Its original snapshot must never be replaced.
        claimed=dict(db.execute("SELECT * FROM tasks WHERE task_id=?",
                                (row["task_id"],)).fetchone())
        db.commit()
        return claimed
    except BaseException:
        db.rollback()
        raise



def renew_claim(db: sqlite3.Connection, task: dict, *, lease_seconds: int = 120) -> bool:
    """Extend ONLY this still-live worker claim, never revive expired claims.

    Used around bounded long local-model requests. Unlike a long initial
    lease, renewal preserves short crash recovery when no worker is alive.
    This method grants no capability and checks the original current
    goal/grant and still-enabled authorization under one write lock.
    """
    if (not isinstance(lease_seconds, int)
        or not 1 <= lease_seconds <= 180):
        raise ValueError("Lease renewal interval out of bounds")
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    try:
        updated = db.execute(
            """UPDATE tasks
               SET lease_until=?,state_version=state_version+1
               WHERE task_id=? AND claim_token=? AND state='RUNNING'
                 AND lease_until>?
                 AND EXISTS (
                     SELECT 1 FROM authority
                     WHERE singleton=1 AND goal_rev=? AND grant_rev=?
                       AND write_allowed=1
                 )""",
            (now + lease_seconds, task["task_id"], task["claim_token"], now,
             task["goal_rev"], task["grant_rev"]),
        ).rowcount
        db.commit()
        return updated == 1
    except BaseException:
        db.rollback()
        raise


def current_guard(db: sqlite3.Connection, task: dict, *, needs_write: bool) -> tuple[bool, str | None]:
    row = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
    if row["goal_rev"] != task["goal_rev"]:
        return False, "STALE_GOAL"
    if needs_write and (not row["write_allowed"] or row["grant_rev"] != task["grant_rev"]):
        return False, "WRITE_GRANT_REVOKED"
    return True, None


def finalize(db: sqlite3.Connection, task: dict, state: str, *, decision: str | None = None,
             artifact_writer=None, error_code: str | None = None,
             _committed_receipt: dict | None = None) -> bool:
    """Hold SQLite write lock over authorization and local file effect.

    A crash between file creation and DB commit is reconciled by O_EXCL + same-content
    readback on a later claim. Does NOT imply arbitrary remote exactly-once semantics.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task["task_id"],)).fetchone()
        if not row or row["claim_token"] != task["claim_token"] or row["state"] != "RUNNING":
            db.commit()
            return False
        ok, reason = current_guard(db, task, needs_write=artifact_writer is not None)
        artifact_hash = None
        if not ok:
            state, decision, error_code = "BLOCKED", None, reason
        elif artifact_writer is not None:
            artifact_hash = artifact_writer()
        db.execute("""UPDATE tasks SET state=?,decision=?,artifact_hash=?,error_code=?,lease_until=NULL,
                    claim_token=NULL,state_version=state_version+1 WHERE task_id=?""",
                   (state, decision, artifact_hash, error_code, task["task_id"]))
        event(db, task["task_id"], "FINALIZED", {"state": state, "decision": decision, "error_code": error_code})
        if state in ("VERIFIED", "NEEDS_REVIEW") and task["interval_seconds"]:
            current = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            new_task_id = uuid.uuid4().hex
            db.execute("""INSERT INTO tasks(task_id,state,state_version,goal_rev,grant_rev,due_at,
                interval_seconds,source_spec,created_at,parent_task) VALUES(?,'PENDING',0,?,?,?,?,?,?,?)""",
                (new_task_id, current["goal_rev"], current["grant_rev"], time.time()+task["interval_seconds"],
                 task["interval_seconds"], task["source_spec"], time.time(), task["task_id"]))
            event(db, new_task_id, "ENQUEUED", {"parent": task["task_id"]})
        db.commit()
        if _committed_receipt is not None:
            # These values are the very same values written under the
            # original IMMEDIATE lock, NOT a later observer's task row.
            # Populate only AFTER commit succeeds; never treat an
            # uncommitted write, failed CAS or artifact exception as proof.
            _committed_receipt.update({
                "status":state,"decision":decision,"reason":error_code
            })
        return True
    except BaseException:
        db.rollback()
        raise



def finalize_observed(db: sqlite3.Connection, task: dict, state: str, *,
                      decision: str | None = None, artifact_writer=None,
                      error_code: str | None = None) -> dict:
    """Report only the finalization actually committed by this lease owner.

    The caller's intended state is never evidence. Goal changes and grant
    revocation may convert a requested result to BLOCKED; lease takeover
    may reject finalization altogether. No read of an unrelated worker's
    mutable state is presented as our own successful task completion.
    """
    receipt={}
    committed=finalize(db,task,state,decision=decision,
                       artifact_writer=artifact_writer,error_code=error_code,
                       _committed_receipt=receipt)
    if not committed:
        return {"task_id":task["task_id"],"status":"STALE_WORKER"}
    # Only values captured by this worker's successful atomic finalize
    # belong in its response. A distinct reviewer can legitimately advance
    # the row as soon as our COMMIT releases the lock.
    if set(receipt)!={"status","decision","reason"}:
        raise RuntimeError("Committed finalize did not supply its result receipt")
    result={"task_id":task["task_id"],"status":receipt["status"]}
    if receipt["reason"] is not None:
        result["reason"]=receipt["reason"]
    if receipt["decision"] is not None:
        result["decision"]=receipt["decision"]
    return result


def alter_authority(db: sqlite3.Connection, *, revoke: bool = False, goal_change: bool = False) -> None:
    if revoke:
        db.execute("UPDATE authority SET write_allowed=0,grant_rev=grant_rev+1 WHERE singleton=1")
    if goal_change:
        db.execute("UPDATE authority SET goal_rev=goal_rev+1 WHERE singleton=1")
    db.commit()
