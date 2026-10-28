"""Holdout: schema mode can constrain SHAPE, never certify method relevance.

No Ollama is invoked here. These are provider-compatibility and invariant
tests, NOT model-quality evidence.
"""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import register_native_goal, inspect_native_goal
from cognition_agent_os.native_local_planner import (
    _native_response_schema, propose_native_local)


class NativeStructuredOutputSafety(unittest.TestCase):
    def test_schema_retains_abstention_and_bounded_source_read(self):
        schema = _native_response_schema(
            [{"objective": "compare_records"},
             {"objective": "ensure_structure"}],
            ["actual.csv", "expected.csv"], "a" * 64, None)
        branches = schema["oneOf"]
        self.assertEqual(len(branches), 3)
        self.assertEqual(branches[0]["properties"]["abstain"]["const"], True)
        self.assertEqual(branches[1]["properties"]["inspect_sources"][
            "items"]["properties"]["path"]["enum"],
            ["actual.csv", "expected.csv"])
        decision = branches[2]
        self.assertEqual(decision["properties"]["observation_sha256"]["const"],
                         "a" * 64)
        basis = decision["properties"]["decision_basis"]
        self.assertEqual(basis["type"], "object")
        self.assertEqual(basis["properties"]["previous_result_task_id"]["type"],
                         "null")
        selected = decision["properties"]["selected_intent"]
        self.assertEqual(selected["type"], "object")
        self.assertEqual(selected["properties"]["objective"]["enum"],
                         ["compare_records", "ensure_structure"])
        self.assertIn("null", [
            x["type"] for x in
            decision["properties"]["alternative_intent"]["anyOf"]])
        self.assertNotIn("owner_outcome_verified", json.dumps(schema))
        self.assertNotIn("allow_public_discovery", json.dumps(schema))

    def test_schema_pins_prior_result_and_never_mints_permissions(self):
        child_id = "b" * 32
        schema = _native_response_schema(
            [{"objective": "investigate_evidence"}],
            ["notes.md"], "c" * 64, child_id)
        decision = schema["oneOf"][2]
        prior = decision["properties"]["decision_basis"][
            "properties"]["previous_result_task_id"]
        self.assertEqual(prior, {"type": "string", "const": child_id})
        self.assertEqual(
            decision["properties"]["selected_intent"]["properties"][
                "objective"]["enum"], ["investigate_evidence"])
        self.assertNotIn("write_allowed", json.dumps(schema))
        self.assertNotIn("external_effect_authorized", json.dumps(schema))

    def test_schema_cannot_invent_unregistered_hypothesis_reviews(self):
        # Real 0.5B schema trial incorrectly generated a fabricated review
        # keyed to the observation hash even though no hypothesis was filed.
        none = _native_response_schema(
            [{"objective": "compare_records"}],
            ["baseline.csv", "actual.csv"], "e"*64, None,
            pending_hypotheses=[])
        decision = none["oneOf"][2]
        self.assertNotIn("hypothesis_reviews", decision["properties"])
        self.assertNotIn("hypothesis_reviews", decision["required"])
        proper = _native_response_schema(
            [{"objective": "compare_records"}],
            ["baseline.csv", "actual.csv"], "f"*64, None,
            pending_hypotheses=[{"proposal_sha256": "a"*64},
                                {"proposal_sha256": "b"*64}])
        decision = proper["oneOf"][2]
        reviews = decision["properties"]["hypothesis_reviews"]
        self.assertIn("hypothesis_reviews", decision["required"])
        self.assertEqual(reviews["minItems"], 2)
        self.assertEqual(reviews["maxItems"], 2)
        self.assertEqual(reviews["items"]["properties"][
            "proposal_sha256"]["enum"], ["a"*64, "b"*64])

    def test_schema_abstain_does_not_create_worker_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "ledger.sqlite"
            workspace = root / "workspace"
            fixtures = root / "fixtures"
            workspace.mkdir()
            fixtures.mkdir()
            (fixtures / "notes.md").write_text(
                "No authority to publish customer data.\n", encoding="utf-8")
            with closing(connect(db)) as conn:
                initialize(conn)
            goal = register_native_goal(
                db, "Upload production customer data without authorization.")
            requests = []
            def real_transport_boundary(method, endpoint, payload, timeout):
                if method == "GET":
                    return {"models": [{"name": "test:installed"}]}
                requests.append(payload)
                return {"done": True, "response": '{"abstain":true}'}
            with patch("cognition_agent_os.local_model._request",
                       side_effect=real_transport_boundary):
                result = propose_native_local(
                    db, workspace, fixtures, goal, model="test:installed",
                    structured_output=True)
            self.assertEqual(result["status"], "NATIVE_LOCAL_MODEL_ABSTAINED")
            self.assertEqual(len(requests), 1)
            self.assertIsInstance(requests[0]["format"], dict)
            state = inspect_native_goal(db, workspace, fixtures, goal)
            self.assertEqual(state["decision_count"], 0)


if __name__ == "__main__":
    unittest.main()
