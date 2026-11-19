from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))

from compound_owner_oracle import evaluate_compound_owner_goal


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CompoundOwnerOracleTests(unittest.TestCase):
    def setUp(self):
        self.sources = {
            "baseline.csv": b"id,amount\nA,7\nB,4\n",
            "actual.csv": b"id,amount\nA,5\nB,4\n",
            "settings.json": b'{"timeout":12}\n',
        }
        self.owner_goal = (
            "Compare baseline.csv with actual.csv by id, report all differences, "
            "then prepare a separate draft of settings.json with owner equal to ops."
        )
        self.contract = {
            "schema_version": 1,
            "goal_id": "compound-owner-goal-01",
            "kind": "csv_reconciliation_plus_json_draft",
            "owner_goal_sha256": sha(self.owner_goal.encode("utf-8")),
            "source_paths": {
                "reference": "baseline.csv",
                "observed": "actual.csv",
                "draft": "settings.json",
            },
            "source_sha256": {
                name: sha(raw) for name, raw in self.sources.items()
            },
            "record_key": "id",
            "draft_fields": {"owner": "ops"},
            "allowed_effect": "LOCAL_CANDIDATES_ONLY",
        }
        self.csv_report = encode({
            "task_id": "a" * 32,
            "goal_rev": 1,
            "source_spec": {
                "kind": "record_reconciliation",
                "reference": "baseline.csv",
                "observed": "actual.csv",
                "objective": "identify_discrepancies",
            },
            "source_sha256": {
                "reference": sha(self.sources["baseline.csv"]),
                "observed": sha(self.sources["actual.csv"]),
            },
            "proposal": {
                "status": "DISCREPANCIES_FOUND",
                "selected_key": "id",
                "reference_only_columns": [],
                "observed_only_columns": [],
                "discrepancies": [{
                    "kind": "field_mismatch",
                    "key": "A",
                    "field": "amount",
                    "reference": "7",
                    "observed": "5",
                }],
                "rows_reference": 2,
                "rows_observed": 2,
                "hypotheses": [],
                "relationship_contract_sha256": None,
                "warning": "Mechanical evidence only.",
            },
            "oracle": "UNTRUSTED_SELF_REPORTED_LABEL",
            "status": "PROPOSAL_NOT_APPROVED",
        })
        self.json_candidate = b'{"timeout":12,"owner":"ops"}\n'
        self.json_artifact = encode({
            "task_id": "b" * 32,
            "goal_rev": 1,
            "source_sha256": sha(self.sources["settings.json"]),
            "goal_spec": {
                "kind": "goal_case",
                "goal_type": "json_keys",
                "input": "settings.json",
                "desired": {"owner": "ops"},
            },
            "candidate_sha256": sha(self.json_candidate),
            "candidate_text": self.json_candidate.decode("utf-8"),
            "status": "PROPOSAL_NOT_APPROVED",
        })
        self.expected_lineage = {
            "root_task_id": "d" * 32,
            "root_parent_task": None,
            "root_kind": "native_goal",
            "owner_goal_sha256": self.contract["owner_goal_sha256"],
            "goal_rev": 1,
            "grant_rev": 1,
            "children": {
                "csv_report": {
                    "task_id": "a" * 32,
                    "parent_task": "d" * 32,
                    "goal_rev": 1,
                    "grant_rev": 1,
                    "state": "NEEDS_REVIEW",
                    "artifact_sha256": sha(self.csv_report),
                },
                "json_draft": {
                    "task_id": "b" * 32,
                    "parent_task": "d" * 32,
                    "goal_rev": 1,
                    "grant_rev": 1,
                    "state": "SANDBOX_VERIFIED",
                    "artifact_sha256": sha(self.json_artifact),
                },
            },
        }

    def evaluate(self, **changes):
        args = {
            "contract": self.contract,
            "current_sources": self.sources,
            "csv_report": self.csv_report,
            "json_artifact": self.json_artifact,
            "json_candidate": self.json_candidate,
            "expected_lineage": self.expected_lineage,
        }
        args.update(changes)
        return evaluate_compound_owner_goal(**args)

    def update_csv_report(self, report):
        self.csv_report = encode(report)
        self.expected_lineage["children"]["csv_report"]["artifact_sha256"] = sha(self.csv_report)

    def update_json_artifact(self, artifact):
        self.json_artifact = encode(artifact)
        self.expected_lineage["children"]["json_draft"]["artifact_sha256"] = sha(self.json_artifact)

    def test_both_independent_effects_are_required_for_whole_goal_pass(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "SYNTHETIC_COMPOUND_OWNER_GOAL_MET", result)
        self.assertTrue(result["synthetic_local_postconditions_met"])
        self.assertEqual(result["subresults"]["csv_reconciliation"]["status"], "PASS")
        self.assertEqual(result["subresults"]["json_draft"]["status"], "PASS")
        self.assertFalse(result["owner_outcome_verified"])
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["real_external_outcome_verified"])
        self.assertFalse(result["authorizes_mutation"])

    def test_missing_csv_report_cannot_be_compensated_by_correct_json_draft(self):
        result = self.evaluate(csv_report=b"")
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertFalse(result["synthetic_local_postconditions_met"])

    def test_missing_json_draft_cannot_be_compensated_by_correct_csv_report(self):
        result = self.evaluate(json_candidate=b"")
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "JSON_DRAFT_PROVENANCE_MISMATCH")

    def test_partial_or_wrong_csv_report_is_rejected(self):
        wrong = json.loads(self.csv_report.decode("utf-8"))
        wrong["proposal"]["discrepancies"] = []
        self.update_csv_report(wrong)
        result = self.evaluate()
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CSV_REPORT_OWNER_POSTCONDITION_MISSED")

    def test_csv_report_cannot_reverse_owner_reference_and_observed_roles(self):
        wrong = json.loads(self.csv_report.decode("utf-8"))
        wrong["source_spec"]["reference"] = "actual.csv"
        wrong["source_spec"]["observed"] = "baseline.csv"
        self.update_csv_report(wrong)
        result = self.evaluate()
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CSV_REPORT_PROVENANCE_MISMATCH")

    def test_source_drift_invalidates_the_whole_compound_result(self):
        changed = dict(self.sources)
        changed["actual.csv"] = b"id,amount\nA,999\nB,4\n"
        result = self.evaluate(current_sources=changed)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "OWNER_SOURCE_DRIFT")

    def test_json_candidate_must_preserve_all_original_fields(self):
        wrong = b'{"timeout":99,"owner":"ops"}\n'
        artifact = json.loads(self.json_artifact.decode("utf-8"))
        artifact["candidate_sha256"] = sha(wrong)
        artifact["candidate_text"] = wrong.decode("utf-8")
        self.update_json_artifact(artifact)
        result = self.evaluate(json_candidate=wrong)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "JSON_DRAFT_OWNER_POSTCONDITION_MISSED")

    def test_json_candidate_must_set_the_requested_value(self):
        wrong = b'{"timeout":12,"owner":"admin"}\n'
        artifact = json.loads(self.json_artifact.decode("utf-8"))
        artifact["candidate_sha256"] = sha(wrong)
        artifact["candidate_text"] = wrong.decode("utf-8")
        self.update_json_artifact(artifact)
        result = self.evaluate(json_candidate=wrong)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "JSON_DRAFT_OWNER_POSTCONDITION_MISSED")

    def test_duplicate_json_keys_are_rejected_in_report_and_candidate(self):
        bad_report = b'{"task_id":"a","task_id":"b"}'
        self.expected_lineage["children"]["csv_report"]["artifact_sha256"] = sha(bad_report)
        result = self.evaluate(csv_report=bad_report)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "DUPLICATE_JSON_KEY")

        self.expected_lineage["children"]["csv_report"]["artifact_sha256"] = sha(self.csv_report)
        bad_candidate = b'{"timeout":12,"owner":"ops","owner":"root"}'
        artifact = json.loads(self.json_artifact.decode("utf-8"))
        artifact["candidate_sha256"] = sha(bad_candidate)
        artifact["candidate_text"] = bad_candidate.decode("utf-8")
        self.update_json_artifact(artifact)
        result = self.evaluate(json_candidate=bad_candidate)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "JSON_DRAFT_OWNER_POSTCONDITION_MISSED")

    def test_both_child_artifacts_must_bind_to_current_goal_revision(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["goal_rev"] = 2
        lineage["children"]["csv_report"]["goal_rev"] = 2
        lineage["children"]["json_draft"]["goal_rev"] = 2
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CSV_REPORT_PROVENANCE_MISMATCH")

    def test_csv_report_must_bind_to_the_expected_child_task_id(self):
        wrong = json.loads(self.csv_report.decode("utf-8"))
        wrong["task_id"] = "c" * 32
        self.update_csv_report(wrong)
        result = self.evaluate()
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CSV_REPORT_PROVENANCE_MISMATCH")

    def test_json_artifact_must_bind_candidate_to_the_expected_child(self):
        wrong = json.loads(self.json_artifact.decode("utf-8"))
        wrong["task_id"] = "c" * 32
        self.update_json_artifact(wrong)
        result = self.evaluate()
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "JSON_DRAFT_PROVENANCE_MISMATCH")

    def test_children_must_be_direct_descendants_of_the_same_root(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["children"]["csv_report"]["parent_task"] = "e" * 32
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CHILD_LINEAGE_MISMATCH")

    def test_root_id_cannot_be_reused_as_a_child_id(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        root_id = lineage["children"]["csv_report"]["task_id"]
        lineage["root_task_id"] = root_id
        lineage["children"]["csv_report"]["parent_task"] = root_id
        lineage["children"]["json_draft"]["parent_task"] = root_id
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CHILD_TASK_ID_COLLISION")

    def test_children_must_share_the_same_current_grant_revision(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["children"]["json_draft"]["grant_rev"] = 2
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CHILD_LINEAGE_MISMATCH")

    def test_artifacts_must_match_exact_ledger_hashes(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["children"]["csv_report"]["artifact_sha256"] = "0" * 64
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CSV_REPORT_LEDGER_HASH_MISMATCH")

    def test_duplicate_csv_keys_fail_closed(self):
        changed = dict(self.sources)
        changed["actual.csv"] = b"id,amount\nA,5\nA,6\n"
        contract = dict(self.contract, source_sha256={name: sha(raw) for name, raw in changed.items()})
        result = self.evaluate(contract=contract, current_sources=changed)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "CSV_OBSERVED_KEY_NOT_UNIQUE")

    def test_csv_utf8_bom_is_handled_without_changing_column_identity(self):
        changed = dict(self.sources)
        changed["baseline.csv"] = b"\xef\xbb\xbf" + changed["baseline.csv"]
        changed["actual.csv"] = b"\xef\xbb\xbf" + changed["actual.csv"]
        contract = dict(
            self.contract,
            source_sha256={name: sha(raw) for name, raw in changed.items()},
        )
        report = json.loads(self.csv_report.decode("utf-8"))
        report["source_sha256"] = {
            "reference": contract["source_sha256"]["baseline.csv"],
            "observed": contract["source_sha256"]["actual.csv"],
        }
        self.update_csv_report(report)
        result = self.evaluate(contract=contract, current_sources=changed)
        self.assertEqual(
            result["status"], "SYNTHETIC_COMPOUND_OWNER_GOAL_MET", result)

    def test_contract_cannot_escape_fixture_scope_or_authorize_writes(self):
        unsafe = dict(self.contract)
        unsafe["source_paths"] = dict(self.contract["source_paths"], draft="../settings.json")
        result = self.evaluate(contract=unsafe)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "UNSAFE_SOURCE_PATH")

        elevated = dict(self.contract, allowed_effect="PRODUCTION_WRITE")
        result = self.evaluate(contract=elevated)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertFalse(result["authorizes_mutation"])

    def test_open_goal_root_uses_the_same_compound_postcondition_oracle(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["root_kind"] = "open_goal"
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "SYNTHETIC_COMPOUND_OWNER_GOAL_MET", result)

    def test_missing_required_child_task_fails_closed(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["children"]["json_draft"] = None
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "MISSING_REQUIRED_CHILD_TASK")

    def test_unregistered_root_kind_is_rejected(self):
        lineage = json.loads(json.dumps(self.expected_lineage))
        lineage["root_kind"] = "unregistered"
        result = self.evaluate(expected_lineage=lineage)
        self.assertEqual(result["status"], "NOT_ACCEPTED")
        self.assertEqual(result["reason"], "BAD_EXPECTED_ROOT_LINEAGE")


    def test_untrusted_product_oracle_label_is_not_used_as_proof(self):
        forged = json.loads(self.csv_report.decode("utf-8"))
        forged["oracle"] = "TRUSTED_SUCCESS"
        self.update_csv_report(forged)
        result = self.evaluate()
        self.assertEqual(result["status"], "SYNTHETIC_COMPOUND_OWNER_GOAL_MET", result)
        forged["proposal"]["discrepancies"] = []
        self.update_csv_report(forged)
        result = self.evaluate()
        self.assertEqual(result["status"], "NOT_ACCEPTED")


if __name__ == "__main__":
    unittest.main()
