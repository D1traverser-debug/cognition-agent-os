from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))

from business_outcome_oracle import (
    FAIL,
    INSUFFICIENT,
    PASS,
    evaluate_dv_regression_triage,
    evaluate_voice_script,
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def consumer_readback(case_id, artifact, quality_key, *, assessment="ACCEPTED",
                      quality="ACCEPTED", delivery_status="DELIVERED"):
    delivered = delivery_status == "DELIVERED"
    return encode({
        "schema_version": 1,
        "case_id": case_id,
        "consumer_id": "synthetic-reviewer",
        "observed_at": "2026-11-18T00:00:00Z",
        "delivery_status": delivery_status,
        "opened": delivered,
        "artifact_sha256": sha(artifact) if delivered and artifact is not None else None,
        "assessment": assessment,
        "quality_assessment": {quality_key: quality},
    })


class VoiceScriptOracleTests(unittest.TestCase):
    def setUp(self):
        self.case_id = "voice-07-08"
        self.source = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "revisions": [
                {"item_id": "07", "field": "quantity", "revision": 1,
                 "value": "12台", "source_id": "S07-v1"},
                {"item_id": "07", "field": "quantity", "revision": 2,
                 "value": "21台", "source_id": "S07-v2"},
                {"item_id": "08", "field": "topic", "revision": 1,
                 "value": "第二条资讯", "source_id": "S08-v1"},
            ],
        })
        self.contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "voice_script",
            "source_sha256": sha(self.source),
            "expected_order": ["07", "08"],
            "min_script_chars": 8,
        })
        self.candidate = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "segments": [
                {"item_id": "07", "text": "第07条：最新核定数量为21台。",
                 "claims": {"quantity": "21台"}, "source_ids": ["S07-v2"]},
                {"item_id": "08", "text": "第08条：接下来播报第二条资讯。",
                 "claims": {"topic": "第二条资讯"}, "source_ids": ["S08-v1"]},
            ],
        })
        self.readback = consumer_readback(
            self.case_id, self.candidate, "read_aloud")

    def evaluate(self, artifact=None, readback=None, source=None, contract=None):
        return evaluate_voice_script(
            contract if contract is not None else self.contract,
            source if source is not None else self.source,
            artifact if artifact is not None else self.candidate,
            readback if readback is not None else self.readback,
        )

    def test_correct_latest_revision_order_sources_and_consumer_readback_pass(self):
        result = self.evaluate()
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["evidence_class"], "SYNTHETIC_CALIBRATION_ONLY")
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["real_external_outcome_verified"])
        self.assertFalse(result["authorizes_mutation"])

    def test_superseded_value_or_wrong_item_order_fails(self):
        wrong = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "segments": [
                {"item_id": "08", "text": "第08条：接下来播报第二条资讯。",
                 "claims": {"topic": "第二条资讯"}, "source_ids": ["S08-v1"]},
                {"item_id": "07", "text": "第07条：数量为12台。",
                 "claims": {"quantity": "12台"}, "source_ids": ["S07-v1"]},
            ],
        })
        result = self.evaluate(artifact=wrong,
            readback=consumer_readback(self.case_id, wrong, "read_aloud"))
        self.assertEqual(result["verdict"], FAIL)
        self.assertIn(result["reason"], {
            "VOICE_SEGMENT_ORDER_MISMATCH", "VOICE_OWNER_FACT_MISMATCH"
        })

    def test_success_receipt_without_deliverable_is_insufficient(self):
        result = evaluate_voice_script(
            self.contract, self.source, None, encode({"status": "SUCCESS"}))
        self.assertEqual(result["verdict"], INSUFFICIENT)

    def test_unreadable_deliverable_is_insufficient_even_with_success_receipt(self):
        unreadable = b"\x00not-json"
        result = evaluate_voice_script(
            self.contract, self.source, unreadable,
            consumer_readback(self.case_id, unreadable, "read_aloud"))
        self.assertEqual(result["verdict"], INSUFFICIENT)

    def test_explicit_consumer_non_delivery_is_failure(self):
        receipt = consumer_readback(
            self.case_id, None, "read_aloud", delivery_status="NOT_DELIVERED",
            assessment="REJECTED", quality="UNKNOWN")
        result = evaluate_voice_script(self.contract, self.source, None, receipt)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["reason"], "CONSUMER_CONFIRMED_NOT_DELIVERED")

    def test_source_drift_is_insufficient_not_a_candidate_failure(self):
        changed = self.source.replace("21台".encode(), "22台".encode())
        result = self.evaluate(source=changed)
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "VOICE_SOURCE_IDENTITY_OR_HASH_MISMATCH")

    def test_unbound_consumer_readback_is_insufficient(self):
        receipt = json.loads(self.readback.decode("utf-8"))
        receipt["artifact_sha256"] = "0" * 64
        result = self.evaluate(readback=encode(receipt))
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "CONSUMER_READBACK_NOT_BOUND_TO_ARTIFACT")

    def test_consumer_rejects_unreadable_aloud_script(self):
        receipt = consumer_readback(
            self.case_id, self.candidate, "read_aloud", quality="REJECTED")
        result = self.evaluate(readback=receipt)
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["reason"], "CONSUMER_READ_ALOUD_REJECTED")


