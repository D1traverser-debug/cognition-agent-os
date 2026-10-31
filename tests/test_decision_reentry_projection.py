import unittest

from cognition_agent_os.decision_reentry_projection import (
    Contradiction, Decision, project_reentry,
)


class ReentryProjectionTests(unittest.TestCase):
    def setUp(self):
        self.nodes = (
            Decision("original_goal", layer="authority"),
            Decision("source_read", ("original_goal",), "source"),
            Decision("entry_selection", ("source_read",), "entry"),
            Decision("decision_method", ("entry_selection",), "method"),
            Decision("execute_patch", ("decision_method",), "implementation"),
            Decision("claim_complete", ("execute_patch",), "evaluation"),
            Decision("unrelated_business", ("original_goal",), "business"),
        )

    def test_missing_original_lines_reopens_source_and_invalidates_descendants(self):
        # Actual 2026-10-31 failure: only 90 of 364 original contract lines
        # were read, yet the assistant claimed to have restored the whole.
        r = project_reentry(self.nodes, Contradiction(
            "contract:2026-10-25:read=1-90/of-364", ("source_read",)))
        self.assertEqual(r.reopen_required, ("source_read",))
        self.assertEqual(r.ancestors_to_challenge, ("original_goal",))
        self.assertEqual(set(r.descendants_invalidated), {
            "entry_selection", "decision_method", "execute_patch", "claim_complete"})
        self.assertEqual(r.unaffected, ("unrelated_business",))
        self.assertFalse(r.authorizes_action)
        self.assertFalse(r.outcome_verified)

    def test_local_failure_reopens_implementation_but_challenges_parent_method(self):
        r = project_reentry(self.nodes, Contradiction(
            "external:posteffect-readback#failed", ("execute_patch",)))
        self.assertEqual(r.descendants_invalidated, ("claim_complete",))
        self.assertIn("decision_method", r.ancestors_to_challenge)
        self.assertNotIn("original_goal", r.reopen_required)

    def test_escalation_reopens_architecture_when_evidence_targets_it(self):
        r = project_reentry(self.nodes, Contradiction(
            "source:architecture-falsifier@sha256", ("decision_method",)))
        self.assertIn("execute_patch", r.descendants_invalidated)
        self.assertIn("claim_complete", r.descendants_invalidated)
        self.assertIn("entry_selection", r.ancestors_to_challenge)

    def test_dag_shared_descendant_is_invalidated_once(self):
        nodes = (Decision("a"), Decision("b"), Decision("shared", ("a", "b")))
        r = project_reentry(nodes, Contradiction("evidence:1", ("a", "b")))
        self.assertEqual(r.descendants_invalidated, ("shared",))

    def test_unknown_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_REENTRY_TARGET"):
            project_reentry(self.nodes, Contradiction("source:1", ("nonexistent",)))

    def test_partial_broken_graph_rejected_even_if_unrelated(self):
        nodes = self.nodes + (Decision("orphan", ("missing",)),)
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_SELF_CAUSAL_PARENT"):
            project_reentry(nodes, Contradiction("source:1", ("source_read",)))

    def test_cycle_rejected(self):
        nodes = (Decision("a", ("c",)), Decision("b", ("a",)),
                 Decision("c", ("b",)))
        with self.assertRaisesRegex(ValueError, "CAUSAL_GRAPH_CYCLE"):
            project_reentry(nodes, Contradiction("source:1", ("a",)))

    def test_no_evidence_ref_or_targets_rejected(self):
        for c in (Contradiction("", ("source_read",)), Contradiction("x", ())):
            with self.assertRaisesRegex(ValueError, "INCOMPLETE_DECISION_EVIDENCE"):
                project_reentry(self.nodes, c)


if __name__ == "__main__":
    unittest.main()