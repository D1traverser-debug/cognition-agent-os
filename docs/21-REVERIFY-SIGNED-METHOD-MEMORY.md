# P10.9 — Historical signed feedback must prove itself again

## Failure of the previous authority boundary

P10.8 verified an externally signed reviewer verdict on import, then
stored only its hashes and a verdict in `signed_outcome_feedback`.
The next `pure_code_repair` task used that **mutable SQLite row** to
reject the same operator hypothesis, without re-verifying the signature.
An actor who modified that SQLite row could therefore influence the
Agent's future choices while claiming an independent review that never
happened. The existing test for forged `events` did not cover forgery
of the actual decision table.

P10.9 repairs this trust gap at the **decision-use** boundary. When a
future repair would be blocked by historical `DOMAIN_REJECTED`, the
Agent must recheck actual retained signed statement bytes, detached
OpenSSH signature bytes, independently prebound public trust root,
original task/revision and immutable code proposal. No signer's private
key, hidden test labels or holdout contents are passed to the proposer.

## Connected implementation, not another authority

`signed_feedback.py` stores the raw (bounded) signed statement and
detached signature alongside existing provenance digests at authenticated
import time. When consulting historical negative experience,
`previously_signed_rejected` independently:

1. Checks the stored byte lengths and SHA256 fingerprints rather than
   trusting stored hash strings.
2. Strictly parses the exact signed statement and enforces its signed
   expiry, outcome, task, reviewer and candidate.
3. Re-reads the owner's prebound public signer file and checks its
   independently pinned digest. Uses local `ssh-keygen -Y verify`,
   namespace `cognition-agent-os-outcome-v1`, on the historical exact
   bytes; there is no shell command interpolation or cloud request.
4. Looks up the original task and compares signed goal/grant/source
   specification/artifact digests and the holdout digest.
5. Reopens the original immutable candidate proposal file and checks
   its actual file hash, original-source SHA, public-suite SHA,
   holdout scope and exact operator transformation.

The history query is bounded to four matching records; unexpectedly
many matches are unverified instead of silently choosing one. It does
not re-open sealed holdout JSON or return held-out labels to the code
proposer. When proof is missing, forged, expired, or contradictory,
the task returns `UNKNOWN / SIGNED_FEEDBACK_PROOF_UNVERIFIABLE`
instead of pretending either that external rejection was proven or
that the old history is certainly safe to ignore. The verification
runs both before proposal admission and again under SQLite's
existing write lock to prevent a concurrent signed outcome import
between decision and immutable file commit.

A genuine original signature is needed before the signed rejection
may influence a new task. An independently signed `DOMAIN_ACCEPTED`
still never grants permission to patch production code.

## Legacy P10.8 database upgrade without trust laundering

Previous `signed_outcome_feedback` schema had no signed byte columns,
only digests. Such legacy records are NOT accepted as signed negative
proof. An explicit original-signer re-import with P10.8's existing
trust-root and full independent artifact/holdout validation can add
those BLOB columns, compare all old provenance fields, and backfill
**only the exact independently verified bytes**. The operation appends
`SIGNED_FEEDBACK_CRYPTO_BACKFILLED`. A conflicting historical claim
is never silently rewritten. The migration occurs inside the same
existing SQLite transaction and does not create another state ledger.

## Evidence and scope

`tests/test_outcome_attestation.py` extends real ephemeral OpenSSH
Ed25519 experiments on Linux and Windows:
- genuine signed rejection still blocks a later identical method;
- changing raw detached signature fails closed;
- also changing its matching DB hash does not make a forged signature
  valid;
- laundering the historic row's public-input digest to a changed
  evidence version is refused;
- changed external public signer root causes abstention;
- the signed-memory lookup never reads hidden/gold cases;
- old P10.8 hash-only rows require explicit authenticated re-import
  before influencing new decisions.

The Linux and Windows complete regression jobs and the real Windows
Task Scheduler host smoke remain mandatory in the cumulative Draft
PR #12. Live public GitHub-source smoke may be skipped.

### Remaining independent-trust limits

This still does NOT cryptographically anchor the entire SQLite ledger
outside the Agent. A malicious actor with the authority to change the
owner trust table, the external trust root and the owner's OS identity
could substitute their own policy and authentically sign a fake
business verdict. Such a compromise cannot be ruled out without real
owner-controlled OS ACL separation, external reviewer identity and
an independent audit root. Original post-signature business truth is
not mathematically proven. Test keys are temporary, NOT a human
reviewer. The Agent still does not autonomously solve arbitrary
multi-file tasks or edit production code. No owner Windows deployment,
new paid tokens or expiring/free-credit API usage occurred.

The important, narrow claim is that an ordinary forged **feedback
database row alone** cannot silently become a trusted past reviewer
decision on future tasks.
