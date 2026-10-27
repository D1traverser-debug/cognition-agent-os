# PR #33 — One shared outcome across different local attempts

**Status:** bounded, opt-in local goal postcondition. Does **not** verify any real-world business outcome, approve a production mutation, automate method invention, or replace the existing SQLite authority/Host/Worker.

## Problem in the previously running implementation

The `outcome_feedback` controller already had a durable, two-attempt local feedback loop and legitimately proved **independently checked local evidence**. It admitted two registered methods, detected a negative first outcome, and scheduled the second through the original SQLite ledger.

However, its v1 success condition was method-relative: a structurally valid JSON proposal or independently checked CSV discrepancy report could each satisfy the loose `INDEPENDENT_LOCAL_EVIDENCE` predicate. It did **not** prove that either addressed the **same required target record**. Treating v1 as goal completion would be a type error.

Rather than add yet another controller or a cosmetic governance gate, the existing controller now supports an **optional v2 goal postcondition**. Old v1 receipts and task contracts are still valid, but v1 does not claim more than evidence existence.

## Concrete acceptance contract

For v2 the caller pins exactly one `acceptance` in the original immutable controller task:

```json
{
  "goal_id": "local-shared-record",
  "objective": "Candidate exact record id=A with owner=ops",
  "acceptance": {
    "kind": "exact_record_postcondition",
    "identity_fields": ["id"],
    "target_record": {"id": "A", "owner": "ops"}
  },
  "alternatives": [
    {"kind": "goal_case", "goal_type": "json_keys",
     "input": "first.json", "desired": {"owner": "ops"}},
    {"kind": "goal_case", "goal_type": "csv_columns",
     "input": "second.csv", "desired": {"owner": "ops"}}
  ]
}
```

Example read-only source data:
- `first.json`: `{"id":"A","owner":"wrong"}` — cannot satisfy append-only preservation and the shared target.
- `second.csv`: header `id`, one row `A` — allows the alternate non-destructive candidate `id,owner\nA,ops\n`.

The controller rejects v2 contracts with different record identities, incompatible declared desired values, unsupported methods, or two identical method families. Source bytes for both alternatives are hashed and pinned at registration. These are **owner-approved alternatives**, not model-discovered plans.

To use the existing CLI against an already initialized explicit-prototype ledger:

```bash
cognition-os --db local.sqlite --workspace ./work --fixtures ./sources \
  seed-evidence-feedback --spec ./shared-goal.json

cognition-os --db local.sqlite --workspace ./work --fixtures ./sources \
  host-tick --auto-local-goal-control --max-jobs 4
```

Invoke Host ticks again as needed. Each tick is a separate process; nothing runs in the background.

## Distinct outcomes and failure rules

The first method's candidate must independently pass its own source/receipt/constraint audit **and** the fixed target equality check. Merely generating a valid proposal is insufficient. If an independent assessor proves either a preservation conflict or `TARGET_NOT_MET`, the controller atomically admits a *different* preapproved capability for the **next** original Host tick.

The second method is also judged against the **same original target**. If it produces extra fields or a different value, the controller reaches `EXHAUSTED_SAFE_ALTERNATIVES`, not success. Source changes, forged candidate bytes, unsupported source/identity, altered authority and inconclusive checks stop admission; they do not trigger an unsafe fallback.

A successful v2 root uses the existing `FEEDBACK_EVIDENCE_READY` state with a distinct receipt reason `SHARED_LOCAL_TARGET_MET`. The read-only root verifier replays the original task lineage and independent candidate/target checks; the receipt and postcondition are not inferred from the planner's self-report.

**Meaning:** the *local reviewable candidate* meets a precise record-level postcondition. Both `business_outcome_verified` and `semantic_outcome_verified` remain **false**. This does NOT prove a production file was changed or a user's original broad goal achieved; no external effect is permitted.

## Actual evaluation, anti-overclaim and next layer

Tests in `tests/test_shared_goal_postcondition.py` exercise:
- Real first preservation failure then an authorized **different task** executing on the next Host tick;
- First proposal passes its own checks but **fails the common target**, then falls back;
- Second method still fails shared target → the controller stops, never falsely accepts;
- Wrong record identity is rejected at admission;
- Source drift, authority revocation and source-specific audit uncertainty prevent promotion;
- A no-op already satisfying the exact target terminates after one attempt;
- Three independent command-line processes recover the same durable ledger lineage;
- v1 evidence-only task contracts remain separate.

**Not proven:** generic natural-language method discovery, unsupervised causal root-cause analysis, learned knowledge transfer, unseen-domain semantic verification, production deployment, owner/business-result acceptance. Those remain separate product outcomes under the original G1–G8, R01–R24 and OT01–OT14 source requirements. The original private CONOPS files are not copied into this public repository.

**Next legitimate step** is an evaluator-controlled external-effect sandbox with a fixed precommitted observable postcondition, where the same goal is attempted using two *functionally different* authorized approaches; record exact state change, permissions, cost and human corrections. Do not reuse v2's 'candidate matched' status as proof of an external action.
