# P10.6 — genuine Windows Task Scheduler invocation and authority readback

## Goal, scope and non-claims

P10.5 established Python compatibility on an actual Windows hosted runner.
It did NOT prove that Windows Task Scheduler could wake the process without
someone invoking its CLI. P10.6 now creates a **real, user-interactive
Windows Scheduled Task** in an ephemeral public-repository GitHub Windows
runner, lets **two different one-minute triggers** invoke the original
`scripts/host_tick.py` entrypoint as separate OS processes, then opens the
same SQLite ledger independently to verify the observed effects.

This is a verified native scheduler / SQLite persistence integration.
It is not a deployment to the owner's actual Windows 11 computer, a
demonstration of post-reboot pre-login execution, or an external business
result. No paid AI tokens, finite trial model credits, privilege elevation
or external source mutation are involved.

## Existing registration path, hardened in place

The pre-existing `scripts/register_windows_host.ps1` was extended rather
than replacing it with a parallel system. Registration remains a **manual
explicit opt-in**, no automatic installation. New parameters are optional:
`-PythonPath`, `-DbPath`, `-WorkspacePath`, `-FixturesPath`,
`-FirstRunAt`, `-DurationDays`. Defaults continue to use local
`runtime/state.sqlite`, `runtime/workspace`, `fixtures`,
`python.exe`, a five-minute interval, and a future start.

The principal is explicitly the **current interactive Windows user** with
`-RunLevel Limited`; `-AutoStageGoals` remains FALSE unless explicitly
supplied. Concurrent starts use `MultipleInstances IgnoreNew`; execution
time is bounded. Task names must match a safe character pattern. Existing
registered tasks are NEVER replaced implicitly. Only already-existing
ledger and Python/entrypoint paths can be registered.

**New safety precondition:** existence of a `.sqlite` file does not
establish an initialized task authority. Before registration,
`scripts/verify_host_registration.py` opens the original ledger read-only
using the same `host._admit_existing_ledger` contract. Missing, corrupt or
unseeded SQLite files reject registration; the validator does not call
`initialize()` or issue write grants. A legitimately revoked write grant
is not silently restored merely to make scheduling work.

Registration uses an explicit one-shot start and bounded repetition,
defaulting to ten years (3650 days, preserving long-running intent) rather
than silently granting forever. Repeat scheduling only works while the
current user is logged on. A pre-login / service-account mechanism requires
a distinct authorized design and OS permission evaluation.

### Example: deliberate local registration (not executed on user's PC)

From the candidate repository root in PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .\fixtures | Out-Null
Set-Content -LiteralPath .\fixtures\old.txt -Value "old"
Set-Content -LiteralPath .\fixtures\new.txt -Value "new"

# Explicitly create the one local authority and task before registering.
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-fixture --old old.txt --new new.txt

# Registration only: this command does not run an AI model or grant access.
.\scripts\register_windows_host.ps1 -IntervalMinutes 5

Get-ScheduledTaskInfo -TaskName CognitionAgentOS-Local
# Revocable; owner must choose when to remove:
Disable-ScheduledTask -TaskName CognitionAgentOS-Local
Unregister-ScheduledTask -TaskName CognitionAgentOS-Local -Confirm:$false
```

The example is **not an instruction to deploy production capabilities**.
PR #12 is still Draft/unmerged and owner-host acceptance is pending.

## Real hosted Windows acceptance design

`scripts/verify_windows_scheduler_probe.py` seeds a new isolated SQLite
DB with two distinct immutable source-evidence tasks: one already due,
one due after ~70 seconds. The probe refuses existing DB replacement.
`scripts/verify_windows_scheduler.ps1` registers a **temporary**
one-minute recurring Scheduled Task with a first run roughly 40 seconds
later using the exact normal registration script and host CLI.

Only after the real OS triggers have fired twice does the checker accept:
- `host_ticks.ticks >= 2` and `processed_total = 2` from the database;
- exactly two original task records completed as `NEEDS_REVIEW`;
- stored immutable artifact hashes independently match actual files;
- input bytes are unchanged;
- ledger grant and goal revisions are unchanged;
- `Get-ScheduledTaskInfo.LastTaskResult = 0`.

A mere task-registration receipt, wall-clock sleep, test-side direct call
to `run_tick`, or Task Scheduler's exit status without SQLite evidence
does not count as a PASS. A `finally` block unregisters the temporary
Windows task and verifies it is gone.

The smoke also tries registering an **empty pre-existing .sqlite file**.
That must fail, and no bad scheduled task may remain.

### Actual observed CI runs

- Initial real integration `39447708137`: FAILED because the PowerShell
  `New-ScheduledTaskPrincipal -RunLevel` enum does not accept
  `LeastPrivilege` (valid enum is `Limited` or `Highest`). Registration
  failed before any native execution claim; parameter was corrected.
- Follow-up `39447960517`: SUCCESS. Actual log reported
  `HOSTED_WINDOWS_SCHEDULER_WITNESSED`, **ticks 2,
  processed_total 2, completed_tasks 2**, unchanged original sources,
  and matched artifact SHA readbacks.
- Strengthened safety integration `39448896882`: SUCCESS; log explicitly
  confirms `UNSEEDED_AUTHORITY_REGISTRATION: BLOCKED`, actual
  scheduler evidence `ticks=2`, `processed_total=2`,
  `completed_tasks=2`, and
  `TEMPORARY_SCHEDULER_TASK_REMOVED`. Linux and native Windows
  offline regression jobs both passed. External live GitHub-source
  smoke remained SKIPPED.

## Remaining real-world acceptance

The user's PC has never been touched. Even a successful hosted Windows
scheduled task does not prove recovery after an actual reboot, pre-login
start, local network constraints, persisted per-user filesystem ACL
behavior, multi-day reliability or user-level business value.

Those still need independent live evidence from the owner's Windows 11
host, with explicit authorization and controlled deployment, before any
`main` release or `PRODUCTION_READY` claim. The runtime is still a
bounded, deterministic capability system, not a general autonomous mind.
