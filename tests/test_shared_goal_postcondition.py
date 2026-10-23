"""Shared-goal red/green acceptance for existing local feedback controller.

These are *candidate* postconditions, not external-world outcomes. They prove
whether alternatives actually share the same immutable requested target and
whether an independently checked failure schedules a DIFFERENT runnable task.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.host import run_tick
from cognition_agent_os.outcome_feedback import register_evidence_goal


class SharedPostconditionFeedback(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.db=root/"tasks.sqlite"
        self.work=root/"workspace"
        self.work.mkdir()
        self.fx=root/"sources"
        self.fx.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)

    def write(self,name,data):
        (self.fx/name).write_text(data,encoding="utf-8")

    def methods(self,*,bad_first=False):
        if bad_first:
            # First proposal is mechanically valid, but adds an unrelated
            # field. The *shared* target is exactly id=A,owner=ops.
            self.write("first.json",'{"id":"A","department":"north"}')
            first={"kind":"goal_case","goal_type":"json_keys",
                   "input":"first.json","desired":{"owner":"ops"}}
        else:
            self.write("first.json",'{"id":"A","owner":"wrong"}')
            first={"kind":"goal_case","goal_type":"json_keys",
                   "input":"first.json","desired":{"owner":"ops"}}
        self.write("second.csv","id\nA\n")
        return [
            first,
            {"kind":"goal_case","goal_type":"csv_columns",
             "input":"second.csv","desired":{"owner":"ops"}},
        ]

    def register(self,methods,goal_id="same-record"):
        return register_evidence_goal(
            self.db,self.fx,goal_id=goal_id,
            objective="Create an independently verified SAME id A, owner ops candidate",
            alternatives=methods,
            acceptance={"kind":"exact_record_postcondition",
                        "identity_fields":["id"],
                        "target_record":{"id":"A","owner":"ops"}})

    def tick(self):
        return run_tick(self.db,self.work,self.fx,max_jobs=4,
                        auto_local_goal_control=True)

    def root(self,task):
        with closing(connect(self.db)) as db:
            return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(task,)).fetchone())

    def children(self,task):
        with closing(connect(self.db)) as db:
            rows=db.execute(
                "SELECT task_id,state,source_spec FROM tasks WHERE parent_task=? "
                "ORDER BY created_at,task_id",(task,)).fetchall()
            return [dict(x) for x in rows]

    def test_first_preservation_conflict_selects_different_valid_same_goal_plan(self):
        task=self.register(self.methods())
        a=self.tick()
        self.assertEqual(len(self.children(task)),1,a)
        b=self.tick()
        self.assertEqual(b["tasks"][0]["reason"],"NO_SAFE_GOAL_PLAN",b)
        children=self.children(task)
        self.assertEqual(len(children),2,b)
        self.assertEqual(json.loads(children[0]["source_spec"])["goal_type"],"json_keys")
        self.assertEqual(json.loads(children[1]["source_spec"])["goal_type"],"csv_columns")
        c=self.tick()
        self.assertEqual(c["tasks"][0]["status"],"NEEDS_REVIEW",c)
        self.assertEqual(self.root(task)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertFalse(c["semantic_outcome_verified"])
        with closing(connect(self.db)) as db:
            receipt=db.execute(
                "SELECT details FROM events WHERE task_id=? AND kind='FEEDBACK_OBSERVED' "
                "ORDER BY event_id DESC LIMIT 1",(task,)).fetchone()
        self.assertEqual(json.loads(receipt[0])["reason"],"SHARED_LOCAL_TARGET_MET")

    def test_mechanically_valid_wrong_goal_result_does_not_self_approve(self):
        task=self.register(self.methods(bad_first=True))
        self.tick()
        first=self.tick()
        self.assertEqual(first["tasks"][0]["status"],"NEEDS_REVIEW",first)
        self.assertEqual(len(self.children(task)),2,first)
        self.assertNotEqual(self.root(task)["state"],"FEEDBACK_EVIDENCE_READY")
        final=self.tick()
        self.assertEqual(final["tasks"][0]["status"],"NEEDS_REVIEW",final)
        self.assertEqual(self.root(task)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertIs(final["semantic_outcome_verified"],False)

    def test_wrong_entity_second_candidate_rejected_at_registration(self):
        methods=self.methods()
        self.write("second.csv","id\nB\n")
        with self.assertRaises(ValueError):
            self.register(methods)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks").fetchone()[0],0)

    def test_source_drift_blocks_second_method_without_false_replan(self):
        task=self.register(self.methods())
        self.tick()
        self.write("first.json",'{"id":"A","owner":"tampered"}')
        self.tick()
        self.assertEqual(self.root(task)["state"],"FEEDBACK_UNVERIFIABLE")
        self.assertEqual(len(self.children(task)),1)

    def test_explicit_revoke_fences_new_plan(self):
        task=self.register(self.methods())
        self.tick()
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        self.tick()
        self.assertEqual(self.root(task)["state"],"FEEDBACK_STOPPED")
        self.assertEqual(len(self.children(task)),1)

    def test_legacy_evidence_only_goal_remains_separate(self):
        methods=self.methods()
        task=register_evidence_goal(self.db,self.fx,goal_id="legacy-evidence",
                                    objective="Find mechanically valid evidence",
                                    alternatives=methods)
        with closing(connect(self.db)) as db:
            spec=json.loads(db.execute(
                "SELECT source_spec FROM tasks WHERE task_id=?",(task,)).fetchone()[0])
        self.assertEqual(spec["version"],1)
        self.assertEqual(spec["outcome_requirement"],"INDEPENDENT_LOCAL_EVIDENCE")
        self.assertNotIn("acceptance",spec)

if __name__=="__main__":
    unittest.main()
