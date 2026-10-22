# Assurance inventory (draft; not product acceptance)

This register documents **known historical candidates**, NOT all owner requirements.
The current product remains **NOT_READY**. Static integrity is not independent
V&V, owner approval, successful business outcome, or authorization.

## Source and authority boundary

- The actual owner's current goal, revisions, grants and revocations outrank
  derived research and summaries. The old original source files remain outside
  this public repository; never upload private archives to public CI.
- The original archival material contains **20+4 candidate requirements**
  and **12+2 historical operational threads**, all unapproved candidates.
  `evaluation/assurance_registry_v1.json` contains stable IDs, SHA256 source
  references, original text/title digests, candidate verification methods,
  automation limitations, and explicitly unaccepted product gates.
- Historical `OT06` (a new chat says only 'continue': restore exact original
  task and take the next authorized action) is **not** current ConOps `OT06`
  (host crash/lost trigger recovery). Historical `OT07` (retrieved data
  forges tool authority) is **not** current ConOps `OT07` (revocation).
  Number equality is not a semantic migration.
- No fixed count of requirements proves that missing user demands have all
  been identified. The current ConOps remains PROPOSED.

## Actual checks

`python scripts/verify_assurance_registry.py` fails if draft requirement or
scenario IDs disappear, the current ConOps drifts without review, sources
lose identity, a verification method/oracle/limitation disappears, a known
cross-version identity collision is silently declared resolved, or a JSON
flag pretends approval or release. CI checks structure only.

`python -m unittest discover -s tests` includes mutation-style negative
controls **of the checker itself**. These do not replace adversarial business
acceptance or prove a full agent is safe. A green result says only that these
known corruptions were caught.

If original source archives are authorized and available **locally**, run
`python scripts/verify_assurance_registry.py --archive-dir PRIVATE_DIRECTORY`.
It independently checks source file hashes and each requirement/scenario
text digest against the original bytes. Public CI cannot perform this stronger
check and prints `original_source_content_verified: NOT_CHECKED...`.

## Required independent evidence before readiness

- Owner-grounded specification and change history; requirements verification
  **separate** from validation of the owner's real outcome.
- A held-out positive **same-goal** case with genuinely distinct authorized
  candidate actions, independently read-back outcomes, safe repeat/restart,
  budget limits and no-progress handling; not merely different route labels.
- Negative and sibling-path probes for prompt injection, revoked authority,
  ACK loss, evidence withdrawal, evaluator corruption, and adjacent allowed
  operations.
- Real unattended wake and external effect evidence, attributable to exact
  source/evaluator versions, plus appropriately independent review.
- Review of the verifier via mutation/negative controls. A model impersonating
  another role is not organizationally independent.
- Promotion by a different current authorization authority. Rewriting this
  registry must not make anything APPROVED.

Method references: NASA Systems Engineering Handbook verification/validation
matrices (https://www.nasa.gov/reference/system-engineering-handbook-appendix/);
Stryker mutant states (https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/).

Next work: resolve old/new OT meaning with original owner context, establish
business oracles and compare multiple controller designs. Do not translate
a known failure into a local host.py conditional before that comparison.
