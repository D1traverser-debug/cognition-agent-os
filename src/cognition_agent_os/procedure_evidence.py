"""Read-only cross-root procedure trial evidence derived from the ONE ledger.

A prior procedure family is surfaced only after its original owner-local
postcondition is independently re-read from current source and output bytes.
This is evidence for a new planner to challenge, not a method promotion,
semantic truth, grant, or execution capability. No new table or scheduler.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .ledger import readonly_snapshot

_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_ROOT_SCAN = 64
_MAX_TRIALS = 8
_MAX_PER_OBJECTIVE = 3
# Only deterministic, capability-specific refusals are surfaced as
# counterexamples. Infrastructure/verifier failures remain inconclusive.
_OBSERVED_FAILURE_CODES = {
    "compare_records": frozenset({"JOIN_KEY_AMBIGUOUS"}),
    "ensure_structure": frozenset({"NO_SAFE_GOAL_PLAN"}),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def procedure_evidence_sha256(evidence: dict) -> str:
    """Fingerprint the exact read-only cross-root projection shown to a planner."""
    if not isinstance(evidence, dict):
        raise ValueError("INVALID_PROCEDURE_EVIDENCE")
    raw = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _procedure_identity(intent: dict) -> dict:
    """Fingerprint the registered procedure family, excluding task bindings."""
    from .intent_planner import compile_intent

    plan = compile_intent(intent)
    steps = []
    for step in plan["steps"]:
        steps.append({key: value for key, value in step.items()
                      if key != "resources"})
    identity = {
        "schema_version": plan["schema_version"],
        "objective": plan["objective"],
        "capability": plan["capability"],
        "steps": steps,
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return {
        "objective": plan["objective"],
        "capability": plan["capability"],
        "procedure_fingerprint": hashlib.sha256(raw).hexdigest(),
    }


def inspect_cross_root_procedure_trials(
        db_path: Path, workspace: Path, fixtures: Path, root_task_id: str,
        *, eligible_objectives: tuple[str, ...] | list[str],
        limit: int = _MAX_TRIALS) -> dict:
    """Return bounded, currently revalidated procedure-family trials.

    A source root contributes only when:
    - it is a different registered native root with a different owner-goal hash;
    - it is under the same current SQLite goal/grant revision;
    - its complete owner-local postcondition is independently verified now;
    - the verified outcome is bound to its last admitted, registered intent.

    The projection is recomputed on every call. Changed sources, artifacts,
    owner grants or root lineage therefore remove the old trial instead of
    silently preserving a stale method endorsement.
    """
    if (not isinstance(root_task_id, str) or not _ID.fullmatch(root_task_id)
        or not isinstance(eligible_objectives, (tuple, list))
        or not 1 <= len(eligible_objectives) <= 4
        or any(not isinstance(x, str) for x in eligible_objectives)
        or len(set(eligible_objectives)) != len(eligible_objectives)
        or type(limit) is not int or not 1 <= limit <= _MAX_TRIALS
        or not db_path.is_file() or db_path.is_symlink()):
        return {"status": "PROCEDURE_TRIAL_INPUT_INVALID", "items": [],
                "authorizes_action": False}

    from .native_decision import inspect_native_goal
    from .owner_postcondition import (
        inspect_owner_local_outcome, _explicit_owner_local_contract)

    current = inspect_native_goal(db_path, workspace, fixtures, root_task_id)
    if (current.get("status") != "NATIVE_NEXT_DECISION_ADMISSIBLE"
        or not isinstance(current.get("original_goal"), str)):
        return {"status": "PROCEDURE_TRIAL_CURRENT_ROOT_NOT_ADMISSIBLE",
                "items": [], "authorizes_action": False}

    current_goal_sha256 = _sha(current["original_goal"])
    exact = _explicit_owner_local_contract(current["original_goal"])
    allowed = set(eligible_objectives)
    if exact is not None:
        allowed.intersection_update({exact["objective"]})
    if not allowed:
        return {"status": "NO_APPLICABLE_PROCEDURE_TRIALS", "items": [],
                "authorizes_action": False}

    with readonly_snapshot(db_path) as db:
        authority = db.execute(
            "SELECT goal_rev,grant_rev,write_allowed FROM authority "
            "WHERE singleton=1").fetchone()
        root = db.execute(
            "SELECT goal_rev,grant_rev,state,parent_task FROM tasks "
            "WHERE task_id=?", (root_task_id,)).fetchone()
        if (authority is None or root is None or root["parent_task"] is not None
            or root["state"] != "DECOMPOSED"
            or authority["write_allowed"] != 1
            or (root["goal_rev"], root["grant_rev"]) !=
               (authority["goal_rev"], authority["grant_rev"])):
            return {"status": "PROCEDURE_TRIAL_CURRENT_GRANT_UNAVAILABLE",
                    "items": [], "authorizes_action": False}
        rows = db.execute(
            "SELECT task_id,created_at FROM tasks "
            "WHERE parent_task IS NULL AND state='DECOMPOSED' "
            "AND goal_rev=? AND grant_rev=? AND task_id<>? "
            "AND json_valid(source_spec) "
            "AND json_extract(source_spec,'$.kind')='native_goal' "
            "AND task_id IN (SELECT task_id FROM events "
            "WHERE kind='NATIVE_GOAL_REGISTERED') "
            "ORDER BY created_at DESC,task_id DESC LIMIT ?",
            (authority["goal_rev"], authority["grant_rev"], root_task_id,
             _MAX_ROOT_SCAN + 1)).fetchall()
        candidate_ids = [row["task_id"] for row in rows[:_MAX_ROOT_SCAN]]
        scan_truncated = len(rows) > _MAX_ROOT_SCAN
        starting_authority = (
            authority["goal_rev"], authority["grant_rev"],
            authority["write_allowed"])
        starting_root = (root["goal_rev"], root["grant_rev"], root["state"])

    items = []
    per_objective = {}
    failure_items = []
    failure_per_objective = {}
    failure_snapshots = {}
    for candidate_id in candidate_ids:
        try:
            prior = inspect_native_goal(
                db_path, workspace, fixtures, candidate_id)
            if (prior.get("status") != "NATIVE_NEXT_DECISION_ADMISSIBLE"
                or not isinstance(prior.get("original_goal"), str)
                or _sha(prior["original_goal"]) == current_goal_sha256
                or not prior.get("decisions")):
                continue
            prior_goal_sha256 = _sha(prior["original_goal"])
            prior_observation_sha256 = prior.get("observation_sha256")
            if (not isinstance(prior_observation_sha256, str)
                or not re.fullmatch(r"[a-f0-9]{64}", prior_observation_sha256)):
                continue
            with readonly_snapshot(db_path) as db:
                events = db.execute(
                    "SELECT event_id,details FROM events WHERE task_id=? "
                    "AND kind='NATIVE_DECISION_ADMITTED' ORDER BY event_id",
                    (candidate_id,)).fetchall()
            if len(events) != len(prior["decisions"]):
                continue
            receipts = {
                row["event_id"]: json.loads(row["details"])
                for row in events
            }

            # Preserve narrowly classified, real Worker refusals as
            # counterexamples even when a later decision in the same root
            # corrected the task. These are execution observations, not
            # independent owner outcomes or causal/root-cause verdicts.
            for attempt in prior["decisions"]:
                objective = attempt.get("selected_objective")
                failure_code = attempt.get("error_code")
                if (objective not in allowed
                    or attempt.get("task_state") != "UNKNOWN"
                    or failure_code not in _OBSERVED_FAILURE_CODES.get(
                        objective, frozenset())
                    or len(failure_items) >= limit
                    or failure_per_objective.get(
                        objective, 0) >= _MAX_PER_OBJECTIVE):
                    continue
                receipt = receipts.get(attempt.get("event_id"))
                if (not isinstance(receipt, dict)
                    or receipt.get("child_task_id") != attempt.get("task_id")):
                    continue
                proposal = receipt.get("proposal")
                if (not isinstance(proposal, dict)
                    or not isinstance(proposal.get("selected_intent"), dict)):
                    continue
                selected_intent = proposal["selected_intent"]
                identity = _procedure_identity(selected_intent)
                if identity["objective"] != objective:
                    continue
                resources = selected_intent.get("resources")
                pinned_sources = receipt.get("source_sha256")
                if not isinstance(resources, list) or not isinstance(
                        pinned_sources, dict):
                    continue
                source_refs = []
                refs_valid = True
                for resource in resources:
                    if (not isinstance(resource, dict)
                        or not isinstance(resource.get("role"), str)
                        or not isinstance(resource.get("path"), str)):
                        refs_valid = False
                        break
                    path = resource["path"]
                    digest = pinned_sources.get(path)
                    if (not isinstance(digest, str)
                        or not re.fullmatch(r"[a-f0-9]{64}", digest)):
                        refs_valid = False
                        break
                    source_refs.append({
                        "role": resource["role"], "path": path,
                        "sha256": digest,
                    })
                if not refs_valid:
                    continue
                source_refs.sort(key=lambda item: (item["role"], item["path"]))
                trace = attempt.get("research_trace")
                trace = trace if isinstance(trace, dict) else {}
                prior_decision_context = {}
                for key in (
                    "selected_reason", "alternative_reason", "expected_evidence",
                    "challenge", "falsifier", "uncertainty",
                ):
                    value = trace.get(key)
                    if isinstance(value, str) and value.strip():
                        prior_decision_context[key] = value[:512]
                failure_items.append({
                    "source_root_id": candidate_id,
                    "source_goal_sha256": prior_goal_sha256,
                    "source_observation_sha256": prior_observation_sha256,
                    "decision_event_id": attempt["event_id"],
                    "evidence_task_id": attempt["task_id"],
                    "objective": objective,
                    "capability": identity["capability"],
                    "procedure_fingerprint": identity["procedure_fingerprint"],
                    "source_refs": source_refs,
                    "prior_decision_context": prior_decision_context,
                    "prior_decision_context_semantics":
                        "UNTRUSTED_MODEL_HYPOTHESES_NOT_CAUSAL_EVIDENCE",
                    "worker_error_code": failure_code,
                    "task_state": "UNKNOWN",
                    "trial_status": "PRIOR_WORKER_REFUSAL_OBSERVED",
                    "failure_semantics":
                        "OBSERVED_WORKER_REFUSAL_NOT_CAUSAL_PROOF",
                    "same_registered_procedure_family": True,
                    "applicability_to_current_goal": "NOT_YET_TESTED",
                    "owner_outcome_verified": False,
                    "root_cause_semantically_verified": False,
                    "authorizes_action": False,
                    "business_outcome_verified": False,
                })
                failure_per_objective[objective] = (
                    failure_per_objective.get(objective, 0) + 1)
                failure_snapshots[candidate_id] = prior_observation_sha256

            # Positive trials require the complete original owner-local
            # postcondition to be independently re-read from current bytes.
            outcome = inspect_owner_local_outcome(
                db_path, workspace, fixtures, candidate_id)
            if (outcome.get("status") != "LOCAL_OWNER_RESULT_VERIFIED"
                or outcome.get("local_owner_outcome_verified") is not True
                or outcome.get("business_outcome_verified") is not False
                or outcome.get("real_external_outcome_verified") is not False):
                continue
            last = prior["decisions"][-1]
            if last.get("task_id") != outcome.get("evidence_task_id"):
                continue
            receipt = receipts.get(last.get("event_id"))
            if not isinstance(receipt, dict):
                continue
            proposal = receipt.get("proposal")
            if (not isinstance(proposal, dict)
                or receipt.get("child_task_id") != outcome["evidence_task_id"]
                or not isinstance(proposal.get("selected_intent"), dict)):
                continue
            identity = _procedure_identity(proposal["selected_intent"])
            objective = identity["objective"]
            if objective not in allowed:
                continue
            count = per_objective.get(objective, 0)
            if count >= _MAX_PER_OBJECTIVE or len(items) >= limit:
                continue
            item = {
                "source_root_id": candidate_id,
                "source_goal_sha256": prior_goal_sha256,
                "source_observation_sha256": prior_observation_sha256,
                "objective": objective,
                "capability": identity["capability"],
                "procedure_fingerprint": identity["procedure_fingerprint"],
                "outcome_scope": outcome["outcome_scope"],
                "evidence_task_id": outcome["evidence_task_id"],
                "evidence_sha256": outcome["evidence_sha256"],
                "trial_status": "PRIOR_ROOT_LOCAL_OWNER_OUTCOME_VERIFIED",
                "same_registered_procedure_family": True,
                "applicability_to_current_goal": "NOT_YET_TESTED",
                "authorizes_action": False,
                "business_outcome_verified": False,
            }
            items.append(item)
            per_objective[objective] = count + 1
            if len(items) >= limit and len(failure_items) >= limit:
                break
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            # One malformed or stale historical root cannot suppress others.
            continue

    # Recheck the current grant and every surfaced positive receipt after the
    # scan. A source/output mutation during the scan must not survive as a
    # fresh transfer hint.
    with readonly_snapshot(db_path) as db:
        authority = db.execute(
            "SELECT goal_rev,grant_rev,write_allowed FROM authority "
            "WHERE singleton=1").fetchone()
        root = db.execute(
            "SELECT goal_rev,grant_rev,state,parent_task FROM tasks "
            "WHERE task_id=?", (root_task_id,)).fetchone()
        current_authority = (
            (authority["goal_rev"], authority["grant_rev"],
             authority["write_allowed"]) if authority else None)
        current_root = (
            (root["goal_rev"], root["grant_rev"], root["state"])
            if root and root["parent_task"] is None else None)
    if (current_authority != starting_authority
        or current_root != starting_root):
        return {"status": "PROCEDURE_TRIAL_SNAPSHOT_CHANGED", "items": [],
                "authorizes_action": False}

    fresh_items = []
    for item in items:
        try:
            fresh_state = inspect_native_goal(
                db_path, workspace, fixtures, item["source_root_id"])
            fresh = inspect_owner_local_outcome(
                db_path, workspace, fixtures, item["source_root_id"])
            if (fresh_state.get("status") == "NATIVE_NEXT_DECISION_ADMISSIBLE"
                and isinstance(fresh_state.get("original_goal"), str)
                and _sha(fresh_state["original_goal"]) == item["source_goal_sha256"]
                and fresh_state.get("observation_sha256") ==
                    item["source_observation_sha256"]
                and fresh.get("status") == "LOCAL_OWNER_RESULT_VERIFIED"
                and fresh.get("local_owner_outcome_verified") is True
                and fresh.get("evidence_task_id") == item["evidence_task_id"]
                and fresh.get("evidence_sha256") == item["evidence_sha256"]):
                fresh_items.append(item)
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            continue

    fresh_failure_items = []
    for candidate_id, expected_observation in failure_snapshots.items():
        try:
            fresh_state = inspect_native_goal(
                db_path, workspace, fixtures, candidate_id)
            if (fresh_state.get("status") != "NATIVE_NEXT_DECISION_ADMISSIBLE"
                or fresh_state.get("observation_sha256") != expected_observation
                or not isinstance(fresh_state.get("original_goal"), str)):
                continue
            decisions_by_event = {
                decision.get("event_id"): decision
                for decision in fresh_state.get("decisions", [])
            }
            for item in failure_items:
                if item["source_root_id"] != candidate_id:
                    continue
                attempt = decisions_by_event.get(item["decision_event_id"])
                if (attempt is not None
                    and attempt.get("task_id") == item["evidence_task_id"]
                    and attempt.get("selected_objective") == item["objective"]
                    and attempt.get("task_state") == "UNKNOWN"
                    and attempt.get("error_code") == item["worker_error_code"]
                    and _sha(fresh_state["original_goal"]) ==
                        item["source_goal_sha256"]):
                    fresh_failure_items.append(item)
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            continue

    with readonly_snapshot(db_path) as db:
        authority = db.execute(
            "SELECT goal_rev,grant_rev,write_allowed FROM authority "
            "WHERE singleton=1").fetchone()
        root = db.execute(
            "SELECT goal_rev,grant_rev,state,parent_task FROM tasks "
            "WHERE task_id=?", (root_task_id,)).fetchone()
        final_authority = (
            (authority["goal_rev"], authority["grant_rev"],
             authority["write_allowed"]) if authority else None)
        final_root = (
            (root["goal_rev"], root["grant_rev"], root["state"])
            if root and root["parent_task"] is None else None)
    current_after = inspect_native_goal(
        db_path, workspace, fixtures, root_task_id)
    if (final_authority != starting_authority
        or final_root != starting_root
        or current_after.get("status") != "NATIVE_NEXT_DECISION_ADMISSIBLE"
        or not isinstance(current_after.get("original_goal"), str)
        or _sha(current_after["original_goal"]) != current_goal_sha256):
        return {"status": "PROCEDURE_TRIAL_SNAPSHOT_CHANGED", "items": [],
                "authorizes_action": False}

    return {
        "status": (
            "CROSS_ROOT_PROCEDURE_TRIALS_AVAILABLE" if fresh_items else
            "CROSS_ROOT_PROCEDURE_FAILURE_EVIDENCE_AVAILABLE"
            if fresh_failure_items else
            "NO_VERIFIED_CROSS_ROOT_PROCEDURE_TRIALS"),
        "items": fresh_items,
        "failure_items": fresh_failure_items,
        "source_roots_scanned": len(candidate_ids),
        "source_root_scan_truncated": scan_truncated,
        "current_root_goal_sha256": current_goal_sha256,
        "any_general_method_transfer_verified": False,
        "any_failure_cause_verified": False,
        "authorizes_action": False,
        "business_outcome_verified": False,
    }
