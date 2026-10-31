"""Installed-model optional native cognition over REAL Host and SQLite.

Ollama transport is mocked only where CI lacks an installed local model.
These tests establish admission/routing/worker/recovery behavior, NOT that a
real local LLM understands novel owner objectives or passes semantic acceptance.
"""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, record_native_hypothesis)
from cognition_agent_os.native_local_planner import advance_native_local_once


class NativeLocalModelLoop(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "state.sqlite"
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        self.workspace = self.root / "work"
        self.workspace.mkdir()
        (self.fixtures / "reference.csv").write_text(
            "item,expected\nA,7\n", encoding="utf-8")
        (self.fixtures / "observed.csv").write_text(
            "item,expected\nA,5\n", encoding="utf-8")
        (self.fixtures / "handoff.json").write_text(
            '{"original":"keep"}\n', encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
        self.goal = (
            "Investigate the actual inventory discrepancy, compare the "
            "original records, and prepare a local JSON audit handoff without "
            "changing any original files or production access."
        )

    @staticmethod
    def compare():
        return {"kind": "goal_intent", "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": "reference.csv"},
                    {"role": "observed", "path": "observed.csv"}]}

    @staticmethod
    def ensure():
        return {"kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "handoff.json"}],
                "requirements": [{"field": "audited", "equals": "yes"}]}

    @staticmethod
    def basis_from_evidence(evidence):
        refs = [{"path": p, "sha256": sha}
                for p, sha in sorted(evidence["source_digest_manifest"].items())]
        past = evidence["past_methods_and_independent_verdicts"]
        return {
            "source_refs": refs,
            "previous_result_task_id": past[-1]["task_id"] if past else None,
            "challenge": "An apparently valid source comparison may still miss the owner result.",
            "falsifier": "Independent artifact readback or changed source facts must invalidate this selection.",
            "uncertainty": "The selected method cannot prove the entire business outcome.",
        }

    def basis_for_root(self, root):
        from cognition_agent_os.native_decision import _sources
        source = _sources(self.fixtures)
        state = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        return self.basis_from_evidence({
            "source_digest_manifest": source,
            "past_methods_and_independent_verdicts": state["decisions"],
        })

    def transport(self, method, path, payload, timeout):
        if method == "GET":
            return {"models": [{"name": "installed:test"}]}
        self.assertEqual(method, "POST")
        self.assertEqual(payload["model"], "installed:test")
        self.assertFalse(payload["stream"])
        self.assertIn(self.goal, payload["prompt"])
        self.assertIn("original_owner_goal", payload["prompt"])
        self.assertIn("past_methods_and_independent_verdicts", payload["prompt"])
        self.assertIn("registered_local_methods", payload["prompt"])
        self.assertIn("untrusted_excerpt", payload["prompt"])
        self.assertNotIn("production_mutation_authorized", payload["prompt"])
        # A real model would supply these, not a preset script.
        history = json.loads(payload["prompt"].split("\n\n")[-1])
        prior = len(history["past_methods_and_independent_verdicts"])
        self.assertIn("verified_prior_results", history)
        if prior:
            verified = history["verified_prior_results"]
            self.assertEqual(len(verified), 1, history)
            self.assertEqual(verified[0]["mechanical_verdict"],
                             "REPORT_MECHANICALLY_VERIFIED")
            self.assertIn("discrepancies",
                          verified[0]["untrusted_verified_result_excerpt"])
            self.assertRegex(verified[0]["artifact_sha256"], r"^[a-f0-9]{64}$")
        else:
            self.assertEqual(history["verified_prior_results"], [])
        selected = self.compare() if prior == 0 else self.ensure()
        alternative = self.ensure() if prior == 0 else self.compare()
        answer = {
            "decision_basis": self.basis_from_evidence(history),
            "selected_intent": selected, "alternative_intent": alternative,
            "decision_reason": "Read the original evidence before preparing handoff.",
            "alternative_reason": "The other method cannot do the first evidence step.",
            "expected_evidence": "Independent local audit of this specific result.",
            "observation_sha256": history["observation_sha256"],
        }
        if history["proposed_method_ideas_to_challenge"]:
            answer["hypothesis_reviews"] = [{
                "proposal_sha256": item["proposal_sha256"],
                "disposition": ("REJECTED" if item["claimed_origin"] == "user"
                                else "CONDITIONALLY_USEFUL"),
                "counterargument": "Neither proposal alone establishes the owner result.",
                "verification_needed": "Read original evidence and independently check results.",
            } for item in history["proposed_method_ideas_to_challenge"]]
        return {"done": True, "response": json.dumps(answer)}

    def test_autonomous_host_does_not_lose_new_owner_beneath_legacy_limit(self):
        """Long-lived shared ledger must schedule actual native roots first.

        A page of unrelated earlier top-level tasks must not consume the
        planner's finite scan window and silently starve a newer owner goal.
        The mocked call checks selection only, not model intelligence.
        """
        from cognition_agent_os.ledger import create_task
        from cognition_agent_os.native_local_planner import advance_native_local_goals
        with closing(connect(self.db)) as db:
            for ordinal in range(132):
                create_task(db, {"kind": "fixture", "ordinal": ordinal},
                            commit=False)
            # Competing nonnative parent workflows can also reach the
            # DECOMPOSED state; that is exactly what used to occupy every
            # slot before the planner even checked the native type.
            db.execute("UPDATE tasks SET state='DECOMPOSED' "
                       "WHERE parent_task IS NULL AND state='PENDING'")
            db.commit()
        native = register_native_goal(self.db, self.goal)
        with patch("cognition_agent_os.native_local_planner.advance_native_adaptive_once",
                   return_value={"status": "NATIVE_TEST_SELECTED",
                                 "root_task_id": native}) as planner:
            chosen = advance_native_local_goals(
                self.db, self.workspace, self.fixtures,
                model="installed:test", limit=1)
        self.assertEqual(chosen, [{
            "status": "NATIVE_TEST_SELECTED",
            "root_task_id": native}])
        planner.assert_called_once_with(
            self.db, self.workspace, self.fixtures, native,
            model="installed:test")

    def test_old_invalid_native_roots_cannot_hide_later_owner_after_page_128(self):
        """Real SQLite scan must not stop at first 128 DECOMPOSED native rows."""
        from cognition_agent_os.ledger import create_task
        from cognition_agent_os.native_local_planner import advance_native_local_goals
        with closing(connect(self.db)) as db:
            for ordinal in range(132):
                create_task(db, {"kind": "native_goal", "old_invalid": ordinal},
                            commit=False)
            db.execute("UPDATE tasks SET state='DECOMPOSED' "
                       "WHERE parent_task IS NULL AND state='PENDING'")
            db.commit()
        valid = register_native_goal(self.db, self.goal)
        with patch("cognition_agent_os.native_local_planner.advance_native_adaptive_once",
                   return_value={"status": "NATIVE_METHOD_ENQUEUED",
                                 "root_task_id": valid}) as planner, patch(
                   "cognition_agent_os.native_local_planner.inspect_native_goal",
                   wraps=inspect_native_goal) as audit:
            chosen = advance_native_local_goals(
                self.db, self.workspace, self.fixtures,
                model="installed:test", limit=1)
        # The unreadable old rows must not each trigger an expensive
        # audit or occupy the planner budget. Only the registered root
        # reaches actual source/owner-lineage reattestation.
        audit.assert_called_once()
        self.assertEqual(chosen[0]["root_task_id"], valid)
        planner.assert_called_once_with(
            self.db, self.workspace, self.fixtures, valid,
            model="installed:test")

    def test_model_reuses_unchanged_failure_to_schedule_another_owner(self):
        """A known failed first method is evidence, not a permanent queue head."""
        from cognition_agent_os.native_local_planner import advance_native_local_goals
        older = [register_native_goal(self.db, self.goal) for _ in range(3)]
        fresh = register_native_goal(self.db, self.goal)
        def prior(_db, root, _obs, _model):
            return ["FAILED", "FAILED"] if root in older else []
        with patch("cognition_agent_os.native_local_planner._previous_no_progress",
                   side_effect=prior), patch(
                   "cognition_agent_os.native_local_planner.advance_native_adaptive_once",
                   return_value={"status": "NATIVE_METHOD_ENQUEUED",
                                 "root_task_id": fresh}) as planner:
            selected = advance_native_local_goals(
                self.db, self.workspace, self.fixtures,
                model="installed:test", limit=1)
        self.assertEqual(selected[0]["root_task_id"], fresh)
        planner.assert_called_once_with(
            self.db, self.workspace, self.fixtures, fresh,
            model="installed:test")

    def test_durable_open_research_is_available_to_next_model_decision(self):
        """A saved competing-method study is useful only if a later planner reads it.

        The stored study is UNTRUSTED, source-pinned research, not an action
        grant or an independent owner outcome. No second model or store.
        """
        from cognition_agent_os.native_decision import (
            record_native_open_research, _sources)
        root = register_native_goal(self.db, self.goal)
        current = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        sources = _sources(self.fixtures)
        study = {
            "observation_sha256": current["observation_sha256"],
            "owner_clause": "actual inventory discrepancy",
            "unresolved_question":
                "Should reference evidence or a secondary physical count guide correction?",
            "competing_methods": [
                {"name": "record_crosscheck",
                 "applicability": "Compare independent original transaction records.",
                 "failure_mode": "Two records may share a data collection error.",
                 "falsifier": "Independent verified counts contradict both records."},
                {"name": "physical_recount",
                 "applicability": "Use a separately validated physical stock tally.",
                 "failure_mode": "The physical count may be stale or incomplete.",
                 "falsifier": "Repeat blind counts disagree with the suggested tally."},
            ],
            "source_refs": [
                {"path": "reference.csv", "sha256": sources["reference.csv"]}],
            "next_research_step":
                "Check whether the independent source can distinguish shared bias.",
            "uncertainty":
                "No physical stock effect or external business outcome has been checked.",
        }
        record_native_open_research(
            self.db, self.workspace, self.fixtures, root, study)
        viewed = []
        def model(method, path, payload, timeout):
            if method == "POST":
                evidence = json.loads(payload["prompt"].split("\n\n")[-1])
                viewed.append(evidence)
            return self.transport(method, path, payload, timeout)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=model):
            admitted = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED", admitted)
        self.assertEqual(len(viewed), 1)
        self.assertEqual(viewed[0]["prior_open_research_total_count"], 1)
        self.assertFalse(viewed[0]["prior_open_research_index_truncated"])
        recorded = viewed[0]["untrusted_prior_open_research"][0]
        self.assertEqual(recorded["source_status"],
                         "SOURCE_PIN_CURRENT_UNVERIFIED_SEMANTICS")
        self.assertEqual(recorded["competing_methods"],
                         study["competing_methods"])
        self.assertNotIn("authorizes_action", recorded)
        self.assertFalse(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["owner_outcome_verified"])

    def test_research_reads_multiple_distinct_evidence_rounds_before_choice(self):
        """The model may ask for more actual evidence without a preset one-read cutoff.

        This checks the real native proposal -> SQLite admission boundary,
        not whether a mocked model can independently understand the domain.
        """
        (self.fixtures / "trace.md").write_text("A" * 2800 + "B" * 2800,
                                                encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        observed = []
        def research(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            evidence = json.loads(payload["prompt"].split("\n\n")[-1])
            excerpts = evidence.get("additional_verified_source_excerpts", [])
            observed.append([(p["path"], p["offset_chars"]) for p in excerpts])
            if not excerpts:
                return {"done": True, "response": json.dumps({
                    "inspect_sources": [{"path": "trace.md", "offset_chars": 500}]})}
            if len(excerpts) == 1:
                self.assertEqual(excerpts[0]["untrusted_excerpt"], "A" * 2048)
                return {"done": True, "response": json.dumps({
                    "inspect_sources": [{"path": "trace.md", "offset_chars": 3100}]})}
            self.assertEqual(excerpts[1]["untrusted_excerpt"], "B" * 2048)
            return self.transport(method, path, payload, timeout)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=research) as provider:
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_METHOD_ENQUEUED", result)
        self.assertEqual(observed, [
            [], [("trace.md", 500)],
            [("trace.md", 500), ("trace.md", 3100)]])
        self.assertEqual(provider.call_count, 4)  # 1 installed GET + 3 POST
        self.assertEqual(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["decision_count"], 1)

    def test_research_cannot_loop_on_identical_observation(self):
        """An unchanged source offset must not induce endless model requests."""
        (self.fixtures / "trace.md").write_text("evidence " * 500,
                                                encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        def repeat(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            return {"done": True, "response": json.dumps({
                "inspect_sources": [{"path": "trace.md", "offset_chars": 500}]})}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=repeat) as provider:
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_PLAN_REFUSED", result)
        self.assertIn("NATIVE_RESEARCH_NO_NEW_EVIDENCE", result["reason"])
        self.assertEqual(provider.call_count, 3)  # 1 GET + 2 POST
        self.assertEqual(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["decision_count"], 0)

    def test_research_read_checkpoint_survives_interrupted_model_turn(self):
        """Evidence reads must survive a stopped turn without saving raw text.

        The transport here is scripted, but state/authority/events are real.
        """
        (self.fixtures / "trace.md").write_text("A" * 2800 + "B" * 2800,
                                                encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        calls = []
        def interrupted(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            history = json.loads(payload["prompt"].split("\n\n")[-1])
            calls.append(history.get("additional_verified_source_excerpts", []))
            if len(calls) == 1:
                return {"done": True, "response": json.dumps({
                    "inspect_sources": [{"path": "trace.md", "offset_chars": 500}]})}
            raise RuntimeError("INTERRUPTED_AFTER_EVIDENCE_READ")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "INTERRUPTED_AFTER"):
                advance_native_local_once(
                    self.db, self.workspace, self.fixtures, root,
                    model="installed:test")
        self.assertEqual(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["decision_count"], 0)
        with closing(connect(self.db)) as db:
            saved = [json.loads(row[0]) for row in db.execute(
                "SELECT details FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ'", (root,))]
        self.assertEqual(len(saved), 1)
        self.assertNotIn("untrusted_excerpt", saved[0])
        self.assertEqual(saved[0]["offset_chars"], 500)
        resumed = []
        def resume(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            history = json.loads(payload["prompt"].split("\n\n")[-1])
            excerpts = history.get("additional_verified_source_excerpts", [])
            resumed.append([(x["path"], x["offset_chars"]) for x in excerpts])
            if len(excerpts) == 1:
                self.assertEqual(excerpts[0]["untrusted_excerpt"], "A" * 2048)
                return {"done": True, "response": json.dumps({
                    "inspect_sources": [{"path": "trace.md", "offset_chars": 3100}]})}
            return self.transport(method, path, payload, timeout)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=resume):
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_METHOD_ENQUEUED", result)
        self.assertEqual(resumed, [
            [("trace.md", 500)],
            [("trace.md", 500), ("trace.md", 3100)]])
        with closing(connect(self.db)) as db:
            saved = [json.loads(row[0]) for row in db.execute(
                "SELECT details FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ'", (root,))]
        self.assertEqual(len(saved), 2)

    def test_forged_research_checkpoint_never_becomes_model_evidence(self):
        """A fabricated prior hash must fail before another model decision."""
        (self.fixtures / "trace.md").write_text("safe reference " * 300,
                                                encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        state = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        from cognition_agent_os.ledger import event
        with closing(connect(self.db)) as db:
            event(db, root, "NATIVE_LOCAL_RESEARCH_READ", {
                "observation_sha256": state["observation_sha256"],
                "model": "installed:test", "path": "trace.md",
                "sha256": "0" * 64, "offset_chars": 500,
                "length_chars": 2048})
            db.commit()
        with patch("cognition_agent_os.local_model._request") as model:
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_PLAN_REFUSED", result)
        self.assertIn("NATIVE_RESEARCH_CHECKPOINT_UNVERIFIABLE", result["reason"])
        model.assert_not_called()
        self.assertEqual(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["decision_count"], 0)

    def test_many_checkpoint_reads_resume_with_lazy_provenance_index(self):
        """History must be durable without replaying all excerpts as context."""
        import hashlib
        from cognition_agent_os.ledger import event
        from cognition_agent_os.native_decision import _sources
        (self.fixtures / "trace.md").write_text("Z" * 18_000,
                                                encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        state = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        digest = _sources(self.fixtures)["trace.md"]
        with closing(connect(self.db)) as db:
            for offset in (0, 2100, 4200, 6300, 8400, 10500, 12600):
                event(db, root, "NATIVE_LOCAL_RESEARCH_READ", {
                    "observation_sha256": state["observation_sha256"],
                    "model": "installed:test", "path": "trace.md",
                    "sha256": digest, "offset_chars": offset,
                    "length_chars": 2048})
            db.commit()
        observed = []
        def research(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            history = json.loads(payload["prompt"].split("\n\n")[-1])
            indexed = history.get("prior_research_receipts", [])
            visible = history.get("additional_verified_source_excerpts", [])
            self.assertEqual(len(indexed), 7)
            self.assertLessEqual(len(visible), 3)
            observed.append([(x["path"], x["offset_chars"]) for x in visible])
            if len(observed) == 1:
                # Review already-pinned evidence without fabricating new discovery.
                return {"done": True, "response": json.dumps({
                    "inspect_sources": [{"path": "trace.md", "offset_chars": 0}]})}
            self.assertIn(("trace.md", 0), observed[1])
            return self.transport(method, path, payload, timeout)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=research):
            planned = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(planned["status"], "NATIVE_METHOD_ENQUEUED", planned)
        self.assertEqual(len(observed), 2)
        with closing(connect(self.db)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ'", (root,)
            ).fetchone()[0]
        self.assertEqual(count, 7)  # recall != new independent evidence

    def test_research_checkpoint_not_forgotten_after_128_unrelated_events(self):
        """Cold resume filters OWNER+OBSERVATION+MODEL before any bounded read."""
        import hashlib
        from cognition_agent_os.ledger import event
        from cognition_agent_os.native_local_planner import (
            _recovered_research_reads, _checkpoint_research_reads)
        (self.fixtures / "trace.md").write_text("X" * 6000, encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        snap = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        model = "installed:test"
        sha = hashlib.sha256(
            (self.fixtures / "trace.md").read_bytes()).hexdigest()
        receipt = {
            "observation_sha256": snap["observation_sha256"],
            "model": model,
            "path": "trace.md", "sha256": sha,
            "offset_chars": 500, "length_chars": 2048,
        }
        with closing(connect(self.db)) as db:
            event(db, root, "NATIVE_LOCAL_RESEARCH_READ", receipt)
            for idx in range(140):
                event(db, root, "NATIVE_LOCAL_RESEARCH_READ", {
                    **receipt,
                    "observation_sha256": "f" * 64,
                    "model": "unrelated-model:" + str(idx),
                })
            db.commit()
        sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in self.fixtures.iterdir()}
        recovered = _recovered_research_reads(
            self.db, self.fixtures, root,
            snap["observation_sha256"], model, sources)
        self.assertEqual(
            [(x["path"], x["offset_chars"]) for x in recovered],
            [("trace.md", 500)])
        # If a caller repeats the known range after losing its response,
        # the single authoritative receipt remains idempotent, not "new".
        _checkpoint_research_reads(
            self.db, self.workspace, self.fixtures, root,
            snap["observation_sha256"], model, [{
                "path": "trace.md", "sha256": sha,
                "offset_chars": 500, "untrusted_excerpt": "X" * 2048,
            }])
        with closing(connect(self.db)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ' "
                "AND json_extract(details,'$.observation_sha256')=? "
                "AND json_extract(details,'$.model')=?",
                (root, snap["observation_sha256"], model)).fetchone()[0]
        self.assertEqual(count, 1)

    def test_forged_research_checkpoint_cannot_be_hidden_by_unrelated_tail(self):
        """Truncation must not hide a corrupted CURRENT claim from the verifier."""
        import hashlib
        from cognition_agent_os.ledger import event
        from cognition_agent_os.native_local_planner import _recovered_research_reads
        (self.fixtures / "trace.md").write_text("Z" * 4200, encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        snap = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        current = snap["observation_sha256"]
        with closing(connect(self.db)) as db:
            event(db, root, "NATIVE_LOCAL_RESEARCH_READ", {
                "observation_sha256": current, "model": "installed:test",
                "path": "trace.md", "sha256": "0" * 64,
                "offset_chars": 500, "length_chars": 2048})
            for idx in range(140):
                event(db, root, "NATIVE_LOCAL_RESEARCH_READ", {
                    "observation_sha256": "e" * 64, "model": f"other:{idx}",
                    "path": "trace.md", "sha256": "0" * 64,
                    "offset_chars": 500, "length_chars": 2048})
            db.commit()
        sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in self.fixtures.iterdir()}
        with self.assertRaisesRegex(
                ValueError, "NATIVE_RESEARCH_CHECKPOINT_UNVERIFIABLE"):
            _recovered_research_reads(
                self.db, self.fixtures, root,
                current, "installed:test", sources)

    def test_durable_research_over_24_reads_keeps_history_but_limits_context(self):
        """Do not mistake a prompt-preview cap for a lifetime memory cap."""
        import hashlib
        from cognition_agent_os.ledger import event
        from cognition_agent_os.native_local_planner import _recovered_research_reads
        (self.fixtures / "trace.md").write_text(
            "Q" * 62_000, encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        observation = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["observation_sha256"]
        sha = hashlib.sha256(
            (self.fixtures / "trace.md").read_bytes()).hexdigest()
        with closing(connect(self.db)) as db:
            for ordinal in range(26):
                event(db, root, "NATIVE_LOCAL_RESEARCH_READ", {
                    "observation_sha256": observation,
                    "model": "installed:test",
                    "path": "trace.md",
                    "sha256": sha, "offset_chars": ordinal * 2100,
                    "length_chars": 2048,
                })
            db.commit()
        sources = {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                   for x in self.fixtures.iterdir()}
        recovered = _recovered_research_reads(
            self.db, self.fixtures, root, observation,
            "installed:test", sources)
        self.assertEqual(len(recovered), 26)
        self.assertEqual(recovered[0]["offset_chars"], 0)
        self.assertEqual(recovered[-1]["offset_chars"], 52_500)
        def agent(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            context = json.loads(payload["prompt"].split("\n\n")[-1])
            self.assertEqual(
                context["prior_research_total_count"], 26)
            self.assertTrue(context["research_history_index_truncated"])
            self.assertLessEqual(len(context["prior_research_receipts"]), 24)
            self.assertLessEqual(len(context.get(
                "additional_verified_source_excerpts", [])), 2)
            # The complete source history is still checked for duplicates
            # despite only a finite amount of metadata reaching the model.
            return {"done": True, "response": '{"abstain":true}'}
        with patch("cognition_agent_os.local_model._request", side_effect=agent):
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_MODEL_ABSTAINED")
        with closing(connect(self.db)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ'", (root,)
            ).fetchone()[0]
            self.assertEqual(count, 26)
        self.assertFalse(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)[
                "owner_outcome_verified"])

    def test_no_progress_abstention_remains_enforced_after_unrelated_events(self):
        """The retry guard is persistent by exact model/evidence identity."""
        from cognition_agent_os.ledger import event
        root = register_native_goal(self.db, self.goal)
        snapshot = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        current = snapshot["observation_sha256"]
        with closing(connect(self.db)) as db:
            event(db, root, "NATIVE_LOCAL_NO_PROGRESS", {
                "observation_sha256": current,
                "model": "installed:test",
                "reason": "MODEL_ABSTAINED",
                "owner_outcome_verified": False,
            })
            for idx in range(70):
                event(db, root, "NATIVE_LOCAL_NO_PROGRESS", {
                    "observation_sha256": "f" * 64,
                    "model": "other:" + str(idx),
                    "reason": "OTHER_MODEL_UNRELATED_FAILURE",
                    "owner_outcome_verified": False,
                })
            db.commit()
        with patch("cognition_agent_os.local_model._request") as model:
            answer = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(answer["status"],
                         "NATIVE_LOCAL_UNCHANGED_EVIDENCE_REFUSED")
        model.assert_not_called()
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?", (root,)
            ).fetchone()[0], 0)

    def test_retried_research_checkpoint_is_idempotent_at_sqlite_boundary(self):
        """Same verified observation reread by a retry must leave one receipt."""
        from cognition_agent_os.native_local_planner import (
            _checkpoint_research_reads, _recovered_research_reads)
        from cognition_agent_os.native_decision import _sources
        (self.fixtures / "trace.md").write_text(
            "R" * 6000, encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        state = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        sources = _sources(self.fixtures)
        snippet = {
            "path": "trace.md", "sha256": sources["trace.md"],
            "offset_chars": 500, "untrusted_excerpt": "R" * 2048,
            "trust": "UNTRUSTED_DATA"}
        for _ in range(2):  # simulate competing retries after same snapshot
            _checkpoint_research_reads(
                self.db, self.workspace, self.fixtures, root,
                state["observation_sha256"], "installed:test", [snippet])
        with closing(connect(self.db)) as db:
            receipts = db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ'", (root,)
            ).fetchone()[0]
        self.assertEqual(receipts, 1)
        recovered = _recovered_research_reads(
            self.db, self.fixtures, root, state["observation_sha256"],
            "installed:test", sources)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["offset_chars"], 500)

    def test_overlapping_retry_is_rejected_before_poisoning_resume(self):
        """Two slightly different overlapping ranges are not distinct evidence."""
        from cognition_agent_os.native_local_planner import (
            _checkpoint_research_reads, _recovered_research_reads)
        from cognition_agent_os.native_decision import _sources
        (self.fixtures / "trace.md").write_text(
            "R" * 6000, encoding="utf-8")
        root = register_native_goal(self.db, self.goal)
        state = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        sources = _sources(self.fixtures)
        def part(offset):
            return {
                "path": "trace.md", "sha256": sources["trace.md"],
                "offset_chars": offset, "untrusted_excerpt": "R" * 2048,
                "trust": "UNTRUSTED_DATA"}
        _checkpoint_research_reads(
            self.db, self.workspace, self.fixtures, root,
            state["observation_sha256"], "installed:test", [part(500)])
        with self.assertRaisesRegex(
                ValueError, "NATIVE_RESEARCH_NO_NEW_EVIDENCE"):
            _checkpoint_research_reads(
                self.db, self.workspace, self.fixtures, root,
                state["observation_sha256"], "installed:test", [part(650)])
        with closing(connect(self.db)) as db:
            receipts = db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='NATIVE_LOCAL_RESEARCH_READ'", (root,)
            ).fetchone()[0]
        self.assertEqual(receipts, 1)
        self.assertEqual(len(_recovered_research_reads(
            self.db, self.fixtures, root, state["observation_sha256"],
            "installed:test", sources)), 1)

    def test_host_autonomous_two_method_loop_and_cold_state(self):
        root = register_native_goal(self.db, self.goal)
        files_before = {p.name: p.read_bytes() for p in self.fixtures.iterdir()}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.transport):
            first = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=1,
                planner_mode="ollama-local", local_model="installed:test",
                auto_native_cognition=True)
            self.assertEqual(first["processed"], 1)
            self.assertEqual(first["tasks"][0]["status"], "NEEDS_REVIEW", first)
            self.assertEqual(first["native_cognition"][0]["status"],
                             "NATIVE_METHOD_ENQUEUED", first)
            second = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=1,
                planner_mode="ollama-local", local_model="installed:test",
                auto_native_cognition=True)
            self.assertEqual(second["tasks"][0]["status"], "NEEDS_REVIEW", second)
            self.assertEqual(second["native_cognition"][0]["status"],
                             "NATIVE_METHOD_ENQUEUED", second)
            third = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=1,
                planner_mode="ollama-local", local_model="installed:test",
                auto_native_cognition=False)
            self.assertEqual(third["tasks"], [], third)
        final = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        self.assertEqual(final["decision_count"], 2)
        self.assertEqual([x["mechanical_verdict"] for x in final["decisions"]],
                         ["REPORT_MECHANICALLY_VERIFIED",
                          "CANDIDATE_MECHANICALLY_VALID"], final)
        self.assertFalse(final["owner_outcome_verified"])
        self.assertEqual(files_before,
                         {p.name:p.read_bytes() for p in self.fixtures.iterdir()})

    def test_cross_root_verified_procedure_trial_is_challenged_not_promoted(self):
        """A verified prior procedure is trialled on a distinct goal, not promoted."""
        from cognition_agent_os.native_local_planner import advance_native_adaptive_once
        from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome
        from cognition_agent_os.procedure_evidence import (
            inspect_cross_root_procedure_trials)

        source_root = register_native_goal(
            self.db,
            "Compare reference.csv with observed.csv and report the differences.")
        first = advance_native_adaptive_once(
            self.db, self.workspace, self.fixtures, source_root, model=None)
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED", first)
        worker = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(worker["tasks"][0]["task_id"], first["child_task_id"])
        self.assertEqual(worker["tasks"][0]["status"], "NEEDS_REVIEW", worker)
        self.assertEqual(inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, source_root)["status"],
            "LOCAL_OWNER_RESULT_VERIFIED")

        # New file bindings and a different owner goal force a genuine
        # cross-root trial rather than replaying the first root's task.
        (self.fixtures / "reference_b.csv").write_text(
            "item,expected\nB,11\n", encoding="utf-8")
        (self.fixtures / "observed_b.csv").write_text(
            "item,expected\nB,9\n", encoding="utf-8")
        target_goal = (
            "Compare reference_b.csv with observed_b.csv and report the differences.")
        target_root = register_native_goal(self.db, target_goal)
        trials = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(
            trials["status"], "CROSS_ROOT_PROCEDURE_TRIALS_AVAILABLE", trials)
        self.assertEqual(len(trials["items"]), 1, trials)
        trial = trials["items"][0]
        self.assertEqual(trial["source_root_id"], source_root)
        self.assertEqual(trial["objective"], "compare_records")
        self.assertEqual(trial["capability"], "csv_evidence_reconciliation_v1")
        self.assertRegex(trial["procedure_fingerprint"], r"^[a-f0-9]{64}$")
        self.assertNotEqual(
            trial["source_goal_sha256"],
            trials["current_root_goal_sha256"])
        self.assertEqual(
            trial["trial_status"], "PRIOR_ROOT_LOCAL_OWNER_OUTCOME_VERIFIED")
        self.assertEqual(
            trial["applicability_to_current_goal"], "NOT_YET_TESTED")
        self.assertFalse(trial["authorizes_action"])
        self.assertFalse(trials["any_general_method_transfer_verified"])

        calls = []
        def model(method, endpoint, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            self.assertEqual(method, "POST")
            history = json.loads(payload["prompt"].rsplit("\n\n", 1)[1])
            evidence = history["cross_root_procedure_trial_evidence"]
            self.assertEqual(evidence["status"],
                             "CROSS_ROOT_PROCEDURE_TRIALS_AVAILABLE")
            self.assertEqual(evidence["items"][0]["source_root_id"], source_root)
            self.assertFalse(evidence["items"][0]["authorizes_action"])
            self.assertIn("NOT proof of current", payload["prompt"])
            calls.append(evidence["items"][0]["procedure_fingerprint"])
            answer = {
                "selected_intent": {
                    "kind": "goal_intent", "objective": "compare_records",
                    "resources": [
                        {"role": "reference", "path": "reference_b.csv"},
                        {"role": "observed", "path": "observed_b.csv"}]},
                "alternative_intent": None,
                "decision_reason": (
                    "The prior cross-root trial makes this registered comparison "
                    "family worth testing on the distinct owner inputs."),
                "alternative_reason": (
                    "No other registered local capability directly compares "
                    "these exact CSV source roles."),
                "expected_evidence": (
                    "A fresh independent SQL report readback for this owner root."),
                "observation_sha256": history["observation_sha256"],
                "decision_basis": self.basis_from_evidence(history),
            }
            return {"done": True, "response": json.dumps(answer)}

        from cognition_agent_os.native_local_planner import advance_native_local_once
        with patch("cognition_agent_os.local_model._request", side_effect=model):
            admitted = advance_native_local_once(
                self.db, self.workspace, self.fixtures, target_root,
                model="installed:test")
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED", admitted)
        self.assertEqual(calls, [trial["procedure_fingerprint"]])
        self.assertFalse(admitted["owner_outcome_verified"])
        self.assertFalse(inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, target_root)[
                "local_owner_outcome_verified"])

        second_worker = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(
            second_worker["tasks"][0]["task_id"], admitted["child_task_id"])
        self.assertEqual(second_worker["tasks"][0]["status"], "NEEDS_REVIEW")
        target_outcome = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, target_root)
        self.assertEqual(target_outcome["status"], "LOCAL_OWNER_RESULT_VERIFIED")
        self.assertTrue(target_outcome["local_owner_outcome_verified"])
        self.assertFalse(target_outcome["business_outcome_verified"])

        # A third, different goal sees two independently verified trials of
        # the same registered procedure family, not a promoted generic method.
        (self.fixtures / "reference_c.csv").write_text(
            "item,expected\nC,13\n", encoding="utf-8")
        (self.fixtures / "observed_c.csv").write_text(
            "item,expected\nC,12\n", encoding="utf-8")
        third_root = register_native_goal(
            self.db,
            "Compare reference_c.csv with observed_c.csv and report the differences.")
        third_trials = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, third_root,
            eligible_objectives=("compare_records",))
        self.assertEqual(len(third_trials["items"]), 2, third_trials)
        self.assertEqual(
            {x["source_root_id"] for x in third_trials["items"]},
            {source_root, target_root})
        self.assertEqual(
            len({x["procedure_fingerprint"] for x in third_trials["items"]}), 1)
        self.assertFalse(third_trials["any_general_method_transfer_verified"])
        self.assertFalse(third_trials["authorizes_action"])


    def test_cross_root_procedure_evidence_changed_during_inference_blocks_admission(self):
        """A prior success invalidated after prompt construction cannot ground a decision."""
        from cognition_agent_os.native_local_planner import advance_native_adaptive_once

        source_root = register_native_goal(
            self.db,
            "Compare reference.csv with observed.csv and report the differences.")
        first = advance_native_adaptive_once(
            self.db, self.workspace, self.fixtures, source_root, model=None)
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED", first)
        worker = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(worker["tasks"][0]["task_id"], first["child_task_id"])
        self.assertEqual(worker["tasks"][0]["status"], "NEEDS_REVIEW", worker)

        (self.fixtures / "reference_b.csv").write_text(
            "item,expected\nB,11\n", encoding="utf-8")
        (self.fixtures / "observed_b.csv").write_text(
            "item,expected\nB,9\n", encoding="utf-8")
        target_root = register_native_goal(
            self.db,
            "Compare reference_b.csv with observed_b.csv and report the differences.")

        def model(method, endpoint, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            self.assertEqual(method, "POST")
            history = json.loads(payload["prompt"].rsplit("\n\n", 1)[1])
            evidence = history["cross_root_procedure_trial_evidence"]
            self.assertEqual(
                evidence["status"], "CROSS_ROOT_PROCEDURE_TRIALS_AVAILABLE")
            prior_artifact = (
                self.workspace / "artifacts" /
                (evidence["items"][0]["evidence_task_id"] + ".json"))
            # Simulate an independent artifact change after the planner read
            # and presented the previously verified result, but before
            # decision admission. The current root's own inputs do not change.
            prior_artifact.write_text('{"tampered":true}\n', encoding="utf-8")
            answer = {
                "selected_intent": {
                    "kind": "goal_intent", "objective": "compare_records",
                    "resources": [
                        {"role": "reference", "path": "reference_b.csv"},
                        {"role": "observed", "path": "observed_b.csv"}]},
                "alternative_intent": None,
                "decision_reason": (
                    "The prior cross-root trial makes this registered comparison "
                    "family worth testing on the distinct owner inputs."),
                "alternative_reason": (
                    "No other registered local capability directly compares "
                    "these exact CSV source roles."),
                "expected_evidence": (
                    "A fresh independent SQL report readback for this owner root."),
                "observation_sha256": history["observation_sha256"],
                "decision_basis": self.basis_from_evidence(history),
            }
            return {"done": True, "response": json.dumps(answer)}

        with patch("cognition_agent_os.local_model._request", side_effect=model):
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, target_root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_PLAN_REFUSED", result)
        self.assertIn(
            "NATIVE_STALE_CROSS_ROOT_PROCEDURE_EVIDENCE", result["reason"])
        state = inspect_native_goal(
            self.db, self.workspace, self.fixtures, target_root)
        self.assertEqual(state["decision_count"], 0, state)
        self.assertFalse(inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, target_root)[
                "local_owner_outcome_verified"])

    def test_cross_root_procedure_trial_is_invalidated_by_source_drift(self):
        from cognition_agent_os.native_local_planner import advance_native_adaptive_once
        from cognition_agent_os.procedure_evidence import (
            inspect_cross_root_procedure_trials)

        source_root = register_native_goal(
            self.db,
            "Compare reference.csv with observed.csv and report the differences.")
        first = advance_native_adaptive_once(
            self.db, self.workspace, self.fixtures, source_root, model=None)
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED", first)
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        target_root = register_native_goal(self.db, self.goal)
        before = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(len(before["items"]), 1, before)

        (self.fixtures / "observed.csv").write_text(
            "item,expected\nA,999\n", encoding="utf-8")
        after = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(after["status"],
                         "NO_VERIFIED_CROSS_ROOT_PROCEDURE_TRIALS", after)
        self.assertEqual(after["items"], [])
        self.assertFalse(after["authorizes_action"])

    def test_cross_root_procedure_trial_is_invalidated_by_artifact_drift(self):
        from cognition_agent_os.native_local_planner import advance_native_adaptive_once
        from cognition_agent_os.procedure_evidence import (
            inspect_cross_root_procedure_trials)

        source_root = register_native_goal(
            self.db,
            "Compare reference.csv with observed.csv and report the differences.")
        first = advance_native_adaptive_once(
            self.db, self.workspace, self.fixtures, source_root, model=None)
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED", first)
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        target_root = register_native_goal(self.db, self.goal)
        before = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(len(before["items"]), 1, before)

        artifact = self.workspace / "artifacts" / (
            first["child_task_id"] + ".json")
        artifact.write_bytes(artifact.read_bytes() + b" changed after verification")
        after = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(after["status"],
                         "NO_VERIFIED_CROSS_ROOT_PROCEDURE_TRIALS", after)
        self.assertEqual(after["items"], [])
        self.assertFalse(after["authorizes_action"])

    def test_cross_root_procedure_trial_is_invalidated_by_grant_change(self):
        from cognition_agent_os.native_local_planner import advance_native_adaptive_once
        from cognition_agent_os.procedure_evidence import (
            inspect_cross_root_procedure_trials)

        source_root = register_native_goal(
            self.db,
            "Compare reference.csv with observed.csv and report the differences.")
        first = advance_native_adaptive_once(
            self.db, self.workspace, self.fixtures, source_root, model=None)
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED", first)
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        target_root = register_native_goal(self.db, self.goal)
        before = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(len(before["items"]), 1, before)

        with closing(connect(self.db)) as db:
            db.execute(
                "UPDATE authority SET grant_rev=grant_rev+1 WHERE singleton=1")
            db.commit()
        after = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(
            after["status"], "PROCEDURE_TRIAL_CURRENT_ROOT_NOT_ADMISSIBLE")
        self.assertEqual(after["items"], [])
        self.assertFalse(after["authorizes_action"])

    def test_cross_root_procedure_trial_does_not_cross_objective_fit(self):
        from cognition_agent_os.native_local_planner import advance_native_adaptive_once
        from cognition_agent_os.procedure_evidence import (
            inspect_cross_root_procedure_trials)

        source_root = register_native_goal(
            self.db,
            "Compare reference.csv with observed.csv and report the differences.")
        first = advance_native_adaptive_once(
            self.db, self.workspace, self.fixtures, source_root, model=None)
        self.assertEqual(first["status"], "NATIVE_METHOD_ENQUEUED", first)
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)

        target_root = register_native_goal(
            self.db,
            "Ensure a sandbox draft of handoff.json has audited equals to yes.")
        trials = inspect_cross_root_procedure_trials(
            self.db, self.workspace, self.fixtures, target_root,
            eligible_objectives=("compare_records", "ensure_structure"))
        self.assertEqual(
            trials["status"], "NO_VERIFIED_CROSS_ROOT_PROCEDURE_TRIALS")
        self.assertEqual(trials["items"], [])
        self.assertFalse(trials["authorizes_action"])

    def test_one_tick_two_model_methods_are_feedback_driven(self):
        """One explicit opt-in Host run must replan after actual first feedback.

        The synthetic model provides candidate JSON; all admission, Worker
        execution, SQLite persistence and independent artifact readback are
        REAL. A valid first artifact is not the whole composite owner goal.
        No external model service, grants, or production writes are implied.
        """
        root = register_native_goal(self.db, self.goal)
        before = {p.name: p.read_bytes() for p in self.fixtures.iterdir()}
        calls = []
        def provider(method, path, payload, timeout):
            if method == "POST":
                evidence = json.loads(payload["prompt"].split("\n\n")[-1])
                calls.append(len(evidence["past_methods_and_independent_verdicts"]))
            return self.transport(method, path, payload, timeout)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=provider):
            result = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=2,
                planner_mode="ollama-local", local_model="installed:test",
                auto_native_cognition=True)
        self.assertEqual(calls, [0, 1], result)
        self.assertEqual(len(result["tasks"]), 2, result)
        self.assertEqual(
            [x["status"] for x in result["tasks"]],
            ["NEEDS_REVIEW", "NEEDS_REVIEW"], result)
        self.assertEqual(len([
            c for c in result["native_cognition"]
            if c["status"] == "NATIVE_METHOD_ENQUEUED"]), 2, result)
        observed = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        self.assertEqual(observed["decision_count"], 2, observed)
        self.assertEqual(
            [x["mechanical_verdict"] for x in observed["decisions"]],
            ["REPORT_MECHANICALLY_VERIFIED", "CANDIDATE_MECHANICALLY_VALID"])
        self.assertIs(observed["owner_outcome_verified"], False)
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in self.fixtures.iterdir()})
        replay = run_tick(self.db, self.workspace, self.fixtures,
                          max_jobs=2, auto_native_cognition=False)
        self.assertEqual(replay["tasks"], [], replay)

    def test_installed_planner_challenges_both_user_and_agent_suggestions(self):
        root = register_native_goal(self.db, self.goal)
        first = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="user", idea="Erase the original CSV before checking the mismatch",
            observation_sha256=first["observation_sha256"])
        second = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        record_native_hypothesis(
            self.db, self.workspace, self.fixtures, root,
            origin="agent", idea="Reconcile the original CSV inputs without mutation",
            observation_sha256=second["observation_sha256"])
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.transport):
            planned = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(planned["status"], "NATIVE_METHOD_ENQUEUED", planned)
        outcome = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(outcome["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertEqual(len(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["hypotheses"]), 2)
        self.assertTrue((self.fixtures / "reference.csv").is_file())

    def test_unknown_goal_model_may_abstain_despite_available_irrelevant_tools(self):
        original = (
            "Research a previously unknown media license, compare the "
            "publisher's legal permissions and rights holders, and publish "
            "nothing without a current independently reviewed license.")
        root = register_native_goal(self.db, original)
        def abstain(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            self.assertEqual(payload["format"], "json")
            self.assertIn(original, payload["prompt"])
            self.assertIn("abstain", payload["prompt"])
            return {"done": True, "response": '{"abstain":true}'}
        with patch("cognition_agent_os.local_model._request", side_effect=abstain):
            first = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(first["status"], "NATIVE_LOCAL_MODEL_ABSTAINED", first)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 0)
        with patch("cognition_agent_os.local_model._request") as model:
            second = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(second["status"],
                         "NATIVE_LOCAL_UNCHANGED_EVIDENCE_REFUSED", second)
        model.assert_not_called()

    def test_corrupted_prior_result_blocks_next_model_step_before_new_inference(self):
        root = register_native_goal(self.db, self.goal)
        first = self.transport
        with patch("cognition_agent_os.local_model._request", side_effect=first):
            planned = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(planned["status"], "NATIVE_METHOD_ENQUEUED")
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)
        artifact = self.workspace / "artifacts" / (planned["child_task_id"] + ".json")
        artifact.write_bytes(artifact.read_bytes() + b" corrupt")
        with patch("cognition_agent_os.local_model._request") as model:
            attempted = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        model.assert_not_called()
        self.assertEqual(attempted["status"], "NATIVE_LOCAL_PLAN_NOT_ADMISSIBLE")
        self.assertFalse(attempted["owner_outcome_verified"])

    def test_source_change_during_reasoning_refuses_plan_without_child(self):
        root = register_native_goal(self.db, self.goal)
        def source_changed(method, path, payload, timeout):
            result = self.transport(method,path,payload,timeout)
            if method == "POST":
                (self.fixtures / "observed.csv").write_text(
                    "item,expected\nA,1000\n", encoding="utf-8")
            return result
        with patch("cognition_agent_os.local_model._request",
                   side_effect=source_changed):
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_PLAN_REFUSED")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 0)

    def test_missing_installed_model_is_not_downloaded_and_does_not_write(self):
        root = register_native_goal(self.db, self.goal)
        with patch("cognition_agent_os.local_model._request",
                   return_value={"models": []}) as request:
            r = advance_native_local_once(
                self.db, self.workspace, self.fixtures, root,
                model="installed:not-present")
        self.assertEqual(r["status"], "NATIVE_LOCAL_MODEL_UNAVAILABLE")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[:2], ("GET", "/api/tags"))
        self.assertEqual(inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)["decision_count"], 0)

    def test_model_can_not_choose_unregistered_domain_or_external_effect(self):
        root = register_native_goal(self.db, self.goal)
        def unsupported(method,path,payload,timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            evidence = json.loads(payload["prompt"].split("\n\n")[-1])
            return {"done": True, "response": json.dumps({
                "decision_basis": self.basis_from_evidence(evidence),
                "selected_intent": {
                    "kind": "goal_intent", "objective": "deploy_production",
                    "resources": []},
                "alternative_intent": self.compare(),
                "decision_reason": "Please deploy an unregistered production method.",
                "alternative_reason": "The registered comparator is only local evidence.",
                "expected_evidence": "Production owner result must not be fabricated.",
                "observation_sha256": json.loads(
                    payload["prompt"].split("\n\n")[-1])["observation_sha256"],
            })}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=unsupported):
            result=advance_native_local_once(
                self.db,self.workspace,self.fixtures,root,model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_PLAN_REFUSED")
        self.assertEqual(inspect_native_goal(
            self.db,self.workspace,self.fixtures,root)["decision_count"],0)

    def test_rejected_model_choice_is_not_called_again_until_evidence_changes(self):
        root = register_native_goal(self.db, self.goal)
        def invalid(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            evidence = json.loads(payload["prompt"].split("\n\n")[-1])
            return {"done": True, "response": json.dumps({
                "decision_basis": self.basis_from_evidence(evidence),
                "selected_intent": {
                    "kind": "goal_intent", "objective": "delete_all_files",
                    "resources": []},
                "alternative_intent": self.compare(),
                "decision_reason": "Unsafe model invented a new action.",
                "alternative_reason": "Registered actions are not arbitrary code.",
                "expected_evidence": "No effects are permitted for invented tools.",
                "observation_sha256": evidence["observation_sha256"],
            })}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=invalid) as provider:
            bad = advance_native_local_once(
                self.db,self.workspace,self.fixtures,root,model="installed:test")
            again = advance_native_local_once(
                self.db,self.workspace,self.fixtures,root,model="installed:test")
            exhausted = advance_native_local_once(
                self.db,self.workspace,self.fixtures,root,model="installed:test")
            self.assertEqual(bad["status"],"NATIVE_LOCAL_PLAN_REFUSED")
            self.assertEqual(again["status"],"NATIVE_LOCAL_PLAN_REFUSED")
            self.assertEqual(exhausted["status"],
                             "NATIVE_LOCAL_UNCHANGED_EVIDENCE_REFUSED")
            self.assertEqual(provider.call_count, 4)  # two bounded attempts
            self.assertIn("No registered capability", provider.call_args.args[2]["prompt"])
            (self.fixtures / "trace.md").write_text(
                "Updated independent investigation evidence.\n",encoding="utf-8")
            changed = advance_native_local_once(
                self.db,self.workspace,self.fixtures,root,model="installed:test")
            self.assertEqual(changed["status"],"NATIVE_LOCAL_PLAN_REFUSED")
            self.assertEqual(provider.call_count, 6)
        self.assertEqual(inspect_native_goal(
            self.db,self.workspace,self.fixtures,root)["decision_count"],0)

    def test_single_eligible_method_runs_without_fabricated_competitor(self):
        """Adaptive effort: one viable capability never requires two fake tools."""
        (self.fixtures / "reference.csv").unlink()
        (self.fixtures / "observed.csv").unlink()
        root = register_native_goal(
            self.db, "Prepare a local JSON handoff with audited=yes, preserve all originals.")
        original = (self.fixtures / "handoff.json").read_bytes()
        def model(method, path, payload, timeout):
            if method == "GET":
                return {"models":[{"name":"installed:test"}]}
            evidence=json.loads(payload["prompt"].split("\n\n")[-1])
            self.assertEqual(
                [x["objective"] for x in evidence["registered_local_methods"]],
                ["ensure_structure"])
            return {"done": True, "response": json.dumps({
                "decision_basis": self.basis_from_evidence(evidence),
                "selected_intent": self.ensure(), "alternative_intent": None,
                "decision_reason": "Only the local JSON conformance tool fits this evidence.",
                "alternative_reason": "Other registered tools lack compatible sources.",
                "expected_evidence": "An independently checked preserved JSON proposal.",
                "observation_sha256": evidence["observation_sha256"],
            })}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=model):
            planned = advance_native_local_once(
                self.db,self.workspace,self.fixtures,root,model="installed:test")
        self.assertEqual(planned["status"],"NATIVE_METHOD_ENQUEUED",planned)
        result=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1,
                        planner_mode="ollama-local",local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"],"NEEDS_REVIEW",result)
        observed=inspect_native_goal(self.db,self.workspace,self.fixtures,root)
        self.assertIsNone(observed["decisions"][0]["alternative_objective"])
        self.assertFalse(observed["owner_outcome_verified"])
        self.assertEqual((self.fixtures/"handoff.json").read_bytes(),original)

    def test_available_but_irrelevant_tool_not_forced_as_competitor(self):
        """Eligibility by file suffix is not relevance to the original owner goal.

        JSON conformance happens to be executable, but this task is about the
        disputed CSV evidence. Mandatory two-tool comparison is false evidence.
        The same grant, grounded proposal, Worker, and independent audit apply.
        """
        from cognition_agent_os.native_decision import (
            admit_native_decision, capability_catalog)
        root = register_native_goal(
            self.db, "Identify the actual CSV inventory discrepancy; leave "
                     "all local sources unchanged and independently verify "
                     "the resulting discrepancy report.")
        original = {p.name: p.read_bytes() for p in self.fixtures.iterdir()}
        methods = capability_catalog(self.fixtures)["methods"]
        eligible = [x["objective"] for x in methods if x["currently_eligible"]]
        self.assertIn("compare_records", eligible)
        self.assertIn("ensure_structure", eligible)  # eligible != relevant
        observed = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        queued = admit_native_decision(
            self.db, self.workspace, self.fixtures, root, {
                "selected_intent": self.compare(),
                "alternative_intent": None,
                "decision_basis": self.basis_for_root(root),
                "decision_reason": (
                    "CSV reconciliation tests the actual owner discrepancy."),
                "alternative_reason": (
                    "The other available JSON tool is mechanically eligible "
                    "but irrelevant to reconciling the CSV business records."),
                "expected_evidence": (
                    "Independent recomputation of an immutable local report."),
                "observation_sha256": observed["observation_sha256"],
            })
        self.assertEqual(queued["status"], "NATIVE_METHOD_ENQUEUED")
        actual = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1)
        self.assertEqual(actual["tasks"][0]["status"], "NEEDS_REVIEW")
        after = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root)
        self.assertEqual(after["decisions"][0]["mechanical_verdict"],
                         "REPORT_MECHANICALLY_VERIFIED")
        self.assertIsNone(after["decisions"][0]["alternative_objective"])
        self.assertFalse(after["owner_outcome_verified"])
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.fixtures.iterdir()},
            original)

    def test_native_auto_needs_model_for_unresolved_goal_not_exact_program(self):
        original = register_native_goal(self.db, self.goal)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("No inference without model")):
            result = run_tick(
                self.db, self.workspace, self.fixtures,
                max_jobs=1, auto_native_cognition=True)
        self.assertEqual(result["native_cognition"][0]["root_task_id"], original)
        self.assertEqual(result["native_cognition"][0]["status"],
                         "NATIVE_COGNITION_REQUIRED_FOR_UNRESOLVED_GOAL")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task IS NOT NULL"
            ).fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
