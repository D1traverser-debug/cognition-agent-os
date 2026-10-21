"""P21 scope and independently reported edge behavior tests (offline only)."""
from __future__ import annotations

from contextlib import closing
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
from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.runner import run_once
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
            self.assertTrue(case["source"].startswith(extracted))
            self.assertEqual(case["source"].count("def calculate(data):"),1)
            self.assertEqual(len(case["public"]),2)
            self.assertEqual(len(case["hidden"]),8)
            with self.assertRaises(ValueError):
                p21.extract_unmodified_function(upstream+b"\n# tampered")
        self.assertNotEqual(pinned,p21.UPSTREAM_GIT_BLOB)

    def test_independent_patch_scope_disallows_adapter_rewriting(self):
        original="def set_partitions(items):\n    yield [items]\n"
        adapter=(
            "\n\ndef calculate(data):\n"
            "    return {'count':len(list(set_partitions(data['items'])))}\n"
        )
        genuine=(
            "def set_partitions(items):\n"
            "    if not items:\n        yield []\n        return\n"
            "    yield [items]\n"+adapter
        ).encode()
        self.assertTrue(p21.candidate_preserves_adapter(
            genuine,original,adapter))
        self.assertFalse(p21.candidate_preserves_adapter(
            (original+adapter).encode(),original,adapter))
        self.assertFalse(p21.candidate_preserves_adapter(
            (original+adapter.replace("count","fake")).encode(),
            original,adapter))
        self.assertFalse(p21.candidate_preserves_adapter(
            b"import os\n"+genuine,original,adapter))
        self.assertFalse(p21.candidate_preserves_adapter(
            b"not valid utf8 \\xff",original,adapter))

    def _new_repair_task_for_local_retry(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        base=Path(folder.name)
        fx=base/"fx";fx.mkdir()
        ws=base/"workspace";ws.mkdir()
        db=base/"state.sqlite"
        source="def calculate(data):\n    return {'out':0}\n"
        expected="def calculate(data):\n    return {'out':data['x']+1}\n"
        fx.joinpath("main.py").write_text(
            "import json,sys\nfrom rules import calculate\n"
            "print(json.dumps(calculate(json.loads(sys.stdin.read()))))\n")
        fx.joinpath("rules.py").write_text(source)
        visible=[{"input":{"x":1},"expected":{"out":2}}]
        hidden=[{"input":{"x":37},"expected":{"out":38}}]
        fx.joinpath("visible.json").write_text(json.dumps(visible))
        sealed=json.dumps(hidden).encode()
        fx.joinpath("sealed.json").write_bytes(sealed)
        fx.joinpath("candidate.json").write_text(
            json.dumps({"changes":[{"path":"rules.py","content":source}]}))
        spec={"kind":"repo_container_repair",
              "files":["main.py","rules.py"],"entrypoint":"main.py",
              "candidate":"candidate.json","visible":"visible.json",
              "holdout":"sealed.json",
              "holdout_sha256":hashlib.sha256(sealed).hexdigest(),
              "goal_statement":"Compute x plus one."}
        with closing(connect(db)) as con:
            initialize(con)
            tid=create_task(con,spec)
        return fx,ws,db,tid,source,expected

    def test_model_nochange_regenerates_only_once_with_public_rejection(self):
        fx,ws,db,tid,original,repaired=self._new_repair_task_for_local_retry()
        seen=[]
        def model(spec,base,visible,model,*,feedback=None):
            self.assertNotIn("sealed",str(feedback))
            seen.append(feedback)
            code=original if len(seen)==1 else repaired
            return json.dumps({"changes":[{"path":"rules.py","content":code}]}).encode()
        with patch.dict(os.environ,{"COGNITION_LOCAL_NOCHANGE_RETRY":"1"}),\
             patch("cognition_agent_os.repo_repair._candidate_from_model",
                   side_effect=model) as local:
            answer=run_once(db,ws,fx,planner_mode="ollama-local",
                            local_model="qwen2.5-coder:7b")
        self.assertEqual(answer["status"],"NEEDS_REVIEW",answer)
        self.assertTrue(answer["nochange_retry_attempted"])
        self.assertEqual(answer["completed_model_generations"],2)
        self.assertEqual(local.call_count,2)
        self.assertIsNone(seen[0])
        self.assertEqual(seen[1]["latest_rejection"]["reason"],
                         "MODEL_CANDIDATE_NO_CHANGE")
        self.assertTrue(seen[1]["latest_rejection"]["must_propose_different_full_source"])
        document=json.loads((ws/"artifacts"/(tid+".json")).read_text())
        self.assertEqual(document["initial_model_generations"],2)
        self.assertEqual(document["initial_public_rejections"][0]["reason"],
                         "MODEL_CANDIDATE_NO_CHANGE")
        self.assertEqual(document["changes"]["rules.py"],repaired)
        self.assertEqual(fx.joinpath("rules.py").read_text(),original)
        self.assertNotIn("sealed",json.dumps(document["initial_public_rejections"]))

    def test_retry_cannot_escape_nochange_or_opt_in_budget(self):
        from cognition_agent_os.repo_repair import audit_repo
        for flag,expected_calls in (("0",1),("1",2),("2",1)):
            with self.subTest(flag=flag):
                fx,ws,db,tid,source,_=self._new_repair_task_for_local_retry()
                output=json.dumps({"changes":[
                    {"path":"rules.py","content":source}]}).encode()
                with patch.dict(os.environ,{"COGNITION_LOCAL_NOCHANGE_RETRY":flag}),\
                     patch("cognition_agent_os.repo_repair._candidate_from_model",
                           return_value=output) as local:
                    result=run_once(db,ws,fx,planner_mode="ollama-local",
                                    local_model="qwen2.5-coder:7b")
                self.assertEqual(result["status"],"UNKNOWN",result)
                self.assertTrue(result["model_called"])
                self.assertEqual(local.call_count,expected_calls)
                self.assertEqual(result["completed_model_generations"],expected_calls)
                self.assertFalse((ws/"artifacts"/(tid+".json")).exists())
                self.assertNotEqual(audit_repo(db,ws,fx,tid)["status"],
                                    "REPO_BYTES_MECHANICALLY_VALID")

    def test_post_initial_retry_public_refiner_gets_only_one_more_call(self):
        from cognition_agent_os.repo_refinement import refine_repo_public
        fx,ws,db,tid,original,repaired=self._new_repair_task_for_local_retry()
        outputs=[
            json.dumps({"changes":[{"path":"rules.py","content":original}]}).encode(),
            json.dumps({"changes":[{"path":"rules.py","content":repaired}]}).encode()
        ]
        with patch.dict(os.environ,{"COGNITION_LOCAL_NOCHANGE_RETRY":"1"}),\
             patch("cognition_agent_os.repo_repair._candidate_from_model",
                   side_effect=outputs):
            result=run_once(db,ws,fx,planner_mode="ollama-local",
                            local_model="qwen2.5-coder:7b")
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        def failing_suite(base,changes,entrypoint,cases,*,include_observed=False):
            return {"passes":0,"total":len(cases),
                    "observed":[{"pass":False,"output_sha256":"0"*64}
                                for _ in cases]}
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=failing_suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   return_value=json.dumps({"changes":[{
                       "path":"rules.py",
                       "content":"def calculate(data):\\n    return {'out':data['x']+2}\\n"
                   }]}).encode()) as model:
            verdict=refine_repo_public(db,ws,fx,tid,
                                       model="qwen2.5-coder:7b",max_attempts=3)
        self.assertEqual(verdict["status"],"PUBLIC_REFINEMENT_BUDGET_EXHAUSTED")
        self.assertEqual(verdict["attempts"],1)
        self.assertEqual(model.call_count,1)
        with closing(connect(db)) as con:
            count=con.execute("""SELECT COUNT(*) FROM events WHERE task_id=?
                AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",(tid,)).fetchone()[0]
        self.assertEqual(count,1)

    def test_local_7b_generation_timeout_is_strictly_bounded(self):
        from cognition_agent_os.repo_repair import _local_generate_timeout
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(_local_generate_timeout("qwen2.5-coder:7b"),180)
            self.assertEqual(_local_generate_timeout("qwen2.5-coder:3b"),90)
        with patch.dict(os.environ,{
                "COGNITION_LOCAL_7B_GENERATE_TIMEOUT_SECONDS":"300"}):
            self.assertEqual(_local_generate_timeout("qwen2.5-coder:7b"),300)
            self.assertEqual(_local_generate_timeout("qwen2.5-coder:0.5b"),90)
        from cognition_agent_os.local_model import LocalModelUnavailable
        for rejected in ("0","999999","301","nan","-1"," 300 ",""):
            with self.subTest(raw=rejected):
                with patch.dict(os.environ,{
                    "COGNITION_LOCAL_7B_GENERATE_TIMEOUT_SECONDS":rejected}):
                    with self.assertRaises(LocalModelUnavailable):
                        _local_generate_timeout("qwen2.5-coder:7b")

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
