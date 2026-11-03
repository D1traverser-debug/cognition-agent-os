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

    def test_review_parent_is_challenged_without_causal_invalidation(self):
        nodes = (
            Decision("owner", layer="authority"),
            Decision("a", layer="method", review_parent_ids=("owner",)),
            Decision("a_effect", ("a",), layer="execution"),
            Decision("b", layer="method", review_parent_ids=("owner", "a")),
            Decision("b_effect", ("b",), layer="execution"),
        )
        result = project_reentry(nodes, Contradiction(
            "evidence:later-failure", ("b",)))
        self.assertEqual(result.ancestors_to_challenge, ("a", "owner"))
        self.assertEqual(result.descendants_invalidated, ("b_effect",))
        self.assertEqual(result.review_descendant_decisions_to_reopen, ())
        self.assertEqual(result.review_descendant_effects_to_reverify, ())
        self.assertFalse(result.authorizes_action)
        self.assertFalse(result.outcome_verified)

    def test_contradicted_decision_reopens_only_explicit_review_descendants(self):
        nodes = (
            Decision("owner", layer="authority"),
            Decision("a", layer="method", review_parent_ids=("owner",)),
            Decision("a_effect", ("a",), layer="execution"),
            Decision("b", layer="method", review_parent_ids=("owner", "a")),
            Decision("b_effect", ("b",), layer="execution"),
            Decision("c", layer="method", review_parent_ids=("owner",)),
            Decision("c_effect", ("c",), layer="execution"),
        )
        result = project_reentry(nodes, Contradiction(
            "evidence:source-drift", ("a",)))
        self.assertEqual(result.descendants_invalidated, ("a_effect",))
        self.assertEqual(result.review_descendant_decisions_to_reopen, ("b",))
        self.assertEqual(result.review_descendant_effects_to_reverify, ("b_effect",))
        self.assertEqual(result.ancestors_to_challenge, ("owner",))
        self.assertEqual(set(result.unaffected), {"c", "c_effect"})

    def test_invalidated_causal_child_reopens_its_review_dependents(self):
        """A ->causal B ->review C must not leave C or its effect unaffected.

        The review link is not a new causal invalidation; C is challenged,
        and its independent effect needs a fresh readback.
        """
        nodes = (
            Decision("a", layer="method"),
            Decision("b", ("a",), layer="method"),
            Decision("c", layer="method", review_parent_ids=("b",)),
            Decision("c_effect", ("c",), layer="execution"),
            Decision("independent", layer="execution"),
        )
        result = project_reentry(nodes, Contradiction(
            "source:verified-snapshot-changed", ("a",)))
        self.assertEqual(result.descendants_invalidated, ("b",))
        self.assertEqual(result.review_descendant_decisions_to_reopen, ("c",))
        self.assertEqual(result.review_descendant_effects_to_reverify,
                         ("c_effect",))
        self.assertEqual(result.unaffected, ("independent",))
        self.assertFalse(result.authorizes_action)
        self.assertFalse(result.outcome_verified)

    def test_review_causal_review_chain_requires_second_review_pass(self):
        """A ->review B ->causal effect ->review C must reach C too."""
        nodes = (
            Decision("a", layer="method"),
            Decision("b", layer="method", review_parent_ids=("a",)),
            Decision("b_effect", ("b",), layer="execution"),
            Decision("c", layer="method", review_parent_ids=("b_effect",)),
            Decision("c_effect", ("c",), layer="execution"),
            Decision("independent", layer="method"),
        )
        result = project_reentry(nodes, Contradiction(
            "source:verified-snapshot-changed", ("a",)))
        self.assertEqual(result.descendants_invalidated, ())
        self.assertEqual(result.review_descendant_decisions_to_reopen,
                         ("b", "c"))
        self.assertEqual(result.review_descendant_effects_to_reverify,
                         ("b_effect", "c_effect"))
        self.assertEqual(result.unaffected, ("independent",))
        self.assertFalse(result.authorizes_action)
        self.assertFalse(result.outcome_verified)

    def test_four_node_mixed_dags_against_independent_parent_oracle(self):
        """Exhaustive tiny DAGs: typed dependency paths, including both edge types.

        The oracle propagates from earlier PARENTS rather than walking the
        implementation's child edges. 4**6=4096 labelled DAGs, each with
        a causally contradictory first decision and independent effect node.
        """
        from itertools import product

        pairs = tuple((i, j) for i in range(4) for j in range(i + 1, 4))
        for choices in product(range(4), repeat=len(pairs)):
            # 0=no edge, 1=causal, 2=review, 3=both.
            parents = [[] for _ in range(4)]
            review_parents = [[] for _ in range(4)]
            for (parent, child), kind in zip(pairs, choices):
                if kind & 1:
                    parents[child].append(parent)
                if kind & 2:
                    review_parents[child].append(parent)
            nodes = tuple(Decision(
                f"n{i}", tuple(f"n{p}" for p in parents[i]),
                layer="execution" if i == 3 else "method",
                review_parent_ids=tuple(f"n{p}" for p in review_parents[i]))
                for i in range(4))
            # Parent-oriented oracle: causal paths propagate invalidation;
            # review edges (or causal descendants of a review) propagate only
            # reconsideration. Neither transfers authority nor owner truth.
            invalidated = [False] * 4
            review_needed = [False] * 4
            for child in range(1, 4):
                invalidated[child] = any(
                    parent == 0 or invalidated[parent]
                    for parent in parents[child])
                review_needed[child] = (
                    any(parent == 0 or invalidated[parent]
                        or review_needed[parent]
                        for parent in review_parents[child])
                    or any(review_needed[parent] for parent in parents[child]))
            expected_invalidated = {
                f"n{i}" for i in range(1, 4) if invalidated[i]}
            expected_review = {
                f"n{i}" for i in (1, 2)
                if review_needed[i] and not invalidated[i]}
            expected_reverify = (
                {"n3"} if review_needed[3] and not invalidated[3] else set())
            result = project_reentry(nodes, Contradiction(
                "independently-observed-changed-source", ("n0",)))
            self.assertEqual(set(result.descendants_invalidated),
                             expected_invalidated, choices)
            self.assertEqual(set(result.review_descendant_decisions_to_reopen),
                             expected_review, choices)
            self.assertEqual(set(result.review_descendant_effects_to_reverify),
                             expected_reverify, choices)
            self.assertEqual(set(result.unaffected),
                             {f"n{i}" for i in range(1, 4)}
                             - expected_invalidated - expected_review
                             - expected_reverify, choices)
            self.assertFalse(result.authorizes_action)
            self.assertFalse(result.outcome_verified)

    def test_review_parent_cycles_and_unknown_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "REVIEW_GRAPH_CYCLE"):
            project_reentry((
                Decision("a", layer="method", review_parent_ids=("b",)),
                Decision("b", layer="method", review_parent_ids=("a",)),
            ), Contradiction("evidence:1", ("a",)))
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_SELF_REVIEW_PARENT"):
            project_reentry((
                Decision("a", layer="method", review_parent_ids=("ghost",)),
            ), Contradiction("evidence:1", ("a",)))

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
