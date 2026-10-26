"""Real Host/SQLite decision-loop tests, independent of open_goal keywords.

These exercise model-neutral plan intake over two dissimilar registered local
capabilities. Candidate rationale is deliberately NOT a semantic oracle.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.goal_drift import observe_owner_goal_drift
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority
from cognition_agent_os.intent_planner import IntentError
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision,
    record_native_hypothesis)


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
        refs = [
            {"path": path.name,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(self.fixtures.iterdir(), key=lambda p: p.name)]
        previous = (state["decisions"][-1]["task_id"]
                    if state["decisions"] else None)
        return {
            "decision_basis": {
                "source_refs": refs, "previous_result_task_id": previous,
                "challenge": "The proposed method might not satisfy all original clauses.",
                "falsifier": "Independent mechanical results or original source drift could refute this choice.",
                "uncertainty": "Mechanical success cannot establish the whole owner outcome.",
            },
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

    def test_user_and_agent_ideas_share_one_challenged_decision_path(self):
        root = self.root_id()
        initial = self.view(root)
        user = record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="user", idea="Immediately rewrite the production stock database",
            observation_sha256=initial["observation_sha256"])
        self.assertEqual(user["status"], "NATIVE_HYPOTHESIS_RECORDED")
        self.assertFalse(user["authorizes_action"])
        after_user = self.view(root)
        agent = record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="agent", idea="Compare the original CSV records first",
            observation_sha256=after_user["observation_sha256"])
        after_agent = self.view(root)
        self.assertEqual([h["claimed_origin"] for h in after_agent["hypotheses"]],
                         ["user", "agent"])
        self.assertEqual(after_agent["original_goal"], self.goal)
        self.assertNotEqual(initial["observation_sha256"],
                            after_agent["observation_sha256"])
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 0)
        proposal = self.candidate(after_agent, self.reconcile(), self.structure())
        with self.assertRaisesRegex(ValueError, "NATIVE_HYPOTHESES_NOT_CHALLENGED"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root, proposal)
        proposal["hypothesis_reviews"] = [{
            "proposal_sha256": item["proposal_sha256"],
            "disposition": "REJECTED" if item["claimed_origin"] == "user"
                           else "CONDITIONALLY_USEFUL",
            "counterargument": "Production mutation is not approved by this goal.",
            "verification_needed": "Independently verify the original record facts.",
        } for item in after_agent["hypotheses"]]
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root, proposal)
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED")
        tick = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertEqual(self.view(root)["decision_count"], 1)

    def test_late_idea_invalidates_stale_decision_and_fake_reviews(self):
        root = self.root_id()
        stale = self.candidate(self.view(root), self.reconcile(), self.structure())
        updated = record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="user", idea="Skip fact checking and declare verified",
            observation_sha256=stale["observation_sha256"])
        with self.assertRaisesRegex(ValueError, "NATIVE_STALE_OBSERVATION"):
            admit_native_decision(self.db, self.workspace, self.fixtures, root, stale)
        current = self.view(root)
        proposition = self.candidate(current, self.reconcile(), self.structure())
        proposition["hypothesis_reviews"] = [{
            "proposal_sha256": "f" * 64,
            "disposition": "CONDITIONALLY_USEFUL",
            "counterargument": "This assertion conflicts with independent evidence.",
            "verification_needed": "Check the source provenance and actual outcome.",
        }]
        with self.assertRaisesRegex(ValueError, "NATIVE_HYPOTHESES_NOT_CHALLENGED"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root, proposition)
        self.assertEqual(self.view(root)["decision_count"], 0)

    def test_proposing_does_not_mint_authority_after_revocation(self):
        root = self.root_id()
        before = self.view(root)
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaisesRegex(ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
            record_native_hypothesis(
                self.db, self.workspace, self.fixtures, root,
                origin="agent", idea="Invent remote write permissions",
                observation_sha256=before["observation_sha256"])
        self.assertEqual(self.view(root)["hypotheses"], [])

    def test_ungrounded_material_choice_rejected_before_ledger_child(self):
        """A plausible comparison alone is not verifiable investigation."""
        root = self.root_id()
        observed = self.view(root)
        proposal = self.candidate(observed, self.reconcile(), self.structure())
        proposal.pop("decision_basis")
        self.assertNotIn("decision_basis", proposal)
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_UNGROUNDED_DECISION"):
            admit_native_decision(self.db, self.workspace, self.fixtures,
                                  root, proposal)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 0)

    def test_hallucinated_or_stale_investigation_refs_are_not_admitted(self):
        root = self.root_id()
        observed = self.view(root)
        proposal = self.candidate(observed, self.reconcile(), self.structure())
        proposal["decision_basis"]["source_refs"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "DECISION_SOURCE_ID_OR_DIGEST_UNVERIFIABLE"):
            admit_native_decision(self.db, self.workspace, self.fixtures, root, proposal)
        proposed = self.candidate(observed, self.reconcile(), self.structure())
        proposed["decision_basis"]["source_refs"] = []
        with self.assertRaisesRegex(ValueError, "METHOD_RESEARCH_SOURCES_NOT_CITED"):
            admit_native_decision(self.db, self.workspace, self.fixtures, root, proposed)
        self.assertEqual(self.view(root)["decision_count"], 0)

    def test_prior_result_must_be_same_verified_decision_chain(self):
        root = self.root_id()
        observed = self.view(root)
        candidate = self.candidate(observed, self.reconcile(), self.structure())
        candidate["decision_basis"]["previous_result_task_id"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "PREVIOUS_DECISION_RESULT_NOT_GROUNDED"):
            admit_native_decision(self.db, self.workspace, self.fixtures, root, candidate)
        self.assertEqual(self.view(root)["decision_count"], 0)

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

    def test_catalog_discovers_real_current_capabilities_and_rejects_ghost_source(self):
        """A native planner need not ask owner to enumerate files or registered tools."""
        common = [sys.executable, "-m", "cognition_agent_os.cli",
                  "--db", str(self.db), "--workspace", str(self.workspace),
                  "--fixtures", str(self.fixtures)]
        root = self.root_id()
        proc = subprocess.run(
            [*common, "native-capability-catalog", "--root-task-id", root],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        catalog = json.loads(proc.stdout)
        self.assertEqual(catalog["status"], "NATIVE_CAPABILITY_CATALOG")
        methods = {x["objective"]: x for x in catalog["methods"]}
        self.assertTrue(methods["compare_records"]["currently_eligible"])
        self.assertTrue(methods["ensure_structure"]["currently_eligible"])
        self.assertFalse(methods["investigate_evidence"]["currently_eligible"])
        self.assertFalse(methods["discover_public_tools"]["currently_eligible"])
        self.assertEqual(methods["compare_records"]["required_resource_roles"],
                         ["reference", "observed"])
        self.assertFalse(catalog["business_outcome_verified"])
        bogus = self.reconcile()
        bogus["resources"][1]["path"] = "nonexistent.csv"
        with self.assertRaisesRegex(ValueError, "SELECTED_NATIVE_SOURCE_UNAVAILABLE"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root,
                self.candidate(self.view(root), bogus, self.structure()))
        self.assertEqual(self.view(root)["decision_count"], 0)
        # A fresh supported source changes the observed catalog, not the
        # original goal or the grant.
        (self.fixtures / "inspection.md").write_text(
            "Inspect local shortage causes before choosing a remedy.\n")
        later = json.loads(subprocess.run(
            [*common, "native-capability-catalog", "--root-task-id", root],
            check=True, capture_output=True, text=True).stdout)
        after = {x["objective"]: x for x in later["methods"]}
        self.assertTrue(after["investigate_evidence"]["currently_eligible"])
        self.assertNotEqual(later["source_manifest_sha256"],
                            catalog["source_manifest_sha256"])

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

    def test_existing_v1_goal_contract_keeps_original_budget_and_can_resume(self):
        from cognition_agent_os.native_decision import _contract, _digest
        root = self.root_id()
        legacy = _contract(self.goal, legacy=True)
        with closing(connect(self.db)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                       (json.dumps(legacy, ensure_ascii=False), root))
            db.execute("UPDATE events SET details=? WHERE task_id=? "
                       "AND kind='NATIVE_GOAL_REGISTERED'",
                       (json.dumps({
                           "contract_sha256": _digest(legacy),
                           "owner_outcome_verified": False,
                           "external_effect_authorized": False,
                       }), root))
            db.commit()
        state = self.view(root)
        self.assertEqual(state["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE", state)
        self.assertEqual(legacy["max_decisions"], 3)
        admission = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(state, self.reconcile(), self.structure()))
        self.assertEqual(admission["status"], "NATIVE_METHOD_ENQUEUED")

    def test_new_research_source_can_enter_after_independently_verified_action(self):
        root = self.root_id()
        first = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), self.reconcile(), self.structure()))
        self.assertEqual(run_tick(self.db, self.workspace, self.fixtures,
                                  max_jobs=1)["tasks"][0]["status"], "NEEDS_REVIEW")
        observed = self.view(root)
        self.assertEqual(observed["decisions"][0]["mechanical_verdict"],
                         "REPORT_MECHANICALLY_VERIFIED")
        (self.fixtures / "new_domain_finding.md").write_text(
            "Independent method review after initial reconciliation.\n",
            encoding="utf-8")
        recovered = self.view(root)
        self.assertEqual(recovered["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE",
                         recovered)
        self.assertEqual(recovered["decisions"][0]["mechanical_verdict"],
                         "REPORT_MECHANICALLY_VERIFIED")
        self.assertNotEqual(observed["observation_sha256"],
                            recovered["observation_sha256"])
        inquiry = {"kind": "goal_intent", "objective": "investigate_evidence",
                   "resources": [],
                   "question": "What does the new review say about the mismatch?"}
        second = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(recovered, inquiry, self.reconcile()))
        self.assertEqual(second["status"], "NATIVE_METHOD_ENQUEUED")
        self.assertNotEqual(first["child_task_id"], second["child_task_id"])

    def test_new_research_document_before_investigation_execution_fences_old_scope(self):
        (self.fixtures / "initial.md").write_text(
            "Only the initial research evidence is approved.", encoding="utf-8")
        root = self.root_id()
        investigation = {"kind": "goal_intent", "objective": "investigate_evidence",
                         "resources": [], "question":
                         "What is the evidence on source-scope approval?"}
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), investigation, self.reconcile()))
        (self.fixtures / "later.md").write_text(
            "A second research source appeared after admission.", encoding="utf-8")
        self.assertEqual(self.view(root)["status"], "NATIVE_SOURCE_CHANGED")
        attempted = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1,
            planner_mode="ollama-local", local_model="installed:test")
        self.assertNotEqual(attempted["tasks"][0]["status"], "NEEDS_REVIEW",
                            attempted)
        self.assertFalse((self.workspace / "artifacts" /
                          (admitted["child_task_id"] + ".json")).exists())

    def test_new_research_document_after_accepted_investigation_is_not_source_drift(self):
        from cognition_agent_os import local_model
        (self.fixtures / "reason_a.md").write_text(
            "The original evidence must remain attributable.", encoding="utf-8")
        (self.fixtures / "reason_b.md").write_text(
            "An external verifier must validate the outcome.", encoding="utf-8")
        root = self.root_id()
        inquiry = {"kind": "goal_intent", "objective": "investigate_evidence",
                   "resources": [], "question":
                   "How can source attribution and independent verification be preserved?"}
        start = self.view(root)
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(start, inquiry, self.reconcile()))
        times = [0]
        def model(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "local:test"}]}
            times[0] += 1
            if times[0] == 1:
                return {"done": True, "response": json.dumps(
                    {"sources": ["reason_a.md", "reason_b.md"]})}
            return {"done": True, "response": json.dumps({
                "findings": [
                    {"source": "reason_a.md",
                     "quote": "The original evidence must remain attributable.",
                     "interpretation": "Provenance must be checked separately."},
                    {"source": "reason_b.md",
                     "quote": "An external verifier must validate the outcome.",
                     "interpretation": "Check actual acceptance separately."}],
                "uncertainty": "This research does not verify the whole owner outcome.",
            })}
        with patch.object(local_model, "_request", side_effect=model):
            processed = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=1,
                planner_mode="ollama-local", local_model="local:test")
        self.assertEqual(processed["tasks"][0]["status"], "NEEDS_REVIEW", processed)
        baseline = self.view(root)
        self.assertEqual(baseline["decisions"][0]["mechanical_verdict"],
                         "SOURCE_GROUNDED_UNREVIEWED", baseline)
        (self.fixtures / "later_finding.md").write_text(
            "A newly acquired independent source changes the next search.",
            encoding="utf-8")
        evolved = self.view(root)
        self.assertEqual(evolved["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE",
                         evolved)
        self.assertEqual(evolved["decisions"][0]["mechanical_verdict"],
                         "SOURCE_GROUNDED_UNREVIEWED", evolved)
        next_action = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(evolved, self.reconcile(), self.structure()))
        subsequent = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(subsequent["tasks"][0]["task_id"],
                         next_action["child_task_id"])
        self.assertEqual(subsequent["tasks"][0]["status"],
                         "NEEDS_REVIEW", subsequent)
        (self.fixtures / "reason_a.md").write_text(
            "The originally pinned source was altered.", encoding="utf-8")
        self.assertEqual(self.view(root)["status"], "NATIVE_SOURCE_CHANGED")

    def test_new_evidence_enables_changed_method_retry_beyond_three_steps(self):
        root = self.root_id()
        for step in range(4):
            if step:
                (self.fixtures / f"followup_{step}.csv").write_text(
                    "supplier,received\nDelta," + str(6-step) + "\n",
                    encoding="utf-8")
            current = self.view(root)
            self.assertEqual(current["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE",
                             current)
            selected = self.reconcile()
            if step:
                selected["resources"][1]["path"] = f"followup_{step}.csv"
            accepted = admit_native_decision(
                self.db, self.workspace, self.fixtures, root,
                self.candidate(current, selected, self.structure()))
            tick = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
            self.assertEqual(tick["tasks"][0]["task_id"],
                             accepted["child_task_id"])
            self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW", tick)
        final = self.view(root)
        self.assertEqual(final["decision_count"], 4)
        self.assertTrue(all(x["mechanical_verdict"] ==
                            "REPORT_MECHANICALLY_VERIFIED"
                            for x in final["decisions"]), final)
        self.assertFalse(final["owner_outcome_verified"])

    def test_appending_evidence_cannot_mask_tampering_of_pinned_fact(self):
        root = self.root_id()
        admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), self.reconcile(), self.structure()))
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        (self.fixtures / "new_review.md").write_text("Extra research", encoding="utf-8")
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,999\n", encoding="utf-8")
        self.assertEqual(self.view(root)["status"], "NATIVE_SOURCE_CHANGED")

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

    def test_native_owner_drift_uses_original_single_ledger_observer(self):
        """Observe native source drift once; never self-approve owner results."""
        root = self.root_id()
        first = observe_owner_goal_drift(
            self.db, workspace=self.workspace, fixtures=self.fixtures)
        self.assertTrue(any(
            x["root_task_id"] == root and x["status"] == "DRIFT_SIGNAL_RECORDED"
            for x in first), first)
        self.assertEqual(observe_owner_goal_drift(
            self.db, workspace=self.workspace, fixtures=self.fixtures), [])
        initial = self.view(root)
        admitted = admit_native_decision(
            self.db,self.workspace,self.fixtures,root,
            self.candidate(initial,self.reconcile(),self.structure()))
        ran = run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(ran["tasks"][0]["task_id"],admitted["child_task_id"])
        self.assertEqual(ran["tasks"][0]["status"],"NEEDS_REVIEW")
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,500\n",encoding="utf-8")
        changed = observe_owner_goal_drift(
            self.db,workspace=self.workspace,fixtures=self.fixtures)
        states = [x["fidelity_state"] for x in changed
                  if x.get("status")=="DRIFT_SIGNAL_RECORDED"]
        self.assertIn("NATIVE_OWNER_SOURCE_CHANGED", states, changed)
        self.assertEqual(observe_owner_goal_drift(
            self.db,workspace=self.workspace,fixtures=self.fixtures), [])
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        revoked = observe_owner_goal_drift(
            self.db,workspace=self.workspace,fixtures=self.fixtures)
        self.assertTrue(any(x["status"]=="NOT_ADMITTED" for x in revoked))
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='OWNER_GOAL_LOCAL_RESULT_OBSERVED'",(root,)
            ).fetchone()[0],0)

    def test_native_accepted_artifact_tamper_sets_objective_drift(self):
        root=self.root_id()
        start=self.view(root)
        child=admit_native_decision(
            self.db,self.workspace,self.fixtures,root,
            self.candidate(start,self.reconcile(),self.structure()))["child_task_id"]
        ran=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(ran["tasks"][0]["status"],"NEEDS_REVIEW")
        payload=self.workspace/"artifacts"/(child+".json")
        payload.write_bytes(payload.read_bytes()+b" unexpected bytes")
        observed=observe_owner_goal_drift(
            self.db,workspace=self.workspace,fixtures=self.fixtures)
        self.assertTrue(any(
            x.get("fidelity_state")=="NATIVE_OWNER_EVIDENCE_UNVERIFIABLE"
            for x in observed),observed)
        self.assertFalse(self.view(root)["business_outcome_verified"])

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
