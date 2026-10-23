"""P7: audited failure disposition, fair review queue, bounded evidence recovery."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize, create_task, alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.host import run_tick
from cognition_agent_os.sandbox_effect import stage_one, advance_due_reviews
from cognition_agent_os.diagnostics import (
    recover_due_unknowns, recover_one_unknown, reject_review_if_untrusted
)


class DiagnosisFairnessTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.dbpath=self.root/"state.sqlite"
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.work=self.root/"work";self.work.mkdir()
        db=connect(self.dbpath);initialize(db);db.close()

    def task(self,tid):
        db=connect(self.dbpath)
        try:
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
            return dict(row) if row else None
        finally:
            db.close()

    def events(self,tid,kind):
        db=connect(self.dbpath)
        try:
            return [dict(r) for r in db.execute(
                "SELECT * FROM events WHERE task_id=? AND kind=?",(tid,kind))]
        finally:
            db.close()

    def seed(self, filename, desired, *, kind="json_keys"):
        db=connect(self.dbpath)
        try:
            return create_task(db,{"kind":"goal_case","goal_type":kind,
                          "input":filename,"desired":desired})
        finally:
            db.close()

    def propose(self, filename, desired):
        tid=self.seed(filename,desired)
        output=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(output["status"],"NEEDS_REVIEW",output)
        return tid

    def test_malformed_oldest_diagnosed_once_other_work_not_starved(self):
        rejected=[]
        for n in range(9):
            fn=f"bad_{n}.json"
            (self.fx/fn).write_text("{}")
            tid=self.propose(fn,{"key":"val"})
            (self.work/"artifacts"/(tid+".json")).write_text("tampered")
            rejected.append(tid)
        (self.fx/"good.json").write_text("{}")
        good=self.propose("good.json",{"key":"val"})
        all_results=[]
        # At most two reviews per tick, even if the oldest proposals are bad.
        for _ in range(6):
            batch=advance_due_reviews(self.dbpath,self.work,self.fx,max_reviews=2)
            all_results.extend(batch)
        self.assertTrue(all(self.task(tid)["state"]=="UNKNOWN" for tid in rejected))
        self.assertTrue(all(len(self.events(tid,"DIAGNOSIS_RECORDED"))==1 for tid in rejected))
        self.assertEqual(self.task(good)["state"],"SANDBOX_VERIFIED")
        self.assertEqual(sum(1 for r in all_results if r["status"]=="SANDBOX_VERIFIED"),1)
        self.assertEqual(advance_due_reviews(self.dbpath,self.work,self.fx,max_reviews=2),[])

    def test_integrity_failure_creates_causal_uncertainty_record_not_false_repair(self):
        (self.fx/"conf.json").write_text('{"critical":"preserve"}')
        tid=self.propose("conf.json",{"missing":"x"})
        path=self.work/"artifacts"/(tid+".json")
        path.write_bytes(path.read_bytes()+b"corrupt")
        result=stage_one(self.dbpath,self.work,self.fx,tid)
        self.assertEqual(result["status"],"NOT_ADMITTED")
        self.assertEqual(result["diagnosis"],"UNTRUSTED_CANDIDATE")
        self.assertEqual(result["next_action"],"ISOLATE_REJECTED_CANDIDATE")
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        audit=self.events(tid,"DIAGNOSIS_RECORDED")
        self.assertEqual(len(audit),1)
        details=json.loads(audit[0]["details"])
        self.assertFalse(details["causal_root_proven"])
        self.assertEqual(len(details["candidate_explanations"]),2)
        self.assertFalse((self.work/"sandbox"/(tid+".candidate")).exists())
        self.assertEqual(stage_one(self.dbpath,self.work,self.fx,tid)["status"],"NOT_ADMITTED")
        self.assertEqual(len(self.events(tid,"DIAGNOSIS_RECORDED")),1)

    def test_stale_authority_gets_blocked_and_other_work_can_run(self):
        (self.fx/"old.json").write_text("{}")
        tid=self.propose("old.json",{"owner":"ops"})
        db=connect(self.dbpath);alter_authority(db,revoke=True);db.close()
        response=stage_one(self.dbpath,self.work,self.fx,tid)
        self.assertEqual(response["status"],"NOT_ADMITTED")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")
        self.assertEqual(response["next_action"],"STOP_UNTIL_EXPLICIT_REAUTHORIZATION")
        self.assertFalse((self.work/"sandbox"/(tid+".candidate")).exists())

    def test_missing_goal_input_recovers_into_new_task_when_evidence_arrives(self):
        tid=self.seed("later.json",{"owner":"ops"})
        first=run_once(self.dbpath,self.work,self.fx)
        self.assertEqual(first["status"],"UNKNOWN")
        self.assertEqual(self.task(tid)["error_code"],"GOAL_EVIDENCE_UNAVAILABLE")
        (self.fx/"later.json").write_text('{"critical":"keep"}')
        tick=run_tick(self.dbpath,self.work,self.fx,auto_stage_goals=True)
        self.assertEqual(tick["diagnostic_followups"][0]["status"],"REPLAN_QUEUED")
        child=tick["diagnostic_followups"][0]["next_task_id"]
        self.assertEqual(self.task(tid)["state"],"NEEDS_REPLAN")
        self.assertEqual(self.task(child)["parent_task"],tid)
        tick2=run_tick(self.dbpath,self.work,self.fx,auto_stage_goals=True)
        self.assertEqual(tick2["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(tick2["sandbox_reviews"][0]["status"],"SANDBOX_VERIFIED")
        self.assertEqual(self.task(child)["state"],"SANDBOX_VERIFIED")
        self.assertEqual((self.fx/"later.json").read_text(),'{"critical":"keep"}')
        record=json.loads(self.events(tid,"DIAGNOSIS_REPLAN")[0]["details"])
        self.assertFalse(record["causal_root_proven"])

    def test_csv_corrupt_then_repaired_recovers_and_stages_without_editing_source(self):
        source=self.fx/"report.csv"
        source.write_text("case,case\nA,10\n")
        tid=self.seed("report.csv",{"passed":"NOT_RUN"},kind="csv_columns")
        self.assertEqual(run_once(self.dbpath,self.work,self.fx)["status"],"UNKNOWN")
        source.write_text("case,cycles\nA,10\n")
        first=run_tick(self.dbpath,self.work,self.fx,auto_stage_goals=True)
        self.assertEqual(first["diagnostic_followups"][0]["status"],"REPLAN_QUEUED")
        child=first["diagnostic_followups"][0]["next_task_id"]
        second=run_tick(self.dbpath,self.work,self.fx,auto_stage_goals=True)
        self.assertEqual(second["sandbox_reviews"][0]["status"],"SANDBOX_VERIFIED")
        self.assertEqual(self.task(child)["state"],"SANDBOX_VERIFIED")
        self.assertEqual((self.work/"sandbox"/(child+".candidate")).read_text(),
                         "case,cycles,passed\nA,10,NOT_RUN\n")
        self.assertEqual(source.read_text(),"case,cycles\nA,10\n")

    def test_unavailable_input_poll_is_delayed_without_creating_fake_child(self):
        tid=self.seed("missing.csv",{"passed":"NO"},kind="csv_columns")
        self.assertEqual(run_once(self.dbpath,self.work,self.fx)["status"],"UNKNOWN")
        first=recover_due_unknowns(self.dbpath,self.fx)
        self.assertEqual(len(first),1)
        self.assertEqual(first[0]["status"],"EVIDENCE_PENDING")
        self.assertEqual(recover_due_unknowns(self.dbpath,self.fx),[])
        self.assertEqual(len(self.events(tid,"DIAGNOSIS_EVIDENCE_STILL_MISSING")),1)
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        self.assertIsNone(self.task(tid)["parent_task"])

    def test_recovered_data_conflicts_then_stop_without_false_action(self):
        tid=self.seed("later.json",{"owner":"ops"})
        run_once(self.dbpath,self.work,self.fx)
        (self.fx/"later.json").write_text('{"owner":"other"}')
        res=recover_due_unknowns(self.dbpath,self.fx)
        self.assertEqual(res[0]["status"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual(self.task(tid)["error_code"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual(recover_due_unknowns(self.dbpath,self.fx),[])
        self.assertFalse((self.work/"sandbox").exists())

    def test_revocation_during_wait_refuses_recovery_without_new_task(self):
        tid=self.seed("later.json",{"owner":"ops"})
        run_once(self.dbpath,self.work,self.fx)
        (self.fx/"later.json").write_text("{}")
        db=connect(self.dbpath);alter_authority(db,revoke=True);db.close()
        res=recover_due_unknowns(self.dbpath,self.fx)
        self.assertEqual(res[0]["status"],"BLOCKED")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")
        self.assertEqual(self.events(tid,"DIAGNOSIS_REPLAN"),[])

    def test_recovery_depth_cap_prevents_recursive_child_spam(self):
        spec={"kind":"goal_case","goal_type":"json_keys",
              "input":"now.json","desired":{"owner":"ops"}}
        (self.fx/"now.json").write_text("{}")
        db=connect(self.dbpath)
        root=create_task(db,spec)
        child=create_task(db,spec,parent=root)
        grandchild=create_task(db,spec,parent=child)
        db.execute("""UPDATE tasks SET state='UNKNOWN',
                error_code='GOAL_EVIDENCE_UNAVAILABLE' WHERE task_id=?""",(grandchild,))
        db.execute("UPDATE tasks SET state='NEEDS_REPLAN' WHERE task_id IN (?,?)",(root,child))
        db.commit();db.close()
        res=recover_one_unknown(self.dbpath,self.fx,grandchild)
        self.assertEqual(res["status"],"REPLAN_EXHAUSTED")
        self.assertEqual(self.task(grandchild)["error_code"],"REPLAN_BUDGET_EXHAUSTED")
        self.assertEqual(recover_due_unknowns(self.dbpath,self.fx),[])

    def test_stage_retry_cooldown_frees_one_slot_for_next_review(self):
        (self.fx/"first.json").write_text("{}")
        first=self.propose("first.json",{"owner":"ops"})
        sandbox=self.work/"sandbox";sandbox.mkdir()
        (sandbox/(first+".candidate")).write_text("CONFLICT")
        self.assertEqual(stage_one(self.dbpath,self.work,self.fx,first)["status"],"EFFECT_UNKNOWN")
        self.assertGreater(self.task(first)["due_at"],0)
        (self.fx/"second.json").write_text("{}")
        second=self.propose("second.json",{"owner":"ops"})
        batch=advance_due_reviews(self.dbpath,self.work,self.fx,max_reviews=1)
        self.assertEqual([r["task_id"] for r in batch],[second])
        self.assertEqual(batch[0]["status"],"SANDBOX_VERIFIED")
        self.assertEqual(self.task(first)["state"],"NEEDS_REVIEW")

    def test_non_goal_json_and_invalid_json_cannot_impersonate_goal(self):
        db=connect(self.dbpath)
        try:
            other=create_task(db,{"kind":"fixture","comment":"goal_case"})
            broken=create_task(db,{"kind":"fixture"})
            db.execute("UPDATE tasks SET state='NEEDS_REVIEW' WHERE task_id IN (?,?)",
                       (other,broken))
            db.execute("UPDATE tasks SET source_spec='not json' WHERE task_id=?",(broken,))
            db.commit()
        finally: db.close()
        (self.fx/"good.json").write_text("{}")
        good=self.propose("good.json",{"owner":"ops"})
        batch=advance_due_reviews(self.dbpath,self.work,self.fx,max_reviews=4)
        self.assertEqual([b["task_id"] for b in batch],[good])
        self.assertEqual(self.task(good)["state"],"SANDBOX_VERIFIED")

    def test_reject_race_does_not_close_freshly_restored_candidate(self):
        (self.fx/"conf.json").write_text("{}")
        tid=self.propose("conf.json",{"owner":"ops"})
        from cognition_agent_os import diagnostics as d
        with patch.object(d,"audit_goal",return_value={"status":"CANDIDATE_MECHANICALLY_VALID"}):
            response=reject_review_if_untrusted(self.dbpath,self.work,self.fx,tid)
        self.assertEqual(response["status"],"RECHECK_REQUIRED")
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")
        self.assertEqual(self.events(tid,"DIAGNOSIS_RECORDED"),[])

    def test_recover_after_restart_keeps_single_child(self):
        tid=self.seed("later.json",{"owner":"ops"})
        run_once(self.dbpath,self.work,self.fx)
        (self.fx/"later.json").write_text("{}")
        r1=recover_due_unknowns(self.dbpath,self.fx)
        r2=recover_due_unknowns(self.dbpath,self.fx)
        self.assertEqual(len(r1),1)
        self.assertEqual(r2,[])
        self.assertEqual(len(self.events(tid,"DIAGNOSIS_REPLAN")),1)


if __name__=="__main__":
    unittest.main()
