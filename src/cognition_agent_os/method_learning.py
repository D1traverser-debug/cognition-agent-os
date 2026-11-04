"""Revalidate cross-task method trials; never promote model confidence to truth."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path

from .cognitive_session import _identity, _project, inspect_session, digest
from .effect_contract import inspect_contract_outcome
from .ledger import connect_existing, readonly_snapshot, event


def _method(db_path, sources, root_id, node_id):
    with readonly_snapshot(db_path) as db:
        view = _project(db, sources, root_id)
    matches = [n for n in view["nodes"] if n["id"] == node_id and n["kind"] == "method"]
    if not view["grant_current"] or len(matches) != 1 or matches[0]["status"] != "CURRENT":
        raise ValueError("METHOD_NOT_CURRENT")
    node = matches[0]
    return {"root_task_id": root_id, "node_id": node_id,
            "sha256": digest(node), "text": node["text"]}


def record_trial(db_path: Path, sources: Path, workspace: Path,
                 method_root: str, method_node: str, trial_root: str,
                 request_id: str):
    """Observation of an operator-bound outcome, not proof of method causation.

    A trial belongs to a DIFFERENT original goal. Failed or stale outcomes
    remain negative/unknown evidence; no automatic action or Skill rewrite.
    """
    if method_root == trial_root:
        raise ValueError("CROSS_TASK_TRIAL_REQUIRED")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 96:
        raise ValueError("INVALID_TRIAL_REQUEST_ID")
    method = _method(db_path, sources, method_root, method_node)
    source_goal = inspect_session(db_path, sources, method_root)["goal_sha256"]
    target_goal = inspect_session(db_path, sources, trial_root)["goal_sha256"]
    if source_goal == target_goal:
        raise ValueError("DIFFERENT_GOAL_REQUIRED")
    result = inspect_contract_outcome(db_path, sources, workspace, trial_root)
    if not result["checks"]:
        raise ValueError("INDEPENDENT_TRIAL_CONTRACT_REQUIRED")
    payload = {"method": method, "trial_root": trial_root,
               "request_id": request_id, "observation": result,
               "causal_improvement_proven": False}
    with closing(connect_existing(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _identity(db, method_root, write=True)
            _identity(db, trial_root, write=True)
            # Fresh independent readback after acquiring the sole writer lock.
            if (_method(db_path, sources, method_root, method_node) != method
                    or inspect_contract_outcome(db_path, sources, workspace, trial_root) != result):
                raise ValueError("TRIAL_CHANGED_DURING_RECORD")
            prior = db.execute("SELECT details FROM events WHERE task_id=? "
                "AND kind='COGNITION_METHOD_TRIAL' AND json_extract(details,'$.request_id')=?",
                (trial_root, request_id)).fetchall()
            if prior:
                if len(prior) != 1 or json.loads(prior[0][0]) != payload:
                    raise ValueError("TRIAL_REQUEST_ID_CONFLICT")
            else:
                event(db, trial_root, "COGNITION_METHOD_TRIAL", payload)
            db.commit()
            return payload
        except BaseException:
            db.rollback()
            raise


def inspect_trials(db_path: Path, sources: Path, workspace: Path,
                   method_root: str, method_node: str):
    try:
        method = _method(db_path, sources, method_root, method_node)
    except ValueError:
        return {"status": "METHOD_WITHDRAWN_OR_STALE", "trials": [], "authorizes_action": False}
    with readonly_snapshot(db_path) as db:
        rows = db.execute("SELECT details FROM events WHERE kind='COGNITION_METHOD_TRIAL' "
            "AND json_extract(details,'$.method.root_task_id')=? "
            "AND json_extract(details,'$.method.node_id')=? ORDER BY event_id DESC LIMIT 257",
            (method_root, method_node)).fetchall()
    trials = []
    seen = set()
    for row in rows[:256]:
        old = json.loads(row[0])
        target = old["trial_root"]
        if target in seen:
            continue
        seen.add(target)
        try:
            now = inspect_contract_outcome(db_path, sources, workspace, target)
            status = ("STALE" if old["method"] != method or now != old["observation"]
                      else "OBSERVED_PASS" if now["contract_outcome_verified"] else "OBSERVED_FAIL")
        except (ValueError, OSError):
            status = "UNAVAILABLE"
        trials.append({"trial_root": target, "status": status})
    bad = any(t["status"] != "OBSERVED_PASS" for t in trials)
    return {"status": "REQUIRES_REINVESTIGATION" if bad else "SCOPED_TRIALS_ONLY",
            "method": method, "trials": trials, "truncated": len(rows) > 256,
            "cross_domain_generalization_verified": False, "authorizes_action": False}
