# Proactive risk review: local controller ACTIVE admission and liveness

Status: **DRAFT EXPERIMENT; NOT a production authorization or product release**.

## Why this work was selected

The previous 443-test green CI established mechanics for the opt-in JSON/CSV
controller but did not actively try to modify an admitted ACTIVE root or
simulate stalled task age. Three prospective mutations failed against PR #19:
changing the registered owner-target string, changing its first method's
desired value, and advancing elapsed runtime beyond 24 hours. That is
direct evidence of test/implementation omissions.

These are only three known classes. The engineering system must identify
further classes without relying on user prompts.

## Original authority and independent responsibility

- The existing task/grant ledger is the **sole local dispatch authority**;
  the registered control contract is a bounded candidate, not a grant.
- At registration, in the same SQLite transaction, save the canonical
  contract SHA256 and exact goal/grant revisions, root ID, created timestamp,
  two-method count and 24-hour deadline in a dedicated REGISTERED event.
  Before *every* controller admission or observation, an independently
  implemented verifier cross-checks original registration evidence. A
  changed method, goal, or event is not trusted.
- The default conformance scanner also checks ACTIVE roots, including when
  local control is disabled. A contradiction triggers the existing quarantine
  mechanism with dependent-task containment.
- A 24-hour total wall-clock budget, alongside the original two-method
  attempt bound, prevents unlimited waiting across process restarts.
  Timeout and failed control fences outstanding PENDING/RUNNING children in
  the same transaction, so expired children cannot later be claimed.
- No test or checker may mark `business_outcome_verified=true`,
  imply owner approval or grant remote writes.

## Failure probes and oracle distinctions

**Before-fix tests:** mutate `tasks.source_spec.target`; mutate
`tasks.source_spec.alternatives[0]`; advance clock >24 h. All must fail
the *old* implementation (as proved by GitHub CI).
  
**After-fix tests:** execute those mutations against the new admission
gate, independently scan ACTIVE roots before the controller is enabled,
forge a REGISTERED event digest, invoke the control transition directly,
and confirm a pending child is atomically fenced after deadline.

**Evaluator itself:** A stored SHA256 in the same SQLite file is NOT a
trusted signature or off-ledger witness. It detects one-sided corruption,
not a database administrator modifying BOTH the task and its event. True
adversarial integrity needs a different trust principal, separate signing
keys and independently persisted/outside-the-ledger hash evidence.

## Proactively identified residual risks (not accepted)

- **High:** A forged privileged SQLite writer can fabricate matching task
  and event; independent external signature/revocation is not yet available.
- **High:** Mixed workflow capability approvals do not follow from identical
  output records; no production effect is authorized.
- **High:** COMPLETE product goal/requirements trace across chat, knowledge
  library, code and original owner consent is not proven.
- **Medium:** Wall-clock rollback may prolong the local deadline. Original
  timestamp is immutable relative to the ledger receipt but wall-clock
  trust is not anchored outside this process.
- **Medium:** Process crash between external effects and acknowledgment is
  outside this experiment. Worker uses only bounded local candidate files.
- **Medium:** Concurrently replacing fixture file bytes remains a filesystem
  TOCTOU consideration; source hashes are rechecked at admission, but no
  general file locking or immutable file-descriptor snapshot is implemented.
- **Medium:** Full ACTIVE state corruption beyond contract/event metadata,
  e.g. adversarial modification of the entire authoritative SQLite file,
  needs external authority and stronger recovery.
- **Medium:** Held-out novel domains and actual unattended user machine
  operation remain unvalidated.

**Release disposition remains NOT_READY.** No merge, production deployment,
branch promotion or external authority granted by these experiments.
