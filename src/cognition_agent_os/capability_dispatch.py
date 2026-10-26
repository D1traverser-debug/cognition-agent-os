"""Explicit, static capability boundary beneath the ONE SQLite task lifecycle.

The runner owns claim, lineage, grant and evidence dependency admission.
These adapters do not schedule, grant, or declare user-level success.
All module destinations are hard-coded; neither task text nor model output
can request arbitrary imports or bypass supported planner modes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import json

from .ledger import finalize_observed


@dataclass(frozen=True)
class CapabilityContext:
    db: sqlite3.Connection
    task: dict
    db_path: Path
    workspace: Path
    fixtures: Path
    planner_mode: str
    local_model: str | None
    fail_at: str | None


def _knowledge(c: CapabilityContext) -> dict:
    from .knowledge_routing import run_knowledge_intent
    return run_knowledge_intent(c.db, c.task, c.fixtures)


def _gap(c: CapabilityContext) -> dict:
    from .research_gap import run_research_gap
    return run_research_gap(c.db, c.task, c.workspace, c.fixtures)


def _assessment(c: CapabilityContext) -> dict:
    from .research_assessment import run_assessment
    return run_assessment(c.db, c.task, c.db_path, c.workspace, c.fixtures)


def _repo_repair(c: CapabilityContext) -> dict:
    from .repo_repair import run_repo_candidate
    return run_repo_candidate(c.db, c.task, c.workspace, c.fixtures,
                              planner_mode=c.planner_mode,
                              local_model=c.local_model)


def _pipeline(c: CapabilityContext) -> dict:
    from .pipeline_repair import run_pipeline_case
    return run_pipeline_case(c.db, c.task, c.workspace, c.fixtures)


def _pure_repair(c: CapabilityContext) -> dict:
    from .repair_search import run_repair_case
    return run_repair_case(c.db, c.task, c.workspace, c.fixtures)


def _investigate(c: CapabilityContext) -> dict:
    from .investigation import run_investigation
    return run_investigation(c.db, c.task, c.workspace, c.fixtures,
                             planner_mode=c.planner_mode,
                             local_model_name=c.local_model)


def _intent(c: CapabilityContext) -> dict:
    from .intent_runtime import run_intent
    return run_intent(c.db, c.task)


def _open_goal(c: CapabilityContext) -> dict:
    from .open_goal import run_open_goal
    return run_open_goal(c.db, c.task, c.fixtures,
                         planner_mode=c.planner_mode,
                         local_model_name=c.local_model)


def _domain_contract(c: CapabilityContext) -> dict:
    # Read-only, commit-pinned inspection of child-native adapter/manifests;
    # no extra controller, business task, grant or remote child write.
    from .domain_contract import run_domain_contract
    return run_domain_contract(c.db, c.task, c.workspace)


def _public_tool_discovery(c: CapabilityContext) -> dict:
    from .public_tool_discovery import run_public_discovery
    return run_public_discovery(c.db, c.task, c.workspace)


def _reconcile(c: CapabilityContext) -> dict:
    from .reconciliation import run_reconciliation
    return run_reconciliation(c.db, c.task, c.workspace, c.fixtures)


def _goal_case(c: CapabilityContext) -> dict:
    from .goal_loop import run_goal_case
    return run_goal_case(c.db, c.task, c.workspace, c.fixtures,
                         fail_at=c.fail_at)


def _snapshot_diff(c: CapabilityContext) -> dict:
    """Preserve the original fixture/GitHub comparison semantics."""
    # Preserve legacy runner's trusted interception seam during migration.
    # It is used by preexisting revocation/source-race tests; the new static
    # capability table does not alter authorization or grant semantics.
    from . import runner as legacy
    from .runner import ArtifactConflict, _artifact_bytes, store_once

    task = c.task
    tid = task["task_id"]
    try:
        spec = json.loads(task["source_spec"])
        old, new, evidence = legacy.get_pair(spec, c.fixtures)
        old_confirm, new_confirm, evidence_confirm = legacy.get_pair(
            json.loads(task["source_spec"]), c.fixtures)
        if old != old_confirm or new != new_confirm or evidence != evidence_confirm:
            raise legacy.SourceUnavailable("Source changed during verification")
        if c.planner_mode == "deterministic":
            proposal = legacy.propose(old, new, evidence)
        elif c.planner_mode == "ollama-local":
            proposal = legacy.propose_local(old, new, evidence,
                                     model=c.local_model or "")
        else:
            raise ValueError("Unsupported planner mode")
    except legacy.LocalModelUnavailable as exc:
        observed = finalize_observed(c.db, task, "UNKNOWN",
                                     error_code="LOCAL_MODEL_UNAVAILABLE")
        return ({**observed, "diagnostic": type(exc).__name__}
                if observed["status"] == "UNKNOWN" else observed)
    except (legacy.SourceUnavailable, FileNotFoundError, KeyError, ValueError, OSError) as exc:
        observed = finalize_observed(c.db, task, "UNKNOWN",
                                     error_code="SOURCE_UNAVAILABLE")
        return ({**observed, "diagnostic": type(exc).__name__}
                if observed["status"] == "UNKNOWN" else observed)
    if proposal["decision"] == "NO_CHANGE":
        return finalize_observed(c.db, task, "VERIFIED", decision="NO_CHANGE")
    data = _artifact_bytes(task, proposal)
    try:
        observed = finalize_observed(
            c.db, task, "NEEDS_REVIEW", decision=proposal["decision"],
            artifact_writer=lambda: store_once(
                c.workspace, tid, data,
                crash_after_write=c.fail_at == "after_artifact_before_commit"))
    except (ArtifactConflict, ValueError, OSError):
        return finalize_observed(c.db, task, "UNKNOWN",
                                 error_code="ARTIFACT_CONFLICT")
    if observed["status"] != "NEEDS_REVIEW":
        return observed
    return {**observed, "artifact": f"artifacts/{tid}.json",
            "semantic_review": "NOT_PERFORMED"}


# Static, reviewable trust boundary. No open plugin auto-discovery or eval.
_HANDLERS = {
    "knowledge_intent": _knowledge,
    "research_gap": _gap,
    "research_assessment": _assessment,
    "repo_container_repair": _repo_repair,
    "pipeline_code_repair": _pipeline,
    "pure_code_repair": _pure_repair,
    "investigate_goal": _investigate,
    "goal_intent": _intent,
    "open_goal": _open_goal,
    "public_tool_discovery": _public_tool_discovery,
    "domain_contract": _domain_contract,
    "record_reconciliation": _reconcile,
    "goal_case": _goal_case,
    "fixture": _snapshot_diff,
    "github": _snapshot_diff,
}

# Existing error codes are stable behavior, not an excuse to change an API.
_DETERMINISTIC_ONLY = {
    "pipeline_code_repair": "PIPELINE_PLANNER_UNAVAILABLE",
    "pure_code_repair": "REPAIR_PLANNER_UNAVAILABLE",
    "record_reconciliation": "RECONCILIATION_PLANNER_NOT_AVAILABLE",
    "goal_case": "GOAL_PLANNER_NOT_AVAILABLE",
}


def dispatch_capability(context: CapabilityContext, source_spec: dict) -> dict:
    """Run ONE pre-registered adapter, never infer capability from free text."""
    kind = source_spec.get("kind")
    if not isinstance(kind, str) or kind not in _HANDLERS:
        return finalize_observed(context.db, context.task, "UNKNOWN",
                                 error_code="INVALID_TASK_SPEC")
    if kind in _DETERMINISTIC_ONLY and context.planner_mode != "deterministic":
        # Natural-language interpretation needs an installed model; the
        # registered LOCAL method it selects is itself deterministic.
        # A typed task submitted directly in ollama-local mode still obeys
        # the original deterministic-only behavior. The runner has already
        # validated a full, pinned parent OPEN_GOAL_DECOMPOSED receipt.
        from_model_goal = False
        parent_id = context.task.get("parent_task")
        if parent_id is not None:
            from .knowledge_routing import check_child_dependency
            parent = context.db.execute(
                "SELECT source_spec FROM tasks WHERE task_id=?",
                (parent_id,)).fetchone()
            if parent:
                try:
                    parent_spec = json.loads(parent["source_spec"])
                    from_model_goal = (
                        isinstance(parent_spec, dict)
                        and parent_spec.get("kind") == "open_goal"
                        and check_child_dependency(
                            context.db, context.task["task_id"], context.fixtures))
                    if (isinstance(parent_spec, dict)
                        and parent_spec.get("kind") == "native_goal"):
                        from_model_goal = check_child_dependency(
                            context.db, context.task["task_id"], context.fixtures,
                            workspace=context.workspace, db_path=context.db_path)
                except (ValueError, TypeError, KeyError):
                    from_model_goal = False
        if not from_model_goal:
            return finalize_observed(context.db, context.task, "UNKNOWN",
                                     error_code=_DETERMINISTIC_ONLY[kind])
    return _HANDLERS[kind](context)
