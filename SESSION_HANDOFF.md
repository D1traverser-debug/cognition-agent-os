# cognition-agent-os — durable continuation checkpoint

## LATEST P10.8 — external signed outcomes change future methods (2026-10-20)

This is the CURRENT candidate checkpoint, superseding P10.7 and all
historical sections below. Preserve the actual outcome: genuinely
self-directed cognition, goal execution with explicit authority,
independently observed outcome evidence, systemic repair and durable
cross-task method revision. Hard budget: no paid remote model tokens,
no expiring/free-credit AI pool, and no unrequested model installation.

**Owner candidate:** `D1traverser-debug/cognition-agent-os`.
**Branch:** `feat/p10-runtime-conformance-20261020`.
**Integration Draft PR #12 to main:**
https://github.com/D1traverser-debug/cognition-agent-os/pull/12 .
All remain unmerged; no owner Windows 11 computer access or release.

**New connected code:**
- `src/cognition_agent_os/signed_feedback.py`: explicit write-once
  `owner_outcome_trust` policy in original SQLite ledger, binds a
  reviewer principal, out-of-band SHA256 of public SSH allowed_signers
  and its file path. The policy can only be enrolled via explicit
  `attestation-bind-trust` command, never by run_tick. Read-only
  preflight refuses missing/empty authority without changing the file.
  No silent replacement or self-restoration is permitted.
- `attestation-record`: real external signature and original P10.4
  source/holdout/lab result are rechecked both before and after acquiring
  existing SQLite write lock. Root SHA and signer must match previously
  bound policy, authority grant/goal must still permit writes.
  A `signed_outcome_feedback` row and provenance event commit in same
  task ledger; repeated identical record idempotent, conflict rejected.
  **DOMAIN_ACCEPTED does not grant production write rights or apply code**.
- In `src/cognition_agent_os/repair_search.py`: DOMAIN_REJECTED
  feedback now changes future action. A new repair that chooses
  identical original SHA, visible SHA, holdout SHA, candidate SHA and
  operator mechanism is rejected before new immutable proposal with
  `SIGNED_REVIEW_PREVIOUSLY_REJECTED`, and checked again inside the
  finalization write lock for races. Changed public input is eligible
  for new evidence-driven hypothesis; model-generated/fake JSON event
  cannot impersonate a signed record.
- Tests extend `tests/test_outcome_attestation.py` using real
  ephemeral Ed25519 signing on Linux/Windows for accepted/rejected
  input, immutable conflicting verdict, exact-scope feedback, forged
  events, unbound/changed root, grant revocation and actual CLI path.
- `docs/20-SIGNED-FEEDBACK-TO-METHOD-REVISION.md` records exact
  command protocol and explicit trust limitations.

**Evidence history (do not hide failed runs):**
- First 222-test CI `39457977932` had two failures from duplicate
  `reason` parameter when formatting a structured refusal.
  Corrected `_no(status,**kw)`.
- The follow-up 225-test CI `39458516905` found that the common
  writable SQLite connection mutated an empty file *before* returning
  an uninitialized trust-root refusal. Corrected by read-only URI
  schema check before writable connect; tightened negative regression.
- Final branch docs and handoff commits need an independently checked
  latest-head CI. Do not claim all checks green until observed.
- No paid/cloud/finite credit LLM use. Real public GitHub source job
  is SKIPPED in normal CI unless explicitly opted in.

**Irreducible trust limits:** the binding API is user-intended but
the local code cannot know if a real human invoked it; a process with
full SQLite write control or the owner's OS identity can still
substitute authority and feedback. No owner filesystem ACL separation
or real, independently signed business verdict has been provided.
A cryptographically valid CI test signature is not real domain gold.
The ledger is the intended local governance authority, not a
tamper-resistant external evidence service. There is still no
general agent-generated multi-file code repair, owner Windows
deployment, true third-party business outcome or main release.

**Next highest-value direction:** true owner-isolated external trust
policy and actual independently defined real-world acceptance, then
end-to-end unfamiliar task → agent proposal/execution → outside
signed outcome → iterative methods across tasks. Do not create
more fixed adapters or fake a signed business success. Remain in
one Draft integration PR #12 and never merge without explicit consent.

## LATEST P10.7 — externally signed independent outcome boundary (2026-10-20)

This is the newest continuation point; prior P10.6 and older headings
below are historical. Preserve user goal: truly self-directed agent that
studies, reasons, executes under authority and independently proves
outcomes, rather than accumulating fixed monitoring modules or labels.
Use zero paid AI token billing, no trial/finite free AI credits and no
unrequested model download.

**Repository:** `D1traverser-debug/cognition-agent-os`;
branch `feat/p10-runtime-conformance-20261020`;
cumulative **Draft PR #12** to main:
https://github.com/D1traverser-debug/cognition-agent-os/pull/12.
The PR remains OPEN, DRAFT, UNMERGED; user Windows PC untouched.
P10.6 previously proved true 2-tick Windows Task Scheduler on GitHub
hosted Windows, NOT owner-PC unattended reboot recovery.

**This increment fixes the P10.4 trust provenance gap**:
Separate implementations of an evaluator and SHA-pinned holdout can
validate calculations and unchanged bytes, but CANNOT show the
reviewer's assertion is not self-issued by the proposing Agent.
- Added `src/cognition_agent_os/outcome_attestation.py`: a strictly
  read-only verification of an externally signed JSON result statement
  using real system OpenSSH `ssh-keygen -Y verify`, fixed namespace
  `cognition-agent-os-outcome-v1` and an independently supplied SHA256
  of an `allowed_signers` trust anchor outside the Agent's workspace
  and fixtures. Private signing key never accepted, copied, generated
  by Agent code or stored in the repository.
- Statement binds `task_id`, revision of goal/grant, immutable
  source_spec SHA, artifact SHA, candidate SHA, holdout SHA, named
  reviewer principal, exact verdict DOMAIN_ACCEPTED/DOMAIN_REJECTED,
  rationale and signed bounded validity interval. Reopens SAME existing
  SQLite, and independently rechecks original source, hidden cases
  and exact staged candidate via P10.4 oracle after the signature.
- New CLI `attestation-subject` emits an **unsigned** scope-exact
  statement from an actually verified lab candidate. It has
  `outcome=REVIEW_REQUIRED` by default (unacceptable for signed proof),
  no gold labels, no private key and no write privilege.
  `attestation-audit` checks externally signed outcome without
  modifying DB/task/artifacts or granting production authorization.
- Signature is only evidence that the allowlisted KEY HOLDER made the
  assertion, not proof of that person's true human identity, honest
  business review, real-world outcome, or production authority. Output
  always sets `key_holder_identity_authenticated=false`,
  `external_business_outcome_verified=false` and
  `production_write_authorized=false`.
  If the proposing Agent controls *both* the public trust key and
  independently supplied expected digest, it can still bootstrap its
  own false root; proper owner OS ACL / signer governance is NOT
  installed or tested on the user's machine.
- `tests/test_outcome_attestation.py` uses **real ephemeral Ed25519
  ssh-keygen sign and verify** on Linux and Windows with signing keys
  kept outside Agent workspace, exercising valid accept/reject,
  unsigned-template refusal, modified verdict, incorrect grant/task,
  unpinned signer, wrong candidate/holdout, expired/too-future
  attestation, modified source/file after signing, malformed JSON and
  CLI read-only no-ledger-create. This is cryptographic mechanism
  coverage with a TEST signer, NOT actual independent human review.
- Design and actual manual reviewer handoff:
  `docs/19-SIGNED-OUTCOME-TRUST-BOUNDARY.md`.
- First P10.7 functional run `39454163255` SUCCESS with
  **212/212 Linux and 212/212 Windows**, including real OpenSSH signer;
  native Windows scheduler also successful. Later changes to the
  unsigned template and two new tests triggered a run
  `39454945150` which was cancelled by subsequent documentation
  commit due to GitHub Actions `cancel-in-progress`, NOT a test failure.
  Latest docs/checkpoint commit requires NEW head CI verification;
  do not reuse old success as proof of new head.

