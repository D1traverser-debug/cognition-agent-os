# P9 — typed goal decomposition, reviewer-pinned relationship contracts

## Scope and outcome

P9 unifies intake of two **typed outcome objectives**, without claiming a
free-form general-purpose autonomous Agent:

- `ensure_structure` with one read-only local JSON file and explicit field
  constraints.
- `compare_records` with two read-only local CSV record sources, from
  dynamic IC regression or finance-like records.

The module `intent_planner.py` compiles these into a bounded five-stage
ordered plan: **OBSERVE → CHALLENGE → PLAN → CHECK → COMMIT**. Steps point
only to code-registered, authorized capabilities. No text from an input
source or a proposed plan becomes executable code, a shell call or a new
privilege. An unsupported objective, unregistered resource, duplicate role,
malformed constraint, additional authority claim or recursive intent fails
closed.

`intent_runtime.py` uses the **existing single SQLite tasks/events and
authority records**. A claimed intent rechecks its grant and goal revision
under a write lock; it atomically transitions to `DECOMPOSED` and creates
exactly one child with the compiled trusted capability's typed source spec.
A separate read-only `intent-audit` recomputes the plan and compares the
parent, one child, and the durable event. The next worker/host iteration
uses its existing P5/P8 evidence gathering, domain checks and sandbox
path. This is deterministic, bounded capability composition — **not**
natural-language goal understanding, free-form causal cognition or automatic
real-world domain acceptance.

### Example typed intent

```json
{
  "kind":"goal_intent",
  "objective":"ensure_structure",
  "resources":[{"role":"input","path":"settings.json"}],
  "requirements":[{"field":"owner","equals":"ops"}]
}
```

Use `seed-intent --spec goal-intent.json`, then `host-tick
--auto-stage-goals` with the existing `--db`, `--workspace` and
`--fixtures` arguments; `intent-audit --task-id PARENT_ID` separately
verifies the event/plan/child graph without modifying the database.

## Provenance gap in P8 and P9's conservative option

P8 inferred a join key from names, uniqueness and overlap. Even when
both P8 and its independently coded SQL oracle agree on calculations,
**they may share a mistaken key assumption**. Identical numbers in a
ledger do not establish that two invoices are the same invoice.

P9 optionally accepts an externally reviewed, **out-of-band SHA-256 pinned**
relationship manifest. The user/reviewer must supply its exact expected digest
through the CLI; the program never manufactures a trust anchor by hashing
an arbitrary user-supplied file and treating that as independent approval.

```json
{
  "schema_version": 1,
  "contract_kind": "record_relationship",
  "reference": "expect.csv",
  "observed": "actual.csv",
  "join_key": "invoice_id",
  "justification": "Reviewer-approved matching identity for the two source systems."
}
```

Store the manifest as a bounded regular local source file, e.g.
`relationship.json`, inside the approved fixtures directory and keep
the digest recorded separately by an authorized reviewer. It must match
exact source names, declared key, version, schema and exact raw-byte SHA256.
Run:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-reconciliation --reference expect.csv --observed actual.csv --relationship-contract relationship.json --expected-contract-sha256 REVIEWER_PINNED_64_HEX_SHA
```

The planner then tests only the pinned key and the separately implemented
SQL oracle independently enforces that choice when recomputing source joins.
No weaker fallback to another uniquely-valued business field is permitted.
A missing key, duplicate key, lack of identity overlap, manifest mutation,
bad digest or scope mismatch results in UNKNOWN/UNVERIFIABLE. Post-write
`reconciliation-audit` reopens the contract source as well as original
records and the authoritative report.

**Fundamental limitation:** no authenticated reviewer-signature or
professionally validated semantics is embedded. Knowing the file's SHA256
does not authenticate who wrote it. An Agent permitted to write both manifest
and expected digest can bypass this origin assumption, so these MUST be
independently controlled in a real installation. `REPORT_MECHANICALLY_VERIFIED`
means the computation conformed to the caller-pinned declaration,
**not that external business semantics were independently proven**.

## Testing and next acceptance

Unit and CLI/integration checks cover both goal families; unknown/unsafe
intent rejection; no recursive intent; grant/revision fencing; one atomic
child and plan event; forged child failure; ambiguous simultaneous
identifiers with a pinned explicit relationship; audit-time digest change;
malformed/out-of-scope or absent relationship; no explicit-key fallback; and
mechanical SQL verification.

Real independent acceptance still requires a trusted human/domain system
to issue the semantics outside the proposing Agent's permissions, plus
unseen genuine records, actual local model/Windows host execution where
applicable and a full business-result readback. The project still has a
stack of unmerged Draft PRs; do not assert that these changes run in
`main` or on the user's computer. No paid AI API, finite model credits,
trial services or model auto-download are used.

## Composed goal + reviewer-pinned relationship: actual P9 end-to-end route

A typed `compare_records` intent can now carry the same required
caller-pinned manifest binding to the approved reconciliation capability,
without bypassing the generic goal decomposition or its audit:

```json
{
  "kind": "goal_intent",
  "objective": "compare_records",
  "resources": [
    {"role": "reference", "path": "expect.csv"},
    {"role": "observed", "path": "actual.csv"}
  ],
  "relationship_contract": {
    "path": "relationship.json",
    "expected_sha256": "THE_INDEPENDENTLY_PINNED_64_HEX_DIGEST"
  }
}
```

`seed-intent` now validates the manifest bytes immediately when an intent
carries such a binding. Its child task inherits the exact pinned spec and
the existing worker/SQL readback repeats the check before a report can be
considered mechanically valid. Test
`test_composed_comparison_uses_reviewer_pinned_key_and_sql` verifies
parent decomposition → child execution → SQL report readback.

The staged task remains local-only; no emitted step may write input CSV
files, grant authority, run shell commands or merge GitHub PRs.

### P9 functional evidence

Initial CI `39429762735` ran 151 tests but encountered a single
validation-error-type leak from `validate_goal` into the typed compiler
(150 passed, one error). It was corrected by normalizing the lower-level
validation error to `IntentError`, with an additional negative test.

Functional CI `39430380039`: **153/153 standard-library unittest
cases passed**, including the unified typed-intent + pinned-contract
end-to-end route. `live_public_source` remained SKIPPED.
This is a code and isolated data-flow observation; real reviewer
authorization and a physical unattended Windows host have not been observed.
