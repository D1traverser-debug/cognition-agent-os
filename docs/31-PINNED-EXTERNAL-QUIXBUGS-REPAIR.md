# P20 — Third-party repository defects and independently authored official acceptance

## Why this is a new evidence tier

P17's real 7B model initially failed 0/2 known benchmark repairs. P18
added an explicit intended-outcome description and measured 2/2 success
on the same known cases. P19 preregistered two new Agent-authored tasks,
yielding 2/2 full PUBLIC and HIDDEN task pass in real Docker. The user
wants an actually useful self-directed code-repair Agent, not a circular
Agent-authored gold benchmark that validates itself.

P20 therefore does NOT author its own target bug source or expected
answers. Instead it consumes a *third-party public historical defect
benchmark*, [jkoppel/QuixBugs](https://github.com/jkoppel/QuixBugs),
which contains Quixey Challenge programs with defects and independently
authored upstream testcases. This is not a live unfamiliar issue triaged
from a real current maintainer backlog. We are not authorized to change
any upstream repository or production code.

## Exact external source and independent expected-value ownership

- Repository: `jkoppel/QuixBugs`
- Upstream commit: `4257f44b0ff1181dedaedee6a447e133219fcebf`
- Upstream license: MIT, Copyright 2017-2019 James Koppel.
  https://github.com/jkoppel/QuixBugs/blob/4257f44b0ff1181dedaedee6a447e133219fcebf/LICENSE
- Actual upstream program/test paths and Git blob object IDs are
  declared in `scripts/verify_p20_external_quixbugs.py#CASES`.

| Upstream task | Buggy source Git blob | Official test JSONL Git blob | PUBLIC rows | Unshown-to-proposer rows |
|---|---|---|---|---|
| `python_programs/gcd.py` | `d0a6618748c438590f33483cde37f82b5b276295` | `be94d203ec68e3492eb4a70d00617837f4d630c0` | 0, 3 | 1, 2, 4, 5 |
| `python_programs/max_sublist_sum.py` | `b2d79601d42b4f4a7b91c747f2ed184b6853f6e1` | `ef79f320e9594f2c141aaccf006175cdc26932fc` | 0, 1 | 2, 3, 4, 5 |

The source/test identities were independently read from the GitHub
connector using the immutable commit before the FIRST P20 inference.
Rows and split are preregistered *before* seeing any P20 model outputs.
The source fetch runs only inside the optional ephemeral CI job from a
full-commit raw.githubusercontent.com URL with allowlisted paths and
bounded HTTPS response sizes. Actual bytes are checked against Git blob
SHA-1 identities. Changed or missing upstream bytes fail closed: no
branch fallback, no alternate local invented testcase. The real job
prints an additional manifest SHA-256.

Official QuixBugs test expected values come from QuixBugs, not
Agent-authored Python oracle guesses. The original buggy function is
copied transiently into the existing sandbox fixture with an added
local JSON-to-function adapter; no corrected/reference implementation
is fetched, studied or used by the proposer. This adapter is not part
of the upstream repository. The original program remains a byte-exact
prefix; upstream source is never modified.

### Execution and separation

Use the **existing** `evaluate_one()` / SQLite grant/claims / original
`repo_repair` proposal path and real Docker execution:
- Only buggy source and task-owner outcome text plus selected PUBLIC
  official rows enter a local loopback Qwen2.5-Coder 7B request.
- The remaining four official rows per task are serialized as sealed
  local fixtures and used by independent Docker reviewer only.
- A model-produced edit must be frozen and pass PUBLIC before hidden
  evaluation. The P16 bounded revision rule applies if first code
  fails visibly. Missing Docker or installed local Ollama fails closed.
- Exactly one opt-in `[run-p20-external-7b]` PR marker installs public
  weights **only** on disposable hosted Linux for the experiment.
  No model weights are downloaded on the owner's Windows 11 machine.
- No paid remote inference tokens, finite trial/service credits,
  arbitrary shell execution by the model, upstream source edits or
  production PR merge.
- `tests/test_p20_external_quixbugs.py` covers pinned URL/path
  admission, actual Git blob format, corrupted upstream bytes, bad
  JSONL, no corrected-source fetch and missing one-time opt-in.

### Crucial epistemic boundaries

**This is independent provenance of the test AUTHOR, not hidden
knowledge of the model.** The QuixBugs repo, official tests and even
corrected reference programs have been public for years and could be
part of Qwen2.5-Coder pretraining. We keep gold out of the live prompt
but cannot assert that the model has never seen these problems before.
QuixBugs programs are also simple Python functions; they do not
establish open-world issue discovery, real project dependency repair,
external user-owned acceptance, OS-isolated reviewer trust,
multi-repository systemic causal interventions or true release
readiness. Inference failure or pass must be recorded as observed,
never substituted with our own hidden outputs.

**Acceptance:** a real result must separately report exact upstream
commit/blob and manifest hash, real Ollama probe, frozen source candidates,
PUBLIC full-suite tasks passed, official heldout full-suite tasks passed,
original source preservation, and ordinary Linux/Windows/Docker/Windows
native scheduler CI. Never call a green infrastructure run a code-repair
success if task scores are zero.

After the run, remove temporary model opt-in, write observed outcome
(even zero) into this doc and `SESSION_HANDOFF.md`, then verify final
non-model head CI on Draft PR #12. Next tier beyond P20 still requires
actual new issues and private/independent maintainer acceptance; P20
does not authorize release.

## Observed outcome on external official QuixBugs gold (2026-10-21)

Genuine first P20 run:
[GitHub Actions #39574300182](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39574300182).
This was actual loopback Ollama Qwen2.5-Coder **7B** inference on
disposable Linux plus the original SQLite authority and real offline Docker,
NOT a mocked unit test, scripted patch or presupplied answer.

**Upstream identity was verified during the job**:
`jkoppel/QuixBugs@4257f44b0ff1181dedaedee6a447e133219fcebf`
with all four preregistered source and official test Git blob hashes
matching actual downloaded bytes. The locally adapted two-task manifest
SHA256 printed by the real runner was
`d13924a771bb5c0a744e8ff1c194f4f1c03fe74ff7870f1534e3ac17cdef91ae`.

| Original external defect | Initial model candidate | PUBLIC official rows | HELDOUT official rows | Revisions | Run time |
|---|---|---:|---:|---:|---:|
| gcd recursive argument bug | Frozen | 2/2 | 4/4 | 0 | 91.40 seconds |
| maximum sublist sum running-maximum bug | Frozen | 2/2 | 4/4 | 0 | 109.17 seconds |
| **Aggregate** | **2/2** | **4/4** | **8/8** | **0** | |

The original QuixBugs source was unchanged, the original code
remained an immutable prefix of the temporary fixture, and no upstream
correct reference implementation was fetched. The separate Docker
review returned `REPAIR_LAB_VERIFIED` on the first candidate for each
case. This is an actual observed externally authored expected-value
match, beyond P19's Agent-authored corpus.

The same CI run verified **Linux 295/295**, **Windows 295/295**,
native offline Docker integration and native hosted Windows Scheduler
with SUCCESS. Mutable public GitHub watch smoke was SKIPPED. The
temporary P20 7B PR opt-in marker was removed after observation.

**Do not overclaim:** QuixBugs is widely published with a public
corrected implementation and official tests; no credible claim of
training-set novelty or hidden-from-model-pretraining independence
is possible. Two classic Python functions also cannot establish
root-cause discovery on arbitrary repositories, a genuine external
maintainer acceptance, unsupervised host operation on the owner's
Windows 11 PC or a production release. Preserve Draft/unmerged state
until genuine separate owner-judged outcomes and release authorization.
The next evidence tier needs live externally raised defects whose
specific gold/acceptance was not available to the model during
planning, never more retuning of these old known cases.
