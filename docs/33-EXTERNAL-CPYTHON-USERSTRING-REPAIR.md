# P22 — Prospectively pinned external CPython UserString issue (pre-inference)

## Outcome and selection

P21 independently reproduced more-itertools #1332 but three genuine 7B trials delivered zero changed candidate. P22 changes **the external task**, not P21 gold, timeout retries, or source permissions. The new task is externally reported [CPython issue #159868](https://github.com/python/cpython/issues/159868), created 2026-10-20 10:13:31Z, observed OPEN at selection on 2026-10-21. The reporter requires `UserString.startswith(UserString(...))` and `endswith(UserString(...))` to accept the wrapped argument consistently with other UserString methods. This issue already links upstream PR #159869; **therefore this is not private/blind maintainer acceptance**, and no upstream PR solution or corrected implementation has been opened or fetched by this agent.

The original upstream source is independent of issue reporting:
- `python/cpython@d220409a13b77de7a6c30abe16ea90db01528edc`, CPython 3.15.0 release commit from 2026-10-09;
- `Lib/collections/__init__.py`, exact full Git blob `5dbcac19e7a92726fb9594f406177870db1c08bd`, reread and independently verified through the GitHub connector;
- isolated **original unmodified UserString class** is ~7KB, copied from the EOF of the pinned upstream source, plus explicit locally authored import setup and JSON adapter. This is not full CPython build or package integration.

## Frozen acceptance before any P22 local inference

Owner of externally observed behavioral claim: upstream reporter; reproduction is **not yet confirmed** until real original-class Docker execution.

Frozen in `scripts/verify_p22_cpython_userstring.py` and `tests/test_p22_cpython_userstring.py`:
- PUBLIC (4): reporter's two direct UserString affix cases should return true; ordinary str positive and negative controls. Expected original baseline **2/4 passing**.
- HELDOUT (8): alternate UserString positives/negatives, start/end bounds, preserved plain-str behavior, and TypeError for an unsupported integer. Gold is derived independently from Python `str` semantics; **Agent-authored, not a signed external/private oracle**.
- model receives only original class, the legitimate goal statement and PUBLIC test cases. HELDOUT is evaluated only by existing isolated post-proposal reviewer.
- independent accepted-stage scope gate: exact import prefix and adapter suffix preserved; AST of all original class members must be unchanged **except both** `startswith` and `endswith`; main entrypoint must remain untouched. Scope PASS is not semantic PASS.
- original full upstream blob and extracted class are verified from a pinned commit. A changed source/changed public baseline must fail closed, not be silently repaired by editing benchmark gold.

A real successful result would require genuine offline Ollama Qwen2.5-Coder 7B tokens, a frozen changed proposal, all four PUBLIC and eight HELDOUT cases passing in genuine non-network Docker, original source preservation, accepted two-method scope, and completed Linux/Windows/Docker/Windows native Scheduler CI. Failed hypotheses, no-change, timeout, skips and absent maintainer review must remain visible.

## Execution boundary

One-time opt-in `[run-p22-issue-7b]` in the **existing Draft PR #12 body** runs only on disposable public GitHub CI. Default ordinary CI does not pull model weights or call remote inference. Local 7B request is bounded at **300s** for this preregistered experiment, not unlimited; P21 no-change retry is OFF for P22. The owner Windows 11 PC, upstream CPython repository and `main` are not writable targets. No metered cloud LLM API, finite/trial credits, automatic main merge, or deployment.

If the initial ordinary head CI fails, correct the concrete reproducible script/tests without changing frozen source/goal/public/heldout and rerun; do not opt into inference while infrastructure is red. Only after preflight verification activate one P22 real-model run, observe/log exact model score and remove the marker; repeat tuning on the same issue does not establish autonomous competence. Regardless of this one result, actual external maintainer acceptance, real owner-PC unattended runtime, and reliable unfamiliar issue generalization remain open.

**Current state:** Frozen candidate preregistered in Draft branch; model experiment NOT YET EXECUTED; no pass score claimed.

## One-time P22 launch evidence

Prerequisite frozen-head ordinary GitHub Actions #39590121884: COMPLETED/SUCCESS (Linux, Windows, offline Docker, hosted Windows Scheduler). Real model job skipped on that preflight run. The temporary opt-in was placed on Draft PR #12 only **after** the regression gate passed. This documentation-only trigger commit changes no source, goal, PUBLIC or HELDOUT fixture or authority. Real experiment result is pending independent CI evidence.

## P22 actual first-run infrastructure failure and independent baseline (2026-10-21)

Real local-model opt-in [GitHub Actions #39590684936](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39590684936) installed genuine Qwen2.5-Coder 7B weights (4.7GB). BEFORE model inference, the first original-source Docker baseline timed out after the existing 8-second subprocess boundary (ContainerUnavailable: CONTAINER_LAUNCH_OR_TIMEOUT). **No model proposal, no frozen patch, no public/heldout model-quality measurement.** Linux/Windows/Docker/Scheduler ordinary CI jobs passed separately, but the experimental model job FAILED. The temporary PR opt-in marker was removed.

An independent baseline-only read-only execution path was then implemented without installing/loading Ollama. In [Actions #39591455559](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39591455559), the real pinned upstream original code executed in Docker: PUBLIC **2/4 passed, 2/4 failed** as independently reported. Same original preissue Git blob; actual case manifest SHA256 **a2da6ddd13e94c2285ee20673f13843080b796183910a344f8980b4c206dad71**. The timed-out first run therefore does not demonstrate an invalid fixture; the exact cause of timeout under the model CI environment remains uncertain.

Next bounded contrastive check adds a P22-only real original Docker baseline **before** installing Ollama and downloading 7B in the same experimental job, followed by the existing post-install original baseline. Both use unchanged source/gold, unchanged Docker 8-second guard, unchanged source/AST reviewer and original SQLite permissions. If baseline fails before model installation, do not infer model quality. If it succeeds before but fails after, resource/cold-start contention requires independent verification; no unproduced candidate score is recorded. If both pass, proceed to genuine model inference and independent acceptance. Keep opt-in one-time, Draft/unmerged, no paid inference and no owner machine deployment.

## P22 same-run cold Docker control experiment launch

The frozen P22 branch head ordinary [Actions #39591816384](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39591816384) is COMPLETE/SUCCESS on Linux, Windows, real Docker (including independent pinned CPython original PUBLIC baseline 2/4) and hosted Windows Scheduler. One single opt-in model job now checks the SAME original Docker baseline before Ollama installation as an internal cold-start control, then repeats the baseline after 7B installation using the unchanged 8-second Docker rule. The actual model result remains unobserved at trigger; this is not a success declaration.
