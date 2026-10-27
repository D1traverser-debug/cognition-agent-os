# P30 — Full task-lifecycle evidence audit and stale Docker gold admission fix

## Objective / authority

Owner-approved direction: advance the **existing** experimental `D1traverser-debug/cognition-agent-os` Draft PR #12 toward a genuinely useful and self-governing local coding system, without mistaking green unit tests for model autonomy. Candidate branch `feat/p10-runtime-conformance-20261020`; no upstream source edits, owner Windows installation, production deployment, main merge or paid/finite-credit inference. This is NOT an officially registered UAOS child.

P25—P29 corrected real claim/evidence, return/state, commit provenance and lease attribution errors. P30 steps back to trace evidence from task admission through candidate generation, independent review and acceptance. This audit deliberately updates an existing *enforcing* admission path instead of inventing another monitoring subsystem.

## Lifecycle evidence inventory — distinguish observed, bounded and missing claims

| Stage | Mechanism and actual evidence | Currently justified claim | Limit / missing evidence |
| --- | --- | --- | --- |
| Task authority and scheduling | Actual SQLite `create_task`, `claim_one`, original grants/revisions, expired-lease takeover red/green P29 | Single DB owner/lease fencing in tested schedules | No distributed consensus or arbitrary-host privilege proof |
| Inputs and original defect | P21 more-itertools, P22 CPython, P23 NuPlan, P24 finance pinned external reporter code plus original reproductions; immutable SHA/manifest checks | Pinned original bytes and case-specific baseline reproduction | Public issues/suggested answers can contaminate model training; extracted adapters not full upstream installs |
| Proposal generation | One real locally installed Qwen2.5-Coder 7B, loopback Ollama (bounded disposable GitHub runners), with whole-file and compact candidate output | Genuine 7B generated two valid candidates for the isolated P23 NuPlan method | P21 had no repaired candidate after bounded tries; P22 no candidate in time; P24 compact no-change rejected; NO cross-repo autonomous success-rate proof |
| Artifact identity | Exact source and proposal hashing, create-once immutable stage, tested artifact crash/retry and P26—P29 ledger attribution | Proposal bytes and observed worker return can be causally connected in covered paths | Does not establish semantic correct patch |
| Independent public/hidden review | Separate actual no-network, non-root Docker reviewer and sealed expected values, 2-stage receipt rules; P23 PUBLIC4/HIDDEN8 both formats pass | Independent heldout acceptance in isolated supplied harness, not production | Repo-specific dependencies, maintainer signoff, integration of entire upstream project absent |
| **Gold freshness at acceptance** | **P30** post-Docker and post-stage immutable gold reattestation inside review commit path | Success cannot be promoted based on *persistently changed* hidden gold in the injected intervals | File system bytes cannot be transactionally locked by SQLite; adversarial ultra-short swaps and malicious host excluded |
| After-the-fact governance | P25 conformance audit re-reads sealed gold on already verified repo repair; critical drift revokes verified state and trips circuit | Delayed corruption can cause persistent containment at tested stages | Doesn't replace correct *initial* acceptance (why P30 was necessary) |
| Host lifecycle | Real `host.run_tick` claim/freeze/review/conformance fault injection; GitHub-hosted Windows native Task Scheduler two-tick CI | Actual bounded host invocation and *separate* Windows scheduling witness | Not evidence of long-running unattended owner-host deployment or successful business action |
| Deployment/outside feedback | No production mutation, no upstream maintainer acceptance, no linked owner-host install | **NOT AUTHORIZED / NOT PROVEN** | Separate informed approval and independent full-project acceptance required |

The important aggregate conclusion is **governance reliability improving, broad task competence still unproven**. Individual correct unit tests or a successful CI workflow are never interchangeable with the model actually fixing an unfamiliar full project.

## P30 actual contradiction, red-first

The repo-container repair path ran the original baseline, PUBLIC tests and sealed HIDDEN test via Docker **before** opening its `BEGIN IMMEDIATE` SQLite acceptance transaction. It then reaudited current source/proposal bytes but not the *current hidden fixture bytes*. After staging a changed file, it again reaudited source/proposal and staged file bytes but **still not gold**. Therefore independent Docker evaluation of an earlier test version could be minted into a fresh `REPAIR_LAB_VERIFIED` receipt despite changed expected values.

