"""Original OT06: recover an explicitly registered objective across cold starts.

One SQLite ledger remains the only task/authorization authority. A continuation
record is an immutable, digest-checked *goal description and pointer* to an
existing task, never a second runnable queue. Neither the current handoff
heading, model narration, nor the latest completed task may mint a new goal.
Resume is strictly read-only and never schedules or invokes an effect.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .ledger import connect
from .source import github_public_branch_head, github_public_branch_head_nested

_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_TASK = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_BRANCH = re.compile(r"[A-Za-z0-9_.\/-]{1,128}\Z")
_ALLOWED_STATES = {
    "PENDING", "RUNNING", "UNKNOWN", "BLOCKED", "NEEDS_REVIEW",
    "NEEDS_REPLAN", "RESEARCH_NEEDED", "VERIFIED", "DECOMPOSED",
    "CONTROL_ACTIVE", "CONTROL_UNVERIFIABLE", "CONTROL_STOPPED",
    "CONTROL_CANDIDATE_MATCHED", "STAGED", "REJECTED",
}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS goal_continuity (
  goal_id TEXT PRIMARY KEY,
  goal_rev INTEGER NOT NULL,
  grant_rev INTEGER NOT NULL,
  contract TEXT NOT NULL,
  contract_sha256 TEXT NOT NULL,
  task_spec_sha256 TEXT NOT NULL,
  checkpoint_version INTEGER NOT NULL,
  registered_at REAL NOT NULL
)
"""


def _canonical(spec: dict) -> bytes:
    return json.dumps(
        spec, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")


def _public_branch_head(repo: str, branch: str) -> str:
    # The original watcher contract remains single-segment-only.
    if "/" in branch:
        return github_public_branch_head_nested(repo, branch)
    return github_public_branch_head(repo, branch)


def _task_fingerprint(task: sqlite3.Row) -> str:
    """Bind the action bytes and parent linkage, never mutable task status."""
    frozen = {
        "task_id": task["task_id"],
        "source_spec": task["source_spec"],
        "parent_task": task["parent_task"],
        "goal_rev": task["goal_rev"],
        "grant_rev": task["grant_rev"],
        "created_at": task["created_at"],
    }
    return hashlib.sha256(_canonical(frozen)).hexdigest()


def _validate(spec: dict) -> dict:
    if not isinstance(spec, dict) or set(spec) != {
        "goal_id", "objective", "acceptance", "constraints",
        "next_task_id", "source"
    }:
        raise ValueError("INVALID_CONTINUITY_CONTRACT")
    goal_id = spec["goal_id"]
    if not isinstance(goal_id, str) or not _ID.fullmatch(goal_id):
        raise ValueError("INVALID_GOAL_ID")
    for field in ("objective", "acceptance"):
        item = spec[field]
        if not isinstance(item, str) or not 1 <= len(item) <= 2048:
            raise ValueError("INVALID_GOAL_FIELD")
    constraints = spec["constraints"]
    if (not isinstance(constraints, list) or not 1 <= len(constraints) <= 16
        or any(not isinstance(s, str) or not 1 <= len(s) <= 256
               for s in constraints)
        or len(set(constraints)) != len(constraints)):
        raise ValueError("INVALID_BOUNDARIES")
    if (not isinstance(spec["next_task_id"], str)
        or not _TASK.fullmatch(spec["next_task_id"])):
        raise ValueError("INVALID_TASK_ID")
    source = spec["source"]
    if source is not None:
        if not isinstance(source, dict) or set(source) != {
            "repo", "branch", "head_sha"
        }:
            raise ValueError("INVALID_SOURCE_REFERENCE")
        if (not isinstance(source["repo"], str)
            or not _REPO.fullmatch(source["repo"])
            or source["repo"].split("/")[0] in (".", "..")
            or source["repo"].split("/")[1] in (".", "..")
            or not isinstance(source["branch"], str)
            or not _BRANCH.fullmatch(source["branch"])
            or source["branch"].startswith("/")
            or source["branch"].endswith("/")
            or ".." in source["branch"]
            or "//" in source["branch"]
            or not isinstance(source["head_sha"], str)
            or not _SHA.fullmatch(source["head_sha"])):
            raise ValueError("UNSAFE_SOURCE_REFERENCE")
    if len(_canonical(spec)) > 8192:
        raise ValueError("CONTINUITY_CONTRACT_TOO_LARGE")
    return spec


def _db_exists(db_path: Path) -> bool:
    return db_path.is_file() and not db_path.is_symlink()


def _guard(db: sqlite3.Connection, spec: dict,
           authority: sqlite3.Row) -> sqlite3.Row:
    if not authority or not authority["write_allowed"]:
        raise PermissionError("NO_CURRENT_GRANT")
    task = db.execute("SELECT * FROM tasks WHERE task_id=?",
                      (spec["next_task_id"],)).fetchone()
    if task is None:
        raise ValueError("NO_REGISTERED_NEXT_TASK")
    if (task["goal_rev"] != authority["goal_rev"]
        or task["grant_rev"] != authority["grant_rev"]
        or task["state"] not in _ALLOWED_STATES):
        raise ValueError("STALE_OR_UNSUPPORTED_TASK")
    return task


def register_goal(db_path: Path, spec: dict) -> dict:
    """Explicit, single-writer registration; never implies owner approval."""
    _validate(spec)
    if not _db_exists(db_path):
        raise ValueError("LEDGER_NOT_INITIALIZED")
    raw = _canonical(spec)
    digest = hashlib.sha256(raw).hexdigest()
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            authority = db.execute(
                "SELECT * FROM authority WHERE singleton=1").fetchone()
            task = _guard(db, spec, authority)
            db.execute(_SCHEMA)
            if db.execute("SELECT 1 FROM goal_continuity WHERE goal_id=?",
                          (spec["goal_id"],)).fetchone():
                raise ValueError("GOAL_ALREADY_REGISTERED")
            db.execute("""INSERT INTO goal_continuity(
                goal_id, goal_rev, grant_rev, contract, contract_sha256,
                task_spec_sha256, checkpoint_version, registered_at)
                VALUES(?,?,?,?,?,?,0,?)""",
                (spec["goal_id"], authority["goal_rev"],
                 authority["grant_rev"], raw.decode("utf-8"),
                 digest, _task_fingerprint(task), time.time()))
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"status": "REGISTERED", "goal_id": spec["goal_id"],
            "contract_sha256": digest, "business_outcome_verified": False}


