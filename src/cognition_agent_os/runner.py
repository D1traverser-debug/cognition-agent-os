"""One bounded unit of work, not an always-on scheduler or real LLM agent."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from .ledger import claim_one, connect, current_guard, event, finalize, initialize
from .planner import propose
from .local_model import LocalModelUnavailable, propose_local
from .source import SourceUnavailable, get_pair


class ArtifactConflict(Exception):
    """Artifact for this intent already exists but differs: refuse overwrite."""


def _artifact_bytes(task: dict, proposal: dict) -> bytes:
    return (json.dumps({"task_id": task["task_id"], "goal_rev": task["goal_rev"],
                        "source": proposal["evidence"], "proposal": proposal,
                        "status": "PROPOSAL_NOT_APPROVED"},
                       ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def store_once(workspace: Path, task_id: str, data: bytes, *, crash_after_write: bool = False) -> str:
    """Local-only immutable intent file. Never follows symlink workspaces."""
    if len(task_id) != 32 or not all(c in "0123456789abcdef" for c in task_id):
        raise ValueError("Invalid task ID")
    if workspace.is_symlink():
        raise ValueError("Workspace may not be symlink")
    workspace.mkdir(parents=True, exist_ok=True)
    directory = workspace / "artifacts"
    if directory.is_symlink():
        raise ValueError("Artifacts dir may not be symlink")
    directory.mkdir(exist_ok=True)
    path = directory / (task_id + ".json")
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ArtifactConflict("Existing artifact differs from expected intent bytes")
    else:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        if crash_after_write:
            os._exit(79)  # Intentional test fault, not recoverable via Python exception.
    actual = path.read_bytes()
    if actual != data:
        raise ArtifactConflict("Artifact changed during independent readback")
    return hashlib.sha256(actual).hexdigest()


def verify_artifact(workspace: Path, task: dict) -> bool:
    """Verification is deterministic file readback only; not a semantic third-party oracle."""
    path = workspace / "artifacts" / (task["task_id"] + ".json")
    if not path.is_file() or path.is_symlink():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == task["artifact_hash"]


def run_once(db_path: Path, workspace: Path, fixture_root: Path, *, fail_at: str | None = None,
             force_lease_expire: bool = False, planner_mode: str = "deterministic",
             local_model: str | None = None) -> dict:
    db = connect(db_path)
    try:
        initialize(db)
        task = claim_one(db)
        if not task:
            return {"status": "IDLE"}
        if fail_at == "after_claim":
            os._exit(78)
        task_id = task["task_id"]
        ok, reason = current_guard(db, task, needs_write=False)
        if not ok:
            finalize(db, task, "BLOCKED", error_code=reason)
            return {"task_id": task_id, "status": "BLOCKED", "reason": reason}
        # A bounded declarative goal is processed by the same claim/grant ledger.
        # This never silently routes a goal through the protocol diff planner.
        try:
            source_spec = json.loads(task["source_spec"])
        except (ValueError, TypeError):
            finalize(db,task,"UNKNOWN",error_code="INVALID_TASK_SPEC")
            return {"task_id":task_id,"status":"UNKNOWN","reason":"INVALID_TASK_SPEC"}
        if not isinstance(source_spec,dict):
            finalize(db,task,"UNKNOWN",error_code="INVALID_TASK_SPEC")
            return {"task_id":task_id,"status":"UNKNOWN","reason":"INVALID_TASK_SPEC"}
        if source_spec.get("kind")=="pipeline_code_repair":
            if planner_mode!="deterministic":
                finalize(db,task,"UNKNOWN",error_code="PIPELINE_PLANNER_UNAVAILABLE")
                return {"task_id":task_id,"status":"UNKNOWN",
                        "reason":"PIPELINE_PLANNER_UNAVAILABLE"}
            from .pipeline_repair import run_pipeline_case
            return run_pipeline_case(db,task,workspace,fixture_root)
        if source_spec.get("kind")=="pure_code_repair":
            if planner_mode!="deterministic":
                finalize(db,task,"UNKNOWN",error_code="REPAIR_PLANNER_UNAVAILABLE")
                return {"task_id":task_id,"status":"UNKNOWN",
                        "reason":"REPAIR_PLANNER_UNAVAILABLE"}
            from .repair_search import run_repair_case
            return run_repair_case(db,task,workspace,fixture_root)
        if source_spec.get("kind")=="goal_intent":
            from .intent_runtime import run_intent
            return run_intent(db,task)
        if source_spec.get("kind")=="record_reconciliation":
            if planner_mode!="deterministic":
                finalize(db,task,"UNKNOWN",error_code="RECONCILIATION_PLANNER_NOT_AVAILABLE")
                return {"task_id":task_id,"status":"UNKNOWN","reason":"RECONCILIATION_PLANNER_NOT_AVAILABLE"}
            from .reconciliation import run_reconciliation
            return run_reconciliation(db,task,workspace,fixture_root)
        if source_spec.get("kind")=="goal_case":
            if planner_mode!="deterministic":
                finalize(db,task,"UNKNOWN",error_code="GOAL_PLANNER_NOT_AVAILABLE")
                return {"task_id":task_id,"status":"UNKNOWN","reason":"GOAL_PLANNER_NOT_AVAILABLE"}
            from .goal_loop import run_goal_case
            return run_goal_case(db,task,workspace,fixture_root,fail_at=fail_at)
        try:
            old, new, evidence = get_pair(source_spec, fixture_root)
            # Compare a second independent source read; no result on unstable observations.
            old_confirm, new_confirm, evidence_confirm = get_pair(json.loads(task["source_spec"]), fixture_root)
            if old != old_confirm or new != new_confirm or evidence != evidence_confirm:
                raise SourceUnavailable("Source changed during verification")
            if planner_mode == "deterministic":
                proposal = propose(old, new, evidence)
            elif planner_mode == "ollama-local":
                proposal = propose_local(old, new, evidence, model=local_model or "")
            else:
                raise ValueError("Unsupported planner mode")
        except LocalModelUnavailable as exc:
            finalize(db, task, "UNKNOWN", error_code="LOCAL_MODEL_UNAVAILABLE")
            return {"task_id": task_id, "status": "UNKNOWN", "reason": "LOCAL_MODEL_UNAVAILABLE", "diagnostic": type(exc).__name__}
        except (SourceUnavailable, FileNotFoundError, KeyError, ValueError, OSError) as exc:
            finalize(db, task, "UNKNOWN", error_code="SOURCE_UNAVAILABLE")
            return {"task_id": task_id, "status": "UNKNOWN", "reason": "SOURCE_UNAVAILABLE", "diagnostic": type(exc).__name__}
        if proposal["decision"] == "NO_CHANGE":
            finalize(db, task, "VERIFIED", decision="NO_CHANGE")
            return {"task_id": task_id, "status": "VERIFIED", "decision": "NO_CHANGE"}
        data = _artifact_bytes(task, proposal)
        try:
            committed = finalize(db, task, "NEEDS_REVIEW", decision=proposal["decision"],
                                 artifact_writer=lambda: store_once(workspace, task_id, data,
                                     crash_after_write=fail_at == "after_artifact_before_commit"))
        except (ArtifactConflict, ValueError, OSError):
            finalize(db, task, "UNKNOWN", error_code="ARTIFACT_CONFLICT")
            return {"task_id": task_id, "status": "UNKNOWN", "reason": "ARTIFACT_CONFLICT"}
        if not committed:
            return {"task_id": task_id, "status": "STALE_WORKER"}
        # The grant or goal may have changed after source fetch. The transaction's
        # authoritative state wins over the planner's pre-execution prediction.
        actual = db.execute("SELECT state,decision,error_code FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if actual["state"] != "NEEDS_REVIEW":
            return {"task_id": task_id, "status": actual["state"], "reason": actual["error_code"]}
        return {"task_id": task_id, "status": "NEEDS_REVIEW", "decision": actual["decision"],
                "artifact": f"artifacts/{task_id}.json", "semantic_review": "NOT_PERFORMED"}
    finally:
        db.close()
