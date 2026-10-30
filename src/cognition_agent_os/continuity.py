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

from .ledger import connect, readonly_snapshot
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
    "FEEDBACK_ACTIVE", "FEEDBACK_EVIDENCE_READY",
    "FEEDBACK_STOPPED", "FEEDBACK_UNVERIFIABLE",
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
    with readonly_snapshot(db_path) as probe:
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



def _all_open_goal_roots(db: sqlite3.Connection) -> list[sqlite3.Row] | None:
    """Recover current owner roots first; older versions are only fallback.

    Historical goal growth must not exhaust the current-version read budget.
    This read-only selector uses the SAME ledger authority and task rows.
    A genuinely excessive CURRENT root set still fails closed rather than
    choosing a recent goal or silently dropping a competing owner original.
    """
    authority = db.execute(
        "SELECT goal_rev FROM authority WHERE singleton=1").fetchone()
    if authority is None:
        return None
    version = authority["goal_rev"]

    def _matching_roots(predicate: str) -> list[sqlite3.Row] | None:
        roots = []
        for row in db.execute(
            "SELECT * FROM tasks WHERE parent_task IS NULL AND "
            + predicate + " ORDER BY created_at,task_id", (version,)
        ):
            try:
                source = json.loads(row["source_spec"])
            except (ValueError, TypeError):
                continue
            if (isinstance(source, dict)
                and source.get("kind") in ("open_goal", "native_goal")):
                roots.append(row)
                if len(roots) > 256:
                    return None
        return roots

    current = _matching_roots("goal_rev=?")
    if current is None or current:
        return current
    # Preserve stale-only diagnostics; do not re-admit old revisions.
    return _matching_roots("goal_rev<>?")


def _attested_owner_root(
        db: sqlite3.Connection, root: sqlite3.Row) -> dict | None:
    """Recover intact owner words across both existing goal types.

    This is a read-only identity projection, not a selectable runnable task.
    Native goal text must match its original immutable registration receipt.
    """
    try:
        spec = json.loads(root["source_spec"])
        if not isinstance(spec, dict):
            return None
        if spec.get("kind") == "open_goal":
            from .open_goal import validate_open_goal
            original = validate_open_goal(spec)["goal"]
        elif spec.get("kind") == "native_goal":
            from .native_decision import _registered_native_contract_matches
            if not _registered_native_contract_matches(
                    db, root["task_id"], spec):
                return None
            original = spec["goal"]
        else:
            return None
        return {"root_task_id": root["task_id"], "original_goal": original}
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def _lineage_root_id(db: sqlite3.Connection, task: sqlite3.Row) -> str | None:
    """Find the selected registered task's root, without minting authority."""
    seen = set()
    node = task
    for _ in range(513):
        if node["task_id"] in seen:
            return None
        seen.add(node["task_id"])
        if node["parent_task"] is None:
            return node["task_id"]
        node = db.execute(
            "SELECT task_id,parent_task FROM tasks WHERE task_id=?",
            (node["parent_task"],)).fetchone()
        if node is None:
            return None
    return None



