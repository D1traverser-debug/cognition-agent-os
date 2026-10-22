"""P35 checks an actual P34 research lineage through the actual original host."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
            rows=db.execute("SELECT * FROM tasks WHERE parent_task=?",(child,)).fetchall()
            self.assertEqual(len(rows),1)
            task=rows[0]["task_id"]
            self.assertEqual(json.loads(rows[0]["source_spec"])["sources"],[sa,sb])
        report=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(len(report["tasks"]),1,report)
        return task,report["tasks"][0]

    def test_immutable_public_source_is_read_by_real_host_without_fixture_duplication(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        sha="a"*40
        a.update({"kind":"github","repo":"example-org/project-a","ref":sha})
        b.update({"kind":"github","repo":"example-org/project-b","ref":sha})
        pinned={(a["repo"],a["path"],sha):(self.fx/a["path"]).read_bytes(),
                (b["repo"],b["path"],sha):(self.fx/b["path"]).read_bytes()}
        child=self.setup_research([a,b])
        # Genuine original host lifecycle; network boundary replaced only in test.
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=lambda repo,path,ref:pinned[(repo,path,ref)]) as fetch:
            task,result=self.review(child,a,b)
        self.assertGreaterEqual(fetch.call_count,4)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        report=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertFalse(report["production_effect_authorized"])
        self.assertEqual(report["candidate_route_for_review"],"structure")

    def test_nested_public_paths_and_same_filename_from_distinct_repositories(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        source_a=(self.fx/a["path"]).read_bytes()
        source_b=(self.fx/b["path"]).read_bytes()
        sha="a"*40
        a.update({"kind":"github","repo":"org-one/repo","path":"reports/evidence.json","ref":sha})
        b.update({"kind":"github","repo":"org-two/repo","path":"reports/evidence.json","ref":sha})
        pinned={(a["repo"],a["path"],sha):source_a,(b["repo"],b["path"],sha):source_b}
        child=self.setup_research([a,b])
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=lambda repo,path,ref:pinned[(repo,path,ref)]):
            task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        report=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(report["candidate_route_for_review"],"structure")
        self.assertFalse(report["production_effect_authorized"])

    def test_distinct_publisher_labels_same_repo_must_abstain(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        pinned={}
        for item in (a,b):
            data=(self.fx/item["path"]).read_bytes()
            item.update({"kind":"github","repo":"one-operator/same-origin",
                         "ref":"a"*40})
            pinned[(item["repo"],item["path"],item["ref"])]=data
        child=self.setup_research([a,b])
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=lambda repo,path,ref:pinned[(repo,path,ref)]):
            task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        report=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(report["reason"],"SAME_REPOSITORY_NOT_INDEPENDENT")
        self.assertIsNone(report["candidate_route_for_review"])

    def test_public_source_transport_failure_does_not_crash_host(self):
        from cognition_agent_os.source import SourceUnavailable
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        for item,repo in ((a,"org-one/repo"),(b,"org-two/repo")):
            item.update({"kind":"github","repo":repo,"ref":"a"*40})
        child=self.setup_research([a,b])
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=SourceUnavailable("temporary public API failure")):
            task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"UNKNOWN",result)
        self.assertFalse((self.work/"artifacts"/(task+".json")).exists())
        after=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(after["processed"],0,after)

    def test_research_transport_recovers_after_cooldown_without_new_authority(self):
        from cognition_agent_os.source import SourceUnavailable
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        pinned={}
        for item,repo in ((a,"org-one/repo"),(b,"org-two/repo")):
            item.update({"kind":"github","repo":repo,"ref":"a"*40})
            pinned[(repo,item["path"],item["ref"])]=(self.fx/item["path"]).read_bytes()
        child=self.setup_research([a,b])
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=SourceUnavailable("outage")):
            task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"UNKNOWN",result)
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT state,due_at FROM tasks WHERE task_id=?",(task,)).fetchone()
            self.assertEqual(row["state"],"PENDING")
            self.assertGreater(row["due_at"],0)
            db.execute("UPDATE tasks SET due_at=0 WHERE task_id=?",(task,))
            db.commit()
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=lambda repo,path,ref:pinned[(repo,path,ref)]):
            next_tick=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(next_tick["tasks"][0]["status"],"NEEDS_REVIEW",next_tick)
        with closing(connect(self.db)) as db:
            retries=db.execute("SELECT COUNT(*) FROM events WHERE task_id=? AND kind='RESEARCH_TRANSPORT_RETRY_QUEUED'",(task,)).fetchone()[0]
            self.assertEqual(retries,1)

    def test_research_transport_retry_budget_exhausts(self):
        from cognition_agent_os.source import SourceUnavailable
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        for item,repo in ((a,"org-one/repo"),(b,"org-two/repo")):
            item.update({"kind":"github","repo":repo,"ref":"a"*40})
        child=self.setup_research([a,b])
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   side_effect=SourceUnavailable("outage")):
            task,first=self.review(child,a,b)
            self.assertEqual(first["status"],"UNKNOWN")
            for attempt in range(2):
                with closing(connect(self.db)) as db:
                    db.execute("UPDATE tasks SET due_at=0 WHERE task_id=?",(task,))
                    db.commit()
                result=run_tick(self.db,self.work,self.fx,max_jobs=1)
                self.assertEqual(result["tasks"][0]["status"],"UNKNOWN",result)
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT state,error_code FROM tasks WHERE task_id=?",(task,)).fetchone()
            self.assertEqual((row["state"],row["error_code"]),("UNKNOWN","RESEARCH_RETRY_EXHAUSTED"))

    def test_public_source_hash_mismatch_fails_closed(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        for s,name in ((a,"project-a"),(b,"project-b")):
            s.update({"kind":"github","repo":"example-org/"+name,"ref":"a"*40})
        child=self.setup_research([a,b])
        with patch("cognition_agent_os.research_assessment.github_public_snapshot",
                   return_value=b'{"changed":true}'):
            task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"UNKNOWN",result)
        self.assertFalse((self.work/"artifacts"/(task+".json")).exists())

    def test_agreement_never_grants_authority(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        child=self.setup_research([a,b])
        task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        artifact=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(artifact["candidate_route_for_review"],"structure")
        self.assertFalse(artifact["production_effect_authorized"])
        self.assertFalse(artifact["source_independence_verified"])
        self.assertFalse((self.work/"sandbox").exists())

    def test_two_publishers_citing_one_underlying_item_cannot_create_consensus(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        for name in ("independent_a","independent_b"):
            p=self.fx/(name+".json")
            obj=json.loads(p.read_text())
            for statement in obj["assertions"]:
                statement["evidence_ref"]="shared:original-document-1"
            raw=json.dumps(obj,sort_keys=True).encode()
            p.write_bytes(raw)
            if name=="independent_a":
                a["sha256"]=hashlib.sha256(raw).hexdigest()
            else:
                b["sha256"]=hashlib.sha256(raw).hexdigest()
        child=self.setup_research([a,b])
        task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        report=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(report["reason"],"SHARED_UNDERLYING_EVIDENCE")
        self.assertIsNone(report["candidate_route_for_review"])

    def test_conflict_abstains_without_selected_route(self):
        a=self.put_evidence("independent_a","publisher_one",{"structure":"supports","compare":"refutes"})
        b=self.put_evidence("independent_b","publisher_two",{"structure":"refutes","compare":"supports"})
        child=self.setup_research([a,b])
        task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        artifact=json.loads((self.work/"artifacts"/(task+".json")).read_text())
        self.assertEqual(artifact["reason"],"CONFLICTING_SOURCE_CLAIMS")
        self.assertIsNone(artifact["candidate_route_for_review"])

    def test_invalid_utf8_research_source_is_isolated_as_unknown(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        invalid=bytes([255,254,250])
        (self.fx/b["path"]).write_bytes(invalid)
        b["sha256"]=hashlib.sha256(invalid).hexdigest()
        child=self.setup_research([a,b])
        task,result=self.review(child,a,b)
        self.assertEqual(result["status"],"UNKNOWN",result)
        self.assertFalse((self.work/"artifacts"/(task+".json")).exists())
        # The scheduler must remain usable after malformed untrusted bytes.
        followup=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(followup["processed"],0,followup)

    def test_changed_source_fails_closed(self):
        a=self.put_evidence("independent_a","publisher_one",{"structure":"supports","compare":"refutes"})
        b=self.put_evidence("independent_b","publisher_two",{"structure":"supports","compare":"refutes"})
        child=self.setup_research([a,b])
        (self.fx/"independent_b.json").write_bytes(b"{}")
        _,result=self.review(child,a,b)
        self.assertEqual(result["status"],"UNKNOWN",result)

    def test_next_host_audit_keeps_valid_then_quarantines_tamper(self):
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        child=self.setup_research([a,b])
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


    def test_manually_attached_child_without_source_grant_is_refused(self):
        child=self.setup_research()
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        with closing(connect(self.db)) as db:
            rogue=create_task(db,{"kind":"research_assessment",
                "research_task_id":child,"sources":[a,b]},parent=child)
        got=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(got["tasks"][0]["status"],"UNKNOWN",got)
        self.assertFalse((self.work/"artifacts"/(rogue+".json")).exists())

    def test_orphan_assessment_cannot_claim_lineage(self):
        child=self.setup_research()
        stances={"structure":"supports","compare":"refutes"}
        a=self.put_evidence("independent_a","publisher_one",stances)
        b=self.put_evidence("independent_b","publisher_two",stances)
        with closing(connect(self.db)) as db:
            rogue=create_task(db,{"kind":"research_assessment",
                "research_task_id":child,"sources":[a,b]})
        result=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(result["tasks"][0]["status"],"UNKNOWN",result)
        self.assertFalse((self.work/"artifacts"/(rogue+".json")).exists())

if __name__=="__main__":
    unittest.main()
