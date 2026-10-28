"""P12 trust boundary regressions without installing or invoking Docker.

Arbitrary whole-file code is not implicitly authorized by the legacy
--auto-stage-goals flag. No cloud model, hidden gold or host Python exec.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.container_lab import (
    validate_task_spec,candidate_changes,cases_from_bytes,
    _docker_run,ContainerUnavailable
)
from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.host import run_tick
from cognition_agent_os.repo_repair import audit_repo
from cognition_agent_os.runner import run_once


class RepositoryPermissionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.ws=self.root/"work";self.ws.mkdir()
        self.db=self.root/"tasks.sqlite"
        db=connect(self.db);initialize(db);db.close()
        self.fx.joinpath("main.py").write_bytes(
            b"import json,sys\nfrom rules import calculate\n"
            b"print(json.dumps(calculate(json.loads(sys.stdin.read()))))\n")
        self.fx.joinpath("rules.py").write_bytes(
            b"def calculate(data):\n    return {'answer':0}\n")
        change="def calculate(data):\n    return {'answer':data['value']+1}\n"
        self.fx.joinpath("candidate.json").write_bytes(
            json.dumps({"changes":[{"path":"rules.py","content":change}]}).encode())
        self.fx.joinpath("public.json").write_bytes(json.dumps([
            {"input":{"value":2},"expected":{"answer":3}}
        ]).encode())
        hidden=json.dumps([{"input":{"value":5},"expected":{"answer":6}}]).encode()
        self.fx.joinpath("holdout.json").write_bytes(hidden)
        self.spec={"kind":"repo_container_repair","files":["main.py","rules.py"],
                   "entrypoint":"main.py","candidate":"candidate.json",
                   "visible":"public.json","holdout":"holdout.json",
                   "holdout_sha256":hashlib.sha256(hidden).hexdigest()}

    def enqueue(self):
        db=connect(self.db)
        tid=create_task(db,self.spec)
        db.close()
        return tid

    def test_existing_auto_stage_never_runs_untrusted_repo(self):
        tid=self.enqueue()
        with patch("cognition_agent_os.repo_repair.review_repo") as executor:
            response=run_tick(self.db,self.ws,self.fx,auto_stage_goals=True)
        self.assertEqual(response["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(response["repair_lab_reviews"],[])
        executor.assert_not_called()
        self.assertEqual(audit_repo(self.db,self.ws,self.fx,tid)["status"],
                         "REPO_BYTES_MECHANICALLY_VALID")
        self.assertFalse((self.ws/"repo_lab").exists())

    def test_new_repo_autoreview_requires_both_explicit_permissions(self):
        tid=self.enqueue()
        with self.assertRaisesRegex(ValueError,"both explicit"):
            run_tick(self.db,self.ws,self.fx,auto_review_repos=True)
        out=run_tick(self.db,self.ws,self.fx)
        self.assertEqual(out["tasks"][0]["status"],"NEEDS_REVIEW")
        with patch("cognition_agent_os.repo_repair.review_repo",
                   return_value={"task_id":tid,"status":"ISOLATION_UNAVAILABLE",
                                 "no_host_execution":True}) as executor:
            result=run_tick(self.db,self.ws,self.fx,
                            auto_stage_goals=True,auto_review_repos=True)
        self.assertEqual(result["repair_lab_reviews"][0]["status"],
                         "ISOLATION_UNAVAILABLE")
        executor.assert_called_once()
        self.assertFalse((self.ws/"repo_lab").exists())

    def test_no_docker_never_falls_back_to_running_host_python(self):
        with patch("cognition_agent_os.container_lab.shutil.which",return_value=None):
            with self.assertRaisesRegex(ContainerUnavailable,"DOCKER_CLI_NOT_INSTALLED"):
                _docker_run(self.fx,"main.py",{"value":3})

    def test_untrusted_candidate_path_and_cases_contract_are_bounded(self):
        for name in ("../outside.py","a/b.py","C:\\bad.py","unexpected.txt","a.py;ls"):
            with self.subTest(path=name):
                proposal={"changes":[{"path":name,"content":"pass"}]}
                with self.assertRaises(ValueError):
                    candidate_changes(json.dumps(proposal).encode(),self.spec["files"])
        for name in ("../escape.py","C:\\bad.py","not-python.txt"):
            altered=dict(self.spec,files=["main.py",name])
            with self.subTest(source=name),self.assertRaises(ValueError):
                validate_task_spec(altered)
        with self.assertRaises(ValueError):
            cases_from_bytes(b'[{"input": {}, "expected": 0}, {"input":{}, "expected":0}]'
                             * 10000)

    def test_untrusted_loopback_model_never_gets_sealed_reference(self):
        from cognition_agent_os import local_model
        calls=[]
        def fake_request(method,path,payload,timeout):
            calls.append((method,path,payload))
            if path=="/api/tags":
                return {"models":[{"name":"local_test:latest"}]}
            assert path=="/api/generate"
            prompt=payload["prompt"]
            self.assertNotIn("holdout.json",prompt)
            self.assertNotIn("secret_expected_99999",prompt)
            return {"done":True,"response":
                    self.fx.joinpath("candidate.json").read_text()}
        self.fx.joinpath("holdout.json").write_bytes(
            b'{"not_sealed_gold_for_model":"secret_expected_99999"}')
        self.spec["holdout_sha256"]=hashlib.sha256(
            self.fx.joinpath("holdout.json").read_bytes()).hexdigest()
        tid=self.enqueue()
        with patch.object(local_model,"_request",side_effect=fake_request):
            result=run_once(self.db,self.ws,self.fx,planner_mode="ollama-local",
                            local_model="local_test:latest")
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        self.assertTrue(result["model_called"])
        self.assertEqual([c[1] for c in calls],
                         ["/api/tags","/api/generate"])
        self.assertEqual(audit_repo(self.db,self.ws,self.fx,tid)["status"],
                         "REPO_BYTES_MECHANICALLY_VALID")
        self.assertFalse((self.ws/"repo_lab").exists())


if __name__=="__main__":
    unittest.main()
