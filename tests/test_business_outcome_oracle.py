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
    quality_keys = (quality_key,) if isinstance(quality_key, str) else tuple(quality_key)
    return encode({
        "schema_version": 1,
        "case_id": case_id,
        "consumer_id": "synthetic-reviewer",
        "observed_at": "2026-11-18T00:00:00Z",
        "delivery_status": delivery_status,
        "opened": delivered,
        "artifact_sha256": sha(artifact) if delivered and artifact is not None else None,
        "assessment": assessment,
        "quality_assessment": {key: quality for key in quality_keys},
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
            self.case_id, self.candidate, ("factual_grounding", "read_aloud"))

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
            readback=consumer_readback(self.case_id, wrong, ("factual_grounding", "read_aloud")))
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
            consumer_readback(self.case_id, unreadable, ("factual_grounding", "read_aloud")))
        self.assertEqual(result["verdict"], INSUFFICIENT)

    def test_explicit_consumer_non_delivery_is_failure(self):
        receipt = consumer_readback(
            self.case_id, None, ("factual_grounding", "read_aloud"), delivery_status="NOT_DELIVERED",
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

    def test_consumer_must_accept_factual_grounding_and_read_aloud(self):
        for quality, expected in (("UNKNOWN", INSUFFICIENT), ("REJECTED", FAIL)):
            with self.subTest(factual_grounding=quality):
                receipt = json.loads(self.readback.decode("utf-8"))
                receipt["quality_assessment"]["factual_grounding"] = quality
                result = self.evaluate(readback=encode(receipt))
                self.assertEqual(result["verdict"], expected, result)
                if quality == "UNKNOWN":
                    self.assertEqual(result["reason"], "CONSUMER_FACTUAL_GROUNDING_UNKNOWN")
                else:
                    self.assertEqual(result["reason"], "CONSUMER_FACTUAL_GROUNDING_REJECTED")

    def test_consumer_rejects_unreadable_aloud_script(self):
        receipt = json.loads(consumer_readback(
            self.case_id, self.candidate, ("factual_grounding", "read_aloud")).decode("utf-8"))
        receipt["quality_assessment"]["read_aloud"] = "REJECTED"
        result = self.evaluate(readback=encode(receipt))
        self.assertEqual(result["verdict"], FAIL)
        self.assertEqual(result["reason"], "CONSUMER_READ_ALOUD_REJECTED")


class PublicVoiceSampleTests(unittest.TestCase):
    """Public-fact calibration; this is not a real business consumer sign-off."""

    def setUp(self):
        self.case_id = "public-tesla-berlin-20261116"
        # Public facts checked against Reuters and TechCrunch, 2026-11-16.
        # No copyrighted article text is stored in this fixture.
        self.source = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "revisions": [
                {"item_id": "01", "field": "investment", "revision": 1,
                 "value": "30亿欧元", "source_id": "Reuters-2026-11-16"},
                {"item_id": "01", "field": "site", "revision": 1,
                 "value": "格林海德工厂", "source_id": "Reuters-2026-11-16"},
                {"item_id": "01", "field": "site", "revision": 2,
                 "value": "格林海德工厂", "source_id": "TechCrunch-2026-11-16"},
                {"item_id": "01", "field": "capacity", "revision": 1,
                 "value": "最高每年100万辆Cybercab", "source_id": "Reuters-2026-11-16"},
                {"item_id": "01", "field": "construction", "revision": 1,
                 "value": "2027年上半年", "source_id": "Reuters-2026-11-16"},
                {"item_id": "01", "field": "production", "revision": 1,
                 "value": "2029年", "source_id": "Reuters-2026-11-16"},
                {"item_id": "01", "field": "permit", "revision": 1,
                 "value": "2026年底前", "source_id": "Reuters-2026-11-16"},
                {"item_id": "01", "field": "status", "revision": 1,
                 "value": "规划", "source_id": "Reuters-2026-11-16"},
            ],
        })
        self.contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "voice_script",
            "source_sha256": sha(self.source),
            "expected_order": ["01"],
            "min_script_chars": 30,
        })
        self.candidate = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "segments": [
                {
                    "item_id": "01",
                    "text": (
                        "特斯拉计划在柏林附近的格林海德工厂投资30亿欧元，"
                        "建设新的Cybercab生产设施，目标年产能最高每年100万辆Cybercab。"
                        "建设预计于2027年上半年启动，生产计划在2029年开始，"
                        "建筑许可申请计划于2026年底前提交。这仍属于规划，并非已实现产能。"
                    ),
                    "claims": {
                        "investment": "30亿欧元",
                        "site": "格林海德工厂",
                        "capacity": "最高每年100万辆Cybercab",
                        "construction": "2027年上半年",
                        "production": "2029年",
                        "permit": "2026年底前",
                        "status": "规划",
                    },
                    "source_ids": ["Reuters-2026-11-16", "TechCrunch-2026-11-16"],
                }
            ],
        })
        self.readback = consumer_readback(
            self.case_id, self.candidate,
            ("factual_grounding", "read_aloud"), quality="UNKNOWN")

    def test_public_article_facts_do_not_self_certify_without_consumer(self):
        result = evaluate_voice_script(
            self.contract, self.source, self.candidate, self.readback)
        self.assertEqual(result["verdict"], INSUFFICIENT, result)
        self.assertEqual(result["reason"], "CONSUMER_FACTUAL_GROUNDING_UNKNOWN")
        self.assertEqual(result["evidence_class"], "SYNTHETIC_CALIBRATION_ONLY")
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["authorizes_mutation"])

    def test_public_article_wrong_capacity_is_rejected(self):
        wrong = json.loads(self.candidate.decode("utf-8"))
        wrong["segments"][0]["claims"]["capacity"] = "最高每年150万辆Cybercab"
        wrong["segments"][0]["text"] = wrong["segments"][0]["text"].replace(
            "最高每年100万辆Cybercab", "最高每年150万辆Cybercab")
        artifact = encode(wrong)
        readback = consumer_readback(
            self.case_id, artifact,
            ("factual_grounding", "read_aloud"), quality="UNKNOWN")
        result = evaluate_voice_script(
            self.contract, self.source, artifact, readback)
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["reason"], "VOICE_OWNER_FACT_MISMATCH")


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

    def test_raw_uvm_reports_are_not_ignored_as_pass(self):
        for severity in ("UVM_INFO", "UVM_WARNING", "UVM_ERROR", "UVM_FATAL"):
            with self.subTest(severity=severity):
                log = (
                    "RUN test=R17 seed=17\n"
                    f"{severity} @ 80ns: reporter [TEST_FAILURE] observed failure\n"
                    "PROCESS_EXIT_CODE=0\n"
                ).encode("utf-8")
                contract = encode({
                    "schema_version": 1,
                    "case_id": self.case_id,
                    "kind": "dv_regression_triage",
                    "raw_log_sha256": sha(log),
                    "simulator_state_sha256": sha(self.state),
                    "expected_test_id": "R17",
                    "expected_seed": 17,
                })
                result = evaluate_dv_regression_triage(
                    contract, log, self.state, self.candidate, self.readback)
                self.assertEqual(result["verdict"], INSUFFICIENT)
                self.assertEqual(
                    result["reason"],
                    "SIMULATOR_LOG_UVM_REPORT_REQUIRES_NORMALIZATION",
                )

    def test_unrecognized_log_error_is_not_ignored_as_pass(self):
        log = (
            "RUN test=R17 seed=17\n"
            "ERROR: simulator assertion failed\n"
            "PROCESS_EXIT_CODE=0\n"
        ).encode("utf-8")
        contract = encode({
            "schema_version": 1,
            "case_id": self.case_id,
            "kind": "dv_regression_triage",
            "raw_log_sha256": sha(log),
            "simulator_state_sha256": sha(self.state),
            "expected_test_id": "R17",
            "expected_seed": 17,
        })
        result = evaluate_dv_regression_triage(
            contract, log, self.state, self.candidate, self.readback)
        self.assertEqual(result["verdict"], INSUFFICIENT)
        self.assertEqual(result["reason"], "SIMULATOR_LOG_UNRECOGNIZED_EVENT")

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
