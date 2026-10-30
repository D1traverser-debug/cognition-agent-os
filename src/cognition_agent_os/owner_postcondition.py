"""Independently read back a narrowly stated ORIGINAL owner's local result.

This is not a model's success opinion or a general business oracle.  A
goal-level result must have been requested in the owner's immutable wording,
actually produced under the SAME Host/SQLite grant, and independently checked
against original sources and a current local output.  Unsupported owner
objectives remain UNKNOWN rather than borrowing a child's mechanical PASS.

No second scheduler, task database, grant, remote write, or hidden promotion.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .ledger import readonly_snapshot
from .intent_planner import compile_intent
from .source import safe_fixture, SourceUnavailable
from .reconciliation_oracle import audit_stored_report
from .goal_audit import _constraints

_MAX_ARTIFACT = 128 * 1024
_EQUALS = re.compile(
    r"(?<![A-Za-z0-9_-])([A-Za-z_][A-Za-z0-9_-]{0,63})"
    r"\s+(?:equal|equals)\s+to\s+([A-Za-z][A-Za-z0-9_-]{0,127})\b",
    re.IGNORECASE,
)
_COMPARE = re.compile(
    r"\bcompare\s+([A-Za-z0-9_.-]+\.csv)\s+"
    r"(?:with|against|to)\s+([A-Za-z0-9_.-]+\.csv)\b",
    re.IGNORECASE,
)


def _unknown(root_id: str, reason: str) -> dict:
    return {
        "root_task_id": root_id, "status": "OWNER_POSTCONDITION_UNVERIFIED",
        "reason": reason, "local_owner_outcome_verified": False,
        "business_outcome_verified": False, "real_external_outcome_verified": False,
    }


def _bytes(workspace: Path, relative: str,
           max_size: int = _MAX_ARTIFACT) -> bytes:
    """Read staged evidence anchored to the workspace, not through path aliases.

    Reuse the source reader's opened-handle containment check so a swapped
    sandbox/artifacts parent directory cannot point the owner verifier at
    matching bytes outside the authorized workspace.
    """
    if workspace.is_symlink() or (workspace / relative).is_symlink():
        raise ValueError("UNSAFE_OR_MISSING_OUTPUT")
    raw = safe_fixture(workspace, relative)
    if len(raw) > max_size:
        raise ValueError("OUTPUT_EXCEEDS_BOUND")
    return raw


def _owner_required_literals(goal: str) -> dict[str, str]:
    """Parse all and only the independently recognizable owner postconditions.

    Ambiguous, partially parsed, contradictory or type-sensitive constraints
    must NOT be converted into a passing local-result claim.
    """
    matches = list(_EQUALS.finditer(goal))
    if (not 1 <= len(matches) <= 16
        or len(re.findall(r"\b(?:equal|equals)\s+to\b", goal, re.I)) != len(matches)):
        raise ValueError("OWNER_POSTCONDITIONS_INCOMPLETE")
    required = {}
    for match in matches:
        key, value = match.group(1), match.group(2)
        if (key in required and required[key] != value
            or value.casefold() in {"true", "false", "null"}):
            raise ValueError("OWNER_POSTCONDITIONS_AMBIGUOUS")
        required[key] = value
    return required


def _explicit_owner_local_contract(goal: str) -> dict | None:
    """Extract only an unambiguous, COMPLETE machine-checkable owner contract.

    This is NOT general language understanding: unknown or conjunctive owner
    work stays outside this narrow preflight. The same parsed contract is used
    to block misbound proposed effects and independently judge local outcomes.
    """
    text = goal.strip().rstrip(".!").strip()
    match = re.fullmatch(
        r"(?:please\s+)?compare\s+([A-Za-z0-9_.-]+\.csv)\s+"
        r"(?:with|against|to)\s+([A-Za-z0-9_.-]+\.csv)\s+"
        r"and\s+(?:report\s+(?:the\s+|all\s+)?"
        r"(?:differences|discrepancies)|"
        r"identify\s+(?:the\s+)?discrepancies)",
        text, flags=re.IGNORECASE,
    )
    if match:
        return {"objective": "compare_records",
                "reference": match.group(1), "observed": match.group(2)}
    match = re.fullmatch(
        r"(?:please\s+)?ensure\s+(?:(?:a|an)\s+)?"
        r"(?:sandbox|isolated)\s+(?:draft|candidate|proposal)\s+"
        r"of\s+([A-Za-z0-9_.-]+\.json)\s+has\s+(.+)",
        text, flags=re.IGNORECASE,
    )
    if not match:
        return None
    clauses = re.sub(
        r",\s*(?:preserving|keeping)\s+(?:the\s+)?"
        r"(?:existing|previous)\s+"
        r"(?:[A-Za-z_][A-Za-z0-9_-]*|entries)\s*$",
        "", match.group(2).strip(), flags=re.IGNORECASE,
    )
    fragments = re.split(r"\s+and\s+|\s*,\s*", clauses, flags=re.IGNORECASE)
    if not 1 <= len(fragments) <= 16:
        return None
    desired = {}
    for fragment in fragments:
        piece = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_-]{0,63})\s+"
            r"(?:equal|equals)\s+to\s+"
            r"([A-Za-z][A-Za-z0-9_-]{0,127})",
            fragment.strip(), flags=re.IGNORECASE,
        )
        if not piece:
            return None
        key, value = piece.group(1), piece.group(2)
        if key in desired and desired[key] != value:
            return None
        desired[key] = value
    return {"objective": "ensure_structure", "input": match.group(1),
            "desired": desired}


def _full_owner_scope_is_supported(goal: str, plan: dict) -> bool:
    """Only a complete known owner contract may certify a local artifact.

    Unrecognized language, partial clauses, ambiguous constraints or a
    model-selected different direction remain UNVERIFIED. Preserve the same
    local outcome grammar used before admission.
    """
    expected = _explicit_owner_local_contract(goal)
    if expected is None or plan["objective"] != expected["objective"]:
        return False
    spec = plan["child_source_spec"]
    if expected["objective"] == "compare_records":
        return (expected["reference"], expected["observed"]) == (
            spec["reference"], spec["observed"])
    return (expected["input"] == spec["input"]
            and expected["desired"] == spec["desired"])


def _native_local_postcondition(db_path: Path, workspace: Path,
                                fixtures: Path, root_id: str,
                                db: sqlite3.Connection, spec: dict) -> dict:
    """Reuse the same original-owner oracle for the new native/MCP pathway.

    Verified source/result mechanics are necessary, not sufficient. Only the
    independently complete named local comparison grammar is recognized.
    Composite, extra, remote and semantic goals remain UNVERIFIED.
    """
    from .native_decision import inspect_native_goal

    observed = inspect_native_goal(
        db_path, workspace, fixtures, root_id)
    if observed["status"] == "NATIVE_GRANT_REVOKED":
        return _unknown(root_id, "CURRENT_OWNER_AUTHORITY_UNAVAILABLE")
    # Fail closed for ANY status without a complete independently replayed
    # decision/evidence readback. Identity-only recovery intentionally lacks
    # "decisions" and may not be mistaken for a result oracle input.
    if (observed["status"] not in (
            "NATIVE_NEXT_DECISION_ADMISSIBLE", "NATIVE_AWAITING_WORKER",
            "NATIVE_DECISION_BUDGET_EXHAUSTED")
        or observed.get("original_goal") != spec.get("goal")):
        return _unknown(root_id, "GOAL_LINEAGE_OR_EVIDENCE_UNVERIFIABLE")
    decisions = observed["decisions"]
    # A complete EXACT owner postcondition may become true only after a
    # corrective decision. Preserve every prior replayed child/audit receipt;
    # a local mechanical PASS for an earlier, reversed input pairing remains
    # a historical subtask, NOT the original owner's final answer.
    if (not decisions or decisions[-1]["task_state"]
        not in ("NEEDS_REVIEW", "SANDBOX_VERIFIED")):
        return _unknown(root_id, "GOAL_LINEAGE_NOT_UNAMBIGUOUS")
    events = db.execute(
        "SELECT details FROM events WHERE task_id=? "
        "AND kind='NATIVE_DECISION_ADMITTED' ORDER BY event_id",
        (root_id,)).fetchall()
    if len(events) != len(decisions):
        return _unknown(root_id, "GOAL_LINEAGE_NOT_UNAMBIGUOUS")
    receipt = json.loads(events[-1]["details"])
    intent = receipt.get("proposal", {}).get("selected_intent")
    plan = compile_intent(intent)
    child_id = receipt.get("child_task_id")
    if (child_id != decisions[-1]["task_id"]
        or decisions[-1]["selected_objective"] != plan["objective"]):
        return _unknown(root_id, "GOAL_LINEAGE_NOT_UNAMBIGUOUS")
    if plan["objective"] == "ensure_structure":
        # Reuse the original owner-scope grammar, artifact inspection and
        # staged sandbox readback from the incumbent open_goal oracle.
        # A model prediction, a mechanically valid draft embedded in JSON,
        # or an unstaged NEEDS_REVIEW child never suffices.
        if not _full_owner_scope_is_supported(spec["goal"], plan):
            return _unknown(root_id, "OWNER_OBLIGATION_COVERAGE_INCOMPLETE")
        child = db.execute(
            "SELECT * FROM tasks WHERE task_id=?", (child_id,)).fetchone()
        source_spec = plan["child_source_spec"]
        if (child is None or child["state"] != "SANDBOX_VERIFIED"
            or child["goal_rev"] != db.execute(
                "SELECT goal_rev FROM tasks WHERE task_id=?",
                (root_id,)).fetchone()[0]
            or json.loads(child["source_spec"]) != source_spec):
            return _unknown(root_id, "SANDBOX_EFFECT_NOT_VERIFIED")
        staged = db.execute(
            "SELECT details FROM events WHERE task_id=? "
            "AND kind='SANDBOX_EFFECT_VERIFIED'", (child_id,)).fetchall()
        if len(staged) != 1:
            return _unknown(root_id, "SANDBOX_EFFECT_RECEIPT_MISSING")
        record_bytes = _bytes(
            workspace, "artifacts/" + child_id + ".json")
        if hashlib.sha256(record_bytes).hexdigest() != child["artifact_hash"]:
            return _unknown(root_id, "CANDIDATE_ARTIFACT_CHANGED")
        record = json.loads(record_bytes)
        if (record.get("task_id") != child_id
            or record.get("goal_spec") != source_spec
            or record.get("status") != "PROPOSAL_NOT_APPROVED"):
            return _unknown(root_id, "CANDIDATE_RECEIPT_CONTRADICTION")
        original = safe_fixture(fixtures, source_spec["input"])
        if hashlib.sha256(original).hexdigest() != record.get("source_sha256"):
            return _unknown(root_id, "OWNER_SOURCE_CHANGED")
        candidate_bytes = _bytes(
            workspace, "sandbox/" + child_id + ".candidate")
        candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()
        event_receipt = json.loads(staged[0]["details"])
        if (candidate_sha != record.get("candidate_sha256")
            or candidate_sha != event_receipt.get("effect_sha256")
            or event_receipt.get("scope") != "isolated_workspace_only"
            or not _constraints(source_spec, original, candidate_bytes)):
            return _unknown(root_id, "INDEPENDENT_SANDBOX_POSTCONDITION_FAILED")
        return {
            "root_task_id": root_id,
            "status": "LOCAL_OWNER_RESULT_VERIFIED",
            "outcome_scope": "ORIGINAL_SANDBOX_DRAFT_POSTCONDITION",
            "local_owner_outcome_verified": True,
            "business_outcome_verified": False,
            "real_external_outcome_verified": False,
            "evidence_task_id": child_id,
            "evidence_sha256": candidate_sha,
        }
    if plan["objective"] != "compare_records":
        return _unknown(root_id, "NO_INDEPENDENT_OWNER_POSTCONDITION")
    if not _full_owner_scope_is_supported(spec["goal"], plan):
        return _unknown(root_id, "OWNER_OBLIGATION_COVERAGE_INCOMPLETE")
    audit = audit_stored_report(
        db_path, workspace, fixtures, child_id)
    if (audit.get("status") != "REPORT_MECHANICALLY_VERIFIED"
        or decisions[-1]["mechanical_verdict"] !=
           "REPORT_MECHANICALLY_VERIFIED"):
        return _unknown(root_id, "COMPARISON_OUTPUT_NOT_INDEPENDENTLY_VALID")
    return {
        "root_task_id": root_id,
        "status": "LOCAL_OWNER_RESULT_VERIFIED",
        "outcome_scope": "ORIGINAL_NAMED_READONLY_COMPARISON_REPORT",
        "local_owner_outcome_verified": True,
        "business_outcome_verified": False,
        "real_external_outcome_verified": False,
        "evidence_task_id": child_id,
        "evidence_sha256": audit["artifact_sha256"],
    }


def inspect_owner_local_outcome(db_path: Path, workspace: Path, fixtures: Path,
                                root_id: str) -> dict:
    """Fresh, read-only outcome judgment, replayed from independent bytes.

    Two owner-meaningful LOCAL outcomes are supported: an explicit named
    comparison report, and an explicitly requested sandbox JSON draft.
    A plan, research proposal, search hit, hash-only mechanical test, or
    unspecified effect is NEVER a verified owner result.
    """
    failure = _unknown(root_id, "NO_INDEPENDENT_OWNER_POSTCONDITION")
    if (not isinstance(root_id, str) or not re.fullmatch(r"[0-9a-f]{32}", root_id)
        or not db_path.is_file() or db_path.is_symlink() or workspace.is_symlink()):
        return failure
    try:
        with readonly_snapshot(db_path) as db:
            owner = db.execute(
                "SELECT * FROM authority WHERE singleton=1").fetchone()
            root = db.execute(
                "SELECT * FROM tasks WHERE task_id=?", (root_id,)).fetchone()
            if not root or not owner:
                return failure
            # Revocation invalidates a cached positive result; source output
            # is never itself a grant or current owner acceptance.
            if (root["goal_rev"] != owner["goal_rev"]
                or root["grant_rev"] != owner["grant_rev"]
                or owner["write_allowed"] != 1):
                return _unknown(root_id, "CURRENT_OWNER_AUTHORITY_UNAVAILABLE")
            spec = json.loads(root["source_spec"])
            if isinstance(spec, dict) and spec.get("kind") == "native_goal":
                if root["parent_task"] is not None or root["state"] != "DECOMPOSED":
                    return _unknown(root_id, "ORIGINAL_GOAL_NOT_ACTIVE")
                return _native_local_postcondition(
                    db_path, workspace, fixtures, root_id, db, spec)
            if (not isinstance(spec, dict) or spec.get("kind") != "open_goal"
                or root["state"] != "DECOMPOSED"):
                return failure
            from .open_goal import validate_open_goal
            validate_open_goal(spec)
            goal = spec["goal"]
            events = db.execute(
                "SELECT details FROM events WHERE task_id=? "
                "AND kind='OPEN_GOAL_DECOMPOSED'", (root_id,)).fetchall()
            children = db.execute(
                "SELECT * FROM tasks WHERE parent_task=?", (root_id,)).fetchall()
            if len(events) != 1 or len(children) != 1:
                return _unknown(root_id, "GOAL_LINEAGE_NOT_UNAMBIGUOUS")
            receipt = json.loads(events[0]["details"])
            child = children[0]
            if (not isinstance(receipt, dict)
                or receipt.get("child_task_id") != child["task_id"]
                or receipt.get("semantic_approval") is not False
                or receipt.get("real_owner_outcome_verified") is not False
                or not isinstance(receipt.get("model_candidate"), dict)
                or child["goal_rev"] != root["goal_rev"]
                or child["grant_rev"] != root["grant_rev"]):
                return _unknown(root_id, "GOAL_PROVENANCE_UNVERIFIABLE")
            intent = receipt["model_candidate"].get("intent")
            plan = compile_intent(intent)
            if (plan != receipt.get("plan") or
                json.loads(child["source_spec"]) != plan["child_source_spec"]):
                return _unknown(root_id, "ORIGINAL_GOAL_PLAN_CONTRADICTED")
            if plan["objective"] == "compare_records":
                if not _full_owner_scope_is_supported(goal, plan):
                    return _unknown(root_id, "OWNER_OBLIGATION_COVERAGE_INCOMPLETE")
                order = _COMPARE.search(goal)
                sources = plan["child_source_spec"]
                if (order is None
                    or (order.group(1), order.group(2)) !=
                      (sources["reference"], sources["observed"])):
                    return _unknown(root_id, "COMPARISON_NOT_OWNER_GROUNDED")
                audit = audit_stored_report(
                    db_path, workspace, fixtures, child["task_id"])
                if audit.get("status") != "REPORT_MECHANICALLY_VERIFIED":
                    return _unknown(root_id, "COMPARISON_OUTPUT_NOT_INDEPENDENTLY_VALID")
                return {
                    "root_task_id": root_id,
                    "status": "LOCAL_OWNER_RESULT_VERIFIED",
                    "outcome_scope": "ORIGINAL_NAMED_READONLY_COMPARISON_REPORT",
                    "local_owner_outcome_verified": True,
                    "business_outcome_verified": False,
                    "real_external_outcome_verified": False,
                    "evidence_task_id": child["task_id"],
                    "evidence_sha256": audit["artifact_sha256"],
                }

            if plan["objective"] != "ensure_structure":
                return failure
            # A staging adapter cannot satisfy an instruction to modify the
            # original source. Only an explicitly requested sandbox DRAFT
            # authorizes this precise local result interpretation.
            if (not re.search(r"\b(?:sandbox|isolated)\b", goal, re.I)
                or not re.search(r"\b(?:draft|candidate|proposal)\b", goal, re.I)):
                return _unknown(root_id, "SANDBOX_DRAFT_NOT_ORIGINAL_OWNER_GOAL")
            desired = _owner_required_literals(goal)
            if not _full_owner_scope_is_supported(goal, plan):
                return _unknown(root_id, "OWNER_OBLIGATION_COVERAGE_INCOMPLETE")
            goal_spec = plan["child_source_spec"]
            if (goal_spec["goal_type"] != "json_keys"
                or goal_spec["desired"] != desired
                or not re.search(
                    r"(?<![A-Za-z0-9_.-])" + re.escape(goal_spec["input"])
                    + r"(?![A-Za-z0-9_.-])", goal, re.I)):
                return _unknown(root_id, "ORIGINAL_ACCEPTANCE_NOT_PRESERVED")
            if child["state"] != "SANDBOX_VERIFIED":
                return _unknown(root_id, "SANDBOX_EFFECT_NOT_VERIFIED")
            effects = db.execute(
                "SELECT details FROM events WHERE task_id=? "
                "AND kind='SANDBOX_EFFECT_VERIFIED'",
                (child["task_id"],)).fetchall()
            if len(effects) != 1:
                return _unknown(root_id, "SANDBOX_EFFECT_RECEIPT_MISSING")
            artifact = _bytes(
                workspace, "artifacts/" + child["task_id"] + ".json")
            if hashlib.sha256(artifact).hexdigest() != child["artifact_hash"]:
                return _unknown(root_id, "CANDIDATE_ARTIFACT_CHANGED")
            record = json.loads(artifact)
            if (record.get("task_id") != child["task_id"]
                or record.get("goal_spec") != goal_spec
                or record.get("status") != "PROPOSAL_NOT_APPROVED"):
                return _unknown(root_id, "CANDIDATE_RECEIPT_CONTRADICTION")
            original = safe_fixture(fixtures, goal_spec["input"])
            if hashlib.sha256(original).hexdigest() != record.get("source_sha256"):
                return _unknown(root_id, "OWNER_SOURCE_CHANGED")
            actual = _bytes(
                workspace, "sandbox/" + child["task_id"] + ".candidate")
            result_sha = hashlib.sha256(actual).hexdigest()
            effect = json.loads(effects[0]["details"])
            if (record.get("candidate_sha256") != result_sha
                or effect.get("effect_sha256") != result_sha
                or effect.get("scope") != "isolated_workspace_only"
                or not _constraints(goal_spec, original, actual)):
                return _unknown(root_id, "INDEPENDENT_SANDBOX_POSTCONDITION_FAILED")
            return {
                "root_task_id": root_id,
                "status": "LOCAL_OWNER_RESULT_VERIFIED",
                "outcome_scope": "ORIGINAL_SANDBOX_DRAFT_POSTCONDITION",
                "local_owner_outcome_verified": True,
                "business_outcome_verified": False,
                "real_external_outcome_verified": False,
                "evidence_task_id": child["task_id"],
                "evidence_sha256": result_sha,
            }
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            sqlite3.Error, UnicodeError, SourceUnavailable):
        return failure
