"""Restricted, source-derived owner-outcome checks, independent of agent code.

Only proves bounded synthetic JSON and CSV output postconditions. Does NOT
verify external business effects, authority, or unattended autonomy.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re

_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
_LIMIT = 128 * 1024


def _json_object(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("DUPLICATE_KEY")
            result[k] = v
        return result
    parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(parsed, dict):
        raise ValueError("NOT_OBJECT")
    return parsed


def _csv_rows(raw: bytes) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True))
    if not rows or not rows[0] or len(set(rows[0])) != len(rows[0]):
        raise ValueError("BAD_HEADER")
    if any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("NONRECTANGULAR")
    return rows


def _literal(value) -> bool:
    return value is None or type(value) in (str, bool, int) and (
        not isinstance(value, str) or len(value) <= 256)


def evaluate_outcome(contract: dict, original: bytes, candidate: bytes) -> dict:
    """Owner-pinned bytes, not planner status, decide a narrow test outcome."""
    fail = {"status": "NOT_ACCEPTED", "business_outcome_verified": False,
            "authorizes_mutation": False, "evidence_class": "SYNTHETIC_LOCAL_TARGET"}
    try:
        if not isinstance(contract, dict) or set(contract) != {
            "schema_version", "goal_id", "kind", "expected", "original_sha256",
            "allowed_effect"}:
            raise ValueError("BAD_CONTRACT")
        if (contract["schema_version"] != 1
            or not isinstance(contract["goal_id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", contract["goal_id"])
            or contract["kind"] not in ("json_fields", "csv_columns")
            or contract["allowed_effect"] != "LOCAL_CANDIDATE_ONLY"
            or not isinstance(contract["original_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", contract["original_sha256"])
            or not isinstance(contract["expected"], dict)
            or not 1 <= len(contract["expected"]) <= 16
            or any(not isinstance(k, str) or not _FIELD.fullmatch(k)
                   for k in contract["expected"])):
            raise ValueError("BAD_CONTRACT")
        if (not isinstance(original, bytes) or not isinstance(candidate, bytes)
            or len(original) > _LIMIT or len(candidate) > _LIMIT):
            raise ValueError("BYTE_BOUND")
        if hashlib.sha256(original).hexdigest() != contract["original_sha256"]:
            raise ValueError("ORIGINAL_DRIFT")
        expected = contract["expected"]
        if contract["kind"] == "json_fields":
            if not all(_literal(v) for v in expected.values()):
                raise ValueError("BAD_CONTRACT")
            before, after = _json_object(original), _json_object(candidate)
            if set(after) != set(before) | set(expected):
                raise ValueError("KEY_SET")
            if any(k not in after or type(after[k]) is not type(v) or after[k] != v
                   for k, v in before.items()):
                raise ValueError("ORIGINAL_CHANGED")
            if any(k not in after or type(after[k]) is not type(v) or after[k] != v
                   for k, v in expected.items()):
                raise ValueError("TARGET_MISSED")
        else:
            if not all(isinstance(v, str) and len(v) <= 128 for v in expected.values()):
                raise ValueError("BAD_CONTRACT")
            before, after = _csv_rows(original), _csv_rows(candidate)
            columns = list(expected)
            if set(columns) & set(before[0]):
                raise ValueError("UNSUPPORTED_EXISTING_COLUMN_GOAL")
            if after[0] != before[0] + columns or len(before) != len(after):
                raise ValueError("COLUMN_LAYOUT")
            for row_a, row_b in zip(before[1:], after[1:]):
                if row_b != row_a + [expected[col] for col in columns]:
                    raise ValueError("ROW_EFFECT")
        return {**fail, "status": "SYNTHETIC_POSTCONDITION_MET",
                "reason": "OWNER_PINNED_LOCAL_POSTCONDITION",
                "original_sha256": contract["original_sha256"],
                "candidate_sha256": hashlib.sha256(candidate).hexdigest()}
    except (ValueError, TypeError, KeyError, UnicodeError, csv.Error) as exc:
        return {**fail, "reason": str(exc)[:90]}


def evaluate_shared_record_goal(contract: dict, source_kind: str,
                                original: bytes, candidate: bytes) -> dict:
    """Different file families can satisfy one pinned record-level outcome.

    A reference acceptance decision, not an admission/switch decision.
    The owner contract is fixed before execution; planner status is ignored.
    """
    fail = {"status": "NOT_ACCEPTED", "business_outcome_verified": False,
            "authorizes_mutation": False, "evidence_class": "SYNTHETIC_SHARED_RECORD"}
    try:
        if (not isinstance(contract, dict) or set(contract) != {
            "schema_version", "goal_id", "canonical_record", "source_sha256",
            "allowed_effect"} or contract.get("schema_version") != 1
            or contract.get("allowed_effect") != "LOCAL_CANDIDATE_ONLY"):
            raise ValueError("BAD_SHARED_CONTRACT")
        if (not isinstance(contract.get("goal_id"), str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", contract["goal_id"])):
            raise ValueError("BAD_GOAL_ID")
        canonical = contract["canonical_record"]
        if (not isinstance(canonical, dict) or not 1 <= len(canonical) <= 16
            or any(not isinstance(k, str) or not _FIELD.fullmatch(k)
                   or not isinstance(v, str) or len(v) > 256
                   for k, v in canonical.items())
            or not isinstance(original, bytes) or not isinstance(candidate, bytes)
            or len(original) > _LIMIT or len(candidate) > _LIMIT):
            raise ValueError("INVALID_RECORD")
        pins = contract["source_sha256"]
        if (not isinstance(pins, dict)
            or set(pins) != {"json_keys", "csv_columns"}
            or any(not isinstance(s, str) or not re.fullmatch(r"[0-9a-f]{64}", s)
                   for s in pins.values())
            or source_kind not in pins):
            raise ValueError("BAD_SOURCE_PINS")
        if hashlib.sha256(original).hexdigest() != pins[source_kind]:
            raise ValueError("ORIGINAL_DRIFT")
        if source_kind == "json_keys":
            old = _json_object(original)
            new = _json_object(candidate)
            if any(not isinstance(v, str) for v in old.values()):
                raise ValueError("SOURCE_NOT_STRING_RECORD")
        else:
            old_rows = _csv_rows(original)
            new_rows = _csv_rows(candidate)
            if len(old_rows) != 2 or len(new_rows) != 2:
                raise ValueError("NOT_SINGLE_RECORD")
            old = dict(zip(old_rows[0], old_rows[1]))
            new = dict(zip(new_rows[0], new_rows[1]))
        if (not all(k in new and new[k] == v for k, v in old.items())
            or new != canonical):
            raise ValueError("SHARED_GOAL_MISSED")
        return {**fail, "status": "SYNTHETIC_SHARED_GOAL_MET",
                "goal_id": contract["goal_id"], "source_kind": source_kind,
                "candidate_sha256": hashlib.sha256(candidate).hexdigest()}
    except (ValueError, TypeError, KeyError, UnicodeError, csv.Error) as exc:
        return {**fail, "reason": str(exc)[:90]}
