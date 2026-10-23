# P17 — Real 7B local coder capacity test on the unchanged sealed benchmark

## Decision and hypothesis

P14/P15 tested Qwen2.5-Coder 0.5B / 1.5B / 3B using **genuine
Ollama inference** on a disposable Linux GitHub runner, and all had
**0/2 independently accepted code repairs**. P16 changed the
negative-hypothesis loop: a repeated/unchanged/malformed generation
now consumes a durable bounded attempt, sends public-only rejection
evidence and uses modest nondeterministic sampling on a later attempt.

P17 tests one relevant competing explanation: the small
code model cannot synthesize the necessary multi-file patch.
The question is whether a genuinely installed **Qwen2.5-Coder 7B**
can improve the same unchanged task outcomes without cloud inference
or privileged execution. It is a falsifiable **capability experiment**,
not a production adoption.

## Protocol

- Existing `scripts/verify_actual_local_model.py`, original independent
  two-case benchmark and fixed public/hidden suites remain unchanged.
  Benchmark SHA256:
  `0357e22e8b567939b5f9b05baddb4acde1619055e9ed2250d3c715515f1e2baf`.
- CI opt-in `[run-p17-7b-local-model]` only. Download open 7B weights
  via Ollama onto the **temporary hosted Linux runner only**;
  bind inference to loopback and disable Ollama cloud, no
  metered model token API or finite third-party inference credits.
  The user Windows 11 host is untouched.
- Confirm an actual unmocked completion of `/api/generate`, then
  let the existing Agent propose whole-file code through the original
  SQLite task/claim authority. Execute the generated code only in
  no-network, read-only, non-root, resource-capped Docker.
- Expose PUBLIC wrong outputs and prior failed proposals under P16's
  total three-generation budget; never reveal hidden case inputs or
  expected results to the model. Duplicate/no-change/malformed
  generations are negative evidence, not new successful hypotheses.
- Report, separately, genuine inference completion, task candidate
  admission, PUBLIC pass, independently checked hidden pass, and
  original code preservation. If hidden acceptance stays 0/2, record
  that failure without a prewritten correct patch, a model substitute,
  a changed benchmark or a fake CI success claim.
- Model download and genuine inference are conditional on temporary
  PR opt-in. Once observed, remove the marker to avoid repeated
  large runner-only weight downloads.

## Non-claims and release blockers

The existence of a 7B model is not independent task success.
Even a 2/2 result on this tiny fixed benchmark would only show
limited functional ability, **not** safe real-world general autonomy.
Docker daemon isolation, owner-PC deployment, human-reviewed business
outcome, authentic owner OS trust root and multi-repository open-world
evaluation remain unproven. Draft PR #12 is not merged; no change to
production sources is authorized.

## Actual unmocked experimental result (2026-10-21)

The explicitly opted-in native experimental run
[Actions #39562470066](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39562470066)
completed **SUCCESS as infrastructure and evidence collection**.
It installed genuine Ollama and `qwen2.5-coder:7b` on disposable
Linux CI, performed a real token-generation probe, and executed
whole-file proposals in the existing real offline Docker runtime.
The benchmark manifest remained
`0357e22e8b567939b5f9b05baddb4acde1619055e9ed2250d3c715515f1e2baf`.

| Unchanged task | Initial valid candidate | Public test pass | Hidden test pass | Observed failure |
|---|---:|---:|---:|---|
| Invoice discount and postage | NO | 0/2 | 0/2 | Source replacement was unchanged, rejected as `Candidate makes no actual source change`. |
| Distinct values above threshold | YES | 0/2 | 0/2 | Wrong whole-file candidate failed publicly. Two P16 correction generations repeated the same refuted hypothesis and were denied by duplicate fingerprints. |

**Aggregate: valid frozen candidates 1/2; public acceptance 0/2;
independent sealed-holdout acceptance 0/2.** Real completed model
inference is independently confirmed. Approximate per-task experiment
wall times were 59 s and 208 s respectively. Hidden examples were
not used to adapt the proposals, and no original source file was
modified. No predetermined correct replacement was supplied.

The same run's standard checks also passed: Linux **283/283** and
Windows **283/283** unittests, genuine sandbox Docker integration
(including strict isolation and hidden refusal probes), and true
hosted Windows Scheduler two ticks / two tasks and cleanup. The
third-party mutable GitHub live source check was SKIPPED by design.

**Interpretation:** The P16 retry/budget mechanism is operating
mechanically, but Qwen2.5-Coder 7B still failed the autonomy capability
gate. It does **not** demonstrate useful general code repair.
The observed data are a tiny fixed benchmark, not proof that 7B
universally fails coding; no general inference should be drawn.

After collecting the actual experimental evidence, the PR's 7B
opt-in marker was removed. Subsequent docs-only CI runs do not
re-download weights, and the archived run above is the reference.
No deployment on the owner's Windows 11 machine, production merge,
paid remote model tokens or finite-trial AI credits occurred.

The next meaningful problem is improving *hypothesis quality* under
a proven public-only evidence boundary and testing on an independent
unseen corpus, not repeating the same two source defects indefinitely.
