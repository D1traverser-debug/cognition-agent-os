# P8 — evidence-driven record reconciliation (bounded cognitive transfer)

## Purpose: test unanticipated concrete inputs, not memorize demonstration answers

P7 handled explicitly known JSON-key/CSV-column repair rules. P8 adds a
**different business outcome**: given two bounded local CSV sources and
the high-level objective `identify_discrepancies`, determine whether there is
sufficient evidence for an unambiguous record association, enumerate *actual*
missing/unexpected/mismatched records, and issue an independently tested
report. No known row identifiers, expected discrepancy lists, hardcoded
invoice numbers or fixed sample verdicts are supplied at intake.

It can operate on two families using the same adapter: IC regression outputs
(`test_id/status/cycles`) and invoice/finance reconciliation
(`invoice_id/amount/currency`). Rows may be shuffled, changed, missing or
unexpected. Randomized test instances use inputs not manually written as
specific expected answers.

## Bounded goal contract and steps

```json
{
  "kind": "record_reconciliation",
  "reference": "expected.csv",
  "observed": "actual.csv",
  "objective": "identify_discrepancies"
}
```

The task agent's scope is two named, local, read-only sources in the existing
fixture root. It does not scan the whole host, access private documents, run
shell commands, send source data to remote AI or alter originals.

The planner dynamically:
1. Reads both source bytes and their CSV schemas under fixed resource caps;
2. Hypothesizes join keys from every shared column; ranks competing keys
   using observed uniqueness, identifier overlap and a disclosed fallible
   identifier-name prior;
3. **Abstains** if no plausible unambiguous key can be inferred, rather than
   inventing a match;
4. Joins records and enumerates missing/extra IDs, mismatched common fields,
   and columns that appear in only one source;
5. Submits every proposed difference to an **independently implemented SQL
   oracle** that reparses original CSV sources, runs SQLite joins and
   independently reconstructs the complete difference set;
6. Records a versioned source-linked immutable local report
   `NEEDS_REVIEW` if discrepancies exist, or a mechanically scoped
   `VERIFIED / RECORD_SETS_CONSISTENT` if record sets match. A read-only
   `reconciliation-audit` operation can re-open current originals, artifact
   and authoritative task after the original worker exited.

This is genuine *data-dependent selection and comparison*, but it is a
bounded algorithmic workflow, not open-ended LLM cognition. The SQL oracle
proves agreement with an independently coded relational computation, **not**
that an inferred join key is the one an accountant, engineer or upstream
specification would endorse.

## Explicit local CLI

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures seed-reconciliation --reference expected.csv --observed actual.csv
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures worker-once
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures reconciliation-audit --task-id REPORTED_TASK_ID
```

The existing opt-in external Windows host can also process due P8 tasks;
this change neither installs nor proves it ran. All reports are
`PROPOSAL_NOT_APPROVED`. No corrections to invoice amounts, IC results or
provider records are applied.

## Acceptance and anti-overclaim

Verification includes generated unfamiliar records from two domains, order
changes, add/delete/mutate events, comparable sources, two plausible
relationship keys (fail closed), malformed CSV, duplicate identifiers, source
and artifact tampering, mismatched independent checker, revoked authority,
and CLI/host integration.

Security and quality limitations:
- Unique value overlap is not proof of semantic identity. Competing key
  hypotheses are recorded; high ambiguity ends UNKNOWN and requires new
  external evidence. Key inference false positives remain possible.
- CSV byte and row counts are finite; no massive data sets or arbitrary
  relational operations.
- A clean mechanical comparison does not establish correct financial
  accounting or correct hardware behavior without independently defined
  domain expectations.
- Real model inference, autonomous handling of arbitrary natural language,
  unknown problem discovery, self-governance, systemic code patching,
  production effects and unattended Windows execution remain open.
- No paid model tokens, credit-trial services or automatic model downloads.

## P8 key-substitution defect found and fixed in CI

The first P8 CI ran 131 cases and found an unsafe inference: a duplicate
explicit identifier (e.g., `invoice_id`) could cause the planner to fall back
to a coincidentally unique value such as `amount`, manufacturing a plausible
join. Both independently coded paths were modified: **if any explicitly
identity-named shared column is invalid or non-overlapping, refuse all
weaker fallback keys**. Candidate planner and independent SQL oracle must
both agree on `INSUFFICIENT_KEY_EVIDENCE` in that case. Regression
`test_duplicate_stable_id_never_falls_back_to_unique_amount` now exercises
the failure directly. A later GitHub Actions run `39427596976` passed
**132 Python tests**.

This still does not prove the correctness of ID-like name inference for
unknown schemas; where the evidence is semantically unclear, abstention or
owner-supplied independent relationship semantics are required.
