"""Independent, offline business-outcome oracles for CAOS S1 calibration.

This module deliberately imports no CAOS planner, Host, ledger, or model code.
It grades candidate bytes against pre-pinned owner contracts and source bytes,
then requires a separately supplied consumer readback. Synthetic PASS is never
reported as a real business outcome and never authorizes an external effect.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MAX_SOURCE_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024
MAX_READBACK_BYTES = 16 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
_PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|PLACEHOLDER)\b|待补充|待确认", re.I)

PASS = "PASS"
FAIL = "FAIL"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json_object(raw: bytes | None, *, limit: int, label: str) -> dict:
    if not isinstance(raw, bytes) or not raw or len(raw) > limit:
        raise ValueError(f"{label}_MISSING_OR_OUT_OF_BOUNDS")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ValueError(f"{label}_UNREADABLE") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_NOT_OBJECT")
    return value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _result(verdict: str, case_id: str | None, reason: str,
            checks: dict[str, Any] | None = None) -> dict:
    return {
        "verdict": verdict,
        "case_id": case_id,
        "reason": reason,
        "checks": checks or {},
        "evidence_class": "SYNTHETIC_CALIBRATION_ONLY",
        "business_outcome_verified": False,
        "real_external_outcome_verified": False,
        "authorizes_mutation": False,
    }


def _consumer_gate(case_id: str, artifact: bytes | None,
                   readback_raw: bytes | None, quality_key: str) -> tuple[str, str]:
    """Require a separate, artifact-bound consumer readback.

    A minimal success string is not a receipt. This schema is a synthetic
    calibration boundary, not an authenticated production reviewer identity.
    """
    try:
        receipt = _json_object(
            readback_raw, limit=MAX_READBACK_BYTES, label="CONSUMER_READBACK")
    except ValueError:
        return INSUFFICIENT, "CONSUMER_READBACK_MISSING_OR_UNREADABLE"

    required = {
        "schema_version", "case_id", "consumer_id", "observed_at",
        "delivery_status", "opened", "artifact_sha256", "assessment",
        "quality_assessment",
    }
    if set(receipt) != required:
        return INSUFFICIENT, "CONSUMER_READBACK_SCHEMA_MISMATCH"
    if (type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["case_id"] != case_id
        or not isinstance(receipt["consumer_id"], str)
        or not _ID.fullmatch(receipt["consumer_id"])
        or not isinstance(receipt["observed_at"], str)
        or not receipt["observed_at"].strip()
        or len(receipt["observed_at"]) > 80):
        return INSUFFICIENT, "CONSUMER_READBACK_IDENTITY_INVALID"
    quality = receipt["quality_assessment"]
    if (not isinstance(quality, dict) or set(quality) != {quality_key}
        or quality[quality_key] not in ("ACCEPTED", "REJECTED", "UNKNOWN")):
        return INSUFFICIENT, "CONSUMER_QUALITY_ASSESSMENT_MISSING"

    if receipt["delivery_status"] == "NOT_DELIVERED":
        if (receipt["opened"] is not False
            or receipt["artifact_sha256"] is not None
            or receipt["assessment"] != "REJECTED"):
            return INSUFFICIENT, "DELIVERY_FAILURE_RECEIPT_INCONSISTENT"
        return FAIL, "CONSUMER_CONFIRMED_NOT_DELIVERED"

    if receipt["delivery_status"] != "DELIVERED":
        return INSUFFICIENT, "DELIVERY_STATUS_UNKNOWN"
    if artifact is None or not isinstance(artifact, bytes):
        return INSUFFICIENT, "DELIVERED_ARTIFACT_NOT_READABLE"
    if (receipt["opened"] is not True
        or not isinstance(receipt["artifact_sha256"], str)
        or not _SHA256.fullmatch(receipt["artifact_sha256"])
        or receipt["artifact_sha256"] != _sha256(artifact)):
        return INSUFFICIENT, "CONSUMER_READBACK_NOT_BOUND_TO_ARTIFACT"
    if receipt["assessment"] == "REJECTED":
        return FAIL, "CONSUMER_REJECTED_DELIVERABLE"
    if receipt["assessment"] != "ACCEPTED":
        return INSUFFICIENT, "CONSUMER_ASSESSMENT_UNKNOWN"
    if quality[quality_key] == "REJECTED":
        return FAIL, f"CONSUMER_{quality_key.upper()}_REJECTED"
    if quality[quality_key] != "ACCEPTED":
        return INSUFFICIENT, f"CONSUMER_{quality_key.upper()}_UNKNOWN"
    return PASS, "CONSUMER_READBACK_ACCEPTED"


def _validate_contract(contract_raw: bytes | None, kind: str,
                       required_keys: set[str]) -> dict:
    contract = _json_object(contract_raw, limit=32 * 1024, label="OWNER_CONTRACT")
    if set(contract) != required_keys:
        raise ValueError("OWNER_CONTRACT_SCHEMA_MISMATCH")
    if (type(contract["schema_version"]) is not int
        or contract["schema_version"] != 1
        or contract["kind"] != kind
        or not isinstance(contract["case_id"], str)
        or not _ID.fullmatch(contract["case_id"])):
        raise ValueError("OWNER_CONTRACT_IDENTITY_INVALID")
    return contract


def evaluate_voice_script(
    contract_raw: bytes | None,
    source_raw: bytes | None,
    artifact_raw: bytes | None,
    consumer_readback_raw: bytes | None,
) -> dict:
    """Grade a structured broadcast script against revisioned source facts.

    Content correctness is deterministic. Read-aloud usability is supplied by
    the separate consumer readback. A synthetic PASS remains calibration only.
    """
    case_id = None
    checks: dict[str, Any] = {}
    try:
        contract = _validate_contract(
            contract_raw, "voice_script",
            {"schema_version", "case_id", "kind", "source_sha256",
             "expected_order", "min_script_chars"},
        )
        case_id = contract["case_id"]
        if (not isinstance(contract["source_sha256"], str)
            or not _SHA256.fullmatch(contract["source_sha256"])
            or not isinstance(contract["expected_order"], list)
            or not contract["expected_order"]
            or len(contract["expected_order"]) > 64
            or any(not isinstance(x, str) or not _ID.fullmatch(x)
                   for x in contract["expected_order"])
            or len(set(contract["expected_order"])) != len(contract["expected_order"])
            or type(contract["min_script_chars"]) is not int
            or not 1 <= contract["min_script_chars"] <= 500):
            raise ValueError("VOICE_CONTRACT_INVALID")

        source = _json_object(source_raw, limit=MAX_SOURCE_BYTES, label="VOICE_SOURCE")
        if (set(source) != {"schema_version", "case_id", "revisions"}
            or type(source.get("schema_version")) is not int
            or source.get("schema_version") != 1
            or source.get("case_id") != case_id
            or _sha256(source_raw) != contract["source_sha256"]):
            return _result(INSUFFICIENT, case_id, "VOICE_SOURCE_IDENTITY_OR_HASH_MISMATCH")

        revisions = source.get("revisions")
        if not isinstance(revisions, list) or not revisions or len(revisions) > 512:
            return _result(INSUFFICIENT, case_id, "VOICE_SOURCE_REVISIONS_UNAVAILABLE")

        latest: dict[tuple[str, str], dict] = {}
        history: dict[tuple[str, str], list[dict]] = {}
        for row in revisions:
            if (not isinstance(row, dict)
                or set(row) != {"item_id", "field", "revision", "value", "source_id"}
                or not isinstance(row["item_id"], str) or not _ID.fullmatch(row["item_id"])
                or not isinstance(row["field"], str) or not _ID.fullmatch(row["field"])
                or type(row["revision"]) is not int or row["revision"] < 1
                or not isinstance(row["value"], str) or not row["value"].strip()
                or len(row["value"]) > 500
                or not isinstance(row["source_id"], str) or not _ID.fullmatch(row["source_id"])):
                return _result(INSUFFICIENT, case_id, "VOICE_SOURCE_REVISION_INVALID")
            key = (row["item_id"], row["field"])
            history.setdefault(key, []).append(row)
            prior = latest.get(key)
            if prior is None or row["revision"] > prior["revision"]:
                latest[key] = row
            elif row["revision"] == prior["revision"]:
                return _result(INSUFFICIENT, case_id, "VOICE_SOURCE_REVISION_CONFLICT")

        expected_items = set(contract["expected_order"])
        source_items = {item for item, _ in latest}
        if not expected_items.issubset(source_items):
            return _result(INSUFFICIENT, case_id, "VOICE_SOURCE_MISSING_REQUIRED_ITEM")

        if artifact_raw is not None and isinstance(artifact_raw, bytes):
            early_verdict, early_reason = _consumer_gate(
                case_id, artifact_raw, consumer_readback_raw, "read_aloud")
            if early_verdict == FAIL:
                return _result(FAIL, case_id, early_reason)
        if artifact_raw is None or not isinstance(artifact_raw, bytes):
            # A valid NOT_DELIVERED consumer observation is an actual failure.
            delivery_verdict, delivery_reason = _consumer_gate(
                case_id, None, consumer_readback_raw, "read_aloud")
            if delivery_verdict == FAIL:
                return _result(FAIL, case_id, delivery_reason)
            return _result(INSUFFICIENT, case_id, "VOICE_ARTIFACT_MISSING")

        try:
            candidate = _json_object(
                artifact_raw, limit=MAX_ARTIFACT_BYTES, label="VOICE_ARTIFACT")
        except ValueError:
            return _result(INSUFFICIENT, case_id, "VOICE_ARTIFACT_UNREADABLE")

        if (set(candidate) != {"schema_version", "case_id", "segments"}
            or type(candidate["schema_version"]) is not int
            or candidate["schema_version"] != 1
            or candidate["case_id"] != case_id
            or not isinstance(candidate["segments"], list)):
            return _result(INSUFFICIENT, case_id, "VOICE_ARTIFACT_SCHEMA_INVALID")

        segments = candidate["segments"]
        actual_order = []
        by_item = {}
        for segment in segments:
            if (not isinstance(segment, dict)
                or set(segment) != {"item_id", "text", "claims", "source_ids"}
                or not isinstance(segment["item_id"], str)
                or not isinstance(segment["text"], str)
                or not isinstance(segment["claims"], dict)
                or not isinstance(segment["source_ids"], list)
                or any(not isinstance(x, str) for x in segment["source_ids"])):
                return _result(INSUFFICIENT, case_id, "VOICE_SEGMENT_SCHEMA_INVALID")
            actual_order.append(segment["item_id"])
            if segment["item_id"] in by_item:
                return _result(FAIL, case_id, "VOICE_DUPLICATE_SEGMENT")
            by_item[segment["item_id"]] = segment

        if actual_order != contract["expected_order"]:
            return _result(FAIL, case_id, "VOICE_SEGMENT_ORDER_MISMATCH",
                           {"expected_order": contract["expected_order"],
                            "actual_order": actual_order})
        if len(segments) != len(contract["expected_order"]):
            return _result(FAIL, case_id, "VOICE_SEGMENT_SET_INCOMPLETE")

        for item_id in contract["expected_order"]:
            segment = by_item[item_id]
            text = segment["text"].strip()
            if (len(text) < contract["min_script_chars"]
                or len(text) > 5000 or _PLACEHOLDER.search(text)):
                return _result(FAIL, case_id, "VOICE_SCRIPT_NOT_USABLE",
                               {"item_id": item_id})
            expected_claims = {}
            expected_sources = set()
            superseded_values = set()
            for (source_item, field), rows in history.items():
                if source_item != item_id:
                    continue
                current = latest[(source_item, field)]
                expected_claims[field] = current["value"]
                expected_sources.add(current["source_id"])
                for old in rows:
                    if old["revision"] < current["revision"] and old["value"] != current["value"]:
                        superseded_values.add(old["value"])
            if segment["claims"] != expected_claims:
                return _result(FAIL, case_id, "VOICE_OWNER_FACT_MISMATCH",
                               {"item_id": item_id,
                                "expected_claims": expected_claims,
                                "actual_claims": segment["claims"]})
            if (len(segment["source_ids"]) != len(set(segment["source_ids"]))
                or sorted(segment["source_ids"]) != sorted(expected_sources)):
                return _result(FAIL, case_id, "VOICE_SOURCE_CITATION_MISMATCH",
                               {"item_id": item_id})
            if not all(value in text for value in expected_claims.values()):
                return _result(FAIL, case_id, "VOICE_SCRIPT_OMITS_REQUIRED_FACT",
                               {"item_id": item_id})
            if any(value in text for value in superseded_values):
                return _result(FAIL, case_id, "VOICE_SCRIPT_REPEATS_SUPERSEDED_FACT",
                               {"item_id": item_id})
        checks["revision_selection"] = "LATEST_REVISION_PER_FIELD"
        checks["item_order"] = "EXACT"
        checks["source_citations"] = "EXACT"
        checks["script_content"] = "OWNER_FACTS_MATCH"

        consumer_verdict, consumer_reason = _consumer_gate(
            case_id, artifact_raw, consumer_readback_raw, "read_aloud")
        checks["consumer_readback"] = consumer_reason
        if consumer_verdict != PASS:
            return _result(consumer_verdict, case_id, consumer_reason, checks)
        return _result(PASS, case_id, "VOICE_SCRIPT_AND_CONSUMER_READBACK_ACCEPTED", checks)
    except ValueError as exc:
        return _result(INSUFFICIENT, case_id, str(exc), checks)


_RUN_RE = re.compile(r"RUN test=([A-Za-z0-9_.:-]+) seed=(\d+)\Z")
_MISMATCH_RE = re.compile(
    r"SCOREBOARD_MISMATCH time_ns=(\d+) signal=([A-Za-z0-9_.\[\]-]+) "
    r"expected=(\S+) actual=(\S+)\Z"
)
_TIMEOUT_RE = re.compile(r"TIMEOUT time_ns=(\d+) reason=(.{1,240})\Z")
_RETRY_RE = re.compile(r"RETRY attempt=(\d+) reason=(.{1,240})\Z")
_EXIT_RE = re.compile(r"PROCESS_EXIT_CODE=(\d+)\Z")


def _parse_simulator_log(raw_log: bytes) -> dict:
    if not isinstance(raw_log, bytes) or not raw_log or len(raw_log) > MAX_SOURCE_BYTES:
        raise ValueError("SIMULATOR_LOG_MISSING_OR_OUT_OF_BOUNDS")
    try:
        lines = raw_log.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("SIMULATOR_LOG_UNREADABLE") from exc
    if not lines or len(lines) > 20000:
        raise ValueError("SIMULATOR_LOG_LINE_BOUND")
    runs, exits, mismatches, timeouts, retries = [], [], [], [], []
    for line_number, line in enumerate(lines, 1):
        if match := _RUN_RE.fullmatch(line):
            runs.append((line_number, match.group(1), int(match.group(2))))
        elif match := _MISMATCH_RE.fullmatch(line):
            mismatches.append((line_number, int(match.group(1))))
        elif match := _TIMEOUT_RE.fullmatch(line):
            timeouts.append((line_number, int(match.group(1))))
        elif match := _RETRY_RE.fullmatch(line):
            retries.append((line_number, int(match.group(1))))
        elif match := _EXIT_RE.fullmatch(line):
            exits.append((line_number, int(match.group(1))))
        elif line.startswith(("RUN ", "SCOREBOARD_MISMATCH", "TIMEOUT ",
                              "RETRY ", "PROCESS_EXIT_CODE=")):
            raise ValueError("SIMULATOR_LOG_EVENT_MALFORMED")
    if len(runs) != 1 or len(exits) != 1:
        raise ValueError("SIMULATOR_LOG_RUN_OR_EXIT_AMBIGUOUS")
    error_events = (
        [(line, time_ns, "SCOREBOARD_MISMATCH") for line, time_ns in mismatches]
        + [(line, time_ns, "TIMEOUT") for line, time_ns in timeouts]
    )
    first_error = min(error_events, key=lambda event: (event[1], event[0])) if error_events else None
    mismatch_count = len(mismatches)
    timeout_count = len(timeouts)
    retry_count = len(retries)
    exit_code = exits[0][1]
    if first_error:
        failure_class = first_error[2]
    elif exit_code != 0:
        failure_class = "PROCESS_EXIT"
    else:
        failure_class = "NONE"
    return {
        "test_id": runs[0][1],
        "seed": runs[0][2],
        "process_exit_code": exit_code,
        "scoreboard_mismatches": mismatch_count,
        "first_error_time_ns": first_error[1] if first_error else None,
        "first_error_line": first_error[0] if first_error else None,
        "timeouts": timeout_count,
        "retries": retry_count,
        "verification_result": "FAILED" if failure_class != "NONE" else "PASSED",
        "failure_class": failure_class,
    }


def evaluate_dv_regression_triage(
    contract_raw: bytes | None,
    raw_log: bytes | None,
    simulator_state_raw: bytes | None,
    artifact_raw: bytes | None,
    consumer_readback_raw: bytes | None,
) -> dict:
    """Grade regression triage against raw log + independent simulator state."""
    case_id = None
    checks: dict[str, Any] = {}
    try:
        contract = _validate_contract(
            contract_raw, "dv_regression_triage",
            {"schema_version", "case_id", "kind", "raw_log_sha256",
             "simulator_state_sha256", "expected_test_id", "expected_seed"},
        )
        case_id = contract["case_id"]
        if (not isinstance(contract["raw_log_sha256"], str)
            or not _SHA256.fullmatch(contract["raw_log_sha256"])
            or not isinstance(contract["simulator_state_sha256"], str)
            or not _SHA256.fullmatch(contract["simulator_state_sha256"])
            or not isinstance(contract["expected_test_id"], str)
            or not _ID.fullmatch(contract["expected_test_id"])
            or type(contract["expected_seed"]) is not int
            or contract["expected_seed"] < 0):
            raise ValueError("DV_CONTRACT_INVALID")
        if (not isinstance(raw_log, bytes) or not raw_log
            or _sha256(raw_log) != contract["raw_log_sha256"]
            or not isinstance(simulator_state_raw, bytes) or not simulator_state_raw
            or _sha256(simulator_state_raw) != contract["simulator_state_sha256"]):
            return _result(INSUFFICIENT, case_id, "DV_SOURCE_IDENTITY_OR_HASH_MISMATCH")

        try:
            observed = _parse_simulator_log(raw_log)
            state = _json_object(
                simulator_state_raw, limit=64 * 1024, label="SIMULATOR_STATE")
        except ValueError as exc:
            return _result(INSUFFICIENT, case_id, str(exc))

        state_keys = {
            "schema_version", "case_id", "test_id", "seed", "process_exit_code",
            "scoreboard_mismatches", "first_error_time_ns", "first_error_line",
            "timeouts", "retries",
        }
        if (set(state) != state_keys
            or type(state["schema_version"]) is not int or state["schema_version"] != 1
            or state["case_id"] != case_id):
            return _result(INSUFFICIENT, case_id, "SIMULATOR_STATE_SCHEMA_OR_IDENTITY_INVALID")
        for key in ("seed", "process_exit_code", "scoreboard_mismatches", "timeouts", "retries"):
            if type(state[key]) is not int or state[key] < 0:
                return _result(INSUFFICIENT, case_id, "SIMULATOR_STATE_NUMERIC_FIELD_INVALID")
        if state["first_error_time_ns"] is not None and (
            type(state["first_error_time_ns"]) is not int or state["first_error_time_ns"] < 0
        ):
            return _result(INSUFFICIENT, case_id, "SIMULATOR_STATE_FIRST_ERROR_INVALID")
        if state["first_error_line"] is not None and (
            type(state["first_error_line"]) is not int or state["first_error_line"] < 1
        ):
            return _result(INSUFFICIENT, case_id, "SIMULATOR_STATE_FIRST_ERROR_LINE_INVALID")

        if (observed["test_id"] != contract["expected_test_id"]
            or observed["seed"] != contract["expected_seed"]
            or state["test_id"] != contract["expected_test_id"]
            or state["seed"] != contract["expected_seed"]):
            return _result(INSUFFICIENT, case_id, "DV_RUN_IDENTITY_MISMATCH")
        state_observation = {key: observed[key] for key in (
            "test_id", "seed", "process_exit_code", "scoreboard_mismatches",
            "first_error_time_ns", "first_error_line", "timeouts", "retries")}
        state_comparison = {key: state[key] for key in state_observation}
        if state_comparison != state_observation:
            return _result(INSUFFICIENT, case_id, "SIMULATOR_STATE_LOG_CONFLICT")

        if artifact_raw is not None and isinstance(artifact_raw, bytes):
            early_verdict, early_reason = _consumer_gate(
                case_id, artifact_raw, consumer_readback_raw, "reproducibility")
            if early_verdict == FAIL:
                return _result(FAIL, case_id, early_reason)
        if artifact_raw is None or not isinstance(artifact_raw, bytes):
            delivery_verdict, delivery_reason = _consumer_gate(
                case_id, None, consumer_readback_raw, "reproducibility")
            if delivery_verdict == FAIL:
                return _result(FAIL, case_id, delivery_reason)
            return _result(INSUFFICIENT, case_id, "DV_TRIAGE_ARTIFACT_MISSING")
        try:
            candidate = _json_object(
                artifact_raw, limit=MAX_ARTIFACT_BYTES, label="DV_TRIAGE_ARTIFACT")
        except ValueError:
            return _result(INSUFFICIENT, case_id, "DV_TRIAGE_ARTIFACT_UNREADABLE")

        candidate_keys = {
            "schema_version", "case_id", "test_id", "seed", "process_exit_code",
            "scoreboard_mismatches", "first_error_time_ns", "first_error_line",
            "timeouts", "retries", "verification_result", "failure_class",
        }
        if (set(candidate) != candidate_keys
            or type(candidate["schema_version"]) is not int
            or candidate["schema_version"] != 1
            or candidate["case_id"] != case_id):
            return _result(INSUFFICIENT, case_id, "DV_TRIAGE_ARTIFACT_SCHEMA_INVALID")
        for key in ("seed", "process_exit_code", "scoreboard_mismatches", "timeouts", "retries"):
            if type(candidate[key]) is not int or candidate[key] < 0:
                return _result(INSUFFICIENT, case_id, "DV_TRIAGE_ARTIFACT_NUMERIC_FIELD_INVALID")
        if (candidate["first_error_time_ns"] is not None and (
                type(candidate["first_error_time_ns"]) is not int
                or candidate["first_error_time_ns"] < 0)
            or candidate["first_error_line"] is not None and (
                type(candidate["first_error_line"]) is not int
                or candidate["first_error_line"] < 1)):
            return _result(INSUFFICIENT, case_id, "DV_TRIAGE_ARTIFACT_FIRST_ERROR_INVALID")

        expected_candidate = {
            "schema_version": 1,
            "case_id": case_id,
            **observed,
        }
        if candidate != expected_candidate:
            return _result(FAIL, case_id, "DV_TRIAGE_FACTS_OR_CLASSIFICATION_MISMATCH",
                           {"expected": expected_candidate, "actual": candidate})
        checks["raw_log"] = "PARSED"
        checks["simulator_state"] = "INDEPENDENTLY_CROSS_CHECKED"
        checks["first_error_location"] = {
            "time_ns": observed["first_error_time_ns"],
            "line": observed["first_error_line"],
        }
        checks["exit_code_not_used_as_only_pass_signal"] = (
            observed["process_exit_code"] == 0
            and observed["verification_result"] == "FAILED"
            and observed["failure_class"] != "NONE"
        )
        consumer_verdict, consumer_reason = _consumer_gate(
            case_id, artifact_raw, consumer_readback_raw, "reproducibility")
        checks["consumer_readback"] = consumer_reason
        if consumer_verdict != PASS:
            return _result(consumer_verdict, case_id, consumer_reason, checks)
        return _result(PASS, case_id, "DV_TRIAGE_AND_CONSUMER_READBACK_ACCEPTED", checks)
    except ValueError as exc:
        return _result(INSUFFICIENT, case_id, str(exc), checks)
