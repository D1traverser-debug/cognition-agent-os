# P6 — isolated enactment, independent readback, bounded replan

## Actual workflow

A declared P5 JSON or CSV goal enters the **existing** SQLite ledger.
The worker obtains source facts, evaluates a no-op and a constrained additive
candidate, and records an immutable `NEEDS_REVIEW` proposal.

P6 adds two deliberately separated operations:

- `goal-stage-sandbox --task-id ID` independently checks that proposal,
  **writes only** `<workspace>/sandbox/<ID>.candidate`, reads its bytes
  back, verifies SHA-256 and original-source stability, and records a bounded
  `SANDBOX_VERIFIED` disposition with a source/effect receipt in the existing
  SQLite event ledger. This is *not* a business or production VERIFIED state.
- `host-tick --auto-stage-goals` is an **explicit opt-in** for the
  same bounded sandbox step after each local tick's proposal production.
  With no flag the prior P5 `NEEDS_REVIEW` behavior is unchanged.
  Without a physically installed OS scheduler it still does not self-awaken.

An existing sandbox candidate with exactly matching immutable bytes can be
read back and reconciled after a process killed between file creation and
SQLite commit. A different existing file is never overwritten, and
`EFFECT_UNKNOWN` is preserved rather than fabricating success.

## Finite autonomous continuation when source changes

When independent review finds that the original input changed after proposal
creation, P6 rechecks the same goal/grant revisions under a SQLite write lock,
marks that parent `NEEDS_REPLAN`, and **atomically** creates one child task in
the original ledger. The next worker tick re-reads current source and develops
a new candidate. Only two such parent-to-child replan transitions are allowed;
repeated drift leads to `UNKNOWN / REPLAN_BUDGET_EXHAUSTED`. No unchecked
external writes, recursive API calls or endless repair loops.

A candidate that fails mechanical review for other reasons is rejected and
not staged. These cases need further causal diagnosis; the prototype does
not claim independent semantically justified replan strategies.

## Example usage

```powershell
# Run after P5 goal seeding. The CLI never writes the fixture source.
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures host-tick --auto-stage-goals
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures status
```

Task-level manual staging is:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures goal-stage-sandbox --task-id YOUR_32_HEX_TASK_ID
```

The stage operation is *local sandbox write*, not permission to replace
`fixtures/config.json`, modify source repositories, deploy, merge, or publish.

## Acceptance evidence and limitations

Tests exercise two families, actual isolated file readback, source preservation,
mismatched pre-existing file, symlink refusal, two independently running staging
processes, real child-process kill before DB commit and reconciliation,
in-flight source drift, stale goal and revoked grants, optional host behavior,
durable replanning, and a strict two-retry budget.

`SANDBOX_VERIFIED` means these narrow local constraints were observed on the
sandbox artifact. A test fixture is **not** independent domain semantics,
unknown-problem discovery, unrestricted goal decomposition, causal explanation,
external user outcome, or deployed Windows background autonomy. Outside
sandbox effects require separate explicit approval and real provider readback.
No model credits or remote LLM APIs are used.

## Persistent effect-failure budget

An already-existing conflicting sandbox file or repeated inability to write
or read back a sandbox effect remains `EFFECT_UNKNOWN` initially. After
**three recorded** `SANDBOX_EFFECT_UNCERTAIN` events for the same task,
P6 stops automatic attempts by moving the task to
`UNKNOWN / SANDBOX_EFFECT_RETRY_EXHAUSTED`, preserving the existing
sandbox file byte-for-byte. A separately authorized diagnosis may later
resolve the situation; no automatic overwrite, retry-limit reset or
false `SANDBOX_VERIFIED` is allowed.

This cap is distinct from the **two source-drift replans**. The regression
test `test_repeated_sandbox_failure_has_finite_retry_budget` proves the
same task cannot spin indefinitely through the host after three such failures.

## Optional Windows scheduled host registration

P2 registration script now accepts `-AutoStageGoals` as an **explicit
owner opt-in**. Omit the switch to keep only read/proposal operation.
Run only on a Windows host with a deliberately pre-seeded SQLite DB and
the project checked out locally:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_windows_host.ps1 -AutoStageGoals
```

Registration is one-time and refuses overwriting an existing scheduled task.
The script's code was updated in the candidate branch; **no successful
Task Scheduler installation or independent background tick on the user's
Windows PC was observed**. Before relying on autonomy, inspect Windows
Task Scheduler history, process exit codes and SQLite host_ticks/events
in the actual installed environment.
