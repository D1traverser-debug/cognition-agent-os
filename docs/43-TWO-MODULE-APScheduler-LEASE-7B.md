# P32 — Full original APScheduler two-module lease cleanup repair, preregistered

## Why this is genuinely multi-module

Outside issue [agronholm/apscheduler#1116](https://github.com/agronholm/apscheduler/issues/1116) reports a crash when a still-running job's lease expires and is re-acquired and released twice. Two original independent methods have unguarded `KeyError` sites:
1. `apscheduler/datastores/memory.py::MemoryDataStore.release_job` pops missing job after previously decrementing `running_jobs`.
2. `apscheduler/_schedulers/async_.py::AsyncScheduler._run_job` removes an already-gone job from `_running_jobs` unconditionally in `finally`.

P31 executed an entire external dateutil package but allowed **only one source method** to change and the 7B proposal was rejected. P32 instead **requires changed code in BOTH original source modules**, with two independent public failure mechanisms, eight separate hidden inputs, genuine full published wheel and actual dependency imports. This addresses a narrower anti-crash/idempotence contract, not the stronger as-yet-unproven claim that genuine scheduler lease reacquisition itself is eliminated. The issue description makes the vulnerable sites public; NOT a blind code-location discovery.

## Original source and dependency identity

Official published APScheduler **4.0.0a6** original wheel `apscheduler-4.0.0a6-py3-none-any.whl` SHA256 `87031f7537aaa6ea2d3e69fdd9454b641f18938fc8cd0c589972006eceba8ee9`.

Pinned release-tag source Git blob SHA1:
- `apscheduler/datastores/memory.py`: `1c3ecccee81d5ed967eb9d81b8380fcdd450c1cf`.
- `apscheduler/_schedulers/async_.py`: `b9bd4d02ec3581c218e8a639d7cf3e6fe12441c6`.

Seven real PyPI dependency wheel SHA256s frozen on the original package baseline:
- anyio 4.9.0 `9f76d541cad6e36af7beb62e978876f3b41e3e04f2c1fbf0884604c0a9c4d93c`.
- attrs 25.3.0 `427318ce031701fea540783410126f03899a97ffc6f61596ad581ac2e40e3bc3`.
- tenacity 9.1.2 `f77bf36710d8b73a50b2dd155c97b870017ad21afe6ab300326b0371b3b05138`.
- tzlocal 5.3.1 `eb1a66c3ef5847adf7a834f1be0800581b683b5608e74f86ecbcef8ab91bb85d`.
- idna 3.10 `946d195a0d259cbba61165e88e65941f16e9b36ea6ddb97f00452bae8b1287d3`.
- sniffio 1.3.1 `2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2`.
- typing_extensions 4.13.2 `a439e7c04b49fec3e5d3e2beaa21755cadbbdc391694e28ccdd36ca4a1408f8c`.

All eight wheels are acquired on **ephemeral GitHub CI only**, downloaded with exact package-version pins, *each runtime SHA256 reattested*, imported from original published wheels in an actual read-only, unprivileged, `--network=none` Docker `python:3.12-alpine` subprocess, without executing external package code on host. It calls actual original `AsyncScheduler`, `MemoryDataStore.release_job`, and `AsyncScheduler._run_job`; no fake isolated method implementation or patched upstream.

## Independently frozen tests, positive and negative

Frozen `scripts/verify_p32_full_apscheduler.py` manifest SHA256 **`0c5a8c23009a4747eee83fdc60d31e09b1294c0a2a8e236b42ed8013f86ef5ab`**. PUBLIC 4:
- Single real `release_job` with correct running count → PASS.
- Double actual `release_job` with already-removed job and accounting invariants → FAIL on original (`KeyError`).
- Tracked original async `_run_job` completion → PASS.
- Real async `_run_job` whose membership is independently cleared before completion → FAIL on original (`KeyError`).

HIDDEN 8 independently authored parameter variants do not merely repeat the same exact JSON PUBLIC inputs: repeated release with differing task identities, positive result retention, error result types and combinations; async removed member with failed function or retention, tracked error path, and missing executor with no member. Only two original Python callsites and their local original data structures are exercised, *not a real six-second lease-expiry scheduling scenario*. The original reporter's longer actual scheduler replay is separate unmeasured scope; test reliability is intentionally deterministic.

The baseline script NEVER shows hidden expected values in the model prompt; the actual Docker process gets only `input`, while Python host tests outputs against expected values. The original full-wheel no-model [Actions #39634212076](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39634212076) reports PUBLIC **2/4**, exactly two original failed behaviors, all eight wheel hashes and original Git blobs checked; HIDDEN not executed. Linux **353/353**, Windows offline, real no-network Docker, hosted native Windows Scheduled Task all **COMPLETED/SUCCESS**. Candidate/model jobs SKIPPED before opt-in.

## Bounded actual 7B intervention and full-wheel acceptance

One explicit, temporary Draft PR #12 `[run-p32-full-apscheduler-7b]` marker authorizes a **single** on-runner local Ollama `qwen2.5-coder:7b` generation, loopback only, with **180s** inference timeout and `num_predict=1650`, deterministic temperature zero. No cloud metering, no owner computer installation, no upstream repository writes, no prepared answer or public feedback retry. The marker is removed immediately after Actions dispatch.

Model sees only public behavioral target, PUBLIC examples and the unchanged original `release_job` and `_run_job` method excerpts. It must emit 2–4 compact unique literal `find/replace` edits bearing the exact original relative file paths. A deterministic independent AST comparison allows modifications exclusively to the original two method bodies while requiring both originals to be changed and all unrelated AST, module imports/class declarations/other methods unchanged. The complete official wheel is rebuilt with both replacements and corrected `.dist-info/RECORD` SHA256 and sizes, while verifying every untouched member remains byte-identical; no changes are written to the upstream repo or local user host.

The **modified** full original package with all real dependencies must pass PUBLIC **4/4** inside Docker to even access separately frozen HIDDEN 8. Only **4/4 plus 8/8** qualifies as P32 `semantic_repair_verified=true`, and even that is *bounded to these tested paths*, not an upstream maintainer accept, actual live lease fix, general AI code repair rate or deployment authorization.

## Outcome

**PENDING ONE REAL LOCAL 7B RUN.** Do not conflate the original Docker reproduction, green Actions infrastructure or successful model token generation with an accepted code patch. The first experiment outcome shall be recorded from the actual Actions job log without changing the frozen manifests, without same-issue retry or false positive. P31 remains an honest rejected-candidate negative outcome.

This is the same experimental Draft PR #12 branch `feat/p10-runtime-conformance-20261020`, not merged into main, not deployed to owner PC and not a registered UAOS service child.


## Actual P32 genuine 7B result — 2026-10-22 Beijing: PARTIAL, NOT ACCEPTED

Measured [Actions #39634952518](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39634952518) on preregistered HEAD `c91d88df4841b7d2f73ac7dfd046653a469dd9d3` **COMPLETED/SUCCESS** for all five actual workflow jobs: Linux offline regression (**353/353**), Windows offline, actual no-network Docker with original APScheduler and dependencies, hosted native Windows scheduler, and experimental **real Qwen2.5-Coder 7B**. Other optional inference and mutable-source jobs SKIPPED. The GitHub Actions conclusion is infrastructure/test execution success, **NOT semantic bug-fix acceptance**.

Independent authentic **original full-wheel baseline** in the same 7B job confirmed `case_passes=[true,false,true,false]`, PUBLIC **2/4**, original 8 published wheel SHA256 identities and frozen P32 manifest `0c5a8c23009a4747eee83fdc60d31e09b1294c0a2a8e236b42ed8013f86ef5ab`; hidden cases not run on original.

**One and only one** real installed on-ephemeral-runner loopback `qwen2.5-coder:7b` model generation finished in **123.76 seconds** (as measured by the P32 runner including candidate validation and public evaluation), without feedback/retry/fallback. Unlike P31, the model actually produced a well-formed, unique compact two-module candidate: `candidate_frozen=true` means both specified full original source methods changed under strict AST allowlist and reconstructed wheel member/`RECORD` integrity checks, leaving all other package members untouched. Candidate was run as a modified **full original APScheduler wheel with actual pinned external dependencies** inside real Docker, PUBLIC **3/4**, not the required 4/4.

**Result `semantic_repair_verified=false`, `hidden_evaluated=false`, `hidden_passes=null`, `automatic_retries=0`, `upstream_writes=false`, `owner_host_touched=false`.** The unchanged original PUBLIC had passed 2/4; the new code passed 3/4. The job output did not include which of the four public inputs failed, the raw untrusted proposed code or individual observed errors. **Do not invent a per-case failure, attribute a root cause, or substitute a manually authored repair.** Stronger actual lease-reacquisition prevention, arbitrary races and full upstream regression test suite remain unproven.

This is a bounded positive advance in **genuine model candidate generation across two real source modules and real dependency execution**, with a **negative actual bug-fix acceptance result**. It does NOT demonstrate full automatic repair or general multi-file correctness. Compared with the previously logged P31 `candidate_frozen=false`/not tested, P32 froze a true multi-file candidate and reached PUBLIC 3/4; these are different issue/task difficulties and are not a statistical model improvement estimate.

**STOP/NO LEAK POLICY:** Do not re-run or tune `agronholm/apscheduler#1116` in P32 based on this public miss. Preserve the original frozen manifest, 4 PUBLIC/8 HIDDEN labels, one-shot result and separate archived P31 negative. Next independent evaluation should be a *different external task* with newly frozen evidence and more representative complete scheduling scenario, not another attempt on this case. No deployment or merge authority changes.
