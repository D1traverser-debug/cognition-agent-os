# P10.4 — evidence-driven isolated source repair and sealed holdout rejection

## Engineering goal

The agent previously distinguished root causes for its dependency graph
and repaired false SQLite state claims, but could not propose, execute or
independently falsify even a small *source-code* change. P10.4 adds a
strictly bounded experiment through the SAME SQLite task/grant/event
authority. It does not add a second autonomous governor, copy of task
state, outside provider, paid model or trial AI credits.

This is a **repair laboratory**, not arbitrary Python execution or a
production code-editing agent. The source is a single function with
1–3 bounded integer/bool parameters and exactly one `return` expression:
either one comparison (`<`, `<=`, `>`, `>=`, `==`, `!=`) or one
arithmetic operator (`+`, `-`, `*`). Any attribute lookup, import,
call, variable assignment, decorator, comprehension, I/O, loop,
exec/eval, nested expression or non-allowlisted AST is **rejected**.
Python source is never imported or executed. A bounded AST interpreter
simulates allowed expressions, including a separate independent
`operator`-based checker.

## Immutable evidence and selection boundary

A `pure_code_repair` task provides named, local files and an
**out-of-band holdout SHA256 pin**:

```json
{
  "kind":"pure_code_repair",
  "source":"rule.py",
  "function":"condition",
  "visible":"public_cases.json",
  "holdout":"holdout_cases.json",
  "holdout_sha256":"REVIEWER_PINNED_64_HEX_SHA256"
}
```

Each test file is JSON list of `{"args":[5,5],"expected":true}` rows.
The planner observes source and public cases only, proves that the
original fails at least one public probe, tries one-operator mutations,
records all alternative visible scores, and freezes an immutable candidate
**only if exactly one** passes every public probe. It abstains on
a non-reproduced failure, ambiguous alternatives or unsupported source.

The planner does not read, receive the contents of or learn labels from the
sealed holdout. A monkeypatched test explicitly aborts if the planner
tries to read that file. This is a **software separation inside one
runtime**, not a secured enclave: an adversarial process with full access
to fixture files could still read the withheld reference. Genuine
third-party independence requires stronger source/permission isolation.

`repair_oracle.py` is a distinct code path that reparses original and
patched AST, independently rejects non-minimal modifications, runs public
cases through separate `operator` evaluators, checks actual proposal
digest and source bytes, then reads and verifies the *pinned* hidden cases.
Failing hidden cases produce `HOLDOUT_REFUTED`, mark the same task
`UNKNOWN`, and **do not write a patched code file**.

Only passing hidden candidates are staged create-once into
`workspace/repair_lab/<taskid>.py`, with exact content readback, and
produce `REPAIR_LAB_VERIFIED` plus
`REPAIR_HOLDOUT_ACCEPTED` in the same SQLite transaction.
If the process dies after writing the file but before DB commit, a new
process reconciles the **same immutable bytes** and records one acceptance,
without overwriting the source or inventing success.

This state means only **pure local AST and pinned holdout mechanically pass**;
it does not authorize writing source files in the repository or merging a PR.

## Method feedback, circuit breaker and non-repeat policy

- A failed held-out hypothesis writes a durable evidence event including
  source SHA, public suite SHA, expected held-out suite SHA and exact
  transformation name. A later identical task does **not** repeat that
  previously refuted method; if the public evidence or pinned holdout changes,
  the inference is fresh. No hidden gold answers are leaked to the proposer.
  This is small-scale evidence-based method revision, **not** general
  continuous learning or abstract algorithm discovery.
- Missing/altered hidden evidence does not fabricate a failing test.
  It yields `HOLDOUT_UNVERIFIABLE` and a durable bounded retry
  budget (three attempts, with due-time cooldown on automated scheduling).
- After an accepted lab candidate, runtime conformance rechecks original
  source, public probes, hidden digest and real staged file/acceptance receipt.
  Confirmed tamper of a previously verified patch trips a distinct
  persistent `pure_code_repair_lab` capability circuit. Subsequent
  manual and opt-in host lab writes are denied; it cannot reset itself.
- Before any repair-lab effect, the normal P10.2 complete conformance
  preflight must admit the system. The SQLite lock revalidates authorization
  and circuit state before touching files.

## Commands (an initialized local ledger is still required)

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-code-repair --source rule.py --function condition --visible public_cases.json --holdout holdout_cases.json --holdout-sha256 REVIEWER_PINNED_SHA256
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures worker-once
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures repair-audit --task-id YOUR_TASK_ID
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures repair-review --task-id YOUR_TASK_ID
```

The existing `host-tick --auto-stage-goals` performs bounded follow-up
in addition to the existing sandbox workflow. Omit the flag to leave the
independent holdout unused until explicitly reviewed.

## Empirical tests and limitations

`tests/test_pure_repair.py` proves comparison and arithmetic repairs,
abstention on ambiguous public tests, source-syntax rejection without code
execution, visible-pass/hidden-fail refutation for an **unseen upper-bound
rule**, immutable artifact tampering, granted/revoked authority,
hidden file mutation, actual subprocess kill after local effect and
crash reconciliation, host opt-in/default isolation, CLI integration,
capability-wide lab circuit and its finite missing-holdout retry, and
exact-scope memory of a previously disproven method.

CI development history:
- first P10.4 run `39441626410`: **9 test failures/errors**, revealing a
  real independent oracle AST comparison mistake and a genuinely ambiguous
  test assumption; both were corrected rather than hidden;
- second run `39441833965`: one incorrect duplicate-review test
  expectation remained, corrected to NOT_PENDING_REVIEW;
- run `39442272966`: **199/199 Python tests PASS**;
- latest functional run `39442609504`: **200/200 PASS**, including durable
  failure feedback. `live_public_source` is SKIPPED, not a fresh remote
  integration claim. After later documentation/handoff-only commits, verify
  latest head CI again.

The following remain unverified: open-world autonomous source-code patching,
unseen third-party business semantics, non-demo trusted reference origin,
actual production fixes and meaningful user outcome, installed local model,
Windows Task Scheduler in real user environment, authenticated signer, and
release acceptance. The existing Draft integration PR #12 still targets
`main` and is UNMERGED.
