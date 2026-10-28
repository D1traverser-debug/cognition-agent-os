"""P13 public feedback loop: no hidden labels to model, real ledger children.

The open-weight model is mocked in *unit tests only*. A separately run
native-Docker CI probe executes the proposed code in actual containers;
nothing here proves a local Ollama model was installed or succeeded.
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

from cognition_agent_os.ledger import connect,initialize,create_task,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.repo_refinement import refine_repo_public
from cognition_agent_os.repo_repair import audit_repo

ROOT=Path(__file__).resolve().parents[1]


class PublicRevisionTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.ws=self.root/"workspace";self.ws.mkdir()
        self.db=self.root/"ledger.sqlite"
        with closing(connect(self.db)) as c:initialize(c)
        self.fx.joinpath("main.py").write_bytes(
            b"import sys,json\nfrom rules import calc\n"
            b"print(json.dumps(calc(json.loads(sys.stdin.read()))))\n")
        self.fx.joinpath("rules.py").write_bytes(
            b"def calc(v):\n    return {'out':0}\n")
        self.bad="def calc(v):\n    return {'out': v['n'] - 1}\n"
        self.almost="def calc(v):\n    return {'out': v['n'] if v['n'] == 1 else v['n']-1}\n"
        self.good="def calc(v):\n    return {'out': v['n'] + 1}\n"
        self.fx.joinpath("candidate.json").write_bytes(json.dumps({
            "changes":[{"path":"rules.py","content":self.bad}]}).encode())
        self.public=[
            {"input":{"n":1},"expected":{"out":2}},
            {"input":{"n":4},"expected":{"out":5}}]
        self.fx.joinpath("visible.json").write_bytes(json.dumps(self.public).encode())
        self.holdout_bytes=b'[{"input":{"hidden_PRIVATE_SECRET_987":6},"expected":{"out":7}}]'
        self.fx.joinpath("hidden.json").write_bytes(self.holdout_bytes)
        self.spec={"kind":"repo_container_repair",
                   "files":["main.py","rules.py"],"entrypoint":"main.py",
                   "candidate":"candidate.json","visible":"visible.json",
                   "holdout":"hidden.json",
                   "holdout_sha256":hashlib.sha256(self.holdout_bytes).hexdigest()}
        with closing(connect(self.db)) as db:
            self.parent=create_task(db,self.spec)
        planned=run_once(self.db,self.ws,self.fx)
        self.assertEqual(planned["status"],"NEEDS_REVIEW")

    def task(self,tid):
        with closing(connect(self.db)) as db:
            return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())

    def suite(self,base,changes,entrypoint,cases,*,include_observed=False):
        self.assertEqual(entrypoint,"main.py")
        self.assertNotIn("hidden_PRIVATE_SECRET_987",repr(cases))
        if not changes or changes["rules.py"] in (
            self.fx.joinpath("rules.py").read_bytes(),self.bad.encode()):
            passes=0
        elif changes["rules.py"]==self.almost.encode():
            passes=1
        elif changes["rules.py"]==self.good.encode():
            passes=2
        else:
            passes=0
        return {"passes":passes,"total":len(cases),
                "observed":[{"pass":i<passes,"output_sha256":str(i)*64}
                            for i in range(len(cases))]}

    def model_output(self,content):
        return json.dumps({"changes":[{"path":"rules.py","content":content}]}).encode()

    def test_failed_public_patch_generates_revised_child_without_gold(self):
        calls=[]
        def model(*args,**kwargs):
            calls.append(kwargs["feedback"])
            return self.model_output(self.almost if len(calls)==1 else self.good)
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite) as docker,\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   side_effect=model) as model_call:
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=2)
        self.assertEqual(result["status"],"REVISED_PUBLIC_CANDIDATE_FROZEN",result)
        self.assertEqual(result["model_candidates_tested"],2)
        child=result["child_task_id"]
        self.assertEqual(self.task(self.parent)["state"],"UNKNOWN")
        self.assertEqual(self.task(child)["state"],"NEEDS_REVIEW")
        self.assertEqual(self.task(child)["parent_task"],self.parent)
        self.assertEqual(audit_repo(self.db,self.ws,self.fx,child)["status"],
                         "REPO_BYTES_MECHANICALLY_VALID")
        proposal=json.loads((self.ws/"artifacts"/(child+".json")).read_text())
        self.assertEqual(proposal["changes"]["rules.py"],self.good)
        self.assertEqual(proposal["public_revision_attempts"].__len__(),2)
        self.assertFalse((self.ws/"repo_lab").exists())
        self.assertFalse(result["production_write_authorized"])
        self.assertTrue(result["independent_holdout_pending"])
        self.assertTrue(all("hidden_PRIVATE_SECRET_987" not in json.dumps(c)
                            and "hidden.json" not in json.dumps(c) for c in calls))
        self.assertEqual(docker.call_count,4) # baseline, prior, two attempts
        self.assertEqual(model_call.call_count,2)
        with closing(connect(self.db)) as db:
            observations=db.execute("""SELECT details FROM events WHERE task_id=?
                AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL' ORDER BY event_id""",
                (self.parent,)).fetchall()
        self.assertEqual(len(observations),2)
        self.assertEqual([json.loads(x[0])["public_passes"] for x in observations],[1,2])

    def test_blocked_ancestor_during_model_cannot_freeze_revision(self):
        """A late ancestor stop invalidates the revision, not just the model."""
        with closing(connect(self.db)) as db:
            root=create_task(db,self.spec,due_at=9999999999)
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",(root,))
            db.execute("UPDATE tasks SET parent_task=? WHERE task_id=?",
                       (root,self.parent))
            db.commit()
        def model_then_stop(*args,**kwargs):
            with closing(connect(self.db)) as db:
                db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",
                           (root,))
                db.commit()
            return self.model_output(self.good)
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite), \
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   side_effect=model_then_stop):
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=1)
        self.assertNotEqual(result["status"],"REVISED_PUBLIC_CANDIDATE_FROZEN",result)
        with closing(connect(self.db)) as db:
            descendants=db.execute(
                "SELECT task_id FROM tasks WHERE parent_task=?",(self.parent,)).fetchall()
        self.assertFalse(descendants)

    def test_preexisting_blocked_ancestor_spends_no_model_budget(self):
        """A typed but invalid lineage is rejected before any model request."""
        with closing(connect(self.db)) as db:
            root=create_task(db,self.spec,due_at=9999999999)
            db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",(root,))
            db.execute("UPDATE tasks SET parent_task=? WHERE task_id=?",
                       (root,self.parent))
            db.commit()
        with patch("cognition_agent_os.repo_refinement.run_suite") as docker, \
             patch("cognition_agent_os.repo_refinement._candidate_from_model") as model:
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=1)
        self.assertNotEqual(result["status"],"REVISED_PUBLIC_CANDIDATE_FROZEN",result)
        docker.assert_not_called()
        model.assert_not_called()

    def test_no_local_model_or_pull_fails_before_revision_commit(self):
        from cognition_agent_os import local_model
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch.object(local_model,"_request",return_value={"models":[]}) as network:
            output=refine_repo_public(self.db,self.ws,self.fx,self.parent,model="not_installed:2b")
        self.assertEqual(output["status"],"INSTALLED_LOCAL_MODEL_UNAVAILABLE")
        self.assertEqual(self.task(self.parent)["state"],"NEEDS_REVIEW")
        self.assertEqual(network.call_count,1)
        self.assertFalse((self.ws/"repo_lab").exists())

    def test_rejects_duplicate_revisions_without_child(self):
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   return_value=self.model_output(self.bad)):
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,model="installed:7b")
        self.assertEqual(result["status"],"MODEL_REPEATED_PRIOR_HYPOTHESIS")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],1)

    def test_repeated_model_hypothesis_triggers_alternative_then_freezes_child(self):
        seen_feedback=[]
        def model(*args,**kw):
            seen_feedback.append(kw["feedback"])
            return self.model_output(self.bad if len(seen_feedback)==1 else self.good)
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite) as executed,\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   side_effect=model):
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=2)
        self.assertEqual(result["status"],"REVISED_PUBLIC_CANDIDATE_FROZEN",result)
        self.assertEqual(result["model_candidates_tested"],2)
        self.assertIn("latest_rejection",seen_feedback[1])
        self.assertEqual(seen_feedback[1]["latest_rejection"]["reason"],
                         "MODEL_REPEATED_PRIOR_HYPOTHESIS")
        self.assertEqual(self.task(result["child_task_id"])["state"],"NEEDS_REVIEW")
        # Bad repeated source must not be executed a second time in Docker.
        self.assertEqual(executed.call_count,3)

    def test_repeated_model_hypotheses_consume_parent_budget_across_calls(self):
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   return_value=self.model_output(self.bad)) as model:
            first=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                     model="installed:7b",max_attempts=2)
            second=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=2)
            third=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                     model="installed:7b",max_attempts=2)
        self.assertEqual(first["status"],"MODEL_REPEATED_PRIOR_HYPOTHESIS")
        self.assertEqual(first["attempts"],2)
        self.assertEqual(second["attempts"],1)
        self.assertEqual(third["status"],"REFINEMENT_BUDGET_EXHAUSTED")
        self.assertEqual(model.call_count,3)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                """SELECT COUNT(*) FROM events WHERE task_id=?
                AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",
                (self.parent,)).fetchone()[0],3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],1)

    def test_malformed_model_outputs_also_consume_attempt_budget(self):
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   return_value=b"malformed-not-json") as gen:
            first=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                     model="installed:7b",max_attempts=2)
            second=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=2)
            third=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                     model="installed:7b",max_attempts=2)
        self.assertEqual(first["status"],"MODEL_CANDIDATE_INVALID")
        self.assertEqual(first["attempts"],2)
        self.assertEqual(second["attempts"],1)
        self.assertEqual(third["status"],"REFINEMENT_BUDGET_EXHAUSTED")
        self.assertEqual(gen.call_count,3)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],1)
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM events
                WHERE task_id=? AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",
                (self.parent,)).fetchone()[0],3)

    def test_bounded_failed_attempts_recorded_then_refused(self):
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   side_effect=[self.model_output(self.almost),
                                self.model_output("def calc(v):\n    return {'out':v['n']*2}\n")]):
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b",max_attempts=2)
        self.assertEqual(result["status"],"PUBLIC_REFINEMENT_BUDGET_EXHAUSTED")
        self.assertEqual(result["attempts"],2)
        # Third, final retry available once; fourth cannot be created.
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   return_value=self.model_output("def calc(v):\n    return {'out': v['n']+5}\n")):
            last=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                    model="installed:7b",max_attempts=2)
            no_more=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                       model="installed:7b",max_attempts=2)
        self.assertEqual(last["attempts"],1)
        self.assertEqual(no_more["status"],"REFINEMENT_BUDGET_EXHAUSTED")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM events WHERE task_id=?
                 AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",
                 (self.parent,)).fetchone()[0],3)

    def test_revocation_during_generation_blocks_child_commit(self):
        def revoke_then_propose(*args,**kwargs):
            with closing(connect(self.db)) as db:alter_authority(db,revoke=True)
            return self.model_output(self.good)
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=self.suite),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model",
                   side_effect=revoke_then_propose):
            result=refine_repo_public(self.db,self.ws,self.fx,self.parent,
                                      model="installed:7b")
        self.assertEqual(result["status"],"REVIEW_AUTHORITY_OR_BUDGET_CHANGED")
        self.assertEqual(self.task(self.parent)["state"],"NEEDS_REVIEW")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],1)

    def test_original_public_working_refuses_to_refine(self):
        def passed(base,changes,entrypoint,cases,*,include_observed=False):
            return {"passes":len(cases),"total":len(cases),
                    "observed":[{"pass":True,"output_sha256":"0"*64} for _ in cases]}
        with patch("cognition_agent_os.repo_refinement.run_suite",side_effect=passed),\
             patch("cognition_agent_os.repo_refinement._candidate_from_model") as proposer:
            out=refine_repo_public(self.db,self.ws,self.fx,self.parent,model="installed:7b")
        self.assertEqual(out["status"],"ORIGINAL_FAILURE_NOT_REPRODUCED")
        proposer.assert_not_called()

    def test_missing_docker_refuses_without_host_code_execution(self):
        from cognition_agent_os.container_lab import ContainerUnavailable
        with patch("cognition_agent_os.repo_refinement.run_suite",
                   side_effect=ContainerUnavailable("DOCKER_CLI_NOT_INSTALLED")):
            out=refine_repo_public(self.db,self.ws,self.fx,self.parent,model="installed:7b")
        self.assertEqual(out["status"],"ISOLATION_UNAVAILABLE")
        self.assertTrue(out["no_host_execution"])

    def test_cli_invalid_parameters_return_nonzero_without_execution(self):
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        argv=[sys.executable,"-m","cognition_agent_os.cli",
              "--db",str(self.db),"--workspace",str(self.ws),
              "--fixtures",str(self.fx),"repo-refine-local",
              "--task-id",self.parent,"--model","installed:7b",
              "--max-attempts","50"]
        result=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=12)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.task(self.parent)["state"],"NEEDS_REVIEW")


if __name__=="__main__":
    unittest.main()
