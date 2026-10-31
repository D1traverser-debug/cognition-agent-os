"""Bounded graph invariants; never proves business or semantic causality.

The native SQLite admission path separately authenticates source and decision
receipts. These tests ensure that the projection cannot invent an edge just
because one decision followed another chronologically.
"""
import unittest

from cognition_agent_os.decision_reentry_projection import (
    Contradiction, Decision, project_reentry,
)


class NativeCausalProjectionTests(unittest.TestCase):
    def test_sibling_after_sibling_is_not_causally_invalidated(self):
        nodes = (
            Decision("owner", layer="authority"),
            Decision("a", ("owner",), layer="method"),
            Decision("a_effect", ("a",), layer="execution"),
            Decision("b", ("owner",), layer="method"),
            Decision("b_effect", ("b",), layer="execution"),
        )
        result = project_reentry(nodes, Contradiction(
            "provider-sha256:evidence", ("a",)))
        self.assertEqual(result.reopen_required, ("a",))
        self.assertEqual(result.descendants_invalidated, ("a_effect",))
        self.assertEqual(set(result.unaffected), {"b", "b_effect"})
        self.assertEqual(result.ancestors_to_challenge, ("owner",))
        self.assertFalse(result.authorizes_action)
        self.assertFalse(result.outcome_verified)

    def test_explicitly_linked_child_would_be_invalidated_if_evidence_proved_link(self):
        nodes = (
            Decision("a"),
            Decision("a_effect", ("a",)),
            Decision("b", ("a_effect",)),
            Decision("b_effect", ("b",)),
        )
        result = project_reentry(nodes, Contradiction(
            "evidence-authenticated-outside-this-function", ("a",)))
        self.assertEqual(set(result.descendants_invalidated), {
            "a_effect", "b", "b_effect"})

    def test_multi_parent_descendant_invalidated_once(self):
        nodes = (Decision("a"), Decision("b"),
                 Decision("shared", ("a", "b")))
        result = project_reentry(nodes, Contradiction(
            "evidence:1", ("a", "b")))
        self.assertEqual(result.descendants_invalidated, ("shared",))

    def test_unrelated_cycle_fails_closed(self):
        nodes = (Decision("a", ("b",)), Decision("b", ("a",)),
                 Decision("valid"))
        with self.assertRaisesRegex(ValueError, "CAUSAL_GRAPH_CYCLE"):
            project_reentry(nodes, Contradiction("evidence:1", ("valid",)))

    def test_unknown_parent_and_missing_target_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_SELF_CAUSAL_PARENT"):
            project_reentry((Decision("a", ("ghost",)),),
                            Contradiction("evidence:1", ("a",)))
        with self.assertRaisesRegex(ValueError, "UNKNOWN_REENTRY_TARGET"):
            project_reentry((Decision("a"),),
                            Contradiction("evidence:1", ("ghost",)))

    def test_model_authored_evidence_is_not_an_independent_oracle(self):
        result = project_reentry((Decision("a"),),
            Contradiction("model-self-report:I-have-proven-it", ("a",)))
        self.assertFalse(result.authorizes_action)
        self.assertFalse(result.outcome_verified)


if __name__ == "__main__":
    unittest.main()
