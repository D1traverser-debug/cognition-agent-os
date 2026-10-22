# Opt-in bounded same-goal controller — candidate experiment

This is a FIRST EXECUTING LOCAL CONTROLLER SLICE, not a deployable autonomous
agent OS and not an independent proof of a real user's external result.

## Choice of architecture

Observed predecessor limits: the static knowledge router chooses only one
route according to a source claim; PR #14 did not replan; PR #15 showed
different route names are not distinct methods; PR #18 independently proved
that JSON and CSV can satisfy the same normalized **synthetic** record goal.

Considered:
1. Add a `host.py` if/else on failed artifacts. Rejected: no same-goal
   contract, no durable concurrent admission, easy to switch after tampering.
2. Replace the current ledger with a second framework. Rejected for this slice:
   duplicates identity, authority, and crash recovery without new evidence.
3. **Chosen for candidate trial:** opt-in, bounded transition on the ORIGINAL
   SQLite task authority; independent byte-level oracle and two pre-registered
   local candidate methods. This is a constrained demonstration, not a
   universal optimal architecture.

## Operational scope

Explicit caller registers one canonical record (all string fields) and exactly
two distinct registered local goal families `json_keys` and `csv_columns`.
Original source bytes are SHA256 pinned. The controller root is stored in
`tasks` as `CONTROL_ACTIVE` (not `PENDING`, not ordinary `DECOMPOSED`,
not a success state); attempts are persisted in `bounded_goal_attempts` in
the same database. Host executes this only with
`run_tick(...,auto_local_goal_control=True)`. It enqueues one local child
for the next tick and never recursively invokes workers.

A first method is switched ONLY if an independent source-readback proves
an explicit field-preservation conflict with the SAME pinned canonical goal,
and the child is in an eligible completed state. An `UNKNOWN` child must
also have the registered `NO_SAFE_GOAL_PLAN` reason. A narrower registered
method can return `VERIFIED/GOAL_ALREADY_SATISFIED` for column existence
while the owner-pinned record still has the wrong value; the controller
must independently reject that as owner-goal success and can consider the
pre-registered alternative. An untrustworthy artifact, missing evidence,
or unrelated `UNKNOWN` may NOT trigger a switch. If the alternate can produce a valid local candidate, the root becomes
`CONTROL_CANDIDATE_MATCHED`. **It does not mutate source bytes, grant new
permissions, attest an external outcome or declare owner acceptance.**

After revoked/stale goal/permission, unsupported task state, unreliable
artifact, changed source or invalid oracle, the controller stops or records
`CONTROL_UNVERIFIABLE`, and DOES NOT blindly try another method.

## Actual test evidence and remaining holes

The prospective tests exercise distinct tick invocations, real SQLite worker
cases, two source families, two different canonical goal IDs, concurrency,
revocation, goal revision, source drift, tampered output, already-satisfied
method and exhausted fallback. Independent oracle has no imports from
planner, ledger, controller or model. No fake model "expert" role is IV&V.

Not yet proven: real unattended deployment, business-owner signed outcomes,
arbitrary capability registration, external service writes/ACK-loss recovery,
heterogeneous provider grants, independent promotion and full failure-class
closure, fairness and actual cost, or general open-domain planning.

Governance: controller root uses a dedicated attempt table. A separate
read-only auditor now recomputes attempt lineage, admitted events, source
hashes and candidate bytes. Generic conformance scans
`CONTROL_CANDIDATE_MATCHED` and quarantines inconsistent claims and
descendants. This does not cover **all** controller ACTIVE-state tampering,
full effect-boundary enforcement, external business truth or organizational
IV&V. Do not mark this as a deployable autonomous OS.

Original goal authority always outranks retrieval and inferred plans.
