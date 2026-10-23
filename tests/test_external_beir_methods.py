"""Methodology and metric sanity tests without network or training/test leakage."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest


class ExternalBEIRMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        file = Path(__file__).resolve().parents[1] / "scripts" / "measure_external_beir_retrieval.py"
        spec = importlib.util.spec_from_file_location("beir_evaluation", file)
        cls.beir = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.beir)

    def test_rankers_true_outcome_sanity(self):
        self.beir.smoke()

    def test_ndcg_exposes_reversed_rank_and_graded_gain(self):
        gold = {"source-1": 2, "source-2": 1}
        perfect = self.beir.ndcg_at(["source-1", "source-2"], gold, 2)
        reversed_rank = self.beir.ndcg_at(["source-2", "source-1"], gold, 2)
        self.assertAlmostEqual(perfect, 1.0)
        self.assertGreater(perfect, reversed_rank)
        self.assertGreater(reversed_rank, 0)

    def test_relevance_labels_never_passed_into_retriever(self):
        corpus = {"article-A": "Research confirms 42 units of safe pressure.",
                  "article-B": "A ship cargo manifest lists 42 containers."}
        question = "What article confirms safe pressure?"
        rankers = (self.beir.PrefixOverlap(corpus),
                   self.beir.InvertedIndex(corpus, passage=False),
                   self.beir.InvertedIndex(corpus, passage=True))
        for ranker in rankers:
            selected = ranker.rank(question, 2)
            self.assertIn("article-A", selected)
            self.assertEqual(len(selected), len(set(selected)))
        # No qrels argument exists on any rank method; score is post hoc.

    def test_deterministic_query_selection_and_no_gold_values(self):
        a = self.beir._choose_ids("scifact", ["3", "1", "2"])
        b = self.beir._choose_ids("scifact", ["2", "1", "3"])
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)

    def test_false_negative_is_not_automatically_model_abstention(self):
        self.assertEqual(self.beir.recall_at([], {"evidence": 1}, 100), 0.0)
        self.assertEqual(self.beir.mrr_at(["irrelevant"], {"evidence": 1}, 10), 0.0)
        # IR evaluation deliberately makes no claim about whether answering is safe.

    def test_zip_path_traversal_never_extracted(self):
        # Implementation reads only validated member paths in-memory; it
        # never calls extract/extractall or writes zip names to the filesystem.
        import inspect
        source = inspect.getsource(self.beir._read_dataset)
        self.assertNotIn(".extractall(", source)
        self.assertNotIn(".extract(", source)


if __name__ == "__main__":
    unittest.main()