def _resume_compound_owner_goal(
    db_path: Path, db: sqlite3.Connection, audit: dict, response: dict,
    workspace: Path, fixtures: Path, now: float,
) -> dict:
    """Cold-resume every admitted owner clause through independent evidence.

    Pure read-only projection. Worker still owns the final effect admission.
    """
    ids = audit.get("child_task_ids")
    clauses = audit.get("original_obligations")
    sequence = audit.get("sequence_rule")
    if (not isinstance(ids, list) or len(ids) != 2
        or len(set(ids)) != 2 or not isinstance(clauses, list)
        or len(clauses) != 2
        or sequence not in ("INDEPENDENT",
                            "AFTER_INDEPENDENT_RESEARCH_EVIDENCE")
        or any(not isinstance(x, dict) or
               set(x) != {"clause", "child_task_id"}
               for x in clauses)
        or [x["child_task_id"] for x in clauses] != ids):
        return {"status": "ORIGINAL_GOAL_LINEAGE_UNVERIFIABLE", **response,
                "reason": "COMPOUND_LINEAGE_UNRECOGNIZED"}
    children = db.execute(
        "SELECT * FROM tasks WHERE parent_task=?", (response["root_task_id"],)
    ).fetchall()
    by_id = {x["task_id"]: x for x in children}
    if (len(children) != 2 or set(by_id) != set(ids)
        or any((by_id[task_id]["goal_rev"], by_id[task_id]["grant_rev"])
               != (response["goal_rev"], response["grant_rev"])
               for task_id in ids)):
        return {"status": "ORIGINAL_GOAL_LINEAGE_UNVERIFIABLE", **response,
                "reason": "COMPOUND_CHILDREN_CHANGED"}
    response.update({
        "child_task_ids": ids,
        "sequence_rule": sequence,
        "original_obligation_progress": [{
            "owner_clause": obligation["clause"],
            "child_task_id": task_id,
            "task_state": by_id[task_id]["state"],
            "error_code": by_id[task_id]["error_code"],
            "owner_outcome_verified": False,
        } for task_id, obligation in zip(ids, clauses)],
    })
    ready, recoverable, pending_dependency, waiting = [], [], [], []
    for index, task_id in enumerate(ids):
        child = by_id[task_id]
        state = child["state"]
        if state == "PENDING":
            # Release timestamp is not independent proof. Recheck the same
            # current grant and predecessor oracle that the Worker uses.
            if index == 1 and sequence == "AFTER_INDEPENDENT_RESEARCH_EVIDENCE":
                from .dependency_gate import dependency_admitted
                allowed, reason = dependency_admitted(
                    db, db_path, dict(child), workspace, fixtures)
                if not allowed:
                    pending_dependency.append({
                        "task_id": task_id, "reason": reason})
                    continue
            if child["due_at"] <= now:
                ready.append(task_id)
            else:
                waiting.append(task_id)
        elif state == "RUNNING":
            if (child["lease_until"] is not None
                and child["lease_until"] <= now):
                recoverable.append(task_id)
            else:
                waiting.append(task_id)
    runnable = ready + recoverable
    response["runnable_task_ids"] = runnable
    response["waiting_dependency_tasks"] = pending_dependency
    if runnable:
        # Independent siblings remain visible; never pick a hidden winner.
        if len(runnable) == 1:
            response["next_task_id"] = runnable[0]
        else:
            response["next_task_ids"] = runnable
        return {"status": ("READY_TO_TICK" if ready else "READY_TO_RECOVER"),
                **response}
    if pending_dependency:
        return {"status": "AWAITING_DEPENDENCY_EVIDENCE", **response}
    if waiting:
        return {"status": "AWAITING_WORKER_OR_DUE_TIME", **response}
    return {"status": "REPLAN_OR_RESEARCH_OWNER_GAP", **response,
            "reason": "COMPOUND_OWNER_OUTCOME_NOT_VERIFIED"}