def checkpoint_goal(db_path: Path, goal_id: str, *,
                    expected_digest: str, next_task_id: str,
                    observed_head_sha: str | None = None,
                    resolve_head=None) -> dict:
    """CAS-update *only* an existing task pointer under the current grant.

    A checkpoint is an explicit permissioned transition, not a model deciding
    that a task or an unreviewed remote commit is now authoritative.
    """
    if (not isinstance(goal_id, str) or not _ID.fullmatch(goal_id)
        or not isinstance(expected_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
        or not isinstance(next_task_id, str)
        or not _TASK.fullmatch(next_task_id)
        or (observed_head_sha is not None and
            (not isinstance(observed_head_sha, str) or
             not _SHA.fullmatch(observed_head_sha)))
        or not _db_exists(db_path)):
        raise ValueError("INVALID_CHECKPOINT")
    # Public source resolution is network I/O. Do it strictly outside the
    # shared SQLite write transaction; a stale result can only be submitted
    # through the digest/version compare-and-set below. A subsequent resume
    # performs an independent fresh HEAD observation.
    uri = db_path.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as probe:
        probe.row_factory = sqlite3.Row
        observed_row = probe.execute(
            "SELECT * FROM goal_continuity WHERE goal_id=?", (goal_id,)).fetchone()
        observed_authority = probe.execute(
            "SELECT * FROM authority WHERE singleton=1").fetchone()
        if observed_row is None or observed_row["contract_sha256"] != expected_digest:
            raise ValueError("STALE_CHECKPOINT")
        if (not observed_authority or not observed_authority["write_allowed"]
            or observed_row["goal_rev"] != observed_authority["goal_rev"]
            or observed_row["grant_rev"] != observed_authority["grant_rev"]):
            raise PermissionError("CHECKPOINT_AUTHORITY_STALE")
        observed_contract = json.loads(observed_row["contract"])
        if hashlib.sha256(_canonical(_validate(observed_contract))).hexdigest() != expected_digest:
            raise ValueError("CHECKPOINT_INTEGRITY_BROKEN")
        observed_source = observed_contract["source"]
        if observed_head_sha is not None and observed_source is None:
            raise ValueError("NO_REMOTE_SOURCE_TO_REATTEST")
    if observed_source is not None:
        resolver = resolve_head or _public_branch_head
        try:
            live = resolver(observed_source["repo"], observed_source["branch"])
        except Exception as exc:
            raise ValueError("SOURCE_REVALIDATION_UNAVAILABLE") from exc
        if not isinstance(live, str) or not _SHA.fullmatch(live):
            raise ValueError("SOURCE_REVALIDATION_UNAVAILABLE")
        if live != (observed_head_sha or observed_source["head_sha"]):
            raise ValueError("SOURCE_REVALIDATION_REQUIRED")
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT * FROM goal_continuity WHERE goal_id=?",
                (goal_id,)).fetchone()
            authority = db.execute(
                "SELECT * FROM authority WHERE singleton=1").fetchone()
            if row is None or row["contract_sha256"] != expected_digest:
                raise ValueError("STALE_CHECKPOINT")
            if (not authority or not authority["write_allowed"]
                or row["goal_rev"] != authority["goal_rev"]
                or row["grant_rev"] != authority["grant_rev"]):
                raise PermissionError("CHECKPOINT_AUTHORITY_STALE")
            spec = json.loads(row["contract"])
            if hashlib.sha256(_canonical(_validate(spec))).hexdigest() != expected_digest:
                raise ValueError("CHECKPOINT_INTEGRITY_BROKEN")
            source = spec["source"]
            if source != observed_source:
                raise ValueError("SOURCE_REFERENCE_CHANGED")
            if observed_head_sha is not None:
                # A fresh public HEAD is a source observation, not an
                # independently accepted owner/business outcome.
                source["head_sha"] = observed_head_sha
            spec["next_task_id"] = next_task_id
            task = _guard(db, spec, authority)
            task_fingerprint = _task_fingerprint(task)
            raw = _canonical(spec)
            digest = hashlib.sha256(raw).hexdigest()
            if digest == expected_digest:
                raise ValueError("UNCHANGED_CHECKPOINT")
            updated = db.execute("""UPDATE goal_continuity
                SET contract=?, contract_sha256=?, task_spec_sha256=?,
                    checkpoint_version=checkpoint_version+1
                WHERE goal_id=? AND contract_sha256=?""",
                (raw.decode("utf-8"), digest, task_fingerprint,
                 goal_id, expected_digest))
            if updated.rowcount != 1:
                raise ValueError("CHECKPOINT_CAS_LOST")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"status": "CHECKPOINT_COMMITTED", "goal_id": goal_id,
            "contract_sha256": digest, "business_outcome_verified": False}


