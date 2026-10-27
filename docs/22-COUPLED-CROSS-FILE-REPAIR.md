# P11 — Coupled two-file source repair: autonomous local experiment, not production execution

## Motivation and actual work

Until P10.9, the only source-code patcher understood **one Python function
in one file** and a single operator replacement. Passing that task's
holdout did not prove the Agent could reason about dependencies between
source files or run a user goal through two connected components.

P11 adds a deterministic, **cross-file hypothesis search** through the
original P0–P10.9 SQLite task/grant/claim/evidence/worker and real
`host-tick` pipeline. This is a tangible expansion of task execution
without installing a language model, depending on paid cloud tokens,
exhaustible model credits, or inventing another governance authority.

**Strict trust boundary:** the new task operates on exactly two
standalone, user-provided Python files, each exposing a pure, two-argument
function whose entire body is a single numeric arithmetic/compare return
expression. The output of stage one feeds the first argument of stage two,
and a third input is the second argument to stage two. It cannot run
arbitrary Python, imports, system commands, file APIs, decorators, nested
calls, network clients, or shell scripts. AST source is parsed and
**manually interpreted**, never `exec`'d/`eval`'d/imported.

This restricted grammar is intentionally NOT a general repository patch
sandbox or a guarantee of arbitrary task correctness. We have not yet
proved a safe open-world executable code environment on the user's PC.

## Data contract

The user (or external goal author) seeds `pipeline_code_repair`
through the existing task intake:

```json
{
  "kind": "pipeline_code_repair",
  "stages": [
    {"source":"net.py","function":"net"},
    {"source":"scale.py","function":"scale"}
  ],
  "visible":"public.json",
  "holdout":"secret.json",
  "holdout_sha256":"EXTERNALLY_PINNED_64_HEX_SHA256"
}
```

Each case is a bounded numeric JSON record, e.g.
`{"args":[9,4,3],"expected":15}`, with no program execution.
The planner reads the two original source files and **visible** cases
but does not read hidden cases. It enumerates possible operator
substitutions across **both files simultaneously**, including candidates
in which only one stage changes; the search must find exactly one
solution passing all visible examples, and the original code must
demonstrably fail an example. Otherwise it abstains with UNKNOWN.

The proposal is stored through the same existing immutable proposal
mechanism, with the task ID, original-source digests, visible-case
digest, selected two-file AST text and candidate hashes. It is NEVER
allowed to write over the original source files or call a remote
model in the deterministic P11 path.

A **separate** code path in `pipeline_oracle.py` runs the independently
implemented P10.4 operator interpreter over the linked outputs; it
rechecks the frozen proposal, source identities and public contract
before checking digest-pinned withheld cases. A candidate passing public
but failing hidden gets UNKNOWN/`PIPELINE_HOLDOUT_REFUTED` and no
staged code. A successful candidate is staged **create-once** at
`workspace/pipeline_lab/<task_id>/<file>.py`. Before updating
`REPAIR_LAB_VERIFIED` and recording its acceptance receipt, the reviewer
again reruns the independent hidden oracle and physically reads the two
staged files. If inputs change between approval and effect, the task
is rejected without a false success receipt.

The original conformance inspector recognizes and independently rechecks
this same existing verified state for the P11 task kind. Previously
verified multi-file repairs are re-audited, and demonstrated tampering
can trip the existing durable repair-lab capability breaker.
There is no self-issued reset.

## Actual entrypoints

On an initialized ledger and existing local fixture files:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-pipeline-repair --spec .\two_stage_spec.json
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures worker-once
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures pipeline-audit --task-id YOUR_TASK_ID
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures pipeline-review --task-id YOUR_TASK_ID
```

The existing `host-tick --auto-stage-goals` path may automatically
perform this **sandbox-only** review after a full preflight. The default
`host-tick` runs proposals only and **does not** consume hidden
cases or apply staged effects. This policy is bounded by the existing
max-jobs, grant/goal revisions, integrity circuit and ledger.

## Independent experiment and negative controls

`tests/test_p11_pipeline_repair.py` contains actual source files for a
two-step pipeline. The first wrong function adds instead of subtracting;
the second wrong function adds a multiplier instead of multiplying.
Neither file can be fixed in isolation to satisfy the whole public
contract: the search must discover the combined
`Add→Sub` **and** `Add→Mult` repair.

The suite also verifies the unseen independent holdout can refute a
public-passing hypothesis, ambiguous goals abstain, invalid paths/imports
are rejected without running arbitrary source, and the planner's
`safe_fixture` path cannot read the hidden case file. A real
`python -m cognition_agent_os.cli` subprocess seeds, plans, audits
and reviews a candidate. Under existing host tick:
- default does not stage, while explicit opt-in processes the task;
- write revocation prevents lab effects;
- verified artifact tampering invalidates success and trips the
  repair-lab circuit before accepting further same-family effects;
- changing a source after the first holdout check but before approval
  prevents a durable acceptance receipt.

The original Linux full regression, Windows full regression and native
Windows Task Scheduler acceptance jobs remain required. The external
public GitHub source smoke is optionally skipped and cannot be counted
as new live integration.

## What is not solved

The two source stages and allowable expression grammar are still fixed.
No novel unknown Python API or arbitrary multi-module algorithm can yet
be generated. No independently managed human domain-gold validator,
owner-controlled OS isolation, local model quality, user-PC deployment,
production file writes or real-world business outcome is proven.
A public CI test suite proves **mechanical scope**, not open-world
general intelligence. The approved release authority remains separate;
all changes are confined to cumulative Draft PR #12, unmerged.
