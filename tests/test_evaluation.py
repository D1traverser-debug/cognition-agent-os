"""P4 curated-reference controls: two disjoint task families, no model or token calls.

Curated references are DEMONSTRATION DATA authored with this change. These tests
do not prove that a separate qualified reviewer verified semantic ground truth.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.evaluation import EvaluationError, evaluate, public_inputs

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evaluation" / "curated_demo_reference.json"


class P4ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pack_digest = hashlib.sha256(PACK.read_bytes()).hexdigest()
        self.raw_cases = json.loads(PACK.read_text(encoding="utf-8"))["cases"]

    def candidate_file(self, answers=None):
        if answers is None:
            answers = [
                {"case_id": case["case_id"], "label": case["gold"],
                 "citations": [{"quote":case["required_quotes"][0],
                                "evidence_sha256":hashlib.sha256(
                                    case["evidence_text"].encode("utf-8")).hexdigest()}]}
                for case in self.raw_cases
            ]
        candidate = {"schema_version":1,"reference_pack_sha256":self.pack_digest,
                     "answers":answers}
        path = self.root / "candidate.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        return path

    def test_export_does_not_expose_gold_or_reference_quotes(self):
        obj = public_inputs(PACK, self.pack_digest)
        self.assertEqual(len(obj["cases"]), 6)
        self.assertEqual({x["family"] for x in obj["cases"]},
                         {"incident_triage", "protocol_impact"})
        self.assertFalse(any("gold" in x or "required_quotes" in x for x in obj["cases"]))
        self.assertEqual(obj["reference_pack_sha256"], self.pack_digest)
        self.assertTrue(all(len(x["evidence_sha256"]) == 64 for x in obj["cases"]))

    def test_two_family_correct_reference_matches_but_cannot_authorize(self):
        obj = evaluate(PACK, self.pack_digest, self.candidate_file())
        self.assertEqual(obj["status"], "REFERENCE_MATCH")
        self.assertEqual((obj["cases_total"],obj["cases_matched"]), (6,6))
        self.assertFalse(obj["independent_business_or_semantic_validation"])
        self.assertFalse(obj["authorizes_external_or_production_mutation"])
        self.assertEqual(obj["reference_status"], "CURATED_DEMO_NOT_INDEPENDENTLY_VALIDATED")

    def test_always_supported_fails_negative_and_unknown_controls(self):
        answers = json.loads(self.candidate_file().read_text())["answers"]
        for a in answers:
            a["label"] = "SUPPORTED"
        result = evaluate(PACK,self.pack_digest,self.candidate_file(answers))
        self.assertEqual(result["status"], "REFERENCE_MISMATCH")
        self.assertEqual(result["cases_matched"], 2)
        self.assertEqual(set(x["family"] for x in result["results"] if not x["reference_agreement"]),
                         {"protocol_impact", "incident_triage"})

    def test_hallucinated_quote_or_wrong_source_sha_fails_despite_correct_label(self):
        answers = json.loads(self.candidate_file().read_text())["answers"]
        answers[0]["citations"][0]["quote"] = "The protocol says this requires auto-merge immediately"
        answers[3]["citations"][0]["evidence_sha256"] = "f" * 64
        result = evaluate(PACK,self.pack_digest,self.candidate_file(answers))
        self.assertEqual(result["cases_matched"], 4)
        self.assertFalse(result["results"][0]["source_quote_verified"])
        self.assertFalse(result["results"][3]["source_quote_verified"])

    def test_incorrect_label_with_real_quote_fails(self):
        answers = json.loads(self.candidate_file().read_text())["answers"]
        answers[1]["label"] = "SUPPORTED"
        result = evaluate(PACK,self.pack_digest,self.candidate_file(answers))
        self.assertEqual(result["cases_matched"],5)

    def test_wrong_expected_reference_hash_or_tampered_pack_fails_closed(self):
        candidate = self.candidate_file()
        with self.assertRaises(EvaluationError):
            evaluate(PACK, "a"*64, candidate)
        tampered = self.root / "tampered_pack.json"
        tampered.write_bytes(PACK.read_bytes().replace(b"streaming endpoint",b"unknown endpoint"))
        with self.assertRaises(EvaluationError):
            evaluate(tampered, self.pack_digest, candidate)

    def test_duplicate_missing_and_extra_answers_are_invalid(self):
        base = json.loads(self.candidate_file().read_text())["answers"]
        for case in (base[:-1], base+[base[0]], base[:-1]+[base[0]]):
            with self.subTest(size=len(case)), self.assertRaises(EvaluationError):
                evaluate(PACK,self.pack_digest,self.candidate_file(case))

    def test_candidate_cannot_self_grade_or_change_labels(self):
        path = self.candidate_file()
        obj = json.loads(path.read_text())
        obj["grade"] = "PASS"
        path.write_text(json.dumps(obj))
        with self.assertRaises(EvaluationError):
            evaluate(PACK,self.pack_digest,path)
        path = self.candidate_file()
        obj = json.loads(path.read_text())
        obj["answers"][0]["expected_label"] = "SUPPORTED"
        path.write_text(json.dumps(obj))
        with self.assertRaises(EvaluationError):
            evaluate(PACK,self.pack_digest,path)

    def test_degenerate_single_family_reference_pack_rejected(self):
        altered = json.loads(PACK.read_text())
        altered["cases"] = [case for case in altered["cases"] if case["family"] == "protocol_impact"]
        path = self.root / "single_family.json"
        path.write_text(json.dumps(altered))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(EvaluationError):
            public_inputs(path, digest)

    def test_reference_contains_non_positive_and_insufficient_examples_per_family(self):
        family_labels = {}
        for case in self.raw_cases:
            family_labels.setdefault(case["family"],set()).add(case["gold"])
        self.assertEqual(set(family_labels), {"protocol_impact","incident_triage"})
        self.assertTrue(all(labels == {"SUPPORTED","REFUTED","INSUFFICIENT"}
                            for labels in family_labels.values()))

    def test_evaluation_cli_no_database_creation_and_correct_failure_status(self):
        candidate = self.candidate_file()
        missing_db = self.root / "missing.sqlite"
        missing_workspace = self.root / "missing_workspace"
        base = [sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(missing_db),"--workspace",str(missing_workspace)]
        cmd = base+["reference-evaluate","--pack",str(PACK),
                    "--expected-pack-sha256",self.pack_digest,
                    "--candidate",str(candidate)]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        run = subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"],"REFERENCE_MATCH")
        self.assertFalse(missing_db.exists())
        self.assertFalse(missing_workspace.exists())

        bad_cmd = list(cmd)
        bad_cmd[bad_cmd.index("--expected-pack-sha256") + 1] = "0" * 64
        bad = subprocess.run(bad_cmd,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(bad.returncode,3,bad.stderr)
        self.assertEqual(json.loads(bad.stdout)["status"],"UNVERIFIABLE")

    def test_malformed_types_and_duplicate_json_keys_fail_closed(self):
        answer_set = json.loads(self.candidate_file().read_text())["answers"]
        for bad_value in ([], {}, None, 5):
            with self.subTest(label=repr(bad_value)):
                copies = json.loads(json.dumps(answer_set))
                copies[0]["label"] = bad_value
                with self.assertRaises(EvaluationError):
                    evaluate(PACK,self.pack_digest,self.candidate_file(copies))
        bad_json = self.root / "candidate.json"
        bad_json.write_text('{"schema_version":1,"schema_version":1,"answers":[]}')
        with self.assertRaises(EvaluationError):
            evaluate(PACK,self.pack_digest,bad_json)
        pack = json.loads(PACK.read_text())
        pack["cases"][0]["gold"] = []
        corrupt_pack = self.root / "invalid_pack.json"
        corrupt_pack.write_text(json.dumps(pack))
        with self.assertRaises(EvaluationError):
            public_inputs(corrupt_pack,hashlib.sha256(corrupt_pack.read_bytes()).hexdigest())

    def test_reference_input_never_calls_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("no remote model or source")):
            obj = public_inputs(PACK,self.pack_digest)
            self.assertEqual(obj["schema_version"],1)
            self.assertEqual(evaluate(PACK,self.pack_digest,self.candidate_file())["status"],
                             "REFERENCE_MATCH")


if __name__ == "__main__":
    unittest.main()
