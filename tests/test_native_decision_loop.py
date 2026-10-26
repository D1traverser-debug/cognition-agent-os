"""Real Host/SQLite decision-loop tests, independent of open_goal keywords.

These exercise model-neutral plan intake over two dissimilar registered local
capabilities. Candidate rationale is deliberately NOT a semantic oracle.
"""
from contextlib import closing
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority
from cognition_agent_os.intent_planner import IntentError
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision)


class NativeDecisionLoop(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "ledger.sqlite"
        self.fixtures = self.root / "sources"
        self.workspace = self.root / "workspace"
        self.fixtures.mkdir()
        self.workspace.mkdir()
        (self.fixtures / "expected.csv").write_text(
            "supplier,received\nDelta,8\n", encoding="utf-8")
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,6\n", encoding="utf-8")
        (self.fixtures / "handoff.json").write_text(
            '{"retain":"immutable"}\n', encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
        self.goal = (
            "Reconcile a supplier stock shortfall against the original records; "
            "preserve a local auditable discrepancy report and then prepare an "
            "isolated provenance-labelled handoff, without editing originals."
        )

    @staticmethod
    def reconcile():
        return {"kind": "goal_intent", "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": "expected.csv"},
                    {"role": "observed", "path": "observed.csv"}]}

    @staticmethod
    def structure():
        return {"kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "handoff.json"}],
                "requirements": [{"field": "audit", "equals": "confirmed"}]}

    def candidate(self, state, selected, alternative):
        return {
            "observation_sha256": state["observation_sha256"],
            "selected_intent": selected, "alternative_intent": alternative,
            "decision_reason": "This registered method directly checks original local evidence first.",
            "alternative_reason": "The other registered method cannot establish the first comparison.",
            "expected_evidence": "Independent on-disk artifact audit, not a model completion opinion.",
        }

    def root_id(self):
        return register_native_goal(self.db, self.goal)

    def view(self, root):
        return inspect_native_goal(self.db, self.workspace, self.fixtures, root)

    def test_novel_full_owner_goal_dynamic_competing_methods_real_host(self):
        original = {p.name: p.read_bytes() for p in self.fixtures.iterdir()}
        root = self.root_id()
        start = self.view(root)
        self.assertEqual(start["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE")
        first = admit_native_decision(self.db, self.workspace, self.fixtures,
                                      root, self.candidate(start, self.reconcile(),
                                                           self.structure()))
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED")
        with self.assertRaisesRegex(ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root,
                self.candidate(start, self.reconcile(), self.structure()))
        tick = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW", tick)
        self.assertEqual(tick["tasks"][0]["task_id"], first["child_task_id"])
        follow = self.view(root)
        self.assertEqual(follow["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE", follow)
        self.assertEqual(follow["decisions"][0]["mechanical_verdict"],
                         "REPORT_MECHANICALLY_VERIFIED")
        second = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(follow, self.structure(), self.reconcile()))
        tick2 = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(tick2["tasks"][0]["status"], "NEEDS_REVIEW", tick2)
        self.assertEqual(tick2["tasks"][0]["task_id"], second["child_task_id"])
        final = self.view(root)
        self.assertEqual(final["decision_count"], 2)
        self.assertEqual(final["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE", final)
        self.assertEqual(final["decisions"][1]["mechanical_verdict"],
                         "CANDIDATE_MECHANICALLY_VALID")
        self.assertFalse(final["business_outcome_verified"])
        self.assertFalse(final["owner_outcome_verified"])
        self.assertEqual({p.name: p.read_bytes()
                          for p in self.fixtures.iterdir()}, original)
        # Exact cold-process restoration uses the existing goal-resume entry.
        proc = subprocess.run(
            [sys.executable, "-m", "cognition_agent_os.cli",
             "--db", str(self.db), "--workspace", str(self.workspace),
             "--fixtures", str(self.fixtures), "goal-resume"],
            capture_output=True, text=True)
        recovered = json.loads(proc.stdout)
        self.assertEqual(recovered["status"], "READY_FOR_NATIVE_DECISION", proc.stderr)
        self.assertEqual(recovered["original_goal"], self.goal)
        self.assertEqual(recovered["native_decision_state"]["decision_count"], 2)

    def test_unfamiliar_chinese_goal_cross_process_native_cli(self):
        """The real CLI, not a Python-only method call, performs admission/readback."""
        chinese = ("核对供应商出入库差异并保留原始数据；随后为审计准备隔离草案，"
                   "不要改写任何生产账户或原始来源。")
        common = [sys.executable, "-m", "cognition_agent_os.cli",
                  "--db", str(self.db), "--workspace", str(self.workspace),
                  "--fixtures", str(self.fixtures)]
        def invoke(*command):
            run = subprocess.run([*common, *command], text=True,
                                 capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            return json.loads(run.stdout)
        created = invoke("seed-native-goal", "--goal", chinese)
        root = created["root_task_id"]
        self.assertEqual(created["status"], "NATIVE_GOAL_REGISTERED")
        initial = invoke("native-goal-readback", "--root-task-id", root)
        self.assertEqual(initial["original_goal"], chinese)
        proposal = self.candidate(initial, self.reconcile(), self.structure())
        path = self.root / "decision.json"
        path.write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
        admitted = invoke("native-decision-admit", "--root-task-id", root,
                          "--spec", str(path))
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED")
        executed = invoke("host-tick", "--max-jobs", "1")
        self.assertEqual(executed["tasks"][0]["task_id"], admitted["child_task_id"])
        self.assertEqual(executed["tasks"][0]["status"], "NEEDS_REVIEW")
        resumed = invoke("goal-resume")
        self.assertEqual(resumed["status"], "READY_FOR_NATIVE_DECISION")
        self.assertEqual(resumed["original_goal"], chinese)
        self.assertEqual(resumed["native_decision_state"]["decisions"][0]
                         ["mechanical_verdict"], "REPORT_MECHANICALLY_VERIFIED")

    def test_conflict_for_first_method_can_be_followed_by_new_method(self):
        root = self.root_id()
        bad = self.structure()
        bad["requirements"][0] = {"field": "retain", "equals": "not_immutable"}
        first = admit_native_decision(self.db, self.workspace, self.fixtures,
                    root, self.candidate(self.view(root), bad, self.reconcile()))
        observed = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(observed["tasks"][0]["task_id"], first["child_task_id"])
        self.assertEqual(observed["tasks"][0]["status"], "UNKNOWN", observed)
        state = self.view(root)
        self.assertEqual(state["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE", state)
        self.assertEqual(state["decisions"][0]["task_state"], "UNKNOWN")
        second = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(state, self.reconcile(), self.structure()))
        later = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(later["tasks"][0]["task_id"], second["child_task_id"])
        self.assertEqual(later["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertFalse(self.view(root)["owner_outcome_verified"])

    def test_prior_evidence_tampering_after_redecision_must_block_worker(self):
        """No cached admission can bypass live preceding-method proof."""
        root = self.root_id()
        first = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), self.reconcile(), self.structure()))
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        follow = self.view(root)
        self.assertEqual(follow["decisions"][0]["mechanical_verdict"],
                         "REPORT_MECHANICALLY_VERIFIED")
        second = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(follow, self.structure(), self.reconcile()))
        first_artifact = self.workspace / "artifacts" / (
            first["child_task_id"] + ".json")
        first_artifact.write_bytes(first_artifact.read_bytes() + b" tampered")
        attempted = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(attempted["tasks"][0]["task_id"],
                         second["child_task_id"], attempted)
        self.assertNotEqual(attempted["tasks"][0]["status"], "NEEDS_REVIEW",
                            attempted)
        self.assertFalse((self.workspace / "artifacts" /
                          (second["child_task_id"] + ".json")).exists())

    def test_source_drift_and_revocation_block_new_model_choice(self):
        root = self.root_id()
        first = admit_native_decision(self.db, self.workspace, self.fixtures,
                    root, self.candidate(self.view(root), self.reconcile(),
                                         self.structure()))
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        old = self.view(root)
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,1\n", encoding="utf-8")
        drift = self.view(root)
        self.assertEqual(drift["status"], "NATIVE_SOURCE_CHANGED", drift)
        with self.assertRaisesRegex(ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
            admit_native_decision(self.db, self.workspace, self.fixtures, root,
                self.candidate(old, self.structure(), self.reconcile()))
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaises(ValueError):
            admit_native_decision(self.db, self.workspace, self.fixtures, root,
                self.candidate(old, self.structure(), self.reconcile()))
        proc = subprocess.run(
            [sys.executable, "-m", "cognition_agent_os.cli",
             "--db", str(self.db), "--workspace", str(self.workspace),
             "--fixtures", str(self.fixtures), "goal-resume"],
            capture_output=True, text=True)
        recovered = json.loads(proc.stdout)
        self.assertEqual(recovered["status"], "AUTHORITY_REVOKED", proc.stderr)
        self.assertEqual(recovered["original_goal"], self.goal)

    def test_worker_refuses_forged_extra_child(self):
        root = self.root_id()
        with closing(connect(self.db)) as db:
            invented = create_task(db, {
                "kind": "goal_case", "goal_type": "json_keys",
                "input": "handoff.json", "desired": {"danger": "accept"}},
                parent=root)
        observed = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(observed["tasks"][0]["task_id"], invented)
        self.assertNotEqual(observed["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertFalse((self.workspace / "artifacts" /
                          (invented + ".json")).exists())

    def test_no_owner_grant_no_public_discovery_and_no_unregistered_effect(self):
        root = self.root_id()
        initial = self.view(root)
        public = {"kind": "goal_intent", "objective": "discover_public_tools",
                  "resources": [], "terms": ["procurement"]}
        with self.assertRaises(PermissionError):
            admit_native_decision(self.db, self.workspace, self.fixtures,
                root, self.candidate(initial, public, self.reconcile()))
        with self.assertRaises((ValueError, IntentError, KeyError)):
            unknown = {"kind": "goal_intent", "objective": "deploy_production",
                       "resources": []}
            admit_native_decision(self.db, self.workspace, self.fixtures, root,
                self.candidate(initial, unknown, self.reconcile()))
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaises(PermissionError):
            register_native_goal(self.db, self.goal)


if __name__ == "__main__":
    unittest.main()
