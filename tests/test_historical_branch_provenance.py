"""Frozen Git-blob provenance guard for old PR evidence; NOT runtime acceptance.

This test uses only repository-local archived bytes and a dated exact-source
receipt. It does not connect GitHub or infer historical PR semantic equivalence,
safe closure, owner permission or a production memory engine.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
RECEIPT=ROOT/"evaluation"/"historical_branch_provenance_v1.json"
SHA=re.compile(r"[0-9a-f]{40}\Z")


def git_blob_sha1(raw:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\x00"+raw).hexdigest()


class HistoricalBranchProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_archive_is_bitwise_identical_to_prior_branch_not_just_same_name(self):
        obs=self.data["archived_byte_identical_from_pr49"]["mappings"]
        self.assertEqual(len(obs),7)
        self.assertEqual(len({x["original_path"] for x in obs}),len(obs))
        self.assertEqual(len({x["preserved_path"] for x in obs}),len(obs))
        for row in obs:
            path=row["preserved_path"]
            self.assertTrue(path.startswith("archive/"),path)
            target=(ROOT/path).resolve()
            self.assertTrue(target.is_relative_to(ROOT),path)
            self.assertTrue(target.is_file() and not target.is_symlink(),path)
            self.assertEqual(git_blob_sha1(target.read_bytes()),
                             row["original_git_blob_sha1"],path)

    def test_isolated_retrieval_research_is_neither_dropped_nor_auto_promoted(self):
        entries=self.data["isolated_not_promoted_from_pr32"]["paths"]
        self.assertEqual(len(entries),15)
        self.assertEqual(len({x["path"] for x in entries}),len(entries))
        self.assertIn("src/cognition_agent_os/evidence_ranker.py",
                      {x["path"] for x in entries})
        for row in entries:
            self.assertRegex(row["git_blob_sha1"],SHA)
            self.assertFalse((ROOT/row["path"]).exists(),
                             "research candidate accidentally entered active tree")
        self.assertIn("DO_NOT_PROMOTE_ISOLATED_RETRIEVAL_RESEARCH_AS_AUTHORITY",
                      self.data["prohibitions"])

    def test_history_is_versioned_not_an_instruction_to_close_pr(self):
        d=self.data
        self.assertEqual(d["schema"],
                         "cognition-historical-branches-frozen-source-inventory-v1")
        self.assertIn("NOT_CURRENT_GITHUB",d["status"])
        self.assertIn("DO_NOT_AUTOMATICALLY_CLOSE_OR_MERGE_BRANCHES",d["prohibitions"])
        p=d["old_pr_observations"]
        self.assertEqual(len(p),28)
        self.assertEqual(len({x["pr"] for x in p}),len(p))
        self.assertTrue(all(x["observed_draft"] is True for x in p))
        self.assertTrue(all(SHA.fullmatch(x["observed_head_sha"]) for x in p))
        self.assertNotIn(53,{x["pr"] for x in p})
        self.assertIn("semantic equivalence", " ".join(d["evidence_limitations"]))

    def test_negative_changed_byte_no_false_equivalence(self):
        original=b"source"
        self.assertNotEqual(git_blob_sha1(original),
                            git_blob_sha1(original+b" "))
        self.assertEqual(git_blob_sha1(b""),hashlib.sha1(b"blob 0\x00").hexdigest())


if __name__=="__main__":
    unittest.main()
