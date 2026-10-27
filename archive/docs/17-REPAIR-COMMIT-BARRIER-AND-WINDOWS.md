# P10.5 — Repair-commit evidence barrier and native Windows integration

## Incident: post-review artifact commitment was not reverified

P10.4 had a TOCTOU-style trust gap: `review_patch` independently
checked source, public cases and reviewer-pinned holdout, then wrote the
candidate into `workspace/repair_lab/`, and committed
`REPAIR_LAB_VERIFIED` without **re-reading those inputs and actual staged
bytes after the effect**. A separate filesystem actor can mutate a source
or holdout after the first review. SQLite `BEGIN IMMEDIATE` serializes
database writes, not outside processes editing the original files.

The existing `repair_oracle.review_patch` now performs another independent
`audit_patch(reveal_holdout=True)` *after* the local file stage, plus
actual file-size, symlink and SHA-256 readback. Candidate hash, holdout
case counts and observed pass count must match the original approval.
Only then can the task reach `REPAIR_LAB_VERIFIED` and emit
`REPAIR_HOLDOUT_ACCEPTED`.

If the second review or staged bytes differ, the task becomes
`UNKNOWN / REPAIR_POST_EFFECT_EVIDENCE_CHANGED`. The event
`REPAIR_POST_EFFECT_REJECTED` preserves the before/after candidate
hashes, later verifier status, and whether staged bytes matched. A
possibly orphaned isolated file is **not** treated as an approved patch
and must not be used as permission to edit original code. A concurrent
filesystem adversary might change bytes after the final readback too;
absolute atomic proof needs protected immutable inputs or external
signer controls, which are NOT part of P10.5.

Fault injection tests deliberately mutate:
- the sealed holdout **after the initial successful independent review**;
- the original Python source **after the same review**;
- the candidate file **after it has already been staged**.

Every scenario must reject durable success with no `REPAIR_HOLDOUT_ACCEPTED`
receipt, even though the isolated file may have been created.

## Incident: prior Linux-only evidence did not establish Windows compatibility

The system's expected installation host is Windows 11, but previous
P0–P10.4 CI used only `ubuntu-latest`. This left fundamental
cross-platform requirements untested. P10.5 adds a cumulative
`windows_offline_regression` GitHub Actions job using
`windows-latest` and `pwsh`; it smoke-tests the native
`scripts/host_tick.py --help` entrypoint and the **same complete Python
unittest suite** as Linux. No paid remote model provider, trial AI credits,
auto-download, production host or user credential is involved.

**First genuine Windows result:** GitHub Actions `39445124518`:
Linux PASS (203 tests); Windows FAIL with 32 errors and 1 failure.
The errors were `[WinError 32]` when test cleanup tried to remove temporary
SQLite databases: read-only connections had been opened with
`with sqlite3.connect(...)`, which ends a transaction but **does not
close the connection**. Linux can unlink an open file, masking this
lifecycle defect. A separate blob-identity test wrote text using
`Path.write_text` on Windows, creating CRLF bytes while its immutable Git
SHA expected explicit LF bytes.

**Systemic corrections:**
- `intent_runtime.audit_intent_plan`,
  `reconciliation_oracle.audit_stored_report`, and
  `repair_oracle.audit_patch` explicitly use
  `with contextlib.closing(sqlite3.connect(...))`. Each audit now
  closes its Windows SQLite handle deterministically; transaction closure
  alone is not mistaken for connection disposal.
- Byte-identity test fixtures in `tests/test_p1.py` use
  `Path.write_bytes(b"...\\n")` to preserve exact Git blob bytes
  regardless of OS-specific text newline translation.
- Cumulative CI now makes Windows regressions part of every PR acceptance
  gate rather than assuming success from Linux-only evidence.

**Confirmed corrected run:** GitHub Actions `39445509712`:
Linux **203/203 PASS**; Windows hosted runner **203/203 PASS**.
The public GitHub external-source live smoke was SKIPPED; it is not an
additional public-network integration proof.

## Authorization and unresolved outcomes

No PR was merged, no remote source modified, no production user file
overwritten, no model called with paid/free-credit tokens, and no
repair-lab result was promoted to authority over its own test oracle.

Windows hosted-runner success proves specific Python CLI/tests execute on
a hosted Windows image. It does **NOT** prove the user's Windows 11 host
has registered a real Task Scheduler job, runs unattended after reboot,
has a locally installed model, handles production filesystem ACLs,
or closes any real-world business outcome.

**Next high-value acceptance:** independent user-host Windows Task Scheduler
restarts and due task replay, externally anchored hidden/reference inputs
whose reviewer authority is distinct from the agent, and unfamiliar
multi-file code changes with outcome-based holdouts. These require
additional real evidence; increasing only regression count is not success.
