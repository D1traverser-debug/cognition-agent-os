"""Read-only recursive decision re-entry projection (candidate, NOT execution authority).

This projects a causal decision DAG without mutating an existing Host ledger.
A caller must independently authenticate its decision/evidence inputs. Neither
this output nor a model-authored claim confers permission or verifies outcomes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    decision_id: str
    parent_ids: tuple[str, ...] = ()
    layer: str = "unspecified"


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
    unaffected: tuple[str, ...]
    evidence_ref: str
    outcome_verified: bool = False
    authorizes_action: bool = False


def project_reentry(decisions: tuple[Decision, ...], contradiction: Contradiction
                    ) -> ReentryProjection:
    """Fail closed on unknown references/cycles; reopen targets and descendants.

    An upstream decision is *challenged*, not automatically falsified: the
    caller must obtain discriminating evidence before escalating to re-open it.
    """
    if not decisions or not contradiction.evidence_ref.strip() or not contradiction.reopen_ids:
        raise ValueError("INCOMPLETE_DECISION_EVIDENCE")
    nodes = {node.decision_id: node for node in decisions}
    if len(nodes) != len(decisions) or any(not k.strip() for k in nodes):
        raise ValueError("DUPLICATE_OR_EMPTY_DECISION_ID")
    if any(not node.layer.strip() for node in decisions):
        raise ValueError("EMPTY_CAUSAL_LAYER")
    children: dict[str, set[str]] = {key: set() for key in nodes}
    for node in decisions:
        if len(set(node.parent_ids)) != len(node.parent_ids):
            raise ValueError("DUPLICATE_CAUSAL_PARENT")
        for parent_id in node.parent_ids:
            if parent_id not in nodes or parent_id == node.decision_id:
                raise ValueError("UNKNOWN_OR_SELF_CAUSAL_PARENT")
            children[parent_id].add(node.decision_id)

    # Validate the entire graph, including unrelated branches. A malformed
    # relationship cannot be ignored just because the selected target is safe.
    color: dict[str, int] = {}

    def visit(identifier: str) -> None:
        if color.get(identifier) == 1:
            raise ValueError("CAUSAL_GRAPH_CYCLE")
        if color.get(identifier) == 2:
            return
        color[identifier] = 1
        for child_id in sorted(children[identifier]):
            visit(child_id)
        color[identifier] = 2

    for identifier in sorted(nodes):
        visit(identifier)

    targets = set(contradiction.reopen_ids)
    if not targets.issubset(nodes):
        raise ValueError("UNKNOWN_REENTRY_TARGET")
    invalidated = set()
    frontier = list(targets)
    while frontier:
        current = frontier.pop()
        for child_id in children[current]:
            if child_id not in targets and child_id not in invalidated:
                invalidated.add(child_id)
                frontier.append(child_id)

    ancestors = set()
    frontier = list(targets)
    while frontier:
        current = frontier.pop()
        for parent_id in nodes[current].parent_ids:
            if parent_id not in ancestors and parent_id not in targets:
                ancestors.add(parent_id)
                frontier.append(parent_id)

    unaffected = set(nodes) - targets - invalidated - ancestors
    return ReentryProjection(
        reopen_required=tuple(sorted(targets)),
        descendants_invalidated=tuple(sorted(invalidated)),
        ancestors_to_challenge=tuple(sorted(ancestors)),
        unaffected=tuple(sorted(unaffected)),
        evidence_ref=contradiction.evidence_ref,
    )


@dataclass(frozen=True)
class ReadWindow:
    """Provider-returned inclusive source range; not model-asserted coverage."""
    version: str
    first: int
    last: int


@dataclass(frozen=True)
class CoverageProjection:
    missing_ranges: tuple[tuple[int, int], ...]
    all_source_units_read: bool
    semantic_understanding_verified: bool = False


def project_read_coverage(*, expected_version: str, total_units: int,
                          windows: tuple[ReadWindow, ...]) -> CoverageProjection:
    """Report byte/line coverage only; never claim meaning or business outcome.

    A read receipt from another version cannot fill a gap. The caller still
    must authenticate provider window receipts and expected source length.
    """
    if not expected_version or total_units <= 0:
        raise ValueError("SOURCE_IDENTITY_UNVERIFIABLE")
    covered = bytearray(total_units)
    for window in windows:
        if (window.version != expected_version or window.first < 1
            or window.last > total_units or window.last < window.first):
            raise ValueError("SOURCE_READ_WINDOW_UNVERIFIABLE")
        covered[window.first - 1:window.last] = b"\x01" * (window.last - window.first + 1)
    missing: list[tuple[int, int]] = []
    start = None
    for pos, bit in enumerate(covered, start=1):
        if not bit and start is None:
            start = pos
        if bit and start is not None:
            missing.append((start, pos - 1))
            start = None
    if start is not None:
        missing.append((start, total_units))
    return CoverageProjection(tuple(missing), not missing)