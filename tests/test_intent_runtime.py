"""P9 typed goal-plan admission, durable child integrity and cross-family outcomes."""
import json
import hashlib
import os
from pathlib import Path
from contextlib import closing
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,create_task,initialize,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.host import run_tick
from cognition_agent_os.intent_planner import compile_intent,IntentError
from cognition_agent_os.intent_runtime import audit_intent_plan

ROOT=Path(__file__).resolve().parents[1]


class IntentRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.fixtures=self.root/"fixtures";self.fixtures.mkdir()
        self.workspace=self.root/"workspace";self.workspace.mkdir()
        self.db_path=self.root/"state.sqlite"
        db=connect(self.db_path);initialize(db);db.close()

    def structured(self):
        return {"kind":"goal_intent","objective":"ensure_structure",
                "resources":[{"role":"input","path":"settings.json"}],
                "requirements":[{"field":"owner","equals":"ops"},
                                {"field":"retry","equals":3}]}

    def comparison(self):
        return {"kind":"goal_intent","objective":"compare_records",
                "resources":[{"role":"reference","path":"old.csv"},
                             {"role":"observed","path":"new.csv"}]}

    def seed(self,spec):
        db=connect(self.db_path)
        try:return create_task(db,spec)
        finally:db.close()

    def task(self,tid):
        db=connect(self.db_path)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:db.close()

    def test_invalid_intent_after_goal_rotation_must_report_blocked(self):
        from cognition_agent_os import intent_runtime
        tid=self.seed(self.structured())
        def rotate(*args,**kwargs):
            db=connect(self.db_path)
            try:alter_authority(db,goal_change=True)
            finally:db.close()
            raise IntentError("Injected malformed intent")
        with patch.object(intent_runtime,"compile_intent",side_effect=rotate):
            result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["reason"],"STALE_GOAL")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")

    def test_deep_descendant_cannot_run_when_root_is_invalid(self):
        """An intermediate DECOMPOSED task must not conceal a blocked root."""
        from cognition_agent_os.ledger import create_task
        for root_state in ("BLOCKED", "UNKNOWN"):
            with self.subTest(root_state=root_state):
                with closing(connect(self.db_path)) as db:
                    root = create_task(db, {"kind":"fixture",
                                            "old":"missing-a", "new":"missing-b"},
                                       due_at=9999999999)
                    middle = create_task(db, {"kind":"fixture",
                                              "old":"missing-c", "new":"missing-d"},
                                         parent=root, due_at=9999999999)
                    leaf = create_task(db, self.structured(), parent=middle)
                    db.execute("UPDATE tasks SET state=? WHERE task_id=?",
                               (root_state, root))
                    db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",
                               (middle,))
                    db.commit()
                result = run_once(self.db_path, self.workspace, self.fixtures)
                self.assertEqual(result["task_id"], leaf)
                self.assertEqual(result["status"], "BLOCKED", result)
                self.assertEqual(self.task(leaf)["error_code"],
                                 "UPSTREAM_TASK_INVALID")

    def test_closed_or_unrecognized_ancestor_never_authorizes_descendant(self):
        """A forbidden or corrupt parent state cannot silently fall through."""
        self.fixtures.joinpath("settings.json").write_text(
            '{"critical":"preserve"}', encoding="utf-8")
        invalid_states = (
            "UNRECOGNIZED_TERMINAL_STATE", "CONTROL_STOPPED",
            "CONTROL_UNVERIFIABLE", "FEEDBACK_STOPPED",
            "FEEDBACK_UNVERIFIABLE", "NEEDS_REPLAN",
            "PENDING", "RUNNING",
        )
        for root_state in invalid_states:
            with self.subTest(ancestor=root_state):
                with closing(connect(self.db_path)) as db:
                    root = create_task(db, self.structured(),
                                       due_at=9999999999)
                    intermediate = create_task(
                        db, self.structured(), parent=root,
                        due_at=9999999999)
                    leaf = create_task(
                        db, {"kind": "goal_case", "goal_type": "json_keys",
                             "input": "settings.json",
                             "desired": {"owner": "ops"}},
                        parent=intermediate)
                    db.execute("UPDATE tasks SET state=? WHERE task_id=?",
                               (root_state, root))
                    db.execute(
                        "UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",
                        (intermediate,))
                    db.commit()
                observed = run_once(self.db_path, self.workspace, self.fixtures)
                self.assertEqual(observed["task_id"], leaf, observed)
                self.assertEqual(observed["status"], "BLOCKED", observed)
                self.assertEqual(self.task(leaf)["error_code"],
                                 "UPSTREAM_TASK_INVALID")
                self.assertFalse((self.workspace / "artifacts" /
                                  (leaf + ".json")).exists())

    def test_valid_decomposed_ancestor_keeps_legitimate_descendants(self):
        """The new invalid-state guard must not block normal decomposition."""
        self.fixtures.joinpath("settings.json").write_text(
            '{"critical":"preserve"}', encoding="utf-8")
        with closing(connect(self.db_path)) as db:
            root = create_task(db, self.structured(),
                               due_at=9999999999)
            leaf = create_task(
                db, {"kind": "goal_case", "goal_type": "json_keys",
                     "input": "settings.json", "desired": {"owner": "ops"}},
                parent=root)
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",
                       (root,))
            db.commit()
        observed = run_once(self.db_path, self.workspace, self.fixtures)
        self.assertEqual(observed["task_id"], leaf)
        self.assertEqual(observed["status"], "NEEDS_REVIEW", observed)

    def test_replan_receipt_must_bind_exact_direct_child(self):
        """A real-looking replan event cannot authorize a different child."""
        from cognition_agent_os.ledger import event
        self.fixtures.joinpath("settings.json").write_text(
            '{"critical":"preserve"}', encoding="utf-8")
        for event_kind, id_field in (
                ("SANDBOX_REPLAN", "child_id"),
                ("DIAGNOSIS_REPLAN", "next_task_id")):
            with self.subTest(kind=event_kind):
                with closing(connect(self.db_path)) as db:
                    parent = create_task(db, self.structured(),
                                         due_at=9999999999)
                    unrelated = create_task(db, self.structured(),
                                             due_at=9999999999)
                    leaf = create_task(
                        db, {"kind": "goal_case", "goal_type": "json_keys",
                             "input": "settings.json",
                             "desired": {"owner": "ops"}},
                        parent=parent)
                    db.execute("UPDATE tasks SET state='NEEDS_REPLAN' "
                               "WHERE task_id=?", (parent,))
                    event(db, parent, event_kind, {id_field: unrelated})
                    db.commit()
                observed = run_once(self.db_path, self.workspace, self.fixtures)
                self.assertEqual(observed["task_id"], leaf)
                self.assertEqual(observed["status"], "BLOCKED", observed)
                self.assertEqual(self.task(leaf)["error_code"],
                                 "UPSTREAM_TASK_INVALID")
                self.assertFalse((self.workspace / "artifacts" /
                                  (leaf + ".json")).exists())

    def test_mid_execution_ancestor_revocation_blocks_actual_artifact_boundary(self):
        """A root can fail AFTER dispatch admission; writer must recheck ancestry."""
        from cognition_agent_os import runner
        from cognition_agent_os.ledger import create_task
        (self.fixtures/"before.txt").write_text("original")
        (self.fixtures/"after.txt").write_text("changed")
        with closing(connect(self.db_path)) as db:
            root = create_task(db, {"kind":"fixture","old":"before.txt",
                                    "new":"after.txt"}, due_at=9999999999)
            parent = create_task(db, {"kind":"fixture","old":"before.txt",
                                      "new":"after.txt"}, parent=root,
                                 due_at=9999999999)
            leaf = create_task(db, {"kind":"fixture","old":"before.txt",
                                    "new":"after.txt"}, parent=parent)
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id IN (?,?)",
                       (root,parent))
            db.commit()
        actual = runner.get_pair
        reads = 0

        def interrupt(spec, fixtures):
            nonlocal reads
            observed = actual(spec, fixtures)
            reads += 1
            if reads == 2:
                with closing(connect(self.db_path)) as db:
                    db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",
                               (root,))
                    db.commit()
            return observed

        with patch.object(runner, "get_pair", side_effect=interrupt):
            result = run_once(self.db_path, self.workspace, self.fixtures)
        self.assertEqual(reads,2)
        self.assertEqual(result["task_id"],leaf)
        self.assertEqual(result["status"],"BLOCKED",result)
        self.assertEqual(result["reason"],"UPSTREAM_TASK_INVALID")
        self.assertFalse((self.workspace/"artifacts"/(leaf+".json")).exists())

    def test_blocked_ancestor_prevents_late_sandbox_effect(self):
        """A review-stage write needs the same live ancestor gate as the worker."""
        from cognition_agent_os.sandbox_effect import stage_one
        self.fixtures.joinpath("settings.json").write_text(
            '{"critical":"preserve"}', encoding="utf-8")
        with closing(connect(self.db_path)) as db:
            root = create_task(db, self.structured(), due_at=9999999999)
            leaf = create_task(
                db, {"kind": "goal_case", "goal_type": "json_keys",
                     "input": "settings.json", "desired": {"owner": "ops"}},
                parent=root)
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",
                       (root,))
            db.commit()
        self.assertEqual(run_once(self.db_path, self.workspace, self.fixtures)["status"],
                         "NEEDS_REVIEW")
        self.assertEqual(self.task(leaf)["state"], "NEEDS_REVIEW")
        with closing(connect(self.db_path)) as db:
            db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",
                       (root,))
            db.commit()
        from cognition_agent_os.goal_audit import audit_goal
        audited = audit_goal(self.db_path, self.workspace, self.fixtures, leaf)
        self.assertEqual(audited["status"], "UPSTREAM_TASK_INVALID", audited)
        observed = stage_one(self.db_path, self.workspace, self.fixtures, leaf)
        self.assertNotEqual(observed["status"], "SANDBOX_VERIFIED", observed)
        self.assertFalse((self.workspace / "sandbox" /
                          (leaf + ".candidate")).exists())
        self.assertNotEqual(self.task(leaf)["state"], "SANDBOX_VERIFIED")

    def test_task_parent_cycle_is_not_a_legitimate_decomposition(self):
        """A corrupted parent graph cannot supply authorization or effects."""
        from cognition_agent_os.ledger import create_task
        with closing(connect(self.db_path)) as db:
            first = create_task(db, self.structured())
            second = create_task(db, self.structured(), parent=first,
                                 due_at=9999999999)
            db.execute("UPDATE tasks SET parent_task=? WHERE task_id=?",
                       (second, first))
            db.commit()
        result = run_once(self.db_path, self.workspace, self.fixtures)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertEqual(self.task(first)["error_code"], "UPSTREAM_TASK_INVALID")

    def test_unknown_capability_cannot_fall_through_to_snapshot_executor(self):
        """Free-text or malformed task kinds never become executable plugins."""
        tid = self.seed({"kind": "run_arbitrary_tool", "old": "x", "new": "y",
                         "module": "os", "command": "untrusted"})
        observed = run_once(self.db_path, self.workspace, self.fixtures)
        self.assertEqual(observed["status"], "UNKNOWN", observed)
        self.assertEqual(self.task(tid)["error_code"], "INVALID_TASK_SPEC")
        self.assertFalse((self.workspace / "artifacts" / (tid + ".json")).exists())

    def test_registered_capability_dispatch_uses_same_ledger_and_cold_resume(self):
        """No new task DB, goal authority or runner is introduced by adapters."""
        from cognition_agent_os.continuity import register_goal, resume_goal
        self.fixtures.joinpath("settings.json").write_text(
            '{"critical":"preserve"}', encoding="utf-8")
        tid = self.seed(self.structured())
        contract = {
            "goal_id": "single_spine",
            "objective": "Maintain valid user goal across sessions",
            "acceptance": "Independent outcome confirmation still required",
            "constraints": ["No unauthorized remote effects"],
            "next_task_id": tid,
            "source": None,
        }
        register_goal(self.db_path, contract)
        resumed = resume_goal(self.db_path)
        self.assertEqual(resumed["status"], "READY_TO_TICK", resumed)
        self.assertEqual(resumed["next_task_id"], tid)
        tick = run_tick(self.db_path, self.workspace, self.fixtures,
                        max_jobs=2)
        self.assertEqual(tick["tasks"][0]["status"], "DECOMPOSED", tick)
        self.assertFalse(tick["semantic_outcome_verified"])
        self.assertFalse(resume_goal(self.db_path)["business_outcome_verified"])

    def test_blocked_upstream_prevents_cross_capability_child_execution(self):
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        for intent in (self.structured(),self.comparison()):
            parent=self.seed(intent)
            admitted=run_once(self.db_path,self.workspace,self.fixtures)
            self.assertEqual(admitted["status"],"DECOMPOSED",admitted)
            child=admitted["child_task_id"]
            with closing(connect(self.db_path)) as db:
                db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",(parent,))
                db.commit()
            observed=run_once(self.db_path,self.workspace,self.fixtures)
            self.assertEqual(observed["task_id"],child,observed)
            self.assertEqual(observed["status"],"BLOCKED",observed)
            self.assertEqual(self.task(child)["error_code"],"UPSTREAM_TASK_INVALID")
            self.assertFalse((self.workspace/"artifacts"/(child+".json")).exists())

    def test_independent_audit_failure_changes_goal_control_decision(self):
        from cognition_agent_os.host import _goal_progress
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        root=self.seed(self.structured())
        tick=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        child=tick["tasks"][0]["child_task_id"]
        before=_goal_progress(self.db_path,self.workspace,self.fixtures)
        goal=next(g for g in before["goals"] if g["root_task_id"]==root)
        self.assertEqual(goal["failed_independent_checks"],0)
        artifact=self.workspace/"artifacts"/(child+".json")
        artifact.write_bytes(artifact.read_bytes()+b" ")
        after=_goal_progress(self.db_path,self.workspace,self.fixtures)
        goal=next(g for g in after["goals"] if g["root_task_id"]==root)
        self.assertEqual(goal["failed_independent_checks"],1)
        self.assertEqual(goal["next_control_action"],"REPLAN_AFTER_FAILED_INDEPENDENT_CHECK")
        self.assertFalse(goal["semantic_outcome_verified"])

    def test_host_automatically_reexecutes_failed_local_artifact_once(self):
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        root=self.seed(self.structured())
        first=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        original=first["tasks"][0]["child_task_id"]
        artifact=self.workspace/"artifacts"/(original+".json")
        artifact.write_bytes(artifact.read_bytes()+b" ")
        retry_tick=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(len(retry_tick["local_evidence_retries"]),1)
        retry=retry_tick["local_evidence_retries"][0]["retry_root_id"]
        self.assertNotEqual(retry,root)
        self.assertEqual(self.task(retry)["state"],"PENDING")
        third=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(third["tasks"][0]["task_id"],retry)
        self.assertEqual(third["tasks"][0]["status"],"DECOMPOSED")
        new_child=third["tasks"][0]["child_task_id"]
        fourth=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(fourth["tasks"][0]["task_id"],new_child)
        self.assertEqual(fourth["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(fourth["local_evidence_retries"],[])
        self.assertTrue((self.workspace/"artifacts"/(new_child+".json")).is_file())
        self.assertFalse(fourth["semantic_outcome_verified"])

    def test_same_bounded_recovery_works_for_csv_reconciliation(self):
        self.fixtures.joinpath("old.csv").write_text("invoice_id,amount\nI1,100\nI2,20\n")
        self.fixtures.joinpath("new.csv").write_text("invoice_id,amount\nI1,80\nI2,20\n")
        self.seed(self.comparison())
        first=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        original=first["tasks"][0]["child_task_id"]
        artifact=self.workspace/"artifacts"/(original+".json")
        self.assertTrue(artifact.is_file())
        artifact.write_bytes(artifact.read_bytes()+b" ")
        second=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(len(second["local_evidence_retries"]),1)
        root=second["local_evidence_retries"][0]["retry_root_id"]
        third=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(third["tasks"][0]["task_id"],root)
        self.assertEqual(third["tasks"][0]["status"],"DECOMPOSED")
        new_child=third["tasks"][0]["child_task_id"]
        fourth=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(fourth["tasks"][0]["task_id"],new_child)
        self.assertEqual(fourth["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(fourth["local_evidence_retries"],[])
        self.assertFalse(fourth["semantic_outcome_verified"])

    def test_source_drift_is_not_blindly_retried(self):
        self.fixtures.joinpath("old.csv").write_text("invoice_id,amount\nI1,100\n")
        self.fixtures.joinpath("new.csv").write_text("invoice_id,amount\nI1,90\n")
        self.seed(self.comparison())
        first=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        self.assertEqual(first["tasks"][1]["status"],"NEEDS_REVIEW")
        self.fixtures.joinpath("new.csv").write_text("invoice_id,amount\nI1,70\n")
        second=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(second["local_evidence_retries"],[])

    def test_changed_audit_verdict_at_commit_refuses_retry(self):
        from cognition_agent_os import local_retry
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        self.seed(self.structured())
        first=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        original=first["tasks"][0]["child_task_id"]
        artifact=self.workspace/"artifacts"/(original+".json")
        artifact.write_bytes(artifact.read_bytes()+b" ")
        original_audit=local_retry.audit_goal
        observations=[0]
        def source_changed_between_checks(*args,**kwargs):
            observations[0]+=1
            if observations[0]==2:
                return {"status":"SOURCE_CHANGED_SINCE_PROPOSAL"}
            return original_audit(*args,**kwargs)
        with patch.object(local_retry,"audit_goal",side_effect=source_changed_between_checks):
            result=local_retry.schedule_failed_local_evidence(
                self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result,[])
        self.assertEqual(observations[0],2)
        with closing(connect(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events WHERE kind='BOUNDED_LOCAL_RETRY'").fetchone()[0],0)

    def test_revoke_prevents_failed_local_artifact_retry(self):
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        self.seed(self.structured())
        first=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        original=first["tasks"][0]["child_task_id"]
        artifact=self.workspace/"artifacts"/(original+".json")
        artifact.write_bytes(artifact.read_bytes()+b" ")
        with closing(connect(self.db_path)) as db:
            alter_authority(db,revoke=True)
        tick=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(tick["local_evidence_retries"],[])

    def test_goal_feedback_independently_checks_structure_before_sandbox_promotion(self):
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        self.seed(self.structured())
        tick=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=2)
        checks=[c for g in tick["goal_progress"]["goals"]
                for c in g["independent_checks"]]
        self.assertTrue(any(c["capability"]=="goal_case" and
                            c["mechanically_verified"] for c in checks),checks)
        self.assertTrue(all(not c["business_outcome_verified"] for c in checks))

    def test_json_intent_generates_child_and_actual_sandbox(self):
        self.fixtures.joinpath("settings.json").write_text('{"critical":"keep"}')
        tid=self.seed(self.structured())
        tick=run_tick(self.db_path,self.workspace,self.fixtures,auto_stage_goals=True)
        self.assertEqual(tick["tasks"][0]["status"],"DECOMPOSED")
        self.assertEqual(tick["tasks"][1]["status"],"NEEDS_REVIEW")
        cid=tick["tasks"][0]["child_task_id"]
        self.assertEqual(self.task(tid)["state"],"DECOMPOSED")
        self.assertEqual(self.task(cid)["parent_task"],tid)
        self.assertEqual(self.task(cid)["state"],"SANDBOX_VERIFIED")
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        actual=json.loads((self.workspace/"sandbox"/(cid+".candidate")).read_text())
        self.assertEqual(actual,{"critical":"keep","owner":"ops","retry":3})
        self.assertEqual(self.fixtures.joinpath("settings.json").read_text(),'{"critical":"keep"}')
        self.assertFalse(tick["semantic_outcome_verified"])

    def test_comparison_intent_generates_full_sql_verifiable_report(self):
        self.fixtures.joinpath("old.csv").write_text("invoice_id,amount\nI1,100\nI2,200\n")
        self.fixtures.joinpath("new.csv").write_text("invoice_id,amount\nI1,101\nI2,200\n")
        tid=self.seed(self.comparison())
        first=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(first["status"],"DECOMPOSED")
        child=first["child_task_id"]
        second=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(second["status"],"NEEDS_REVIEW")
        self.assertEqual(second["selected_key"],"invoice_id")
        self.assertEqual(second["discrepancies_count"],1)
        from cognition_agent_os.reconciliation_oracle import audit_stored_report
        self.assertEqual(audit_stored_report(self.db_path,self.workspace,self.fixtures,child)["status"],
                         "REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        self.assertEqual(self.task(child)["state"],"NEEDS_REVIEW")
        progress=run_tick(self.db_path,self.workspace,self.fixtures,max_jobs=1)["goal_progress"]
        self.assertTrue(any(c["capability"]=="record_reconciliation" and c["mechanically_verified"] for g in progress["goals"] for c in g["independent_checks"]))

    def test_composed_comparison_uses_reviewer_pinned_key_and_sql(self):
        self.fixtures.joinpath("old.csv").write_text(
            "primary_id,alternate_id,amount\nA,Z,100\nB,Y,200\n")
        self.fixtures.joinpath("new.csv").write_text(
            "primary_id,alternate_id,amount\nA,Z,101\nB,Y,200\n")
        manifest={
            "schema_version":1,"contract_kind":"record_relationship",
            "reference":"old.csv","observed":"new.csv",
            "join_key":"primary_id",
            "justification":"Independently reviewed primary record identifier association."
        }
        raw=(json.dumps(manifest,sort_keys=True)+"\n").encode()
        self.fixtures.joinpath("linkage.json").write_bytes(raw)
        intent={**self.comparison(),"relationship_contract":{
            "path":"linkage.json","expected_sha256":hashlib.sha256(raw).hexdigest()}}
        tid=self.seed(intent)
        first=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(first["status"],"DECOMPOSED")
        child=first["child_task_id"]
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        self.assertEqual(result["selected_key"],"primary_id")
        from cognition_agent_os.reconciliation_oracle import audit_stored_report
        self.assertEqual(
            audit_stored_report(self.db_path,self.workspace,self.fixtures,child)["status"],
            "REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual(self.task(child)["state"],"NEEDS_REVIEW")

    def test_composed_intent_rejects_self_claimed_trust_without_digest(self):
        bad={**self.comparison(),"relationship_contract":{
            "path":"linkage.json","key":"primary_id"}}
        with self.assertRaises(IntentError):
            compile_intent(bad)

    def test_unknown_intent_never_executes_and_never_creates_child(self):
        spec={**self.comparison(),"objective":"execute_shell"}
        with self.assertRaises(IntentError):
            compile_intent(spec)
        tid=self.seed(spec)
        result=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"INTENT_NOT_ADMITTED")
        self.assertFalse((self.workspace/"artifacts").exists())
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"UNVERIFIABLE")

    def test_duplicate_roles_and_untrusted_extensions_rejected(self):
        for bad in [
            {**self.comparison(),"resources":[{"role":"reference","path":"a.csv"},
                                            {"role":"reference","path":"b.csv"}]},
            {**self.structured(),"permissions":"allow_any_shell"},
            {**self.structured(),"requirements":[{"field":"owner","equals":"a"},
                                                {"field":"owner","equals":"b"}]},
            {**self.comparison(),"resources":[{"role":"reference","path":"../etc/passwd"},
                                            {"role":"observed","path":"new.csv"}]},
            {**self.structured(),"requirements":[{"field":"bad field","equals":"x"}]},
            {**self.structured(),"requirements":[{"field":"allowed","equals":["run shell"]}]},
            {**self.structured(),"resources":[{"role":"input","path":":/absolute"}]},
            {**self.comparison(),"requirements":[]}
        ]:
            with self.subTest(value=bad),self.assertRaises(IntentError):
                compile_intent(bad)

    def test_authority_revoked_after_goal_enqueued_blocks_decomposition(self):
        tid=self.seed(self.structured())
        db=connect(self.db_path);alter_authority(db,revoke=True);db.close()
        outcome=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(outcome["status"],"BLOCKED")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")
        db=connect(self.db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],1)
        db.close()

    def test_goal_revision_invalidates_plan(self):
        tid=self.seed(self.comparison())
        db=connect(self.db_path);alter_authority(db,goal_change=True);db.close()
        outcome=run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(outcome["status"],"BLOCKED")
        self.assertEqual(self.task(tid)["state"],"BLOCKED")

    def test_no_nested_intents_even_under_claim(self):
        parent=self.seed(self.structured())
        db=connect(self.db_path)
        child=create_task(db,self.comparison(),parent=parent)
        db.execute("UPDATE tasks SET state='UNKNOWN' WHERE task_id=?",(parent,))
        db.commit();db.close()
        result=run_once(self.db_path,self.workspace,self.fixtures)
        # Upstream failure is an earlier, stricter invariant than recursive
        # intent admission. The descendant must never reach an adapter.
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["reason"],"UPSTREAM_TASK_INVALID")
        self.assertEqual(self.task(child)["state"],"BLOCKED")

    def test_nested_intent_still_refused_when_ancestor_is_decomposed(self):
        from cognition_agent_os.ledger import create_task
        parent = self.seed(self.structured())
        with closing(connect(self.db_path)) as db:
            child = create_task(db, self.comparison(), parent=parent)
            # PENDING is not an admitted lineage; test the recursion rule
            # with an already-decomposed ancestor instead of invalid setup.
            db.execute("UPDATE tasks SET state='DECOMPOSED', due_at=? WHERE task_id=?",
                       (9999999999, parent))
            db.commit()
        result = run_once(self.db_path,self.workspace,self.fixtures)
        self.assertEqual(result["task_id"],child)
        self.assertEqual(result["status"],"UNKNOWN",result)
        self.assertEqual(result["reason"],"INTENT_RECURSION_REFUSED")

    def test_plan_receipt_falsification_cannot_forge_validity(self):
        tid=self.seed(self.structured())
        self.assertEqual(run_once(self.db_path,self.workspace,self.fixtures)["status"],"DECOMPOSED")
        self.assertEqual(audit_intent_plan(self.db_path,tid)["status"],"PLAN_MECHANICALLY_VALID")
        db=connect(self.db_path)
        child=db.execute("SELECT task_id FROM tasks WHERE parent_task=?",(tid,)).fetchone()[0]
        db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                   (json.dumps({"kind":"fixture","old":"x","new":"y"}),child))
        db.commit();db.close()
        self.assertEqual(audit_intent_plan(self.db_path,tid)["reason"],
                         "CHILD_TASK_IDENTITY_MISMATCH")

    def test_cli_seeds_one_intent_and_audits_without_second_db(self):
        spec=self.structured()
        manifest=self.root/"intent.json"
        manifest.write_text(json.dumps(spec))
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        common=[sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(self.db_path),"--workspace",str(self.workspace),
                "--fixtures",str(self.fixtures)]
        def cli(args):
            return subprocess.run(common+args,env=env,capture_output=True,text=True,timeout=12)
        first=cli(["seed-intent","--spec",str(manifest)])
        self.assertEqual(first.returncode,0,first.stderr)
        tid=json.loads(first.stdout)["task_id"]
        self.assertEqual(cli(["worker-once"]).returncode,0)
        checked=cli(["intent-audit","--task-id",tid])
        self.assertEqual(checked.returncode,0,checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["status"],"PLAN_MECHANICALLY_VALID")
        d=connect(self.db_path)
        self.assertEqual(d.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],2)
        d.close()


if __name__=="__main__":
    unittest.main()
