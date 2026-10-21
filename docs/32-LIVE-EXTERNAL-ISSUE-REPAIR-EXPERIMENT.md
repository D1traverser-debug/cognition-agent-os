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
