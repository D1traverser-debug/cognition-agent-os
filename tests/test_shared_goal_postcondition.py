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

    def test_two_mechanically_valid_steps_cannot_claim_wrong_common_record(self):
        # Both formats are structurally valid. The SECOND candidate preserves
        # an extra field, so it still fails the originally declared exact target.
        methods=self.methods()
        self.write("second.csv","id,department\nA,north\n")
        task=self.register(methods,goal_id="exhaust-wrong-final")
        self.tick()
        first=self.tick()
        self.assertEqual(first["tasks"][0]["reason"],"NO_SAFE_GOAL_PLAN",first)
        self.assertEqual(len(self.children(task)),2)
        last=self.tick()
        self.assertEqual(last["tasks"][0]["status"],"NEEDS_REVIEW",last)
        self.assertEqual(self.root(task)["state"],"FEEDBACK_STOPPED")
        self.assertEqual(self.root(task)["error_code"],"EXHAUSTED_SAFE_ALTERNATIVES")
        self.assertIs(last["semantic_outcome_verified"],False)
        for _ in range(3):
            self.tick()
        self.assertEqual(len(self.children(task)),2)

    def test_no_op_on_same_exact_record_is_verified_without_second_attempt(self):
        methods=self.methods()
        self.write("first.json",'{"id":"A","owner":"ops"}')
        task=self.register(methods,goal_id="already-correct")
        self.tick()
        observed=self.tick()
        self.assertEqual(observed["tasks"][0]["status"],"VERIFIED",observed)
        self.assertEqual(self.root(task)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertEqual(len(self.children(task)),1)
        self.assertIs(observed["semantic_outcome_verified"],False)

    def test_source_change_after_first_failure_blocks_fallback_admission(self):
        methods=self.methods()
        task=self.register(methods,goal_id="second-source-drift")
        self.tick()
        # First child legitimately cannot preserve the conflicting owner.
        # The second attempt's source changed from its registration digest.
        self.write("second.csv","id\nB\n")
        self.tick()
        self.assertEqual(self.root(task)["state"],"FEEDBACK_UNVERIFIABLE")
        self.assertEqual(len(self.children(task)),1)

    def test_artifact_swap_after_independent_audit_is_inconclusive(self):
        # Simulate artifact bytes changing AFTER a separately invoked audit:
        # successful audit of earlier bytes must not license a later read.
        import hashlib
        from unittest.mock import patch
        from cognition_agent_os.outcome_feedback import _outcome
        task=self.register(self.methods(),goal_id="swap-race")
        for _ in range(3):
            self.tick()
        child=self.children(task)[-1]
        with closing(connect(self.db)) as db:
            # Production controller receives the complete SQLite row, not
            # the abbreviated display projection returned by children().
            child=dict(db.execute("SELECT * FROM tasks WHERE task_id=?",
                                  (child["task_id"],)).fetchone())
        self.assertEqual(child["state"],"NEEDS_REVIEW")
        filename=self.work/"artifacts"/(child["task_id"]+".json")
        filename.write_bytes(filename.read_bytes()+b" ")
        method={
            "task_spec":json.loads(child["source_spec"]),
            "source_sha256":{"second.csv":hashlib.sha256(
                (self.fx/"second.csv").read_bytes()).hexdigest()},
        }
        with patch("cognition_agent_os.outcome_feedback.audit_goal",
                   return_value={"status":"CANDIDATE_MECHANICALLY_VALID"}):
            result=_outcome(child,method,self.db,self.work,self.fx,{
                "kind":"exact_record_postcondition",
                "identity_fields":["id"],
                "target_record":{"id":"A","owner":"ops"},
            })
        self.assertEqual(result,"INCONCLUSIVE")

    def test_unrelated_or_malformed_acceptance_cannot_be_self_issued(self):
        methods=self.methods()
        invalid=[
            {"kind":"exact_record_postcondition","identity_fields":["id"],
             "target_record":{"id":"B","owner":"ops"}},
            {"kind":"exact_record_postcondition","identity_fields":["id"],
             "target_record":{"id":"A","owner":False}},
            {"kind":"exact_record_postcondition","identity_fields":[],
             "target_record":{"id":"A","owner":"ops"}},
        ]
        for acceptance in invalid:
            with self.subTest(acceptance=acceptance):
                with self.assertRaises(ValueError):
                    register_evidence_goal(
                        self.db,self.fx,goal_id="refuse-noncomparable",
                        objective="One exact shared target",alternatives=methods,
                        acceptance=acceptance)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],0)

    def test_cold_command_line_restarts_execute_distinct_common_goal_methods(self):
        # A user can seed once; three disconnected CLI processes pick up the
        # same SQLite/authority contract without Python-side test scheduling.
        import subprocess
        import sys
        methods=self.methods()
        spec={
            "goal_id":"cold-cli-shared-goal",
            "objective":"Candidate for id A with owner ops",
            "alternatives":methods,
            "acceptance":{"kind":"exact_record_postcondition",
                "identity_fields":["id"],
                "target_record":{"id":"A","owner":"ops"}},
        }
        specfile=self.fx.parent/"shared-goal-seed.json"
        specfile.write_text(json.dumps(spec,sort_keys=True),encoding="utf-8")
        common=[sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(self.db),"--workspace",str(self.work),
                "--fixtures",str(self.fx)]
        created=subprocess.run(common+["seed-evidence-feedback","--spec",str(specfile)],
                               capture_output=True,text=True,check=True)
        tid=json.loads(created.stdout)["task_id"]
        results=[]
        for _ in range(3):
            tick=subprocess.run(common+["host-tick","--auto-local-goal-control",
                                         "--max-jobs","4"],check=True,
                                capture_output=True,text=True)
            results.append(json.loads(tick.stdout))
        self.assertEqual(len(self.children(tid)),2)
        self.assertEqual(results[1]["tasks"][0]["reason"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual(results[2]["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertFalse(any(x["semantic_outcome_verified"] for x in results))

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
