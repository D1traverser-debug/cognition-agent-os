"""P12 code-base experiments: no host untrusted code execution in tests.

Actual Docker subprocess behavior is separately exercised in the CI
repo_container_integration job; these tests check agent admission,
conformance, task evidence and failure paths via a mocked container
boundary, not fake claims of real container execution.
"""
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

from cognition_agent_os.container_lab import (
    candidate_changes,validate_task_spec,run_suite,ContainerUnavailable)
from cognition_agent_os.ledger import connect,initialize,create_task,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.repo_repair import audit_repo,review_repo
from cognition_agent_os.conformance import inspect_conformance,capability_disabled,REPAIR_LAB_CAPABILITY
from cognition_agent_os.host import run_tick

ROOT=Path(__file__).resolve().parents[1]


class RepoLabTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.fx=self.base/"fx";self.fx.mkdir()
        self.ws=self.base/"work";self.ws.mkdir()
        self.dbpath=self.base/"state.sqlite"
        db=connect(self.dbpath);initialize(db);db.close()
        self.original_main=(
            b"import json,sys\nfrom calculations import calculate\n"
            b"print(json.dumps(calculate(json.loads(sys.stdin.read()))))\n")
        self.original_rules=b"def calculate(data):\n    return {'net': 0}\n"
        self.fixed_rules=(
            "def calculate(data):\n"
            "    by_group = {}\n"
            "    for row in data['rows']:\n"
            "        value = row['amount']\n"
            "        if row['kind'] == 'debit':\n"
            "            value = -value\n"
            "        name = row['group']\n"
            "        by_group[name] = by_group.get(name, 0) + value\n"
            "    return {'by_group': by_group, 'net': sum(by_group.values())}\n")
        self.fx.joinpath("main.py").write_bytes(self.original_main)
        self.fx.joinpath("calculations.py").write_bytes(self.original_rules)
        self.fx.joinpath("candidate.json").write_bytes(json.dumps({
            "changes":[{"path":"calculations.py","content":self.fixed_rules}]
        }).encode())
        self.public=[
            {"input":{"rows":[{"kind":"credit","amount":15,"group":"tools"},
                              {"kind":"debit","amount":4,"group":"tools"}]},
             "expected":{"by_group":{"tools":11},"net":11}},
            {"input":{"rows":[]},"expected":{"by_group":{},"net":0}}
        ]
        self.hidden=[
            {"input":{"rows":[{"kind":"debit","amount":2,"group":"food"},
                              {"kind":"credit","amount":20,"group":"travel"}]},
             "expected":{"by_group":{"food":-2,"travel":20},"net":18}},
            {"input":{"rows":[{"kind":"credit","amount":1,"group":"a"},
                              {"kind":"credit","amount":7,"group":"a"}]},
             "expected":{"by_group":{"a":8},"net":8}}
        ]
        self.fx.joinpath("public.json").write_bytes(json.dumps(self.public).encode())
        sealed=json.dumps(self.hidden).encode()
        self.fx.joinpath("hidden.json").write_bytes(sealed)
        self.spec={"kind":"repo_container_repair",
             "files":["main.py","calculations.py"],"entrypoint":"main.py",
             "candidate":"candidate.json","visible":"public.json",
             "holdout":"hidden.json",
             "holdout_sha256":hashlib.sha256(sealed).hexdigest()}

    def seed(self):
        db=connect(self.dbpath)
        tid=create_task(db,self.spec)
        db.close()
        return tid

    def state(self,tid):
        with closing(connect(self.dbpath)) as db:
            return dict(db.execute(
                "SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())

    def plan(self):
        tid=self.seed()
        result=run_once(self.dbpath,self.ws,self.fx)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        self.assertFalse(result["holdout_seen_by_planner"])
        return tid

    def _fake_suite(self,base,changes,entrypoint,cases):
        self.assertEqual(entrypoint,"main.py")
        self.assertIn("for row in",changes["calculations.py"].decode())
        self.assertNotIn("hidden.json",json.dumps(base,default=str))
        return {"passes":len(cases),"total":len(cases),
                "observed":[{"pass":True} for _ in cases]}

    def test_whole_file_loop_dict_logic_frozen_and_separate_evaluated(self):
        tid=self.plan()
        proposal=json.loads((self.ws/"artifacts"/(tid+".json")).read_text())
        self.assertIn("for row",proposal["changes"]["calculations.py"])
        self.assertEqual(audit_repo(self.dbpath,self.ws,self.fx,tid)["status"],
                         "REPO_BYTES_MECHANICALLY_VALID")
        with patch("cognition_agent_os.repo_repair.run_suite",
                   side_effect=self._fake_suite):
            result=review_repo(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"REPAIR_LAB_VERIFIED",result)
        self.assertEqual(self.state(tid)["state"],"REPAIR_LAB_VERIFIED")
        self.assertEqual((self.ws/"repo_lab"/tid/"calculations.py").read_text(),
                         self.fixed_rules)
        self.assertEqual(self.fx.joinpath("calculations.py").read_bytes(),
                         self.original_rules)
        self.assertEqual(audit_repo(self.dbpath,self.ws,self.fx,tid,
                                   require_staged=True)["status"],
                         "REPO_BYTES_MECHANICALLY_VALID")
        self.assertEqual(inspect_conformance(
            self.dbpath,self.ws,self.fx)["mechanically_valid"],1)

    def test_hidden_counterexample_refutes_without_creating_lab(self):
        tid=self.plan()
        def mismatch(base,changes,entrypoint,cases):
            if cases==self.hidden:
                return {"passes":len(cases)-1,"total":len(cases)}
            return self._fake_suite(base,changes,entrypoint,cases)
        with patch("cognition_agent_os.repo_repair.run_suite",
                   side_effect=mismatch):
            result=review_repo(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"HOLDOUT_REFUTED")
        self.assertEqual(self.state(tid)["state"],"UNKNOWN")
        self.assertFalse((self.ws/"repo_lab").exists())

    def test_no_docker_is_strictly_no_host_fallback(self):
        tid=self.plan()
        with patch("cognition_agent_os.repo_repair.run_suite",
                   side_effect=ContainerUnavailable("DOCKER_CLI_NOT_INSTALLED")):
            result=review_repo(self.dbpath,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"ISOLATION_UNAVAILABLE")
        self.assertTrue(result["no_host_execution"])
        self.assertEqual(self.state(tid)["state"],"NEEDS_REVIEW")
        self.assertFalse((self.ws/"repo_lab").exists())

    def test_planner_never_reads_hidden_gold_even_model_candidate(self):
        from cognition_agent_os import repo_repair
        original=repo_repair.safe_fixture
        seen=[]
        def public_only(root,filename):
            seen.append(filename)
            if filename=="hidden.json":
                raise AssertionError("Hidden expected leaked into planner")
            return original(root,filename)
        with patch.object(repo_repair,"safe_fixture",side_effect=public_only):
            self.plan()
        self.assertEqual(set(seen),
                         {"main.py","calculations.py","candidate.json","public.json"})

    def test_model_generation_uses_installed_loopback_without_gold(self):
        from cognition_agent_os import local_model
        calls=[]
        def fake_request(method,path,payload,timeout):
            calls.append((method,path,payload))
            if path=="/api/tags":
                return {"models":[{"name":"local-model:7b"}]}
            self.assertNotIn("hidden.json",payload["prompt"])
            self.assertNotIn("by_group\\\":{\\\"food",payload["prompt"])
            return {"done":True,"response":json.dumps({
                "changes":[{"path":"calculations.py","content":self.fixed_rules}]})}
        tid=self.seed()
        with patch.object(local_model,"_request",side_effect=fake_request):
            result=run_once(self.dbpath,self.ws,self.fx,
                            planner_mode="ollama-local",
                            local_model="local-model:7b")
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        self.assertTrue(result["model_called"])
        self.assertEqual(len(calls),2)

    def test_missing_local_model_never_autopulls_or_cloud_fallback(self):
        from cognition_agent_os import local_model
        tid=self.seed()
        with patch.object(local_model,"_request",
             return_value={"models":[]}) as call:
            result=run_once(self.dbpath,self.ws,self.fx,
                            planner_mode="ollama-local",local_model="missing:7b")
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(self.state(tid)["state"],"UNKNOWN")
        self.assertEqual(call.call_count,1)

    def test_unapproved_files_and_code_inputs_rejected(self):
        invalid={
            "changes":[{"path":"../injected.py","content":"print('bad')"}]}
        with self.assertRaises(ValueError):
            candidate_changes(json.dumps(invalid).encode(),self.spec["files"])
        for name in ("../entry.py","a/b.py","..\\evil.py","x.py;id"):
            spec=dict(self.spec,files=[name,"main.py"],entrypoint="main.py")
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_task_spec(spec)
        self.fx.joinpath("candidate.json").write_bytes(
            json.dumps(invalid).encode())
        tid=self.seed()
        result=run_once(self.dbpath,self.ws,self.fx)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertFalse((self.ws/"artifacts").exists())

    def test_grant_revoke_and_staged_tamper_are_denied(self):
        tid=self.plan()
        db=connect(self.dbpath);alter_authority(db,revoke=True);db.close()
        with patch("cognition_agent_os.repo_repair.run_suite",
                   side_effect=self._fake_suite):
            result=review_repo(self.dbpath,self.ws,self.fx,tid)
        self.assertNotEqual(result["status"],"REPAIR_LAB_VERIFIED")
        self.assertFalse((self.ws/"repo_lab").exists())

    def test_successful_lab_tamper_trips_original_repair_breaker(self):
        tid=self.plan()
        with patch("cognition_agent_os.repo_repair.run_suite",
                   side_effect=self._fake_suite):
            self.assertEqual(review_repo(self.dbpath,self.ws,self.fx,tid)["status"],
                             "REPAIR_LAB_VERIFIED")
        (self.ws/"repo_lab"/tid/"calculations.py").write_text("forged")
        found=inspect_conformance(self.dbpath,self.ws,self.fx,enforce=True)
        self.assertEqual(found["status"],"CONFORMANCE_VIOLATIONS")
        self.assertTrue(capability_disabled(self.dbpath,REPAIR_LAB_CAPABILITY))

    def test_default_host_no_hidden_evaluation_and_explicit_optin(self):
        tid=self.seed()
        ordinary=run_tick(self.dbpath,self.ws,self.fx)
        self.assertEqual(ordinary["repair_lab_reviews"],[])
        self.assertEqual(self.state(tid)["state"],"NEEDS_REVIEW")
        with patch("cognition_agent_os.repo_repair.run_suite",
                   side_effect=self._fake_suite):
            enabled=run_tick(self.dbpath,self.ws,self.fx,auto_stage_goals=True)
        self.assertEqual(enabled["repair_lab_reviews"][0]["status"],
                         "REPAIR_LAB_VERIFIED")

    def test_cli_queue_and_audit_are_real_subprocesses(self):
        doc=self.base/"spec.json";doc.write_bytes(json.dumps(self.spec).encode())
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        base=[sys.executable,"-m","cognition_agent_os.cli",
              "--db",str(self.dbpath),"--workspace",str(self.ws),
              "--fixtures",str(self.fx)]
        def command(args):
            return subprocess.run(base+args,capture_output=True,
                                  text=True,env=env,timeout=15)
        seeded=command(["seed-repo-repair","--spec",str(doc)])
        self.assertEqual(seeded.returncode,0,seeded.stderr)
        tid=json.loads(seeded.stdout)["task_id"]
        worker=command(["worker-once"])
        self.assertEqual(worker.returncode,0,worker.stderr)
        self.assertEqual(json.loads(worker.stdout)["status"],"NEEDS_REVIEW")
        audit=command(["repo-audit","--task-id",tid])
        self.assertEqual(audit.returncode,0,audit.stderr)
        self.assertEqual(json.loads(audit.stdout)["status"],
                         "REPO_BYTES_MECHANICALLY_VALID")

    def test_docker_invocation_hardening_and_no_network(self):
        from cognition_agent_os import container_lab as lab
        commands=[]
        class Process:
            returncode=0
            stdout=b'{"ok":true}\\n'
        with patch.object(lab.shutil,"which",return_value="/usr/bin/docker"),\
             patch.object(lab.subprocess,"run",
               side_effect=lambda args,**kw: (commands.append((args,kw)) or Process())):
            res=lab._docker_run(self.base,"main.py",{"x":1})
        self.assertEqual(res,{"ok":True})
        command,options=commands[0]
        self.assertIn("--network=none",command)
        self.assertIn("--pull=never",command)
        self.assertIn("--read-only",command)
        self.assertIn("--cap-drop=ALL",command)
        self.assertIn("--security-opt=no-new-privileges",command)
        self.assertIn("--user=65534:65534",command)
        self.assertIn("readonly",command[command.index("--mount")+1])
        self.assertEqual(options["timeout"],8)
        self.assertNotIn("shell",options)


if __name__=="__main__":
    unittest.main()
