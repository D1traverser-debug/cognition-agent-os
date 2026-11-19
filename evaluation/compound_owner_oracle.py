"""Independent compound owner-outcome oracle for bounded local tasks.

This evaluator is intentionally outside the CAOS runtime. It does not import
planner, Host, Worker, intent compiler, or owner-postcondition code. The
expected owner contract and ledger-lineage snapshot are supplied by the
benchmark harness, never by the model. It grades two local candidate effects
and never authorizes writes or claims a real business outcome.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from typing import Any

try:  # Package import in the repository; direct module import in isolated tests.
    from .owner_outcome_oracle import evaluate_outcome
except ImportError:  # pragma: no cover - direct evaluation harnesses.
    from owner_outcome_oracle import evaluate_outcome

_LIMIT = 128 * 1024
_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
_GOAL_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_TASK_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _json_object(raw: bytes) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(parsed, dict):
        raise ValueError("JSON_REPORT_NOT_OBJECT")
    return parsed


def _csv_table(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(raw) > _LIMIT:
        raise ValueError("CSV_BYTE_BOUND")
    rows = list(csv.reader(
        io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    if (not rows or not 1 <= len(rows[0]) <= 24
            or len(rows) > 251 or len(set(rows[0])) != len(rows[0])
            or any(not isinstance(field, str) or not _FIELD.fullmatch(field)
                   for field in rows[0])
            or any(len(row) != len(rows[0]) for row in rows[1:])):
        raise ValueError("CSV_BAD_HEADER_OR_ROWS")
    header = rows[0]
    records = [dict(zip(header, row)) for row in rows[1:]]
    return header, records


def _safe_basename(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and value not in (".", "..")
        and "/" not in value
        and "\\" not in value
        and ":" not in value
        and ".." not in value
    )


def _expected_reconciliation(reference: bytes, observed: bytes, key: str) -> dict[str, Any]:
    header_ref, rows_ref = _csv_table(reference)
    header_obs, rows_obs = _csv_table(observed)
    if key not in header_ref or key not in header_obs:
        raise ValueError("CSV_OWNER_KEY_MISSING")
    by_ref: dict[str, dict[str, str]] = {}
    by_obs: dict[str, dict[str, str]] = {}
    for row in rows_ref:
        identity = row[key]
        if not identity or identity in by_ref:
            raise ValueError("CSV_REFERENCE_KEY_NOT_UNIQUE")
        by_ref[identity] = row
    for row in rows_obs:
        identity = row[key]
        if not identity or identity in by_obs:
            raise ValueError("CSV_OBSERVED_KEY_NOT_UNIQUE")
        by_obs[identity] = row

    discrepancies: list[dict[str, str]] = []
    for identity in sorted(by_ref.keys() - by_obs.keys()):
        discrepancies.append({"kind": "missing_observed", "key": identity})
    for identity in sorted(by_obs.keys() - by_ref.keys()):
        discrepancies.append({"kind": "unexpected_observed", "key": identity})
    common_fields = sorted((set(header_ref) & set(header_obs)) - {key})
    for identity in sorted(by_ref.keys() & by_obs.keys()):
        for field in common_fields:
            if by_ref[identity][field] != by_obs[identity][field]:
                discrepancies.append({
                    "kind": "field_mismatch",
                    "key": identity,
                    "field": field,
                    "reference": by_ref[identity][field],
                    "observed": by_obs[identity][field],
                })

    if len(discrepancies) > 1200:
        raise ValueError("CSV_DISCREPANCY_BOUND")
    reference_only = sorted(set(header_ref) - set(header_obs))
    observed_only = sorted(set(header_obs) - set(header_ref))
    return {
        "status": "DISCREPANCIES_FOUND" if discrepancies or reference_only or observed_only else "CONSISTENT",
        "selected_key": key,
        "reference_only_columns": reference_only,
        "observed_only_columns": observed_only,
        "discrepancies": discrepancies,
        "rows_reference": len(rows_ref),
        "rows_observed": len(rows_obs),
    }


def _validate_lineage(lineage: object, contract: dict) -> dict[str, Any]:
    required = {
        "root_task_id", "root_parent_task", "root_kind", "owner_goal_sha256",
        "goal_rev", "grant_rev", "ledger_child_task_count", "child_order",
        "children",
    }
    if not isinstance(lineage, dict) or set(lineage) != required:
        raise ValueError("BAD_EXPECTED_LINEAGE")
    root_id = lineage["root_task_id"]
    if (not isinstance(root_id, str) or not _TASK_ID.fullmatch(root_id)
            or lineage["root_parent_task"] is not None
            or lineage["root_kind"] not in ("native_goal", "open_goal")
            or lineage["owner_goal_sha256"] != contract["owner_goal_sha256"]
            or not isinstance(lineage["owner_goal_sha256"], str)
            or not _SHA256.fullmatch(lineage["owner_goal_sha256"])
            or type(lineage["goal_rev"]) is not int or lineage["goal_rev"] < 1
            or type(lineage["grant_rev"]) is not int or lineage["grant_rev"] < 1):
        raise ValueError("BAD_EXPECTED_ROOT_LINEAGE")
    children = lineage["children"]
    child_count = lineage["ledger_child_task_count"]
    if (type(child_count) is not int or child_count < 0
            or not isinstance(children, dict)
            or set(children) != {"csv_report", "json_draft"}):
        raise ValueError("BAD_EXPECTED_CHILDREN")
    if child_count < 2 or any(
            children[label] is None for label in ("csv_report", "json_draft")):
        raise ValueError("MISSING_REQUIRED_CHILD_TASK")
    if child_count > 2:
        raise ValueError("UNACCOUNTED_CHILD_TASKS")
    expected_states = {"csv_report": "NEEDS_REVIEW", "json_draft": "SANDBOX_VERIFIED"}
    ids = []
    for label, child in children.items():
        if not isinstance(child, dict) or set(child) != {
            "task_id", "parent_task", "goal_rev", "grant_rev", "state", "artifact_sha256"
        }:
            raise ValueError("BAD_EXPECTED_CHILD_LINEAGE")
        if (not isinstance(child["task_id"], str)
                or not _TASK_ID.fullmatch(child["task_id"])
                or child["parent_task"] != root_id
                or type(child["goal_rev"]) is not int
                or child["goal_rev"] != lineage["goal_rev"]
                or type(child["grant_rev"]) is not int
                or child["grant_rev"] != lineage["grant_rev"]
                or child["state"] != expected_states[label]
                or not isinstance(child["artifact_sha256"], str)
                or not _SHA256.fullmatch(child["artifact_sha256"])):
            raise ValueError("CHILD_LINEAGE_MISMATCH")
        ids.append(child["task_id"])
    if len(set(ids)) != 2 or root_id in ids:
        raise ValueError("CHILD_TASK_ID_COLLISION")
    order = lineage["child_order"]
    if (not isinstance(order, list) or len(order) != 2
            or order != [
                children["csv_report"]["task_id"],
                children["json_draft"]["task_id"],
            ]):
        raise ValueError("CHILD_ORDER_MISMATCH")
    return lineage


def evaluate_compound_owner_goal(
    contract: dict,
    current_sources: dict[str, bytes],
    csv_report: bytes,
    json_artifact: bytes,
    json_candidate: bytes,
    expected_lineage: dict,
) -> dict[str, Any]:
    """Grade a complete two-effect goal from source, artifact and ledger bytes.

    Required effects:
      1. A source-pinned CSV discrepancy report from the expected child task.
      2. A separately staged JSON draft from the expected child task, preserving
         all original fields and setting every owner-pinned requirement.

    expected_lineage MUST be read independently from the initialized SQLite
    ledger by the harness. It binds both child IDs to the same original
    owner-goal root (native_goal or incumbent open_goal), goal revision,
    grant revision and artifact hashes. It is
    not a model claim and it does not grant authority.

    This evaluator ignores Host/model success labels and report claims about
    their own oracle. It recomputes the CSV result and delegates only the narrow
    JSON byte postcondition to the separate standard-library evaluator. A
    partial result is never a whole-goal pass.
    """
    failure: dict[str, Any] = {
        "status": "NOT_ACCEPTED",
        "synthetic_local_postconditions_met": False,
        "owner_outcome_verified": False,
        "business_outcome_verified": False,
        "real_external_outcome_verified": False,
        "authorizes_mutation": False,
        "evidence_class": "SYNTHETIC_COMPOUND_LOCAL_OWNER",
    }
    try:
        required = {
            "schema_version", "goal_id", "kind", "owner_goal_sha256",
            "source_paths", "source_sha256", "record_key", "draft_fields",
            "allowed_effect",
        }
        if not isinstance(contract, dict) or set(contract) != required:
            raise ValueError("BAD_COMPOUND_CONTRACT")
        if (
            type(contract["schema_version"]) is not int
            or contract["schema_version"] != 1
            or not isinstance(contract["goal_id"], str)
            or not _GOAL_ID.fullmatch(contract["goal_id"])
            or contract["kind"] != "csv_reconciliation_plus_json_draft"
            or contract["allowed_effect"] != "LOCAL_CANDIDATES_ONLY"
            or not isinstance(contract["owner_goal_sha256"], str)
            or not _SHA256.fullmatch(contract["owner_goal_sha256"])
            or not isinstance(contract["record_key"], str)
            or not _FIELD.fullmatch(contract["record_key"])
            or not isinstance(contract["draft_fields"], dict)
            or not 1 <= len(contract["draft_fields"]) <= 16
            or any(not isinstance(k, str) or not _FIELD.fullmatch(k)
                   for k in contract["draft_fields"])
        ):
            raise ValueError("BAD_COMPOUND_CONTRACT")

        lineage = _validate_lineage(expected_lineage, contract)
        source_paths = contract["source_paths"]
        if not isinstance(source_paths, dict) or set(source_paths) != {
            "reference", "observed", "draft"
        }:
            raise ValueError("BAD_SOURCE_PATHS")
        if any(not _safe_basename(value) for value in source_paths.values()):
            raise ValueError("UNSAFE_SOURCE_PATH")
        if len(set(source_paths.values())) != 3:
            raise ValueError("SOURCE_PATH_COLLISION")

        pins = contract["source_sha256"]
        if not isinstance(pins, dict) or set(pins) != set(source_paths.values()):
            raise ValueError("BAD_SOURCE_PINS")
        if any(not isinstance(value, str) or not _SHA256.fullmatch(value)
               for value in pins.values()):
            raise ValueError("BAD_SOURCE_PINS")
        if not isinstance(current_sources, dict) or set(current_sources) != set(source_paths.values()):
            raise ValueError("SOURCE_SET_MISMATCH")
        if any(not isinstance(raw, bytes) or len(raw) > _LIMIT
               for raw in current_sources.values()):
            raise ValueError("SOURCE_BYTE_BOUND")
        if (not isinstance(csv_report, bytes) or not isinstance(json_artifact, bytes)
                or not isinstance(json_candidate, bytes)):
            raise ValueError("CANDIDATE_NOT_BYTES")
        if any(len(raw) > _LIMIT for raw in (csv_report, json_artifact, json_candidate)):
            raise ValueError("CANDIDATE_BYTE_BOUND")

        for path, raw in current_sources.items():
            if hashlib.sha256(raw).hexdigest() != pins[path]:
                raise ValueError("OWNER_SOURCE_DRIFT")

        reference_path = source_paths["reference"]
        observed_path = source_paths["observed"]
        draft_path = source_paths["draft"]
        reference = current_sources[reference_path]
        observed = current_sources[observed_path]
        original_draft = current_sources[draft_path]

        expected_csv = _expected_reconciliation(
            reference, observed, contract["record_key"]
        )
        report = _json_object(csv_report)
        csv_child = lineage["children"]["csv_report"]
        if hashlib.sha256(csv_report).hexdigest() != csv_child["artifact_sha256"]:
            raise ValueError("CSV_REPORT_LEDGER_HASH_MISMATCH")
        if (
            report.get("task_id") != csv_child["task_id"]
            or type(report.get("goal_rev")) is not int
            or report["goal_rev"] != lineage["goal_rev"]
            or report.get("source_spec") != {
                "kind": "record_reconciliation",
                "reference": reference_path,
                "observed": observed_path,
                "objective": "identify_discrepancies",
            }
            or report.get("source_sha256") != {
                "reference": pins[reference_path],
                "observed": pins[observed_path],
            }
            or report.get("status") != "PROPOSAL_NOT_APPROVED"
        ):
            raise ValueError("CSV_REPORT_PROVENANCE_MISMATCH")
        proposal = report.get("proposal")
        if not isinstance(proposal, dict):
            raise ValueError("CSV_REPORT_PROPOSAL_MISSING")
        if proposal.get("relationship_contract_sha256") is not None:
            raise ValueError("CSV_REPORT_UNEXPECTED_RELATIONSHIP_CONTRACT")
        for field, expected in expected_csv.items():
            if proposal.get(field) != expected:
                raise ValueError("CSV_REPORT_OWNER_POSTCONDITION_MISSED")

        draft_artifact = _json_object(json_artifact)
        json_child = lineage["children"]["json_draft"]
        if hashlib.sha256(json_artifact).hexdigest() != json_child["artifact_sha256"]:
            raise ValueError("JSON_ARTIFACT_LEDGER_HASH_MISMATCH")
        expected_json_spec = {
            "kind": "goal_case",
            "goal_type": "json_keys",
            "input": draft_path,
            "desired": contract["draft_fields"],
        }
        if (
            draft_artifact.get("task_id") != json_child["task_id"]
            or type(draft_artifact.get("goal_rev")) is not int
            or draft_artifact["goal_rev"] != lineage["goal_rev"]
            or draft_artifact.get("source_sha256") != pins[draft_path]
            or draft_artifact.get("goal_spec") != expected_json_spec
            or draft_artifact.get("candidate_sha256") != hashlib.sha256(json_candidate).hexdigest()
            or draft_artifact.get("candidate_text") != json_candidate.decode("utf-8")
            or draft_artifact.get("status") != "PROPOSAL_NOT_APPROVED"
        ):
            raise ValueError("JSON_DRAFT_PROVENANCE_MISMATCH")

        json_contract = {
            "schema_version": 1,
            "goal_id": contract["goal_id"][:58] + "-json",
            "kind": "json_fields",
            "expected": contract["draft_fields"],
            "original_sha256": pins[draft_path],
            "allowed_effect": "LOCAL_CANDIDATE_ONLY",
        }
        json_result = evaluate_outcome(json_contract, original_draft, json_candidate)
        if json_result.get("status") != "SYNTHETIC_POSTCONDITION_MET":
            raise ValueError("JSON_DRAFT_OWNER_POSTCONDITION_MISSED")

        return {
            **failure,
            "status": "SYNTHETIC_COMPOUND_OWNER_GOAL_MET",
            "synthetic_local_postconditions_met": True,
            "goal_id": contract["goal_id"],
            "root_task_id": lineage["root_task_id"],
            "reason": "BOTH_INDEPENDENT_LOCAL_POSTCONDITIONS_MET",
            "subresults": {
                "csv_reconciliation": {
                    "status": "PASS",
                    "report_task_id": report["task_id"],
                    "source_sha256": {
                        "reference": pins[reference_path],
                        "observed": pins[observed_path],
                    },
                    "discrepancies_count": len(expected_csv["discrepancies"]),
                },
                "json_draft": {
                    "status": "PASS",
                    "candidate_sha256": json_result["candidate_sha256"],
                    "source_sha256": pins[draft_path],
                },
            },
        }
    except (ValueError, TypeError, KeyError, UnicodeError, csv.Error) as exc:
        return {**failure, "reason": str(exc)[:100]}
