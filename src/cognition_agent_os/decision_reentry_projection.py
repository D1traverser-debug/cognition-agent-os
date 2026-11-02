"""Read-only typed decision re-entry projection (never execution authority).

Causal parents can invalidate dependent effects. Review parents only identify
prior decisions that must be challenged/reconsidered; they never prove
causality or invalidate another decision. Chronology alone creates no edge.
The caller must independently authenticate every relationship.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    decision_id: str
    parent_ids: tuple[str, ...] = ()
    layer: str = "unspecified"
    review_parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Contradiction:
    """An observation requesting re-entry, not a verified causal conclusion."""

    evidence_ref: str
    reopen_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReentryProjection:
    reopen_required: tuple[str, ...]
    descendants_invalidated: tuple[str, ...]
    ancestors_to_challenge: tuple[str, ...]
    review_descendant_decisions_to_reopen: tuple[str, ...]
    review_descendant_effects_to_reverify: tuple[str, ...]
    unaffected: tuple[str, ...]
    evidence_ref: str
    outcome_verified: bool = False
    authorizes_action: bool = False


def project_reentry(decisions: tuple[Decision, ...], contradiction: Contradiction
                    ) -> ReentryProjection:
    """Project causal invalidation separately from reasoning-review re-entry.

    A causal parent edge can invalidate downstream effects. A review-parent
    edge only schedules a prior or later decision for renewed challenge. It
    never invalidates that decision or its effect. Unknown references and
    cycles fail closed across both relationship types.
    """
    if (not decisions or not isinstance(contradiction.evidence_ref, str)
        or not contradiction.evidence_ref.strip() or not contradiction.reopen_ids):
        raise ValueError("INCOMPLETE_DECISION_EVIDENCE")
    nodes = {node.decision_id: node for node in decisions}
    if len(nodes) != len(decisions) or any(
            not isinstance(k, str) or not k.strip() for k in nodes):
        raise ValueError("DUPLICATE_OR_EMPTY_DECISION_ID")
    if any(not isinstance(node.layer, str) or not node.layer.strip()
           for node in decisions):
        raise ValueError("EMPTY_CAUSAL_LAYER")

    causal_children: dict[str, set[str]] = {key: set() for key in nodes}
    review_children: dict[str, set[str]] = {key: set() for key in nodes}
    all_children: dict[str, set[str]] = {key: set() for key in nodes}

    for node in decisions:
        if len(set(node.parent_ids)) != len(node.parent_ids):
            raise ValueError("DUPLICATE_CAUSAL_PARENT")
        if len(set(node.review_parent_ids)) != len(node.review_parent_ids):
            raise ValueError("DUPLICATE_REVIEW_PARENT")
        for parent_id in node.parent_ids:
            if parent_id not in nodes or parent_id == node.decision_id:
                raise ValueError("UNKNOWN_OR_SELF_CAUSAL_PARENT")
            causal_children[parent_id].add(node.decision_id)
            all_children[parent_id].add(node.decision_id)
        for parent_id in node.review_parent_ids:
            if parent_id not in nodes or parent_id == node.decision_id:
                raise ValueError("UNKNOWN_OR_SELF_REVIEW_PARENT")
            review_children[parent_id].add(node.decision_id)
            all_children[parent_id].add(node.decision_id)

    # Validate each relationship class independently, then the combined
    # graph. This catches a causal edge opposed by a review edge as well.
    def validate_acyclic(children: dict[str, set[str]], error_code: str) -> None:
        color: dict[str, int] = {}

        def visit(identifier: str) -> None:
            if color.get(identifier) == 1:
                raise ValueError(error_code)
            if color.get(identifier) == 2:
                return
            color[identifier] = 1
            for child_id in sorted(children[identifier]):
                visit(child_id)
            color[identifier] = 2

        for identifier in sorted(nodes):
            visit(identifier)

    validate_acyclic(causal_children, "CAUSAL_GRAPH_CYCLE")
    validate_acyclic(review_children, "REVIEW_GRAPH_CYCLE")
    validate_acyclic(all_children, "DECISION_RELATIONSHIP_CYCLE")

    targets = set(contradiction.reopen_ids)
    if not targets.issubset(nodes):
        raise ValueError("UNKNOWN_REENTRY_TARGET")

    def descendants(frontier: set[str], children: dict[str, set[str]]) -> set[str]:
        found: set[str] = set()
        pending = list(frontier)
        while pending:
            current = pending.pop()
            for child_id in children[current]:
                if child_id not in targets and child_id not in found:
                    found.add(child_id)
                    pending.append(child_id)
        return found

    invalidated = descendants(targets, causal_children)
    review_descendants = descendants(targets, review_children) - invalidated
    # A review-descendant decision's own produced effects also need fresh
    # readback. They are NOT causally invalidated by the ancestor's failure.
    review_descendant_nodes = set(review_descendants)
    pending_review_effects = list(review_descendants)
    while pending_review_effects:
        current = pending_review_effects.pop()
        for child_id in causal_children[current]:
            if (child_id not in targets and child_id not in invalidated
                and child_id not in review_descendant_nodes):
                review_descendant_nodes.add(child_id)
                pending_review_effects.append(child_id)

    ancestors: set[str] = set()
    pending = list(targets)
    while pending:
        current = pending.pop()
        for parent_id in (
            *nodes[current].parent_ids, *nodes[current].review_parent_ids
        ):
            if parent_id not in ancestors and parent_id not in targets:
                ancestors.add(parent_id)
                pending.append(parent_id)

    review_decisions = {
        identifier for identifier in review_descendant_nodes
        if nodes[identifier].layer != "execution"
        and nodes[identifier].layer != "authority"
    }
    review_effects = {
        identifier for identifier in review_descendant_nodes
        if nodes[identifier].layer == "execution"
    }
    unaffected = (
        set(nodes) - targets - invalidated - ancestors - review_descendant_nodes
    )

    return ReentryProjection(
        reopen_required=tuple(sorted(targets)),
        descendants_invalidated=tuple(sorted(invalidated)),
        ancestors_to_challenge=tuple(sorted(ancestors)),
        review_descendant_decisions_to_reopen=tuple(sorted(review_decisions)),
        review_descendant_effects_to_reverify=tuple(sorted(review_effects)),
        unaffected=tuple(sorted(unaffected)),
        evidence_ref=contradiction.evidence_ref,
    )
