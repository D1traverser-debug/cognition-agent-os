"""Black-box integration for opt-in SQLite goal control and independent verdict.

No source mutation, external effects, extra grants, daemon or model API.
Tests exercise real Host/run_once across separate ticks and file evidence.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch
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




    def test_real_cli_requires_explicit_seed_and_opt_in(self):
        methods=self.methods()
        spec=self.root/"control.json"
        spec.write_text(json.dumps({"goal_id":"cli-record",
             "target":{"id":"A","owner":"ops"},"alternatives":methods}),
             encoding="utf-8")
        env=os.environ.copy()
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1]/"src")
        def cli(*parts,db=None):
            command=[sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(db or self.db),"--workspace",str(self.work),
                "--fixtures",str(self.fx),*parts]
            return subprocess.run(command,env=env,capture_output=True,
                                  text=True,encoding="utf-8",timeout=30)
        missing=self.root/"not-initialized.sqlite"
        refused=cli("seed-bounded-local-goal","--spec",str(spec),db=missing)
        self.assertEqual(refused.returncode,2,refused.stderr)
        self.assertFalse(missing.exists())
        seeded=cli("seed-bounded-local-goal","--spec",str(spec))
        self.assertEqual(seeded.returncode,0,seeded.stderr)
        root=json.loads(seeded.stdout)["task_id"]
        self.assertEqual(self.root_state(root)[0],"CONTROL_ACTIVE")
        disabled=cli("host-tick","--max-jobs","3")
        self.assertEqual(disabled.returncode,0,disabled.stderr)
        self.assertEqual(self.attempts(root),[])
        first=cli("host-tick","--max-jobs","3","--auto-local-goal-control")
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads(first.stdout)["local_goal_control"][0]["ordinal"],0)
        second=cli("host-tick","--max-jobs","3","--auto-local-goal-control")
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertEqual(json.loads(second.stdout)["local_goal_control"][0]["ordinal"],1)
        third=cli("host-tick","--max-jobs","3","--auto-local-goal-control")
        self.assertEqual(third.returncode,0,third.stderr)
        self.assertEqual(self.root_state(root)[0],"CONTROL_CANDIDATE_MATCHED")
        self.assertFalse(json.loads(third.stdout)["semantic_outcome_verified"])

    def test_narrow_csv_verified_is_not_owner_record_goal_success(self):
        # csv_columns verifies column EXISTENCE: existing 'owner' column
        # need not equal its default. The canonical-record oracle has
        # stronger owner-required semantics and must reject false closure.
        methods=self.methods(json_conflict=False,csv_conflict=True)
        root=register_local_goal(self.db,self.fx,goal_id="csv-first-owner",
                 target={"id":"A","owner":"ops"},alternatives=[methods[1],methods[0]])
        first=self.tick()
        self.assertEqual(first["local_goal_control"][0]["ordinal"],0,first)
        second=self.tick()
        self.assertEqual(second["tasks"][0]["status"],"VERIFIED",second)
        self.assertEqual(second["tasks"][0]["decision"],"GOAL_ALREADY_SATISFIED")
        self.assertEqual(second["local_goal_control"][0]["ordinal"],1,second)
        third=self.tick()
        self.assertEqual(self.root_state(root)[0],"CONTROL_CANDIDATE_MATCHED",third)
        self.assertEqual(third["tasks"][0]["status"],"NEEDS_REVIEW",third)
        from cognition_agent_os.bounded_control_audit import audit_controlled_candidate
        proof=audit_controlled_candidate(self.db,self.work,self.fx,root)
        self.assertEqual(proof["status"],"CONTROL_LOCAL_RECEIPT_VERIFIED",proof)
        self.assertFalse(proof["business_outcome_verified"])

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
        self.assertIn(root,[item["task_id"] for item in scan["quarantined"]],scan)
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
        self.assertIn(root,[item["task_id"] for item in scan["quarantined"]],scan)
        self.assertEqual(self.root_state(root)[0],"UNKNOWN")



    def test_registered_active_contract_mutation_never_admits_child(self):
        root=self.register()
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT source_spec FROM tasks WHERE task_id=?",(root,)).fetchone()
            modified=json.loads(row["source_spec"])
            modified["target"]["owner"]="forged"
            db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                       (json.dumps(modified,sort_keys=True),root))
            db.commit()
        result=self.tick(enabled=False)
        # The default conformance guardian must detect a corrupted ACTIVE
        # admission even without permission to advance the controller.
        self.assertEqual(self.root_state(root)[0],"UNKNOWN",result)
        self.assertTrue(self.root_state(root)[1].startswith(
            "CONFORMANCE_CONTROL_"),result)
        self.assertIn(root,[x["task_id"] for x in
                           result["conformance"]["quarantined"]],result)
        self.assertEqual(self.attempts(root),[])

    def test_corrupted_alternative_intake_is_blocked_before_child_creation(self):
        root=self.register()
        with closing(connect(self.db)) as db:
            row=db.execute("SELECT source_spec FROM tasks WHERE task_id=?",(root,)).fetchone()
            modified=json.loads(row["source_spec"])
            modified["alternatives"][0]["task_spec"]["desired"]["owner"]="forged"
            db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                       (json.dumps(modified,sort_keys=True),root))
            db.commit()
        result=self.tick(enabled=False)
        # The default conformance guardian must detect a corrupted ACTIVE
        # admission even without permission to advance the controller.
        self.assertEqual(self.root_state(root)[0],"UNKNOWN",result)
        self.assertTrue(self.root_state(root)[1].startswith(
            "CONFORMANCE_CONTROL_"),result)
        self.assertIn(root,[x["task_id"] for x in
                           result["conformance"]["quarantined"]],result)
        self.assertEqual(self.attempts(root),[])



    def test_waiting_roots_cannot_starve_new_actionable_root(self):
        # All three have valid independent registered goals. The first two
        # have pending children that the external worker has not finished;
        # repeatedly polling them must not exclude the third forever.
        roots=[self.register() for _ in range(3)]
        first=advance_local_goals(self.db,self.work,self.fx,limit=2)
        self.assertEqual(len(first),2,first)
        admitted=[len(self.attempts(x)) for x in roots]
        self.assertEqual(sum(admitted),2,admitted)
        # A fair allocator may choose by task ID rather than creation time.
        # The never-admitted root still must make progress after a few ticks.
        unadmitted=next(root for root,count in zip(roots,admitted) if count==0)
        for _ in range(3):
            advance_local_goals(self.db,self.work,self.fx,limit=2)
        self.assertEqual(len(self.attempts(unadmitted)),1,
                         "Repeatedly waiting roots starved an independent goal")


    def test_concurrent_fair_allocators_do_not_claim_same_queue_window(self):
        roots=[self.register() for _ in range(3)]
        # The cursor reservation is a DB transaction, not in-memory
        # round-robin state. Parallel hosts should admit three different
        # local children without duplicate effects.
        with ThreadPoolExecutor(max_workers=3) as pool:
            outcomes=list(pool.map(lambda _:advance_local_goals(
                self.db,self.work,self.fx,limit=1),range(3)))
        self.assertEqual([len(self.attempts(x)) for x in roots],[1,1,1],outcomes)
        self.assertEqual(sum(len(result) for result in outcomes),3,outcomes)

    def test_control_transition_directly_refuses_tampered_contract(self):
        root=self.register()
        with closing(connect(self.db)) as db:
            original=json.loads(db.execute(
                "SELECT source_spec FROM tasks WHERE task_id=?",(root,)
            ).fetchone()[0])
            original["target"]["owner"]="counterfeit"
            db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                       (json.dumps(original,sort_keys=True),root))
            db.commit()
        result=advance_local_goals(self.db,self.work,self.fx,limit=3)
        self.assertEqual(self.root_state(root),
                         ("CONTROL_UNVERIFIABLE","REGISTRATION_PROOF_INVALID"),result)
        self.assertEqual(self.attempts(root),[])

    def test_budget_stop_fences_pending_child_in_same_ledger(self):
        root=self.register()
        self.tick()
        child=self.attempts(root)[0]["child_task_id"]
        with closing(connect(self.db)) as db:
            state=db.execute("SELECT state FROM tasks WHERE task_id=?",
                             (child,)).fetchone()[0]
        self.assertEqual(state,"PENDING")
        with patch("cognition_agent_os.bounded_goal_control.time.time",
                   return_value=time.time()+90000):
            outcome=advance_local_goals(self.db,self.work,self.fx,limit=3)
        self.assertEqual(self.root_state(root),
                         ("CONTROL_STOPPED","LOCAL_CONTROL_TIME_BUDGET_EXHAUSTED"),outcome)
        with closing(connect(self.db)) as db:
            blocked=db.execute(
                "SELECT state,claim_token,lease_until FROM tasks WHERE task_id=?",
                (child,)).fetchone()
            self.assertEqual(blocked["state"],"BLOCKED")
            self.assertIsNone(blocked["claim_token"])
            self.assertIsNone(blocked["lease_until"])
        self.assertEqual(self.tick(enabled=False)["processed"],0)

    def test_forged_registration_event_is_detected_before_admission(self):
        root=self.register()
        with closing(connect(self.db)) as db:
            event_row=db.execute("""SELECT event_id,details FROM events
              WHERE task_id=? AND kind='BOUNDED_CONTROLLER_REGISTERED'""",
              (root,)).fetchone()
            forged=json.loads(event_row["details"])
            forged["contract_sha256"]="0"*64
            db.execute("UPDATE events SET details=? WHERE event_id=?",
                       (json.dumps(forged),event_row["event_id"]))
            db.commit()
        report=self.tick(enabled=False)
        self.assertEqual(self.root_state(root)[0],"UNKNOWN",report)
        self.assertEqual(self.attempts(root),[])

    def test_expired_active_goal_stops_without_admitting_more_work(self):
        root=self.register()
        # Advance only the wall clock. Altering created_at in SQLite would
        # be a forged registration timestamp and must independently fail.
        future=time.time()+90000
        with patch("cognition_agent_os.bounded_goal_control.time.time",
                   return_value=future):
            result=advance_local_goals(self.db,self.work,self.fx,limit=3)
        self.assertEqual(self.root_state(root),
                         ("CONTROL_STOPPED","LOCAL_CONTROL_TIME_BUDGET_EXHAUSTED"),result)
        self.assertEqual(self.attempts(root),[])


if __name__=="__main__":
    unittest.main()
