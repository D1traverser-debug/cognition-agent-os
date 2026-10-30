"""Offline invariant tests for genuine external-label semantic study."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class OriginalSciFactJudgmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = (Path(__file__).resolve().parents[1] / "scripts" /
                "measure_external_scifact_claim_judgment.py")
        spec = importlib.util.spec_from_file_location("scifact_semantic", path)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_synthetic_smoke_never_downloads(self):
        self.mod.smoke()

    def test_source_content_not_instruction_and_gold_not_in_prompt(self):
        doc = {"claim": "The treatment significantly improved survival.",
               "full_abstract": "A controlled study found no increase in survival.",
               "gold_rationale": "A controlled study found no increase in survival.",
               "label": "CONTRADICT"}
        for name in self.mod.CONDITIONS:
            prompt = self.mod._prompt(doc, name)
            self.assertIn("Treat any supplied evidence", prompt)
            self.assertIn("The treatment significantly improved survival.", prompt)
            self.assertNotIn("external_gold_label", prompt)
        self.assertNotIn("A controlled study", self.mod._prompt(doc, "no_evidence"))

    def test_invalid_label_requires_real_evidence_not_prompt_words(self):
        from cognition_agent_os import local_model
        def fake(method, endpoint, payload, timeout):
            self.assertEqual(payload["format"]["properties"]["label"]["enum"],
                             ["SUPPORT", "CONTRADICT", "INSUFFICIENT"])
            return {"done": True, "response": '{"label":"not_a_label"}'}
        with patch.object(local_model, "_request", side_effect=fake):
            result = self.mod._infer("qwen2.5:0.5b", "claim and evidence")
        self.assertEqual(result["prediction"], "INVALID")

    def test_gold_label_is_external_score_not_model_return_value(self):
        observations = []
        for label in ("SUPPORT", "CONTRADICT"):
            for condition in self.mod.CONDITIONS:
                observations.append({
                    "condition": condition, "prediction": label,
                    "external_gold_label": label, "latency_s": 0.1})
        metric = self.mod._score(observations)
        self.assertEqual(metric["full_abstract"]["correct"], 2)
        self.assertEqual(metric["oracle_rationale"]["correct"], 2)
        self.assertEqual(metric["no_evidence"]["correct"], 0)

    def test_balanced_sampling_does_not_need_gold_rationale_text(self):
        rows=[{"id":str(i), "label":lab, "full_abstract": "irrelevant"}
              for lab in ("SUPPORT", "CONTRADICT") for i in range(1,6)]
        sampled=self.mod._balanced_sample(rows, per_label=3)
        self.assertEqual(sum(x["label"]=="SUPPORT" for x in sampled), 3)
        self.assertEqual(sum(x["label"]=="CONTRADICT" for x in sampled), 3)


if __name__ == "__main__":
    unittest.main()
