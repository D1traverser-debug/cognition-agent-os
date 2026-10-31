"""Cross-task method experience requires distinct owner outcomes and source bindings."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    admit_native_decision, inspect_native_goal, register_native_goal,
)
from cognition_agent_os.native_local_planner import advance_native_local_once
from cognition_agent_os.native_method_memory import inspect_replicated_local_methods
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome


class CrossTaskMethodMemoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "ledger.sqlite"
        self.fixtures = self.root / "fixtures"
        self.workspace = self.root / "workspace"
        self.fixtures.mkdir()
        self.workspace.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)

    def _write_pair(self, suffix: str) -> tuple[str, str]:
        reference = f"reference_{suffix}.csv"
        observed = f"observed_{suffix}.csv"
        (self.fixtures / reference).write_text(
            "id,amount\nA,7\nB,5\n", encoding="utf-8")
        (self.fixtures / observed).write_text(
            "id,amount\nA,6\nB,5\n", encoding="utf-8")
        return reference, observed

    def _complete_compare(self, suffix: str, *, goal: str | None = None) -> str:
        reference, observed = self._write_pair(suffix)
        goal = goal or (
            f"Compare {reference} with {observed} and report differences."
        )
        root = register_native_goal(self.db, goal)
        state = inspect_native_goal(
            self.db, self.workspace, self.fixtures, root
        )
        source_refs = [
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(self.fixtures.iterdir())
        ]
        proposal = {
            "selected_intent": {
                "kind": "goal_intent",
                "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": reference},
                    {"role": "observed", "path": observed},
                ],
            },
            "alternative_intent": None,
            "decision_reason": "Use the exact owner-named read-only comparison.",
            "alternative_reason": "No other registered local method satisfies the named report.",
            "expected_evidence": "Independent source and artifact recomputation.",
            "observation_sha256": state["observation_sha256"],
            "decision_basis": {
                "source_refs": source_refs,
                "previous_result_task_id": None,
                "challenge": "A unique join key may be absent or ambiguous.",
                "falsifier": "Independent recomputation rejects the discrepancy report.",
                "uncertainty": "A local report cannot prove external inventory truth.",
            },
        }
        admitted = admit_native_decision(
            self.db, self.workspace, self.fixtures, root, proposal
        )
        tick = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1
        )
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW", tick)
        self.assertEqual(tick["tasks"][0]["task_id"], admitted["child_task_id"])
        owner = inspect_owner_local_outcome(
            self.db, self.workspace, self.fixtures, root
        )
        self.assertTrue(owner["local_owner_outcome_verified"], owner)
        self.assertFalse(owner["business_outcome_verified"])
        return root

    def test_one_owner_goal_is_not_enough_to_reuse_a_method(self):
        self._complete_compare("a")
        current = register_native_goal(
            self.db, "Investigate a new supplier discrepancy and its causes."
        )
        memory = inspect_replicated_local_methods(
            self.db, self.workspace, self.fixtures, current
        )
        self.assertEqual(memory["status"], "NO_REPLICATED_LOCAL_METHOD_EXPERIENCE")
        self.assertEqual(memory["methods"], [])
        self.assertFalse(memory["authorizes_action"])

    def test_two_distinct_owner_goals_replicate_a_local_method_pattern(self):
        first = self._complete_compare("a")
        second = self._complete_compare("b")
        self.assertNotEqual(first, second)
        current = register_native_goal(
            self.db,
            "Investigate a supplier discrepancy, compare the source records, "
            "and prepare a local handoff without changing originals.",
        )
        memory = inspect_replicated_local_methods(
            self.db, self.workspace, self.fixtures, current
        )
        self.assertEqual(memory["status"], "REPLICATED_LOCAL_METHOD_EXPERIENCE", memory)
        self.assertEqual(len(memory["methods"]), 1, memory)
        method = memory["methods"][0]
        self.assertEqual(
            method["method_key"],
            "compare_records|ORIGINAL_NAMED_READONLY_COMPARISON_REPORT",
        )
        self.assertEqual(method["independent_owner_goal_count"], 2)
        self.assertEqual(method["independent_source_binding_count"], 2)
        self.assertEqual(method["independent_result_artifact_count"], 2)
        self.assertEqual(method["source_role_pattern"], ["reference", "observed"])
        self.assertFalse(method["authorizes_action"])
        self.assertFalse(method["business_outcome_verified"])
        self.assertEqual(
            {x["root_task_id"] for x in method["examples"]}, {first, second}
        )
        self.assertTrue(all(
            "reference_" not in json.dumps(example)
            and "observed_" not in json.dumps(example)
            for example in method["examples"]
        ))

    def test_duplicate_goal_and_source_binding_do_not_count_as_replication(self):
        goal = "Compare reference_same.csv with observed_same.csv and report differences."
        first = self._complete_compare("same", goal=goal)
        second = self._complete_compare("same", goal=goal)
        self.assertNotEqual(first, second)
        current = register_native_goal(
            self.db, "Investigate a separate unfamiliar process."
        )
        memory = inspect_replicated_local_methods(
            self.db, self.workspace, self.fixtures, current
        )
        self.assertEqual(memory["status"], "NO_REPLICATED_LOCAL_METHOD_EXPERIENCE")

    def test_live_source_drift_revokes_a_previously_replicated_pattern(self):
        first = self._complete_compare("a")
        self._complete_compare("b")
        current = register_native_goal(
            self.db, "Investigate a new process using independent evidence."
        )
        before = inspect_replicated_local_methods(
            self.db, self.workspace, self.fixtures, current
        )
        self.assertEqual(before["status"], "REPLICATED_LOCAL_METHOD_EXPERIENCE")
        (self.fixtures / "observed_a.csv").write_text(
            "id,amount\nA,999\nB,5\n", encoding="utf-8"
        )
        after = inspect_replicated_local_methods(
            self.db, self.workspace, self.fixtures, current
        )
        self.assertEqual(after["status"], "NO_REPLICATED_LOCAL_METHOD_EXPERIENCE")
        self.assertFalse(after["methods"])
        self.assertNotEqual(first, current)

    def test_cross_task_experience_reaches_the_next_native_model_decision(self):
        first = self._complete_compare("a")
        second = self._complete_compare("b")
        current = register_native_goal(
            self.db,
            "Investigate an unfamiliar supplier export workflow, compare "
            "independent evidence, and prepare a local handoff.",
        )
        seen = []
        prompts = []

        def model(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            prompts.append(payload["prompt"])
            seen.append(json.loads(payload["prompt"].split("\n\n")[-1]))
            return {"done": True, "response": '{"abstain":true}'}

        with patch("cognition_agent_os.local_model._request", side_effect=model):
            result = advance_native_local_once(
                self.db, self.workspace, self.fixtures, current,
                model="installed:test",
            )
        self.assertEqual(result["status"], "NATIVE_LOCAL_MODEL_ABSTAINED", result)
        self.assertEqual(len(seen), 1)
        memory = seen[0]["replicated_cross_task_method_experience"]
        self.assertEqual(memory["status"], "REPLICATED_LOCAL_METHOD_EXPERIENCE")
        self.assertEqual(memory["methods"][0]["independent_owner_goal_count"], 2)
        self.assertIn("NOT universal method truth", prompts[0])
        self.assertIn(first, {x["root_task_id"] for x in memory["methods"][0]["examples"]})
        self.assertIn(second, {x["root_task_id"] for x in memory["methods"][0]["examples"]})


if __name__ == "__main__":
    unittest.main()
