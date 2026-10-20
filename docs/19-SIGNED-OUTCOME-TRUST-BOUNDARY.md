# P10.7 — independent signed outcome boundary (not self-issued approval)

## Concrete governance gap

Earlier P10.4–P10.6 used separately implemented source/holdout oracles
and SHA-256-pinned reference inputs. That detects mechanical mistakes and
byte substitution but **does not authenticate a reviewer**: a proposer
who can replace the gold file and its expected hash may invent its own
purported independent success.

P10.7 implements the missing **external cryptographic assertion** boundary,
without allowing an Agent to give itself production permissions.

This is a **read-only opt-in verification workflow**, not a new state
authority and not an automated domain-truth claim. No paid AI tokens, model
downloads, trial credits, private key uploads, production source mutation,
or new database are required.

## Trust and signer separation

An external reviewer controls an OpenSSH private signing key. The Agent
receives only: (1) a bounded JSON statement, (2) its detached OpenSSH
signature, (3) a trust-root `allowed_signers` public key file kept **outside
agent-controlled fixtures/workspace**, and (4) the independently provided,
exact SHA-256 digest of that root, plus the expected reviewer principal.

The Agent calls the local installed **`ssh-keygen -Y verify`**
implementation with fixed namespace
`cognition-agent-os-outcome-v1` (no shell interpolation or cloud endpoint).
It also independently reopens the original SQLite task, confirms
`REPAIR_LAB_VERIFIED`, exact task ID, grant/goal revisions, source
specification digest, immutable artifact digest, candidate digest and
holdout digest, then re-runs the P10.4 source/hidden-case/staged-file
oracle. The signed record has an explicit issue/expiry window of no more
than 30 days. Expired, wrong-principal, wrong-key, wrong-task, mismatched
candidate, altered source or spoofed verdict all fail closed.

Both `DOMAIN_ACCEPTED` and `DOMAIN_REJECTED` are legitimate possible
**signed assertions**. The signature proves only that a holder of an
allowlisted key signed the exact statement; it does **not** prove the
signer's human identity, that the signer correctly inspected the business
result, or that production writes may proceed. The output always marks
`key_holder_identity_authenticated=false`,
`external_business_outcome_verified=false` and
`production_write_authorized=false`.

The expected signer-list SHA must be provided by **someone other than
the proposing Agent** and protected as part of an owner-controlled
trust-root policy. If a malicious Agent can modify both the allowed signer
file and the expected hash/CLI arguments, it can substitute its own key:
a cryptographic API alone does not provide this OS-level isolation.
The test harness's temporary key is not a real external authority.

## Reviewable unsigned subject

`attestation-subject` is read-only and generates a scope-exact unsigned
JSON template from a previously independently verified repair lab task.
The `statement` object has `outcome=REVIEW_REQUIRED` until a separate
reviewer actively replaces it with `DOMAIN_ACCEPTED` or
`DOMAIN_REJECTED` and provides a genuine rationale. The proposer cannot
self-assert either verdict through the template.

Example, using an already initialized local ledger and an accepted
P10.4 repair lab task:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures attestation-subject --task-id VERIFIED_TASK_ID --principal reviewer@example.com
```

The reviewer independently saves the returned `statement` object to a
UTF-8 JSON file, examines their own real-world evidence, chooses
`DOMAIN_ACCEPTED` or `DOMAIN_REJECTED`, supplies their specific
rationale, and signs the **exact final JSON file bytes** on their
controlled machine:

```powershell
ssh-keygen -Y sign -f C:\trusted-reviewer\ed25519_private -n cognition-agent-os-outcome-v1 C:\trusted-reviewer\outcome.json
```

The private key MUST remain with the external signer, never in a
repo checkout, connected Agent tool or task fixture. The detached
`outcome.json.sig` is passed to the verifier along with a separately
administered allowlisted public signer file:

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures attestation-audit --statement C:\trusted-reviewer\outcome.json --signature C:\trusted-reviewer\outcome.json.sig --allowed-signers C:\trusted-reviewer\allowed_signers --expected-allowed-sha256 EXTERNALLY_PINNED_64_HEX_DIGEST --principal reviewer@example.com
```

The CLI does not initialize SQLite, write a task, issue a grant, record
an approval event or promote a patch to production. A trusted,
durable OS-enforced reviewer key policy and an owner-authorized business
outcome workflow remain future acceptance prerequisites.

## Empirical evidence and falsification

`tests/test_outcome_attestation.py` uses the OS's **real OpenSSH
Ed25519 signer/verifier**, with keys generated outside the Agent's
fixtures and workspace inside a temporary test harness. It tests
authentic signatures for both outcomes, forged verdicts, substituted
allowed public keys, wrong principal, task IDs, grant revisions, source,
proposal and candidate digests, wrong holdout, expired/future signatures,
duplicate JSON fields, lab file/input mutations *after signing*,
untrusted signer paths inside the workspace, a read-only CLI, and
unsigned statement exporting which cannot claim acceptance.

These verify the signature binding on actual Linux and Windows runners,
NOT independent human review of actual third-party unseen tasks. The
native Windows scheduler tests and all earlier P0–P10.6 regressions
remain part of the cumulative draft PR #12 integration gate.

**Release status:** draft, unmerged, user Windows 11 host uninstalled;
no real reviewer-signed business success, no trusted owner key enclave,
no local Ollama evidence and no general autonomous synthesis. Signatures
remain evidence for a future independent action policy, not a shortcut
around explicit grant review.
