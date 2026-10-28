"""Public GitHub ref observer with a durable optimistic cursor, not a semantic agent.

Each observation becomes a *pinned immutable* evidence task in the same
SQLite transaction as the cursor advancement. No remote write or model call.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from .ledger import connect, create_task
from .source import (
    SourceUnavailable, git_blob_sha, github_public_branch_head,
    github_public_snapshot, _REPO_RE, _BRANCH_RE,
)

MIN_INTERVAL = 900  # At most 4 watches, 2 GitHub API reads per check: <=32/hour.
MAX_WATCHES = 4


def _validate(repo: str, path: str, branch: str, interval: int) -> None:
    if not _REPO_RE.fullmatch(repo) or not _BRANCH_RE.fullmatch(branch) or ".." in branch:
        raise ValueError("Invalid public repo or single-segment branch")
    if not path or path.startswith("/") or "\\" in path or ".." in Path(path).parts or "//" in path:
        raise ValueError("Invalid watched path")
    if not MIN_INTERVAL <= interval <= 86400:
        raise ValueError("Watch interval must be 900..86400 seconds; public API is rate-limited")


def initialize_watches(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS watch_sources (
      watch_id TEXT PRIMARY KEY,
      repo TEXT NOT NULL, path TEXT NOT NULL, branch TEXT NOT NULL,
      goal_rev INTEGER NOT NULL, grant_rev INTEGER NOT NULL,
      interval_seconds INTEGER NOT NULL, due_at REAL NOT NULL,
      baseline_ref TEXT, baseline_blob TEXT, cursor_epoch INTEGER NOT NULL DEFAULT 0,
      last_outcome TEXT, last_error TEXT, last_checked_at REAL, created_at REAL NOT NULL,
      UNIQUE(repo,path,branch)
    );
    CREATE TABLE IF NOT EXISTS watch_observations (
      observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
      watch_id TEXT NOT NULL, outcome TEXT NOT NULL,
      previous_ref TEXT, current_ref TEXT, content_blob TEXT,
      created_task TEXT, happened_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_watches_due ON watch_sources(due_at);
    """)


