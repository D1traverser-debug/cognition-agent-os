# P12 — General whole-file candidate experiments in an offline Docker lab

## What this phase actually changes

P11 explored small edits limited to enumerated AST operators. P12 accepts
**whole-file source replacement candidates** for a bounded 2–6 file Python
project. The candidate can include loops, dictionaries and calls not present
in the previous pure-expression grammar. It is untrusted data until a
separately authorized Docker laboratory runs it and checks public plus
held-out reference results.

This is **not** unrestricted access to a working repository, automatic
production commits, real-world correctness or proven local-model
intelligence. It remains a task in the ONE existing SQLite authority,
claim, artifact, conformance and revision ledger.

## Candidate and evaluator separation

`repo_container_repair` has:
- `files`: 2–6 flat allowlisted local `.py` files;
- `entrypoint`: an allowlisted source file taking a JSON object from stdin
  and producing a JSON result on stdout;
- `candidate`: an externally provided JSON file with an array of
  `{"path":"rules.py","content":"<entire source>"}` changes;
- `visible`: a bounded public JSON input/expected suite;
- `holdout` and `holdout_sha256`: a separately pinned withheld suite.

`worker-once --planner-mode deterministic` freezes an untrusted
candidate provided outside the model. Optional
`--planner-mode ollama-local --local-model NAME` can **ask an already
installed loopback Ollama model** to propose full-file replacements based
only on original sources and *visible* examples. It checks the local
model list first. **No auto-pull, remote token API, free-credit quota,
trial account or payment** is used. Passing a mocked local-model test
does not prove a real model has been installed or has worked on the
user's computer.

The candidate is frozen with original source SHA256s, visible case SHA,
candidate content SHA, task/grant revision, provenance and an explicit
`SEALED_NOT_READ_BY_PLANNER` flag. Proposal alone has NO execution or
production-write authority.

`repo-review` is a separate positive opt-in to run the candidate in
a **preinstalled** Docker container. There is never a host-Python
execution fallback. Real Docker runs use:
- image `python:3.12-alpine`, `--pull=never`;
- stdin attachment `-i` so the candidate receives actual case input;
- no network, read-only source mount, read-only root, no extra
  capabilities, `no-new-privileges`, non-root UID/GID 65534,
  PID/CPU/memory limits and 8-second launch timeout;
- input JSON only. Neither expected public outputs nor withheld expected
  outputs nor hidden file bytes are mounted or passed to the candidate.
  The host comparison process alone owns reference expectations.

For an observed repair to be admitted, the **original source must fail
at least one public case**, and the modified candidate must pass every
public case and all separately pinned hidden cases. It then stages
approved whole-file outputs create-once under
`workspace/repo_lab/<task-id>/`, not over the original source.
Source, proposal and staged bytes are rechecked before recording
`REPAIR_LAB_VERIFIED` and a non-production `REPO_DOCKER_HOLDOUT_ACCEPTED`
receipt. Subsequent runtime conformance can invalidate tampered claims
and disable the existing repair-lab family circuit.

## Explicit authorization boundary

The earlier `host-tick --auto-stage-goals` opt-in was designed for
bounded AST/sandbox review. **It must not silently authorize execution
of whole-file arbitrary Python even within Docker.** P12 requires
a *separate* `--auto-review-repos` flag **and** the pre-existing
`--auto-stage-goals` flag to enable automatic Docker code review.

A manual `repo-review --task-id ...` remains a distinct explicit review
action. Neither path can merge code, change the original source,
self-issue a write grant or bypass a revoked grant/circuit. If the
Docker binary or image is missing, the operation returns
`ISOLATION_UNAVAILABLE` rather than executing Python on the host.

```powershell
# Requires existing initialized authority, fixtures and explicit task spec.
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-repo-repair --spec .\repo-task.json

# Freeze supplied candidate; never executes its Python code:
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures worker-once

# Runs arbitrary proposed Python ONLY in installed offline Docker:
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures repo-review --task-id TASK_ID

# For automatic Docker review, both affirmative flags are required:
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures host-tick --auto-stage-goals --auto-review-repos
```

## First real CI failure and correction

The initial actual `repo_container_integration` run
`39531912897` failed even while the Linux and Windows Python
unittests and Windows Task Scheduler jobs succeeded. In
`container_lab._docker_run`, `subprocess.run(input=...)` passed JSON
into the Docker CLI but `docker run` lacked `-i` and passed EOF to
the container. The Python candidate therefore could not parse stdin,
produced a nonzero exit, and was correctly **not accepted**. The
Docker command was fixed to attach stdin. It was not made to fall
back to host execution or treat a crash as passing.

A separate improvement requires a witness that the original program
actually fails public input before accepting a replacement as a repair.
The integration script now includes the already-correct baseline with
a comment-only change, which must be rejected as
`NO_FAILURE_REPRODUCED`.

`tests/test_p12_repository_permissions.py` adds offline denial cases
for Docker-not-installed, untrusted filenames, implicit old-host
execution, and the isolated local-model proposer prompt.
`scripts/verify_repo_container.py` uses REAL Linux Docker containers
to check a multi-module debit/credit aggregation fix, hidden failures,
network and file-write restrictions, no hidden gold mounted and baseline
failure reproduction.

**Verified functional CI:** Commit
`316b4cb33b2ca83187136519def343faf9e7a4d9` completed
[GitHub Actions run 39535169493](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39535169493)
with Linux **260/260 PASS**, Windows **260/260 PASS**,
`repo_container_integration` **PASS** (real public/hidden multi-file
execution, no-network nonroot and read-only rejection probe,
public-fitting/hidden-refuted candidate, original-no-failure rejection),
and real Windows native Scheduler **PASS** (two OS ticks, two processed
tasks and clean temporary task removal). A previous intermediate
commit caused four old test failures because their mock assumed no
baseline and a single host flag; the old tests were corrected for the
new security contract, not skipped. Public third-party live-source
smoke remains SKIPPED and no local Ollama model was actually run.
Later documentation-only commits still require a fresh final-head CI.

## Evidence still missing

- No owner-host Docker deployment, secured Windows Docker/WSL worker, or
  real local open-weight model response has been demonstrated.
- GitHub hosted Docker is a containment experiment, not a proof that
  Docker protects against hostile daemon/kernel exploits.
- Docker image `python:3.12-alpine` is currently a mutable tag, not an
  independently pinned image digest. Supply-chain pinning remains a
  release prerequisite for stronger reproducibility.
- Neither sandbox output comparison nor a pinned golden JSON establishes
  an actual third-party business outcome. Externally managed signed
  owner/domain review from P10.7–P10.9 has not been generalized to
  arbitrary repository tasks.
- The Agent does not autonomously discover arbitrary defects on the
  user's Windows 11 computer and has not changed the production repo.

All changes remain in cumulative Draft integration PR #12, UNMERGED,
without paid model token charges or finite AI-credit dependencies.
