"""A bounded Host-owned cognitive feedback step, not a second controller.

The original Host remains the only tick entry; the existing ledger, runner,
independent sandbox reviewer and native admission retain all grants and writes.
This extracts one decision/effect feedback seam so alternative cognition policies
can be evaluated without copying the Host or task authority.
"""
from __future__ import annotations

from pathlib import Path
from collections.abc import Callable


def drain_native_feedback(
    db_path: Path, workspace: Path, fixture_root: Path, *,
    max_jobs: int, planner_mode: str, local_model: str | None,
    auto_native_cognition: bool, auto_stage_goals: bool,
    preflight: dict | None, native_choices: list[dict],
    run_one: Callable, review_due: Callable,
    advance_cognition: Callable | None = None,
) -> tuple[list[dict], list[dict], int]:
    """Drain existing Worker tasks, then replan only from their verified result.

    No new ledger, scheduler, approval, independent verifier, or effect runner.
    The caller supplies the same already-authorized functions as the Host.
    A followed-up native admission cannot bypass the original Host tick budget.
    """
    if not 1 <= max_jobs <= 64:
        raise ValueError("INVALID_NATIVE_FEEDBACK_BUDGET")
    if not isinstance(native_choices, list):
        raise ValueError("INVALID_NATIVE_FEEDBACK_CHOICES")
    if auto_native_cognition and advance_cognition is None:
        from .native_local_planner import advance_native_adaptive_once
        advance_cognition = advance_native_adaptive_once
    results: list[dict] = []
    early_reviews: list[dict] = []
    review_budget = min(max_jobs, 8)
    for _ in range(max_jobs):
        result = run_one(
            db_path, workspace, fixture_root,
            planner_mode=planner_mode, local_model=local_model)
        if result["status"] == "IDLE":
            break
        results.append(result)
        if (auto_native_cognition and auto_stage_goals
            and preflight is not None and preflight["admitted"] and review_budget):
            observed_reviews = review_due(
                db_path, workspace, fixture_root, max_reviews=1)
            early_reviews.extend(observed_reviews)
            review_budget -= len(observed_reviews)
        if not auto_native_cognition or len(results) == max_jobs:
            continue
        # Only an effect of this tick's admitted child can request new planning;
        # unrelated completed tasks never trigger another model call.
        planned = {
            choice["child_task_id"]: choice
            for choice in native_choices
            if choice.get("status") == "NATIVE_METHOD_ENQUEUED"
        }
        selected = planned.get(result.get("task_id"))
        completed_ids = {item.get("task_id") for item in results}
        # Only same-root siblings can establish this local wait dependency.
        # A pending child belonging to an unrelated original goal has no
        # inferred causal relationship with this root, and must not starve it.
        if selected is None:
            continue
        selected_root = selected["root_task_id"]
        if any(
                child_id not in completed_ids
                for child_id, choice in planned.items()
                if choice["root_task_id"] == selected_root):
            continue
        # JSON ensure_structure produces a candidate NEEDS_REVIEW artifact;
        # owner completion depends on a separately opted-in sandbox stage.
        # Without that grant, another model attempt cannot supply the missing
        # effect, and would waste calls or create misleading new decisions.
        if (selected.get("selected_objective") == "ensure_structure"
            and result["status"] == "NEEDS_REVIEW"
            and not (auto_stage_goals and preflight is not None
                     and preflight["admitted"])):
            native_choices.append({
                "status": "NATIVE_SANDBOX_EFFECT_AWAITING_OPT_IN",
                "root_task_id": selected_root,
                "child_task_id": result.get("task_id"),
                "owner_outcome_verified": False,
                "reason": "SANDBOX_STAGING_NOT_AUTHORIZED",
            })
            continue
        followup = advance_cognition(
            db_path, workspace, fixture_root, selected["root_task_id"],
            model=local_model)
        native_choices.append(followup)
    return results, early_reviews, review_budget
