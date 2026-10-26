"""Natural-language owner goal -> pre-existing investigation Worker and oracle."""
import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from cognition_agent_os.host import run_tick, _goal_progress
from cognition_agent_os.ledger import connect,create_task,initialize
from cognition_agent_os.investigation import audit_investigation
from cognition_agent_os.goal_audit import audit_goal
from cognition_agent_os.open_goal import audit_open_goal

class OpenGoalResearchVertical(unittest.TestCase):
    def setUp(self):
        d=TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.r=Path(d.name)
        self.fx=self.r/"evidence";self.fx.mkdir()
        self.ws=self.r/"workspace";self.ws.mkdir()
        self.db=self.r/"authority.sqlite"
        with closing(connect(self.db)) as db:initialize(db)
        (self.fx/"cause.md").write_text(
            "The UART timeout counter pauses during reset assertion.\n")
        (self.fx/"trace.md").write_text(
            "The recorded reset bit remained set for 35 simulation cycles.\n")
        self.goal="Investigate the UART timeout causes using local engineering evidence."

    def seed(self,goal=None):
        with closing(connect(self.db)) as db:
            return create_task(db,{"kind":"open_goal","goal":goal or self.goal})

    def children(self,parent):
        with closing(connect(self.db)) as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM tasks WHERE parent_task=?",(parent,))]

    def root_error_code(self,parent):
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT error_code FROM tasks WHERE task_id=?",(parent,)).fetchone()
            return row["error_code"]

    def respond(self,method,path,payload,timeout):
        if method=="GET":
            return {"models":[{"name":"installed:test"}]}
        props=payload["format"]["properties"]
        if "sources" in props:
            answer={"sources":["cause.md","trace.md"]}
        elif "findings" in props:
            answer={"findings":[
                {"source":"cause.md",
                 "quote":"The UART timeout counter pauses during reset assertion.",
                 "interpretation":"Reset may cause a paused timeout counter."},
                {"source":"trace.md",
                 "quote":"The recorded reset bit remained set for 35 simulation cycles.",
                 "interpretation":"The trace records a prolonged reset."}],
                "uncertainty":"This is a local engineering hypothesis, not silicon evidence."}
        else:raise AssertionError("unexpected model schema")
        return {"done":True,"response":json.dumps(answer)}

    def test_natural_goal_to_research_artifact_and_independent_readback(self):
        parent=self.seed()
        prior={p.name:p.read_bytes() for p in self.fx.iterdir()}
        with patch("cognition_agent_os.local_model._request",side_effect=self.respond):
            out=run_tick(self.db,self.ws,self.fx,max_jobs=2,
                         planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual([v["status"] for v in out["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],out)
        child=self.children(parent)[0]
        self.assertEqual(json.loads(child["source_spec"]),{
            "kind":"investigate_goal","question":self.goal,
            "scope":"LOCAL_EVIDENCE_ONLY"})
        self.assertEqual(audit_open_goal(self.db,self.fx,parent)["status"],
                         "METHOD_CANDIDATE_MECHANICALLY_GROUNDED")
        self.assertEqual(audit_investigation(
            self.db,self.ws,self.fx,child["task_id"])["status"],
            "SOURCE_GROUNDED_UNREVIEWED")
        research=json.loads((self.ws/"artifacts"/(child["task_id"]+".json")).read_text())
        self.assertEqual(set(research["selected_sources"]),{"cause.md","trace.md"})
        self.assertIs(research["business_outcome_verified"],False)
        self.assertIs(research["authorizes_mutation"],False)
        self.assertEqual({p.name:p.read_bytes() for p in self.fx.iterdir()},prior)

    def test_independent_research_and_sandbox_draft_conjunction(self):
        """Both explicit owner obligations must run via the SAME Host and ledger."""
        (self.fx/"settings.json").write_text('{"timeout":7}\n')
        original={p.name:p.read_bytes() for p in self.fx.iterdir()}
        parent=self.seed(
            "Investigate the UART timeout using local engineering evidence and "
            "ensure a sandbox draft of settings.json has owner equal to ops.")
        with patch("cognition_agent_os.local_model._request",side_effect=self.respond):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=3,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual([x["status"] for x in result["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW","NEEDS_REVIEW"],result)
        children=self.children(parent)
        self.assertEqual(len(children),2)
        by_kind={json.loads(x["source_spec"])["kind"]:x for x in children}
        self.assertEqual(set(by_kind),{"investigate_goal","goal_case"})
        self.assertEqual(audit_open_goal(self.db,self.fx,parent)["status"],
                         "COMPOUND_METHODS_MECHANICALLY_GROUNDED")
        self.assertEqual(audit_investigation(
            self.db,self.ws,self.fx,by_kind["investigate_goal"]["task_id"])["status"],
                         "SOURCE_GROUNDED_UNREVIEWED")
        self.assertEqual(audit_goal(
            self.db,self.ws,self.fx,by_kind["goal_case"]["task_id"])["status"],
                         "CANDIDATE_MECHANICALLY_VALID")
        self.assertEqual({p.name:p.read_bytes() for p in self.fx.iterdir()},original)
        root=result["goal_progress"]["goals"][0]
        self.assertFalse(root["owner_outcome_verified"])
        self.assertFalse(root["semantic_outcome_verified"])
        self.assertFalse(root["research_only"])
        self.assertEqual(len(root["independent_checks"]),2)
        self.assertTrue(all(x["mechanically_verified"]
                            and x["business_outcome_verified"] is False
                            for x in root["independent_checks"]))
        self.assertFalse(root["local_owner_result"]["local_owner_outcome_verified"])
        obligations=root["original_obligation_progress"]
        self.assertEqual(len(obligations),2)
        self.assertEqual({x["child_task_id"] for x in obligations},
                         {x["task_id"] for x in children})
        self.assertTrue(all(x["task_state"]=="NEEDS_REVIEW"
                            and x["mechanically_verified"]
                            and x["owner_outcome_verified"] is False
                            for x in obligations))

    def test_sequential_research_then_draft_is_not_parallelized(self):
        """The original owner 'then' must wait for independently checked evidence."""
        (self.fx/"settings.json").write_text('{"timeout":7}\n')
        parent=self.seed(
            "Investigate the UART timeout using local evidence and then "
            "ensure a sandbox draft of settings.json has owner equal to ops.")
        initial=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                         planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual([x["status"] for x in initial["tasks"]],["DECOMPOSED"],initial)
        kids=self.children(parent)
        self.assertEqual(len(kids),2)
        by_kind={json.loads(x["source_spec"])["kind"]:x for x in kids}
        research=by_kind["investigate_goal"]["task_id"]
        draft=by_kind["goal_case"]["task_id"]
        self.assertEqual(self.root_error_code(parent),None)
        with patch("cognition_agent_os.local_model._request",side_effect=self.respond):
            middle=run_tick(self.db,self.ws,self.fx,max_jobs=2,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual([x["status"] for x in middle["tasks"]],["NEEDS_REVIEW"],middle)
        self.assertEqual(middle["tasks"][0]["task_id"],research)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT state FROM tasks WHERE task_id=?",
                                        (draft,)).fetchone()["state"],"PENDING")
        self.assertEqual(audit_investigation(
            self.db,self.ws,self.fx,research)["status"],"SOURCE_GROUNDED_UNREVIEWED")
        final=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                       planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(final["tasks"][0]["task_id"],draft)
        self.assertEqual(final["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(audit_open_goal(self.db,self.fx,parent)["status"],
                         "COMPOUND_METHODS_MECHANICALLY_GROUNDED")
        self.assertFalse(final["goal_progress"]["goals"][0]["owner_outcome_verified"])

    def test_compound_research_and_write_must_not_downgrade_owner_goal(self):
        (self.fx/"settings.json").write_text('{"timeout":7}\n')
        parent=self.seed(
            "Investigate the UART timeout and set settings.json owner equal to ops; both required.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("unsupported compound owner goal")):
            out=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"],"UNKNOWN",out)
        self.assertFalse(self.children(parent))

    def test_composite_english_research_then_implement_preserves_all_obligations(self):
        parent=self.seed(
            "Investigate the UART timeout using local evidence and then implement a code fix.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("composite goal must not be downgraded")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"UNKNOWN",result)
        self.assertEqual(self.root_error_code(parent),"OPEN_GOAL_METHOD_UNSUPPORTED")
        self.assertFalse(self.children(parent))

    def test_composite_chinese_research_and_fix_preserves_all_obligations(self):
        parent=self.seed("排查 UART 超时，并修复对应代码，不能只输出分析报告。")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("unsupported full owner goal")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"UNKNOWN",result)
        self.assertEqual(self.root_error_code(parent),"OPEN_GOAL_METHOD_UNSUPPORTED")
        self.assertFalse(self.children(parent))

    def test_informational_deployment_research_is_not_execution_intent(self):
        parent=self.seed(
            "Research how to deploy the UART fix safely using local engineering evidence.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("explicit research should not need method inference")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"DECOMPOSED",result)
        self.assertEqual(len(self.children(parent)),1)
        self.assertEqual(json.loads(self.children(parent)[0]["source_spec"])["scope"],
                         "LOCAL_EVIDENCE_ONLY")

    def test_readonly_research_with_explicit_no_write_is_allowed(self):
        parent=self.seed(
            "Investigate the UART timeout using local evidence; do not modify any files.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("read-only research must remain admitted")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"DECOMPOSED",result)
        self.assertEqual(json.loads(self.children(parent)[0]["source_spec"])["scope"],
                         "LOCAL_EVIDENCE_ONLY")

    def test_research_then_deploy_is_not_misread_as_informational(self):
        parent=self.seed("Research how to deploy the UART fix, then deploy it to production.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("no model can authorize external deployment")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"UNKNOWN",result)
        self.assertEqual(self.root_error_code(parent),"OPEN_GOAL_METHOD_UNSUPPORTED")
        self.assertFalse(self.children(parent))

    def test_readonly_inquiry_about_fix_is_not_implementation(self):
        parent=self.seed("Investigate how to fix the UART timeout using local evidence.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("research does not execute a fix")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                            planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"DECOMPOSED",result)
        self.assertEqual(json.loads(self.children(parent)[0]["source_spec"])["scope"],
                         "LOCAL_EVIDENCE_ONLY")

    def test_no_model_means_no_fake_investigation(self):
        parent=self.seed()
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("no local model installed")):
            out=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"],"UNKNOWN",out)
        self.assertFalse(self.children(parent))

    def test_source_changed_between_parent_and_child_prevents_research(self):
        parent=self.seed()
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("no model for exact routing")):
            one=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                         planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(one["tasks"][0]["status"],"DECOMPOSED",one)
        child=self.children(parent)[0]
        (self.fx/"cause.md").write_text("Unversioned source replacement.\n")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("invalidated source must be blocked")):
            two=run_tick(self.db,self.ws,self.fx,max_jobs=1,
                         planner_mode="ollama-local",local_model="installed:test")
        self.assertIn(two["tasks"][0]["status"],("UNKNOWN","BLOCKED"),two)
        self.assertFalse((self.ws/"artifacts"/(child["task_id"]+".json")).exists())
        self.assertEqual(audit_open_goal(self.db,self.fx,parent)["status"],
                         "SOURCE_CHANGED_SINCE_PROPOSAL")

    def test_hostile_model_cannot_mint_research_artifact_or_authority(self):
        parent=self.seed()
        def hostile(method,path,payload,timeout):
            if method=="GET":return {"models":[{"name":"installed:test"}]}
            if "sources" in payload.get("format",{}).get("properties",{}):
                return {"done":True,"response":json.dumps({"sources":["cause.md"]})}
            return {"done":True,"response":json.dumps({
                "findings":[{"source":"cause.md",
                    "quote":"The UART timeout counter pauses during reset assertion.",
                    "interpretation":"Reset may stop timeout counter."}],
                "uncertainty":"unverified","grant":"admin"})}
        with patch("cognition_agent_os.local_model._request",side_effect=hostile):
            out=run_tick(self.db,self.ws,self.fx,max_jobs=2,
                         planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(out["tasks"][0]["status"],"DECOMPOSED",out)
        child=self.children(parent)[0]
        self.assertEqual(child["state"],"UNKNOWN",out)
        self.assertFalse((self.ws/"artifacts"/(child["task_id"]+".json")).exists())

if __name__=="__main__":unittest.main()