def _no_action(status: str, **extra: object) -> dict:
    return {"status": status, "business_outcome_verified": False, **extra}


def resume_goal(db_path: Path, *, resolve_head=None) -> dict:
    """No writes, no guessed goals, no implicit trust in a handoff file.

    When a GitHub branch is pinned, the head must be checked against a live
    resolver. Failure/branch drift returns no executable next-task pointer.
    """
    if not _db_exists(db_path):
        return _no_action("LEDGER_NOT_INITIALIZED")
    try:
        uri = db_path.resolve(strict=True).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            authority = db.execute(
                "SELECT * FROM authority WHERE singleton=1").fetchone()
            table = db.execute("""SELECT 1 FROM sqlite_master
                 WHERE type='table' AND name='goal_continuity'""").fetchone()
            if authority is None or not table:
                return _no_action("NO_DURABLE_GOAL")
            rows = db.execute(
                "SELECT * FROM goal_continuity ORDER BY goal_id").fetchall()
            if not rows:
                return _no_action("NO_DURABLE_GOAL")
            active = [r for r in rows
                      if r["goal_rev"] == authority["goal_rev"]]
            if not active:
                return _no_action("STALE_GOAL_REVISION",
                                  goal_ids=[r["goal_id"] for r in rows])
            if not authority["write_allowed"] or any(
                r["grant_rev"] != authority["grant_rev"] for r in active):
                return _no_action("AUTHORITY_REVOKED")
            if len(active) != 1:
                return _no_action(
                    "AMBIGUOUS_ACTIVE_GOALS",
                    goal_ids=[r["goal_id"] for r in active])
            row = active[0]
            raw = row["contract"].encode("utf-8")
            if hashlib.sha256(raw).hexdigest() != row["contract_sha256"]:
                return _no_action("INTEGRITY_CONFLICT")
            try:
                spec = _validate(json.loads(raw))
            except (ValueError, TypeError, KeyError, OverflowError):
                return _no_action("INTEGRITY_CONFLICT")
            if spec["goal_id"] != row["goal_id"]:
                return _no_action("INTEGRITY_CONFLICT")
            task = db.execute(
                "SELECT * FROM tasks WHERE task_id=?",
                (spec["next_task_id"],)).fetchone()
            if (task is None or task["goal_rev"] != row["goal_rev"]
                or task["grant_rev"] != row["grant_rev"]
                or _task_fingerprint(task) != row["task_spec_sha256"]):
                return _no_action("TASK_LINEAGE_UNVERIFIABLE",
                                  goal_id=row["goal_id"])
            if spec["source"] is not None:
                src = spec["source"]
                resolver = resolve_head or _public_branch_head
                try:
                    observed = resolver(src["repo"], src["branch"])
                    if not isinstance(observed, str) or not _SHA.fullmatch(observed):
                        return _no_action("SOURCE_UNAVAILABLE",
                                          goal_id=row["goal_id"])
                except Exception:
                    return _no_action("SOURCE_UNAVAILABLE",
                                      goal_id=row["goal_id"])
                if observed != src["head_sha"]:
                    return _no_action(
                        "SOURCE_REVALIDATION_REQUIRED", goal_id=row["goal_id"],
                        pinned_head_sha=src["head_sha"],
                        observed_head_sha=observed)
            state = task["state"]
            next_action = {
                "PENDING": ("NOT_DUE" if task["due_at"] > time.time()
                            else "READY_TO_TICK"),
                "CONTROL_ACTIVE": "READY_TO_TICK",
                "RUNNING": ("READY_TO_RECOVER" if
                    task["lease_until"] is not None
                    and task["lease_until"] <= time.time()
                    else "AWAITING_WORKER"),
                "NEEDS_REVIEW": "NEEDS_INDEPENDENT_REVIEW",
                "VERIFIED": "NEEDS_OWNER_OUTCOME_REVIEW",
                "CONTROL_CANDIDATE_MATCHED": "NEEDS_OWNER_OUTCOME_REVIEW",
                "UNKNOWN": "NEEDS_REPLAN",
                "BLOCKED": "BLOCKED",
                "NEEDS_REPLAN": "NEEDS_REPLAN",
                "RESEARCH_NEEDED": "NEEDS_RESEARCH_REVIEW",
                "CONTROL_UNVERIFIABLE": "NEEDS_REPLAN",
                "CONTROL_STOPPED": "NEEDS_REPLAN",
            }.get(state, "NEEDS_RECONCILIATION")
            result = _no_action(
                next_action, goal_id=row["goal_id"],
                objective=spec["objective"],
                acceptance=spec["acceptance"],
                constraints=spec["constraints"],
                task_state=state,
                contract_sha256=row["contract_sha256"],
                checkpoint_version=row["checkpoint_version"])
            if next_action in ("READY_TO_TICK", "READY_TO_RECOVER"):
                result["next_task_id"] = spec["next_task_id"]
            else:
                result["task_id_for_review"] = spec["next_task_id"]
            return result
    except (sqlite3.Error, OSError, UnicodeError):
        return _no_action("CONTINUITY_UNAVAILABLE")