class DvRegressionOracleTests(unittest.TestCase):
    def setUp(self):
        self.case_id = "dv-r17-seed17"
        self.log = (
            "RUN test=R17 seed=17\n"
            "SCOREBOARD_MISMATCH time_ns=80 signal=uart.rx "
            "expected=0x1 actual=0x0\n"
            "PROCESS_EXIT_CODE=0\n"
        ).encode("utf-8")
        self.state = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "test_id": "R17",
            "seed": 17,
            "process_exit_code": 0,
            "scoreboard_mismatches": 1,
            "first_error_time_ns": 80,
            "first_error_line": 2,
            "timeouts": 0,
            "retries": 0,
        })
        self.contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "dv_regression_triage",
            "raw_log_sha256": sha(self.log),
            "simulator_state_sha256": sha(self.state),
            "expected_test_id": "R17",
            "expected_seed": 17,
        })
        self.candidate = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "test_id": "R17",
            "seed": 17,
            "process_exit_code": 0,
            "scoreboard_mismatches": 1,
            "first_error_time_ns": 80,
            "first_error_line": 2,
            "timeouts": 0,
            "retries": 0,
            "verification_result": "FAILED",
            "failure_class": "SCOREBOARD_MISMATCH",
        })
        self.readback = consumer_readback(
            self.case_id, self.candidate, "reproducibility")

    def evaluate(self, artifact=None, readback=None, state=None, log=None, contract=None):
        return evaluate_dv_regression_triage(
            contract if contract is not None else self.contract,
            log if log is not None else self.log,
            state if state is not None else self.state,
            artifact if artifact is not None else self.candidate,
            readback if readback is not None else self.readback,
        )

    def test_correct_first_error_and_exit_zero_with_mismatch_is_failed_run(self):
        result = self.evaluate()
        self.assertEqual(result["verdict"], PASS, result)
        self.assertTrue(result["checks"]["exit_code_not_used_as_only_pass_signal"])
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["authorizes_mutation"])

    def test_wrong_first_error_or_false_pass_classification_fails(self):
        wrong = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "test_id": "R17",
            "seed": 17,
            "process_exit_code": 0,
            "scoreboard_mismatches": 1,
            "first_error_time_ns": 90,
            "first_error_line": 2,
            "timeouts": 0,
            "retries": 0,
            "verification_result": "PASSED",
            "failure_class": "NONE",
        })
        result = self.evaluate(
            artifact=wrong,
            readback=consumer_readback(self.case_id, wrong, "reproducibility"))
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["reason"], "DV_TRIAGE_FACTS_OR_CLASSIFICATION_MISMATCH")

    def test_success_receipt_without_triage_artifact_is_insufficient(self):
        result = evaluate_dv_regression_triage(
            self.contract, self.log, self.state, None, encode({"status": "SUCCESS"}))
        self.assertEqual(result["verdict"], INSUFFICIENT)

    def test_unreadable_triage_artifact_is_insufficient(self):
        unreadable = b"{not-json"
        result = self.evaluate(
            artifact=unreadable,
            readback=consumer_readback(self.case_id, unreadable, "reproducibility"))
        self.assertEqual(result["verdict"], INSUFFICIENT)

    def test_log_and_independent_simulator_state_conflict_is_insufficient(self):
        conflict = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "test_id": "R17",
            "seed": 17,
            "process_exit_code": 0,
            "scoreboard_mismatches": 0,
            "first_error_time_ns": None,
            "first_error_line": None,
            "timeouts": 0,
            "retries": 0,
        })
        contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "dv_regression_triage",
            "raw_log_sha256": sha(self.log),
            "simulator_state_sha256": sha(conflict),
            "expected_test_id": "R17",
            "expected_seed": 17,
        })
        result = self.evaluate(state=conflict, contract=contract)
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "SIMULATOR_STATE_LOG_CONFLICT")

    def test_wrong_seed_is_insufficient_not_a_false_failure(self):
        wrong_log = self.log.replace(b"seed=17", b"seed=18")
        contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "dv_regression_triage",
            "raw_log_sha256": sha(wrong_log),
            "simulator_state_sha256": sha(self.state),
            "expected_test_id": "R17",
            "expected_seed": 17,
        })
        result = self.evaluate(log=wrong_log, contract=contract)
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "DV_RUN_IDENTITY_MISMATCH")


    def test_timeout_before_mismatch_is_reported_as_first_error(self):
        log = (
            "RUN test=R18 seed=18\n"
            "TIMEOUT time_ns=50 reason=ready_wait_expired\n"
            "SCOREBOARD_MISMATCH time_ns=80 signal=uart.rx expected=1 actual=0\n"
            "RETRY attempt=1 reason=bounded_retry\n"
            "PROCESS_EXIT_CODE=0\n"
        ).encode("utf-8")
        state = encode({
            "schema_version": 1,
            "case_id": "dv-r18-seed18",
            "test_id": "R18",
            "seed": 18,
            "process_exit_code": 0,
            "scoreboard_mismatches": 1,
            "first_error_time_ns": 50,
            "first_error_line": 2,
            "timeouts": 1,
            "retries": 1,
        })
        contract = encode({
            "schema_version": 1,
            "case_id": "dv-r18-seed18",
            "kind": "dv_regression_triage",
            "raw_log_sha256": sha(log),
            "simulator_state_sha256": sha(state),
            "expected_test_id": "R18",
            "expected_seed": 18,
        })
        candidate = encode({
            "schema_version": 1,
            "case_id": "dv-r18-seed18",
            "test_id": "R18",
            "seed": 18,
            "process_exit_code": 0,
            "scoreboard_mismatches": 1,
            "first_error_time_ns": 50,
            "first_error_line": 2,
            "timeouts": 1,
            "retries": 1,
            "verification_result": "FAILED",
            "failure_class": "TIMEOUT",
        })
        result = evaluate_dv_regression_triage(
            contract, log, state, candidate,
            consumer_readback("dv-r18-seed18", candidate, "reproducibility"))
        self.assertEqual(result["verdict"], PASS, result)

    def test_malformed_critical_log_event_fails_closed(self):
        malformed = (
            "RUN test=R17 seed=17\n"
            "SCOREBOARD_MISMATCH time_ns=80 expected=0x1 actual=0x0\n"
            "PROCESS_EXIT_CODE=0\n"
        ).encode("utf-8")
        contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "dv_regression_triage",
            "raw_log_sha256": sha(malformed),
            "simulator_state_sha256": sha(self.state),
            "expected_test_id": "R17",
            "expected_seed": 17,
        })
        result = self.evaluate(log=malformed, contract=contract)
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "SIMULATOR_LOG_EVENT_MALFORMED")

    def test_boolean_cannot_masquerade_as_numeric_seed(self):
        wrong = json.loads(self.candidate.decode("utf-8"))
        wrong["seed"] = True
        artifact = encode(wrong)
        result = self.evaluate(
            artifact=artifact,
            readback=consumer_readback(self.case_id, artifact, "reproducibility"))
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "DV_TRIAGE_ARTIFACT_NUMERIC_FIELD_INVALID")


if __name__ == "__main__":
    unittest.main()
