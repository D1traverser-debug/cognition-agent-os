"""P34: an unserved goal creates ONE bounded, reviewable research agenda.

This probes the original host, claim/grant DB, offline artifact writer and
native independent conformance; no pretend scholarly researcher is involved.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect,create_task,initialize,alter_authority
from cognition_agent_os.runner import run_once


class ResearchGapHostTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.work=self.root/"workspace";self.work.mkdir()
        self.db=self.root/"task.sqlite"
        with connect(self.db) as db:initialize(db)
        (self.fx/"structure.json").write_text('{"keep":42}')
        (self.fx/"before.csv").write_text("id,amount\nA,1\n")
        (self.fx/"after.csv").write_text("id,amount\nA,2\n")

    def put_knowledge(self,claims):
        raw=json.dumps({"schema_version":1,"source_id":"reviewed-study",
                        "claims":claims},sort_keys=True).encode()
        (self.fx/"study.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def spec(self,sha,*,opt_in=True):
        value={"kind":"knowledge_intent","goal_key":"repair-goal",
            "knowledge":{"path":"study.json","sha256":sha,"source_id":"reviewed-study"},
            "options":[
                {"route":"structure","intent":{"kind":"goal_intent",
                    "objective":"ensure_structure",
                    "resources":[{"role":"input","path":"structure.json"}],
                    "requirements":[{"field":"owner","equals":"ops"}]}},
                {"route":"compare","intent":{"kind":"goal_intent",
                    "objective":"compare_records",
                    "resources":[{"role":"reference","path":"before.csv"},
                                 {"role":"observed","path":"after.csv"}]}}
            ]}
        if opt_in:value["research_on_gap"]=True
        return value

    def enqueue(self,spec):
        with connect(self.db) as db:
            return create_task(db,spec)

    def inspect(self):
        with connect(self.db) as db:
            return [dict(x) for x in db.execute("SELECT * FROM tasks")]

    def test_no_matching_claim_autonomously_enqueues_single_reviewable_research_step(self):
        sha=self.put_knowledge([{"goal_key":"unrelated-goal","route":"structure",
                                 "status":"active","source_ref":"atlas:q5"}])
        root=self.enqueue(self.spec(sha))
        one=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(one["tasks"][0]["status"],"RESEARCH_NEEDED",one)
        child=one["tasks"][0]["research_task_id"]
        self.assertEqual(len(self.inspect()),2)
        self.assertEqual(self.inspect()[0]["state"],"RESEARCH_NEEDED")
        two=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(two["tasks"][0]["status"],"NEEDS_REVIEW",two)
        result=json.loads((self.work/"artifacts"/(child+".json")).read_text())
        self.assertEqual(result["status"],"RESEARCH_REQUEST_NOT_ANSWER")
        self.assertEqual(result["gap_kind"],"NO_EXACT_GOAL_CLAIM")
        self.assertEqual(set(result["routes"]),{"structure","compare"})
        self.assertFalse(result["source_trust_proven"])
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse((self.work/"sandbox").exists())
        self.assertEqual((self.fx/"structure.json").read_text(),'{"keep":42}')
        self.assertEqual(run_tick(self.db,self.work,self.fx)["processed"],0)
        self.assertEqual(len(self.inspect()),2)
        self.assertEqual(self.inspect()[0]["state"],"RESEARCH_NEEDED")
        self.assertEqual(self.inspect()[1]["state"],"NEEDS_REVIEW")
        self.assertTrue(two["conformance"]["mechanically_valid"]>=1)

    def test_conflict_starts_research_not_silent_first_match(self):
        sha=self.put_knowledge([
            {"goal_key":"repair-goal","route":"compare","status":"active","source_ref":"atlas:x"},
            {"goal_key":"repair-goal","route":"structure","status":"active","source_ref":"atlas:y"}])
        self.enqueue(self.spec(sha))
        report=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual([x["status"] for x in report["tasks"]],
                         ["RESEARCH_NEEDED","NEEDS_REVIEW"],report)
        child=report["tasks"][0]["research_task_id"]
        artifact=json.loads((self.work/"artifacts"/(child+".json")).read_text())
        self.assertEqual(artifact["gap_kind"],"CONFLICTING_CLAIMS")
        self.assertNotIn("selected_route",artifact)

    def test_withdrawal_or_untrusted_source_does_not_elevate_to_action(self):
        sha=self.put_knowledge([{"goal_key":"repair-goal","route":"compare",
                                 "status":"withdrawn","source_ref":"atlas:revoked"}])
        self.enqueue(self.spec(sha))
        tick=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual([x["status"] for x in tick["tasks"]],
                         ["RESEARCH_NEEDED","NEEDS_REVIEW"])
        child=tick["tasks"][0]["research_task_id"]
        agenda=json.loads((self.work/"artifacts"/(child+".json")).read_text())
        self.assertEqual(agenda["gap_kind"],"WITHDRAWN_CLAIM")
        # Byte swap cannot be reinterpreted as a new source of truth.
        self.put_knowledge([{"goal_key":"repair-goal","route":"structure",
                            "status":"active","source_ref":"atlas:replacement"}])
        later=run_tick(self.db,self.work,self.fx,max_jobs=4)
        self.assertTrue(later["conformance"]["quarantined"],later)
        states={r["task_id"]:r["state"] for r in self.inspect()}
        self.assertEqual(states[child],"UNKNOWN")
        self.assertFalse((self.work/"sandbox").exists())

    def test_pin_changed_between_admission_and_research_blocks_old_child(self):
        sha=self.put_knowledge([{"goal_key":"different-goal","route":"compare",
                                 "status":"active","source_ref":"atlas:different"}])
        root=self.enqueue(self.spec(sha))
        first=run_tick(self.db,self.work,self.fx,max_jobs=1)
        self.assertEqual(first["tasks"][0]["status"],"RESEARCH_NEEDED")
        child=first["tasks"][0]["research_task_id"]
        self.put_knowledge([{"goal_key":"repair-goal","route":"compare",
                            "status":"active","source_ref":"atlas:fresh"}])
        another=self.enqueue({"kind":"fixture","old":"structure.json",
                              "new":"structure.json"})
        second=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual(second["tasks"][0]["status"],"UNKNOWN",second)
        self.assertEqual(second["tasks"][1]["status"],"VERIFIED",second)
        self.assertFalse((self.work/"artifacts"/(child+".json")).exists())
        self.assertEqual({r["task_id"]:r["state"] for r in self.inspect()}[child],"UNKNOWN")

    def test_unapproved_manual_research_child_never_writes_an_agenda(self):
        sha=self.put_knowledge([{"goal_key":"other-goal","route":"compare",
                                 "status":"active","source_ref":"atlas:q1"}])
        arbitrary={"kind":"research_gap","parent_id":"0"*32,
                   "goal_key":"repair-goal","gap_kind":"NO_EXACT_GOAL_CLAIM",
                   "knowledge":{"path":"study.json","sha256":sha,
                                "source_id":"reviewed-study"},
                   "routes":{"structure":{"capability":"arbitrary-shell",
                                          "plan_sha256":"0"*64}}}
        self.enqueue(arbitrary)
        result=run_once(self.db,self.work,self.fx)
        self.assertEqual(result["status"],"UNKNOWN",result)
        self.assertFalse((self.work/"artifacts").exists())

    def test_tampered_research_output_is_revoked_without_new_user_task(self):
        sha=self.put_knowledge([{"goal_key":"other-goal","route":"compare",
                                 "status":"active","source_ref":"atlas:study"}])
        self.enqueue(self.spec(sha))
        first=run_tick(self.db,self.work,self.fx,max_jobs=2)
        child=first["tasks"][0]["research_task_id"]
        artifact=self.work/"artifacts"/(child+".json")
        self.assertTrue(artifact.is_file(),first)
        artifact.write_text('{"status":"RESEARCH_COMPLETED"}')
        tick=run_tick(self.db,self.work,self.fx,max_jobs=4)
        self.assertEqual(tick["processed"],0)
        self.assertTrue(tick["conformance"]["quarantined"],tick)
        states={r["task_id"]:r["state"] for r in self.inspect()}
        self.assertEqual(states[child],"UNKNOWN")
        self.assertEqual(json.loads((self.fx/"structure.json").read_text()),
                         {"keep":42})

    def test_no_research_optin_keeps_original_policy_and_legal_neighbor(self):
        sha=self.put_knowledge([{"goal_key":"other-goal","route":"compare",
                                 "status":"active","source_ref":"atlas:q1"}])
        root=self.enqueue(self.spec(sha,opt_in=False))
        other=self.enqueue({"kind":"fixture","old":"structure.json","new":"structure.json"})
        report=run_tick(self.db,self.work,self.fx,max_jobs=2)
        self.assertEqual([x["status"] for x in report["tasks"]],
                         ["UNKNOWN","VERIFIED"],report)
        self.assertEqual(len([r for r in self.inspect() if r["parent_task"]==root]),0)

    def test_goal_revision_denies_research_child(self):
        sha=self.put_knowledge([{"goal_key":"other-goal","route":"compare",
                                 "status":"active","source_ref":"atlas:q1"}])
        root=self.enqueue(self.spec(sha))
        with connect(self.db) as db:alter_authority(db,goal_change=True)
        got=run_once(self.db,self.work,self.fx)
        self.assertEqual(got["status"],"BLOCKED")
        self.assertFalse(any(r["parent_task"]==root for r in self.inspect()))

    def test_missing_source_does_not_fabricate_research_conclusions(self):
        sha=self.put_knowledge([{"goal_key":"other-goal","route":"compare",
                                 "status":"active","source_ref":"atlas:q1"}])
        root=self.enqueue(self.spec(sha))
        (self.fx/"study.json").unlink()
        got=run_once(self.db,self.work,self.fx)
        self.assertEqual(got["status"],"UNKNOWN",got)
        self.assertFalse(any(r["parent_task"]==root for r in self.inspect()))

if __name__=="__main__":
    unittest.main()
