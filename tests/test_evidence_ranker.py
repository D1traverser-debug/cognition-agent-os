"""Independent boundary and metric tests for retrieval contender (no model)."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.evidence_ranker import (
    chunk_bm25, prefix_overlap, select_docs, tokens, windows)


class EvidenceMethodTests(unittest.TestCase):
    def test_query_pinned_input_no_gold_parameter(self):
        docs = {"a.md": "A safety review approved 42 units.",
                "b.md": "The lunch schedule was changed."}
        self.assertTrue(chunk_bm25("What units did the safety review approve?", docs)["a.md"] >
                        chunk_bm25("What units did the safety review approve?", docs)["b.md"])

    def test_suffix_decisive_information_not_lost_in_chunking(self):
        prefix = "Old report contains no specific pressure figures. " * 20
        evidence = prefix + "The final compressor limit is 42 kilopascals."
        self.assertTrue(any("42 kilopascals" in x for x in windows(evidence)))
        self.assertLessEqual(len(windows(evidence)[-1]), 650)
        docs = {"a.md": evidence,
                "b.md": prefix + "The final canteen order is sandwiches."}
        q = "What is the final compressor limit in kilopascals?"
        self.assertGreater(chunk_bm25(q, docs)["a.md"], chunk_bm25(q, docs)["b.md"])

    def test_no_evidence_not_faked(self):
        docs = {"a.md": "Kitchen inventory includes fruit and bread."}
        self.assertEqual(select_docs("What is the pump's serial identifier?",
                                     docs, method="chunk_bm25", cutoff=32), [])

    def test_scope_bad_input_fail_closed(self):
        with self.assertRaises(ValueError):
            chunk_bm25("", {"a.md": "text"})
        with self.assertRaises(ValueError):
            select_docs("x", {"a.md": "value"}, method="unknown", cutoff=0)
        with self.assertRaises(ValueError):
            chunk_bm25("y", {"a.md": "b" * 12001})

    def test_chinese_tokenization_is_explicit_not_silent_english_only(self):
        self.assertIn("证", tokens("验证变更必须批准"))
        self.assertIn("批", tokens("验证变更必须批准"))

    def test_preregistered_holdout_never_used_to_calibrate(self):
        from scripts.evaluate_evidence_retrieval import run
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "experiment.json"
            report = run(output=out)
            self.assertTrue(out.is_file())
            self.assertEqual(len(json.loads(out.read_text())["methods"]), 2)
            self.assertFalse(report["release_authorized"])
            self.assertFalse(report["model_inference_executed"])
            for method in report["methods"].values():
                self.assertEqual(method["development"]["total"], 8)
                self.assertEqual(method["holdout"]["total"], 16)
                self.assertGreaterEqual(method["holdout"]["false_answerable"], 0)


if __name__ == "__main__":
    unittest.main()
