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


def assess_route_fitness(route_entries: list[dict]) -> dict:
    """A pair of labels never suffices to prove distinct same-goal methods.

    Only rejects known invalid pairs. Future positive admission requires
    owner-pinned equivalence and independently validated different mechanisms.
    """
    result = {"status": "NO_PROVEN_ALTERNATIVE", "safe_to_autoswitch": False}
    if (not isinstance(route_entries, list) or len(route_entries) != 2
        or any(not isinstance(e, dict) or set(e) != {"route", "intent"}
               or not isinstance(e["intent"], dict) for e in route_entries)):
        return {**result, "reason": "INVALID_PAIR"}
    x, y = (e["intent"] for e in route_entries)
    if x == y:
        return {**result, "reason": "DUPLICATE_METHOD"}
    if x.get("objective") != y.get("objective"):
        return {**result, "reason": "DIFFERENT_OBJECTIVES"}
    if x.get("resources") != y.get("resources") or x.get("requirements") != y.get("requirements"):
        return {**result, "reason": "DIFFERENT_BOUND_TARGETS"}
    return {**result, "reason": "NO_INDEPENDENT_EQUIVALENCE_EVIDENCE"}
