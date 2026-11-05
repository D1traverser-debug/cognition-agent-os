"""Operator-bound effects/outcomes for managed cognitive sessions.

No natural-language parser can certify arbitrary owner intent. The operator
binds a finite executable contract outside the model-visible MCP interface.
Its semantics still require review; hashes prove identity, not correctness.
Legacy typed ledgers remain compatible and are reported as unmanaged.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path

from .cognitive_session import _identity, _project, digest
from .ledger import connect_existing, readonly_snapshot, event
from .source import safe_fixture, SourceUnavailable


def managed(db, root_id):
    return db.execute("SELECT 1 FROM events WHERE task_id=? "
                      "AND kind='COGNITION_MANAGED' OR kind='COGNITION_MANAGED_LEDGER' LIMIT 1",
                      (root_id,)).fetchone() is not None


def enable_managed_session(db_path: Path, root_id: str):
    with closing(connect_existing(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _enable_managed(db, root_id)
            db.commit()
        except BaseException:
            db.rollback()
            raise


def _enable_managed(db, root_id):
    """Also used inside registration so a new client root is never unguarded."""
    _identity(db, root_id, write=True)
    if not managed(db, root_id):
        if db.execute("SELECT 1 FROM tasks WHERE parent_task=? LIMIT 1",
                      (root_id,)).fetchone():
            raise ValueError("MANAGED_SESSION_REQUIRES_NO_PRIOR_EFFECTS")
        event(db, root_id, "COGNITION_MANAGED", {"version": 1})


def require_managed_session(db_path: Path, root_id: str):
    """Public client effect entry: never fall through to legacy unbound mode.

    Reads/research remain available for old roots. The later admission/Worker
    guards still check the actual contract and evidence under their own lock.
    """
    with readonly_snapshot(db_path) as db:
        _identity(db, root_id, write=True)
        if not managed(db, root_id):
            raise PermissionError("UNMANAGED_NATIVE_EFFECTS_DISABLED")


def _check_shape(check):
    if (not isinstance(check, dict) or set(check) != {"space", "path", "test", "value"}
            or check["space"] not in ("sources", "workspace")
            or not isinstance(check["path"], str) or not check["path"]
            or check["test"] not in ("sha256", "text_contains", "json_equals")):
        raise ValueError("INVALID_EXECUTABLE_CHECK")
    if check["test"] in ("sha256", "text_contains") and not isinstance(check["value"], str):
        raise ValueError("INVALID_EXECUTABLE_CHECK_VALUE")
    if check["test"] == "text_contains" and not check["value"]:
        raise ValueError("EMPTY_CHECK_IS_NOT_EVIDENCE")
    if check["test"] == "sha256" and (len(check["value"]) != 64
            or any(c not in "0123456789abcdef" for c in check["value"])):
        raise ValueError("INVALID_CHECK_DIGEST")
    digest(check)  # Reject non-JSON/non-finite data before any write.


def evaluate_check(check, sources: Path, workspace: Path):
    _check_shape(check)
    try:
        raw = safe_fixture(sources if check["space"] == "sources" else workspace,
                           check["path"])
        observed_sha = hashlib.sha256(raw).hexdigest()
        if check["test"] == "sha256":
            passed = observed_sha == check["value"]
        elif check["test"] == "text_contains":
            passed = check["value"] in raw.decode("utf-8")
        else:
            # Canonical typed comparison: Python's True == 1 is not JSON equality.
            passed = digest(json.loads(raw)) == digest(check["value"])
        return {"check": check, "passed": passed, "observed_sha256": observed_sha}
    except (OSError, ValueError, UnicodeError, SourceUnavailable):
        return {"check": check, "passed": False, "reason": "SOURCE_UNAVAILABLE_OR_INVALID"}


def install_contract(db_path: Path, sources: Path, root_id: str, contract: dict, *,
                     workspace: Path | None = None, rebind_pending: bool = False):
    """Trusted operator API only; intentionally not an MCP model tool.

    Binding/replacing this policy is an authorization operation. A process with
    arbitrary SQL/shell access is outside this MCP boundary and can bypass it.
    """
    if (not isinstance(contract, dict)
            or set(contract) != {"version", "goal_sha256", "effects", "outcomes"}
            or type(contract["version"]) is not int or contract["version"] != 1
            or not isinstance(contract["effects"], list) or len(contract["effects"]) > 32
            or not isinstance(contract["outcomes"], list) or len(contract["outcomes"]) > 64):
        raise ValueError("INVALID_EFFECT_CONTRACT")
    for effect in contract["effects"]:
        if (not isinstance(effect, dict) or set(effect) != {"spec", "prerequisites"}
                or not isinstance(effect["spec"], dict)
                or not isinstance(effect["prerequisites"], list)
                or len(effect["prerequisites"]) > 32):
            raise ValueError("INVALID_CONTRACT_EFFECT")
        for check in effect["prerequisites"]:
            _check_shape(check)
    for check in contract["outcomes"]:
        _check_shape(check)
    contract_sha = digest(contract)
    with closing(connect_existing(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _identity(db, root_id, write=True)
            view = _project(db, sources, root_id)
            if not managed(db, root_id):
                raise ValueError("MANAGED_SESSION_REQUIRED")
            if contract["goal_sha256"] != view["goal_sha256"]:
                raise ValueError("EFFECT_CONTRACT_GOAL_CHANGED")
            prior = _latest_contract(db, root_id)
            if (prior is None or prior["sha256"] != contract_sha
                    or prior["event_id"] < _restore_epoch(db)):
                event(db, root_id, "COGNITION_EFFECT_CONTRACT", {
                    "contract": contract, "sha256": contract_sha,
                    "semantics": "OPERATOR_BOUND_NOT_AUTOMATIC_NL_VERIFICATION"})
            rebound = []
            if rebind_pending:
                if workspace is None:
                    raise ValueError("REBIND_REQUIRES_WORKSPACE")
                pending = db.execute("SELECT task_id,source_spec FROM tasks "
                    "WHERE parent_task=? AND state='PENDING'", (root_id,)).fetchall()
                for child in pending:
                    old = _action_binding(db, root_id, child["task_id"])
                    if old is None:
                        raise ValueError("CANNOT_REBIND_UNADMITTED_CHILD")
                    binding = enforce_admission(db, sources, workspace, root_id,
                                                json.loads(child["source_spec"]))
                    event(db, root_id, "COGNITION_ACTION_REBOUND", {
                        "child_task_id": child["task_id"], **binding,
                        "previous_binding_sha256": digest(old)})
                    rebound.append(child["task_id"])
            db.commit()
            return {"status": "CONTRACT_BOUND", "sha256": contract_sha, "rebound_pending": rebound}
        except BaseException:
            db.rollback()
            raise


def _latest_contract(db, root_id):
    row = db.execute("SELECT details,event_id FROM events WHERE task_id=? "
                     "AND kind='COGNITION_EFFECT_CONTRACT' ORDER BY event_id DESC LIMIT 1",
                     (root_id,)).fetchone()
    if row is None:
        return None
    data = json.loads(row[0])
    if digest(data["contract"]) != data["sha256"]:
        raise ValueError("EFFECT_CONTRACT_CORRUPT")
    data["event_id"] = row[1]
    return data


def _restore_epoch(db):
    return db.execute("SELECT coalesce(max(event_id),0) FROM events "
                      "WHERE kind='COGNITION_RESTORE_FENCE'").fetchone()[0]


def enforce_admission(db, sources: Path, workspace: Path, root_id: str, spec: dict):
    if not managed(db, root_id):
        return None
    view = _project(db, sources, root_id)
    policy = _latest_contract(db, root_id)
    if policy is None or policy["contract"]["goal_sha256"] != view["goal_sha256"]:
        raise PermissionError("CURRENT_OPERATOR_EFFECT_CONTRACT_REQUIRED")
    if policy["event_id"] < _restore_epoch(db):
        raise PermissionError("RESTORED_EFFECTS_REQUIRE_OPERATOR_REBIND")
    effects = [e for e in policy["contract"]["effects"] if digest(e["spec"]) == digest(spec)]
    if len(effects) != 1:
        raise PermissionError("EFFECT_NOT_IN_OWNER_BOUND_CONTRACT")
    checks = [evaluate_check(c, sources, workspace) for c in effects[0]["prerequisites"]]
    if not all(c["passed"] for c in checks):
        raise PermissionError("EFFECT_PREREQUISITE_NOT_VERIFIED")
    decisions = [n for n in view["nodes"] if n["kind"] == "decision"]
    if not decisions or decisions[-1]["status"] != "CURRENT":
        raise ValueError("CURRENT_COGNITIVE_DECISION_REQUIRED")
    decision = decisions[-1]
    # Any later input may change the goal or invalidate its evidence. Merely
    # recording an interpretation is not a decision to continue the action.
    # Recheck inside the same existing admission/effect-time transaction.
    if (view["uninterpreted_input_count"] or
            any(item["event_id"] > decision["event_id"] for item in view["inputs"])):
        raise PermissionError("COGNITIVE_INPUT_REQUIRES_REDECISION")
    # A research/architecture decision cannot be borrowed as evidence for an
    # unrelated typed action. The same immutable decision names its exact action.
    if decision.get("action_spec") is None or digest(decision["action_spec"]) != digest(spec):
        raise ValueError("COGNITIVE_DECISION_ACTION_MISMATCH")
    method_evidence = []
    if decision.get("method_refs"):
        # Reuse the existing trial reader; no second method status/promotion
        # table. Bind this dependency at admission AND the effect-time guard.
        from .method_learning import inspect_trials
        db_path = Path(db.execute("PRAGMA database_list").fetchone()[2])
        for ref in decision["method_refs"]:
            trials = inspect_trials(db_path, sources, workspace,
                                    ref["root_task_id"], ref["node_id"])
            if trials["status"] != "SCOPED_TRIALS_ONLY" or trials.get("truncated"):
                raise ValueError("COGNITIVE_METHOD_EVIDENCE_INVALIDATED")
            if ref["use"] == "reuse" and not trials["trials"]:
                raise ValueError("COGNITIVE_METHOD_REUSE_REQUIRES_TRIAL")
            method_evidence.append({"reference": ref, "snapshot_sha256": digest(trials)})
    return {"policy_sha256": policy["sha256"], "goal_sha256": view["goal_sha256"],
            "policy_event_id": policy["event_id"],
            "decision_id": decision["id"], "decision_event_id": decision["event_id"],
            "spec_sha256": digest(spec), "prerequisites": checks,
            **({"method_evidence": method_evidence} if method_evidence else {}),
            "sources_root": str(sources.resolve()), "workspace_root": str(workspace.resolve())}


def bind_action(db, root_id, child_id, binding):
    if binding is not None:
        event(db, root_id, "COGNITION_ACTION_BOUND", {"child_task_id": child_id, **binding})


def _action_binding(db, root_id, child_id):
    rows = db.execute("SELECT kind,details FROM events WHERE task_id=? "
        "AND kind IN ('COGNITION_ACTION_BOUND','COGNITION_ACTION_REBOUND') "
        "AND json_extract(details,'$.child_task_id')=? ORDER BY event_id", (root_id, child_id)).fetchall()
    if not rows or rows[0][0] != "COGNITION_ACTION_BOUND":
        return None
    prior = json.loads(rows[0][1])
    for row in rows[1:]:
        current = json.loads(row[1])
        if row[0] != "COGNITION_ACTION_REBOUND" or current.pop("previous_binding_sha256", None) != digest(prior):
            return None
        prior = current
    return prior


def verify_action_binding(db, sources: Path, workspace: Path, root_id: str,
                          child_id: str, spec: dict):
    if not managed(db, root_id):
        return True
    try:
        old = _action_binding(db, root_id, child_id)
        if old is None:
            return False
        now = enforce_admission(db, sources, workspace, root_id, spec)
        return old == {"child_task_id": child_id, **now}
    except (ValueError, PermissionError, KeyError, TypeError):
        return False


def current_effect_guard(db, task):
    """Recheck under the existing artifact writer's SQLite lock, not only preflight."""
    parent = task.get("parent_task")
    scope = parent or task["task_id"]
    if not managed(db, scope):
        return True
    if parent is None:
        return json.loads(task["source_spec"]).get("kind") == "native_goal"
    try:
        binding = _action_binding(db, parent, task["task_id"])
        if binding is None:
            return False
        return verify_action_binding(db, Path(binding["sources_root"]),
            Path(binding["workspace_root"]), parent, task["task_id"],
            json.loads(task["source_spec"]))
    except (KeyError, ValueError, TypeError, OSError):
        return False


def inspect_contract_outcome(db_path: Path, sources: Path, workspace: Path, root_id: str):
    with readonly_snapshot(db_path) as db:
        view = _project(db, sources, root_id)
        policy = _latest_contract(db, root_id)
        current = bool(policy and view["grant_current"]
                       and policy["contract"]["goal_sha256"] == view["goal_sha256"]
                       and policy["event_id"] > _restore_epoch(db))
        checks = ([evaluate_check(c, sources, workspace) for c in policy["contract"]["outcomes"]]
                  if current else [])
        verified = bool(checks and all(c["passed"] for c in checks))
        return {"status": "CONTRACT_VERIFIED" if verified else "CONTRACT_NOT_VERIFIED",
                "checks": checks, "contract_sha256": policy["sha256"] if policy else None,
                "goal_sha256": view["goal_sha256"],
                "contract_outcome_verified": verified,
                "original_goal_semantics_automatically_verified": False,
                "external_business_outcome_verified": False}
