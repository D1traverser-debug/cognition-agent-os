# P27 — delegated handlers must not misreport the SQLite task decision

## Goal and authority

Continuation of P26 on `D1traverser-debug/cognition-agent-os` candidate Draft PR #12, not merged or deployed. No owner Windows PC software installation, main changes, upstream writes, new agent governance authority, metered/finite-credit model API, or real 7B model generation. This is a run-path behavior conformance change, not a monitoring dashboard.

P26 repaired top-level `runner.run_once` and `repo_repair.run_repo_candidate` branches that ignored durable SQLite `finalize()` outcomes, leading to false claims such as VERIFIED after the authoritative row was actually BLOCKED. P27 examines remaining delegated handlers for the same failure: `goal_case`, `record_reconciliation`, `pipeline_code_repair`, `pure_code_repair`, and `goal_intent`.

## First falsify, then enforce

Five fresh tests were first inserted into the existing temporary SQLite/filesystem regression classes (not mock outcomes):

- `tests/test_goal_loop.py`: compute a genuine already-satisfied `goal_case` plan, then increment `goal_rev` before finalization. Existing finalizer committed `BLOCKED / STALE_GOAL`, while the handler returned a misleading `decision=GOAL_ALREADY_SATISFIED` attached to BLOCKED.
- `tests/test_reconciliation.py`: compute a genuine consistent CSV pair, then rotate goal version before transaction commit. `BLOCKED` state was present but the returned payload omitted authoritative `reason=STALE_GOAL`, violating the uniform result contract.
- `tests/test_p11_pipeline_repair.py`: inject a candidate proposal failure after an independent goal rotation; prior delegated return claimed `UNKNOWN` although ledger committed `BLOCKED`.
- `tests/test_pure_repair.py`: same fact pattern for pure AST repair, also falsely `UNKNOWN`.
- `tests/test_intent_runtime.py`: invalid compiled intent after concurrent goal rotation; earlier refusal branch falsely claimed `UNKNOWN`, rather than committed `BLOCKED`. Normal successful decomposition was already protected by its own SQLite transaction and remains unchanged.

Initial genuine historical regression [Actions #39612624251](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39612624251): Linux ran **339 tests**, with these five new tests yielding **4 FAIL + 1 ERROR**, including one `KeyError: reason`; other P26 earlier tests remained PASS. This red pre-fix evidence proves actual response/ledger contradictions rather than assuming code inspection is enough. The injected authority changes use real SQLite operations. Tests do not run untrusted source or local models on the host.

## Runtime enforcement — same original authority

Each delegated handler now uses `ledger.finalize_observed()` (introduced at P26) for paths that finish via `finalize()`, and constructs any supplementary fields only **after** confirming the actually committed expected state:

- `goal_loop.py`: evidence failures, no-safe-plan, true NO_OP verification, guarded artifact freeze and conflicts. No speculative `GOAL_ALREADY_SATISFIED` decision on BLOCKED or stale owner.
- `reconciliation.py`: ambiguous join, exception, consistent record VERIFIED (including final lock-time readback), discrepancy proposal NEEDS_REVIEW; blocked result now reports authoritative `reason` instead of synthetic metadata. No semantic/business approval follows from a mechanical join verdict.
- `pipeline_repair.py`: source/proposal failures, guarded candidate freeze and conflict returns. HIDDEN remains unseen by proposer.
- `repair_search.py`: source/proposal failures, historic rejected hypothesis, signed feedback validation/rejection, guarded immutable freeze and exception paths. No externally signed acceptance authorizes source application.
- `intent_runtime.py`: early compile refusal and recursive decomposition refusal now use recorded ledger outcome. Normal successful typed child decomposition already uses one SQLite transaction with guard/lease check and does not change.

All modifications use the original SQLite authority; no second state machine, permission widening, benchmark-gold change, model/hidden test exposure, or new runtime trigger. A false success/unknown status must not hide `STALE_GOAL`, a revoked permission or an obsolete worker. The common wrapper reads actual committed `state`, `decision`, `error_code` and returns `STALE_WORKER` when the claiming owner did not commit.

Post-fix [Actions #39613260542](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39613260542): workflow **COMPLETED / SUCCESS**, Linux **339/339 PASS**, all five formerly red cases individually observed PASS in CI logs, Windows offline regression, real no-network Docker integration and hosted native Windows Scheduled Task PASS, all real-model and live public source opt-ins SKIPPED. No retest of P21-P24 historic model samples or claim of increased model repair rate.

## Limitations and next falsifiable work

These are real SQLite goal-revision fault injections but do not independently prove every possible interleaving of concurrent lease takeover/SQLite commit/readback on every delegated handler. The frozen candidate audit, independent business semantics and external maintainer acceptance remain separate, unproven production constraints. P27 did not replay a new outside-model task; P23 one-lab success and P21/P22/P24 negatives remain unchanged. The direct transactional `run_intent` happy path was reviewed but not adversarially changed here.

Next investigate the small post-commit gap in `finalize_observed()`: its state readback occurs after the SQLite finalize transaction commits, potentially permitting a concurrent task-state transition between commit and readback. Write a precise adversarial concurrent test and compare the event/row provenance before claiming complete linearizable reporting. Do not quietly expand a generic monitor or merge production main.

After storing documentation and latest `SESSION_HANDOFF.md`, verify **the new final candidate HEAD** under ordinary no-model CI, and record final CI witness as a PR comment instead of creating another self-triggered commit.