def _resume_existing_open_goal(db_path: Path, db: sqlite3.Connection,
                               authority: sqlite3.Row | None, *,
                               workspace: Path | None,
                               fixtures: Path | None) -> dict:
    """Recover original open_goal roots directly, not a hand-authored summary.

    No second queue, grant, registration or state mutation. Multiple current
    goals require explicit selection rather than silently using the latest.
    Exact original words come from the immutable ledger task source_spec.
    """
    from .open_goal import validate_open_goal, audit_open_goal
    from .owner_postcondition import inspect_owner_local_outcome

    roots = _all_open_goal_roots(db)
    if roots is None or authority is None:
        return _no_action("OWNER_GOAL_LEDGER_UNVERIFIABLE")
    if not roots:
        return _no_action("NO_DURABLE_GOAL")
    active = [r for r in roots if r["goal_rev"] == authority["goal_rev"]]
    if not active:
        return _no_action("STALE_GOAL_REVISION",
                          root_task_ids=[r["task_id"] for r in roots])
    if len(active) != 1:
        originals = [_attested_owner_root(db, r) for r in active]
        if any(x is None for x in originals):
            return _no_action("OWNER_GOAL_LEDGER_UNVERIFIABLE")
        return _no_action(
            "AMBIGUOUS_OPEN_OWNER_GOALS",
            root_task_ids=[r["task_id"] for r in active],
            original_goals=originals,
            authority_current=bool(authority["write_allowed"]))
    root = active[0]
    root_id = root["task_id"]
    try:
        raw_spec = json.loads(root["source_spec"])
    except (ValueError, TypeError):
        return _no_action("ORIGINAL_GOAL_UNVERIFIABLE", root_task_id=root_id)
    if isinstance(raw_spec, dict) and raw_spec.get("kind") == "native_goal":
        from .native_decision import inspect_native_goal
        if _attested_owner_root(db, root) is None:
            return _no_action("ORIGINAL_GOAL_UNVERIFIABLE", root_task_id=root_id)
        base = {
            "root_task_id": root_id, "original_goal": raw_spec["goal"],
            "original_contract_sha256": hashlib.sha256(
                root["source_spec"].encode("utf-8")).hexdigest(),
            "goal_rev": root["goal_rev"], "grant_rev": root["grant_rev"],
            "root_state": root["state"], "source_of_truth": "ORIGINAL_SQLITE_TASK",
            "local_owner_outcome_verified": False,
            "business_outcome_verified": False,
            "real_external_outcome_verified": False,
        }
        if (not authority["write_allowed"] or
            root["grant_rev"] != authority["grant_rev"]):
            return {"status": "AUTHORITY_REVOKED", **base,
                    "authority_current": False}
        if workspace is None or fixtures is None:
            return {"status": "SOURCE_AND_OUTCOME_READBACK_REQUIRED", **base}
        native = inspect_native_goal(db_path, workspace, fixtures, root_id)
        state = native["status"]
        status = {
            "NATIVE_NEXT_DECISION_ADMISSIBLE": "READY_FOR_NATIVE_DECISION",
            "NATIVE_AWAITING_WORKER": "AWAITING_WORKER",
            "NATIVE_DECISION_BUDGET_EXHAUSTED": "NEEDS_OWNER_OUTCOME_REVIEW",
        }.get(state, "REPLAN_OR_RECONCILE_ORIGINAL_GOAL")
        return {"status": status, **base,
                "authority_current": True, "native_decision_state": native,
                "native_next_action_authorized": (
                    state == "NATIVE_NEXT_DECISION_ADMISSIBLE")}
    try:
        original = validate_open_goal(raw_spec)
    except (ValueError, TypeError, KeyError):
        return _no_action("ORIGINAL_GOAL_UNVERIFIABLE", root_task_id=root_id)

    digest = hashlib.sha256(root["source_spec"].encode("utf-8")).hexdigest()
    response = {
        "root_task_id": root_id,
        "original_goal": original["goal"],
        "original_contract_sha256": digest,
        "goal_rev": root["goal_rev"],
        "grant_rev": root["grant_rev"],
        "root_state": root["state"],
        "authority_current": True,
        "source_of_truth": "ORIGINAL_SQLITE_TASK",
        "local_owner_outcome_verified": False,
        "business_outcome_verified": False,
        "real_external_outcome_verified": False,
        "unattended_business_completion_proven": False,
    }
    if (not authority["write_allowed"]
        or root["grant_rev"] != authority["grant_rev"]):
        # Read and execution grants are distinct. Revoke must not silently
        # destroy the owner's immutable goal identity or original words.
        # No next_task_id is emitted, and NO executable action is recovered.
        return {"status": "AUTHORITY_REVOKED", **response,
                "authority_current": False}
    now = time.time()
    if root["state"] in ("PENDING", "RUNNING"):
        if root["state"] == "PENDING":
            action = ("NOT_DUE" if root["due_at"] > now else "READY_TO_TICK")
        else:
            action = ("READY_TO_RECOVER" if root["lease_until"] is not None
                      and root["lease_until"] <= now else "AWAITING_WORKER")
        if action in ("READY_TO_TICK", "READY_TO_RECOVER"):
            response["next_task_id"] = root_id
        return {"status": action, **response}
    if root["state"] != "DECOMPOSED":
        return {"status": "REPLAN_OR_RECONCILE_ORIGINAL_GOAL", **response,
                "reason": "ROOT_NOT_ACTIVE_OR_COMPLETED"}

    if workspace is None or fixtures is None:
        return {"status": "SOURCE_AND_OUTCOME_READBACK_REQUIRED", **response}
    # Decomposition matters only if source pins, candidate compilation,
    # original root, exact child and grant replay successfully.
    audit = audit_open_goal(db_path, fixtures, root_id)
    if audit["status"] == "COMPOUND_METHODS_MECHANICALLY_GROUNDED":
        return _resume_compound_owner_goal(
            db_path, db, audit, response, workspace, fixtures, now)
    if audit["status"] != "METHOD_CANDIDATE_MECHANICALLY_GROUNDED":
        return {"status": "ORIGINAL_GOAL_LINEAGE_UNVERIFIABLE", **response,
                "reason": audit["status"]}
    child_id = audit["child_task_id"]
    child = db.execute(
        "SELECT * FROM tasks WHERE task_id=? AND parent_task=?",
        (child_id, root_id)
    ).fetchone()
    if child is None or (child["goal_rev"], child["grant_rev"]) != (
            root["goal_rev"], root["grant_rev"]):
        return {"status": "ORIGINAL_GOAL_LINEAGE_UNVERIFIABLE", **response}
    response.update({
        "child_task_id": child_id,
        "child_state": child["state"],
        "chosen_capability": audit["capability"],
    })
    outcome = inspect_owner_local_outcome(
        db_path, workspace, fixtures, root_id)
    response["local_outcome_evidence"] = {
        "status": outcome["status"],
        "reason": outcome.get("reason"),
        "outcome_scope": outcome.get("outcome_scope"),
        "evidence_sha256": outcome.get("evidence_sha256"),
    }
    if outcome["local_owner_outcome_verified"]:
        return {"status": "LOCAL_OWNER_RESULT_VERIFIED", **response,
                "local_owner_outcome_verified": True}
    # An unverified local child is not automatically a solved original goal.
    state = child["state"]
    if state in ("PENDING", "RUNNING"):
        action = ("NOT_DUE" if child["due_at"] > now else "READY_TO_TICK"
                  ) if state == "PENDING" else (
                    "READY_TO_RECOVER" if child["lease_until"] is not None
                    and child["lease_until"] <= now else "AWAITING_WORKER")
        if action in ("READY_TO_TICK", "READY_TO_RECOVER"):
            response["next_task_id"] = child_id
        return {"status": action, **response}
    return {"status": "REPLAN_OR_RESEARCH_OWNER_GAP", **response,
            "reason": outcome.get("reason") or "ORIGINAL_GOAL_NOT_PROVEN"}



