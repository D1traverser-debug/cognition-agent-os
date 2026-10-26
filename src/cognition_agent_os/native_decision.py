"""Model-neutral cognition boundary on the existing Host/SQLite authority.

External reasoning (for example the ChatGPT tool loop) can propose the NEXT
bounded registered action against a complete immutable owner goal. Every new
choice uses fresh source and result evidence, a CAS observation fingerprint,
and the same Worker/grant/lineage gateway. This is NOT a model or oracle:
the semantic quality of an option remains unproven until an independent owner
outcome is available. No paid model, second scheduler, plugin installation,
arbitrary code import or production provider effect is implied.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .intent_planner import compile_intent, IntentError
from .ledger import connect, create_task, event, require_initialized_ledger
from .source import safe_fixture, SourceUnavailable

_ID = re.compile(r"[a-f0-9]{32}\Z")
_MAX_DECISIONS = 3
_MAX_SOURCE_COUNT = 64
_VALID_KINDS = frozenset({
    "goal_case", "record_reconciliation", "investigate_goal",
    "public_tool_discovery",
})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def _contract(goal: str, *, allow_public_discovery: bool = False) -> dict:
    if (not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 2048
        or type(allow_public_discovery) is not bool):
        raise ValueError("INVALID_NATIVE_OWNER_GOAL")
    return {"kind": "native_goal", "version": 1,
            "goal": goal, "allow_public_discovery": allow_public_discovery,
            "max_decisions": _MAX_DECISIONS}


def _sources(fixtures: Path) -> dict[str, str]:
    """Bound the complete local evidence corpus, not a model-selected subset."""
    if not fixtures.is_dir() or fixtures.is_symlink():
        raise ValueError("INVALID_NATIVE_SOURCE_ROOT")
    result = {}
    entries = sorted(fixtures.iterdir(), key=lambda p: p.name)
    if len(entries) > _MAX_SOURCE_COUNT:
        raise ValueError("SOURCE_MANIFEST_EXCEEDS_BOUND")
    for path in entries:
        if (not path.is_file() or path.suffix.lower() not in
            (".json", ".csv", ".md", ".txt")):
            raise ValueError("UNSUPPORTED_NATIVE_SOURCE")
        raw = safe_fixture(fixtures, path.name)
        result[path.name] = hashlib.sha256(raw).hexdigest()
    return result


def _proposal(candidate: dict, contract: dict) -> dict:
    """Require independently compilable *competing* local methods.

    Their prose explanations are untrusted model hypotheses. No model-chosen
    module path, shell command, URL or grant is consumed as executor authority.
    """
    if (not isinstance(candidate, dict) or set(candidate) !=
        {"selected_intent", "alternative_intent", "decision_reason",
         "alternative_reason", "expected_evidence", "observation_sha256"}):
        raise ValueError("INVALID_NATIVE_DECISION")
    fields = ("decision_reason", "alternative_reason", "expected_evidence")
    if any(not isinstance(candidate[x], str) or
           not 8 <= len(candidate[x].strip()) <= 512 for x in fields):
        raise ValueError("MISSING_DECISION_COMPARISON")
    if (not isinstance(candidate["observation_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", candidate["observation_sha256"])):
        raise ValueError("INVALID_OBSERVATION_FINGERPRINT")
    selected = compile_intent(candidate["selected_intent"])
    alternative = compile_intent(candidate["alternative_intent"])
    if selected["objective"] == alternative["objective"]:
        raise ValueError("COMPETING_METHODS_NOT_DISTINCT")
    if (not contract["allow_public_discovery"]
        and (selected["objective"] == "discover_public_tools"
             or alternative["objective"] == "discover_public_tools")):
        raise PermissionError("PUBLIC_DISCOVERY_NOT_AUTHORIZED")
    if selected["child_source_spec"]["kind"] not in _VALID_KINDS:
        raise ValueError("UNREGISTERED_NATIVE_CAPABILITY")
    return {"selected": selected, "alternative": alternative}


def register_native_goal(db_path: Path, goal: str, *,
                         allow_public_discovery: bool = False) -> str:
    """Add the original goal without invoking the fixed-grammar open_goal router."""
    contract = _contract(goal, allow_public_discovery=allow_public_discovery)
    require_initialized_ledger(db_path)
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            auth = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if auth is None or auth["write_allowed"] != 1:
                raise PermissionError("NATIVE_GOAL_CURRENT_GRANT_REQUIRED")
            root = create_task(db, contract, commit=False)
            db.execute("UPDATE tasks SET state='DECOMPOSED',"
                       "decision='AWAIT_NATIVE_DECISION',"
                       "state_version=state_version+1 WHERE task_id=?", (root,))
            event(db, root, "NATIVE_GOAL_REGISTERED", {
                "contract_sha256": _digest(contract),
                "owner_outcome_verified": False,
                "external_effect_authorized": False})
            db.commit()
            return root
        except BaseException:
            db.rollback()
            raise


def _audit(db: sqlite3.Connection, db_path: Path,
           workspace: Path, fixtures: Path, root_id: str) -> dict:
    """Independent lineage and live evidence readback, no task writes."""
    fail = {"root_task_id": root_id, "status": "NATIVE_GOAL_UNVERIFIABLE",
            "owner_outcome_verified": False, "business_outcome_verified": False}
    root = db.execute(
        "SELECT * FROM tasks WHERE task_id=? AND parent_task IS NULL",
        (root_id,)).fetchone()
    if root is None or root["state"] != "DECOMPOSED":
        return {**fail, "reason": "ORIGINAL_GOAL_NOT_ACTIVE"}
    try:
        contract = json.loads(root["source_spec"])
        if contract != _contract(contract["goal"],
                                allow_public_discovery=contract["allow_public_discovery"]):
            raise ValueError("INVALID_ORIGINAL_CONTRACT")
        reg = db.execute(
            "SELECT details FROM events WHERE task_id=? AND kind='NATIVE_GOAL_REGISTERED'",
            (root_id,)).fetchall()
        if (len(reg) != 1 or json.loads(reg[0]["details"]) != {
            "contract_sha256": _digest(contract),
            "owner_outcome_verified": False, "external_effect_authorized": False}):
            raise ValueError("ORIGINAL_RECEIPT_CHANGED")
        decisions = db.execute(
            "SELECT details FROM events WHERE task_id=? AND kind='NATIVE_DECISION_ADMITTED' "
            "ORDER BY event_id", (root_id,)).fetchall()
        children = db.execute(
            "SELECT * FROM tasks WHERE parent_task=? ORDER BY created_at,task_id",
            (root_id,)).fetchall()
        if len(decisions) > _MAX_DECISIONS or len(children) != len(decisions):
            raise ValueError("DECISION_CHILD_CARDINALITY_CHANGED")
        by_id = {row["task_id"]: row for row in children}
        if len(by_id) != len(children):
            raise ValueError("DUPLICATE_DECISION_CHILD")
        current_sources = _sources(fixtures)
        observations = []
        previous_id = None
        for index, item in enumerate(decisions):
            receipt = json.loads(item["details"])
            if (not isinstance(receipt, dict)
                or set(receipt) != {"child_task_id", "ordinal", "proposal",
                                   "selected_plan_sha256", "source_sha256",
                                   "prior_child_task_id", "owner_outcome_verified"}
                or receipt["ordinal"] != index
                or receipt["prior_child_task_id"] != previous_id
                or receipt["owner_outcome_verified"] is not False):
                raise ValueError("DECISION_RECEIPT_CHANGED")
            parsed = _proposal(receipt["proposal"], contract)
            selected = parsed["selected"]
            child = by_id.get(receipt["child_task_id"])
            if (child is None or child["goal_rev"] != root["goal_rev"]
                or child["grant_rev"] != root["grant_rev"]
                or json.loads(child["source_spec"]) != selected["child_source_spec"]
                or receipt["selected_plan_sha256"] != selected["plan_sha256"]):
                raise ValueError("DECISION_CHILD_PROVENANCE_CHANGED")
            if receipt["source_sha256"] != current_sources:
                return {**fail, "status": "NATIVE_SOURCE_CHANGED",
                        "original_goal": contract["goal"],
                        "reason": "SOURCE_PIN_DRIFT"}
            previous_id = child["task_id"]
            verdict = "NOT_YET_INDEPENDENTLY_CHECKED"
            if child["state"] in ("NEEDS_REVIEW", "VERIFIED"):
                kind = selected["child_source_spec"]["kind"]
                if kind == "goal_case":
                    from .goal_audit import audit_goal
                    result = audit_goal(db_path, workspace, fixtures, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "CANDIDATE_MECHANICALLY_VALID"
                elif kind == "record_reconciliation":
                    from .reconciliation_oracle import audit_stored_report
                    result = audit_stored_report(
                        db_path, workspace, fixtures, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "REPORT_MECHANICALLY_VERIFIED"
                elif kind == "investigate_goal":
                    from .investigation import audit_investigation
                    result = audit_investigation(
                        db_path, workspace, fixtures, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "SOURCE_GROUNDED_UNREVIEWED"
                elif kind == "public_tool_discovery":
                    from .public_tool_discovery import audit_public_discovery
                    result = audit_public_discovery(
                        db_path, workspace, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED"
                else:
                    accepted = False
                if not accepted:
                    return {**fail, "status": "NATIVE_EVIDENCE_UNVERIFIABLE",
                            "original_goal": contract["goal"],
                            "reason": verdict}
            observations.append({
                "task_id": child["task_id"], "task_state": child["state"],
                "selected_objective": selected["objective"],
                "alternative_objective": parsed["alternative"]["objective"],
                "mechanical_verdict": verdict,
                "owner_outcome_verified": False})
        auth = db.execute(
            "SELECT * FROM authority WHERE singleton=1").fetchone()
        grant_current = bool(auth and auth["write_allowed"] == 1
            and (auth["goal_rev"], auth["grant_rev"]) ==
                (root["goal_rev"], root["grant_rev"]))
        # Hash SOURCE IDs and externally observed task states/results, not
        # private goal text in public event logs.
        fingerprint = _digest({
            "root": root_id, "contract": _digest(contract),
            "goal_rev": root["goal_rev"], "grant_rev": root["grant_rev"],
            "grant_current": grant_current, "sources": current_sources,
            "decisions": [json.loads(e["details"]) for e in decisions],
            "children": observations})
        waiting = bool(observations and
            observations[-1]["task_state"] in ("PENDING", "RUNNING"))
        return {
            "root_task_id": root_id,
            "status": ("NATIVE_GRANT_REVOKED" if not grant_current
                       else "NATIVE_AWAITING_WORKER" if waiting
                       else "NATIVE_DECISION_BUDGET_EXHAUSTED"
                            if len(decisions) >= _MAX_DECISIONS
                       else "NATIVE_NEXT_DECISION_ADMISSIBLE"),
            "original_goal": contract["goal"],
            "observation_sha256": fingerprint,
            "decisions": observations, "decision_count": len(decisions),
            "owner_outcome_verified": False, "business_outcome_verified": False,
        }
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error,
            IntentError, SourceUnavailable, PermissionError) as exc:
        return {**fail, "reason": type(exc).__name__}


def inspect_native_goal(db_path: Path, workspace: Path, fixtures: Path,
                        root_id: str) -> dict:
    """Read-only resumable native-cognition decision state."""
    if (not isinstance(root_id, str) or not _ID.fullmatch(root_id)
        or not db_path.is_file() or db_path.is_symlink()):
        return {"root_task_id": root_id, "status": "NATIVE_GOAL_UNVERIFIABLE",
                "owner_outcome_verified": False}
    uri = db_path.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        return _audit(db, db_path, workspace, fixtures, root_id)


def admit_native_decision(db_path: Path, workspace: Path, fixtures: Path,
                          root_id: str, candidate: dict) -> dict:
    """Append ONE model proposal if current evidence CAS still matches.

    The original Host/Worker executes the child on its next tick. This function
    has no tool runner, daemon, model API, independent scheduler or new grant.
    """
    require_initialized_ledger(db_path)
    if not isinstance(root_id, str) or not _ID.fullmatch(root_id):
        raise ValueError("INVALID_NATIVE_ROOT_ID")
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            observed = _audit(db, db_path, workspace, fixtures, root_id)
            if observed["status"] != "NATIVE_NEXT_DECISION_ADMISSIBLE":
                raise ValueError("NATIVE_DECISION_NOT_ADMISSIBLE:" + observed["status"])
            root = db.execute("SELECT * FROM tasks WHERE task_id=?",
                              (root_id,)).fetchone()
            contract = json.loads(root["source_spec"])
            parsed = _proposal(candidate, contract)
            if candidate["observation_sha256"] != observed["observation_sha256"]:
                raise ValueError("NATIVE_STALE_OBSERVATION")
            if any(x["selected_objective"] == parsed["selected"]["objective"]
                   for x in observed["decisions"]):
                raise ValueError("REPEATED_NATIVE_METHOD_WITHOUT_NEW_EVIDENCE")
            # Compare/grant and exact source snapshot rechecked *inside*
            # the original SQLite write transaction.
            auth = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if (auth is None or auth["write_allowed"] != 1
                or (auth["goal_rev"], auth["grant_rev"]) !=
                   (root["goal_rev"], root["grant_rev"])):
                raise PermissionError("CURRENT_NATIVE_GRANT_REVOKED")
            source_hashes = _sources(fixtures)
            child = create_task(db, parsed["selected"]["child_source_spec"],
                                parent=root_id, commit=False)
            previous = (observed["decisions"][-1]["task_id"]
                        if observed["decisions"] else None)
            event(db, root_id, "NATIVE_DECISION_ADMITTED", {
                "child_task_id": child,
                "ordinal": observed["decision_count"],
                "proposal": candidate,
                "selected_plan_sha256": parsed["selected"]["plan_sha256"],
                "source_sha256": source_hashes,
                "prior_child_task_id": previous,
                "owner_outcome_verified": False})
            db.commit()
            return {"status": "NATIVE_METHOD_ENQUEUED",
                    "root_task_id": root_id, "child_task_id": child,
                    "selected_objective": parsed["selected"]["objective"],
                    "alternative_objective": parsed["alternative"]["objective"],
                    "business_outcome_verified": False,
                    "owner_outcome_verified": False}
        except BaseException:
            db.rollback()
            raise


def native_child_admitted(db: sqlite3.Connection, fixtures: Path,
                          task_id: str) -> bool:
    """Worker provenance check; refuse forged model-selected child or drift.

    Full artifact/outcome audit is performed by the independent Host readback.
    """
    try:
        task = db.execute("SELECT * FROM tasks WHERE task_id=?",
                          (task_id,)).fetchone()
        root = db.execute("SELECT * FROM tasks WHERE task_id=?",
                          (task["parent_task"],)).fetchone()
        contract = json.loads(root["source_spec"])
        if (root["state"] != "DECOMPOSED"
            or contract != _contract(contract["goal"],
                                     allow_public_discovery=contract["allow_public_discovery"])):
            return False
        receipts = db.execute(
            "SELECT details FROM events WHERE task_id=? "
            "AND kind='NATIVE_DECISION_ADMITTED' ORDER BY event_id",
            (root["task_id"],)).fetchall()
        children = db.execute("SELECT task_id FROM tasks WHERE parent_task=?",
                              (root["task_id"],)).fetchall()
        if (not 1 <= len(receipts) <= _MAX_DECISIONS
            or len(children) != len(receipts)):
            return False
        pinned = _sources(fixtures)
        known = set()
        previous = None
        for ordinal, r in enumerate(receipts):
            entry = json.loads(r["details"])
            if (entry["ordinal"] != ordinal
                or entry["prior_child_task_id"] != previous
                or entry["source_sha256"] != pinned
                or entry["owner_outcome_verified"] is not False):
                return False
            selected = _proposal(entry["proposal"], contract)["selected"]
            candidate = db.execute("SELECT source_spec,goal_rev,grant_rev "
                                   "FROM tasks WHERE task_id=?",
                                   (entry["child_task_id"],)).fetchone()
            if (candidate is None
                or json.loads(candidate["source_spec"]) != selected["child_source_spec"]
                or entry["selected_plan_sha256"] != selected["plan_sha256"]
                or (candidate["goal_rev"], candidate["grant_rev"]) !=
                   (root["goal_rev"], root["grant_rev"])
                or entry["child_task_id"] in known):
                return False
            known.add(entry["child_task_id"])
            previous = entry["child_task_id"]
        return known == {x["task_id"] for x in children} and task_id in known
    except (KeyError, ValueError, TypeError, sqlite3.Error, OSError,
            SourceUnavailable, IntentError, PermissionError):
        return False
