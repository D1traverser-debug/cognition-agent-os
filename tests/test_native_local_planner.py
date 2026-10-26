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
        selected = self.compare() if prior == 0 else self.ensure()
        alternative = self.ensure() if prior == 0 else self.compare()
        answer = {
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
            return {"done": True, "response": json.dumps({
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
