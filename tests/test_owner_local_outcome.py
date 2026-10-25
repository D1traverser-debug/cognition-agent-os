"""Owner-outcome acceptance: actual environment result, not planner/test flags.

Exercise original CLI-style root -> real Host -> typed registered child ->
independent local effect/readback -> owner's original acceptance.  The fixture
bytes are intentionally still unchanged.  This does not assert external
business completion or general autonomous planning.
"""
from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize, create_task, alter_authority
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome


class RealOwnerLocalOutcome(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.db=self.root/"ledger.sqlite"
        self.ws=self.root/"ws"
        self.ws.mkdir()
        self.fx=self.root/"inputs"
        self.fx.mkdir()
        (self.fx/"settings.json").write_text('{"timeout":7}\n',encoding="utf-8")
        (self.fx/"baseline.csv").write_text("id,amount\nA,4\nB,5\n",encoding="utf-8")
        (self.fx/"actual.csv").write_text("id,amount\nA,6\nB,5\n",encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)

    def seed(self,goal):
        with closing(connect(self.db)) as db:
            return create_task(db,{"kind":"open_goal","goal":goal})

    def result(self,root):
        out=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        return next(x for x in out["goal_progress"]["goals"]
                    if x["root_task_id"]==root)["local_owner_result"]

    def test_original_sandbox_draft_goal_has_real_independent_local_result(self):
        goal=("Please ensure a sandbox draft of settings.json has owner equal to "
              "ops, preserving the existing timeout.")
        root=self.seed(goal)
        original=(self.fx/"settings.json").read_bytes()
        result=run_tick(self.db,self.ws,self.fx,max_jobs=2,
                        auto_stage_goals=True)
        self.assertEqual([x["status"] for x in result["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],result)
        owner=result["goal_progress"]["goals"][0]["local_owner_result"]
        self.assertEqual(owner["status"],"LOCAL_OWNER_RESULT_VERIFIED",result)
        self.assertTrue(owner["local_owner_outcome_verified"])
        self.assertFalse(owner["business_outcome_verified"])
        self.assertEqual((self.fx/"settings.json").read_bytes(),original)
        child=owner["evidence_task_id"]
        staged=self.ws/"sandbox"/(child+".candidate")
        self.assertEqual(json.loads(staged.read_text()),
                         {"timeout":7,"owner":"ops"})
        # Read back independently on restart without re-inference.
        self.assertTrue(inspect_owner_local_outcome(
            self.db,self.ws,self.fx,root)["local_owner_outcome_verified"])
        # A tampered effect must revoke local completion even though the
        # ledger has a historical SANDBOX_VERIFIED state.
        staged.write_text('{"timeout":7,"owner":"wrong"}\n')
        self.assertFalse(inspect_owner_local_outcome(
            self.db,self.ws,self.fx,root)["local_owner_outcome_verified"])


    def test_real_host_goal_status_and_drift_agree_after_real_effect(self):
        """A proven local result cannot coexist with a stale local drift alarm."""
        root=self.seed(
            "Please ensure a sandbox draft of settings.json has owner equal "
            "to ops, preserving the existing timeout.")
        first=run_tick(self.db,self.ws,self.fx,max_jobs=2,auto_stage_goals=True)
        result=next(x for x in first["goal_progress"]["goals"]
                    if x["root_task_id"]==root)["local_owner_result"]
        self.assertTrue(result["local_owner_outcome_verified"])
        self.assertFalse(any(
            x.get("status")=="DRIFT_SIGNAL_RECORDED"
            for x in first["owner_goal_drift"]),first)
        second=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(second["owner_goal_drift"], [],second)
        staged=self.ws/"sandbox"/(result["evidence_task_id"]+".candidate")
        staged.write_text('{"owner":"wrong","timeout":7}\\n')
        third=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        drift=[x for x in third["owner_goal_drift"]
               if x.get("status")=="DRIFT_SIGNAL_RECORDED"]
        self.assertEqual(len(drift),1,third)
        self.assertEqual(drift[0]["fidelity_state"],
                         "OWNER_POSTCONDITION_REGRESSED")
        # A replay of unchanged evidence cannot re-emit an alert. A separate
        # Host tick may legitimately produce new conformance evidence, so
        # isolate observation idempotency from independent Host mutations.
        from cognition_agent_os.goal_drift import observe_owner_goal_drift
        self.assertEqual(observe_owner_goal_drift(
            self.db,workspace=self.ws,fixtures=self.fx),[])
        with closing(connect(self.db)) as db:
            from cognition_agent_os.ledger import event
            event(db, root, "INDEPENDENT_RESULT_RECHECKED",
                  {"new_evidence": "separate conformance verdict"})
            db.commit()
        reopened=observe_owner_goal_drift(
            self.db,workspace=self.ws,fixtures=self.fx)
        self.assertEqual(len(reopened),1,reopened)
        self.assertEqual(reopened[0]["status"],"DRIFT_SIGNAL_RECORDED")
        self.assertEqual(observe_owner_goal_drift(
            self.db,workspace=self.ws,fixtures=self.fx),[])


    def test_installed_cli_host_entry_reports_original_local_result(self):
        """Exercise the shipped host-tick parser, not just its Python helper."""
        from contextlib import redirect_stdout
        from io import StringIO
        from cognition_agent_os.cli import main
        root=self.seed(
            "Please ensure a sandbox draft of settings.json has owner equal "
            "to ops, preserving the existing timeout.")
        output=StringIO()
        with redirect_stdout(output):
            code=main([
                "--db",str(self.db),"--workspace",str(self.ws),
                "--fixtures",str(self.fx),"host-tick",
                "--max-jobs","2","--auto-stage-goals"])
        self.assertEqual(code,0,output.getvalue())
        report=json.loads(output.getvalue())
        goal=next(x for x in report["goal_progress"]["goals"]
                  if x["root_task_id"]==root)
        self.assertEqual(goal["local_owner_result"]["status"],
                         "LOCAL_OWNER_RESULT_VERIFIED",report)
        self.assertFalse(goal["local_owner_result"]["business_outcome_verified"])
        self.assertFalse(any(
            x.get("status")=="DRIFT_SIGNAL_RECORDED"
            for x in report["owner_goal_drift"]),report)

    def test_original_comparison_is_readonly_report_not_business_truth(self):
        root=self.seed("Compare baseline.csv with actual.csv and report differences.")
        out=run_tick(self.db,self.ws,self.fx,max_jobs=2)
        self.assertEqual([x["status"] for x in out["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],out)
        found=next(x for x in out["goal_progress"]["goals"]
                   if x["root_task_id"]==root)["local_owner_result"]
        self.assertEqual(found["status"],"LOCAL_OWNER_RESULT_VERIFIED",out)
        self.assertEqual(found["outcome_scope"],
                         "ORIGINAL_NAMED_READONLY_COMPARISON_REPORT")
        self.assertFalse(found["business_outcome_verified"])
        self.assertFalse(found["real_external_outcome_verified"])
        # Source changes cannot leave a stale positive business claim.
        (self.fx/"actual.csv").write_text(
            "id,amount\nA,999\nB,5\n",encoding="utf-8")
        self.assertFalse(inspect_owner_local_outcome(
            self.db,self.ws,self.fx,root)["local_owner_outcome_verified"])


    def test_unsupported_extra_owner_clause_does_not_count_as_complete(self):
        """A correct subtask is not the whole conjunctive owner goal."""
        root=self.seed(
            "Compare baseline.csv with actual.csv and report differences "
            "and calculate a bar chart of mismatches.")
        out=run_tick(self.db,self.ws,self.fx,max_jobs=2)
        self.assertEqual([x["status"] for x in out["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],out)
        verdict=inspect_owner_local_outcome(self.db,self.ws,self.fx,root)
        self.assertFalse(verdict["local_owner_outcome_verified"],verdict)

    def test_second_sandbox_deliverable_cannot_be_ignored(self):
        root=self.seed(
            "Please ensure a sandbox draft of settings.json has owner equal to "
            "ops and create another backup document.")
        out=run_tick(self.db,self.ws,self.fx,max_jobs=2,auto_stage_goals=True)
        self.assertEqual([x["status"] for x in out["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],out)
        verdict=inspect_owner_local_outcome(self.db,self.ws,self.fx,root)
        self.assertFalse(verdict["local_owner_outcome_verified"],verdict)

    def test_unrequested_sandbox_and_revoked_grant_do_not_count(self):
        root=self.seed("Please ensure settings.json has owner equal to ops.")
        result=run_tick(self.db,self.ws,self.fx,max_jobs=2,
                        auto_stage_goals=True)
        found=next(x for x in result["goal_progress"]["goals"]
                   if x["root_task_id"]==root)["local_owner_result"]
        self.assertFalse(found["local_owner_outcome_verified"])
        self.assertEqual(found["reason"],"SANDBOX_DRAFT_NOT_ORIGINAL_OWNER_GOAL")
        draft=self.seed(
            "Ensure sandbox draft of settings.json has team equal to core.")
        out=run_tick(self.db,self.ws,self.fx,max_jobs=2,
                     auto_stage_goals=True)
        self.assertTrue(inspect_owner_local_outcome(
            self.db,self.ws,self.fx,draft)["local_owner_outcome_verified"])
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        self.assertFalse(inspect_owner_local_outcome(
            self.db,self.ws,self.fx,draft)["local_owner_outcome_verified"])
