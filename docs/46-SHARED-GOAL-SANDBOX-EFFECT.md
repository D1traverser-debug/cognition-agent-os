# G1/G8 vertical integration: same goal, real sandbox effect, independent readback

**Status:** bounded integration candidate on PR #36. This is not an autonomous general system, an approved product release, an independent business outcome, or a permission to mutate any source/production/external provider.

## First principles and scope

Requirement provenance, **not current frozen authority**: historical ConOps `CONOPS_OPERATING_THREADS_AND_TRACE(1).json` (G1–G8, OT01–OT12) and `CONOPS_K04_Q05_EXTENSION.json` (OT13–OT14, R21–R24) record early proposed scenarios. Later user corrections, independently tested design changes, rejected alternatives and actual current code must be reconciled before planning; these historical labels do not exhaust the system mission. The six current release gates are separate technical acceptance criteria, not the ConOps G1–G8 namespace. A mechanical candidate, hash, status, CI pass or LLM declaration cannot establish owner-meaningful business results.

There are three meaningful solutions to this gap. (A) add another controller/host: rejected because two lifecycles and grants would diverge. (B) mark PR #33's v2 candidate as executed: rejected because it creates a false result. (C) extend the existing feedback adapter with a frozen result-scope contract and require the original Host+Worker+stager+independent readback: implemented for **local isolated files only**. No arbitrary tools, cloud bill, auto-deployment or external side effect is admitted.

## Actual integrated path

1. Explicitly initialize existing prototype SQLite ledger; register owner-provided *one immutable shared exact-record target*, two different pinned capability families and `"execution_scope":"LOCAL_SANDBOX_POSTCONDITION"`.
2. The original `control_kernel.drive_active_controller` validates the grant and atomically admits the first preapproved task on the original `tasks` and `events` tables. This is not generic model-discovered planning.
3. `Host.run_tick` drives the original `runner.run_once`. A preservation conflict is an independently refuted candidate and can select the second preapproved method under existing attempt and source budgets.
4. The **separately required** `--auto-stage-goals` Host switch invokes the original `sandbox_effect.stage_one` executor with original source/lease/current-grant checks. It creates `workspace/sandbox/<child_id>.candidate`, records a receipt and `SANDBOX_VERIFIED`. The user source remains unchanged.
5. The v3 feedback adapter only considers `NEEDS_REVIEW` to be **waiting**; it cannot declare success based on a proposal alone. The existing independent `conformance._verify_staged` replays the original candidate, source, actual staged bytes and effect receipt. `source.safe_fixture` reopens the actual sandbox effect using the hardened file-read boundary. A separate exact-record postcondition checker compares those bytes to the **original frozen common target**.
6. Only then can the *original* feedback root reach `FEEDBACK_EVIDENCE_READY` with the version-distinguishing reason `SHARED_SANDBOX_POSTCONDITION_MET`; `business_outcome_verified=false` and `semantic_outcome_verified=false` remain mandatory. If both methods have independently proven wrong-target effects, exhaust safely; if a source/effect/receipt is missing or forged, remain inconclusive, never switch on missing evidence.
7. An originally correct source may satisfy the target with an independently checked `VERIFIED` no-op and no new effect. Revocation fences new actions. The durable ledger and unchanged CLI identity let independent host processes continue without a new prompt.

## Explicit CLI (after local `cognition-os init`)

Create read-only fixture sources `first.json` with `{"id":"A","owner":"wrong"}` and `second.csv` with `id\nA\n`, and save this intake:

```json
{
  "goal_id": "local-shared-effect",
  "objective": "Produce a local staged record A whose owner is ops",
  "execution_scope": "LOCAL_SANDBOX_POSTCONDITION",
  "acceptance": {
    "kind": "exact_record_postcondition",
    "identity_fields": ["id"],
    "target_record": {"id": "A", "owner": "ops"}
  },
  "alternatives": [
    {"kind": "goal_case", "goal_type": "json_keys", "input": "first.json", "desired": {"owner": "ops"}},
    {"kind": "goal_case", "goal_type": "csv_columns", "input": "second.csv", "desired": {"owner": "ops"}}
  ]
}
```

```sh
cognition-os --db local.sqlite --workspace ./work --fixtures ./sources init
cognition-os --db local.sqlite --workspace ./work --fixtures ./sources seed-evidence-feedback --spec ./shared-effect.json
cognition-os --db local.sqlite --workspace ./work --fixtures ./sources host-tick --auto-local-goal-control --auto-stage-goals --max-jobs 4
# Execute a second and third discrete host tick on the same database.
```

Without both explicit Host switches, no controller-selected sandbox effect is completed. No process runs in the background unless an independently configured OS scheduler invokes it.

## Independent falsification and boundaries

`tests/test_shared_posteffect_feedback.py` exercises staged bytes and DB readback, first-method conflict, first method that mechanically works but misses the common target, no-op, absence of stage permission, signed/host-independent source truth not claimed, source drift after claimed effect, forged/tampered staged file, revocation, unsupported requested effect scopes, exact old v2 behavior and three separate real CLI processes. At code SHA `962ee4e560972d3cc1f47bddf1b6986b17d2c011`, [Actions #40050033744](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40050033744) passed: Linux 552/552 and Windows 552 with 5 explicitly skipped POSIX/hostile-directory-only cases, alongside installed CLI, hosted Windows scheduler, Docker and Graphify. Later documentation commits require their *own* matching SHA checks. This is evidence for a bounded local slice, not independent business-semantic correctness.

**Still missing:** external provider adapter with stable operation IDs, explicitly scoped live provider authorization, provider readback/UNKNOWN ACK recovery, genuinely unseen natural-language method discovery and verified cross-domain learning, real user's business acceptance, and persistent owner-host installation. The ConOps G1–G8 and readiness gate remain **NOT_READY**. A correct local sandbox record is not a production write or general semantic proof.

**Continuity:** this file is a candidate-only execution record. The authoritative next step is to derive a provider-neutral effect/idempotency/readback contract (without granting provider access), then validate against a sealed evaluator-controlled external-effect sandbox and unfamiliar tasks while measuring unauthorized repeats, uncertain effects and owner correction burden. Do not silently promote this opt-in local adapter into any production or remote workflow.