**Critical scope constraints:** This cannot enable production patches
or signed review decisions without a real separately managed reviewer
private key, independently anchored public-key policy and external gold.
No such key was granted by the user and no autonomous real-world
business acceptance has been observed. There is no actual owner Windows
11 install or local-model inference. No merge or remote paid API calls.

**Next valuable engineering direction:** get an owner-administered,
permission-separated trust root and a real unseen user-supplied
outcome/reference source; bind the signed verdict to a durable,
independently re-auditable learning signal only AFTER trust-root ownership
is enforced. Do not accept model-generated signer roots or auto-reenable
fused capabilities. Keep work on cumulative Draft PR #12 and verify the
last CI head on both OSes before any release claim.

## LATEST P10.6 — OS-triggered Windows host plus fail-closed registration (2026-10-20)

This section is the exact CURRENT checkpoint, superseding P10.5 below.

**Goal and budget:** Genuine autonomous cognition, authorized action,
independent evidence, systemic correction and durable learning; no paid
cloud model tokens or finite AI-credit/trial dependency. Tests of fixed
capabilities do not establish general AI autonomy.

**Single repo and candidate authority:**
`D1traverser-debug/cognition-agent-os`, branch
`feat/p10-runtime-conformance-20261020`, cumulative integration
**Draft PR #12** https://github.com/D1traverser-debug/cognition-agent-os/pull/12,
base `main`, still open and UNMERGED. P0–P10.6 remain candidate code.
No user Windows PC deployment, no production action, no PR merge.

**New engineering implementation and observed tests:**
- Located and modified EXISTING `scripts/register_windows_host.ps1`
  (did NOT create a parallel registration authority). Keeps explicit
  owner opt-in. Adds absolute parameterized Python/DB/workspace/fixtures,
  future start, bounded recurring trigger duration; current interactive
  user `-LogonType Interactive -RunLevel Limited`, no admin credential,
  no silent `AutoStageGoals`, no overwrite of existing task.
  Long-running default repetition duration preserved as 3650 days.
- `scripts/verify_host_registration.py`: invokes read-only existing
  `host._admit_existing_ledger` so bogus/uninitialized SQLite cannot
  register a scheduler or mint a new write grant.
- `scripts/verify_windows_scheduler_probe.py`: seeds two different
  source-evidence tasks with distinct due times into one isolated SQLite;
  independent read-only verification of host_ticks (ticks>=2, processed
  total exactly 2), source immutability, two actual `NEEDS_REVIEW`
  results, hashes of durable artifacts and unchanged authority revision.
- `scripts/verify_windows_scheduler.ps1`: registers an ephemeral *real*
  user-scoped Windows Task Scheduler task, allows actual 1-minute recurring
  Windows triggers to launch `scripts/host_tick.py` as separate processes,
  checks Task Scheduler return code AND the SQLite/file readback, then
  unregisters task in finally. Also tests empty SQLite registration fails
  without leaving a task behind. No direct run_tick calls in witness loop.
- GitHub Actions adds mandatory `windows_native_scheduler` job alongside
  Linux and Windows full regression (both previously 203/203 PASS).
  Public source live integration remains optional/SKIPPED.
- Initial scheduler CI `39447708137` FAILED due real PowerShell enum
  `LeastPrivilege` not accepted for `-RunLevel`; corrected to `Limited`.
- Windows native follow-up `39447960517` SUCCESS with authenticated
  OS task info, **ticks=2, processed_total=2, completed_tasks=2** and
  immutable artifact readback.
- Strengthened negative integration `39448896882` SUCCESS, logs prove
  `UNSEEDED_AUTHORITY_REGISTRATION: BLOCKED`, two native scheduler
  wakeups with two completed tasks, and
  `TEMPORARY_SCHEDULER_TASK_REMOVED`. Linux and Windows suites PASS.
- Design: `docs/18-WINDOWS-NATIVE-SCHEDULER-ACCEPTANCE.md`.
  Latest docs/handoff-only commits require head CI reread before
  calling the final head independently verified.

**Not proven:** owner Windows 11 Scheduler installation, actual reboot
recovery, execution before login without current user interactive session,
independent reviewer/domain outcome, general reasoning/inference or local
LLM model quality. A hosted GitHub Windows OS is an external test host,
NOT the user's PC. No production release and no owner authority grant.

**Next meaningful engineering/workflow:** close trusted independent
business/reference-result oracle in owner-controlled source and complete
real user-host Windows scheduled/reboot test when legitimate access exists.
Do not fabricate evidence for inaccessible owner host; keep Draft #12
unmerged unless an authorized release decision is given. Continue
enhancing autonomous methods via real unseen goals and independent
accepted results, not another governance/monitoring clone.

## LATEST P10.5 — post-effect acceptance barrier + native Windows CI (2026-10-20)

This section supersedes prior P10.4 and all historical checkpoints below.
User's actual objective remains autonomous cognition, authorized execution,
independent outcomes and systemic self-correction, with no paid LLM API tokens
or finite AI-credit/trial dependencies. Do not confuse 203 passing offline
regressions with general autonomy.

**Current repository and write scope:**
`D1traverser-debug/cognition-agent-os`, cumulative integration candidate
branch `feat/p10-runtime-conformance-20261020`, open Draft PR #12
https://github.com/D1traverser-debug/cognition-agent-os/pull/12
against `main`; NO merges/deployments or modifications to the user's
Windows PC. All P0–P10.5 changes are present only in the Draft candidate.

**Two concrete risk reductions in P10.5:**
1. Found an actual P10.4 local repair TOCTOU acceptance gap.
   `repair_oracle.review_patch` previously evaluated hidden cases and then
   staged files and persisted success without **new independent post-effect
   input+staged-byte readback**. Now its same-ledger write transaction
   re-runs `audit_patch` after the stage and checks actual staged file
   SHA, size and non-symlink status before writing `REPAIR_HOLDOUT_ACCEPTED`.
   Changed original source, changed pinned holdout or modified staged file
   triggers `UNKNOWN / REPAIR_POST_EFFECT_EVIDENCE_CHANGED`,
   `REPAIR_POST_EFFECT_REJECTED`; unapproved orphaned lab bytes do NOT
   authorize source changes. Three injected between-review/effect file races
   proved this behavior. This doesn't prevent an OS-level attacker from
   modifying unprotected files after the final read; protected trust roots
   and physical access boundaries are not available.
2. **First real GitHub-hosted Windows compatibility execution:** newly
   added `windows_offline_regression` CI job executes native
   `scripts/host_tick.py` and full unittest suite on Windows.
   First run `39445124518`: Linux 203 PASS but Windows **32 errors + 1
   failure**. Cause: `with sqlite3.connect(...)` doesn't close a
   connection, and Windows forbids deleting open SQLite files; immutable
   Git source fixture `write_text` translated LF to CRLF. Repaired
   read-only connection lifecycle in
   `intent_runtime.audit_intent_plan`,
   `reconciliation_oracle.audit_stored_report`,
   `repair_oracle.audit_patch` using `contextlib.closing`. Tests that
   assert blob hashes now build exact bytes with `write_bytes`.
   Corrected GitHub Actions run `39445509712`: **Linux 203/203 PASS,
   Windows hosted-runner 203/203 PASS**; `live_public_source` SKIPPED.
- Latest design/proof: `docs/17-REPAIR-COMMIT-BARRIER-AND-WINDOWS.md`.
- Latest functional code commit with dual OS PASS:
  `f57e24dd5e6e797e78809314c7f34ebd07773de8`.
  Later documentation/handoff-only commits need another head CI check.

**Still unproven / prohibited:** the user's actual Windows Task Scheduler
unattended run, OS reboot recovery in owner host, independently authenticated
holdout reviewer authority, local installed Ollama quality, unbounded
goal-based code synthesis, external business outcomes, production writes,
or a completed release; PR #12 remains DRAFT and no `main` merge occurred.
An internal SHA pin does not establish an independent reviewer identity.
No paid model API or finite AI credits were used.

**Next highest-value follow-through:** accept real owner-host unattended
tick evidence with an independently controlled acceptance suite; then test
an unfamiliar multi-module task via isolated review and holdout before
any owner-approved release. Keep existing single task/grant DB and cumulative
integration PR; do not spawn parallel governors or pad with monitors.

