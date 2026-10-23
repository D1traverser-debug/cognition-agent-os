# Integrated product readiness gate — 2026-10-22

**Current disposition: NOT_READY for unattended autonomous use.** Green CI is component evidence, not business outcome, deployed host, or autonomous planning evidence.

## Required single-system acceptance

1. **Goal -> choice:** Given a registered goal, bounded budget, legal grants and at least two registered capabilities, the common controller independently selects the next task. An adverse independent verdict causes a *different* authorized plan to be selected and durably admitted without a new chat prompt.
2. **Choice -> execution -> revision:** The newly selected task actually runs in the same task ledger. Independent readback changes the original goal's decision on the next tick. Repetition, no-progress and budget exhaustion halt safely.
3. **Unattended host:** A real external trigger invokes host ticks repeatedly while the user is absent; restart preserves lineage and avoids duplicate effects.
4. **Conformance and safety:** Scope, revocation, policy, lease fencing and attempt budgets are enforced at effect boundaries. Independent conformance finds systemic failures, creates constrained repairs, verifies impact across sibling paths, and requires legitimate promotion authority.
5. **Generalization:** Two materially different held-out task domains pass this *same* control-loop test without domain-specific controller branches. A production test evaluates owner-meaningful outcomes, not just hashes.
6. **Evidence attribution:** Every acceptance claim links specific executed artifact, authority, evaluator, host trigger and independent effect; unverified is not pass.

## Evidence at this revision

- CLI entrypoint and durable SQLite task ledger: IMPLEMENTED as bounded prototype.
- Deterministic registered task execution and independent mechanical checks: PARTIALLY INTEGRATED.
- Generic negative-outcome -> alternative selection -> admitted child -> execution -> next independent outcome, without user intervention: **NOT IMPLEMENTED**.
- Real user's unattended long-lived deployment: **NOT VERIFIED**.
- Multi-domain outcome-based held-out generalization: **NOT VERIFIED**.
- End-to-end self-governance including authorized promotion and recurrence prevention: **NOT VERIFIED**.

## Immediate implementation order

Use the existing Host, runner, ledger, intent and independent auditors; **do not build another monitoring Agent**. Add a single reusable controller transition for independently observed unmet objectives. It must select exclusively among pre-registered bounded actions, atomically record one authorized successor, and prove it actually executes on a later tick. Test negative outcomes, revocation, concurrency, crash recovery, exhausted alternatives and held-out second domain. Keep review-only outcomes review-only. Only then evaluate real host deployment.

**Release rule:** Until all six gates have end-to-end evidence on the same system candidate, the project must not be described as a usable autonomous OS. Do not conflate GitHub Actions with a deployed controller. Draft branches must not be merged or deployed implicitly.
