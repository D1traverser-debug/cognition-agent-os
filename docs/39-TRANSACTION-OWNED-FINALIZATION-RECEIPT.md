# P28 — Transaction-owned finalization receipt prevents cross-worker attribution

## Result and project authority

The existing `cognition-agent-os` candidate branch is an **experimental** Draft PR #12, not merged into main, registered as a production UAOS domain, deployed to the owner's Windows PC, or authorized to write to other repositories. No paid or finite-credit model API was used. P28 improves the original SQLite ledger/worker execution path, rather than adding a passive observer or independent authority.

### Reproduced ownership/provenance race

P26 and P27 made `finalize_observed()` consult committed SQLite state instead of optimistic planner predictions. But the implementation called `finalize()` (which commits and releases the single SQLite write lock) **then separately SELECTed** the task's *latest* row. A distinct authorized reviewer can legitimately advance a freshly committed proposal before that SELECT; the worker then reports the reviewer's result as its own action.

The preregistered test `tests/test_pure_repair.py::test_review_between_finalize_commit_and_result_read_cannot_be_misattributed` uses a real temporary SQLite database, real immutable pure-code repair proposal/artifact, and the original independent sealed `review_patch()` on a separate SQLite connection. An injected deterministic wrapper around the original `ledger.finalize()` performs exactly this interleaving:

1. The original worker commits `NEEDS_REVIEW` / `BOUNDED_CODE_PATCH_PROPOSAL`, and the transaction releases the write lock.
2. A separate authorized holdout reviewer then evaluates the actual frozen patch and commits `REPAIR_LAB_VERIFIED` / `ISOLATED_OPERATOR_PATCH_HOLDOUT_PASS`.
3. The original worker resumes its *old* `finalize_observed()` and queries the latest row, falsely claiming `REPAIR_LAB_VERIFIED` as if the original proposal worker had verified withheld semantics. The real durable SQLite row is `REPAIR_LAB_VERIFIED`, and the reviewer legitimately owns that subsequent transition; only the original worker's **attribution** was false.

The unmodified implementation was measured RED in [Actions #39616272265](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39616272265): Linux ran **340 tests, 1 FAIL** on this exact injected interleaving (`'REPAIR_LAB_VERIFIED' != 'NEEDS_REVIEW'`). The output exposed the wrong worker response `{'status':'REPAIR_LAB_VERIFIED','decision':'ISOLATED_OPERATOR_PATCH_HOLDOUT_PASS'}`. Windows offline regression also failed this adversarial test; normal Docker and native Windows Scheduler remained green. No direct arbitrary SQL mutation fabricated the reviewer promotion.

### Implemented prevention

The original `ledger.finalize(...)->bool` retains its public boolean return and existing `BEGIN IMMEDIATE` lock, CAS-like lease/token ownership guard, grant/goal check, artifact effect, durable FINALIZED event and optional recurring follow-on task. An **optional internal** `_committed_receipt:dict` argument captures only `{status,decision,reason}` computed by THIS locked finalization; it is populated **after a successful DB commit**. A failed ownership check or failed transaction does not issue a success receipt.

`finalize_observed()` now gives `finalize()` a fresh receipt object, returns `STALE_WORKER` if the original ownership/finalization check failed, and composes the worker-visible status/decision/error exclusively from this transaction's committed receipt. It no longer SELECTs a latest row after COMMIT, so a subsequent, valid reviewer transition cannot contaminate this worker's stated outcome. Unexpected success without a receipt is an explicit fail-closed invariant error, not invented status. Authorization or artifact semantics, default planner behavior, sealed holdout and model outputs were not changed.

### Verified evidence and limits

[Actions #39616816505](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39616816505) on pre-archive HEAD `61097c5c5d9e0a6917dda80113644e7f75baa5fa` completed **SUCCESS**: Linux **340/340** (the exact formerly red interleaving now PASS), Windows offline standard-library regression, genuine no-network Docker integration, hosted Windows native user-scoped Scheduled Task with real ticks; all experimental real 7B/local-model and live-source jobs SKIPPED. Historical RED remains preserved to establish causality.

The test proves a particular *legitimate* post-commit reviewer promotion race and that the original worker doesn't misattribute it; it does **not** prove all possible concurrent schedules, eliminate race windows in *other* APIs such as `claim_one()`, or establish true semantic correctness of independent model repairs. The original reviewer is still free to promote a task; the fix is about provenance of the prior worker's response. Normal CI passing does not authorize production merge/deployment, original-code replacement or upstream modification.

Next: verify the final branch HEAD after documentation/handoff with all model jobs SKIPPED, and record the final HEAD CI in the existing Draft PR comment to avoid another source/CI loop. A subsequent P29 investigation may use similar red-first evidence against `claim_one()`'s own post-commit row read, or another material claim/authority discrepancy; do not assert it is broken before falsification.
