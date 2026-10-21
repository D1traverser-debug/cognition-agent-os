# P21 — authentic OPEN GitHub issue → actual source → falsifiable repair

## Outcome being tested

P20's QuixBugs examples were externally authored, but were a widely
published old benchmark with public solutions. P21 uses a newly reported,
still OPEN GitHub defect rather than a synthetic Agent-written task or
historic benchmark answer. It tests whether the existing bounded
coding model can reproduce the externally reported failure and produce
a valid, scope-preserving fix. The focus is actual code and outcome,
not another administration/monitoring subsystem.

## Current external source and reporter authority (2026-10-21)

- Real [more-itertools issue #1332](https://github.com/more-itertools/more-itertools/issues/1332):
  **set_partitions yields no partition for an empty iterable**.
- Reporter: `saadkhantareen`; created 2026-10-15T10:03:18Z;
  state **OPEN** when read on 2026-10-21. Reporter states:
  `list(set_partitions([])) == [[]]`, whereas currently actual
  behavior is `[]`. Bell numbers for 0..5 should be
  **1,1,2,5,15,52**, not **0,1,2,5,15,52**.
- Original code upstream
  `more-itertools/more-itertools@4aeb4338ae1407d8da9723e86da99efeb446f719`
  from 2026-10-14, before issue publication;
  `more_itertools/more.py` original file Git blob SHA-1
  `9c56ab37558733ece94d676f71d502d8048bc1d5`.
- Reporter also expects explicit `k=1` on empty input to continue
  generating no partition; explicit `k=0` to raise ValueError;
  min/max size bounds must not eliminate the zero-block partition.
- Issue has no maintainer fix or acceptance asserted here; other
  contributors may independently resolve it. **Never open/submit
  upstream PR or claim maintainer approval without explicit authority.**

## Exact existing implementation boundary

`scripts/verify_p21_live_issue.py` fetches ONLY the immutable,
allowlisted full upstream `more.py` file on disposable CI, verifies
its whole Git blob hash, then extracts the original contiguous
`def set_partitions` function, ending before `class time_limited`.
This is required because the original upstream module is ~175KB,
while the repository experiment allows 16KB per file. Extraction
creates a **function-scope experimental reproduction**, not a
whole-project patch, project dependency install, nor endorsement of
a full repo integration result. The original function code is an
unmodified prefix in the candidate's `calculator.py`.

An explicitly authored JSON adapter invokes the original function
and returns partition count, presence of the empty partition,
or a ValueError category. This adapter is experiment infrastructure,
not a replacement implementation. The same source/JSON adapters,
original SQLite task/grants, preflight, installed local Ollama 7B,
no-network unprivileged Docker, immutable artifact and independent
Docker holdout reviewer are reused from P12-P20.

**Important independent post-acceptance check:** A successful Docker
holdout alone could be obtained by a model rewriting the JSON adapter
rather than the underlying upstream function. P21 therefore checks
the accepted *staged* `calculator.py` retains the exact original
adapter as a suffix, does not alter `main.py`, and actually changes
the upstream function. Report `function_only_contract_pass`
separately from `REPAIR_LAB_VERIFIED` (the existing reviewer).

## Acceptance frozen BEFORE first model call

Source/issue/CASE/goal/holdout identities are stored in
`scripts/verify_p21_live_issue.py` and contract unit tests
`tests/test_p21_real_issue.py`. The CI opt-in marker is activated
**only after this content is committed**. Input goal derives from
the external reporter's behavior contract, not the Agent's chosen
correct patch.

PUBLIC: reporter's exact empty-iterable failure case, plus a
two-element ordinary Bell count. HIDDEN: 8 Agent-derived but
independently mathematically checked cases, including empty
iterable with explicit `k=1` and `k=0`, nonempty Bell numbers
for 1/3/4/5 elements, 3-element `k=2`, and empty `min_size=2`.
Visible reporter expected values and every HIDDEN edge are **public
in the issue/code or mathematically derivable**, and are not private
maintainer gold. Hidden means *not supplied in this candidate prompt*,
not independent secrecy from pretrained language models.

Real CI must first execute the frozen old actual original upstream
function in Docker. Only if the reporter's regression actually fails
and the ordinary nonempty control passes may the real local model
hypothesis be evaluated. If the original failure cannot be
reproduced, explicitly fail instead of manufacturing a broken fixture.

The model must produce a genuine whole-file candidate, freeze it
immutably, and pass public then all hidden cases in Docker. Reject
successful-looking candidates that bypass the original function,
alter the adapter or rewrite the entrypoint. Track true frozen,
public/hidden, scope-preserved, source-preservation and model
generations independently. No fixed reference patch is generated
in advance and there is no fallback fake inference.

## Experiment and claims

The only opt-in is temporary PR body marker
`[run-p21-issue-7b]`, which runs on ephemeral GitHub-hosted Linux
with actually installed Qwen2.5-Coder 7B weights. No automatic
model pull at runtime; the user Windows PC remains untouched, and
no metered remote model or finite credits are used. Marker must be
removed after observing the real result so ordinary branch builds
do not repeat weight downloads.

An observed P21 result can support successful bounded repair of a
specific actual reported defect in a copied function. It CANNOT
establish a real maintainer review, legal issue ownership, merged
upstream fix, private unseen issue novelty, complete dependency
integration or fully autonomous open-world issue discovery. Only
a future outside owner review/actual upstream test+merge would
establish that stronger tier, and even that is project-specific.

P21 is kept on cumulative `cognition-agent-os` Draft PR #12.
Never merge main/production or change upstream project code.
Record actual success, failure, skipped steps and next blocker.

## P21 first actual run — reproduced defect, genuine 7B request timed out

[GitHub Actions #39578220154](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39578220154)
used the pinned upstream source bytes. Verified full upstream Git
blob and extracted function SHA256
`8133f98d95e9bfc4a413772940f7ee61e1ff35c5b2281f108c26801ac9eb27fd`.
The frozen public/hidden adaptation manifest SHA256 was
`2617fecb61f8442ec99d5503460117e2a2f9dd7ebe9348c847ec08935f477b69`.
Real original-source Docker baseline: **1 of 2 PUBLIC failed** as
reported, with a normal nonempty control passing. This is actual
bug reproduction, not model opinion.

Actual Ollama Qwen2.5-Coder 7B proof succeeded, but the initial full
generation exhausted the P17/P20 180-second local request timeout:
`LocalModelUnavailable`, `candidate_frozen=false`,
`public_pass=false`, `heldout_pass=false`,
`function_only_contract_pass=false`, `elapsed_seconds=180.14`.
This is **no candidate / NOT FIXED**, and cannot be credited
as a public or private acceptance failure of a candidate that
was never generated. The job finished green because this research
harness reports honest model quality/unavailability separately
from infrastructure success. All Linux/Windows 302/302, native
Docker and Windows Scheduler jobs passed. Upstream unchanged.

**Bounded diagnosis/intervention:** 180.14s matches the configured
180s generate timeout and `LocalModelUnavailable` is the observed
failure. The precise root may also involve local 7B throughput,
host CPU pressure or output length; a longer cap only tests
the time-budget explanation. Candidate code quality remains
unmeasured until complete generation.

One narrow, explicit additional evaluation allows **300 seconds**
for real locally installed `qwen2.5-coder:7b` ONLY with the
CI-controlled one-time P21 opt-in. Historical unflagged local
7B stays 180 seconds; all other local model calls stay 90s.
`COGNITION_LOCAL_7B_GENERATE_TIMEOUT_SECONDS` accepts ONLY
`180` or `300`; malformed or unbounded input fails closed.
The original source, issue goal, public and hidden fixtures
are unchanged. This is not a model API billable-token usage
or release authorization. Do not endlessly escalate timeout:
if a completed 300s generation is absent, report capacity
blocker, do not invent repair quality.

Real second attempt results are NOT yet available at this
checkpoint. Keep Draft, remove temporary model opt-in after
observing the repeat; record exact run and limitations.

## P21 second real run — completed candidate is unchanged (2026-10-21)

[Real GitHub Actions #39579650252](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39579650252)
re-ran the *identical* upstream issue, original source and original
PUBLIC/HIDDEN fixture bytes. The frozen manifest SHA256 remained
`2617fecb61f8442ec99d5503460117e2a2f9dd7ebe9348c847ec08935f477b69`.
The reporter's real Docker baseline still failed 1 of 2 PUBLIC cases.
One full local Ollama Qwen2.5-Coder 7B completion was observed after
**283.65 seconds** with the strictly bounded 300s request budget.
However, `candidate_changes` rejected the full JSON proposal with
`Candidate makes no actual source change`. The ledger finalized
`REPOSITORY_PROPOSAL_UNAVAILABLE`, no frozen candidate,
PUBLIC and HIDDEN accepted FALSE, and no adapter-scope pass. These
are model-quality/proposal-admission results, not a successful
repair or even a Docker-tested changed source. All originals intact.
Linux/Windows **303/303**, real offline Docker and hosted Windows
Task Scheduler passed as infrastructure, not code quality.
Temporary second model marker removed after observation.

**Narrow causal finding:** the elapsed generation cap was a
blocking constraint in the first run. Removing that constraint
uncovered an unchanged-hypothesis failure. The second real run
did not complete a changed code candidate. A longer timeout alone
is not a repair mechanism.

**Exactly one bounded negative-feedback intervention:** Within the
original SQLite `run_repo_candidate` entry, when a completed
local Qwen2.5-Coder 7B generation produces **no source change**,
an explicit P21 opt-in permits one additional generation with a
bounded PUBLIC rejection containing the prior candidate hash,
`MODEL_CANDIDATE_NO_CHANGE` and instruction to produce a
materially different implementation. It does **not** run or
evaluate the unchanged candidate, read hidden fixtures, consult
prewritten gold, create extra privileged agents or change source.
Either the second candidate passes allowlist/nonchange admission
and gets frozen for *independent* Docker review, or the task
fails UNKNOWN. No infinite feedback loop is introduced.
Ordinary runs, deterministic candidates and other local models
retain their prior behavior. A P21 initial 2-generation attempt
reduces the later allowed public-refinement budget to at most one
additional model generation. Evidence is recorded in the frozen
artifact (`initial_model_generations=2`, rejection fingerprint).
Fresh contract tests verify successful recovery and fail-closed
behavior under repeated no-change responses and malformed opt-in.

One-time opt-in specifically gates `COGNITION_LOCAL_NOCHANGE_RETRY=1`
and **300s** generation only on disposable real GitHub-hosted
Linux. The same external issue source, goal, publicly reproduced
failure, and all 8 original heldout checks stay byte-for-byte
unchanged. This is the third and final planned capacity-controlled
P21 experiment, not open-ended benchmark tuning. Even a full
success is a *function-extraction scoped* fix pending external
maintainer acceptance, not a real upstream project merge.
