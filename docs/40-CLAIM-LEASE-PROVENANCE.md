# P29 — Claimed lease token must belong to the claiming worker

## Scope and actual failure

Independent experimental repository `D1traverser-debug/cognition-agent-os`, Draft PR #12, branch `feat/p10-runtime-conformance-20261020` only. No merge, release, owner-Windows deployment, upstream source modification, paid or finite-credit model API. P28 fixed cross-worker finalization result attribution; P29 examined whether the earlier `claim_one()` boundary had the same post-COMMIT race.

Before the change `ledger.claim_one()` held a SQLite `BEGIN IMMEDIATE` write lock to select a due task, update its lease token, and insert a `CLAIMED` receipt. **But it committed that lock before SELECTing the row to return**. A lease may expire and a second authorized worker may acquire the same task before this SELECT. The first worker can then receive the second worker's token/version as though the first issued them. This corrupts lease provenance and could cause the first worker to impersonate the second worker at subsequent guarded effects. It is distinct from the legitimate fact that a first worker's token may expire between issuance and use.

## Independent red-first falsification

`tests/test_p1.py::test_claim_owner_snapshot_cannot_be_replaced_after_commit` was committed **before the product fix**. It creates a genuine temporary SQLite ledger, task, and two separate SQLite connections. The first worker calls `claim_one()` with a zero-duration lease. A wrapper around only that connection's `commit()` method lets its actual commit finish, then immediately calls the real second worker's `claim_one()` with a later time and 90-second lease. The second worker legitimately takes ownership on its own separate connection. No task-state overwrite, invented token, fake SQLite transaction or monkeypatched `claim_one()` return is used; the test reads the two real `CLAIMED` ledger events as independent provenance.

Expected invariants: first worker returns **first** `CLAIMED.new_token` and state_version=1, second returns **second** token and state_version=2, ledger's latest row correctly belongs to second. A stale first token cannot `finalize()` the second worker's task, while the durable row stays `RUNNING` with the second token.

[Red original-source GitHub Actions #39620032712](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39620032712): Linux 341 tests, exactly the new P29 adversarial test FAIL. The first worker returned the second worker's token rather than the first `CLAIMED.new_token` (`AssertionError` two unequal token hashes in the test log). This is a **genuinely reproduced cross-worker attribution failure**, not a conjecture from code review. Other historic original-source findings remain unchanged.

## Minimal original-authority fix

Commit `de6f0f04175b6cce8401b7abb6388f32ecaed950` in `src/cognition_agent_os/ledger.py::claim_one()` moves the snapshot SELECT **inside the existing IMMEDIATE transaction**, after updating the lease and event and before `db.commit()`, and returns those snapshot bytes after commit. The original function API, committed database state, single write lock, guard/lease/token validity and recovery semantics remain unchanged. The return value belongs to the claiming worker, even when its lease has legitimately expired by the time the caller resumes. The existing `finalize` ownership guard continues to reject stale tokens; claiming a snapshot never authorizes arbitrary subsequent effects.

The regression was strengthened in `9317a90dd8a379f5396f95ec2211ac4b0dc6b55b` to explicitly try `finalize()` with the first claim after takeover; the call returns False, without overwriting the new second worker's `RUNNING` row.

## Verified acceptance and limits

First fixed-head Linux suite at [Actions #39620240459](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39620240459) passed, but other jobs were superseded by the strengthened negative test and must NOT be counted as an all-platform green run. The **actual full** pre-archive [Actions #39620403889](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39620403889) on HEAD `9317a90dd8a379f5396f95ec2211ac4b0dc6b55b` COMPLETED/SUCCESS: Linux **341/341** (P29 test now PASS), Windows offline regression PASS, real no-network Docker integration PASS, hosted Windows native user-scoped Scheduled Task two-tick witness PASS. Optional actual Qwen2.5-Coder 7B and live-source/paid experimental workflows SKIPPED.

This proves one actual expired-lease double-claim interleaving and the normal stale token guard, not all concurrency schedules, clock-drift behavior, distributed multi-node leasing or real model repair quality. Ownership after the first lease expires is still legitimately transferrable; provenance is fixed, not the semantics of lease timeout. No secondary authority or monitor introduced.

Next: check final ordinary CI after this report and `SESSION_HANDOFF.md` checkpoint; record a final-head witness on existing Draft PR #12 without another self-triggering source commit. Do not merge, deploy, or retune historical P21/P22/P23/P24 tasks without independent motivation.
