"""P33: knowledge evidence routes only among owner-authorized registered intents."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import alter_authority, connect, create_task, initialize
from cognition_agent_os.runner import run_once

class KnowledgeRoutingRuntimeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.fixtures=self.root/"fixture";self.fixtures.mkdir()
        self.workspace=self.root/"workspace"
        self.dbpath=self.root/"state.sqlite"
        db=connect(self.dbpath);initialize(db);db.close()
        self.fixtures.joinpath("settings.json").write_text('{"keep":"value"}')
        self.fixtures.joinpath("old.csv").write_text("item,amount\nA,5\n")
        self.fixtures.joinpath("new.csv").write_text("item,amount\nA,7\n")

    def knowledge(self,claims):
        raw=json.dumps({"schema_version":1,"source_id":"reviewed-atlas-lesson",
                        "claims":claims},sort_keys=True).encode()
        self.fixtures.joinpath("lesson.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def options(self):
        return [
            {"route":"repair_structure","intent":{
                "kind":"goal_intent","objective":"ensure_structure",
                "resources":[{"role":"input","path":"settings.json"}],
                "requirements":[{"field":"owner","equals":"ops"}]}},
            {"route":"compare_records","intent":{
                "kind":"goal_intent","objective":"compare_records",
                "resources":[{"role":"reference","path":"old.csv"},
                             {"role":"observed","path":"new.csv"}]}}
        ]

    def spec(self,digest,goal="settings-owner"):
        return {"kind":"knowledge_intent","goal_key":goal,
                "knowledge":{"path":"lesson.json","sha256":digest,
                             "source_id":"reviewed-atlas-lesson"},
                "options":self.options()}

    def seed(self,spec):
        db=connect(self.dbpath)
        try:return create_task(db,spec)
        finally:db.close()

    def rows(self):
        db=connect(self.dbpath)
        try:
            return [dict(x) for x in db.execute("SELECT * FROM tasks ORDER BY created_at")]
        finally:db.close()

    def test_selected_knowledge_drives_actual_registered_goal_and_sandbox(self):
        digest=self.knowledge([{"goal_key":"settings-owner","route":"repair_structure",
                               "status":"active","source_ref":"atlas:Q01/fit"}])
        root=self.seed(self.spec(digest))
        report=run_tick(self.dbpath,self.workspace,self.fixtures,
                        max_jobs=3,auto_stage_goals=True)
        self.assertEqual(report["processed"],2,report)
        self.assertEqual(report["tasks"][0]["status"],"DECOMPOSED")
        self.assertEqual(report["tasks"][0]["route"],"repair_structure")
        child=report["tasks"][0]["child_task_id"]
        self.assertIn(report["tasks"][1]["status"],("NEEDS_REVIEW","SANDBOX_VERIFIED"))
        self.assertEqual(json.loads((self.workspace/"sandbox"/(child+".candidate")).read_text()),
                         {"keep":"value","owner":"ops"})
        self.assertEqual(self.fixtures.joinpath("settings.json").read_text(),'{"keep":"value"}')
        self.assertEqual(self.rows()[0]["task_id"],root)
        self.assertFalse(report["semantic_outcome_verified"])

    def test_evidence_selects_a_different_existing_capability(self):
        digest=self.knowledge([{"goal_key":"settings-owner","route":"compare_records",
                               "status":"active","source_ref":"atlas:Q05/observe"}])
        self.seed(self.spec(digest))
        report=run_tick(self.dbpath,self.workspace,self.fixtures,max_jobs=2)
        self.assertEqual([x["status"] for x in report["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],report)
        self.assertEqual(report["tasks"][0]["route"],"compare_records")
        self.assertEqual(report["tasks"][1]["discrepancies_count"],1)
        self.assertFalse((self.workspace/"sandbox").exists())

    def test_withdrawn_or_near_neighbor_evidence_blocks_but_unrelated_task_continues(self):
        for claim in [
            {"goal_key":"settings-owners","route":"repair_structure",
             "status":"active","source_ref":"atlas:near-neighbor"},
            {"goal_key":"settings-owner","route":"repair_structure",
             "status":"withdrawn","source_ref":"atlas:withdrawn"},
        ]:
            with self.subTest(claim=claim):
                digest=self.knowledge([claim])
                root=self.seed(self.spec(digest))
                other=self.seed({"kind":"fixture","old":"settings.json","new":"settings.json"})
                tick=run_tick(self.dbpath,self.workspace,self.fixtures,max_jobs=2)
                self.assertEqual(tick["tasks"][0]["status"],"UNKNOWN",tick)
                self.assertIn(tick["tasks"][0].get("reason"),(
                    "KNOWLEDGE_NOT_APPLICABLE","KNOWLEDGE_UNAVAILABLE"))
                self.assertEqual(tick["tasks"][1]["status"],"VERIFIED")
                self.assertEqual(len([r for r in self.rows() if r["parent_task"]==root]),0)
                # Repeat with fresh persisted ledgers per case.
                self.dbpath=self.root/("other-"+claim["source_ref"].replace(":","-")+".sqlite")
                db=connect(self.dbpath);initialize(db);db.close()

    def test_conflicting_claims_never_select_the_first_matching_one(self):
        digest=self.knowledge([
            {"goal_key":"settings-owner","route":"repair_structure",
             "status":"active","source_ref":"atlas:evidence-a"},
            {"goal_key":"settings-owner","route":"compare_records",
             "status":"active","source_ref":"atlas:evidence-b"}])
        tid=self.seed(self.spec(digest))
        result=run_once(self.dbpath,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"UNKNOWN",result)
        self.assertEqual(len([r for r in self.rows() if r["parent_task"]==tid]),0)

    def test_source_change_after_routing_refuses_child_on_following_tick(self):
        digest=self.knowledge([{"goal_key":"settings-owner","route":"repair_structure",
                               "status":"active","source_ref":"atlas:pin"}])
        tid=self.seed(self.spec(digest))
        first=run_tick(self.dbpath,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(first["tasks"][0]["status"],"DECOMPOSED",first)
        self.knowledge([{"goal_key":"settings-owner","route":"compare_records",
                         "status":"active","source_ref":"atlas:later"}])
        second=run_tick(self.dbpath,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(second["tasks"][0]["status"],"UNKNOWN",second)
        self.assertEqual(second["tasks"][0]["reason"],"KNOWLEDGE_SOURCE_CHANGED")
        self.assertFalse((self.workspace/"sandbox").exists())
        self.assertEqual(len([r for r in self.rows() if r["parent_task"]==tid]),1)

    def test_goal_revision_mid_knowledge_resolution_cannot_admit_child(self):
        from cognition_agent_os import knowledge_routing
        digest=self.knowledge([{"goal_key":"settings-owner","route":"repair_structure",
                               "status":"active","source_ref":"atlas:pin"}])
        tid=self.seed(self.spec(digest))
        original=knowledge_routing.resolve_knowledge_route
        def rotating(*args,**kwargs):
            resolved=original(*args,**kwargs)
            db=connect(self.dbpath)
            try:alter_authority(db,goal_change=True)
            finally:db.close()
            return resolved
        with patch.object(knowledge_routing,"resolve_knowledge_route",side_effect=rotating):
            result=run_once(self.dbpath,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"BLOCKED",result)
        self.assertEqual(result["reason"],"STALE_GOAL")
        self.assertEqual(len([r for r in self.rows() if r["parent_task"]==tid]),0)

if __name__=="__main__":
    unittest.main()
