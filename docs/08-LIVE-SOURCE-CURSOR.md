# P3 — live public branch observations with transactional immutable-task cursor

This is an incremental **source-ingestion** capability, **not** a self-directed
cognition or business-outcome verifier. Branch HEAD is mutable; the evidence jobs
are immutable pairs of 40-digit commit SHA values.

## Workflow

1. An explicit owner first seeds a public source watch (repo/path/branch) into the
   existing local SQLite authority. Rate floor: 900s, maximum four watchers
   (unauthenticated GitHub public API rate limits apply).
2. The existing OS-hosted `host-tick` observes due watches before draining tasks.
   Each read resolves the current public branch to a pinned full commit SHA,
   downloads one path from that SHA, and independently verifies Git Blob SHA.
3. The *first* observation saves its commit/blob as BASELINED without a fake task.
   If a later commit has identical content, advance the cursor with NO_CONTENT_CHANGE.
   If content differs, atomically enqueue one immutable `github` evidence task and
   advance the watch cursor in the **same SQLite transaction**.
4. Independent workers use the existing P1 `get_pair` immutable-source
   verification. Diff is a `NEEDS_REVIEW` proposal, never an unverified semantic PASS.
5. The optimistic `cursor_epoch` prevents two simultaneous polls from enqueuing
   duplicate tasks or regressing the cursor. Stale observations are discarded.
   Errors leave the previous evidence cursor intact. Authorization (goal/grant
   revision and explicit write permission) is rechecked after network retrieval
   under the transaction lock.

## On a locally checked out project

```powershell
# First run, with Python 3.10+; project uses standard library only.
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace seed-watch-github --repo D1traverser-debug/cognition-agent-os --branch main --path README.md --interval-seconds 1800

# Explicit one tick: first invocation establishes BASELINED (no invented change).
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace host-tick

# Inspect trusted watch source versions, failures, and follow-up evidence tasks.
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace status
```

Only an actually installed Windows Task Scheduler registration (previous P2
`scripts/register_windows_host.ps1`) wakes the host when the user sends
no messages. CI cannot establish unattended operation on the user's computer.
No API key or cloud model is needed. Public GitHub REST uses rate-limited free
requests, not AI Token credits. A burst of new changes adds the worker's
additional pinned-content reads; on 429 or network failure the system reports
source unavailable and keeps a retryable checkpoint rather than bypassing quotas.

## Fault and outcome evidence

Tested scenarios in `tests/test_watch.py`: no fake initial change, content
identity over moving commits, real content difference issuing one pinned job,
same-head integrity conflict, source failure/retry, write-grant revocation before
and during network retrieval, stale goal version, atomic rollback between task
enqueue and checkpoint, concurrent same-watch observers, input/budget bounds,
metadata identity falsification, and overdue-poll behavior.

`scripts/verify_live_watch.py` is an actual public GitHub REST integration
smoke for HEAD-to-baseline, followed by the existing immutable source test.
It does **not** simulate a genuine future commit from outside of the test runner.

## Known limitations and next acceptance work

- This observes latest snapshots of **one existing file** on a single-segment
  branch. Rapid intermediate commits, renames, deletions, changed repository
  permissions, force pushes or inaccessible historical commits can require
  reconciliation; no completeness guarantee over every historical commit.
- There is no proof that "spec changed" implies "affected architecture" or
  that an independently accepted user goal has been achieved. Model proposals
  remain advice; independent semantic/holdout evaluation remains the next gate.
- No Windows installation, always-on autonomy, remote writes, merged
  production release or expensive cloud model is claimed.
- Cursor progress records successful durable task issuance, not successful
  worker execution. Tasks may be UNKNOWN, BLOCKED or NEEDS_REVIEW; the task
  ledger retains their distinct states without falsely replaying observations.
- The max-four watcher bound reduces but does not guarantee public API
  quota compliance. Other applications on the same IP share quotas.
