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

## Positive shared-outcome reference

A further test pins **one canonical record** before either execution:
`{ "id": "A", "owner": "ops" }`. The live worker then executes two
registered goal families: `json_keys` on a JSON source and `csv_columns`
on a CSV source. Their distinct output bytes are separately checked by the
same **format-normalizing** reference oracle, which ignores their planner
status. Both match the bounded canonical record. Independent negative inputs
that change the record ID or source bytes are rejected.

This proves that two *different existing mechanisms* can in principle
produce the **same narrow synthetic deliverable**. It does **not** mean the
knowledge-routing controller knows how to register, select or switch between
them; its current compiled intent registry is more limited. The test offers
a correct positive reference for evaluating future eligible alternatives,
not a claimed autonomous fallback.

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

An earlier test-only helper, `assess_route_fitness`, was removed: it
compared route labels but never controlled actual task admission. The bounded
local controller instead checks target compatibility and rejects duplicate
method families at real SQLite registration; its read-only postcondition
audit remains separate. Only JSON/CSV synthetic record equivalence has been
shown—not general business-goal equivalence or unrestricted route switching.

## What this does not demonstrate

No real deployed user outcome, blind-domain generalization, unattended worker,
external-effect provider, legitimate promotion owner, or cross-capability
replanning. Synthetic test contracts written by the developer are NOT owner
sign-off. No production mutation, cloud LLM calls, or new authority introduced.

Later bounded-controller experiments tested one synthetic shared record goal
across the two local methods and existing-ledger restart/concurrency rules.
That remains outside **real-user outcome confirmation** and does not establish
novel-domain selection, general tool authority or third-party acceptance.
