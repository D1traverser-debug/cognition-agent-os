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

_ID = re.compile(r"[0-9a-f]{32}\\Z")
_MAX_ROOT_SCAN = 64
_MAX_TRIALS = 8
_MAX_PER_OBJECTIVE = 3


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    for candidate_id in candidate_ids:
        try:
            prior = inspect_native_goal(
                db_path, workspace, fixtures, candidate_id)
            if (prior.get("status") != "NATIVE_NEXT_DECISION_ADMISSIBLE"
                or not isinstance(prior.get("original_goal"), str)
                or _sha(prior["original_goal"]) == current_goal_sha256
                or not prior.get("decisions")):
                continue
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
            with readonly_snapshot(db_path) as db:
                events = db.execute(
                    "SELECT details FROM events WHERE task_id=? "
                    "AND kind='NATIVE_DECISION_ADMITTED' ORDER BY event_id",
                    (candidate_id,)).fetchall()
            if len(events) != len(prior["decisions"]):
                continue
            receipt = json.loads(events[-1]["details"])
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
            if count >= _MAX_PER_OBJECTIVE:
                continue
            item = {
                "source_root_id": candidate_id,
                "source_goal_sha256": _sha(prior["original_goal"]),
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
            if len(items) >= limit:
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
            fresh = inspect_owner_local_outcome(
                db_path, workspace, fixtures, item["source_root_id"])
            if (fresh.get("status") == "LOCAL_OWNER_RESULT_VERIFIED"
                and fresh.get("local_owner_outcome_verified") is True
                and fresh.get("evidence_task_id") == item["evidence_task_id"]
                and fresh.get("evidence_sha256") == item["evidence_sha256"]):
                fresh_items.append(item)
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
    if (final_authority != starting_authority
        or final_root != starting_root):
        return {"status": "PROCEDURE_TRIAL_SNAPSHOT_CHANGED", "items": [],
                "authorizes_action": False}

    return {
        "status": ("CROSS_ROOT_PROCEDURE_TRIALS_AVAILABLE" if fresh_items
                   else "NO_VERIFIED_CROSS_ROOT_PROCEDURE_TRIALS"),
        "items": fresh_items,
        "source_roots_scanned": len(candidate_ids),
        "source_root_scan_truncated": scan_truncated,
        "current_root_goal_sha256": current_goal_sha256,
        "any_general_method_transfer_verified": False,
        "authorizes_action": False,
        "business_outcome_verified": False,
    }
