# P15 — Public observed-vs-expected diagnostics for genuine local correction

## Root cause observed in P14

P14 genuinely ran Qwen2.5-Coder 0.5B, 1.5B and 3B locally on
ephemeral GitHub Ubuntu CI with Docker-executed candidate code.
All three had **0/2 public and 0/2 sealed-holdout success** on identical
two Python repair tasks, despite real token generation and real source
execution. P14 had fixed a fatal distinction between candidate crashes
and Docker installation errors, but the model feedback still contained
only the public input, expected JSON and **SHA256 of the wrong output**.

A SHA256 output fingerprint proves identity, not semantic difference.
A model cannot infer whether a wrong public candidate returned
`{"total":27}`, `{"total":21}` or a completely unrelated object from
those hashes. The previous correction loop discarded precisely the
value needed for debugging. P15 changes the causal feedback, rather
than adding monitoring or new planner authorities.

## New bounded and directionally isolated data flow

`container_lab.run_suite` now accepts
`include_observed=False` (the default). Only the explicitly invoked
P13 `repo_refinement` PUBLIC runs set this to `True`. When a
candidate produces well-formed JSON that differs from the PUBLIC
expected result, the observation includes `observed_value` only
if its canonical encoded JSON is **<=512 bytes**. All observations
still include the output SHA. Program failures retain a fixed,
allowlisted `execution_error` code instead of exposing untrusted
stderr, tracebacks or host filesystem paths.

`repo_refinement._public_feedback` combines the PUBLIC input,
PUBLIC reference expected value, actual wrong `observed_value`
(when bounded), and candidate source text. It sends these only to
an **already installed** localhost Ollama proposer for a bounded
new hypothesis. The existing candidate allowlist, model response
JSON Schema, no-repeat hash admission, 3-trial budget, immutable
SQLite parent/child record, independent Docker execution and
explicit user opt-in remain in effect.

**Withheld tests are not changed and do not opt in.**
`repo_review`, `audit_repo` and any sealed acceptance calls use
the default `run_suite(...,include_observed=False)`, so no hidden
`observed_value` is collected for the proposer to accidentally
include in a later prompt. Reference expected outputs are compared on
the trusted host side, never passed into the Docker container.

Security caveat: any program-generated PUBLIC output is adversarial
data; the 512-byte bound is a data minimization guard, not a guarantee
against prompt injection. Existing model output is still untrusted
and cannot grant itself tools, production source writes or permissions.

## Real experiment and falsification

The existing unmodified P14 two-case set and independent sealed
references remain in `scripts/verify_actual_local_model.py`. To
avoid downloading three real models with known 0/2 results on every
commit, P15 adds a **separate explicit**
`[run-p15-feedback-model]` PR-body gate that installs only the
non-metered `qwen2.5-coder:3b` weights on a disposable CI runner.
The actual installed unmocked model uses P12 and P13's identical
candidate and revision entrypoints, and actual Docker, with the new
PUBLIC observed-value feedback enabled.

The benchmark records true frozen candidates, PUBLIC and sealed
pass counts, and quality failures. **0/2 remains an admissible measured
result**; experiment CI success does not mean the model became
reliable. Nothing runs on owner Windows 11 and there is no paid
model API, finite trial credit or fallback predetermined patch.

Tests in `tests/test_p14_candidate_execution_feedback.py`
prove that bounded PUBLIC wrong values appear in model feedback;
hidden/default invocations keep only digests; output over 512 bytes
is not echoed. `scripts/verify_repo_container.py` now separately
checks via ACTUAL Docker candidate executions that model feedback
has correct bounded observed values and no hidden-only category.
The final P15 real-model test must NOT be claimed until its hosted
CI log provides the actual measurement.

## Remaining honesty boundaries

Passing the static tests only establishes controlled evidence handling.
Passing a two-case held-out benchmark cannot establish open-world
autonomy; a failed result cannot prove every future model is unusable.
Owner-host deployment, independent human outcome review, image digest
pinning, end-to-end unfamiliar third-party tasks and user-specific
hardware availability are not established. No production merge or
release is authorized. All work remains inside cumulative Draft PR #12.
