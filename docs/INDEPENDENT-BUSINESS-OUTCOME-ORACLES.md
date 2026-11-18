# CAOS S1 — Independent Business Outcome Oracles

Status: SYNTHETIC CALIBRATION ONLY. REAL BUSINESS SIGN-OFF REMAINS OPEN.

This evaluation layer is separate from the CAOS planner, Host, SQLite ledger,
model output, and runtime status. It reads pinned owner contracts, immutable
source bytes, candidate bytes, and a separately supplied consumer readback.
It never imports or trusts a planner success claim.

## Supported calibration endpoints

### Broadcast / voice-script delivery

The voice oracle derives the latest revision for each item and field from the
pinned source. It checks required item presence and order, exact facts, latest
source IDs, omitted facts, superseded values, placeholders, and minimum script
content. Read-aloud usability requires a separate consumer assessment bound to
the exact artifact digest.

The deterministic checks do not claim to understand style or guarantee
broadcast quality. Read-aloud usability remains a consumer-side assessment.

### IC / DV regression triage

The DV oracle pins the original raw log and an independent simulator-state
snapshot. It parses test ID, seed, scoreboard mismatches, timeout and retry
events, process exit code, and first-error time and line. The current parser
accepts a bounded normalized event grammar; it is not a generic VCS/Questa/
Xcelium UVM transcript parser. A raw `UVM_ERROR` or `UVM_FATAL` line is
rejected as INSUFFICIENT_EVIDENCE until a separately tested normalizer maps
it into the canonical event format. It must never be silently ignored as a
clean run. The independent simulator state must agree with the raw log before
a candidate can be graded.

A process exit code of zero is not a passing regression when the scoreboard
records a mismatch. The candidate must report the observed failure class and
first-error location. A separate consumer readback must confirm that a
successor can open and reproduce the triage.

## Verdict contract

- PASS: pinned source, candidate content, and artifact-bound consumer readback
  satisfy the synthetic contract.
- FAIL: readable evidence contradicts the owner contract, or the consumer
  explicitly rejects the deliverable / confirms non-delivery.
- INSUFFICIENT_EVIDENCE: evidence is missing, unreadable, stale, conflicting,
  unbound, or structurally ambiguous.

Every result is marked SYNTHETIC_CALIBRATION_ONLY. It always reports
business_outcome_verified=false, real_external_outcome_verified=false, and
authorizes_mutation=false. The synthetic consumer receipt is not
cryptographically authenticated. It is not a real editor, engineer, customer,
or downstream provider sign-off.

## Calibration matrix

Both domains have tests for correct content, wrong content, a success-only
receipt, and an unreadable artifact. Additional negative tests cover stale
facts, source drift, explicit non-delivery, wrong regression seed, malformed
critical log events, false PASS from exit-code zero, and disagreement between
the raw log and independent simulator state.

The R17 / seed-17 fixture reuses the handover's known exit-code, mismatch, and
80 ns first-error facts. Its timeout/retry counts are explicit synthetic
fixture values, not claims about the historical raw run. A separate R18
fixture exercises a timeout and retry.

Run from the repository root:
python -m unittest discover -s tests -p 'test_business_outcome_oracle.py' -v

## What this does not prove

- No real customer document, production regression, or client engineering
  artifact was used.
- No real presenter, editor, verification engineer, or downstream business
  consumer has signed off.
- The synthetic readback is not a trusted external identity or provider
  receipt.
- This does not prove native ChatGPT Skill selection, unfamiliar-task method
  discovery, cross-domain transfer, or complete product readiness.
- A passing oracle does not permit publication, customer-file modification,
  simulator changes, or any other external effect.

## Next acceptance boundary

Before real business acceptance can close, obtain an explicitly approved,
sanitized holdout or public sample and identify the actual consumer endpoint.
Capture its independent readback: opened artifact digest, delivery state, and
domain-specific usability or reproducibility result. Keep original source and
holdout sealed from the executor. If no independent consumer can be observed,
retain REAL_BUSINESS_SIGN_OFF as OPEN; do not promote synthetic calibration to
a product claim.
