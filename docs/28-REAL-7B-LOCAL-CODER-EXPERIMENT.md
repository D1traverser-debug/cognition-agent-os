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

Evidence status: **await genuine P17 CI result for this commit**.
Do not reuse the P16 basic unit-test green as 7B capability evidence.