## LATEST P10.4 — isolated source patch experiment + held-out method correction (2026-10-20)

This is the currently authoritative continuation for candidate project
`D1traverser-debug/cognition-agent-os`. Previous P10.3 and earlier headings
below are historical. All work was committed to existing cumulative
**Draft PR #12** https://github.com/D1traverser-debug/cognition-agent-os/pull/12
on `feat/p10-runtime-conformance-20261020`, whose base is `main`;
the PR remains open, unmerged. Earlier drafts #1–#11 are also unmerged.
No owner Windows deployment, local model installation, production release,
or paid/limited-credit cloud inference occurred.

**Goal:** genuine autonomous cognition, hypothesis formation, permitted
execution, independent evidence of outcomes, systemic repair and durable
method revision. Prior graph experiments were bounded, not general code
repair. Hard cost boundary remains zero paid tokens/AI trial credits.

**New connected engineering:**
- `src/cognition_agent_os/repair_search.py`: existing runner accepts
  `pure_code_repair` tasks from same SQLite ledger/permissions. For one
  strictly pure Python 1–3 argument function with one comparator or arithmetic
  operator, AST parser rejects calls, imports, decorators, loops, globals,
  arbitrary expressions. A safe expression interpreter compares ALL
  alternative one-operator mutations using **public failing examples only**.
  Failure not reproduced or >1 viable candidate -> UNKNOWN/ABSTAIN.
  Immutable candidate is stored under existing artifact writer.
  Proposer cannot read the sealed holdout by its code path; monkeypatched
  test rejects any attempt to fetch it.
- `src/cognition_agent_os/repair_oracle.py`: a separate AST/operator-based
  evaluator rechecks source, immutable candidate, minimally changed AST,
  public cases and an externally SHA256-pinned **withheld** case suite.
  Hidden refutation -> UNKNOWN, no patched source file. Hidden acceptance
  -> create-once `workspace/repair_lab/<taskid>.py`, read back bytes and
  atomically record `REPAIR_LAB_VERIFIED` /
  `REPAIR_HOLDOUT_ACCEPTED` in original events. Crash between staging and
  DB commit is idempotently reconciled by a second process.
  All original fixtures, repository code and production data unchanged.
  Absence of hidden evidence is not counted as failed gold: 3-attempt
  budget, due-time cooldown and eventual UNKNOWN.
- `src/cognition_agent_os/conformance.py` independently revalidates both
  pending proposal and accepted lab states each tick; confirmed lab artifact
  integrity mismatch trips persistent `pure_code_repair_lab` capability
  circuit rather than repeatedly continuing a compromised execution method.
  Global write authority and P10 complete pre-effect conformance remain
  necessary; no repair-lab alternative bypass for a sandbox circuit.
- `src/cognition_agent_os/host.py` opt-in
  `host-tick --auto-stage-goals` includes bounded lab holdout reviews;
  default no automatic lab action.
  CLI: `seed-code-repair`, `repair-audit` (read-only) and
  `repair-review` (reviewed isolated effect).
- **Durable method correction**: when holdout refutes an operator
  substitution, its exact source SHA/public-suite SHA/holdout SHA/method
  are recorded in ledger. A future task with identical evidence refuses
  to repeat the known-failed same hypothesis; changing the public evidence
  allows a new experiment. No holdout *test contents* are given to proposer.
  This is narrowly scoped negative learning, not universal method evolution.
- `tests/test_pure_repair.py`: bounded comparison vs arithmetic rules,
  heldout counterexample to public-probe overfit, hidden read trap,
  unsafe executable syntax refusal, conflict, grant revocation, file tamper,
  proven lab circuit, missing holdout budget, real independent subprocess
  killed after stage effect and recovered, host and CLI paths.
  Documentation: `docs/16-ISOLATED-SOURCE-REPAIR.md`.

**Hard CI evidence:**
First CI `39441626410` failed 9 cases from mistaken AST function-vs-module
comparison and inadequate visible distinguishing cases; fixed.
Next CI `39441833965` had 1 test assertion for idempotent second review;
fixed.
Functional CI `39442272966` SUCCESS **199/199**.
Most recent functional commit
`e6de1efa42427a556fe2b267236c2b816f755edd`,
CI `39442609504` SUCCESS **200/200 Python tests**,
live public-source smoke SKIPPED. Documentation and handoff-only follow-up
commits must have final head CI checked before marking current head tested.

**Critical limitations:** pure AST evaluation is NOT an isolated OS process
sandbox for arbitrary code; holdout is software-separated and byte-pinned,
NOT authenticated by independently trusted reviewer keys or permission-enforced
secrecy. The task cannot produce arbitrary patches, choose new APIs,
interact with user apps or validate real-world semantic outcomes.
Accepted patch file is an isolated experiment only, never production
promotion or `main` merge. Real unattended Windows host, local Ollama
model execution, human domain trust and external outcomes remain unobserved.

**Next highest-value actual work, not new monitoring:** broaden autonomy by
a *real* separate outcome oracle and practical unseen task across unfamiliar
code/records, with independent trusted gold unavailable to proposer.
Introduce separate legitimate signing/access controls and physical host
acceptance before self-modifying real agent code. Do not invent credits,
merge any Draft or claim deployment without owner authorization. Keep all
new modifications in cumulative Draft PR #12 and verify true CI.

## CURRENT P10.3 — measured causal mechanisms and independent class repair (2026-10-20)

This is the exact latest continuation; it supersedes P10.2 and historical
markers below. The user needs autonomous goal/cognition/governance with **no
paid LLM token charges or expiring free AI credit schemes**, not another
monitor or library of prewritten demo answers.

**Repository/authority:** `D1traverser-debug/cognition-agent-os`.
Current cumulative integration candidate: Draft PR #12
https://github.com/D1traverser-debug/cognition-agent-os/pull/12
on branch `feat/p10-runtime-conformance-20261020` targeting `main`.
No PRs were merged, no owner Windows machine or production resources touched.

**Systemic defect P10.3 actually repaired:** P10.2 treated
`_descendants` exceeding 256 and any cycle as indistinguishable
`DEPENDENCY_GRAPH_UNBOUNDED`, revoking the entire ledger write grant
even when the graph was a provably legitimate large acyclic tree.
P10.3 added `src/cognition_agent_os/graph_experiment.py`:
- Two independently implemented graph closure experiments on live SQLite
  in the same write transaction: bounded Python BFS versus SQLite recursive
  CTE (UNION), with independent ancestor-cycle check. Hard complete
  closure cap 4096 nodes. Acyclic fanout/chain/branching versus actual
  cycles and oracle disagreement are evidence-discriminated; never guess
  a repair from single proof.
- Only if the graph is complete, acyclic and independently agreed, expand
  existing `_quarantine` to the *entire* proven descendant list
  (not just first 256). Preserve unrelated write grants.
- After executing the local quarantine, use SQL again to check every
  dependent task's real UNKNOWN/BLOCKED state, along with the root and
  lineage set. Write `CONFORMANCE_REPAIR_ACCEPTED` only on successful
  independent readback. Otherwise
  `CONFORMANCE_REPAIR_REJECTED` + globally revoked grant/circuit.
- Cycle, missing/invalid graph, >4096, independent oracle exception or
  oracle disagreement still result in global emergency stop; no branch
  silently restores authorization. Structural hypotheses and source graph
  hash persist in same `events` ledger as `CONFORMANCE_GRAPH_EXPERIMENT`.
- Existing task ownership, approvals, due queue, sandbox-only scope,
  budget and preflight remain in force. An ancestry index was added at
  DB initialization for traversal performance. Not a new agent database.
- Tests `tests/test_graph_experiment.py` and adjusted
  `tests/test_governance_failclosed.py` prove large legitimate fanout
  no longer causes whole-ledger revocation, real cycles still stop, 4096+
  still stops, independent disagreement and SQL exception stop, and
  deliberately incomplete quarantine is **rejected on independent
  readback**. Unseen generated fanout/chain/branching shape variations
  are tested against actual temp SQLite data.

**Verified functional evidence:** GitHub Actions run `39437997734`,
commit `3563e434f318aa4f3f0fab4d59be4b90dc9daed3`, cumulative
offline_regression **182/182 PASS**. External live_public_source SKIPPED.
Latest docs and handoff-only updates need a head CI reread before
calling the whole final commit verified. No paid remote inference used.

