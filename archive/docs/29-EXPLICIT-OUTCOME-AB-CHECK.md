# P18 — explicit owner outcome semantics as a repair hypothesis input

## Observed failure and causal alternatives

P17 verified genuine Qwen2.5-Coder 7B inference and an intact independent
Docker acceptance pipeline, but both known repair tasks failed PUBLIC and
HIDDEN acceptance (0/2 each; P17 Actions 39562470066). A larger model
alone did not resolve the observed model-quality failure.

At least two explanations remain plausible:
1. The generation model cannot produce correct multi-file Python code
   under current resource/prompt constraints.
2. The proposer lacks the *intended outcome* and receives only buggy source
   plus two example pairs. Multiple incompatible semantics can match finite
   public examples. A code repair is not uniquely specified by examples.

Neither cause is established by one failure. P18 tests the second mechanism
without claiming a new benchmark or a general capability improvement.

## Mechanism and authority

An **optional, owner-supplied** `goal_statement` string is carried inside the
existing immutable `repo_container_repair` task specification. Validation
refuses empty/control-character/over-1200-byte strings and unregistered
fields. It is **task evidence, not permission**: it cannot override original
write grants, source SHA, file allowlist, Docker restrictions, or independent
acceptance. A model prompt includes the plain-text goal as untrusted data.
Every candidate still must be concrete whole-file code, genuinely change
an allowlisted source file, pass actual PUBLIC Docker cases, and later pass
separately checked sealed HIDDEN Docker cases; no original project source
is changed. The P13 bounded three-generation negative-evidence policy remains.

Tasks that omit `goal_statement` preserve the historical behavior.

## Testable comparison

`scripts/verify_actual_local_model.py` now supports
`P18_EXPLICIT_GOAL=1`. This adds a task-owner textual outcome to each of
the two fixed P14 tasks. Baseline with the flag absent/0 has no such field.
The original `CASES` data and P14 fixture SHA256 remain unchanged:
`0357e22e8b567939b5f9b05baddb4acde1619055e9ed2250d3c715515f1e2baf`.

The task-owner statements are:
- Invoice: product of price and quantity, monetary discount deducted,
  postage added, JSON total output.
- Distinct count: different numbers strictly above the provided
  threshold, one vote per unique qualifying value.

These phrases are authored after the original P17 observation. Therefore
even a quality increase on these same two known tasks would demonstrate only
a *within-benchmark, explicitly specified outcome* effect, NOT blind general
learning or independent unfamiliar-code repair. The evaluator receives the
original unmodified PUBLIC and HIDDEN fixtures, while the model never reads
HIDDEN inputs, expected values, or reference patch bytes.

A strictly PR-opt-in marker `[run-p18-goal-7b]` enables genuine disposable
Linux Ollama Qwen2.5-Coder 7B + native offline Docker. The application itself
never downloads weights. On experiment completion remove the PR marker so
ordinary CI avoids another model download. Always separate:
real inference, valid frozen candidate, PUBLIC suite pass, HIDDEN suite pass,
and untouched source. Report zero scores faithfully.

## Regression, adversarial checks and release

- `tests/test_p14_real_model_benchmark_contract.py` asserts the model
  prompt receives the exact owner goal, schema allowlisting remains intact,
  malformed/too-large/control-character goal fields are refused, and an
  unknown extra execution key is denied.
- The test also exhibits genuine *public-example ambiguity*: both `>`
  and `>=` threshold semantics can agree on ordinary examples yet differ
  on a boundary input. A finite example match cannot prove intended behavior.
- The P14 baseline case digest, PUBLIC suite and sealed HIDDEN bytes are
  invariant across the optional-goal experiment.
- Linux, Windows, actual Docker and native Windows scheduler CI must all
  be checked on the final functional HEAD. Real inference must be explicitly
  observed, not inferred from simulated unit tests.

This is a **hypothesis-quality intervention**, not a release authorization.
Further work must obtain genuinely independently selected unfamiliar task
goals/cases, source-authenticated acceptance and holdout outcomes; a two-case
post-hoc benchmark alone cannot validate open-world autonomy. No paid remote
LLM API, finite trial/credit service, owner's Windows machine, or main branch
mutation is permitted by this work.

## Observed real model comparison — 2026-10-21

Actual disposable hosted Linux 7B + real Docker run
[GitHub Actions #39568633684](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39568633684)
completed successfully **as an infrastructure and candidate-quality experiment**.
The identical archived P14 fixture manifest remained
`0357e22e8b567939b5f9b05baddb4acde1619055e9ed2250d3c715515f1e2baf`.
No correct reference source was given to the local model, no hidden case
was used to adjust a candidate, and original project source stayed unchanged.

| Genuine 7B condition | Initial candidates frozen | PUBLIC full pass | HIDDEN full pass | Revisions |
|---|---:|---:|---:|---:|
| P17 — no explicit goal | 1/2 | 0/2 | 0/2 | failed corrections |
| P18 — explicit task intent | **2/2** | **2/2** | **2/2** | **0** |

P18 invoice result: native first review `REPAIR_LAB_VERIFIED`, PUBLIC
2/2, HIDDEN 2/2, elapsed ~65.6 seconds. Distinct-threshold result:
native first review `REPAIR_LAB_VERIFIED`, PUBLIC 2/2, HIDDEN 2/2,
elapsed ~66.1 seconds. The same run completed Linux **285/285**,
Windows **285/285**, true Docker integration and genuine hosted Windows
Scheduler with SUCCESS; third-party live source job was SKIPPED.
The P18 model opt-in marker was removed from Draft PR #12 after the result.

**Causal limits:** The test uses the identical two already-known tasks, and
Agent-authored outcome descriptions written *after* previous failures.
They are not actual owner-signed requirements, genuine new blind corpus,
or independent third-party semantic adjudication. The outcome supports
that missing intent materially contributed to these two observed failures;
it cannot rule out model nondeterminism or benchmark contamination or prove
transferable repair competence. P18 remains a bounded experiment under
Draft/unmerged release constraints. The next meaningful test must
pre-register unfamiliar tasks and gold before any local-model inference.
