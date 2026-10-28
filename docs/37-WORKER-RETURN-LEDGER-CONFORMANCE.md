# P26 — Worker returned state must agree with authoritative task ledger

## Runtime self-governance, not a passive alert

This increment continues P25 directly in existing SQLite authority and execution path of `D1traverser-debug/cognition-agent-os` Draft PR #12. It does not create an external monitor. The public task outcome returned by the worker must be the state that was actually accepted at the authoritative `finalize` boundary, not an earlier optimistic planner assumption. Model candidates, externally authored bugs and CI job labels are not substitutes for durable state.

## Independent falsification before repairing the code

Four fresh real SQLite fault injection tests were added **before the implementation**, in `tests/test_p1.py` and `tests/test_p12_repo_lab.py`:

1. A normal fixture worker observes identical bytes and returns `NO_CHANGE`, while an injected concurrent authority update increments `goal_rev` before finalization. The ledger properly commits `BLOCKED / STALE_GOAL`, but the worker previously **claimed VERIFIED**.
2. A normal fixture worker sees an injected source fetch error after the same goal rotation. Ledger commits `BLOCKED / STALE_GOAL`; worker previously **claimed UNKNOWN / SOURCE_UNAVAILABLE**.
3. An external repository repair worker is interrupted by an injected concurrent token takeover during candidate validation. Its outdated `finalize` correctly rejects the stale claim, leaving the new worker's `RUNNING` lease intact; the old worker previously **claimed UNKNOWN**, falsely implying it had finalized.
4. An external repository repair worker encounters invalid candidate data after a concurrent goal rotation. The ledger commits `BLOCKED / STALE_GOAL`; the old worker previously **claimed UNKNOWN / REPOSITORY_PROPOSAL_UNAVAILABLE**.

[Red historical run #39607834192](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39607834192): Linux 334 tests, **exactly those four new tests FAILED**. This is causally meaningful evidence, not a manufactured success. Tests used actual temporary SQLite transactions, authority revision and token changes; candidate validation is mocked so no untrusted model code or Docker is executed on the test host.

## Implemented enforcement

`ledger.py::finalize_observed()` is a centralized wrapper around existing `finalize()`, preserving its single SQLite write-lock, atomic artifact writer and authorization checks. A failed finalization returns `STALE_WORKER` only; a committed finalization reads and reports the actual durable `state`, `decision` and `error_code`. It does not synthesize VERIFIED, declare semantic acceptance, or read another worker's state as proof of its own completion.

`runner.py::run_once()` now uses this contract across its own immediate branches: invalid spec, unsupported planner modes, preflight access failure, source/model exceptions, no-change VERIFIED, artifact freeze success and artifact conflict. In particular, an honest `NO_CHANGE` planner conclusion does **not** override a mid-flight goal revision that results in `BLOCKED`.

`repo_repair.py::run_repo_candidate()` uses the same contract for invalid/no-change candidate exceptions, artifact conflicts and successful proposal freeze. In-flight model telemetry (including P24's completed-generation rejection marker) remains separate from authoritative ledger outcome. A stale worker cannot claim to have finalized another worker's lease. Existing repair-lab Docker and hidden-gold separation remain unchanged.

## Verification and limits

[Green post-fix run #39608518977](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39608518977) on pre-archive HEAD `77a040a36c4f423262bfe802d421bc8f607d8939`: Linux 334/334 including all four formerly red cases, native Windows offline regression, actual no-network Docker integration, and actual hosted Windows user-scoped Scheduled Task all COMPLETED/SUCCESS. All optional experimental 7B and cloud model jobs SKIPPED. No paid/finite-credit inference, owner-host installation, external upstream write, branch main merge, deployment or release.

**Scope limitation:** this refactor covers top-level worker branches and repository-candidate worker branches, not every specialized delegated handler (`run_goal_case`, `run_reconciliation`, `run_intent`, pipeline/pure repair). Those handlers have their own task transitions and must be evaluated with deliberate adversarial tests before claiming a universal return-ledger invariant. Atomic DB commit and subsequent readback do not prove unrelated semantic correctness or arbitrary remote exactly-once outcomes. Do not advertise complete agentic production reliability from these limited tests.

Next: check CI on final handoff commit with all model jobs SKIPPED; post a PR witness to avoid an endless commit/CI loop. Continue tracing remaining delegated paths at the common authority boundary with precise fault injection and fail-closed outcomes rather than another standalone monitoring stack.