**Interpretation boundary:** genuine structural evidence supports a
causal mechanism distinction and safe remediation of the dependent
*state claims*. It does NOT prove broad, independent business
correctness, open-ended root-cause discovery, arbitrary autonomously
generated source-code patches, OS-level host deployment, human-approved
reviewer signatures or real local model intelligence. SHA-pinned
reviewer manifests are not independent authentication, and no
breaker-reset interface exists.

**Next highest-value gap:** independently executed unfamiliar user
workflows and actual goal-outcome measurements, ideally using a
locally installed zero-paid-token inference model, separately
authenticated review authority, and real Windows Task Scheduler
evidence. Establish an isolated holdout experimental test that can
falsify an automatically proposed *code* patch, rather than merely
mechanical SQLite containment. Do not create more monitoring-only
phases or merge the Draft without owner authorization. Preserve these
exact limits and proof chains.

## LATEST P10.2 — fail-open containment and pre-effect check fixes (2026-10-20)

This is the **most recent continuation checkpoint**; it supersedes the P10
and older sections below. The project is still the same
`D1traverser-debug/cognition-agent-os`, branch
`feat/p10-runtime-conformance-20261020`, cumulative
**Draft PR #12 targeting main**:
https://github.com/D1traverser-debug/cognition-agent-os/pull/12.
This increment was committed to the existing integration candidate,
**not a new stacked mini-PR**; all drafts remain unmerged and main unchanged.

**User's actual goal:** genuinely autonomous self-discovering cognition,
authorized execution, independent outcome verification, systemic causal
repair and durable learning across unfamiliar tasks. Never mistake static
task kinds, a watcher, a circuit breaker or passing tests for complete
general autonomy. **Hard cost budget:** no paid LLM tokens, finite trial
AI credits or automatic model downloads; local-only opt-in if installed.

**Two concrete governance failures independently identified:**
1. P10's dependency-closure exception (cycle or >256 descendants) was
   previously swallowed into `DEPENDENCY_BUDGET_BLOCKED` with no
   containment; a corrupted parent and its large unknown lineage could
   keep carrying stale authority. Fixed in `conformance.py`:
   `_emergency_dependency_stop` atomically revokes ledger-wide write
   authorization, marks root UNKNOWN and persists global sandbox stop in
   the **same SQLite transaction**; records
   `CONFORMANCE_EMERGENCY_STOP` without lying about fully checked
   descendants. No automatic self-reenable.
2. Host previously ran conformance only AFTER sandbox auto-stage:
   a corrupt receipt/file between ticks could be discovered after the
   next effect. Fixed by bounded *pre-effect* `effect_preflight`, invoked
   by BOTH `host.run_tick` (before new work and auto-stage) and explicit
   `sandbox_effect.stage_one`. An incomplete scan (more than 512
   currently eligible evidence claims) blocks new local effects.
   Fully quarantined noncritical contradictions do not starve legal
   independent tasks. Existing source-drift replanning is still allowed;
   stale evidence must not be mistaken for forged success.

**Evidence:** `tests/test_governance_failclosed.py` includes >256
descendant fanout, cyclic ancestry, previous forged receipt and sandbox
tampering followed by a second task, scanner capacity exhausted,
contained noncritical malformed reviews + subsequent legal effect,
and source-change control. An initial extended CI
`39435548093` had a real **1/175 failure** due to excessive
preflight blocking of valid work. The containment/admission predicate
was fixed and followed by successful cumulative Actions run
`39435827296`: **176/176 Python unit tests green**,
`live_public_source` SKIPPED (not a live upstream check).
Code commit of passing run:
`d14e6280f7c8ac949ab504536da04fceba768d44`.
Subsequent documentation/checkpoint-only commits must receive a
new head CI check before head is called tested.

**What is NOT proven:** actual cause (cycle vs legitimate fanout) in
real installations; autonomously generated source-code repair with
separate independent holdout; professional semantic gold, controlled
independent business outcome evidence; installed local Ollama; actual
unattended Windows Task Scheduler; signed external root of trust; real
`main` release. No production changes occurred.

**Next material work (avoid new fixed-domain adapters):** design a
separately authorized causal repair experiment inside an isolated code
workspace that can distinguish competing failure mechanisms using
holdout tests and prove the remedy across the entire capability class.
Never auto-reset an integrity circuit without an external trust anchor;
never let root-cause speculation become approval. When owner host access
exists, measure true scheduled ticks and end-to-end user outcomes.
Use Draft integration PR #12 for authorized review, NOT an automatic merge.

## P10 CURRENT — self-governing conformance and cumulative integration candidate

This replaces P9 and all prior CURRENT markers below as the exact resume state.
Historical state remains for diagnosis but is not proof of native deployment.

**Goal:** actual independent autonomous cognition + execution + governance, not
monitoring only, innumerable fixed-schema task modules or made-up CI completion
claims. User constraint: no paid cloud model tokens, time-limited/credit-based
AI services or automatic model downloads.

**Candidate owner:** `D1traverser-debug/cognition-agent-os`.
**Branch:** `feat/p10-runtime-conformance-20261020`.
**Integration Draft PR #12 -> main:**
https://github.com/D1traverser-debug/cognition-agent-os/pull/12
This is one cumulative P0–P10 candidate review target rather than another
tiny stack-only PR. Historical Draft PR #1–#11 remain open, draft and unmerged.
**No merge, production change, or physical Windows install was executed.**

**New P10 governance work:**
- `src/cognition_agent_os/conformance.py`: independent ongoing recheck of
  `NEEDS_REVIEW`, `SANDBOX_VERIFIED`, `DECOMPOSED`, and mechanically
  verifiable `VERIFIED` against actual source bytes, stored artifact hashes,
  sandbox effect bytes, receipt events and bounded parent/child ancestry.
  Explicit PASS vs INSUFFICIENT_EVIDENCE vs CONFIRMED_INCONSISTENCY.
- The existing host tick *automatically* runs a bounded enforcement sweep
  after work (local execution only when an actual host calls it). Confirmed
  mechanical contradictions are quarantined in the SAME SQLite task authority
  and all descendants are blocked/invalidated transitively, with durable
  `CONFORMANCE_VIOLATION` events. Missing proof is not called tampering.
- Durable `conformance_scan.last_task_id` in the original SQLite DB rotates
  across eligible tasks, preventing first-N bad observations from hiding later
  ones. Partial scans NEVER claim complete coverage.
- **System-level action:** serious confirmed `SANDBOX_VERIFIED` integrity
  inconsistencies trip persistent `conformance_capability_guard` for
  `goal_sandbox_stage` in the SAME DB. Exactly-once trigger event and a
  write-locked guard in P6 `stage_one` ensure future sandbox stage effects
  are disabled until independently accepted remediation. Auto staging does
  not bypass the circuit, and no user-observed reminders are necessary for
  local detection or safe-stop. An unknown / incomplete historical proof
  does not trip this high-severity guard. No automatic self-reenable.
- CLI `conformance-audit` is read-only and refuses missing DB;
  `--enforce` is an explicit manual form of the existing default host
  enforcement. All release decisions explicitly remain BLOCKED absent
  independent domain truth and genuine unattended-host proof.
- Test suite `tests/test_conformance.py` executes real temp SQLite/source
  artifacts, forgery, false receipts, changed files, verified intent parent
  descendants, truthful unsupported historical successes, full cursor
  rotation, CLI read-only/enforce and capability circuit breaker.
- Design: `docs/15-RUNTIME-CONFORMANCE-AND-RELEASE-GATE.md`.

**Verified evidence:**
- First integration CI `39432349451` on initial P10 implementation:
  167/167 Python tests SUCCESS against a Draft PR with base `main`.
- Latest capability-circuit functional commit
  `2d79cc206d1d2438ab9de526390abda5041463a7`;
  CI run `39433023953` SUCCESS: **169/169 offline Python unittest PASS**.
- `live_public_source` SKIPPED, NOT independently validated this turn.
- Later documentation and checkpoint-only changes must have latest head
  CI reread. No paid model API calls, free-credit consumption or remote
  provider mutations.

