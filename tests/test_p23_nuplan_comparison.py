"""P23 frozen outside issue: provenance, deterministic gold and scope controls."""
import json
import unittest
from unittest.mock import patch

from scripts import verify_p23_nuplan_comparison as p23

FAKE_UPSTREAM = (
    b"from typing import Optional\n"
    b"GeometryMap = dict\n"
    b"class STRTreeOccupancyMap:\n"
    b"    def _get_other_geometries(self, ignore_id: str) -> GeometryMap:\n"
    b"        # This intentionally retains the upstream defect.\n"
    b"        return {geom_id: geom for geom_id, geom in self._geom_map.items() if geom_id not in ignore_id}\n"
)

class P23IndependentOutsideRepairTests(unittest.TestCase):
    def test_pinned_outside_identity_not_a_reused_prior_issue(self):
        self.assertEqual(p23.UPSTREAM_REPOSITORY, "motional/nuplan-devkit")
        self.assertEqual(p23.UPSTREAM_COMMIT, "e9241677")
        self.assertEqual(p23.UPSTREAM_GIT_BLOB, "c61a13776fcb1fc55a43daa826a757eb992e4bda")
        self.assertEqual(p23.ISSUE,"https://github.com/motional/nuplan-devkit/issues/429")
        self.assertIn("/e9241677/",p23.source_url())
        self.assertNotIn("/master/",p23.source_url())
        self.assertLess(len(p23.GOAL.encode()),1200)
        self.assertEqual(len(p23.PUBLIC),4)
        self.assertEqual(len(p23.HIDDEN),8)

    def test_hidden_reference_oracle_and_original_bug_baseline(self):
        # The independent expected values are keyed equality and preserve
        # payloads. They do not use model proposals or precomputed patches.
        for row in p23.PUBLIC+p23.HIDDEN:
            data=row["input"]
            expected={k:v for k,v in data["geometries"].items()
                      if k != data["ignore_id"]}
            self.assertEqual(row["expected"],{"remaining":expected})
        broken=[]
        for row in p23.PUBLIC:
            data=row["input"]
            actual={k:v for k,v in data["geometries"].items()
                    if k not in data["ignore_id"]}
            broken.append(actual == row["expected"]["remaining"])
        self.assertEqual(broken,[False,True,False,True])
        self.assertNotEqual(json.dumps(p23.PUBLIC,sort_keys=True),
                            json.dumps(p23.HIDDEN,sort_keys=True))

    def test_exact_original_method_extraction_and_format_ab_identity(self):
        pinned=p23.git_blob_sha1(FAKE_UPSTREAM)
        with patch.object(p23,"UPSTREAM_GIT_BLOB",pinned):
            method=p23.extract_original_method(FAKE_UPSTREAM)
            self.assertIn("not in ignore_id",method)
            self.assertTrue(method.startswith("    def _get_other_geometries("))
            whole=p23.make_case(FAKE_UPSTREAM,False)
            compact=p23.make_case(FAKE_UPSTREAM,True)
            self.assertEqual(whole["source"],compact["source"])
            self.assertEqual(whole["public"],compact["public"])
            self.assertEqual(whole["hidden"],compact["hidden"])
            self.assertEqual(whole["goal_statement"],compact["goal_statement"])
            self.assertNotIn("candidate_format",whole)
            self.assertEqual(compact["candidate_format"],"exact_replace")
            self.assertEqual(whole["name"],"p23_nuplan_full")
            self.assertEqual(compact["name"],"p23_nuplan_compact")
            digest=p23.manifest(FAKE_UPSTREAM)
            self.assertEqual(len(digest),64)
            self.assertTrue(all(c in "0123456789abcdef" for c in digest))
            with self.assertRaises(ValueError):
                p23.extract_original_method(FAKE_UPSTREAM+b"# mutated")

    def test_scope_accepted_is_not_semantic_acceptance(self):
        pinned=p23.git_blob_sha1(FAKE_UPSTREAM)
        with patch.object(p23,"UPSTREAM_GIT_BLOB",pinned):
            method=p23.extract_original_method(FAKE_UPSTREAM)
            original=p23.PREFIX+method+p23.ADAPTER
            altered=method.replace("return {geom_id:", "return {geom_id:").replace(
                "if geom_id not in ignore_id","if False")
            self.assertTrue(p23.preserves_scope((p23.PREFIX+altered+p23.ADAPTER).encode(),method))
            self.assertFalse(p23.preserves_scope(original.encode(),method))
            self.assertFalse(p23.preserves_scope(
                (p23.PREFIX+altered+p23.ADAPTER+"# attacker").encode(),method))
            self.assertFalse(p23.preserves_scope(
                (p23.PREFIX+"    def evil(self):\n        return 1\n"+p23.ADAPTER).encode(),method))
            # Other top-level code could have escaped the old single-method
            # reviewer: it must never be considered an isolated method patch.
            self.assertFalse(p23.preserves_scope(
                (p23.PREFIX+altered+"\nimport math\n"+p23.ADAPTER).encode(),method))
            self.assertFalse(p23.preserves_scope(
                (p23.PREFIX+"    @staticmethod\n"+altered+p23.ADAPTER).encode(),method))
            self.assertFalse(p23.preserves_scope(b"\xff\xfe",method))

    def test_fail_closed_ambiguous_class_or_method(self):
        pin=p23.git_blob_sha1(FAKE_UPSTREAM+FAKE_UPSTREAM)
        with patch.object(p23,"UPSTREAM_GIT_BLOB",pin):
            with self.assertRaises(ValueError):
                p23.extract_original_method(FAKE_UPSTREAM+FAKE_UPSTREAM)
        empty=b"class Other:\n    pass\n"
        with patch.object(p23,"UPSTREAM_GIT_BLOB",p23.git_blob_sha1(empty)):
            with self.assertRaises(ValueError):
                p23.extract_original_method(empty)

if __name__=="__main__":
    unittest.main()
