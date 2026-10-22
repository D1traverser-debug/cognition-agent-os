"""Black-box integration for opt-in SQLite goal control and independent verdict.

No source mutation, external effects, extra grants, daemon or model API.
Tests exercise real Host/run_once across separate ticks and file evidence.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.bounded_goal_control import (
    advance_local_goals, register_local_goal)
from cognition_agent_os.bounded_outcome_oracle import assess_local_record
from cognition_agent_os.bounded_control_audit import audit_controlled_candidate
from cognition_agent_os.conformance import inspect_conformance
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect,initialize,alter_authority


class DurableSameGoalControllerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.work=self.root/"workspace";self.work.mkdir()
        self.db=self.root/"ledger.sqlite"
        with closing(connect(self.db)) as db:
            initialize(db)

    def methods(self, *, json_conflict=True,csv_conflict=False):
        self.fx.joinpath("first.json").write_text(
            '{"id":"A","owner":"wrong"}' if json_conflict else '{"id":"A"}',
            encoding="utf-8")
        self.fx.joinpath("second.csv").write_text(
            "id,owner\nA,wrong\n" if csv_conflict else "id\nA\n",
            encoding="utf-8")
        return [
            {"kind":"goal_case","goal_type":"json_keys","input":"first.json",
             "desired":{"owner":"ops"}},
            {"kind":"goal_case","goal_type":"csv_columns","input":"second.csv",
             "desired":{"owner":"ops"}}]

    def register(self, *,json_conflict=True,csv_conflict=False,target=None):
        return register_local_goal(
            self.db,self.fx,goal_id="owner-record",
            target=target or {"id":"A","owner":"ops"},
            alternatives=self.methods(json_conflict=json_conflict,csv_conflict=csv_conflict))

    def tick(self, *,enabled=True):
        return run_tick(self.db,self.work,self.fx,max_jobs=3,
                        auto_local_goal_control=enabled)

    def attempts(self,root):
        with closing(connect(self.db)) as db:
            return [dict(x) for x in db.execute(
                "SELECT * FROM bounded_goal_attempts WHERE root_task_id=? ORDER BY ordinal",
                (root,)).fetchall()]

    def root_state(self,root):
        with closing(connect(self.db)) as db:
            r=db.execute("SELECT state,error_code FROM tasks WHERE task_id=?",(root,)).fetchone()
            return r["state"],r["error_code"]

    def test_conflict_drives_alternative_then_independent_local_goal(self):
        root=self.register()
        old_json=self.fx.joinpath("first.json").read_bytes()
        old_csv=self.fx.joinpath("second.csv").read_bytes()
        before=self.tick(enabled=False)
        self.assertEqual(before["processed"],0,before)
        self.assertEqual(self.attempts(root),[])
        first=self.tick()
        self.assertEqual([x["ordinal"] for x in first["local_goal_control"]],[0],first)
        self.assertEqual(len(self.attempts(root)),1)
        second=self.tick()
        self.assertEqual(second["tasks"][0]["status"],"UNKNOWN",second)
        self.assertEqual(second["tasks"][0]["reason"],"NO_SAFE_GOAL_PLAN")
        self.assertEqual([x["ordinal"] for x in second["local_goal_control"]],[1],second)
        self.assertEqual(len(self.attempts(root)),2)
        third=self.tick()
        self.assertEqual(third["tasks"][0]["status"],"NEEDS_REVIEW",third)
        self.assertEqual(third["local_goal_control"][0]["status"],
                         "CONTROL_CANDIDATE_MATCHED",third)
        self.assertEqual(self.root_state(root),
                         ("CONTROL_CANDIDATE_MATCHED","PINNED_LOCAL_POSTCONDITION"))
        self.assertFalse(third["semantic_outcome_verified"])
        self.assertFalse(third["local_goal_control"][0]["business_outcome_verified"])
        self.assertEqual(self.fx.joinpath("first.json").read_bytes(),old_json)
        self.assertEqual(self.fx.joinpath("second.csv").read_bytes(),old_csv)
        again=self.tick()
        self.assertEqual(again["processed"],0,again)
        self.assertEqual(len(self.attempts(root)),2)

    def test_nonconflict_candidate_needs_no_second_attempt(self):
        root=self.register(json_conflict=False)
        self.tick()
        second=self.tick()
        self.assertEqual(second["local_goal_control"][0]["status"],
                         "CONTROL_CANDIDATE_MATCHED",second)
        self.assertEqual(len(self.attempts(root)),1)

    def test_two_conflicts_stop_after_finite_budget_even_if_worker_false_noop(self):
        root=self.register(csv_conflict=True)
        self.tick()
        self.tick()
        final=self.tick()
        self.assertEqual(self.root_state(root),
                         ("CONTROL_STOPPED","EXHAUSTED_SAFE_ALTERNATIVES"),final)
        self.assertEqual(len(self.attempts(root)),2)
        self.assertFalse(final["semantic_outcome_verified"])

    def test_revocation_fences_new_alternative(self):
        root=self.register()
        self.tick()
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        after=self.tick()
        self.assertEqual(self.root_state(root),
                         ("CONTROL_STOPPED","WRITE_GRANT_REVOKED"),after)
        self.assertEqual(len(self.attempts(root)),1)

    def test_goal_change_fences_new_alternative(self):
        root=self.register()
        self.tick()
        with closing(connect(self.db)) as db:
            alter_authority(db,goal_change=True)
        after=self.tick()
        self.assertEqual(self.root_state(root),("CONTROL_STOPPED","STALE_GOAL"),after)
        self.assertEqual(len(self.attempts(root)),1)

    def test_source_drift_blocks_action_and_disables_switch(self):
        root=self.register()
        self.fx.joinpath("first.json").write_text('{"id":"B"}',encoding="utf-8")
        report=self.tick()
        self.assertEqual(self.root_state(root),
                         ("CONTROL_UNVERIFIABLE","SOURCE_CHANGED"),report)
        self.assertEqual(len(self.attempts(root)),0)

    def test_independent_oracle_error_does_not_switch(self):
        root=self.register(json_conflict=False)
        self.tick()
        child=self.attempts(root)[0]["child_task_id"]
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",(child,)).fetchone()
            self.assertEqual(row["state"],"PENDING")
        worker=self.tick(enabled=False)
        self.assertEqual(worker["tasks"][0]["status"],"NEEDS_REVIEW",worker)
        # Corrupt an actual proposed artifact after worker finalized; the
        # independent check must reject, NOT reinterpret this as an allowed
        # source-preservation conflict.
        artifact=self.work/"artifacts"/(child+".json")
        artifact.write_bytes(artifact.read_bytes()+b" tamper")
        stopped=self.tick()
        self.assertEqual(self.root_state(root)[0],"CONTROL_UNVERIFIABLE",stopped)
        self.assertEqual(len(self.attempts(root)),1)

    def test_registration_rejects_mismatched_target_or_duplicate_method(self):
        methods=self.methods()
        with self.assertRaises(ValueError):
            register_local_goal(self.db,self.fx,goal_id="owner-record",
                                target={"id":"B","owner":"ops"},alternatives=methods)
        with self.assertRaises(ValueError):
            register_local_goal(self.db,self.fx,goal_id="owner-record",
                                target={"id":"A","owner":"ops"},
                                alternatives=[methods[0],methods[0]])
        # Both registrations failed before the optional table existed.
        # Assert the actual authoritative ledger remains unchanged.
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],0)

    def test_independent_observation_does_not_use_planner_verdict(self):
        raw=b'{"id":"A","owner":"wrong"}'
        sha=hashlib.sha256(raw).hexdigest()
        verdict=assess_local_record(kind="json_keys",original=raw,
             current_sha256=sha,pinned_sha256=sha,
             target={"id":"A","owner":"ops"},candidate=None)
        self.assertEqual(verdict["verdict"],"PRESERVATION_CONFLICT")
        self.assertFalse(verdict["business_outcome_verified"])
        self.assertEqual(assess_local_record(
             kind="json_keys",original=raw,current_sha256=sha,
             pinned_sha256="0"*64,target={"id":"A","owner":"ops"},
             candidate=None)["verdict"],"UNVERIFIABLE")

    def test_two_workers_admit_only_one_first_child(self):
        root=self.register()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:advance_local_goals(
                self.db,self.work,self.fx,limit=1),range(2)))
        self.assertEqual(len(self.attempts(root)),1,results)
        self.assertEqual(sum(len(x) for x in results),1,results)

    def test_different_goal_instance_same_controller_no_domain_branch(self):
        methods=self.methods()
        self.fx.joinpath("first.json").write_text('{"ticket":"T01","owner":"wrong"}')
        self.fx.joinpath("second.csv").write_text("ticket\nT01\n")
        root=register_local_goal(self.db,self.fx,goal_id="ticket-record",
                 target={"ticket":"T01","owner":"ops"},alternatives=methods)
        self.tick();self.tick();self.tick()
        self.assertEqual(self.root_state(root)[0],"CONTROL_CANDIDATE_MATCHED")


    def test_independent_controller_receipt_and_conformance_scan(self):
        root=self.register()
        self.tick();self.tick();self.tick()
        proof=audit_controlled_candidate(self.db,self.work,self.fx,root)
        self.assertEqual(proof["status"],"CONTROL_LOCAL_RECEIPT_VERIFIED",proof)
        self.assertEqual(proof["attempts"],2,proof)
        self.assertFalse(proof["business_outcome_verified"])
        scan=inspect_conformance(self.db,self.work,self.fx,enforce=False,max_cases=64)
        matches=[f for f in scan["findings"] if f["task_id"]==root]
        self.assertEqual(len(matches),1,scan)
        self.assertEqual(matches[0]["proof"],"MECHANICALLY_VALID",matches)

    def test_forged_controller_receipt_detected_and_quarantined(self):
        root=self.register()
        self.tick();self.tick();self.tick()
        with closing(connect(self.db)) as db:
            r=db.execute("""SELECT event_id,details FROM events WHERE task_id=?
                    AND kind='BOUNDED_CONTROLLER_DECIDED'""",(root,)).fetchone()
            forged=json.loads(r["details"])
            forged["candidate_sha256"]="0"*64
            db.execute("UPDATE events SET details=? WHERE event_id=?",
                       (json.dumps(forged),r["event_id"]))
            db.commit()
        bad=audit_controlled_candidate(self.db,self.work,self.fx,root)
        self.assertEqual(bad["reason"],"FINAL_POSTCONDITION_MISMATCH",bad)
        scan=inspect_conformance(self.db,self.work,self.fx,enforce=True,max_cases=64)
        self.assertIn(root,scan["quarantined"],scan)
        self.assertEqual(self.root_state(root)[0],"UNKNOWN")

    def test_corrupted_artifact_after_positive_claim_rejected(self):
        root=self.register(json_conflict=False)
        self.tick();self.tick()
        child=self.attempts(root)[0]["child_task_id"]
        artifact=self.work/"artifacts"/(child+".json")
        artifact.write_bytes(artifact.read_bytes()+b" malicious")
        proof=audit_controlled_candidate(self.db,self.work,self.fx,root)
        self.assertEqual(proof["reason"],"CHILD_ARTIFACT_REJECTED",proof)
        scan=inspect_conformance(self.db,self.work,self.fx,enforce=True,max_cases=64)
        self.assertIn(root,scan["quarantined"],scan)
        self.assertEqual(self.root_state(root)[0],"UNKNOWN")



if __name__=="__main__":
    unittest.main()