**Truth and trust boundaries:**
- A local scanner cannot prove actual Windows Task Scheduler wakeups, domain
  semantic correctness, causal root-repair, code provenance of a reviewer,
  installed local Ollama model quality or open-world goal understanding.
  `external_semantic_evidence` and `unattended_windows_host_evidence`
  remain NOT_OBSERVED; release gate unconditionally BLOCKED for these.
- Integrity guard is local SQLite authority; protecting against a malicious
  actor who can modify the code + SQLite DB itself requires external signed
  independent trust roots/OS permissions not yet available.
- Some legacy fixture `VERIFIED` claims only have incomplete historical
  evidence; conformance reports INSUFFICIENT_EVIDENCE and does not falsify
  or hide these records.
- The 11 earlier PRs plus cumulative integration PR #12 remain unmerged.
  **Current main is not the candidate Agent.** No Windows background
  execution or user-host configuration was performed.

**Highest-value next engineering, not phase inflation:**
1. Obtain independently authenticated domain oracle / trusted reviewer
   source that cannot be replaced by the proposing agent. Verify actual
   unknown cases and outcome value; keep separate from mechanical evidence.
2. Plan+execute genuine unfamiliar goal with local installed inference and
   independently observed real result. Remediation must address classes of
   failures and falsify alternative causal hypotheses, not just static checks.
3. Validate physical Windows unattended host and persistent recovery.
4. Use cumulative Draft integration PR #12 for authorized release review,
   with an explicit independent acceptance decision before any merge.
   Do not merge or claim release without approval.

## P9 CURRENT — typed goal compilation + caller-pinned semantic relationship (2026-10-20)

THIS IS THE CURRENT CANDIDATE PROJECT CHECKPOINT. Historical P8 and earlier
sections below are not evidence that candidate code is deployed.

**Owner:** `D1traverser-debug/cognition-agent-os`.
**Branch:** `feat/p9-intent-contract-20261020` stacked on P8.
**Draft PR #11:** https://github.com/D1traverser-debug/cognition-agent-os/pull/11
**Integration:** confirmed PRs #1 through #11 are ALL OPEN / DRAFT / UNMERGED,
with #1 based on `main` and others successively stacked on preceding branches.
`main` is NOT the functioning Agent. No approval or attempt to merge, deploy
to user's Windows PC, auto-download local model or incur paid AI credits.

**User outcome / hard constraints:**
Create a genuinely self-directed autonomous cognition/execution system able
to discover problems, reason about hypotheses, select authorized actions,
verify real outcomes and revise across unfamiliar domains, with NO remote
paid LLM tokens, limited AI free credits or trial-dependent quota. Code
regressions and more typed task adapters alone do NOT satisfy this outcome.

**New P9 implementation:**
- `src/cognition_agent_os/intent_planner.py`: one typed `goal_intent`
  compiler for `ensure_structure` (read local JSON and preserve data while
  meeting explicit constraints) or `compare_records` (two local CSV sources,
  dynamic join/discrepancy). Records bounded OBSERVE, CHALLENGE, PLAN, CHECK,
  COMMIT steps and a reproducible `plan_sha256` with explicit source and
  effect scopes. No arbitrary commands or agent-generated permissions.
- `src/cognition_agent_os/intent_runtime.py`: integrates with the
  existing `tasks`/`events`/`authority` database. Fences claimed parent,
  checks fresh grant/goal under one SQLite transaction, atomically emits
  exactly one typed child and marks parent `DECOMPOSED`. Nested intent
  creation refused. `intent-audit` independently reconstructs plan and
  validates persisted event/child parentage. New CLI `seed-intent`.
- `src/cognition_agent_os/semantic_contract.py`: strict caller-supplied
  out-of-band SHA-256 of exact reviewer-claimed relationship manifest,
  scoped to specific original source names and a declared join column.
  `seed-reconciliation --relationship-contract ... --expected-contract-sha256 ...`
  refuses unsigned-by-digest substitution or wrong scope. The P8 planner
  and separate SQL audit only use the specified key after checking source
  uniqueness and overlap. A stale or tampered manifest invalidates later
  read-only `reconciliation-audit` even when a previous report looked valid.
  The composed `compare_records` intent can now directly carry the same
  pinned manifest binding, validated at `seed-intent` intake and by its child.
- Tests `tests/test_intent_runtime.py` and `tests/test_semantic_contract.py`
  cover both task families, composed pin-through-intent integration,
  unregistered/recursive goals, path/privilege injection, genuine SQLite
  child+event linkage, false/falsified audit records, stale goal/permission,
  bad digest/scope, tampered manifest, ambiguous keys and no fallback to
  unrelated business fields.
- Design and acceptance: `docs/14-GOAL-INTENT-AND-SEMANTIC-CONTRACTS.md`.

**Hard CI evidence:**
- First P9 run `39429762735` executed 151 cases but had one
  validation-error-contract leak (GoalError instead of IntentError);
  corrected with typed lower-level error normalization and new negatives.
- Functional P9 run `39430380039` SUCCESS: **153/153 offline Python
  regressions PASS**. `live_public_source` SKIPPED by design.
  Later docs/checkpoint commits must have final head CI reread.
- Zero paid remote model tokens/free credit allocation used.

**Limitations demanding external evidence:**
- Fixed capability registry + typed constraints is an *increment toward*
  generic planning, not unrestricted natural-language understanding or
  open-world tool planning. The five steps are a compiled plan receipt, not
  five independently executed cognitive agents.
- SHA256 detects substituted manifest bytes but does NOT cryptographically
  authenticate a reviewer or prove human/domain semantic correctness.
  A model allowed to edit both manifest and expected digest can forge a
  supposed 'review'. A real deployment MUST isolate trusted expected digest
  from proposing-agent authority and independently validate actual labels.
- `REPORT_MECHANICALLY_VERIFIED` and `PLAN_MECHANICALLY_VALID`
  are not independent business outcome validation or permissions to mutate
  production. Original sources remain unchanged. No Windows unattended
  schedule / local Ollama inference has been physically observed.

**Next highest-value objective (do not multiply placeholder phases):**
1. Establish a genuine trusted reviewer/domain acceptance channel (or an
   externally executable objective oracle), with separate signer/security
   authority and unseen real-world cases; test disagreement and proof provenance.
2. Demonstrate bounded goal-to-outcome closure on genuinely unfamiliar tasks,
   causal mechanism falsification, independent readback and persistent method
   revision; avoid replacing autonomy with new fixed-schema examples.
3. Address draft stack #1–#11 through a deliberate, owner-authorized
   integration acceptance workflow; until integrated, the Candidate Agent
   does not exist on `main` or the user's Windows host. Do NOT merge without
   user consent; no pretend background processing.

## P8 CURRENT — evidence-driven record reconciliation (2026-10-20)

This is the authoritative latest *candidate project checkpoint*, superseding
historical P7 and below. Do not confuse a proposed capability branch with
deployed system capabilities.

- Owner: `D1traverser-debug/cognition-agent-os`.
- Candidate head branch: `feat/p8-evidence-reconciliation-20261020`.
- Draft PR #10: https://github.com/D1traverser-debug/cognition-agent-os/pull/10
  stacked on P7, open/unmerged. `main` remains unchanged.
- Principal purpose: progress beyond hard-coded individual repairs by
  inferring **competing relational join hypotheses from actual unseen data**
  in bounded, opt-in record reconciliation tasks. Same SQLite task authority,
  bounded host and independent artifact ledger; no new parallel governor.
- `src/cognition_agent_os/reconciliation.py`: source CSV parsing,
  hypotheses for shared join keys, identifier uniqueness and overlap
  evidence, ambiguous-case abstention, full missing/extra/field-mismatch
  enumeration, and immutable report proposal after independent oracle.
- `src/cognition_agent_os/reconciliation_oracle.py`: second implementation
  independently reparses source CSVs, recomputes proposed key with SQL overlap
  evidence, uses SQLite joins to check all differences, and provides
  post-write read-only audit of artifact and authoritative source state.
  This is independent **algorithmic/mechanical** evidence, not external
  domain semantic endorsement.
