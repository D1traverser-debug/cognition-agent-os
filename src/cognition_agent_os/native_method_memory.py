"""Cross-task method experience derived from freshly rechecked owner-local outcomes.

This is a read-only projection over the EXISTING task ledger. It creates no
controller, memory authority, trust root, task, or permission. A method family
is surfaced only after distinct owner goals, source bindings and result
artifacts have independently passed the existing local owner oracle.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .ledger import require_initialized_ledger, readonly_snapshot

_ID = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_MAX_SCAN = 64
_MIN_REPLICATES = 2
_MAX_EXAMPLES = 4

_OUTCOME_SCOPES = {
    ("compare_records", "ORIGINAL_NAMED_READONLY_COMPARISON_REPORT"),
    ("ensure_structure", "ORIGINAL_SANDBOX_DRAFT_POSTCONDITION"),
}
_ROLE_PATTERNS = {
    "compare_records": ["reference", "observed"],
    "ensure_structure": ["input"],
}
_METHOD_SUMMARIES = {
    "compare_records": (
        "Bind the owner's reference source before the observed source; "
        "compare original records read-only and independently recheck the report."
    ),
    "ensure_structure": (
        "Build an isolated draft from the original input; preserve existing "
        "content, add only owner-requested fields, and independently read back "
        "the sandbox result."
    ),
}


def _unavailable(reason: str) -> dict:
    return {
        "status": "METHOD_EXPERIENCE_UNAVAILABLE",
        "reason": reason,
        "methods": [],
        "authorizes_action": False,
        "business_outcome_verified": False,
        "real_external_outcome_verified": False,
    }


def inspect_replicated_local_methods(
    db_path: Path,
    workspace: Path,
    fixtures: Path,
    root_id: str,
    *,
    scan_limit: int = _MAX_SCAN,
) -> dict:
    """Recompute bounded cross-task patterns; never trust a cached promotion.

    Each example must pass both the native decision-lineage audit and the
    complete original-owner local postcondition oracle at read time. At least
    two distinct goal contracts, source bindings and result artifacts are
    required. Stale, revoked, malformed or unsupported roots are omitted.
    """
    if (
        not isinstance(root_id, str)
        or _ID.fullmatch(root_id) is None
        or type(scan_limit) is not int
        or not 1 <= scan_limit <= _MAX_SCAN
    ):
        return _unavailable("INVALID_METHOD_MEMORY_SCOPE")
    try:
        require_initialized_ledger(db_path)
        with readonly_snapshot(db_path) as db:
            current = db.execute(
                "SELECT parent_task,goal_rev,grant_rev,state FROM tasks "
                "WHERE task_id=?", (root_id,)
            ).fetchone()
            authority = db.execute(
                "SELECT goal_rev,grant_rev,write_allowed FROM authority "
                "WHERE singleton=1"
            ).fetchone()
            if (
                current is None
                or current["parent_task"] is not None
                or current["state"] != "DECOMPOSED"
                or authority is None
                or authority["write_allowed"] != 1
                or (current["goal_rev"], current["grant_rev"])
                != (authority["goal_rev"], authority["grant_rev"])
            ):
                return _unavailable("CURRENT_ROOT_OR_GRANT_UNVERIFIABLE")
            rows = db.execute(
                """
                SELECT t.task_id,t.source_spec
                FROM tasks AS t
                WHERE t.task_id<>?
                  AND t.parent_task IS NULL
                  AND t.state='DECOMPOSED'
                  AND t.goal_rev=?
                  AND t.grant_rev=?
                  AND json_valid(t.source_spec)
                  AND json_extract(t.source_spec,'$.kind')='native_goal'
                  AND EXISTS (
                    SELECT 1 FROM events AS e
                    WHERE e.task_id=t.task_id AND e.kind='NATIVE_GOAL_REGISTERED'
                  )
                  AND EXISTS (
                    SELECT 1 FROM events AS e
                    WHERE e.task_id=t.task_id AND e.kind='NATIVE_DECISION_ADMITTED'
                  )
                ORDER BY t.created_at DESC,t.task_id DESC
                LIMIT ?
                """,
                (root_id, current["goal_rev"], current["grant_rev"],
                 scan_limit + 1),
            ).fetchall()
        history_truncated = len(rows) > scan_limit
        candidates = rows[:scan_limit]
    except Exception:
        return _unavailable("LEDGER_SNAPSHOT_UNAVAILABLE")

    # Local imports keep the projection read-only and avoid import cycles.
    from .native_decision import inspect_native_goal
    current_audit = inspect_native_goal(
        db_path, workspace, fixtures, root_id
    )
    if current_audit.get("status") not in (
        "NATIVE_NEXT_DECISION_ADMISSIBLE",
        "NATIVE_AWAITING_WORKER",
        "NATIVE_DECISION_BUDGET_EXHAUSTED",
    ):
        return _unavailable("CURRENT_NATIVE_ROOT_NOT_ADMISSIBLE")
    from .owner_postcondition import (
        _explicit_owner_local_contract,
        inspect_owner_local_outcome,
    )

    grouped: dict[tuple[str, str], list[dict]] = {}
    checked = 0
    omitted_unverifiable = 0
    for row in candidates:
        try:
            spec = json.loads(row["source_spec"])
            if (
                not isinstance(spec, dict)
                or spec.get("kind") != "native_goal"
                or not isinstance(spec.get("goal"), str)
                or _explicit_owner_local_contract(spec["goal"]) is None
            ):
                continue
            state = inspect_native_goal(
                db_path, workspace, fixtures, row["task_id"]
            )
            if state.get("status") not in (
                "NATIVE_NEXT_DECISION_ADMISSIBLE",
                "NATIVE_DECISION_BUDGET_EXHAUSTED",
            ):
                omitted_unverifiable += 1
                continue
            decisions = state.get("decisions")
            if not isinstance(decisions, list) or not decisions:
                continue
            last = decisions[-1]
            objective = last.get("selected_objective")
            if objective not in ("compare_records", "ensure_structure"):
                continue
            owner = inspect_owner_local_outcome(
                db_path, workspace, fixtures, row["task_id"]
            )
            if (
                owner.get("local_owner_outcome_verified") is not True
                or owner.get("business_outcome_verified") is not False
                or owner.get("real_external_outcome_verified") is not False
                or owner.get("evidence_task_id") != last.get("task_id")
            ):
                continue
            scope = owner.get("outcome_scope")
            if (objective, scope) not in _OUTCOME_SCOPES:
                omitted_unverifiable += 1
                continue
            expected_mechanical = (
                "REPORT_MECHANICALLY_VERIFIED"
                if objective == "compare_records"
                else "CANDIDATE_MECHANICALLY_VALID"
            )
            expected_state = (
                "NEEDS_REVIEW" if objective == "compare_records"
                else "SANDBOX_VERIFIED"
            )
            if (
                last.get("mechanical_verdict") != expected_mechanical
                or last.get("task_state") != expected_state
            ):
                omitted_unverifiable += 1
                continue

            # Bind each sample to the exact typed inputs and their source
            # digests, not merely to an objective label or model rationale.
            with readonly_snapshot(db_path) as db:
                child = db.execute(
                    "SELECT source_spec FROM tasks WHERE task_id=?",
                    (owner["evidence_task_id"],),
                ).fetchone()
            if child is None:
                omitted_unverifiable += 1
                continue
            child_spec = json.loads(child["source_spec"])
            if objective == "compare_records":
                if (
                    child_spec.get("kind") != "record_reconciliation"
                    or not isinstance(child_spec.get("reference"), str)
                    or not isinstance(child_spec.get("observed"), str)
                ):
                    omitted_unverifiable += 1
                    continue
                required_paths = {
                    child_spec["reference"], child_spec["observed"]
                }
            else:
                if (
                    child_spec.get("kind") != "goal_case"
                    or not isinstance(child_spec.get("input"), str)
                ):
                    omitted_unverifiable += 1
                    continue
                required_paths = {child_spec["input"]}
            source_refs = last.get("research_trace", {}).get("source_refs", [])
            ref_map = {
                item.get("path"): item.get("sha256")
                for item in source_refs
                if isinstance(item, dict)
            }
            if (
                not required_paths.issubset(ref_map)
                or any(
                    not isinstance(ref_map[name], str)
                    or _SHA.fullmatch(ref_map[name]) is None
                    for name in required_paths
                )
            ):
                omitted_unverifiable += 1
                continue
            binding = {
                "child_source_spec": child_spec,
                "source_refs": [
                    {"path": name, "sha256": ref_map[name]}
                    for name in sorted(required_paths)
                ],
            }
            binding_sha = hashlib.sha256(json.dumps(
                binding, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")
            ).encode("utf-8")).hexdigest()

            goal_sha = hashlib.sha256(
                spec["goal"].encode("utf-8")
            ).hexdigest()
            evidence_sha = owner.get("evidence_sha256")
            if not isinstance(evidence_sha, str) or _SHA.fullmatch(evidence_sha) is None:
                omitted_unverifiable += 1
                continue
            alternative = last.get("alternative_objective")
            if alternative is not None and not isinstance(alternative, str):
                omitted_unverifiable += 1
                continue
            example = {
                "root_task_id": row["task_id"],
                "owner_goal_sha256": goal_sha,
                "source_binding_sha256": binding_sha,
                "selected_objective": objective,
                "alternative_objective": alternative,
                "outcome_scope": scope,
                "evidence_task_id": owner["evidence_task_id"],
                "evidence_sha256": evidence_sha,
                "source_role_pattern": _ROLE_PATTERNS[objective],
            }
            grouped.setdefault((objective, scope), []).append(example)
            checked += 1
        except Exception:
            # One damaged historical root cannot poison or authorize the
            # remaining independent roots.
            omitted_unverifiable += 1

    methods = []
    for (objective, scope), examples in sorted(grouped.items()):
        unique_goals = {item["owner_goal_sha256"] for item in examples}
        unique_bindings = {item["source_binding_sha256"] for item in examples}
        unique_evidence = {item["evidence_sha256"] for item in examples}
        if min(len(unique_goals), len(unique_bindings), len(unique_evidence)) < _MIN_REPLICATES:
            continue
        distinct = {}
        for item in examples:
            distinct.setdefault(item["owner_goal_sha256"], item)
        selected = sorted(
            distinct.values(),
            key=lambda item: (item["owner_goal_sha256"], item["root_task_id"]),
        )[:_MAX_EXAMPLES]
        methods.append({
            "method_key": objective + "|" + scope,
            "objective": objective,
            "outcome_scope": scope,
            "method_summary": _METHOD_SUMMARIES[objective],
            "source_role_pattern": _ROLE_PATTERNS[objective],
            "independent_owner_goal_count": len(unique_goals),
            "independent_source_binding_count": len(unique_bindings),
            "independent_result_artifact_count": len(unique_evidence),
            "minimum_independent_replicates_required": _MIN_REPLICATES,
            "examples": selected,
            "transfer_limit": (
                "Advisory only for the same registered local objective and "
                "outcome scope. Revalidate current sources and the complete "
                "current owner goal; never copy old file paths or infer business truth."
            ),
            "authorizes_action": False,
            "business_outcome_verified": False,
            "real_external_outcome_verified": False,
        })
    return {
        "status": (
            "REPLICATED_LOCAL_METHOD_EXPERIENCE"
            if methods else "NO_REPLICATED_LOCAL_METHOD_EXPERIENCE"
        ),
        "methods": methods,
        "candidate_roots_seen": len(candidates),
        "scan_limit": scan_limit,
        "history_scan_truncated": history_truncated,
        "independently_rechecked_roots": checked,
        "omitted_unverifiable_roots": omitted_unverifiable,
        "minimum_independent_replicates_required": _MIN_REPLICATES,
        "semantic_truth_verified": False,
        "authorizes_action": False,
        "business_outcome_verified": False,
        "real_external_outcome_verified": False,
    }
