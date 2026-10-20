# cognition-agent-os — durable continuation checkpoint

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