- CLI: `seed-reconciliation --reference expected.csv --observed actual.csv`
  and `reconciliation-audit --task-id ...`, using existing worker/host.
- Dynamic tests: `tests/test_reconciliation.py` cover generated DV regression
  cases and financial invoices, shuffle/missing/extra/field changes,
  15 seeded unfamiliar random cases, ambiguity, source and report tampering,
  grants, malformed input, CLI + host, and malicious SQL/proposal mismatch.
- Initial P8 CI run `39427366238`: 131 tests, one FAILURE exposing
  real unsafe hypothesis substitution: duplicate `invoice_id` could
  silently fall back to coincidentally unique `amount`.
  Both planner and independently coded SQL oracle now reject such invalid
  explicit identity evidence (no implicit weaker fallback), with regression.
- **Most recent verified code run** `39427596976`: SUCCESS,
  `offline_regression` **132/132 tests**; `live_public_source` SKIPPED.
  After P8 code test run, documentation/handoff-only commits also need
  latest head CI check. No claim of new external GitHub live validation.
- Budget: zero paid remote LLM API tokens, no finite AI credits, no model pulls.
  Original business sources are read-only; discrepancies are
  `NEEDS_REVIEW / PROPOSAL_NOT_APPROVED`; `VERIFIED` for consistent
  records means only this specific mechanical relational contract.

**Unproven:** inferred key reflects real-world business meaning, user-validated
financial or chip-testing correctness, independent human/third-party semantic
oracle, genuinely open-ended natural-language goal planning, unknown
cross-domain risk discovery, broad causal mechanism comparison, self-directed
systemic repair, real installed Windows unattended host, or tested local
model inference. Code regression counts do not prove these outcomes.

**Next highest-value P9:** challenge the inference assumptions via actual
independent domain truth: semantic join-key provenance, alternative hypotheses
and falsification against withheld non-synthetic records; introduce general
goal-to-observation-to-decision planning with explicit resources/authority,
and test actual result transfer. Address stacks of unmerged PRs: request an
authorized integration/release acceptance process before assuming this code
is running from main. Do not spend paid AI credits.

## P7 CURRENT — durable diagnostic routing and fair recovery (2026-10-20)

This section supersedes P6 and older descriptions below; those are history, not
proof of new semantic autonomy.

- New independent repository `D1traverser-debug/cognition-agent-os`.
- **Current Draft PR #9**: https://github.com/D1traverser-debug/cognition-agent-os/pull/9
- Head branch: `feat/p7-diagnosis-fairness-20261020`, stacked on
  `feat/p6-sandbox-outcome-loop-20261020`, NOT merged into `main`.
- Most recently verified functional commit BEFORE this checkpoint:
  `a9a65889b544a2979e7a56e064c3ff7b915b01a2`.
- GitHub Actions run `39425408187`: offline_regression SUCCESS,
  **113/113 Python tests**, including cross-family JSON/CSV recovery.
  `live_public_source`: SKIPPED (NOT a fresh live-source pass).
- No paid LLM APIs, expiring model-credit allowances, paid provider API,
  model installation or real Windows host actions. Model quality not tested.

**Outcome and implementation:** P6 had a real systemic review starvation
failure. Old invalid proposals occupied a bounded first-N query each host tick,
suppressing later legal candidates. P7 `diagnostics.py` now re-evaluates
audit evidence inside the existing SQLite write transaction, atomically
classifies untrusted artifacts -> UNKNOWN, revoked/stale grants -> BLOCKED,
persists competing UNPROVEN candidate causes and a disposition-specific
next-action class; closes invalid tasks from automatic review selection.
P7 `sandbox_effect.py` selects strictly JSON kind=goal_case and due reviews,
honors 60s/120s transient-stage cooldown and prior three-attempt limit.
It does NOT automatically approve tampered proposals or overwrite source files.

**Autonomous narrow recovery:** Previously UNKNOWN
`GOAL_EVIDENCE_UNAVAILABLE` JSON/CSV tasks can be independently re-observed
after the source file reappears/corrects. An opted-in host tick
`--auto-stage-goals` rereads the source, guards goal and grant, and
atomically produces one new child on the EXISTING tasks ledger (no parallel
planner/scheduler). Missing evidence gets a 900s due-time cooldown,
conflicting requirement stops with NO_SAFE_GOAL_PLAN, stale authority blocks,
and two ancestry replans remain the budget. Next tick processes child and
may stage into isolated sandbox, with independent readback.
Tests prove invalid older items do not starve younger valid ones, repeated
failures do not multiply child tasks, a stale pre-audit cannot close newly
valid work, and both JSON and CSV tasks can resume without touching originals.

**Not proved:** open-ended autonomous goal decomposition, unknown-risk discovery,
genuine competing cause falsification or self-corrective method learning,
external semantic/user-goal acceptance, real provider effects, true Windows
unattended host scheduling, or installed local Ollama inference. Mechanical
`SANDBOX_VERIFIED` remains distinct from business outcome success.

**Next highest-value P8:** move toward open-ended but bounded goal
decomposition into evidence-seeking/competing-hypothesis/action steps, with
a genuinely independently executable domain oracle; test at least two real
non-handwritten input families and prioritize effective systemic repair
rather than new monitors. Do not elevate to general autonomous agent or merge
candidate stacks without independent outcome proofs.

## P6 LATEST checkpoint — 2026-10-20 (current exact resume)

This checkpoint supersedes P5 and earlier below; those remain historical.

**Owner/repository:** D1traverser-debug/cognition-agent-os.
**Candidate branch:** `feat/p6-sandbox-outcome-loop-20261020`.
**Draft PR #8:** https://github.com/D1traverser-debug/cognition-agent-os/pull/8
(stacked on P5; all previous PRs remain draft; main not changed).

**Governing goal:** an independently useful, self-directed cognition/execution
agent; not a pile of monitors, templates, test scores or semantic claims without
independent outcome evidence. Hard budget: no paid LLM API, remote inference
tokens, limited free AI credits or trial allocation; only opt-in already
installed local Ollama is permissible and unproven on a physical host.

**P6 implemented code:**
- `src/cognition_agent_os/sandbox_effect.py`: independently audit P5's
  immutable local proposal, recheck goal/grant and task state under the existing
  SQLite `BEGIN IMMEDIATE`, create-once file in
  `workspace/sandbox/<taskid>.candidate`, independent SHA/readback, original
  source intact, durable event `SANDBOX_EFFECT_VERIFIED` and distinct task
  state `SANDBOX_VERIFIED`. No remote effect, no source modification and NO
  domain/business VERIFIED claim.
- On original source drift: same SQLite ledger transitions parent to
  `NEEDS_REPLAN` and issues one new `goal_case` child atomically;
  max **two** parent-child replans then UNKNOWN.
- On repeated sandbox write/readback uncertainty: max **three** persisted
  attempts then `UNKNOWN / SANDBOX_EFFECT_RETRY_EXHAUSTED`; do not overwrite
  an unknown/conflicting existing file or produce false success.
- `goal-stage-sandbox --task-id ...` CLI, opt-in host
  `host-tick --auto-stage-goals` and optional Windows registration
  switch `-AutoStageGoals` (no OS installation observed).
- `tests/test_sandbox_effect.py`: two families, real subprocess killed after
  file creation and before SQLite commit, second process reconciliation,
  two independent staging processes, revoked/stale authority, mismatched
  sandbox effect, source drift replan and budget, symlink refusal, host opt-in,
  repeated failed effect attempts; existing P0-P5 tests preserved.
- Operational limits: `docs/11-SANDBOX-OUTCOME-AND-REPLAN.md`.

**Current hard evidence:** code functional commit
`6d9c854f02761f4f3386e0dc240006c8f8d7426c`,
GitHub Actions run `39422945419`, public-repository
`offline_regression` SUCCESS, **100 Python tests OK**,
`live_public_source` SKIPPED by design. Prior successful P3
immutable/mutable public GitHub checks live in separate earlier runs;
no new live GitHub remote checks demonstrated by this run.
Subsequent documentation and PowerShell registration switch changes
must be reread and their latest CI checked before calling head tested.
No actual Windows Task Scheduler registration or real installed local
model observation took place.

