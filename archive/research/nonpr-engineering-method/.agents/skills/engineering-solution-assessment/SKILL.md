---
name: engineering-solution-assessment
description: "Use for new features, defect diagnosis, recurring failures, compatibility/refactoring changes and significant architecture decisions in this repository. Validate the real objective and entrypoint, challenge initial fixes, compare viable solutions, test outcomes and preserve fit/nonfit evidence. Not for ordinary Q&A."
---

# Evidence-driven engineering solution assessment

The objective is to complete unfamiliar and complex engineering work without expecting the user to foresee every failure or prescribe correct techniques. This skill is a **workflow resource**, not a second authority, task ledger or new Agent.

## Start from actual behavior, not a guessed patch

Recover owner-desired observable behavior, original source of requirements, nonnegotiable contracts, and affected users. Separate user or model **proposed solutions** from binding outcomes. Inspect actual code and runtime entrypoint; trace CLI, Host, Worker, caller, permissions and environment as relevant. A function that exists but is never triggered has not delivered a feature.

Consult `references/failure-classes.md` for unfamiliar or systemic tasks. Search for hidden/unknown factors, not just matching keywords.

## Choose rather than imitate methods

Consult `references/method-selection.md` and `knowledge/engineering-methods/method_cards_v1.json`. Research primary current materials if their fit or API is unclear. Compare no-change/diagnosis, compatible extension and change at the owning abstraction for material cases. Evaluate correctness, blast radius, contract migration, security, recovery, maintainability, total complexity and rollback. Seek an observation that would **disprove** the favored plan. Choose the best **complete** authorized intervention, which may be local or architectural; do not equate fewest edited lines with minimal risk.

DDD, Spec Kit, Superpowers, ADR, stateful testing, contract tests and architecture fitness checks are competing **tools**, not mandatory rituals. Do not automatically install a framework. If the task needs deep reasoning, do not defer essential capability merely for a quick green CI.

## Implement and refute the success claim

Check the normal real entrypoint, error/negative path, old-user compatibility, distinct environment and recovery when applicable. For long-lived architectural changes, test a changed requirement and an unrelated protected behavior. Use independent/source-bound oracle and record exactly which business outcome can or cannot be observed; a self-written unit test or valid JSON cannot alone certify it.

A failed result reopens the diagnosis and even the method choice. Do not mask problems by adding a rule or writing another congratulatory report.

## Learning that changes future work

Consult `references/learning-and-transfer.md`. Record external primary source, when a method fits/does not fit, disconfirming evidence, actual verification and a genuinely different follow-up task where the method transfers. New knowledge remains CANDIDATE until independently verified; do not duplicate the existing owner’s evolution controller.

## Completion evidence

Report user goal, selected vs rejected approaches, actual commits/call path and independent checks, non-regressions, unresolved uncertainty and next real blocker. **If actual Codex/ChatGPT host did not load the skill, say activation was not observed.** Do not claim user account custom instructions were changed.
