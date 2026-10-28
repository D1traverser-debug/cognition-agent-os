# P7 — durable diagnosis, fair review admission and evidence-based recovery

## User outcome / causal engineering risk

P6 could generate an infinite **partial-handling** loop: an invalid old
`NEEDS_REVIEW` item remained in the first N review slots forever, preventing
legitimate newer tasks from being staged. Repeated sandbox write failures also
had a budget but lacked an automatic admission cooldown. Separately, a
`GOAL_EVIDENCE_UNAVAILABLE` task remained `UNKNOWN` after its original input
was later supplied; the host could not independently continue it.

P7 modifies the **existing tasks/events/authority SQLite owner**. It does not
make another scheduler, diagnosis database or source of truth.

## Diagnosis is a disposition and bounded next action, not just an alert

An independently invalid goal candidate now yields a durable
`DIAGNOSIS_RECORDED` event after task/grant/source recheck under
`BEGIN IMMEDIATE`, with a structured **observed evidence class**,
two competing unproven causal explanations and the safe next-action class.

- Revoked/stale authority → `BLOCKED`,
  `STOP_UNTIL_EXPLICIT_REAUTHORIZATION`.
- Tampered/mismatched candidate or inconsistent constraints → `UNKNOWN`,
  `ISOLATE_REJECTED_CANDIDATE`.
- Missing/unreliable/unreadable audit evidence → `UNKNOWN`,
  `REQUIRE_NEW_VALID_EVIDENCE`.

Invalid reviews leave the runnable `NEEDS_REVIEW` pool, allowing other
tasks to proceed. A stale initial diagnosis is checked again in a locked
transaction; a proposal that became valid is **not** closed based on a
now-obsolete observation. No cause is represented as proven merely because a
classification matched.

## Fairness and anti-loop bound

Automatic review admission reads only valid JSON specs where
`kind == goal_case`, `state == NEEDS_REVIEW` and `due_at <= now`.
It orders by due time and stable tie-breakers, limiting each batch. A failing
sandbox write/readback receives a durable retry timestamp (`+60s`,
`+120s`); repeated failures still exhaust the existing 3-attempt budget.
Explicit manual stage commands can attempt the same task, but cannot defeat
the hard 3-attempt cap.

A proposed audit failure transitions out of the review pool (UNKNOWN/BLOCKED),
rather than being silently selected again every tick. Such a failure may not
be auto-repaired without trusted new evidence.

## Automatic source-evidence recovery

When a `goal_case` entered `UNKNOWN / GOAL_EVIDENCE_UNAVAILABLE` because a
local fixture was missing, malformed or unreadable, the opted-in
`host-tick --auto-stage-goals` also makes a bounded independent attempt to
reacquire that exact authorized source:

1. Check task state, revision and grant in the **same** task ledger.
2. Re-read bounded source twice and recompute a *new* candidate with existing
   goal constraints; do not copy a stale plan, bypass an expired grant or
   pretend source data exists.
3. If source remains inaccessible, set a durable 900-second next check and
   preserve UNKNOWN, without fabricating a task or recording the same event
   every tick.
4. If current source conflicts with desired values, classify
   `NO_SAFE_GOAL_PLAN` and stop (no destructive overwrite).
5. If source now supports an allowed candidate or safe no-op, atomically
   transition parent to `NEEDS_REPLAN`, create **one** child in the same
   `tasks` table, and preserve observed source SHA in an event.
6. Uphold the existing **2-replan lineage cap**; excess is
   `REPLAN_BUDGET_EXHAUSTED`, not an infinite loop.

New children are processed by the *next host tick*, not by recursive execution
in the same call.

## Realistic limitations

The diagnosis evaluates predeclared JSON/CSV goal families, mechanical
source and file evidence, and coarse alternative causes. It does **not**
discover unknown real-world causal models, acquire independent semantic
ground truth or prove the user-facing goal. The source may change after the
double-read: downstream P5/P6 precommit checks remain required. P7 writes
only candidate sandbox files and local SQLite state, not provider accounts
or production targets.

Nothing here establishes that Windows Task Scheduler ran unattended on the
owner's computer; no paid or credit-metered model is used. A verified
`SANDBOX_VERIFIED` is not an independently accepted business outcome.

## Acceptance cases

`tests/test_diagnostics.py` covers nine invalid oldest tasks without
starving a later legitimate one, durable one-time diagnosis, revoked authority,
an unknown goal whose source later becomes available leading to a child task
and staged result, unavailable-source cooldown, conflicting desired values,
recovery grant change, replan exhaustion, retry cooldown fairness, malformed
non-goal spec isolation, stale precheck races and restart idempotence.
Retain all P0–P6 regression tests.