**Unproven and remaining:** semantic quality/independent ground truth;
open-ended goal decomposition, unknown problem identification and true
causal competition, autonomous solution choice and verified post-action
domain value; applying real provider actions/receipts; durable learned
methods and systematic defect-class repair; fairness if a permanently
unadmitted review consumes the first review slots repeatedly; actual
unattended physical host. Do not mark full Agent as finished.

**Next P7 priority:** close the feedback loop in the existing task
authority by turning independently observed failed/unknown dispositions
into durable diagnosis and bounded next-action transitions, with
fair admission of other legal work, not merely replaying failed reviews.
Prove task-family transfer, real meaningful outcomes and no user
supervisor dependency. Preserve strict authorization and cost bounds.
Additional owner Windows access/real independent semantic labels are
external evidence blockers but unrelated authorized engineering can continue.

## P5 LATEST — verified bounded goal-driven action candidate loop (2026-10-20)

This is the **current exact continuation** and takes precedence over historical
P4/P3 checkpoints retained below.

Owner/project: `D1traverser-debug/cognition-agent-os` candidate branch
`feat/p5-bounded-goal-loop-20261020`, Draft PR #7 stacked on P4 branch:
https://github.com/D1traverser-debug/cognition-agent-os/pull/7

**Governing objective:** a genuinely useful self-directed cognition and execution
agent, not a stack of GitHub watchers or synthetic benchmarks. Preserve user's
hard requirement: NO paid LLM calls, finite free AI model credits or
trial-dependent services. An explicitly installed local Ollama model is the
only optional inference path; none needed for this P5 prototype.

**Implemented P5 code:**
- `src/cognition_agent_os/goal_loop.py`: bounded declarative JSON key and CSV
  column conformance goals; two alternative candidate actions (NO_OP or
  explicitly allowed additive repair); original-source double-read, three
  bounded alternative hypotheses, semantic disagreement marked unresolved;
  source preservation check before mutation; local immutable proposal only.
- `seed-goal` CLI and existing `run_once` + `host-tick` support use the
  **same** SQLite task/grant/lease/fencing ledger, not a second goal state store.
- `src/cognition_agent_os/goal_audit.py` and CLI `goal-audit`: a second,
  read-only implementation compares authoritative task, current source
  SHA, original values, candidate artifact hash and goal constraints.
  It does NOT approve, source-edit, close a real business goal or mutate DB.
- Tests `tests/test_goal_loop.py`, `tests/test_goal_audit.py`: two families,
  real subprocess crash/restart and dual-worker race, grant/goal revision,
  input changing after planning, corrupted or conflicting sources, dirty
  artifacts, malicious proposer corruption, extra unrequested JSON fields,
  safe no-op and opt-in CLI intake.
- Instructions: `docs/10-BOUNDED-GOAL-LOOP.md`.

**Current code acceptance evidence:**
- GitHub Actions run `39421227885`, offline_regression success,
  **85 unittest cases in 5.170s**, including extra-field falsification.
  `live_public_source` SKIPPED, *not* newly verified. Earlier P3 live-public
  source smoke remains independently observed in run `39415344574`.
- Test failure in an earlier P5 candidate was test-only Python continuation
  escaping (two backslashes); repaired and rerun successfully.
- Static review found a material scope hole (extra JSON keys permitted
  by the first version of two constraints checkers); BOTH the proposed
  candidate checker and separate auditor now fail closed for any
  unrequested added key. Tested adversarially.
- Tests demonstrate mechanical non-destructive proposal generation,
  authorization and separate readback, not open-ended cognition.

**Unfinished genuine capabilities:** arbitrary goal decomposition, unknown
information discovery, independent semantic/causal hypothesis testing,
self-initiated evidence gathering, disposition-driven automatic replanning,
controlled enactment with external success check, cross-domain learned method
transfer, productive user-goal closure, actually installed Windows unattended
host, and real existing Ollama model inference. P5 proposal candidates are
still `NEEDS_REVIEW`, not completed corrections. No main merge.

**Next highest-value P6 action:** bind independent audit outcomes into
durable revisable plan/evidence-followup transitions rather than leaving
all candidate review to the user. Use existing tasks/events and strict
authority/provenance, include successful authorized end-to-end sandbox
application and post-application outcome observation on at least two distinct
families. Preserve anti-loop budget and independent oracle separation.
Then demonstrate transfer on unfamiliar tasks and real unattended host
before any claim of general autonomy. The user should not have to remind the
Agent to notice its own failures.

## P4 LATEST verified continuation, 2026-10-20 (supersedes P4 checkpoint below)

- Current project candidate: Draft PR #6, `feat/p4-evidence-oracle-20261020` against `feat/p3-live-source-cursor-20261020`.
- Evaluator: pinned-reference strict JSON/quote/source-SHA checks across TWO task families; **mechanical reference comparison**, not independently accepted semantic oracle.
- Added `src/cognition_agent_os/reference_model.py` and CLI `reference-propose-local`: only explicitly installed local Ollama model on fixed loopback, no auto-download, no cloud provider, model output is untrusted candidate JSON. Reference pack's gold never sent by this API.
- Tests `tests/test_reference_model.py` include simulated loopback contract, model missing, cloud names refused, malformed/self-graded answers, no database creation. **No real Ollama weights have been run**.
- Latest tested functional commit before this handoff: `8bc8f865bfdcc72deb91059396163b9a10f062eb`.
- GitHub Actions run `39419105254`: offline_regression SUCCESS, **61 Python tests**; live_public_source SKIPPED BY DESIGN. An earlier P3 run `39415344574` has real GitHub-source PASS but must not be promoted to proof of this turn's live validation.
- CI architecture now correctly isolates offline safety regressions from opt-in external public GitHub API tests. Earlier P4 runs: one testing-command bug (fixed), one transient SOURCE_UNAVAILABLE after 56 tests passed. Exact upstream HTTP cause unknown.
- Zero remote AI API/token-credit spend, zero paid tools. `main` untouched. Do not merge stacked Draft PRs before acceptance.

**Evidence needed to exit current P4**: independently curated and truly withheld cases with professional ground truth / executable domain oracle; separately secured reference not viewable by the model; real installed local model predictions; heldout positive/negative/unknown impact acceptance; source and business outcome checks. Missing external reviewer and physical user Windows host are real external constraints; they are NOT grounds to falsely claim all other future autonomous engineering work is done.

**Next capability for main objective**: bounded autonomous goal-decomposition → evidence acquisition → competing causal hypothesis/solution → controlled action → independently observed outcome → knowledge revision/generalization, across at least two genuinely executed business families, with safety and resource limits. Test against adversarial and unfamiliar cases; no more monitoring-only substitution.

## 2026-10-20 P4 reference-evaluation increment — CURRENT TOP CHECKPOINT

The main objective remains a general self-directed cognition/execution system, **not** an accumulation of watchers or test count. Current candidate work is in `D1traverser-debug/cognition-agent-os`, pending Draft PR #6 (stacked on #5):
https://github.com/D1traverser-debug/cognition-agent-os/pull/6

**Code and evidence (check current PR head before trusting historical identifiers):**
- P4 evaluation module: `src/cognition_agent_os/evaluation.py`.
- Read-only CLI: `reference-export` (model-visible evidence without gold) and `reference-evaluate` (strict pinned reference-agreement checker). Neither initializes task DB or authorizes writes.
- Six curated demonstration reference cases in `evaluation/curated_demo_reference.json`, covering BOTH protocol impact and incident triage with SUPPORTED / REFUTED / INSUFFICIENT classes.
- Adversarial, no-network/no-database and two-family controls: `tests/test_evaluation.py`.
- Design limitations and honest trust boundaries: `docs/09-PINNED-REFERENCE-EVALUATION.md`.
- Work after P3 included strict unexpected-JSON checks and one tests-only CLI-argument correction. The first P4 CI run failed one malformed test invocation; subsequent run showed **56/56 local cases OK** but then failed on a real public GitHub `SOURCE_UNAVAILABLE` smoke. Exact HTTP cause not established, so not described as proven rate limit.
- Corrected CI semantics: on PRs always run **offline local regression**; separately preserve an explicit `workflow_dispatch` **live_public_source** job so transient public API outages cannot be portrayed as code regressions or green external checks.
- Verified commit immediately before this checkpoint: `0eeadadfd018e13232fe63ecf9422bc5fb442c64`; Actions run `39418479792`: offline_regression SUCCESS, 56 tests; live_public_source SKIPPED (NOT VERIFIED in that run). Prior P3 live GitHub smoke was positively observed in run `39415344574`.
- Zero remote model tokens/credits, paid APIs, and cloud services used; `main` untouched.

