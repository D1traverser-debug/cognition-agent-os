"""Real native Host/SQLite tests for independent original-owner admission.

The preflight must reject a model's executable but owner-contradicting local
effect BEFORE worker execution; the same original owner contract is used at
independent outcome review. Unrecognized composite goals are not forcibly
reinterpreted as complete local goals.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision)
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome


class NativeExplicitOwnerPreflight(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.db = self.home / "authority.sqlite"
        self.work = self.home / "workspace"
        self.sources = self.home / "sources"
        self.work.mkdir()
        self.sources.mkdir()
        for name, content in {
            "baseline.csv": "id,amount\nA,7\n",
            "actual.csv": "id,amount\nA,5\n",
            "irrelevant.csv": "id,amount\nA,1\n",
            "settings.json": '{"timeout":12}\n',
        }.items():
            (self.sources / name).write_text(content, encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
        self.before = {p.name: p.read_bytes()
                       for p in self.sources.iterdir()}

    def choice(self, root, intent):
        state = inspect_native_goal(self.db, self.work, self.sources, root)
        return {
            "selected_intent": intent, "alternative_intent": None,
            "decision_reason": "Use original owner constraints for exact local artifact.",
            "alternative_reason": "Other registered methods do not match owner intent.",
            "expected_evidence": "Independent Host readback must satisfy original owner.",
            "observation_sha256": state["observation_sha256"],
            "decision_basis": {
                "source_refs": [
                    {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
                    for name, raw in sorted(self.before.items())],
                "previous_result_task_id": None,
                "challenge": "A syntactically runnable tool could do unrelated work.",
                "falsifier": "Independent source and output readback rejects the plan.",
                "uncertainty": "Local success does not prove external business outcome.",
            },
        }

    @staticmethod
    def compare(ref, obs):
        return {"kind": "goal_intent", "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": ref},
                    {"role": "observed", "path": obs},
                ]}

    @staticmethod
    def structure():
        return {"kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "settings.json"}],
                "requirements": [{"field": "owner", "equals": "ops"}]}

    def unchanged(self):
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.sources.iterdir()},
            self.before)

    def test_model_reversed_csv_is_refused_pre_worker_but_correct_plan_passes(self):
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        with self.assertRaisesRegex(
                ValueError, "NATIVE_METHOD_CONTRADICTS_EXPLICIT_OWNER_CONTRACT"):
            admit_native_decision(
                self.db, self.work, self.sources, root,
                self.choice(root, self.compare("actual.csv", "baseline.csv")))
        self.assertEqual(
            inspect_native_goal(self.db, self.work, self.sources, root)
            ["decision_count"], 0)
        admitted = admit_native_decision(
            self.db, self.work, self.sources, root,
            self.choice(root, self.compare("baseline.csv", "actual.csv")))
        receipt = run_tick(self.db, self.work, self.sources, max_jobs=1)
        self.assertEqual(receipt["tasks"][0]["task_id"], admitted["child_task_id"])
        self.assertTrue(inspect_owner_local_outcome(
            self.db, self.work, self.sources, root)["local_owner_outcome_verified"])
        self.unchanged()

    def test_irrelevant_csv_for_named_json_goal_is_refused_before_worker(self):
        root = register_native_goal(
            self.db, "Please ensure an isolated draft of settings.json "
                     "has owner equal to ops.")
        with self.assertRaisesRegex(
                ValueError, "NATIVE_METHOD_CONTRADICTS_EXPLICIT_OWNER_CONTRACT"):
            admit_native_decision(
                self.db, self.work, self.sources, root,
                self.choice(root, self.compare("baseline.csv", "actual.csv")))
        self.assertEqual(
            inspect_native_goal(self.db, self.work, self.sources, root)
            ["decision_count"], 0)
        admitted = admit_native_decision(
            self.db, self.work, self.sources, root,
            self.choice(root, self.structure()))
        receipt = run_tick(
            self.db, self.work, self.sources,
            max_jobs=1, auto_stage_goals=True)
        self.assertEqual(receipt["tasks"][0]["task_id"], admitted["child_task_id"])
        self.assertTrue(inspect_owner_local_outcome(
            self.db, self.work, self.sources, root)["local_owner_outcome_verified"])
        self.unchanged()

    def test_composite_owner_request_can_progress_without_false_whole_success(self):
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences "
                     "and send the findings to staff.")
        admission = admit_native_decision(
            self.db, self.work, self.sources, root,
            self.choice(root, self.compare("baseline.csv", "actual.csv")))
        receipt = run_tick(self.db, self.work, self.sources, max_jobs=1)
        self.assertEqual(receipt["tasks"][0]["task_id"], admission["child_task_id"])
        outcome = inspect_owner_local_outcome(
            self.db, self.work, self.sources, root)
        self.assertFalse(outcome["local_owner_outcome_verified"])
        self.assertFalse(outcome["business_outcome_verified"])
        self.unchanged()


    def test_model_prompt_receives_independently_recognized_original_contract(self):
        """Small model guesses are not the authority for exact owner slots."""
        import json
        from unittest.mock import patch
        from cognition_agent_os.native_local_planner import propose_native_local
        root = register_native_goal(
            self.db, "Compare baseline.csv with actual.csv and report differences.")
        observed = []
        def read_model_request(method, path, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            context = json.loads(payload["prompt"].split("\n\n")[-1])
            observed.append(context["explicit_owner_local_contract_if_recognized"])
            return {"done": True, "response": '{"abstain":true}'}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=read_model_request):
            result = propose_native_local(
                self.db, self.work, self.sources, root,
                model="installed:test")
        self.assertEqual(result["status"], "NATIVE_LOCAL_MODEL_ABSTAINED")
        self.assertEqual(observed, [{
            "objective": "compare_records", "reference": "baseline.csv",
            "observed": "actual.csv"}])
        self.assertEqual(inspect_native_goal(
            self.db, self.work, self.sources, root)["decision_count"], 0)
        self.unchanged()


if __name__ == "__main__":
    unittest.main()
