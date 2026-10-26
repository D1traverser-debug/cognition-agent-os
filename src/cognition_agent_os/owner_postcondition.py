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


def _full_owner_scope_is_supported(goal: str, plan: dict) -> bool:
    """Prove coverage of the *whole* admitted goal, not one matching clause.

    This deliberately accepts only two small owner-outcome grammars. A
    partially parsed extra deliverable cannot be accepted just because the
    chosen child's artifact is mechanically correct. Unsupported language
    is unverified, not an instruction to grant another capability.
    """
    text = goal.strip().rstrip(".!").strip()
    if plan["objective"] == "compare_records":
        match = re.fullmatch(
            r"(?:please\s+)?compare\s+([A-Za-z0-9_.-]+\.csv)\s+"
            r"(?:with|against|to)\s+([A-Za-z0-9_.-]+\.csv)\s+"
            r"and\s+(?:report\s+(?:the\s+|all\s+)?"
            r"(?:differences|discrepancies)|"
            r"identify\s+(?:the\s+)?discrepancies)",
            text, flags=re.IGNORECASE,
        )
        spec = plan["child_source_spec"]
        return bool(match and
                    (match.group(1), match.group(2)) ==
                    (spec["reference"], spec["observed"]))
    if plan["objective"] != "ensure_structure":
        return False
    match = re.fullmatch(
        r"(?:please\s+)?ensure\s+(?:a\s+)?"
        r"(?:sandbox|isolated)\s+(?:draft|candidate|proposal)\s+"
        r"of\s+([A-Za-z0-9_.-]+\.json)\s+has\s+(.+)",
        text, flags=re.IGNORECASE,
    )
    if not match or match.group(1) != plan["child_source_spec"]["input"]:
        return False
    clauses = match.group(2).strip()
    # Preservation is checked from real source/output by _constraints.
    # Only a bounded, explicitly named non-mutation qualifier is covered.
    clauses = re.sub(
        r",\s*(?:preserving|keeping)\s+(?:the\s+)?"
        r"(?:existing|previous)\s+"
        r"(?:[A-Za-z_][A-Za-z0-9_-]*|entries)\s*$",
        "", clauses, flags=re.IGNORECASE,
    )
    fragments = re.split(r"\s+and\s+|\s*,\s*", clauses, flags=re.IGNORECASE)
    if not 1 <= len(fragments) <= 16:
        return False
    accepted = {}
    for clause in fragments:
        piece = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_-]{0,63})\s+"
            r"(?:equal|equals)\s+to\s+"
            r"([A-Za-z][A-Za-z0-9_-]{0,127})",
            clause.strip(), flags=re.IGNORECASE,
        )
        if not piece:
            return False
        key, value = piece.group(1), piece.group(2)
        if key in accepted and accepted[key] != value:
            return False
        accepted[key] = value
    return accepted == plan["child_source_spec"]["desired"]


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
        with closing(sqlite3.connect(
            db_path.resolve(strict=True).as_uri() + "?mode=ro",
            uri=True, timeout=5,
        )) as db:
            db.row_factory = sqlite3.Row
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
