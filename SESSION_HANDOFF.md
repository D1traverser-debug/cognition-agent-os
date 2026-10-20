# cognition-agent-os — durable continuation checkpoint

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
