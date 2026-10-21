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
