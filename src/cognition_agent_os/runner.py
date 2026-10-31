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
from .source import SourceUnavailable, get_pair, safe_fixture
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


def read_audited_artifact(workspace: Path, task_id: str, audit: dict,
                          *, max_bytes: int) -> bytes:
    """Read only the exact bytes whose digest the independent audit accepted.

    Auditors and effect adapters use separate file reads. Reopening an artifact
    after a successful audit without comparing its bytes to the audited digest
    creates a time-of-check/time-of-use gap. Return the bounded, safe in-root
    snapshot only when it still has the exact audited identity.
    """
    if (not isinstance(task_id, str) or len(task_id) != 32
        or any(c not in "0123456789abcdef" for c in task_id)
        or not isinstance(audit, dict)
        or type(max_bytes) is not int or not 1 <= max_bytes <= 1024 * 1024):
        raise ArtifactConflict("INVALID_AUDITED_ARTIFACT_REQUEST")
    expected = audit.get("artifact_sha256")
    if (not isinstance(expected, str) or len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)):
        raise ArtifactConflict("AUDITED_ARTIFACT_IDENTITY_MISSING")
    relative = f"artifacts/{task_id}.json"
    path = workspace / relative
    if (workspace.is_symlink() or (workspace / "artifacts").is_symlink()
        or path.is_symlink()):
        raise ArtifactConflict("ARTIFACT_CHANGED_AFTER_AUDIT")
    try:
        raw = safe_fixture(workspace, relative)
    except (OSError, ValueError, SourceUnavailable) as exc:
        raise ArtifactConflict("ARTIFACT_CHANGED_AFTER_AUDIT") from exc
    if len(raw) > max_bytes or hashlib.sha256(raw).hexdigest() != expected:
        raise ArtifactConflict("ARTIFACT_CHANGED_AFTER_AUDIT")
    return raw


def run_once(db_path: Path, workspace: Path, fixture_root: Path, *, fail_at: str | None = None,
             force_lease_expire: bool = False, planner_mode: str = "deterministic",
             local_model: str | None = None, only_task_id: str | None = None) -> dict:
    # Direct invocation must obey the same explicit authority admission as host/CLI.
    require_initialized_ledger(db_path)
    db = connect(db_path)
    try:
        task = claim_one(db, only_task_id=only_task_id)
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
        if not check_child_dependency(
                db,task_id,fixture_root,workspace=workspace,db_path=db_path):
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
