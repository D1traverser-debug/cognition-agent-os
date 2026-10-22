# Independent outcome baseline — synthetic scope only

This experiment addresses a failure in the existing evidence story: a planner,
an artifact digest, and a checked task state are not independent evidence that
an owner's outcome occurred. The outcome test must have an expected result
fixed **before** running the worker and must not read its self-grade.

## Independent (limited) local oracle

`evaluation/owner_outcome_oracle.py` imports only the standard library and
accepts the owner's separately supplied, source-hash-pinned test contract, the
original source bytes, and the candidate bytes. It does not import agent
planner/checker classes, read task status, mutate originals or grant authority.

`tests/test_owner_outcome_holdouts.py` drives the **actual** SQLite worker and
captures its real artifact candidate as opaque bytes, then applies a separate
implementation of exact postconditions for JSON config enrichment and DV CSV
column enrichment. It mutates unchanged original fields, drops CSV records,
duplicates JSON keys, changes the source digest, and attempts to claim a
production write. These variants MUST be rejected.

A local postcondition match is deliberately called
`SYNTHETIC_POSTCONDITION_MET`, **not** product-complete or business-verified.
The result always has `business_outcome_verified=false` and
`authorizes_mutation=false`.

## Route-equivalence counterexample

A decision engine MUST NOT treat two different labels as two different
authorized ways of realizing the same owner-defined objective:

- Different objective: original PR #14 routes `ensure_structure` and
  `compare_records` are not same-goal substitute plans.
- Identical intent under two labels: original mutation PR #15 showed 409 tests
  still passed; two labels did not imply separate methods.
- Different input or acceptance postcondition: no evidence of same owner goal.
- Similar-looking methods: still require separate validation and a bounded
  equivalent effect contract, not automatic promotion.

The read-only helper `assess_route_fitness` only rejects unsupported pairs;
it never approves an auto-switch. Current capability registry has no proven
pair of distinct methods targeting the same independently defined outcome.
This is an explicit **architecture blocker**, not a prompt to insert a
`host.py` conditional or to make a duplicate method sound different.

## What this does not demonstrate

No real deployed user outcome, blind-domain generalization, unattended worker,
external-effect provider, legitimate promotion owner, or cross-capability
replanning. Synthetic test contracts written by the developer are NOT owner
sign-off. No production mutation, cloud LLM calls, or new authority introduced.

Required next positive experiment: two genuinely independent methods with
one fixed owner outcome/effect contract, each independently eligible, where
one fails a hidden result oracle and the other legitimately succeeds, then a
durable existing-ledger controller transition in the presence of revocation,
crash, attempt exhaustion and concurrency. This experiment only makes an
unsafe shortcut measurable; it does not assert that full capability exists.
