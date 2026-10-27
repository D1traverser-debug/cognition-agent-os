# P13 — Public-test feedback-driven full-file repair revision

## Purpose and exact boundary

P12 can execute and evaluate an externally supplied or locally generated
whole-file patch in preinstalled offline Docker. It could not use a failed
public candidate as feedback for **another** code proposal while
preserving original task authority and sealed independent holdout.
P13 adds that bounded missing link, not another event monitor.

`repo-refine-local` is an **explicit one-shot action** on an existing
`repo_container_repair` task in `NEEDS_REVIEW` with a frozen immutable
candidate. It will not trigger from a normal `host-tick` or from the old
`--auto-stage-goals` flag. Unlike text-only inference it actually runs
each candidate in the existing Docker-only no-network, non-root,
read-only resource-capped execution layer; there is no host Python
fallback and no automatic Docker image pull.

An **already installed** loopback-only Ollama model is required to
generate each new candidate. An absent model returns
`INSTALLED_LOCAL_MODEL_UNAVAILABLE` — there is no automatic model
download, cloud API, paid token bill, finite model-credit trial or
pretended completion.

## Boundaries of the loop

1. Re-read the original task/claim, immutable artifact and source
   SHA256, authority revisions and existing conformance circuit.
2. Reproduce failure of the original code against PUBLIC cases in
   Docker; also execute its initial frozen candidate against those
   same PUBLIC cases. If the original works or the candidate already
   passes, there is no reason for revision.
3. Submit the original allowlisted 2–6 source files and PUBLIC cases
   to the installed model. A subsequent attempt also receives the
   preceding *proposed* source text and failed PUBLIC
   `input/expected/index/observed-output-hash` feedback. **No sealed
   holdout name, hidden case input or expected output is opened or
   copied into the prompt.**
4. Validate each proposed full-file JSON patch against the original
   file allowlist and 16 KiB/file limit. A repeated candidate or
   unchanged original fails closed. Execute each novel candidate in
   Docker on PUBLIC cases only, and record its candidate fingerprint,
   pass count and attempt index as durable events inside the original
   SQLite task ledger.
5. Maximum **three model-generated candidates per original parent**
   across invocations. Attempts are counted from persisted events, not
   from process memory. Explicit `--max-attempts 1/2/3` can further
   restrict each invocation.
6. Only if all public tests pass, re-check current goal/grant and
   original source/public bytes under a SQLite write lock, atomically
   create a linked child `NEEDS_REVIEW` task and immutable
   create-once proposal, then supersede the failed original with
   `UNKNOWN / PUBLIC_REVISION_SUPERSEDED`. The original source stays
   unchanged. The child is not `REPAIR_LAB_VERIFIED` and has not
   used sealed hidden reference cases.
7. The **separate** `repo-review --task-id CHILD` action (or the
   separately authorized whole-file Docker host mode) performs a
   complete P12 baseline/public/held-out check. Passing PUBLIC tests
   does not become permission to access production files.

No previous gold output is used for repairing a hidden failure, and a
candidate that fits public but fails hidden is independently rejected,
not given the gold as model feedback. This avoids self-grading, though
no finite public corpus guarantees general semantic correctness.

### CLI

With an initialized ledger, a frozen `NEEDS_REVIEW` parent task,
already installed Docker image and already installed Ollama model:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures repo-refine-local --task-id PARENT_TASK_ID --model INSTALLED_LOCAL_MODEL_TAG --max-attempts 2
```

The command itself is explicit consent to the bounded Docker execution
and locally installed model calls. No host scheduler automatically
invokes it. On public success it returns `child_task_id`; then a
separate human-approved or explicitly automated `repo-review` must
accept the held-out outcome before a lab result exists.

## Actual scope of CI evidence

Unit tests in `tests/test_p13_public_refinement.py` use a **mock
proposer and mocked Docker results** to check durable parent/child
provenance, two-step feedback adaptation, independently bounded attempts,
missing model, Docker missing, grant revocation mid-generation, repeated
hypothesis, exact artifact hashes and hidden-input non-disclosure.
These do NOT prove real LLM reasoning.

The `repo_container_integration` job includes a second,
independent P13 experiment inside actual hosted Linux Docker. A
deliberately scripted stub proposer returns first an incompletely fixed
full-file candidate, then an actually correct multi-module program.
The real container must observe an initial public failure, a partial
public improvement, a complete public pass and then a separate genuine
sealed-holdout pass. The CI evidence must label
`actual_ollama_model=false` (NO REAL MODEL USED) even when real Docker
execution passes. Any Docker failure is a failure, not converted to
a mocked success.

Observed during development: the initial P13 native Docker probe
failed `CONTAINER_EXIT_NONZERO` because the newly generated test
fixture incorrectly wrote literal `\\n` characters instead of
newlines into a Python source. Its test-source byte encoding was fixed.
Require the latest HEAD CI to pass Linux, Windows, actual Docker and
actual hosted Windows native Task Scheduler before calling P13 complete.

## Remaining release blockers

- No proof an installed open-weight LLM genuinely generated a novel
  multi-file patch on an independently supplied, unfamiliar task.
  A mock generated two-round sequence is *control-flow testing* only.
- Not a general browser/desktop autonomous agent or a privileged
  Windows host sandbox; no actual user machine deployment, owner
  trust-root isolation or independent human business outcome.
- A mutable Docker image tag is still not a pinned digest. Host
  Docker/daemon compromise remains outside its sandbox threat model.
- The repair operator, tools, unit tests and goal specification still
  determine the domain. No production-code patch, merge, real-world
  approval or paid/token-credit model API usage has occurred.

All changes are restricted to cumulative **Draft PR #12**, unmerged.
