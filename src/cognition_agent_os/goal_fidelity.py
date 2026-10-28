"""Domain-neutral owner-goal fidelity observation from the ONE task ledger.

This is intentionally NOT a semantic oracle, second planner or permission owner.
It catches objective-loss patterns that are mechanically observable and keeps
research, local evidence, and real owner result strictly distinct.
"""
from __future__ import annotations

import hashlib
import json


def check_goal_fidelity(root: dict, descendants: list[dict]) -> dict:
    """Classify real task lineage without guessing that a business goal passed.

    Non-current root details are observational evidence only. This function is
    pure and cannot create tasks, grant authority, or promote a method.
    """
    try:
        source = root["source_spec"]
        original = json.loads(source)
        if not isinstance(original, dict):
            raise ValueError("invalid root")
        root_kind = original.get("kind")
        if not isinstance(root_kind, str):
            raise ValueError("invalid root kind")
    except (ValueError, TypeError, KeyError):
        return {
            "root_contract_digest": None,
            "fidelity_state": "GOAL_IDENTITY_UNVERIFIABLE",
            "next_goal_action": "RECONCILE_ORIGINAL_OWNER_GOAL",
            "owner_outcome_verified": False,
        }
    anchor = hashlib.sha256(source.encode("utf-8")).hexdigest()
    statuses = {d["state"] for d in descendants}
    pending = bool(statuses & {"PENDING", "RUNNING"})
    # A repeated identical typed proposal is a warning, not sufficient proof
    # of drift: e.g. a legal retry might have a fresh, independently pinned
    # evidence revision. Never quarantine on this observation alone.
    specs = [d["source_spec"] for d in descendants]
    duplicate = len(specs) != len(set(specs))
    research = any(
        _kind(d) in ("investigate_goal", "public_tool_discovery")
        for d in descendants)
    research_only = bool(descendants) and all(
        _kind(d) in ("investigate_goal", "public_tool_discovery")
        for d in descendants)
    if duplicate and not pending:
        status, next_action = (
            "REPEATED_CANDIDATE_UNVERIFIED",
            "CHECK_NEW_EVIDENCE_BEFORE_REPEATING")
    elif pending:
        status, next_action = "LEGAL_WORK_PENDING", "CONTINUE_ADMITTED_WORK"
    elif root["state"] in ("BLOCKED", "UNKNOWN"):
        status, next_action = (
            "OWNER_GOAL_BLOCKED_WITHOUT_RESULT", "RESEARCH_OR_REPLAN_WITH_CURRENT_GRANT")
    elif root["state"] == "DECOMPOSED" and not descendants:
        status, next_action = "NO_ADMITTED_CHILD", "RECONCILE_PLAN_AND_LEDGER"
    elif research_only and root_kind == "open_goal":
        status, next_action = (
            "EVIDENCE_RESEARCH_ONLY_NOT_OWNER_RESULT",
            "COMPARE_SUPPORTED_METHODS_WITH_ORIGINAL_GOAL")
    elif root["state"] == "DECOMPOSED" and descendants:
        status, next_action = (
            "LOCAL_WORK_NOT_OWNER_RESULT",
            "VERIFY_OR_REPLAN_OWNER_POSTCONDITIONS")
    elif root["state"] in ("NEEDS_REVIEW", "SANDBOX_VERIFIED", "VERIFIED"):
        status, next_action = (
            "COMPONENT_RESULT_NOT_OWNER_RESULT",
            "VERIFY_OR_REPLAN_OWNER_POSTCONDITIONS")
    else:
        status, next_action = (
            "OWNER_OUTCOME_NOT_INDEPENDENTLY_ESTABLISHED",
            "CHECK_REAL_OWNER_POSTCONDITIONS")
    return {
        "root_contract_digest": anchor,
        "fidelity_state": status,
        "next_goal_action": next_action,
        "owner_outcome_verified": False,
        "repeated_source_spec_count": len(specs)-len(set(specs)),
        "research_only": research_only,
    }


def _kind(row: dict) -> str | None:
    try:
        spec = json.loads(row["source_spec"])
        return spec.get("kind") if isinstance(spec, dict) else None
    except (ValueError, TypeError, KeyError):
        return None
