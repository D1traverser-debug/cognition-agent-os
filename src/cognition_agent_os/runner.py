"""One bounded unit of work, not an always-on scheduler or real LLM agent."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from .ledger import claim_one, connect, current_guard, event, finalize_observed, require_initialized_ledger, lineage_guard
from .planner import propose
from .local_model import LocalModelUnavailable, propose_local
from .source import SourceUnavailable, get_pair
from .isolated_filesystem import stage_immutable, ImmutableStageConflict


class ArtifactConflict(Exception):
    """Artifact for this intent already exists but differs: refuse overwrite."""


def _artifact_bytes(task: dict, proposal: dict) -> bytes:
    return (json.dumps({"task_id": task["task_id"], "goal_rev": task["goal_rev"],
                        "source": proposal["evidence"], "proposal": proposal,
                        "status": "PROPOSAL_NOT_APPROVED"},
                       ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def store_once(workspace: Path, task_id: str, data: bytes, *, crash_after_write: bool = False) -> str:
    """One immutable local artifact via the shared filesystem effect boundary."""
    if len(task_id) != 32 or not all(c in "0123456789abcdef" for c in task_id):
        raise ValueError("Invalid task ID")
    try:
        return stage_immutable(
            workspace, ("artifacts",), task_id + ".json", data,
            create_workspace=True, crash_after_write=crash_after_write)
    except ImmutableStageConflict as exc:
        raise ArtifactConflict(str(exc)) from exc


def verify_artifact(workspace: Path, task: dict) -> bool:
    """Verification is deterministic file readback only; not a semantic third-party oracle."""
    path = workspace / "artifacts" / (task["task_id"] + ".json")
    if not path.is_file() or path.is_symlink():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == task["artifact_hash"]


def run_once(db_path: Path, workspace: Path, fixture_root: Path, *, fail_at: str | None = None,
             force_lease_expire: bool = False, planner_mode: str = "deterministic",
             local_model: str | None = None) -> dict:
    # Direct invocation must obey the same explicit authority admission as host/CLI.
    require_initialized_ledger(db_path)
    db = connect(db_path)
    try:
        task = claim_one(db)
        if not task:
            return {"status": "IDLE"}
        if fail_at == "after_claim":
            os._exit(78)
        task_id = task["task_id"]
        ok, reason = current_guard(db, task, needs_write=False)
        if not ok:
            return finalize_observed(db,task,"BLOCKED",error_code=reason)
        # A bounded declarative goal is processed by the same claim/grant ledger.
        # This never silently routes a goal through the protocol diff planner.
        try:
            source_spec = json.loads(task["source_spec"])
        except (ValueError, TypeError):
            return finalize_observed(db,task,"UNKNOWN",error_code="INVALID_TASK_SPEC")
        if not isinstance(source_spec,dict):
            return finalize_observed(db,task,"UNKNOWN",error_code="INVALID_TASK_SPEC")
        # Every descendant inherits the entire owner goal's authority, not
        # just the status of its immediate parent. This is a read-only gate.
        if not lineage_guard(db, task):
            return finalize_observed(db, task, "BLOCKED",
                                     error_code="UPSTREAM_TASK_INVALID")
        # Evidence dependencies are stored in THIS authoritative ledger.
        # Check before dispatch to any executor, not merely during routing.
        from .knowledge_routing import check_child_dependency
        if not check_child_dependency(db,task_id,fixture_root):
            return finalize_observed(db,task,"UNKNOWN",
                                     error_code="KNOWLEDGE_SOURCE_CHANGED")
        # A released predecessor is NOT self-approval. Before any successor
        # executor dispatch, independently reread its original source/result.
        from .dependency_gate import dependency_admitted
        dependency_ok, dependency_reason = dependency_admitted(
            db,db_path,task,workspace,fixture_root)
        if not dependency_ok:
            blocked=dependency_reason in (
                "STALE_GOAL","WRITE_GRANT_REVOKED","UPSTREAM_TASK_INVALID")
            return finalize_observed(
                db,task,"BLOCKED" if blocked else "UNKNOWN",
                error_code=dependency_reason)
        from .capability_dispatch import CapabilityContext, dispatch_capability
        # One active task/claim/grant/lineage gate; domain adapters are
        # strictly registered and cannot choose a new authorization source.
        return dispatch_capability(CapabilityContext(
            db=db, task=task, db_path=db_path, workspace=workspace,
            fixtures=fixture_root, planner_mode=planner_mode,
            local_model=local_model, fail_at=fail_at), source_spec)
    finally:
        db.close()
