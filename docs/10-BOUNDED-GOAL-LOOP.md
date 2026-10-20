# P5 — bounded goal-to-action loop, not general autonomy

## Governing purpose

This stage moves from a fixed GitHub watcher/benchmark toward a **goal-driven**
workflow. A goal is explicitly registered once in the existing SQLite
task/grant ledger. The worker itself determines what evidence is needed, checks
competing *candidate action* hypotheses, creates a non-destructive candidate,
tests it with independent mechanical constraints, then records the durable
outcome. A host that has been physically installed can process these goals
without new chat messages; CI is **not** evidence that it was installed.

No additional AI tokens, metered APIs or limited free credits are needed.

## Present bounded families, not arbitrary reasoning

1. `json_keys`: a goal specifies required top-level scalar values in a local
   JSON object. If missing, the worker may add the **explicitly supplied**
   value. It must retain every existing key and value. Conflicting existing
   values are **UNKNOWN / NO_SAFE_GOAL_PLAN** — no silent overwrite.
2. `csv_columns`: a goal specifies required CSV column names with **explicit**
   default strings for new columns. The worker may add those columns, preserving
   existing headers, every row and every existing cell.

Only approved local fixture sources are supported; no shell command, remote
write, general website navigation or OS arbitrary-path mutation is exposed.
Task intake is bounded (16 goal fields, 64 KiB source and 200 CSV rows).
`source_spec` uses the same `tasks` table, versioned goal/grant revisions,
lease, fencing and immutable artifact writer. There is **no shadow goal DB**.

The worker evaluates at least two action candidates: `NO_OP` versus the
allowed additive candidate. A separate source-preservation checker rejects
unsafe candidates rather than trusting a planner saying PASS. The recorded
three diagnostic hypotheses are **limited evidence interpretations**;
the external reason why data differs is unresolved unless independently
observed. There is no claim of general causal inference.

## Intake example

Create local `goal.json` (intended path is in an isolated fixture directory):

```json
{
  "kind": "goal_case",
  "goal_type": "json_keys",
  "input": "config.json",
  "desired": {"owner": "ops", "retries": 3}
}
```

Then use existing host entrypoint:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-goal --spec .\goal.json
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures host-tick
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures status
```

An already-satisfied source yields `VERIFIED / GOAL_ALREADY_SATISFIED`
meaning **only these bounded explicit constraints** are met. A candidate that
would change data yields `NEEDS_REVIEW`, not VERIFIED and not applied to the
source. An ambiguous or corrupted source is `UNKNOWN`; revoked writes or
outdated goals are `BLOCKED`. The output artifact stores the original source
hash, selected candidate and alternative checks; it is not an independent
professional/business proof.

## Acceptance and limitations

Test evidence should include the JSON and CSV paths, no-op, conflicting target
vs actual input, missing/corrupt source, goal revision and grant revocation,
input changing after the first observation, subprocess crash between file write
and DB commit, artifact mismatch on retry, two independent workers and actual
host tick invocation. These check **mechanical goal handling and safety**, not
LLM inference quality or unknown-task transfer.

This does not yet (a) autonomously discover unrestricted user goals or new
causal issues, (b) choose among open-ended research methods, (c) verify external
business results, (d) learn general methods or safely merge fixes, or (e)
prove Windows background execution. Real held-out goals and external semantic
judges are still needed. Expansion of the goal contract must preserve the same
authorization + readback constraints rather than invoking a shell or overwriting
sources.
