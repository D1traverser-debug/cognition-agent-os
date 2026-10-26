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
    register_native_goal, inspect_native_goal)
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
        return {"done": True, "response": json.dumps(answer)}

    def test_host_autonomous_two_method_loop_and_cold_state(self):
        root = register_native_goal(self.db, self.goal)
        files_before = {p.name: p.read_bytes() for p in self.fixtures.iterdir()}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.transport):
            first = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=1,
                planner_mode="ollama-local", local_model="installed:test",
                auto_native_cognition=True)
            self.assertEqual(first["processed"], 0)
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
            self.assertEqual(third["tasks"][0]["status"], "NEEDS_REVIEW", third)
        final = inspect_native_goal(self.db, self.workspace, self.fixtures, root)
        self.assertEqual(final["decision_count"], 2)
        self.assertEqual([x["mechanical_verdict"] for x in final["decisions"]],
                         ["REPORT_MECHANICALLY_VERIFIED",
                          "CANDIDATE_MECHANICALLY_VALID"], final)
        self.assertFalse(final["owner_outcome_verified"])
        self.assertEqual(files_before,
                         {p.name:p.read_bytes() for p in self.fixtures.iterdir()})

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

    def test_single_method_shortcut_forbidden_when_real_alternative_exists(self):
        from cognition_agent_os.native_decision import admit_native_decision
        root=register_native_goal(self.db,self.goal)
        observed=inspect_native_goal(self.db,self.workspace,self.fixtures,root)
        with self.assertRaisesRegex(ValueError,"NATIVE_COMPARISON_REQUIRED"):
            admit_native_decision(
                self.db,self.workspace,self.fixtures,root,{
                    "selected_intent":self.compare(),
                    "alternative_intent":None,
                    "decision_basis":self.basis_for_root(root),
                    "decision_reason":"Use the local record comparison first.",
                    "alternative_reason":"No other comparison considered.",
                    "expected_evidence":"Independent local report readback.",
                    "observation_sha256":observed["observation_sha256"],
                })
        self.assertEqual(inspect_native_goal(
            self.db,self.workspace,self.fixtures,root)["decision_count"],0)

    def test_native_auto_needs_explicit_model_selection(self):
        register_native_goal(self.db, self.goal)
        with self.assertRaisesRegex(ValueError, "explicit installed local model"):
            run_tick(self.db, self.workspace, self.fixtures, max_jobs=1,
                     auto_native_cognition=True)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task IS NOT NULL"
            ).fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
