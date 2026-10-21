# P19 — prospectively frozen unfamiliar code-repair tasks

## Motivation

P18 demonstrated a real Qwen2.5-Coder 7B improvement to 2/2 PUBLIC
and 2/2 sealed HIDDEN acceptance on two fixed P14 cases when explicit
goal semantics were added. But the added descriptions were authored
AFTER inspecting old benchmark failures. P18 can therefore test the
mechanism only within a known, potentially overfit scenario.

The next falsifiable question is whether the same existing code/proposal/
SQLite/Docker/independent-hidden workflow transfers to two DIFFERENT,
prospectively fixed tasks without adjusting their examples after
model generation. This is about candidate quality, not a new monitor,
agent management subsystem or permission escalation.

## Frozen before inference

`scripts/verify_p19_unfamiliar_model.py#CASES` supplies two different
task families not derived from the P14 invoice or distinct-threshold
examples.

1. **Digital verification regression retry semantics**: select the
   highest numbered attempt per (suite, test), then count latest PASS
   and latest non-PASS results and list sorted failing test identifiers.
   Known defect: current buggy code keeps the first observed attempt.
   The hidden cases include empty input, out-of-order attempts and
   mixed ERROR/FAIL behavior.
2. **Half-open interval union**: compute covered length without double
   counting overlapping, repeated or touching ranges, including
   negative coordinates and empty intervals. Known defect: buggy
   source adds raw interval lengths rather than merging overlap.

Each task includes two PUBLIC examples, three or four separate HIDDEN
examples, a textual `goal_statement`, a distinct buggy source module
and the same generic `main.py` entrypoint.

The task gold was authored before real P19 model inference. A distinct,
non-LLM algorithm in `tests/test_p19_unfamiliar_corpus.py` checks EVERY
reference expected result and enforces the prospective corpus
contract. This is stronger separation from model outputs than editing
known failures after observing them; it is still **agent-authored**,
not an outside professional review, nor an externally authenticated
business result. Model weights might already know the general
algorithms; this alone cannot prove open-world autonomy.

## Execution and failure boundaries

- The P19 benchmark uses `evaluate_one()` from the existing P14 script.
  This means same live unmocked local Ollama admission, no patch fallback,
  original SQLite task/grant/version, allowed whole-file outputs, and
  actual non-root no-network read-only Docker execution.
- The model sees goal, original buggy file text and PUBLIC examples only.
  The model never receives HIDDEN examples, reference solutions, test
  oracle functions, or an evaluator self-PASS signal.
- Every real candidate must change an allowed source and pass PUBLIC
  before HIDDEN review. A failure remains a measured failure, not
  skipped/auto-completed. Revisions remain bounded to the existing P16
  three-attempt total.
- `script/verify_p19_unfamiliar_model.py` is intentionally misspelled
  nowhere as an executable installation; real entry is
  `scripts/verify_p19_unfamiliar_model.py`.
- `[run-p19-unfamiliar-7b]` opts into one disposable GitHub-hosted
  Linux 7B run; without it, no model weights are pulled. Nothing
  installs on the owner's Windows 11 computer, uses metered model
  token APIs or consumes finite free/trial model credits.
- The precise P19 `CASES` digest is printed from actual repository
  source by the benchmark and will be recorded after inference.
  Any post-result fixture mutation invalidates direct same-corpus
  scoring; a revised task set needs a new version and digest.

## Acceptance distinctions

Evaluate separately: real local inference, valid frozen candidates,
complete PUBLIC case pass, complete HIDDEN case pass, original source
preservation, outcome quality, and any disagreement with task-owner
semantics. Infrastructure SUCCESS never implies 2/2 repair quality.

Even 2/2 P19 hidden success would establish at most successful bounded
transfer to two more agent-authored examples. It would not establish
independent third-party acceptance, signed evaluator trust, autonomous
open-world issue discovery, Windows owner-host deployment, generalized
repair across repositories or permission for source promotion. Keep
Draft PR #12 unmerged.

## Why not simply import a public benchmark wholesale?

Public coding benchmarks can be contaminated by training exposure and
may contain test defects. These limitations have been documented for
SWE-bench Verified and SWE-bench Pro; neither a leaderboard score nor
a test PASS can replace task-specific independent semantic adjudication.

Primary references:
- https://github.com/SWE-bench/SWE-bench
- https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
- https://openai.com/index/separating-signal-from-noise-coding-evaluations/
