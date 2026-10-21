"""P21 scope and independently reported edge behavior tests (offline only)."""
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

from cognition_agent_os.container_lab import cases_from_bytes
from scripts import verify_p21_live_issue as p21


class ExternalLiveIssueTests(unittest.TestCase):
    def test_issue_is_exact_recent_external_report_not_self_authored(self):
        self.assertEqual(p21.ISSUE_NUMBER,1332)
        self.assertEqual(p21.UPSTREAM_REPOSITORY,"more-itertools/more-itertools")
        self.assertEqual(p21.ISSUE_URL,
                         "https://github.com/more-itertools/more-itertools/issues/1332")
        self.assertEqual(p21.UPSTREAM_COMMIT,
                         "4aeb4338ae1407d8da9723e86da99efeb446f719")
        self.assertRegex(p21.UPSTREAM_GIT_BLOB,r"^[0-9a-f]{40}$")
        self.assertEqual(len(p21.GOAL_STATEMENT.encode()),len(
            p21.GOAL_STATEMENT.encode("utf-8")))
        self.assertLess(len(p21.GOAL_STATEMENT.encode()),1200)
        self.assertIn(p21.UPSTREAM_COMMIT,p21.source_url())
        self.assertNotIn("/main/",p21.source_url())
        self.assertNotIn("/master/",p21.source_url())

    def test_reporter_owned_public_bug_vs_pinned_hidden_edge_cases(self):
        self.assertEqual(p21.PUBLIC[0],{"input":{"items":[]},"expected":{
            "count":1,"has_empty_partition":True}})
        self.assertEqual(len(p21.PUBLIC),2)
        self.assertEqual(len(p21.HIDDEN),8)
        self.assertEqual(len(cases_from_bytes(
            json.dumps(p21.HIDDEN).encode())),8)
        self.assertIn({"input":{"items":[],"k":1},"expected":{
            "count":0,"has_empty_partition":False}},p21.HIDDEN)
        self.assertIn({"input":{"items":[],"k":0},"expected":{
            "error":"ValueError"}},p21.HIDDEN)
        self.assertIn({"input":{"items":[],"min_size":2},"expected":{
            "count":1,"has_empty_partition":True}},p21.HIDDEN)
        for row in p21.HIDDEN:
            self.assertNotIn(json.dumps(row["input"],sort_keys=True),
                json.dumps(p21.PUBLIC,sort_keys=True))

    def test_bell_numbers_of_report_match_independent_combinatorics(self):
        # Not a replacement for external maintainer business acceptance:
        # this checks the author's Bell counts using independent
        # Stirling numbers, not this module's repair source.
        stirling=[[1]]
        for n in range(1,6):
            last=stirling[-1]
            nxt=[0]*(n+1)
            for k in range(1,n+1):
                nxt[k]=(last[k-1] if k-1<len(last) else 0)+(
                    k*last[k] if k<len(last) else 0)
            stirling.append(nxt)
        bells=[sum(x) for x in stirling]
        self.assertEqual(bells,[1,1,2,5,15,52])
        for n in (1,3,4,5):
            target={"input":{"items":list(range(n))},"expected":{
                "count":bells[n],"has_empty_partition":False}}
            if n==1:
                self.assertEqual(p21.HIDDEN[2]["expected"],target["expected"])
            if n==3:
                self.assertEqual(p21.HIDDEN[3]["expected"],target["expected"])
            if n in (4,5):
                self.assertIn(target,p21.HIDDEN)

    def test_function_extraction_has_exact_snapshot_identity(self):
        upstream=(
            b"# original header\n"
            b"def set_partitions(iterable, k=None):\n"
            b"    L = list(iterable)\n"
            b"    def set_partitions_helper(L, k):\n"
            b"        yield [L]\n"
            b"    n = len(L)\n"
            b"    if k is None:\n"
            b"        for k in range(1, n + 1):\n"
            b"            yield from set_partitions_helper(L, k)\n"
            b"\nclass time_limited:\n    pass\n"
        )
        # The exact upstream blob is much larger: substitute a mock pin
        # only for offline parser behavior, never for a genuine CI result.
        pinned=p21.git_blob_sha1(upstream)
        with patch.object(p21,"UPSTREAM_GIT_BLOB",pinned):
            extracted=p21.extract_unmodified_function(upstream)
            self.assertTrue(extracted.startswith("def set_partitions("))
            self.assertNotIn("class time_limited",extracted)
            case=p21.prepare_case(upstream)
            self.assertIn("def calculate(data):",case["source"])
            self.assertEqual(case["source"].split("\n\ndef calculate(data):")[0],
                             extracted.rstrip("\n"))
            self.assertEqual(len(case["public"]),2)
            self.assertEqual(len(case["hidden"]),8)
            with self.assertRaises(ValueError):
                p21.extract_unmodified_function(upstream+b"\n# tampered")
        self.assertNotEqual(pinned,p21.UPSTREAM_GIT_BLOB)

    def test_no_actual_issue_access_or_inference_without_exact_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            env=dict(os.environ)
            env["P14_LOCAL_MODEL"]="qwen2.5-coder:0.5b"
            env.pop("P21_ISSUE_OPT_IN",None)
            env.pop("PYTHONPATH",None)
            x=subprocess.run([
                sys.executable,str(Path(__file__).resolve().parents[1]/
                    "scripts"/"verify_p21_live_issue.py")],
                cwd=directory,env=env,capture_output=True,text=True,
                timeout=12)
            self.assertNotEqual(x.returncode,0)
            self.assertIn("one-time explicitly approved local 7B CI",x.stderr)
            self.assertNotIn("ModuleNotFoundError",x.stderr)

    def test_source_blob_hash_uses_actual_git_binary_blob_format(self):
        original=b"hello"
        expected=hashlib.sha1(b"blob 5\0hello").hexdigest()
        self.assertEqual(p21.git_blob_sha1(original),expected)
        self.assertEqual(p21.UPSTREAM_GIT_BLOB.__len__(),40)


if __name__=="__main__":
    unittest.main()
