# P14 — Genuine offline local-model coding measurements: 0% task success

## Why this phase exists

P13 passed a true Docker two-iteration feedback loop with a **scripted
fake proposer**. That proved execution plumbing, not local-model reasoning.
P14 explicitly runs **real installed open-weight model inference** on
two fixed, independently judged multi-file Python repair tasks. No remote
inference API, paid model tokens or expiring AI credits are used.

This is a capability *falsification* exercise: model logic can fail
without the CI experiment being declared a technical infrastructure
failure. The benchmark never inserts a prepared correct patch.

## Real test environment and original data

Temporary **public GitHub-hosted Linux** runner only; no owner
Windows 11 computer is accessed. A CI-only script installs real
Ollama and pulls Qwen2.5-Coder 0.5B, 1.5B and 3B open weights.
Ollama is served at `127.0.0.1:11434` with
`OLLAMA_NO_CLOUD=1`; inference uses only the previously existing
loopback `_request` API without mocked responses.

The benchmark in `scripts/verify_actual_local_model.py` holds two
fixed source tasks with source files `main.py` and `calculator.py`:
- an invoice totals calculation that wrongly adds a discount instead
  of subtracting it, while shipping is added correctly;
- a threshold counter that wrongly counts duplicates and includes
  the threshold, rather than counting **distinct values strictly above**
  that threshold.

Both tasks include two PUBLIC examples and two different hidden
examples. The reference expected values are cross-checked by
`tests/test_p14_real_model_benchmark_contract.py` with a trusted
independent calculation. The model sees the original source and
PUBLIC inputs and expected outputs, but does not receive hidden
examples, their labels, the fixture paths or a precomputed patch.
Benchmark manifest SHA256:

`0357e22e8b567939b5f9b05baddb4acde1619055e9ed2250d3c715515f1e2baf`

The original program's failure is reproduced inside the existing real
network-disabled, read-only, non-root Docker execution environment;
all new candidates go through existing immutable SQLite proposal
admission, public evaluation and separate sealed-holdout acceptance.

## Real model execution and observed results

**First run:**
[Actions #39539858927](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39539858927)
installed real local 0.5B and completed inference but froze **0/2
valid whole-file candidates** (0/2 hidden). It demonstrated that model
availability does not establish valid repair output.

**Second run:**
[Actions #39540175403](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39540175403)
compared real 0.5B and 1.5B after enforcing Ollama's supported JSON
Schema for exact `changes[{path, content}]` format:
0.5B froze 2/2 candidates, but both produced no valid JSON output
in Docker; 1.5B froze 2/2 and ran but failed both PUBLIC suites,
then repeated the earlier incorrect hypothesis. No hidden success.

**Correction prompted by real failures:** previously
`CONTAINER_EXIT_NONZERO`, `CONTAINER_OUTPUT_BOUNDS` and invalid
JSON were reported as `ISOLATION_UNAVAILABLE`. That inaccurately
confused candidate code failure with an absent/broken Docker service
and prevented useful public-feedback revision.

`container_lab.py` now reports a separate
`CandidateExecutionFailed` class for real container-run program
nonzero, empty/oversize output and invalid JSON; `run_suite` counts
these as failed cases. Only missing Docker, launch/timeouts or Docker
CLI internal failures stay `ContainerUnavailable`. P13
`_public_feedback` may send a **bounded, allowlisted, public-only
execution error code** to the model, never host traceback, hidden
labels or Docker write privileges. It explicitly advises generating
a DIFFERENT patch after an observed public failure, while still
enforcing the original hash-based duplicate rejection and attempt cap.
`tests/test_p14_candidate_execution_feedback.py` covers those cases.

**Final real comparative run:**
[Actions #39541759002](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39541759002)
completed SUCCESS as a **real experimental procedure**, not as a
statement of useful model quality:

| Model | Valid frozen candidates | All public cases pass | Sealed holdout pass |
|---|---:|---:|---:|
| Qwen2.5-Coder 0.5B | 2/2 | **0/2** | **0/2** |
| Qwen2.5-Coder 1.5B | 0/2 | **0/2** | **0/2** |
| Qwen2.5-Coder 3B | 2/2 | **0/2** | **0/2** |

0.5B's real code proposals reached Docker but had 0 public passes;
subsequent proposals repeated the prior failed hypothesis. 1.5B
proposed the original source unchanged on both tasks, leading to the
expected refusal `Candidate makes no actual source change`. 3B
froze two real candidates, had 0 public passes on both, and later
repeated its previous invalid hypothesis. The two 3B per-case
measurements were approximately 97 seconds each on CPU-only CI.
No hidden tests were opened to repair the failures. Nothing in the
original repository was modified.

The same final run independently passed:
- Linux and native Windows regression suites;
- actual sandboxed whole-file Docker integration, including negative
  network/readonly and hidden-example refutation probes;
- true Windows Task Scheduler 2 native ticks / 2 tasks and cleanup.
The external GitHub live-source integration is skipped unless separately
requested. Overall Actions green means the bench, not the model,
functioned correctly. **Code-repair autonomy acceptance is NOT MET.**

## Follow-up controls and decisions

The P14 real-model job is isolated behind an explicit
`[run-p14-real-model]` PR body opt-in. This opt-in was **removed after
the evidence was collected** to avoid repetitively downloading
approximately 3.3GB of model weights on every docs-only commit.
The archived run above is the observed P14 model proof. The ordinary
CI continues to enforce Linux/Windows/Docker/Task Scheduler behavior.

Further work must not claim a successful autonomous coder unless
an actually installed model generates novel, valid, useful patches
on independent unseen tasks and passes external holdouts. Reasonable
next experiments include larger local coder weights with sufficient
owner CPU/GPU resources or improvements to goal specification and
feedback grounded only in PUBLIC evidence. A nonzero suite success
rate is a minimum engineering signal, not proof of broad AGI.

Owner-machine installation, OS reviewer/trust-root separation and
third-party business acceptance are all **unproven**. The cumulative
Draft PR #12 remains unmerged. No production source writes, paid
model API charges or limited free inference credits occurred.
