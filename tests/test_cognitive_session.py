"""Behavioral probes: real SQLite, source drift, concurrent edits and Worker effects.

Policy fixtures are explicit operator contracts, NOT an NLP accuracy benchmark.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.cognitive_session import (
    inspect_session, record_node, amend_goal, reopen_node)
from cognition_agent_os.effect_contract import (
    enable_managed_session, install_contract, inspect_contract_outcome)
from cognition_agent_os.intent_planner import compile_intent
from cognition_agent_os.ledger import connect, create_task, alter_authority, event, current_guard
from cognition_agent_os.method_learning import record_trial, inspect_trials
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision)
from cognition_agent_os.runner import run_once
from cognition_agent_os.session_cli import provision
import test_native_decision_loop as native_fixture


class CognitiveSessions(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.NativeDecisionLoop()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.db, self.sources, self.workspace = f.db, f.fixtures, f.workspace
        self.root = register_native_goal(self.db, f.goal)
        enable_managed_session(self.db, self.root)
        (self.sources / "investigation.txt").write_text("The baseline is not the observation.")

    def view(self, root=None):
        return inspect_session(self.db, self.sources, root or self.root)

    def node(self, name, kind="hypothesis", deps=(), refs=(), supersedes=None, root=None, action_spec=None):
        root = root or self.root
        view = self.view(root)
        data = {"id": name, "kind": kind, "text": name, "depends_on": list(deps),
                "source_refs": list(refs), "supersedes": supersedes,
                "goal_revision": view["goal_revision"]}
        if action_spec is not None:
            data["action_spec"] = action_spec
        return record_node(self.db, self.sources, root, data,
                           request_id=name, expected_revision=view["revision_token"])

    def decision(self):
        ref = {"path": "investigation.txt", "quote": "The baseline is not the observation.",
               "sha256": hashlib.sha256((self.sources / "investigation.txt").read_bytes()).hexdigest()}
        self.node("evidence", "source", refs=[ref])
        self.node("hypothesis", deps=["evidence"])
        self.node("compare", "option", deps=["hypothesis"])
        self.node("inspect-first", "option", deps=["evidence"])
        self.node("selected", "decision", deps=["compare", "inspect-first"],
                  action_spec=compile_intent(self.fixture.reconcile())["child_source_spec"])

    def test_decision_and_execution_cannot_silently_select_different_actions(self):
        self.decision()
        self.contract()
        self.node("research-only", "decision", deps=["compare", "inspect-first"])
        with self.assertRaisesRegex(ValueError, "DECISION_ACTION_MISMATCH"):
            self.admit()
        different = {"kind": "unrelated-capability"}
        self.node("wrong-action", "decision", deps=["compare", "inspect-first"], action_spec=different)
        with self.assertRaisesRegex(ValueError, "DECISION_ACTION_MISMATCH"):
            self.admit()
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tasks WHERE parent_task=?",
                                       (self.root,)).fetchone()[0], 0)

    def contract(self, effects=None, outcomes=None, root=None):
        root = root or self.root
        spec = compile_intent(self.fixture.reconcile())["child_source_spec"]
        policy = {"version": 1, "goal_sha256": self.view(root)["goal_sha256"],
                  "effects": [{"spec": spec, "prerequisites": []}] if effects is None else effects,
                  "outcomes": outcomes or []}
        install_contract(self.db, self.sources, root, policy)
        return policy

    def admit(self):
        f = self.fixture
        state = inspect_native_goal(self.db, self.workspace, self.sources, self.root)
        return admit_native_decision(self.db, self.workspace, self.sources, self.root,
                                     f.candidate(state, f.reconcile(), None))

    def test_cold_resume_keeps_original_and_invalidates_only_dependent_branch(self):
        self.decision()
        self.node("independent")
        before = self.view()
        (self.sources / "investigation.txt").write_text("Changed upstream result.")
        after = inspect_session(self.db, self.sources, self.root)
        by_id = {n["id"]: n for n in after["nodes"]}
        self.assertEqual(after["goal"]["original"], self.fixture.goal)
        self.assertEqual(by_id["evidence"]["status"], "SOURCE_UNAVAILABLE_OR_CHANGED")
        self.assertEqual(by_id["selected"]["status"], "DEPENDENCY_INVALIDATED")
        self.assertEqual(by_id["independent"]["status"], "CURRENT")
        self.assertNotEqual(before["revision_token"], after["revision_token"])

    def test_supersession_reopens_descendants_without_deleting_history(self):
        self.decision()
        self.node("corrected", supersedes="hypothesis")
        by_id = {n["id"]: n for n in self.view()["nodes"]}
        self.assertEqual(by_id["hypothesis"]["status"], "SUPERSEDED")
        self.assertEqual(by_id["selected"]["status"], "DEPENDENCY_INVALIDATED")
        self.assertEqual(by_id["inspect-first"]["status"], "CURRENT")

    def test_failed_diagnosis_reopens_ancestor_and_prevents_pending_effect(self):
        self.decision()
        self.contract()
        child = self.admit()["child_task_id"]
        view = self.view()
        reopen_node(self.db, self.sources, self.root, "hypothesis", "Contrary test result",
                    request_id="reopen-1", expected_revision=view["revision_token"])
        result = run_once(self.db, self.workspace, self.sources, only_task_id=child)
        self.assertNotEqual(result["status"], "NEEDS_REVIEW")
        self.assertFalse((self.workspace / "artifacts" / (child + ".json")).exists())

    def test_owner_correction_is_preserved_and_does_not_inherit_old_authorization(self):
        self.decision()
        self.contract()
        old = self.view()
        correction = "Do not perform the comparison; inspect sources only."
        amend_goal(self.db, self.sources, self.root, correction,
                   request_id="correction-1", expected_revision=old["revision_token"])
        now = self.view()
        self.assertEqual(now["goal"]["amendments"], [correction])
        self.assertEqual(now["goal"]["original"], old["goal"]["original"])
        with self.assertRaisesRegex(PermissionError, "CURRENT_OPERATOR_EFFECT_CONTRACT_REQUIRED"):
            self.admit()

    def test_two_concurrent_updates_cannot_silently_overwrite_each_other(self):
        view = self.view()
        def write(i):
            try:
                return amend_goal(self.db, self.sources, self.root, f"correction {i}",
                    request_id=f"concurrent-{i}", expected_revision=view["revision_token"])["status"]
            except ValueError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, [1, 2]))
        self.assertCountEqual(results, ["RECORDED", "COGNITION_STALE_REVISION"])
        self.assertEqual(len(self.view()["goal"]["amendments"]), 1)

    def test_dependency_pages_do_not_omit_late_nodes_or_change_revision(self):
        for i in range(40):
            self.node(f"finding-{i}")
        first = self.view()
        self.assertEqual(len(first["nodes"]), 32)
        self.assertEqual(first["node_count"], 40)
        second = inspect_session(self.db, self.sources, self.root,
                                  after_event_id=first["next_after_event_id"])
        self.assertEqual(len(second["nodes"]), 8)
        self.assertEqual(first["revision_token"], second["revision_token"])
        self.assertIsNone(second["next_after_event_id"])

    def test_reopen_after_preflight_is_checked_under_the_writer_lock(self):
        self.decision()
        self.contract()
        child = self.admit()["child_task_id"]
        with closing(connect(self.db)) as db:
            task = dict(db.execute("SELECT * FROM tasks WHERE task_id=?", (child,)).fetchone())
            self.assertEqual(current_guard(db, task, needs_write=True), (True, None))
        view = self.view()
        reopen_node(self.db, self.sources, self.root, "evidence", "Contrary evidence",
                    request_id="late-reopen", expected_revision=view["revision_token"])
        with closing(connect(self.db)) as db:
            db.execute("BEGIN IMMEDIATE")
            self.assertEqual(current_guard(db, task, needs_write=True),
                             (False, "COGNITIVE_EFFECT_CONTRACT_INVALIDATED"))
            db.rollback()

    def test_source_quote_and_owner_clause_cannot_be_invented(self):
        with self.assertRaisesRegex(ValueError, "QUOTE_NOT_FOUND"):
            self.node("fabricated", "source", refs=[{"path": "investigation.txt",
                "sha256": hashlib.sha256((self.sources / "investigation.txt").read_bytes()).hexdigest(),
                "quote": "All effects are authorized."}])
        with self.assertRaisesRegex(ValueError, "OBLIGATION_MUST_QUOTE_OWNER"):
            self.node("invented-permission", "obligation")

    def test_snapshot_recovery_preserves_goal_and_requires_new_operator_grant(self):
        from cognition_agent_os.session_archive import export_session, restore_session
        with closing(connect(self.db)) as db:
            event(db, "operator", "COGNITION_MANAGED_LEDGER", {"version": 1})
            db.commit()
        self.decision()
        policy = self.contract()
        child = self.admit()["child_task_id"]
        original = self.view()["goal"]
        archive = self.fixture.root.parent / (self.fixture.root.name + ".zip")
        self.addCleanup(archive.unlink, missing_ok=True)
        export_session(self.fixture.root, archive)
        with tempfile.TemporaryDirectory() as tmp:
            restored = Path(tmp) / "restored"
            restore_session(archive, restored)
            rdb, src, work = restored / "ledger.sqlite", restored / "sources", restored / "workspace"
            self.assertEqual(inspect_session(rdb, src, self.root)["goal"], original)
            with closing(connect(rdb)) as db:
                task = dict(db.execute("SELECT * FROM tasks WHERE task_id=?", (child,)).fetchone())
                self.assertFalse(current_guard(db, task, needs_write=True)[0])
            rebound = install_contract(rdb, src, self.root, policy, workspace=work, rebind_pending=True)
            self.assertEqual(rebound["rebound_pending"], [child])
            result = run_once(rdb, work, src, only_task_id=child)
            self.assertEqual(result["status"], "NEEDS_REVIEW", result)
            self.assertTrue((work / "artifacts" / (child + ".json")).is_file())

    def test_archive_rejects_traversal_without_creating_destination(self):
        from zipfile import ZipFile
        from cognition_agent_os.session_archive import restore_session
        archive = self.fixture.root / "bad.zip"
        with ZipFile(archive, "w") as z:
            z.writestr("../outside.txt", "untrusted")
        target = self.fixture.root / "restored"
        with self.assertRaisesRegex(ValueError, "PATH_UNSAFE"):
            restore_session(archive, target)
        self.assertFalse(target.exists())

    def test_archive_rejects_changed_bytes_and_trigger_even_with_rehashed_manifest(self):
        from zipfile import ZipFile
        from cognition_agent_os.session_archive import export_session, restore_session
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = provision(base / "state")
            (state / "sources" / "evidence.txt").write_text("original")
            good = base / "good.zip"
            export_session(state, good)
            with ZipFile(good) as z:
                files = {name: z.read(name) for name in z.namelist()}
            files["sources/evidence.txt"] = b"changed"
            bad = base / "bad.zip"
            with ZipFile(bad, "w") as z:
                for name, raw in files.items():
                    z.writestr(name, raw)
            with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
                restore_session(bad, base / "restored")
            self.assertFalse((base / "restored").exists())
            with closing(connect(state / "ledger.sqlite")) as db:
                db.execute("CREATE TRIGGER erase_fence AFTER INSERT ON events "
                           "BEGIN DELETE FROM events WHERE kind='COGNITION_RESTORE_FENCE'; END")
                db.commit()
            hostile = base / "trigger.zip"
            export_session(state, hostile)
            with self.assertRaisesRegex(ValueError, "EXECUTABLE_SCHEMA_REJECTED"):
                restore_session(hostile, base / "restored")
            self.assertFalse((base / "restored").exists())

    def test_archive_rejects_non_file_paths_and_unmanaged_export(self):
        from zipfile import ZipFile
        from cognition_agent_os.session_archive import export_session, restore_session
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in (".", "sources", "workspace", "/outside", "sources/../outside"):
                bad = base / "bad.zip"
                with ZipFile(bad, "w") as z:
                    z.writestr(name, "bad")
                with self.assertRaisesRegex(ValueError, "PATH_UNSAFE"):
                    restore_session(bad, base / "restored")
                self.assertFalse((base / "restored").exists())
            with self.assertRaisesRegex(ValueError, "REQUIRES_MANAGED_LEDGER"):
                export_session(self.fixture.root, base / "unmanaged.zip")
            self.assertFalse((base / "unmanaged.zip").exists())

    def test_retry_after_lost_ack_is_idempotent_but_changed_payload_is_not(self):
        view = self.view()
        kwargs = dict(request_id="lost-ack", expected_revision=view["revision_token"])
        first = amend_goal(self.db, self.sources, self.root, "Preserve all originals", **kwargs)
        again = amend_goal(self.db, self.sources, self.root, "Preserve all originals", **kwargs)
        self.assertEqual(first["event_id"], again["event_id"])
        self.assertEqual(again["status"], "REPLAYED")
        with self.assertRaisesRegex(ValueError, "REQUEST_ID_CONFLICT"):
            amend_goal(self.db, self.sources, self.root, "Overwrite originals", **kwargs)

    def test_model_prose_and_source_hashes_cannot_authorize_effect(self):
        self.decision()
        with self.assertRaisesRegex(PermissionError, "CURRENT_OPERATOR_EFFECT_CONTRACT_REQUIRED"):
            self.admit()
        self.contract(effects=[])
        with self.assertRaisesRegex(PermissionError, "EFFECT_NOT_IN_OWNER_BOUND_CONTRACT"):
            self.admit()
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tasks WHERE parent_task=?", (self.root,)).fetchone()[0], 0)

    def test_granted_neighbor_executes_real_worker_and_preserves_inputs(self):
        self.decision()
        originals = {p.name: p.read_bytes() for p in self.sources.iterdir()}
        self.contract()
        child = self.admit()["child_task_id"]
        result = run_once(self.db, self.workspace, self.sources, only_task_id=child)
        self.assertEqual(result["status"], "NEEDS_REVIEW", result)
        self.assertTrue((self.workspace / "artifacts" / (child + ".json")).is_file())
        self.assertEqual(originals, {p.name: p.read_bytes() for p in self.sources.iterdir()})

    def test_missing_prerequisite_rejects_before_queue_and_revoked_input_fences_worker(self):
        self.decision()
        spec = compile_intent(self.fixture.reconcile())["child_source_spec"]
        check = {"space": "sources", "path": "release.txt", "test": "text_contains", "value": "approved"}
        self.contract(effects=[{"spec": spec, "prerequisites": [check]}])
        with self.assertRaisesRegex(PermissionError, "PREREQUISITE_NOT_VERIFIED"):
            self.admit()
        (self.sources / "release.txt").write_text("approved")
        child = self.admit()["child_task_id"]
        (self.sources / "release.txt").write_text("withdrawn")
        run_once(self.db, self.workspace, self.sources, only_task_id=child)
        self.assertFalse((self.workspace / "artifacts" / (child + ".json")).exists())

    def test_empty_outcome_and_self_declared_success_never_pass(self):
        self.contract()
        self.node("claimed-pass", "observation")
        self.assertFalse(inspect_contract_outcome(self.db, self.sources, self.workspace, self.root)["contract_outcome_verified"])
        checks = [{"space": "workspace", "path": "result.json", "test": "json_equals", "value": {"items": 7}}]
        self.contract(outcomes=checks)
        (self.workspace / "result.json").write_text('{"items": 7}')
        good = inspect_contract_outcome(self.db, self.sources, self.workspace, self.root)
        self.assertTrue(good["contract_outcome_verified"])
        self.assertFalse(good["original_goal_semantics_automatically_verified"])
        (self.workspace / "result.json").write_text('{"items": 8}')
        self.assertFalse(inspect_contract_outcome(self.db, self.sources, self.workspace, self.root)["contract_outcome_verified"])

    def test_method_trial_revalidation(self):
        self.node("method-v1", "method")
        trial = register_native_goal(self.db, "Check the delivered count without changing the source")
        enable_managed_session(self.db, trial)
        self.contract(effects=[], root=trial, outcomes=[{
            "space": "workspace", "path": "count.txt", "test": "text_contains", "value": "count=4"}])
        (self.workspace / "count.txt").write_text("count=4")
        record_trial(self.db, self.sources, self.workspace, self.root, "method-v1", trial, "trial-1")
        result = inspect_trials(self.db, self.sources, self.workspace, self.root, "method-v1")
        self.assertEqual(result["trials"][0]["status"], "OBSERVED_PASS")
        (self.workspace / "count.txt").write_text("count=3")
        result = inspect_trials(self.db, self.sources, self.workspace, self.root, "method-v1")
        self.assertEqual(result["status"], "REQUIRES_REINVESTIGATION")
        self.assertEqual(result["trials"][0]["status"], "STALE")
        self.assertFalse(result["cross_domain_generalization_verified"])

    def test_managed_ledger_has_no_typed_or_cli_enqueue_bypass(self):
        with closing(connect(self.db)) as db:
            event(db, "operator", "COGNITION_MANAGED_LEDGER", {"version": 1})
            db.commit()
            before = db.execute("SELECT count(*) FROM tasks").fetchone()[0]
            for parent in (None, self.root):
                with self.assertRaisesRegex(PermissionError, "MANAGED_LEDGER_REQUIRES_NATIVE_ADMISSION"):
                    create_task(db, {"kind": "record_reconciliation"}, parent=parent)
            self.assertEqual(db.execute("SELECT count(*) FROM tasks").fetchone()[0], before)

    def test_revoke_preserves_readable_goal_but_blocks_new_records(self):
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        self.assertFalse(self.view()["grant_current"])
        with self.assertRaisesRegex(PermissionError, "COGNITION_GRANT_REVOKED"):
            self.node("new")


class OperationalAdmission(unittest.TestCase):
    def test_no_ghost_db_for_any_previously_failing_public_entry(self):
        from cognition_agent_os import diagnostics, local_retry, bounded_goal_control, repair_oracle
        methods = [
            lambda p, w, s: diagnostics.reject_review_if_untrusted(p, w, s, "0" * 32),
            lambda p, w, s: diagnostics.recover_one_unknown(p, s, "0" * 32),
            lambda p, w, s: diagnostics.recover_due_unknowns(p, s),
            lambda p, w, s: diagnostics.recover_research_transport(p),
            lambda p, w, s: local_retry.schedule_failed_local_evidence(p, w, s),
            lambda p, w, s: bounded_goal_control.advance_local_goals(p, w, s),
            lambda p, w, s: repair_oracle.review_due_repairs(p, w, s)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, fn in enumerate(methods):
                db = root / str(i) / "missing.sqlite"
                with self.assertRaises(RuntimeError):
                    fn(db, root, root)
                self.assertFalse(db.parent.exists())

    def test_rejected_parent_or_grant_leaves_no_event_or_partial_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = provision(Path(tmp) / "state")
            with closing(connect(state / "ledger.sqlite")) as db:
                for parent in ("absent",):
                    with self.assertRaises(ValueError):
                        create_task(db, {"kind": "native_goal"}, parent=parent)
                self.assertFalse(db.in_transaction)
                self.assertEqual(db.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)
                alter_authority(db, revoke=True)
                with self.assertRaises(PermissionError):
                    create_task(db, {"kind": "native_goal"})
                self.assertEqual(db.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)