The P25 after-the-fact conformance guard could later detect this, but had not prevented the original unsound successful acceptance. P30 therefore protects the acceptance decision at its source.

Two new red-first tests in `tests/test_p12_repo_lab.py`:

1. **After Docker, before SQLite approval:** the fake Docker execution boundary reports the original case results and then swaps `hidden.json` before the reviewer transaction. Expected: `HOLDOUT_PIN_MISMATCH`, durable state remains `NEEDS_REVIEW`, no staged directory or accepted receipt.
2. **After staging, before SQLite receipt:** the mock wrapper uses the **real** `_stage` to write its candidate and immediately swaps `hidden.json`. Expected: `POST_EFFECT_REJECTED`, durable `UNKNOWN`, one rejection receipt, zero approval receipts. The already-written file is an **unapproved orphan**, never trusted or applied upstream.

Actual [red first GitHub Actions #39623014362](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39623014362), commit `c8474547afd4d78b520fde2b787121f7b1a0f0a6`: Linux **343 tests, exactly 2 FAIL**. Both had incorrectly returned `REPAIR_LAB_VERIFIED` in the original implementation. These are real temporary SQLite/fixture/storage state with **mocked Docker executable** as a controlled fault injection. Original real Docker integration is separately verified, not claimed to participate in the mutation injection.

## P30 enforced change and host proof

Fix commit `e20bca1332bbe6772c08ebee046c419c277b6ad7` in `src/cognition_agent_os/repo_repair.py::review_repo`:

- Re-read exact sealed HIDDEN bytes (the actual SHA256 and equality with the earlier evaluated `hidden` bytes) **inside the original SQLite write lock BEFORE staging**. Changed/missing gold returns `HOLDOUT_PIN_MISMATCH`; no approved effect.
- After staging, re-read the exact gold bytes AGAIN. Changed/missing gold routes through the existing durable `REPO_POST_STAGE_EVIDENCE_CHANGED` / `REPO_DOCKER_POST_STAGE_REJECTED` path, with diagnostic boolean `holdout_pin_still_valid`. The task cannot be promoted to `REPAIR_LAB_VERIFIED`.
- The model/planner still does **not** see sealed hidden expected values. Public feedback, candidate generation policy, goal/grant checks, actual Docker isolation and source non-mutation are unchanged.

Third [host-lifecycle test](https://github.com/D1traverser-debug/cognition-agent-os/blob/feat/p10-runtime-conformance-20261020/tests/test_p12_repo_lab.py) added at commit `01bb38820c6680b6dbcace492ef83ab58154659d`: actual `host.run_tick(auto_stage_goals=True,auto_review_repos=True)` processes a seeded repo task, freezes the proposal, invokes independently admitted repo review, detects changed gold, leaves task `NEEDS_REVIEW`, and emits NO holdout acceptance receipt. The host, SQLite, candidate and conformance paths are genuine; ONLY the arbitrary-code Docker process is replaced with the controlled fault injector.

Actual full [green Actions #39623752186](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39623752186) on pre-archive commit `01bb38820c6680b6dbcace492ef83ab58154659d`: Linux **344/344** including the three new tests, Windows offline, real no-network Docker integration and native Windows user-scoped Scheduled Task **COMPLETED/SUCCESS**; 7B/live source/paid opt-ins SKIPPED.

## Final boundaries and next priority

This prevents the observed persistent fixture drift across two specific acceptance windows, but SQLite locking does not make arbitrary filesystem contents transactional, and transient gold swaps/restores cannot be excluded against a malicious host. Nor does a passing isolated harness prove repair in an unfamiliar full repository. The strongest missing capability evidence is a fully pinned, non-trivial externally authored repo repair with original dependencies, multiple interacting files, independent holdout, and maintainer/second-system acceptance **without the suggested fix included in the prompt**. A further model test must be prospectively frozen and genuinely informative; do NOT repeatedly retune P21/P22/P23/P24, relax results or replace model output with a script. Existing no-cloud/no-owner-host restrictions continue.

Next: check FINAL post-archive candidate HEAD CI (model jobs SKIPPED), and post its actual status as an existing PR #12 comment instead of another self-triggering source commit. More scanning/monitoring documentation by itself is not a substitute for real capability advancement.
