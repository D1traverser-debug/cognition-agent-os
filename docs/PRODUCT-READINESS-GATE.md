# Integrated product readiness gate — 2026-10-23 (PR #26 candidate)

**Current disposition: NOT_READY for unattended autonomous use.** Green CI is component evidence, not business outcome, deployed host, or autonomous planning evidence.

## Required single-system acceptance

1. **Goal -> choice:** Given a registered goal, bounded budget, legal grants and at least two registered capabilities, the common controller independently selects the next task. An adverse independent verdict causes a *different* authorized plan to be selected and durably admitted without a new chat prompt.
2. **Choice -> execution -> revision:** The newly selected task actually runs in the same task ledger. Independent readback changes the original goal's decision on the next tick. Repetition, no-progress and budget exhaustion halt safely.
3. **Unattended host:** A real external trigger invokes host ticks repeatedly while the user is absent; restart preserves lineage and avoids duplicate effects.
4. **Conformance and safety:** Scope, revocation, policy, lease fencing and attempt budgets are enforced at effect boundaries. Independent conformance finds systemic failures, creates constrained repairs, verifies impact across sibling paths, and requires legitimate promotion authority.
5. **Generalization:** Two materially different held-out task domains pass this *same* control-loop test without domain-specific controller branches. A production test evaluates owner-meaningful outcomes, not just hashes.
6. **Evidence attribution:** Every acceptance claim links specific executed artifact, authority, evaluator, host trigger and independent effect; unverified is not pass.

## Evidence at this revision

- Installable `cognition-os` CLI and durable SQLite task ledger: VERIFIED as a bounded prototype on ephemeral Ubuntu and Windows CI; database is created by explicit `init`, not by `status` or a missing-path seed. This is not installation on the owner's machine.
- Deterministic registered task execution and independent mechanical checks: PARTIALLY INTEGRATED.
- Independent **local** negative-outcome -> bounded second preauthorized alternative -> admitted child -> execution -> subsequent mechanical verification: **IMPLEMENTED FOR TWO FIXED DOMAINS, NOT A GENERAL OUTCOME CONTROLLER**. Current JSON/CSV and record-reconciliation adapters still contain domain-specific decisions; neither new method discovery nor external business-outcome acceptance has been shown.
- Existing PR24→PR25 architecture A/B: seven reproducible local scenarios × three runs, unchanged terminal-state behavior and stable traces, **PASS**; does not establish optimality or general autonomy.
- Official Graphify structural path check: **PASS** for call-edge inventory, not semantic comprehension; AOCI official bootstrap has zero model-authored entries, index not aligned.
- Current candidate cross-platform installation: **PASS** on Ubuntu and Windows via independent venv, with revoke persistence and malformed-DB refusal; not approval to deploy.
- Real user's unattended long-lived deployment: **NOT VERIFIED**.
- Multi-domain outcome-based held-out generalization: **NOT VERIFIED**.
- End-to-end self-governance including authorized promotion and recurrence prevention: **NOT VERIFIED**.

## Immediate implementation order

The remaining product blockers are qualitatively different from fixing the packaging:
1. Freeze an owner-specific, independently measurable real business objective and permission contract. Validate real external effect readback with an independent checker not authored or controlled by the planner.
2. Under identical models/budgets and blinded task sets, compare raw-repo context versus Graphify, genuine model-authored AOCI, and AOCI+Graphify. Reject tooling that increases stale-context or maintenance failures without improving correct outcomes.
3. Test new, previously unknown task types and causal alternative selection across at least two materially different real domains. Track objective completion, permission denials, repeats, negative transfer, latency and human corrections.
4. Only after the above, verify original OT06 new-chat continuity against the live authoritative state and real owner-device unattended operation. Hosted CI scheduler is not a substitute.

Keep PR #26 in Draft and PR #25 as historical experimental evidence. Do not treat the initial local `init` write flag as a user-approved remote production grant.

**Release rule:** Until all six gates have end-to-end evidence on the same system candidate, the project must not be described as a usable autonomous OS. Do not conflate GitHub Actions with a deployed controller. Draft branches must not be merged or deployed implicitly.