def _resume_goal_local(db_path: Path, *,
                       workspace: Path | None = None,
                       fixtures: Path | None = None) -> dict:
    """No writes, no guessed goals, no implicit trust in a handoff file.

    When a GitHub branch is pinned, the head must be checked against a live
    resolver. Failure/branch drift returns no executable next-task pointer.
    """
    if not _db_exists(db_path):
        return _no_action("LEDGER_NOT_INITIALIZED")
    try:
        with readonly_snapshot(db_path) as db:
            authority = db.execute(
                "SELECT * FROM authority WHERE singleton=1").fetchone()
            table = db.execute("""SELECT 1 FROM sqlite_master
                 WHERE type='table' AND name='goal_continuity'""").fetchone()
            if authority is None:
                return _no_action("NO_DURABLE_GOAL")
            if not table:
                return _resume_existing_open_goal(
                    db_path, db, authority, workspace=workspace,
                    fixtures=fixtures)
            rows = db.execute(
                "SELECT * FROM goal_continuity ORDER BY goal_id").fetchall()
            if not rows:
                return _resume_existing_open_goal(
                    db_path, db, authority, workspace=workspace,
                    fixtures=fixtures)
            active = [r for r in rows
                      if r["goal_rev"] == authority["goal_rev"]]
            if not active:
                # An expired legacy registration cannot become an implicit
                # selector over a newer owner goal. Reuse the SAME canonical
                # task ledger's current-root recovery and authority checks;
                # historical rows remain intact, never reactivated.
                current = _resume_existing_open_goal(
                    db_path, db, authority, workspace=workspace,
                    fixtures=fixtures)
                if current["status"] not in (
                        "NO_DURABLE_GOAL", "STALE_GOAL_REVISION"):
                    return current
                return _no_action("STALE_GOAL_REVISION",
                                  goal_ids=[r["goal_id"] for r in rows])
            if len(active) != 1:
                # Every registered owner contract remains recoverable when
                # multiple goals compete. Returning only IDs silently drops
                # objective, acceptance and prohibitions on a cold start.
                # Validate EACH contract and its pinned task before exposing
                # those originals; no arbitrary newest-goal selection.
                registered = []
                registered_root_ids = set()
                for candidate in active:
                    raw_contract = candidate["contract"].encode("utf-8")
                    if (hashlib.sha256(raw_contract).hexdigest()
                            != candidate["contract_sha256"]):
                        return _no_action("INTEGRITY_CONFLICT")
                    try:
                        original = _validate(json.loads(raw_contract))
                    except (ValueError, TypeError, KeyError, OverflowError):
                        return _no_action("INTEGRITY_CONFLICT")
                    if original["goal_id"] != candidate["goal_id"]:
                        return _no_action("INTEGRITY_CONFLICT")
                    current_task = db.execute(
                        "SELECT * FROM tasks WHERE task_id=?",
                        (original["next_task_id"],)).fetchone()
                    if (current_task is None
                        or current_task["goal_rev"] != candidate["goal_rev"]
                        or current_task["grant_rev"] != candidate["grant_rev"]
                        or _task_fingerprint(current_task)
                            != candidate["task_spec_sha256"]):
                        return _no_action("TASK_LINEAGE_UNVERIFIABLE")
                    ancestor = _lineage_root_id(db, current_task)
                    if ancestor is None:
                        return _no_action("TASK_LINEAGE_UNVERIFIABLE")
                    registered_root_ids.add(ancestor)
                    registered.append({
                        "goal_id": original["goal_id"],
                        "objective": original["objective"],
                        "acceptance": original["acceptance"],
                        "constraints": original["constraints"],
                    })
                # Competing unregistered roots are still legitimate owner
                # goals. Do not let the >=2 registered-goal shortcut hide
                # them, and do not double-count an ancestor already selected
                # by a registered pointer.
                roots = _all_open_goal_roots(db)
                if roots is None:
                    return _no_action("OWNER_GOAL_LEDGER_UNVERIFIABLE")
                others = [
                    root for root in roots
                    if (root["goal_rev"] == authority["goal_rev"]
                        and root["task_id"] not in registered_root_ids)
                ]
                other_originals = [_attested_owner_root(db, root)
                                   for root in others]
                if any(item is None for item in other_originals):
                    return _no_action("OWNER_GOAL_LEDGER_UNVERIFIABLE")
                return _no_action(
                    "AMBIGUOUS_ACTIVE_GOALS",
                    goal_ids=[r["goal_id"] for r in active],
                    registered_goals=registered,
                    other_original_goals=other_originals,
                    authority_current=bool(authority["write_allowed"]))
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
            # A registered continuity pointer is not an implicit choice over
            # a DIFFERENT current owner open_goal. Otherwise a bare cold
            # "continue" silently loses another valid original objective.
            # An open_goal on this same task's ancestor chain is one goal,
            # not a competing one; no duplicate goal registry is introduced.
            open_roots = _all_open_goal_roots(db)
            selected_root = _lineage_root_id(db, task)
            if open_roots is None:
                return _no_action("OWNER_GOAL_LEDGER_UNVERIFIABLE")
            if selected_root is None:
                return _no_action("TASK_LINEAGE_UNVERIFIABLE",
                                  goal_id=row["goal_id"])
            other_roots = [
                r for r in open_roots
                if r["goal_rev"] == authority["goal_rev"]
                and r["task_id"] != selected_root
            ]
            if other_roots:
                originals = [_attested_owner_root(db, root)
                             for root in other_roots]
                if any(x is None for x in originals):
                    return _no_action("OWNER_GOAL_LEDGER_UNVERIFIABLE")
                return _no_action(
                    "AMBIGUOUS_DURABLE_GOALS",
                    goal_ids=[row["goal_id"]],
                    registered_goal={
                        "goal_id": row["goal_id"],
                        "objective": spec["objective"],
                        "acceptance": spec["acceptance"],
                        "constraints": spec["constraints"],
                    },
                    other_original_goals=originals,
                    authority_current=bool(
                        authority["write_allowed"]
                        and row["grant_rev"] == authority["grant_rev"]))
            if (not authority["write_allowed"]
                or row["grant_rev"] != authority["grant_rev"]):
                # Recover the authenticated goal CONTRACT on cold restart,
                # not its runnable task pointer. The grant stays revoked.
                return _no_action(
                    "AUTHORITY_REVOKED",
                    goal_id=row["goal_id"],
                    objective=spec["objective"],
                    acceptance=spec["acceptance"],
                    constraints=spec["constraints"],
                    task_state=task["state"],
                    contract_sha256=row["contract_sha256"],
                    checkpoint_version=row["checkpoint_version"],
                    authority_current=False)
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
                "FEEDBACK_ACTIVE": "READY_TO_TICK",
                "FEEDBACK_EVIDENCE_READY": "NEEDS_OWNER_OUTCOME_REVIEW",
                "FEEDBACK_STOPPED": "NEEDS_REPLAN",
                "FEEDBACK_UNVERIFIABLE": "NEEDS_REPLAN",
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
            # Private handoff only. The caller must check any pinned remote
            # source AFTER closing this SQLite snapshot, and reread authority.
            if spec["source"] is not None:
                result["_source_check"] = spec["source"]
            return result
    except (sqlite3.Error, OSError, UnicodeError):
        return _no_action("CONTINUITY_UNAVAILABLE")



