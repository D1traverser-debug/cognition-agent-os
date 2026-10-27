# P10.8 — externally signed outcomes change the next method decision

## The missing closure

P10.7 could verify an external Ed25519/OpenSSH-signed outcome but the
read-only result never changed future behavior. A reject verdict was just
another report, while the deterministic repair worker could propose the
exact rejected operator mutation on another identical task.

P10.8 closes that narrow loop **without creating another agent or task
authority**. It adds a write-once owner-selected review trust binding and
a transactional signed-outcome receipt inside the existing SQLite task
ledger. A previously authenticated `DOMAIN_REJECTED` becomes a narrowly
scoped **negative method constraint** for future P10.4 pure-function
repairs. `DOMAIN_ACCEPTED` becomes an auditable historical observation,
but does not advance task state, apply code, reset an integrity circuit,
or authorize any deployment.

This is a controlled behavioral adaptation for one testable repair family,
not general autonomous understanding or a validated business outcome.

## Trust policy before any feedback

Owner policy enrollment is a separate explicit command. A caller must
supply a full externally pinned SHA-256 of a public `allowed_signers`
file and a reviewer principal. The file must live outside the Agent's
workspace and fixtures; the SQLite authority must already exist and
permit writes. The policy is **write-once** in the same ledger and is
not silently replaced on later calls.

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures attestation-bind-trust --allowed-signers C:\reviewer\allowed_signers --expected-allowed-sha256 OPERATOR_PINNED_PUBLIC_ROOT_DIGEST --principal reviewer@example.com
```

No host tick or autonomous worker invokes enrollment. It uses a
read-only database check before any writable SQLite connection so that
an empty/corrupt SQLite path is not altered by a failed enrollment.

**Critical trust caveat:** the ledger alone cannot authenticate that a
human owner executed this command. A process with control of the
database, write grant and OS credential could enroll or tamper with
policy. Genuine independent owner trust demands OS filesystem ACLs,
different login/security identities and external audit/control of the
trusted public root. These controls have NOT been deployed on the user's
Windows 11 host. Test harness enrollment is NOT a human review.

## Import a genuinely signed verdict

A real reviewer controls the private key outside the Agent workspace.
Following the P10.7 `attestation-subject` export, the reviewer changes
`REVIEW_REQUIRED` to `DOMAIN_ACCEPTED` or `DOMAIN_REJECTED`,
supplies a specific rationale, and independently signs the exact statement.
The Agent receives only signed bytes, detached signature, external public
signer file, independently pinned fingerprint and principal.

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures attestation-record --statement C:\reviewer\outcome.json --signature C:\reviewer\outcome.json.sig --allowed-signers C:\reviewer\allowed_signers --expected-allowed-sha256 OPERATOR_PINNED_PUBLIC_ROOT_DIGEST --principal reviewer@example.com
```

`signed_feedback.record_signed_feedback` calls the existing independent
OpenSSH signature verifier and exact P10.4 source/artifact/holdout lab
auditor **before and again under BEGIN IMMEDIATE**. The claimed reviewer
identity, public root fingerprint and exact resolved public key path must
match the previously bound owner policy. Current goal/grant versions
are checked. Only then does one `signed_outcome_feedback` row and one
`EXTERNAL_SIGNED_OUTCOME_RECORDED` event commit together. Same signed
input is idempotent; conflicting verdicts/reviews for the same task
cannot overwrite the original evidence. The original source file and
candidate patch remain unchanged.

Only for `DOMAIN_REJECTED`, subsequent `pure_code_repair` planning
compares all of: original-source SHA, visible case file SHA, holdout
digest, proposed candidate SHA, and precise old→new operator mechanism.
Identical evidence is refused with
`SIGNED_REVIEW_PREVIOUSLY_REJECTED` before writing a new patch proposal.
It also rechecks the constraint in the SQLite finalization write lock,
fencing a concurrent external rejection. New public evidence or a new
independent holdout digest is a new hypothesis and may proceed.

A free-form `EXTERNAL_SIGNED_OUTCOME_RECORDED` event injected without
the signed-claim import does **not** produce this outcome. A positive
signature does **not** remove a rejected method or confer release rights.

## Tests and boundaries

`tests/test_outcome_attestation.py` uses ephemeral **real Ed25519**
OpenSSH signing on both Linux and Windows to exercise accept/reject,
cross-task negative learning, exact-scope exceptions, no lab write for
repeat rejected methods, duplicate/conflicting signed records, false
self-authored event injection, altered signer root, manual grant
revocation, CLI import and owner-policy initialization failures.

The first full extension run `39457977932` ran 222 tests but failed two
cases because a structured refusal branch passed the same `reason`
parameter twice. Fixed as an actual error-boundary defect. A subsequent
225-test run `39458516905` found that `connect()` mutated an empty
SQLite file *before* trust initialization could be rejected; now a
strictly read-only check guards the binding path. Latest complete
CI status belongs to the final branch head, not these earlier runs.

### Deliberately NOT claimed

- Authenticated real-world identity or correctness of the reviewer.
- An actual external business goal met by a deployed Agent.
- Protection from a malicious process with direct SQLite write access,
  full host filesystem control or the owner's OS identity.
- Cryptographically revalidating every historical signed-feedback row
  against an immutable external audit log after a trusted DB itself is
  compromised. Historical receipts rely on the same trusted ledger.
- Autonomous recovery of signers, self-enrollment of trust roots,
  automatic code promotion, unrestricted Python execution or
  production mutation.
- Actual use of paid cloud AI tokens, expiring trial AI credits or
  changes to the user's Windows PC.

Only the cumulative **Draft PR #12** is modified, with no merge to
`main`. True external outcome and trust enforcement remain release
blockers regardless of regression counts.
