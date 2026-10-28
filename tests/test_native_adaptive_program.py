"""Exact owner contracts run by program, uncertain goals stay model-driven.

Real Host/SQLite/Worker and independent owner postcondition; no test-double
model is needed to prove ordinary CSV and isolated JSON effects. A real LLM's
semantic ability is NOT asserted by these tests.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, record_native_hypothesis)
from cognition_agent_os.native_local_planner import advance_native_adaptive_once
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome


class NativeAdaptiveProgramTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.db, self.work, self.fixtures = (
            root / "ledger.sqlite", root / "work", root / "fixtures")
        self.work.mkdir()
        self.fixtures.mkdir()
        for name, data in {
            "baseline.csv": "id,amount\nA,7\n",
            "actual.csv": "id,amount\nA,5\n",
            "irrelevant.csv": "id,amount\nA,9\n",
            "settings.json": '{"timeout":12}\n',
        }.items():
            (self.fixtures / name).write_text(data, encoding="utf-8")
        with closing(connect(self.db)) as con:
            initialize(con)
        self.original = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.fixtures.iterdir()}

    def unchanged(self):
        self.assertEqual(self.original, {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.fixtures.iterdir()})

    def test_exact_csv_program_completes_with_zero_model_requests(self):
        goal = "Compare baseline.csv with actual.csv and report differences."
        root = register_native_goal(self.db, goal)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("LLM must not run")) as provider:
            admitted = advance_native_adaptive_once(
                self.db, self.work, self.fixtures, root, model="not-installed")
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED", admitted)
        self.assertEqual(admitted["planner"], "EXACT_OWNER_PROGRAM_GROUNDED")
        self.assertEqual(admitted["model_calls_in_step"], 0)
        provider.assert_not_called()
        tick = run_tick(self.db, self.work, self.fixtures, max_jobs=1)
        self.assertEqual(tick["tasks"][0]["task_id"], admitted["child_task_id"])
        result = inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, root)
        self.assertTrue(result["local_owner_outcome_verified"], result)
        self.assertFalse(result["business_outcome_verified"])
        self.unchanged()
        no_repeat = advance_native_adaptive_once(
            self.db, self.work, self.fixtures, root, model="not-installed")
        self.assertEqual(no_repeat["status"], "NATIVE_ORIGINAL_OWNER_ALREADY_VERIFIED")

    def test_exact_json_draft_program_stages_and_independently_verifies(self):
        root = register_native_goal(
            self.db, "Please ensure an isolated draft of settings.json "
                     "has owner equal to ops.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("LLM must not run")) as provider:
            admitted = advance_native_adaptive_once(
                self.db, self.work, self.fixtures, root, model="not-installed")
        self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED", admitted)
        self.assertEqual(admitted["model_calls_in_step"], 0)
        provider.assert_not_called()
        tick = run_tick(self.db, self.work, self.fixtures,
                        max_jobs=1, auto_stage_goals=True)
        self.assertEqual(tick["tasks"][0]["task_id"], admitted["child_task_id"])
        result = inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, root)
        self.assertTrue(result["local_owner_outcome_verified"], result)
        self.assertEqual(result["outcome_scope"],
                         "ORIGINAL_SANDBOX_DRAFT_POSTCONDITION")
        self.unchanged()

    def test_one_opted_in_host_tick_executes_and_checks_exact_owner_goal(self):
        """A single explicit Host invocation must not stop after just planning.

        The same tick must admit one existing registered local method, run
        the existing worker under its current grant, and independently read
        the complete local owner postcondition. No fresh scheduler invocation,
        cloud model, recursive side-effect loop or extra authority is allowed.
        """
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("No model was authorized")) as model:
            tick = run_tick(self.db, self.work, self.fixtures, max_jobs=1,
                            auto_native_cognition=True)
        model.assert_not_called()
        self.assertEqual(tick["status"], "PROCESSED", tick)
        self.assertEqual(len(tick["native_cognition"]), 1, tick)
        self.assertEqual(tick["native_cognition"][0]["status"],
                         "NATIVE_METHOD_ENQUEUED", tick)
        self.assertEqual(len(tick["tasks"]), 1, tick)
        self.assertEqual(tick["tasks"][0]["task_id"],
                         tick["native_cognition"][0]["child_task_id"], tick)
        actual = inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, root)
        self.assertTrue(actual["local_owner_outcome_verified"], actual)
        self.assertFalse(actual["business_outcome_verified"])
        self.unchanged()
        resumed = run_tick(self.db, self.work, self.fixtures, max_jobs=1,
                           auto_native_cognition=True)
        self.assertEqual(resumed["tasks"], [], resumed)
        self.unchanged()

    def test_real_host_entry_requires_no_model_for_exact_owner_goal(self):
        """One opted-in tick completes, next tick is a replay-safe readback."""
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("No Ollama during host work")):
            first = run_tick(
                self.db, self.work, self.fixtures, max_jobs=1,
                auto_native_cognition=True)
            self.assertEqual(first["native_cognition"][0]["status"],
                             "NATIVE_METHOD_ENQUEUED", first)
            self.assertEqual(first["native_cognition"][0]["planner"],
                             "EXACT_OWNER_PROGRAM_GROUNDED")
            second = run_tick(
                self.db, self.work, self.fixtures, max_jobs=1,
                auto_native_cognition=True)
        self.assertEqual(len(first["tasks"]), 1, first)
        self.assertEqual(first["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertEqual(second["tasks"], [], second)
        self.assertEqual(second["native_cognition"][0]["status"],
                         "NATIVE_ORIGINAL_OWNER_ALREADY_VERIFIED")
        result = inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, root)
        self.assertTrue(result["local_owner_outcome_verified"], result)
        self.assertFalse(result["business_outcome_verified"])
        self.unchanged()

    def test_original_owner_not_hidden_by_more_than_128_newer_unsupported_goals(self):
        """Real Host regression: do not drop old actionable owner on new arrivals.

        Before this fix the newest-first LIMIT 128 returned only recent
        unsupported goals and exhausted the capacity on a no-model refusal.
        The old exact owner never reached Worker even though no permission or
        input had changed.
        """
        original = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        for i in range(130):
            register_native_goal(
                self.db, "Unfamiliar specialist objective number %03d: "
                         "investigate sources and compare approaches." % i)
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("No model can be called")) as provider:
            first = run_tick(
                self.db, self.work, self.fixtures, max_jobs=1,
                auto_native_cognition=True)
            self.assertEqual(len(first["native_cognition"]), 1, first)
            admitted = first["native_cognition"][0]
            self.assertEqual(admitted["root_task_id"], original)
            self.assertEqual(admitted["status"], "NATIVE_METHOD_ENQUEUED", first)
            second = run_tick(
                self.db, self.work, self.fixtures, max_jobs=1,
                auto_native_cognition=True)
        provider.assert_not_called()
        self.assertEqual(first["tasks"][0]["task_id"],
                         admitted["child_task_id"])
        self.assertEqual(second["tasks"], [], second)
        actual = inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, original)
        self.assertTrue(actual["local_owner_outcome_verified"], actual)
        self.assertFalse(actual["business_outcome_verified"])
        self.unchanged()

    def test_unresolved_owner_does_not_occupy_entire_program_action_budget(self):
        """Unknown scope remains UNKNOWN; older runnable owners still run."""
        unknown = register_native_goal(
            self.db, "Analyze a new scientific domain and invent new tools.")
        first = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        second = register_native_goal(
            self.db, "Please ensure an isolated draft of settings.json "
                     "has owner equal to ops.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("No model is authorized")):
            planned = run_tick(
                self.db, self.work, self.fixtures,
                max_jobs=2, auto_native_cognition=True)
        self.assertEqual(
            [x["root_task_id"] for x in planned["native_cognition"]],
            [first, second], planned)
        self.assertTrue(all(x["status"] == "NATIVE_METHOD_ENQUEUED"
                            for x in planned["native_cognition"]))
        self.assertEqual(inspect_native_goal(
            self.db, self.work, self.fixtures, unknown)["decision_count"], 0)
        self.assertFalse(inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, unknown)["local_owner_outcome_verified"])
        self.unchanged()

    def test_missing_named_resource_is_not_improvised(self):
        root = register_native_goal(
            self.db, "Compare baseline.csv with missing.csv and report differences.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("Model fallback would guess wrong")):
            result = advance_native_adaptive_once(
                self.db, self.work, self.fixtures, root, model="not-installed")
        self.assertEqual(result["status"], "NATIVE_PROGRAM_PLAN_REFUSED", result)
        self.assertEqual(inspect_native_goal(
            self.db, self.work, self.fixtures, root)["decision_count"], 0)
        self.unchanged()

    def test_composite_owner_goal_is_not_falsely_routed_or_marked_complete(self):
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report "
                     "differences and send findings to employees.")
        requests = []
        def model(method, path, payload, timeout):
            requests.append(method)
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            return {"done": True, "response": '{"abstain":true}'}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=model):
            result = advance_native_adaptive_once(
                self.db, self.work, self.fixtures, root, model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_MODEL_ABSTAINED", result)
        self.assertIn("POST", requests)
        self.assertFalse(inspect_owner_local_outcome(
            self.db, self.work, self.fixtures, root)["local_owner_outcome_verified"])
        self.unchanged()

    def test_owner_method_idea_is_challenged_not_bypassed_by_exact_program(self):
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        before = inspect_native_goal(self.db, self.work, self.fixtures, root)
        record_native_hypothesis(
            self.db, self.work, self.fixtures, root, origin="user",
            idea="The opposite CSV direction would be faster.",
            observation_sha256=before["observation_sha256"])
        # The program shortcut MUST NOT ignore unresolved user/agent ideas.
        with patch("cognition_agent_os.local_model._request",
                   return_value={"models": []}) as provider:
            result = advance_native_adaptive_once(
                self.db, self.work, self.fixtures, root, model="missing")
        self.assertEqual(result["status"], "NATIVE_LOCAL_MODEL_UNAVAILABLE", result)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(provider.call_args.args[0], "GET")
        self.assertEqual(inspect_native_goal(
            self.db, self.work, self.fixtures, root)["decision_count"], 0)
        self.unchanged()

    def test_revoked_grant_does_not_call_model_or_create_effect(self):
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        with closing(connect(self.db)) as con:
            con.execute("UPDATE authority SET write_allowed=0 WHERE singleton=1")
            con.commit()
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("Model after revocation")):
            result = advance_native_adaptive_once(
                self.db, self.work, self.fixtures, root, model="not-installed")
        self.assertNotEqual(result["status"], "NATIVE_METHOD_ENQUEUED")
        self.assertEqual(inspect_native_goal(
            self.db, self.work, self.fixtures, root)["decision_count"], 0)
        self.unchanged()


if __name__ == "__main__":
    unittest.main()