def resume_goal(db_path: Path, *, resolve_head=None,
                workspace: Path | None = None,
                fixtures: Path | None = None) -> dict:
    """Resume under one local snapshot; do remote I/O with NO SQLite reader.

    A pinned GitHub HEAD is verified against the live provider, then the
    complete local goal/authority/root selection is observed AGAIN before
    returning a runnable hint. Neither the hint nor source SHA is an effect
    grant; the Worker admission boundary still repeats current CAS checks.
    """
    first = _resume_goal_local(db_path, workspace=workspace, fixtures=fixtures)
    pinned = first.pop("_source_check", None)
    if pinned is None:
        return first
    resolver = resolve_head or _public_branch_head
    try:
        live = resolver(pinned["repo"], pinned["branch"])
        source_valid = isinstance(live, str) and _SHA.fullmatch(live)
    except Exception:
        live = None
        source_valid = False

    # Re-read AFTER the remote call (and after the first snapshot is CLOSED).
    # This rejects revocation, new competing roots, checkpoint movement,
    # source replacement or task-state changes while network I/O ran.
    latest = _resume_goal_local(db_path, workspace=workspace, fixtures=fixtures)
    current = latest.pop("_source_check", None)
    if current is None:
        return latest
    if (current != pinned
        or first.get("contract_sha256") != latest.get("contract_sha256")
        or first.get("checkpoint_version") != latest.get("checkpoint_version")
        or first.get("goal_id") != latest.get("goal_id")):
        # Never export a stale next_task_id as a side effect of discovering
        # that the original contract changed while contacting a provider.
        return _no_action(
            "SOURCE_REVALIDATION_REQUIRED",
            goal_id=latest.get("goal_id"),
            objective=latest.get("objective"),
            acceptance=latest.get("acceptance"),
            constraints=latest.get("constraints"),
            contract_sha256=latest.get("contract_sha256"),
            checkpoint_version=latest.get("checkpoint_version"),
            authority_current=False)
    blocked_original = {
        "goal_id": latest["goal_id"],
        "objective": latest["objective"],
        "acceptance": latest["acceptance"],
        "constraints": latest["constraints"],
        "contract_sha256": latest["contract_sha256"],
        "checkpoint_version": latest["checkpoint_version"],
        "authority_current": True,
    }
    if not source_valid:
        return _no_action("SOURCE_UNAVAILABLE", **blocked_original)
    if live != current["head_sha"]:
        return _no_action(
            "SOURCE_REVALIDATION_REQUIRED", **blocked_original,
            pinned_head_sha=current["head_sha"], observed_head_sha=live)
    return latest
