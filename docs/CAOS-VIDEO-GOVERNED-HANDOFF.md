# CAOS parent -> Video Studio governed execution boundary (candidate)

## Failure being addressed

An owner selected Video work within an existing CAOS-governed conversation; the assistant performed Video-only analysis without a prior owner-goal/corrections restoration, source criticism, method comparison, or independent owner-outcome check. The Video standalone runtime's absence of a CAOS API dependency was misread as permission to bypass CAOS governance.

## Why this is an architecture repair, not another checklist

Video Studio's existing StudioEngine can claim a ready task without any parent admission. Its candidate Video branch uses existing project/task and append-only event records to refuse a CAOS_PARENT project claim until a current brief-bound receipt is admitted. The parent source adds child_handoff.py to prepare that portable receipt without adding a Host, a second ledger, or duplicating Video business state.

CLI: python -m cognition_agent_os.child_handoff --project-id PROJECT --brief video-brief.json --draft reviewed-decision.json --output parent-receipt.json

CLI on child: vga-studio --root WORKSPACE admit-parent-handoff PROJECT parent-receipt.json

A governed Video brief requires governance.mode=CAOS_PARENT, governance.parent_system=cognition-agent-os and an explicit allowed_effects list. The parent input draft includes owner_goal_ref, owner_corrections, source_refs, decision (competing hypotheses/tests, alternatives, falsifier, rollback), allowed_effects, verification (owner_outcomes and independent_evidence), unknowns. This exact schema is checked in both repos. The resulting receipt binds to the JSON brief SHA-256 and exact project identity.

## Decision alternatives

A. More Skill text alone: inexpensive but does not prevent prior failure; rejected as sole remedy.
B. Require CAOS Runtime for every Video project: centralizes too much, breaks legitimate standalone use, lacks evidence of necessity; not chosen.
C. Cross-boundary optional governed mode with an execution admission check: selected as a conditional candidate because it closes a concrete native task-claim bypass, preserves child authority and has negative tests.

## Remaining independent failure modes

The receipt is a structural/identity binding, NOT a signed grant, a proof of research, a source-truth verdict or an independent owner-outcome result. An agent could still incorrectly start a new task as standalone, especially if ChatGPT did not select the CAOS Skill. Native Skill invocation and origin-classification require first-party conversation traces, not the module or synthetic tests. Test against legitimate unrelated chats as a negative control; do not force CAOS globally.

Do not promote this candidate before same-commit CI, cross-repo controlled integration, independent source/owner acceptance, and real ChatGPT first-mile evidence. No production deployment or merge is implied by this document.