**What P4 does NOT establish:**
The gold labels were developed within the same code change and checked into the PUBLIC repo. This is a reliable *mechanical reference checker* plus regressions, **not** a blind, third-party, or independent semantic evaluator. No local Ollama model predictions or genuine unseen task results have been measured. A `REFERENCE_MATCH` is not user-goal verification or production mutation admission. Native Windows Task Scheduler unattended wake-up is still unobserved.

**Next meaningful actions:**
1. Current P4 PR #6 CI and main baseline reread; keep in Draft until independent acceptance.
2. Obtain/model a genuinely **external and objective acceptance oracle** or verified reviewer-labeled sealed cases, with clear source/label provenance and realistic holdout. Avoid confusing synthetic fixture success with transfer.
3. Connect P4 evaluator to a real bounded proposal for a second task family (not just static sample QA), feed genuine local-model predictions only if an already-installed model and host exist; never auto-pull or spend remote tokens.
4. Continue toward self-initiated goal decomposition, causal hypotheses/contradiction testing, systemic repair, held-out transfer and post-action verification. Distinguish `code tested`, `host observed`, `semantic outcome proven`. User need not repeatedly remind Agent of this objective.
5. Explicit user's Windows installation/permissions and independent qualified semantic review are true external constraints on physical claims; continue any other authorized software validation when these are unavailable.

## 2026-10-20 P3 verified extension — current resume point

This section supersedes the previous "Next priorities" when the two differ;
historical P2 evidence below is retained as historical.

- Project owner candidate branch: `feat/p3-live-source-cursor-20261020`.
- New Draft PR #5 (stacked on #4): https://github.com/D1traverser-debug/cognition-agent-os/pull/5.
- Last tested code commit before this checkpoint: `3f139536e022cdad25f69e246963580dff835f89`.
- GitHub Actions run `39415197547`: **success**, 43 unittest cases OK (4.575s).
  The CI ran two genuine unauthenticated-public-API checks: (a) mutable
  branch HEAD to pinned SHA/blob with initial BASELINED/no artificial job;
  (b) real old/new immutable modelcontextprotocol specification docs
  producing CHANGE_REQUIRES_REVIEW vs same-source NO_CHANGE with file readback.
- Functional P3 components: `src/cognition_agent_os/watch.py`,
  branch resolver in `source.py`, `seed-watch-github` CLI, `host-tick`
  integration, status/audit, `tests/test_watch.py`, `docs/08-LIVE-SOURCE-CURSOR.md`.
  SQLite cursor and immutable evidence-task insert occur in one transaction;
  concurrent observers use cursor_epoch optimism; pre/post-network write
  authority checks; source failures do not advance the evidence cursor.
- CI initially failed on missing/mis-escaped regex, which was repaired and
  reverified. External JSON shape hardening was also added and regression-tested.
- No cloud model calls, AI tokens, credit allotments or paid tools used by the code.

**Unverified**: Windows Task Scheduler installation/real offline wake-ups; live
external *future changed commit* moving during a running watcher (tested with
fault-injected snapshots, not live third-party commits); semantic impact of a
spec edit; independent goal outcome; automatic goal breakdown; cross-domain
unknown-problem discovery; systematic autonomous repair; true always-on agent.

**Next independent outcome (P4)**: build an evidence-grounded evaluation and
human-curated/holdout oracle gate that can score a bounded local-model proposal
against independently curated affected/unaffected cases without letting the
proposing model mark itself PASS; then demonstrate a distinct second task family
beyond GitHub watcher. Keep original long-term autonomous cognition mission
in scope. Remote model APIs, trial credits and finite AI credits prohibited.
Local open-source model allowed only if already installed and explicitly
selected; no claims of installed model tests until observed.

Checkpoint date: 2026-10-20. Repository: `D1traverser-debug/cognition-agent-os`. This file is a checkpoint, not an independently executing agent or permission to mutate production.

## Governing objective

Build a self-directed cognition/execution system that takes user outcomes and bounded authority, researches and challenges causal assumptions, acts, independently verifies results, discovers systemic failure classes, repairs and learns without relying on repeated user correction. Keep the system valuable to real tasks, not merely a software specification diff monitor.

Binding budget constraint: no remote LLM usage billed per token; no AI trials, limited free credits or paid services. Default deterministic, model calls zero. An existing optional installed local Ollama model is allowed only when explicitly configured and cannot approve its own conclusions. The user's Windows 11 computer is the candidate host, not assumed deployed.

## Exact repo topology and fresh evidence

- `main`: legacy initial README only; NO P1/P2 promotion.
- Draft PR #1: architecture baseline.
- Draft PR #2: SQLite/task/grant/evidence worker prototype.
- Draft PR #3: local-only Ollama option, public source smoke, CI; head branch `feat/free-local-inference-20261020`.
- Draft PR #4: P2 Windows local host tick and durable resume; head branch `feat/local-scheduled-host-20261020`; base is PR #3 branch. URL: https://github.com/D1traverser-debug/cognition-agent-os/pull/4
- Verifiable CI for P2 before this checkpoint commit: run `39412342231`, job `118592922230`, `31 tests in 3.277s; OK`, real immutable public GitHub source smoke step PASS, associated with commit `c31848131b34fa1fa892a39c8995e6d2f5fb78d0`. New commits require new CI checks.

The actual P2 code adds `host-tick`, bounded queue draining, refused unseeded host authority, durable `host_ticks` local observations, test coverage for new process restart / no duplicate replay / missed tick / retained revocation, no-install entrypoint and an explicit-opt-in Windows Task Scheduler registration script. Docs: `docs/07-LOCAL-HOST-RECOVERY.md`.

## Verified vs not verified

VERIFIED IN GITHUB ACTIONS: 31 Python tests, real pinned public source read smoke. The developer's container Python syntax check is additional limited evidence. CI does not prove a Windows task was installed or truly woke after the chat closed.

NOT VERIFIED: a real Task Scheduler registration or unattended tick on the user's PC; independent task intake; actual locally installed LLM weight execution/quality; surprise-risk identification; competing causal theory validation; semantic or business holdout; autonomous issue repair and promotion; always-on host availability; end-to-end outcome acceptance. A static pinned pair on a recurring task repeats the same observation — it is not a live repository watcher.

## Next causal/execution priorities (in order)

1. Re-read current PR #4 head and Actions evidence. If new CI is green, keep changes in draft until physical deployment evidence; do not report autonomy finished.
2. After owner explicitly installs local host on Windows, verify independent Task Scheduler history + SQLite `host_ticks` + user-independent overdue task advancement. If no OS access, do not pretend this occurred; continue independent offline implementation/testing instead.
3. Build real **changing** source ingestion on an immutable-snapshot checkpoint scheme (branch/ref observation must resolve immutable SHA, anti-replay and authorization needed). Prove changed/unaffected cases before assuming polling is useful.
4. Add outcome-grounded semantic judgments and an independent holdout oracle before any autonomous solution promotion. Study other task families to prevent one-demo architecture.
5. Only then implement bounded autonomous goal decomposition, systemic causal repair and post-change observation. No broad-purpose agent is complete until real held-out task outcomes are proven.

## Continuation contract

Recover parent reference from `D1traverser-debug/universal-agent-os@main:ENTRYPOINT.md` and `CURRENT_SYSTEM.json`; current independent project repository is the owner of cognition-agent-os project code and candidate evidence. `uaos-controller-runtime` is a behavioral dispatcher, not verifiable native ChatGPT interception. Respect candidate branch → PR → owner CI → controlled promotion → reread. Reassess the actual outcome before choosing next work; use current repo evidence over memories or this checkpoint if inconsistent. Never treat a PR, synthetic fixtures or model self-rating as independent evidence of real autonomy.
