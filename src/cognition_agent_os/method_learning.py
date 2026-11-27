"""Revalidate cross-task method trials; never promote model confidence to truth."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path

from .cognitive_session import _identity, _project, inspect_session, digest
from .effect_contract import inspect_contract_outcome, _action_binding, _restore_epoch
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


def _observed_usage(db_path, sources, workspace, method, trial_root, outcome):
    """Link independently checked output bytes to a real method-bound effect.

    Do not recursively re-admit an executed action: its old trial snapshot is
    expected to change when this result becomes evidence. Scoped usage is
    not causal improvement or semantic transfer.
    """
    with readonly_snapshot(db_path) as db:
        view = _project(db, sources, trial_root)
        if not view["grant_current"]:
            return []
        nodes = {node["id"]: node for node in view["nodes"]}
        rows = db.execute(
            "SELECT task_id,state,state_version,source_spec,artifact_hash "
            "FROM tasks WHERE parent_task=? ORDER BY task_id LIMIT 257",
            (trial_root,)).fetchall()
        if len(rows) > 256:
            return []
        checked = {c["check"]["path"]: c["observed_sha256"]
                   for c in outcome["checks"]
                   if c["check"]["space"] == "workspace" and c["passed"]
                   and "observed_sha256" in c}
        receipts = []
        for row in rows:
            if row["state"] not in ("NEEDS_REVIEW", "VERIFIED", "SANDBOX_VERIFIED"):
                continue
            child = row["task_id"]
            binding = _action_binding(db, trial_root, child)
            if not binding:
                continue
            node = nodes.get(binding["decision_id"])
            if (not node or node["status"] != "CURRENT"
                    or node["event_id"] != binding["decision_event_id"]
                    or node["event_id"] <= _restore_epoch(db)
                    or binding["goal_sha256"] != view["goal_sha256"]
                    or binding["spec_sha256"] != digest(json.loads(row["source_spec"]))
                    or binding["sources_root"] != str(sources.resolve())
                    or binding["workspace_root"] != str(workspace.resolve())):
                continue
            if not any(
                    item["reference"]["root_task_id"] == method["root_task_id"]
                    and item["reference"]["node_id"] == method["node_id"]
                    for item in binding.get("method_evidence", [])):
                continue
            path = "artifacts/" + child + ".json"
            if not row["artifact_hash"] or checked.get(path) != row["artifact_hash"]:
                continue
            receipts.append({"child_task_id": child,
                             "decision_event_id": node["event_id"],
                             "binding_sha256": digest(binding),
                             "state_version": row["state_version"],
                             "artifact_sha256": row["artifact_hash"]})
        return receipts


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
    usage = _observed_usage(db_path, sources, workspace, method, trial_root, result)
    payload = {"method": method, "trial_root": trial_root,
               "request_id": request_id, "observation": result,
               "usage": usage, "causal_improvement_proven": False}
    with closing(connect_existing(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _identity(db, method_root, write=True)
            _identity(db, trial_root, write=True)
            # Fresh independent readback after acquiring the sole writer lock.
            if (_method(db_path, sources, method_root, method_node) != method
                    or inspect_contract_outcome(db_path, sources, workspace, trial_root) != result
                    or _observed_usage(db_path, sources, workspace, method, trial_root, result) != usage):
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
            usage = _observed_usage(db_path, sources, workspace, method, target, now)
            # Older events are observations only. They cannot acquire a new
            # usage receipt retroactively merely because an artifact exists.
            linked = bool(old.get("usage")) and old["usage"] == usage
            status = ("STALE" if old["method"] != method or now != old["observation"]
                      or (old.get("usage") and not linked)
                      else "OBSERVED_PASS" if now["contract_outcome_verified"] else "OBSERVED_FAIL")
        except (ValueError, OSError, KeyError, TypeError):
            status, linked = "UNAVAILABLE", False
        trials.append({"trial_root": target, "status": status,
                       "method_use_verified": bool(linked and status == "OBSERVED_PASS")})
    bad = any(t["status"] != "OBSERVED_PASS" for t in trials)
    return {"status": "REQUIRES_REINVESTIGATION" if bad else "SCOPED_TRIALS_ONLY",
            "method": method, "trials": trials, "truncated": len(rows) > 256,
            "cross_domain_generalization_verified": False, "authorizes_action": False}