def create_watch(db: sqlite3.Connection, repo: str, path: str, branch: str = "main",
                 *, interval_seconds: int = 1800) -> str:
    _validate(repo, path, branch, interval_seconds)
    initialize_watches(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        authority = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if authority is None or not authority["write_allowed"]:
            raise PermissionError("Explicit write authority required before registering watcher")
        if db.execute("SELECT COUNT(*) FROM watch_sources").fetchone()[0] >= MAX_WATCHES:
            raise ValueError("Watch cap exceeded (free public GitHub rate budget)")
        watch_id = uuid.uuid4().hex
        db.execute("""INSERT INTO watch_sources
          (watch_id,repo,path,branch,goal_rev,grant_rev,interval_seconds,due_at,created_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (watch_id,repo,path,branch,authority["goal_rev"],authority["grant_rev"],
           interval_seconds,time.time(),time.time()))
        db.commit()
        return watch_id
    except BaseException:
        db.rollback()
        raise


def _authorized(db: sqlite3.Connection, watch: sqlite3.Row) -> bool:
    row = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
    return bool(row and row["goal_rev"] == watch["goal_rev"]
                and row["grant_rev"] == watch["grant_rev"] and row["write_allowed"])


def _audit(db: sqlite3.Connection, watch: sqlite3.Row, outcome: str,
           head: str | None, blob: str | None, task_id: str | None, now: float) -> None:
    db.execute("""INSERT INTO watch_observations
          (watch_id,outcome,previous_ref,current_ref,content_blob,created_task,happened_at)
          VALUES(?,?,?,?,?,?,?)""",
          (watch["watch_id"],outcome,watch["baseline_ref"],head,blob,task_id,now))


def observe_one(db_path: Path, watch_id: str, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    db = connect(db_path)
    try:
        # Host/tick initializes this schema before calling observe_one.
        prior = db.execute("SELECT * FROM watch_sources WHERE watch_id=?", (watch_id,)).fetchone()
        if prior is None or prior["due_at"] > now:
            return {"watch_id": watch_id, "status": "NOT_DUE"}
        if not _authorized(db, prior):
            return {"watch_id": watch_id, "status": "BLOCKED", "reason": "WATCH_AUTHORITY_REVOKED_OR_STALE"}
        head = blob = None
        failure = None
        try:
            head = github_public_branch_head(prior["repo"], prior["branch"])
            content = github_public_snapshot(prior["repo"], prior["path"], head)
            blob = git_blob_sha(content)
        except (SourceUnavailable, ValueError, OSError) as exc:
            failure = type(exc).__name__
        db.execute("BEGIN IMMEDIATE")
        try:
            current = db.execute("SELECT * FROM watch_sources WHERE watch_id=?", (watch_id,)).fetchone()
            if current is None or current["cursor_epoch"] != prior["cursor_epoch"] or current["due_at"] > now:
                db.commit()
                return {"watch_id": watch_id, "status": "STALE_OBSERVATION"}
            if not _authorized(db, current):
                db.commit()
                return {"watch_id":watch_id,"status":"BLOCKED","reason":"WATCH_AUTHORITY_REVOKED_OR_STALE"}
            if failure:
                outcome = "SOURCE_UNAVAILABLE"
                task_id = None
            elif current["baseline_ref"] is None:
                outcome = "BASELINED"
                task_id = None
            elif current["baseline_ref"] == head and current["baseline_blob"] != blob:
                outcome = "INTEGRITY_CONFLICT"
                task_id = None
                failure = "CONTENT_CHANGED_WITHOUT_COMMIT_CHANGE"
            elif current["baseline_blob"] == blob:
                outcome = "NO_CONTENT_CHANGE"
                task_id = None
            else:
                spec = {"kind":"github", "repo":current["repo"], "path":current["path"],
                        "old_ref":current["baseline_ref"], "new_ref":head}
                task_id = create_task(db, spec, commit=False)
                outcome = "TASK_ENQUEUED"
            if outcome not in ("SOURCE_UNAVAILABLE", "INTEGRITY_CONFLICT"):
                db.execute("""UPDATE watch_sources SET baseline_ref=?,baseline_blob=?,
                    cursor_epoch=cursor_epoch+1,last_outcome=?,last_error=NULL,
                    last_checked_at=?,due_at=? WHERE watch_id=?""",
                    (head,blob,outcome,now,now+current["interval_seconds"],watch_id))
            else:
                # Do not advance evidence cursor on errors; allow bounded retry on next due tick.
                db.execute("""UPDATE watch_sources SET cursor_epoch=cursor_epoch+1,
                    last_outcome=?,last_error=?,last_checked_at=?,due_at=? WHERE watch_id=?""",
                    (outcome,failure,now,now+current["interval_seconds"],watch_id))
            _audit(db, current, outcome, head, blob, task_id, now)
            db.commit()
            return {"watch_id":watch_id,"status":outcome,"current_ref":head,
                    "task_id":task_id, "semantic_outcome_verified":False}
        except BaseException:
            db.rollback()
            raise
    finally:
        db.close()


def poll_due_watches(db_path: Path, *, max_watches: int = MAX_WATCHES) -> list[dict]:
    if not 1 <= max_watches <= MAX_WATCHES:
        raise ValueError("Invalid watcher polling bound")
    db = connect(db_path)
    try:
        initialize_watches(db)
        now = time.time()
        ids = [r["watch_id"] for r in db.execute(
            "SELECT watch_id FROM watch_sources WHERE due_at <= ? ORDER BY due_at LIMIT ?",
            (now,max_watches))]
    finally:
        db.close()
    return [observe_one(db_path, watch_id) for watch_id in ids]
