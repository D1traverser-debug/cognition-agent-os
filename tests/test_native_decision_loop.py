"""Real Host/SQLite decision-loop tests, independent of open_goal keywords.

These exercise model-neutral plan intake over two dissimilar registered local
capabilities. Candidate rationale is deliberately NOT a semantic oracle.
"""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.goal_drift import observe_owner_goal_drift
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority
from cognition_agent_os.intent_planner import IntentError
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision,
    record_native_hypothesis, record_native_open_research)


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

    def test_lost_creation_ack_replays_same_root_without_duplicate_goal(self):
        """Prospective crash/retry fault across grant, naming and cold memory."""
        stable_request = "owner-native-create-acklost-0001"
        created = register_native_goal(
            self.db, self.goal, client_request_id=stable_request)
        # Simulate a lost transport acknowledgement: the client never saw
        # created, retries the same request after the original DB commit.
        replayed = register_native_goal(
            self.db, self.goal, client_request_id=stable_request)
        self.assertEqual(replayed, created)
        with closing(connect(self.db)) as db:
            roots = db.execute(
                "SELECT count(*) FROM tasks WHERE parent_task IS NULL "
                "AND json_extract(source_spec,'$.kind')='native_goal'"
            ).fetchone()[0]
        self.assertEqual(roots, 1)
        self.assertEqual(self.view(created)["original_goal"], self.goal)
        self.assertEqual(self.view(created)["decision_count"], 0)
        # A reused request identity cannot switch a prior user's actual
        # desired outcome or elevate public discovery capabilities.
        with self.assertRaisesRegex(
                ValueError, "NATIVE_GOAL_IDEMPOTENCY_CONFLICT"):
            register_native_goal(
                self.db, self.goal + " now perform unsafe writes",
                client_request_id=stable_request)
        with self.assertRaisesRegex(
                ValueError, "NATIVE_GOAL_IDEMPOTENCY_CONFLICT"):
            register_native_goal(
                self.db, self.goal, allow_public_discovery=True,
                client_request_id=stable_request)
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaises(PermissionError):
            register_native_goal(
                self.db, self.goal, client_request_id=stable_request)

    def test_original_goal_identity_survives_local_source_manifest_outage(self):
        """Root identity comes from authenticated ledger, not file availability."""
        root = self.root_id()
        original = self.goal
        expected = self.fixtures / "expected.csv"
        scenarios = ("unsupported_entry", "source_count_exhausted",
                     "directory_unavailable")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                injected = []
                if scenario == "unsupported_entry":
                    bad = self.fixtures / "unexpected.lock"
                    bad.write_text("transient writer temp file", encoding="utf-8")
                    injected.append(bad)
                elif scenario == "source_count_exhausted":
                    for index in range(62):
                        bad = self.fixtures / ("added_%02d.md" % index)
                        bad.write_text("research source placeholder", encoding="utf-8")
                        injected.append(bad)
                else:
                    self.fixtures.rename(self.root / "sources-temporarily-offline")
                try:
                    # Pure identity must remain recoverable despite failed
                    # evidence audit. No stale source can authorize action.
                    observed = self.view(root)
                    self.assertEqual(observed["original_goal"], original)
                    self.assertEqual(observed["status"],
                                     "NATIVE_SOURCE_UNAVAILABLE")
                    self.assertFalse(observed["owner_outcome_verified"])
                    self.assertNotIn("observation_sha256", observed)
                    # Separate consumers of the same source/identity state
                    # must not crash or silently call the owner result PASS.
                    owner = inspect_owner_local_outcome(
                        self.db, self.workspace, self.fixtures, root)
                    self.assertFalse(owner["local_owner_outcome_verified"])
                    monitored = observe_owner_goal_drift(
                        self.db, workspace=self.workspace,
                        fixtures=self.fixtures)
                    self.assertTrue(any(
                        item.get("fidelity_state")
                            == "NATIVE_OWNER_SOURCE_UNAVAILABLE"
                        for item in monitored), monitored)
                    with self.assertRaisesRegex(
                            ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
                        record_native_open_research(
                            self.db, self.workspace, self.fixtures, root, {})
                finally:
                    if scenario == "directory_unavailable":
                        (self.root / "sources-temporarily-offline").rename(
                            self.fixtures)
                    for path in injected:
                        path.unlink()
                recovered = self.view(root)
                self.assertEqual(recovered["original_goal"], original)
                self.assertEqual(recovered["status"],
                                 "NATIVE_NEXT_DECISION_ADMISSIBLE")
                # Permit fresh outage detection on the next injected fault,
                # instead of treating all outages as one unchanged signal.
                observe_owner_goal_drift(
                    self.db, workspace=self.workspace,
                    fixtures=self.fixtures)
        self.assertEqual(expected.read_text(encoding="utf-8"),
                         "supplier,received\nDelta,8\n")
        # Adversarial opposite case: source outage must NOT cause the system
        # to trust a forged/tampered ledger registration as an owner goal.
        with closing(connect(self.db)) as db:
            db.execute(
                "UPDATE events SET details=? WHERE task_id=? "
                "AND kind='NATIVE_GOAL_REGISTERED'",
                ('{"contract_sha256":"' + "f" * 64 + '",'
                 '"owner_outcome_verified":false,'
                 '"external_effect_authorized":false}', root))
            db.commit()
        (self.fixtures / "unexpected.lock").write_text(
            "outage again", encoding="utf-8")
        forged = self.view(root)
        self.assertEqual(forged["status"], "NATIVE_GOAL_UNVERIFIABLE")
        self.assertNotIn("original_goal", forged)

    def test_simultaneous_native_creation_same_key_one_original_root(self):
        """Two SQLite connections racing after client retry cannot fork owner."""
        key = "owner-native-concurrent-acklost-0002"
        barrier = Barrier(2)

        def call():
            barrier.wait(timeout=10)
            return register_native_goal(
                self.db, self.goal, client_request_id=key)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(call)
            second = executor.submit(call)
            values = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(values[0], values[1])
        with closing(connect(self.db)) as db:
            roots = db.execute(
                "SELECT task_id FROM tasks WHERE parent_task IS NULL "
                "AND json_extract(source_spec,'$.kind')='native_goal'"
            ).fetchall()
            registrations = db.execute(
                "SELECT count(*) FROM events WHERE kind='NATIVE_GOAL_REGISTERED'"
            ).fetchone()[0]
        self.assertEqual(len(roots), 1)
        self.assertEqual(registrations, 1)
        self.assertEqual(roots[0]["task_id"], values[0])
        self.assertEqual(self.view(values[0])["original_goal"], self.goal)

    def test_unregistered_professional_domain_can_research_and_resume_without_execution(self):
        """Real SQLite research state before ANY local executable fits the goal."""
        (self.fixtures / "thermal-observations.md").write_text(
            "Calibration runs diverge when chamber humidity increases.\\n",
            encoding="utf-8")
        goal = ("Diagnose unknown humidity-dependent chamber calibration drift; "
                "do not modify the chamber and require external expert confirmation "
                "before declaring any calibration safe.")
        root = register_native_goal(self.db, goal)
        before = self.view(root)
        self.assertEqual(before["decision_count"], 0)
        source = self.fixtures / "thermal-observations.md"
        proposal = {
            "observation_sha256": before["observation_sha256"],
            "owner_clause": "do not modify the chamber",
            "unresolved_question": (
                "Does humidity alter the sensor response, the reference system, "
                "or the sampling procedure?"),
            "competing_methods": [
                {
                    "name": "reference_crosscheck",
                    "applicability": "Check against an independently calibrated reference.",
                    "failure_mode": "The reference sensor may share the same bias.",
                    "falsifier": "A third independent reference contradicts the effect.",
                },
                {
                    "name": "controlled_humidity_study",
                    "applicability": "Compare instrument response across controlled humidity levels.",
                    "failure_mode": "Temperature drift may confound the result.",
                    "falsifier": "Matched dry and humid samples show equal drift.",
                },
            ],
            "source_refs": [{"path": source.name,
                             "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            "next_research_step": (
                "Locate independent calibration standards and matched test conditions."),
            "uncertainty": "Neither method has been executed nor externally validated.",
        }
        recorded = record_native_open_research(
            self.db, self.workspace, self.fixtures, root, proposal)
        self.assertEqual(recorded["status"], "NATIVE_OPEN_RESEARCH_RECORDED")
        self.assertFalse(recorded["authorizes_action"])
        resumed = self.view(root)  # fresh readonly DB connection = cold state readback
        self.assertEqual(resumed["original_goal"], goal)
        self.assertEqual(resumed["decision_count"], 0)
        self.assertEqual(len(resumed["open_research"]), 1)
        self.assertEqual(resumed["open_research"][0]["proposal"]["competing_methods"],
                         proposal["competing_methods"])
        self.assertEqual(resumed["open_research"][0]["source_status"],
                         "SOURCE_PIN_CURRENT_UNVERIFIED_SEMANTICS")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM tasks WHERE parent_task=?", (root,)
            ).fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, "NATIVE_STALE_OBSERVATION"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, proposal)
        repeated = dict(proposal)
        repeated["observation_sha256"] = resumed["observation_sha256"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_NATIVE_OPEN_RESEARCH"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, repeated)
        malicious = dict(repeated)
        malicious["execute_shell"] = "curl provider/erase"
        with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_OPEN_RESEARCH"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, malicious)
        fake = dict(repeated)
        fake["source_refs"] = [{"path": source.name, "sha256": "a" * 64}]
        with self.assertRaisesRegex(ValueError, "NATIVE_RESEARCH_SOURCE_UNVERIFIABLE"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, fake)
        # Previously pinned evidence can go stale without falsifying owner
        # identity, granting an action or mutating a user's source.
        source.write_text("New measurement requires independent review.\\n",
                          encoding="utf-8")
        changed = self.view(root)
        self.assertEqual(changed["open_research"][0]["source_status"],
                         "SOURCE_STALE_OR_REMOVED")
        self.assertFalse(changed["owner_outcome_verified"])

    def test_open_research_history_is_not_a_permanent_prompt_quota(self):
        """Seventy genuine research events survive with a bounded, pageable read."""
        goal = "Investigate an unregistered professional task without an external write."
        root = register_native_goal(self.db, goal)
        for index in range(70):
            state = self.view(root)
            self.assertEqual(state["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE")
            proposal = {
                "observation_sha256": state["observation_sha256"],
                "owner_clause": "unregistered professional task",
                "unresolved_question": "Which independently verified method fits this novel domain?",
                "competing_methods": [
                    {"name": "source_comparison",
                     "applicability": "Inspect original professional evidence.",
                     "failure_mode": "One source may be biased or stale.",
                     "falsifier": "Independent new evidence contradicts the claim."},
                    {"name": "independent_replication",
                     "applicability": "Repeat the observation using another method.",
                     "failure_mode": "A replicated method may share hidden errors.",
                     "falsifier": "Blind reference data falsify the observation."},
                ],
                "source_refs": [],
                "next_research_step": (
                    f"Investigate external reference approach number {index} independently."),
                "uncertainty": "None of these proposals establishes the owner outcome.",
            }
            receipt = record_native_open_research(
                self.db, self.workspace, self.fixtures, root, proposal)
            self.assertEqual(receipt["status"], "NATIVE_OPEN_RESEARCH_RECORDED")
        seen = []
        before = None
        for _ in range(6):
            state = inspect_native_goal(
                self.db, self.workspace, self.fixtures, root,
                research_before_event_id=before)
            self.assertEqual(state["open_research_count"], 70)
            page = state["open_research"]
            self.assertLessEqual(len(page), 16)
            seen.extend(item["event_id"] for item in page)
            before = state["open_research_next_before_event_id"]
            if before is None:
                break
        self.assertEqual(len(seen), 70)
        self.assertEqual(len(set(seen)), 70)
        self.assertEqual(seen, sorted(seen, reverse=True))
        latest = self.view(root)
        oldest = dict(proposal)
        oldest["next_research_step"] = (
            "Investigate external reference approach number 0 independently.")
        oldest["observation_sha256"] = latest["observation_sha256"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_NATIVE_OPEN_RESEARCH"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, oldest)
        self.assertEqual(self.view(root)["observation_sha256"],
                         latest["observation_sha256"])
        with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_RESEARCH_CURSOR"):
            inspect_native_goal(self.db, self.workspace, self.fixtures,
                                root, research_before_event_id=0)
        # Old untrustworthy receipts must NOT disappear from the validation
        # merely because they are no longer on the latest model-facing page.
        with closing(connect(self.db)) as db:
            db.execute(
                "UPDATE events SET details=json_set(details,"
                "'$.proposal.owner_clause','forged historical clause') "
                "WHERE event_id=?", (min(seen),))
            db.commit()
        self.assertEqual(self.view(root)["status"], "NATIVE_GOAL_UNVERIFIABLE")

    def test_open_research_cannot_bypass_revoked_effect_authority(self):
        root = register_native_goal(
            self.db, "Investigate an unregistered professional task")
        observed = self.view(root)
        proposal = {
            "observation_sha256": observed["observation_sha256"],
            "owner_clause": "unregistered professional task",
            "unresolved_question": "Which domain model should be validated?",
            "competing_methods": [
                {"name": "model_a", "applicability": "Check primary evidence.",
                 "failure_mode": "Sources may be incomplete.",
                 "falsifier": "Independent sample rejects the result."},
                {"name": "model_b", "applicability": "Measure with independent data.",
                 "failure_mode": "Tool accuracy is unknown.",
                 "falsifier": "External auditor rejects the measurement."},
            ],
            "source_refs": [],
            "next_research_step": "Locate primary professional specifications.",
            "uncertainty": "No tools or sources have yet been verified.",
        }
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaisesRegex(ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, proposal)

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

    def test_unchanged_hypothesis_is_not_repeated_as_ceremony_each_step(self):
        root = self.root_id()
        opening = self.view(root)
        record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="user", idea="Compare actual inputs before changing anything",
            observation_sha256=opening["observation_sha256"])
        fresh = self.view(root)
        proposal = self.candidate(fresh, self.reconcile(), self.structure())
        proposal["hypothesis_reviews"] = [{
            "proposal_sha256": fresh["hypotheses"][0]["proposal_sha256"],
            "disposition": "CONDITIONALLY_USEFUL",
            "counterargument": "A CSV comparison cannot establish downstream business truth.",
            "verification_needed": "Independently verify the source discrepancy report.",
        }]
        admit_native_decision(self.db, self.workspace, self.fixtures, root, proposal)
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        later = self.view(root)
        self.assertEqual(later["pending_hypotheses"], [])
        followup = self.candidate(later, self.structure(), self.reconcile())
        next_choice = admit_native_decision(
            self.db, self.workspace, self.fixtures, root, followup)
        self.assertEqual(next_choice["status"], "NATIVE_METHOD_ENQUEUED")
        self.assertEqual(self.view(root)["decision_count"], 2)

    def test_unresolved_research_survives_decision_and_worker_readback(self):
        """A challenged-but-UNRESOLVED original idea must not be forgotten.

        This checks the durable SQLite audit after an independently checked
        worker outcome. A one-time review is not research resolution.
        """
        root = self.root_id()
        opening = self.view(root)
        record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="user",
            idea="First verify whether the original supplier data is complete",
            observation_sha256=opening["observation_sha256"])
        current = self.view(root)
        unresolved = current["pending_hypotheses"][0]
        first = self.candidate(current, self.reconcile(), self.structure())
        first["hypothesis_reviews"] = [{
            "proposal_sha256": unresolved["proposal_sha256"],
            "disposition": "UNRESOLVED_RESEARCH_REQUIRED",
            "counterargument": "The given records may omit later supplier corrections.",
            "verification_needed": "Check independent supplier evidence before closure.",
        }]
        admit_native_decision(
            self.db, self.workspace, self.fixtures, root, first)
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)

        # Re-open through the public read-only audit, not the earlier
        # proposal's in-memory review. The unverified concern still exists.
        later = self.view(root)
        self.assertEqual(later["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE")
        # Cold resume must inherit WHY the previous method was chosen, what
        # could falsify it, and what remained unproven. Only the independent
        # mechanical verdict is observed, not the model's rationale.
        trace = later["decisions"][0]["research_trace"]
        self.assertEqual(trace["selected_reason"], first["decision_reason"])
        self.assertEqual(trace["alternative_reason"], first["alternative_reason"])
        self.assertEqual(trace["falsifier"], first["decision_basis"]["falsifier"])
        self.assertEqual(trace["source_refs"], first["decision_basis"]["source_refs"])
        self.assertEqual(trace["semantic_verdict"], "UNVERIFIED_MODEL_ARGUMENTS")
        self.assertEqual(trace["hypothesis_reviews"], first["hypothesis_reviews"])
        self.assertEqual(later["decisions"][0]["mechanical_verdict"],
                         "REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual(
            [h["proposal_sha256"] for h in later["pending_hypotheses"]],
            [unresolved["proposal_sha256"]])
        second = self.candidate(later, self.structure(), self.reconcile())
        with self.assertRaisesRegex(
                ValueError, "NATIVE_HYPOTHESES_NOT_CHALLENGED"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root, second)
        second["hypothesis_reviews"] = [{
            "proposal_sha256": unresolved["proposal_sha256"],
            "disposition": "CONDITIONALLY_USEFUL",
            "counterargument": "The local discrepancy report does not prove source completeness.",
            "verification_needed": "Seek independent later supplier updates before outcome closure.",
        }]
        # Re-labeling an UNRESOLVED hypothesis in model-written prose is NOT
        # fresh research evidence. The independently verified Worker report
        # proves only a local CSV discrepancy, not supplier completeness.
        with self.assertRaisesRegex(
                ValueError, "UNRESOLVED_HYPOTHESIS_NO_NEW_EVIDENCE"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root, second)
        self.assertEqual(self.view(root)["decision_count"], 1)
        self.assertEqual(len(self.view(root)["pending_hypotheses"]), 1)

        # A new externally supplied source becomes a live, hash-pinned input,
        # independently re-read by the normal admission transaction. It
        # allows a NEW provisional disposition, never source truth or an
        # independent full-owner/business-success claim.
        (self.fixtures / "supplier_update.md").write_text(
            "External follow-up: inventory snapshots may omit late returns.\\n",
            encoding="utf-8")
        with_new_evidence = self.view(root)
        self.assertEqual(len(with_new_evidence["pending_hypotheses"]), 1)
        reconsidered = self.candidate(
            with_new_evidence, self.structure(), self.reconcile())
        reconsidered["hypothesis_reviews"] = [{
            "proposal_sha256": unresolved["proposal_sha256"],
            "disposition": "CONDITIONALLY_USEFUL",
            "counterargument": "New source warns that the supplier snapshot may omit returns.",
            "verification_needed": "An independent supplier owner must confirm final completeness.",
        }]
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root, reconsidered)
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED")
        # A freshly hash-pinned source is NEW EVIDENCE, not an oracle.
        # It may justify another method attempt, but must not silently
        # erase the original supplier-completeness doubt. This also
        # defeats the adversarial "add irrelevant.md and cite it" bypass.
        pending = self.view(root)["pending_hypotheses"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending[0]["proposal_sha256"], unresolved["proposal_sha256"])
        self.assertFalse(self.view(root)["owner_outcome_verified"])
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)

        # Source update was already reviewed in the SECOND decision.
        # The THIRD decision must not reuse that same update indefinitely
        # as "new evidence" to re-label the unresolved question again.
        after_review = self.view(root)
        self.assertEqual(len(after_review["pending_hypotheses"]), 1)
        # Select an UNUSED, eligible research family so the independent
        # duplicate-method guard cannot be the reason this test passes.
        # This is a separate research path, not a second CSV/JSON retry.
        recycled = self.candidate(
            after_review,
            {"kind": "goal_intent", "objective": "investigate_evidence",
             "resources": [],
             "question": "Are late supplier returns missing from stock snapshots?"},
            self.structure())
        recycled["hypothesis_reviews"] = [{
            "proposal_sha256": unresolved["proposal_sha256"],
            "disposition": "REJECTED",
            "counterargument": "Already-cited late-returns note supposedly settles stock records.",
            "verification_needed": "Independent supplier confirmation remains unavailable.",
        }]
        with self.assertRaisesRegex(
                ValueError, "UNRESOLVED_HYPOTHESIS_NO_NEW_EVIDENCE"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root, recycled)
        self.assertEqual(self.view(root)["decision_count"], 2)
        self.assertEqual(len(self.view(root)["pending_hypotheses"]), 1)

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

    def test_cold_process_native_cli_challenges_untrusted_user_method(self):
        common = [sys.executable, "-m", "cognition_agent_os.cli",
                  "--db", str(self.db), "--workspace", str(self.workspace),
                  "--fixtures", str(self.fixtures)]
        root = self.root_id()
        initial = json.loads(subprocess.run(
            [*common, "native-goal-readback", "--root-task-id", root],
            check=True, capture_output=True, text=True).stdout)
        result = subprocess.run([
            *common, "native-hypothesis", "--root-task-id", root,
            "--origin", "user", "--idea",
            "Assume the discrepancy is harmless without checking originals",
            "--observation-sha256", initial["observation_sha256"],
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"],
                         "NATIVE_HYPOTHESIS_RECORDED")
        recovered = json.loads(subprocess.run(
            [*common, "native-goal-readback", "--root-task-id", root],
            check=True, capture_output=True, text=True).stdout)
        self.assertEqual(recovered["original_goal"], self.goal)
        self.assertEqual(recovered["hypotheses"][0]["claimed_origin"], "user")
        self.assertFalse((self.workspace / "artifacts").exists())
        self.assertNotEqual(initial["observation_sha256"],
                            recovered["observation_sha256"])

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

    def test_source_drift_accepts_causal_hypothesis_without_resuming_action(self):
        root = self.root_id()
        admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), self.reconcile(), self.structure()))
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,4\n", encoding="utf-8")
        drift = self.view(root)
        self.assertEqual(drift["status"], "NATIVE_SOURCE_CHANGED")
        recorded = record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="agent", idea="Maybe the supplier changed its stock version",
            observation_sha256=drift["research_reentry_sha256"])
        self.assertEqual(recorded["status"], "NATIVE_HYPOTHESIS_RECORDED")
        self.assertFalse(recorded["authorizes_action"])
        self.assertFalse(recorded["origin_authenticated"])
        resumed = self.view(root)
        self.assertEqual(resumed["status"], "NATIVE_SOURCE_CHANGED")
        self.assertNotEqual(resumed["research_reentry_sha256"],
                            drift["research_reentry_sha256"])
        self.assertEqual(len(resumed["hypotheses"]), 1)
        with self.assertRaisesRegex(ValueError, "NATIVE_STALE_OBSERVATION"):
            record_native_hypothesis(
                self.db, self.workspace, self.fixtures, root,
                origin="agent", idea="Maybe another timestamp is wrong",
                observation_sha256=drift["research_reentry_sha256"])
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaises(PermissionError):
            record_native_hypothesis(
                self.db, self.workspace, self.fixtures, root,
                origin="agent", idea="Maybe a third unrelated source is wrong",
                observation_sha256=self.view(root)["research_reentry_sha256"])
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 1)

    def test_source_drift_allows_only_research_with_fresh_cas(self):
        root = self.root_id()
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), self.reconcile(), self.structure()))
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,1\n", encoding="utf-8")
        note = self.fixtures / "followup.md"
        note.write_text("Conflicting supplier revisions need independent tracing.",
                        encoding="utf-8")
        blocked = self.view(root)
        self.assertEqual(blocked["status"], "NATIVE_SOURCE_CHANGED")
        self.assertNotIn("observation_sha256", blocked)
        self.assertFalse(blocked["authorizes_action"])
        self.assertRegex(blocked["research_reentry_sha256"], r"^[a-f0-9]{64}$")
        proposal = {
            "observation_sha256": blocked["research_reentry_sha256"],
            "owner_clause": "Reconcile a supplier stock shortfall",
            "unresolved_question": "Which supplier revision caused the conflict?",
            "competing_methods": [
                {"name": "original_recheck",
                 "applicability": "Crosscheck immutable supplier originals.",
                 "failure_mode": "Archived originals may also be incomplete.",
                 "falsifier": "Signed supplier update contradicts originals."},
                {"name": "external_audit",
                 "applicability": "Seek separately verified vendor records.",
                 "failure_mode": "The external source may not be independent.",
                 "falsifier": "Third party audit contradicts external data."}],
            "source_refs": [{"path": note.name,
                             "sha256": hashlib.sha256(note.read_bytes()).hexdigest()}],
            "next_research_step": "Inspect the primary supplier version history.",
            "uncertainty": "Neither research route has independent outcome evidence.",
        }
        # Real MCP tool body over the single SQLite authority; only
        # the MCP SDK registration layer is simulated.
        from cognition_agent_os.native_mcp_bridge import build_mcp_server
        class _McpShim:
            def __init__(self, name):
                self.tools = {}
            def tool(self):
                def register(func):
                    self.tools[func.__name__] = func
                    return func
                return register
        fake = types.ModuleType("mcp")
        fake_server = types.ModuleType("mcp.server")
        fake_server.MCPServer = _McpShim
        with patch.dict(sys.modules, {"mcp": fake, "mcp.server": fake_server}):
            service = build_mcp_server(
                self.db, self.workspace, self.fixtures,
                allow_goal_writes=True)
        observed = service.tools["native_goal_inspect"](root)
        self.assertEqual(observed["research_reentry_sha256"],
                         blocked["research_reentry_sha256"])
        recorded = service.tools["native_open_research_record"](root, proposal)
        self.assertEqual(recorded["status"], "NATIVE_OPEN_RESEARCH_RECORDED")
        self.assertFalse(recorded["authorizes_action"])
        resumed = service.tools["native_goal_inspect"](root)
        self.assertEqual(resumed["status"], "NATIVE_SOURCE_CHANGED")
        self.assertEqual(resumed["open_research_count"], 1)
        self.assertEqual(len(resumed["open_research"]), 1)
        self.assertEqual(resumed["open_research"][0]["source_status"],
                         "SOURCE_PIN_CURRENT_UNVERIFIED_SEMANTICS")
        self.assertFalse(resumed["open_research"][0]["authorizes_action"])
        self.assertNotIn("observation_sha256", resumed)
        self.assertNotEqual(resumed["research_reentry_sha256"],
                            blocked["research_reentry_sha256"])
        with self.assertRaisesRegex(ValueError, "NATIVE_STALE_OBSERVATION"):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, proposal)
        with self.assertRaisesRegex(ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
            admit_native_decision(
                self.db, self.workspace, self.fixtures, root,
                {"observation_sha256": "f" * 64})
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 1)
        self.assertEqual(admitted["selected_objective"], "compare_records")
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        newer = dict(proposal)
        newer["observation_sha256"] = self.view(root)["research_reentry_sha256"]
        with self.assertRaises(PermissionError):
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, newer)

    def test_source_drift_research_page_recovers_all_history(self):
        root = self.root_id()
        admit_native_decision(
            self.db, self.workspace, self.fixtures, root,
            self.candidate(self.view(root), self.reconcile(), self.structure()))
        (self.fixtures / "observed.csv").write_text(
            "supplier,received\nDelta,7\n", encoding="utf-8")
        for index in range(18):
            state = self.view(root)
            self.assertEqual(state["status"], "NATIVE_SOURCE_CHANGED")
            proposal = {
                "observation_sha256": state["research_reentry_sha256"],
                "owner_clause": "Reconcile a supplier stock shortfall",
                "unresolved_question": "Which source revision is trustworthy?",
                "competing_methods": [
                    {"name": "ledger_check",
                     "applicability": "Inspect immutable original records.",
                     "failure_mode": "Original file may already be incomplete.",
                     "falsifier": "Independent vendor signed record disagrees."},
                    {"name": "vendor_probe",
                     "applicability": "Compare independent vendor source reports.",
                     "failure_mode": "Vendor report may share the same input.",
                     "falsifier": "Independent third party audit disagrees."}],
                "source_refs": [],
                "next_research_step": (
                    f"Check external revision and negative control {index}."),
                "uncertainty": "External effect has not yet been independently tested.",
            }
            record_native_open_research(
                self.db, self.workspace, self.fixtures, root, proposal)
        first = self.view(root)
        self.assertEqual(first["open_research_count"], 18)
        self.assertEqual(len(first["open_research"]), 16)
        self.assertIsNotNone(first["open_research_next_before_event_id"])
        second = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root,
            research_before_event_id=first["open_research_next_before_event_id"])
        self.assertEqual(len(second["open_research"]), 2)
        self.assertIsNone(second["open_research_next_before_event_id"])
        all_ids = [x["event_id"] for x in first["open_research"]]
        all_ids += [x["event_id"] for x in second["open_research"]]
        self.assertEqual(all_ids, sorted(all_ids, reverse=True))
        self.assertEqual(len(set(all_ids)), 18)
        self.assertNotIn("observation_sha256", first)
        self.assertNotIn("observation_sha256", second)

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
        observation = self.view(root)
        self.assertEqual(observation["status"], "NATIVE_SOURCE_CHANGED")
        # A new unrelated research note cannot conceal the modified primary fact.
        self.assertEqual(observation["invalidated_source_paths"], ["observed.csv"])
        self.assertEqual(observation["reopen_decision_ordinal"], 0)
        self.assertFalse(observation["owner_outcome_verified"])

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
        self.assertEqual(drift["invalidated_source_paths"], ["observed.csv"])
        self.assertEqual(drift["reopen_decision_ordinal"], 0)
        self.assertEqual(drift["reopen_scope"], "SOURCE_AND_METHOD_CAUSAL_REEXAMINATION")
        self.assertTrue(drift["affected_decision_event_ids"])
        self.assertNotIn("observation_sha256", drift)
        self.assertFalse(drift["owner_outcome_verified"])
        from cognition_agent_os.host import _goal_progress
        host_view = _goal_progress(self.db, self.workspace, self.fixtures)
        reported = next(x for x in host_view["goals"]
                        if x["root_task_id"] == root)
        self.assertEqual(reported["next_control_action"],
                         "REOPEN_NATIVE_CAUSAL_SOURCE_REVIEW")
        self.assertEqual(reported["reopen_source_paths"], ["observed.csv"])
        self.assertEqual(reported["reopen_decision_ordinal"], 0)
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
