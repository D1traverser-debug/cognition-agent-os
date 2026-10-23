"""Goal-independent candidate feedback on the SAME host/ledger, two domains.

The accepted result is independent LOCAL EVIDENCE, never business completion.
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
from cognition_agent_os.conformance import inspect_conformance


class OutcomeFeedbackTwoDomains(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.db = root / "tasks.sqlite"
        self.work = root / "work"
        self.work.mkdir()
        self.fx = root / "fixtures"
        self.fx.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)

    def write(self, name, contents):
        (self.fx / name).write_text(contents, encoding="utf-8")
        return name

    def structure_methods(self):
        self.write("conflict.json", '{"id":"A","owner":"wrong"}')
        self.write("valid.csv", "id\nA\n")
        return [
            {"kind":"goal_case","goal_type":"json_keys",
             "input":"conflict.json","desired":{"owner":"ops"}},
            {"kind":"goal_case","goal_type":"csv_columns",
             "input":"valid.csv","desired":{"owner":"ops"}},
        ]

    def reconciliation_methods(self):
        self.write("amb_ref.csv", "code,zone\nA,1\nB,2\n")
        self.write("amb_obs.csv", "code,zone\nA,1\nB,2\n")
        self.write("ref.csv", "id,amount\nA,4\nB,5\n")
        self.write("obs.csv", "id,amount\nA,6\nB,5\n")
        return [
            {"kind":"record_reconciliation","reference":"amb_ref.csv",
             "observed":"amb_obs.csv","objective":"identify_discrepancies"},
            {"kind":"record_reconciliation","reference":"ref.csv",
             "observed":"obs.csv","objective":"identify_discrepancies"},
        ]

    def seed(self, methods, name="local-evidence"):
        return register_evidence_goal(
            self.db, self.fx, goal_id=name,
            objective="Produce independently rechecked local evidence",
            alternatives=methods)

    def tick(self):
        return run_tick(self.db,self.work,self.fx,max_jobs=4,
                        auto_local_goal_control=True)

    def root(self, task_id):
        with closing(connect(self.db)) as db:
            return dict(db.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())

    def children(self,task_id):
        with closing(connect(self.db)) as db:
            return [dict(x) for x in db.execute(
                "SELECT * FROM tasks WHERE parent_task=? ORDER BY created_at",
                (task_id,)).fetchall()]

    def test_structure_failure_switches_and_second_mechanically_passes(self):
        tid=self.seed(self.structure_methods())
        a=self.tick()
        self.assertEqual(len(self.children(tid)),1,a)
        b=self.tick()
        self.assertEqual(b["tasks"][0]["status"],"UNKNOWN",b)
        self.assertEqual(b["tasks"][0]["reason"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual(len(self.children(tid)),2,b)
        c=self.tick()
        self.assertEqual(c["tasks"][0]["status"],"NEEDS_REVIEW",c)
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        self.assertFalse(c["semantic_outcome_verified"])
        self.assertEqual(c["local_goal_control"][-1]["status"],"FEEDBACK_EVIDENCE_READY")
        self.assertIs(c["local_goal_control"][-1]["business_outcome_verified"],False)
        self.assertEqual(self.tick()["conformance"]["status"] in
                         ("MECHANICAL_EVIDENCE_OBSERVED","PARTIAL_EVIDENCE"),True)

    def test_reconciliation_key_ambiguity_switches_to_independent_sql(self):
        tid=self.seed(self.reconciliation_methods(),name="inventory-diff")
        self.tick()
        failed=self.tick()
        self.assertEqual(failed["tasks"][0]["reason"],"JOIN_KEY_AMBIGUOUS",failed)
        self.assertEqual(len(self.children(tid)),2,failed)
        approved=self.tick()
        self.assertEqual(approved["tasks"][0]["status"],"NEEDS_REVIEW",approved)
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        # No external mutation occurred. The owner still decides whether the
        # independently computed discrepancies satisfy its actual goal.
        self.assertFalse(approved["semantic_outcome_verified"])

    def test_source_mutation_fences_existing_child(self):
        tid=self.seed(self.structure_methods())
        self.tick()
        self.write("conflict.json",'{"id":"A","owner":"tampered"}')
        self.tick()
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_UNVERIFIABLE")
        self.assertEqual(len(self.children(tid)),1)

    def test_revocation_prevents_next_method(self):
        tid=self.seed(self.structure_methods())
        self.tick()
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        self.tick()
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_STOPPED")
        self.assertEqual(len(self.children(tid)),1)

    def test_duplicate_host_ticks_cannot_admit_third_child(self):
        tid=self.seed(self.structure_methods())
        for _ in range(7):
            self.tick()
        self.assertEqual(len(self.children(tid)),2)
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_EVIDENCE_READY")

    def test_mechanically_accepted_artifact_tamper_is_detected(self):
        tid=self.seed(self.reconciliation_methods())
        for _ in range(3):
            self.tick()
        children=self.children(tid)
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_EVIDENCE_READY")
        artifact=self.work / "artifacts" / (children[-1]["task_id"]+".json")
        artifact.write_text('{"status":"FORGED"}')
        conformance=inspect_conformance(
            self.db,self.work,self.fx,enforce=True,max_cases=64)
        findings=[f for f in conformance["findings"] if f["task_id"]==tid]
        self.assertEqual(findings[0]["disposition"],"CONFIRMED_INCONSISTENCY")
        self.assertEqual(self.root(tid)["state"],"UNKNOWN")


    def test_missing_first_source_does_not_crash_host_or_grant_new_action(self):
        tid=self.seed(self.structure_methods())
        (self.fx / "conflict.json").unlink()
        result=self.tick()
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_UNVERIFIABLE",result)
        self.assertEqual(self.children(tid),[])
        self.assertFalse(result["semantic_outcome_verified"])

    def test_forged_negative_status_does_not_trigger_fallback(self):
        self.write("conflict.json", '{"id":"A"}')
        self.write("valid.csv", "id\nA\n")
        methods=[
            {"kind":"goal_case","goal_type":"json_keys",
             "input":"conflict.json","desired":{"owner":"ops"}},
            {"kind":"goal_case","goal_type":"csv_columns",
             "input":"valid.csv","desired":{"owner":"ops"}},
        ]
        tid=self.seed(methods)
        self.tick()
        child=self.children(tid)[0]["task_id"]
        with closing(connect(self.db)) as db:
            db.execute(
                "UPDATE tasks SET state='UNKNOWN',error_code='NO_SAFE_GOAL_PLAN' "
                "WHERE task_id=?",(child,))
            db.commit()
        self.tick()
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_UNVERIFIABLE")
        self.assertEqual(len(self.children(tid)),1)

    def test_orphaned_attempt_refuses_duplicate_child_and_fences_running_work(self):
        tid=self.seed(self.structure_methods())
        self.tick()
        child=self.children(tid)[0]["task_id"]
        with closing(connect(self.db)) as db:
            db.execute("DELETE FROM evidence_feedback_attempts WHERE root_task_id=?",
                       (tid,))
            db.commit()
        self.tick()
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_UNVERIFIABLE")
        self.assertEqual(len(self.children(tid)),1)
        self.assertEqual(self.children(tid)[0]["task_id"],child)
        self.assertEqual(self.children(tid)[0]["state"],"BLOCKED")

    def test_default_host_does_not_advance_unopted_feedback(self):
        tid=self.seed(self.structure_methods())
        result=run_tick(self.db,self.work,self.fx,max_jobs=3)
        self.assertEqual(self.root(tid)["state"],"FEEDBACK_ACTIVE")
        self.assertEqual(self.children(tid),[])
        self.assertEqual(result["local_goal_control"],[])


if __name__=="__main__":
    unittest.main()
