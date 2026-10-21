"""P22 prospective external source, scope, and acceptance-contract tests.

No real model is called in ordinary CI; that needs temporary PR opt-in.
"""
from __future__ import annotations
import hashlib
import json
import unittest
from unittest.mock import patch

from scripts import verify_p22_cpython_userstring as p22

class P22FrozenExternalIssueTests(unittest.TestCase):
    def test_real_issue_and_immutable_preissue_source(self):
        self.assertEqual(p22.UPSTREAM_REPOSITORY,"python/cpython")
        self.assertEqual(p22.UPSTREAM_COMMIT,
                         "d220409a13b77de7a6c30abe16ea90db01528edc")
        self.assertEqual(p22.UPSTREAM_GIT_BLOB,
                         "5dbcac19e7a92726fb9594f406177870db1c08bd")
        self.assertEqual(p22.ISSUE_URL,
                         "https://github.com/python/cpython/issues/159868")
        self.assertIn(p22.UPSTREAM_COMMIT,p22.source_url())
        self.assertNotIn("/main/",p22.source_url())
        self.assertLess(len(p22.GOAL_STATEMENT.encode()),1300)
        self.assertEqual(len(p22.PUBLIC),4)
        self.assertEqual(len(p22.HIDDEN),8)
        self.assertEqual({r["input"]["method"] for r in p22.PUBLIC},
                         {"startswith","endswith"})
        self.assertEqual(sum(r["input"]["type"]=="UserString"
                             for r in p22.PUBLIC),2)
        self.assertNotIn(json.dumps(p22.HIDDEN,sort_keys=True),
                         json.dumps(p22.PUBLIC,sort_keys=True))

    def test_independent_reference_values_not_from_buggy_implementation(self):
        # For a valid UserString argument the expected answer has the
        # underlying str's match semantics; for an unsupported int, native
        # string methods still raise TypeError. This is independent of
        # whatever code the real model proposes.
        for row in p22.PUBLIC+p22.HIDDEN:
            inp=row["input"]
            data=inp["text"]
            if inp["type"]=="int":
                self.assertEqual(row["expected"],{"error":"TypeError"})
            else:
                arg=inp["affix"]
                result=getattr(data,inp["method"])(
                    arg,inp.get("start",0),inp.get("end",2**63-1))
                self.assertEqual(row["expected"],{"match":bool(result)})

    def test_original_extraction_rejects_changed_git_blob(self):
        old=(b"# preissue upstream header\n"
             b"class UserString(_collections_abc.Sequence):\n"
             b"    def removeprefix(self, prefix):\n"
             b"        return prefix\n"
             b"    def endswith(self, suffix, start=0, end=42):\n"
             b"        return self.data.endswith(suffix, start, end)\n"
             b"    def startswith(self, prefix, start=0, end=42):\n"
             b"        return self.data.startswith(prefix, start, end)\n")
        pin=p22.git_blob_sha1(old)
        with patch.object(p22,"UPSTREAM_GIT_BLOB",pin):
            extracted=p22.extract_unmodified_class(old)
            self.assertTrue(extracted.startswith("class UserString("))
            self.assertNotIn("preissue upstream header",extracted)
            case=p22.prepare_case(old)
            self.assertTrue(case["source"].startswith(p22.PREFIX))
            self.assertTrue(case["source"].endswith(p22.ADAPTER))
            self.assertEqual(case["public"],p22.PUBLIC)
            self.assertEqual(case["hidden"],p22.HIDDEN)
            self.assertEqual(case["candidate_format"],"exact_replace")
            self.assertEqual(case["goal_statement"],p22.GOAL_STATEMENT)
            with self.assertRaises(ValueError):
                p22.extract_unmodified_class(old+b"# mutated upstream bytes")
        self.assertNotEqual(pin,p22.UPSTREAM_GIT_BLOB)

    def test_scoped_posteffect_gate_enforces_both_methods_only(self):
        original=(
            "class UserString(_collections_abc.Sequence):\n"
            "    def __init__(self, value):\n"
            "        self.data = value\n"
            "    def startswith(self, prefix, start=0, end=10):\n"
            "        return self.data.startswith(prefix, start, end)\n"
            "    def endswith(self, suffix, start=0, end=10):\n"
            "        return self.data.endswith(suffix, start, end)\n"
            "    def lower(self):\n"
            "        return self.data.lower()\n")
        # These are intentionally BAD semantic changes. A scope PASS
        # alone never establishes functional correctness.
        edited=original.replace(
            "return self.data.startswith(prefix, start, end)",
            "return False").replace(
            "return self.data.endswith(suffix, start, end)",
            "return True")
        candidate=(p22.PREFIX+edited+p22.ADAPTER).encode()
        self.assertTrue(p22.candidate_preserves_scope(candidate,original))
        self.assertFalse(p22.candidate_preserves_scope(
            (p22.PREFIX+original+p22.ADAPTER).encode(),original))
        self.assertFalse(p22.candidate_preserves_scope(
            (p22.PREFIX+edited.replace("return self.data.lower()",
                                     "return None")+p22.ADAPTER).encode(),
            original))
        self.assertFalse(p22.candidate_preserves_scope(
            (p22.PREFIX+edited+p22.ADAPTER.replace("'match'","'fake'")).encode(),
            original))
        self.assertFalse(p22.candidate_preserves_scope(
            b"import os\n"+candidate,original))
        self.assertFalse(p22.candidate_preserves_scope(
            b"\xffnot utf8",original))
        self.assertFalse(p22.candidate_preserves_scope(
            (p22.PREFIX+original.replace("return self.data.startswith(prefix, start, end)",
                                          "return False")+p22.ADAPTER).encode(),
            original))

if __name__=="__main__":
    unittest.main()
