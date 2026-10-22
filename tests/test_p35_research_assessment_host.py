"""P35 checks an actual P34 research lineage through the actual original host."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect,create_task,initialize

class ResearchAssessmentHostTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.fx=self.root/"fixtures"; self.fx.mkdir()
        self.work=self.root/"workspace"; self.work.mkdir()
        self.db=self.root/"task.sqlite"
        with closing(connect(self.db)) as db:initialize(db)
        (self.fx/"structure.json").write_bytes(b'{"keep":42}')
        (self.fx/"before.csv").write_bytes(b"id,amount\nA,1\n")
        (self.fx/"after.csv").write_bytes(b"id,amount\nA,2\n")

    def setup_research(self, sources=None):
        raw=json.dumps({"schema_version":1,"source_id":"seeded",
            "claims":[{"goal_key":"other","route":"structure","status":"active","source_ref":"initial:1"}]},
            sort_keys=True).encode()
        (self.fx/"initial.json").write_bytes(raw)
        root_spec={"kind":"knowledge_intent","goal_key":"repair-goal",
            "knowledge":{"path":"initial.json","sha256":hashlib.sha256(raw).hexdigest(),"source_id":"seeded"},
            "research_on_gap":True,
            "options":[{"route":"structure","intent":{"kind":"goal_intent","objective":"ensure_structure",
                "resources":[{"role":"input","path":"structure.json"}],
                "requirements":[{"field":"owner","equals":"ops"}]}},
                {"route":"compare","intent":{"kind":"goal_intent","objective":"compare_records",
                "resources":[{"role":"reference","path":"before.csv"},
                             {"role":"observed","path":"after.csv"}]}}]}
        if sources is not None:
            root_spec["research_sources"]=sources
        with closing(connect(self.db)) as db:root=create_task(db,root_spec)
        tick=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual([t["status"] for t in tick["tasks"]],["RESEARCH_NEEDED","NEEDS_REVIEW"],tick)
        return tick["tasks"][0]["research_task_id"]

    def put_evidence(self,name,publisher,stances):
        raw=json.dumps({"source_id":name,"publisher_id":publisher,"goal_key":"repair-goal",
            "assertions":[{"route":r,"stance":s,"evidence_ref":"fixture:"+name}
                          for r,s in stances.items()]},sort_keys=True).encode()
        (self.fx/(name+".json")).write_bytes(raw)
        return {"path":name+".json","sha256":hashlib.sha256(raw).hexdigest(),
                "source_id":name,"publisher_id":publisher}

    def review(self,child,sa,sb):
        with closing(connect(self.db)) as db:
            task=create_task(db,{"kind":"research_assessment","research_task_id":child,
                                 "sources":[sa,sb]})
        report=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(len(report["tasks"]),1,report)
        return task,report["tasks"][0]

    def test_agreement_never_grants_authority(self):
        child=self.setup_research()
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        artifact=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(artifact["candidate_route_for_review"],"structure")
        self.assertFalse(artifact["production_effect_authorized"])
        self.assertFalse(artifact["source_independence_verified"])
        self.assertFalse((self.work/"sandbox").exists())

    def test_conflict_abstains_without_selected_route(self):
        child=self.setup_research()
        a=self.put_evidence("independent_a","publisher_one",{"structure":"supports","compare":"refutes"})
        b=self.put_evidence("independent_b","publisher_two",{"structure":"refutes","compare":"supports"})
        task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        artifact=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(artifact["reason"],"CONFLICTING_SOURCE_CLAIMS")
        self.assertIsNone(artifact["candidate_route_for_review"])

    def test_changed_source_fails_closed(self):
        child=self.setup_research()
        a=self.put_evidence("independent_a","publisher_one",{"structure":"supports","compare":"refutes"})
        b=self.put_evidence("independent_b","publisher_two",{"structure":"supports","compare":"refutes"})
        (self.fx/"independent_b.json").write_bytes(b"{}")
        _,result=self.review(child,a,b)
        self.assertEqual(result["status"],"UNKNOWN",result)

    def test_next_host_audit_keeps_valid_then_quarantines_tamper(self):
        child=self.setup_research()
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        assessment,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        next_tick=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual(next_tick["processed"],0,next_tick)
        self.assertFalse(next_tick["conformance"]["quarantined"],next_tick)
        (self.fx/"independent_b.json").write_bytes(b"{}")
        observations=[run_tick(self.db,self.work,self.fx,max_jobs=2) for _ in range(5)]
        self.assertTrue(any(t["conformance"]["quarantined"] for t in observations),observations)
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT state FROM tasks WHERE task_id=?",(assessment,)).fetchone()
            self.assertEqual(row["state"],"UNKNOWN")

    def test_original_host_self_enqueues_consented_review_without_second_user_task(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        child=self.setup_research([a,b])
        with closing(connect(self.db)) as db:
            queued=db.execute("SELECT * FROM tasks WHERE parent_task=?",(child,)).fetchall()
            self.assertEqual(len(queued),1)
            self.assertEqual(json.loads(queued[0]["source_spec"])["kind"],"research_assessment")
            auto_id=queued[0]["task_id"]
        next_tick=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual(next_tick["tasks"][0]["status"],"NEEDS_REVIEW",next_tick)
        report=json.loads((self.work/"artifacts"/(auto_id+".json")).read_text())
        self.assertEqual(report["candidate_route_for_review"],"structure")
        self.assertFalse(report["production_effect_authorized"])
        for _ in range(4):
            tick=run_tick(self.db,self.work,self.fx,max_jobs=2)
        with closing(connect(self.db)) as db:
            count=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",(child,)).fetchone()[0]
            self.assertEqual(count,1)

if __name__=="__main__":
    unittest.main()
