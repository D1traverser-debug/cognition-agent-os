# P34 — Runtime-discovered knowledge deficit → bounded research task in the original host

## Strategic alignment

This is a specific slice of the user's larger mandate: independently detect goal-relevant capability gaps, research the domain, compare competing explanations/methods, execute only with proper authority, verify actual outcomes, and continue the system-wide mission without repeatedly redirecting the user into debugging unrelated GitHub benchmarks. Consult `docs/00-PRODUCT-CONOPS.md` (OT03, OT08, OT13), `docs/01-ARCHITECTURE-DECISIONS.md`, `docs/44-KNOWLEDGE-TO-ACTION-REAL-HOST.md`, and Library `/Continuity/General_Learning/INDEX.md` / the 2026-10-19 all-domain Learning Atlas. The published ConOps is still PROPOSED, not a production authorization.

In P33 a manually seeded `knowledge_intent` could select either of two already authorized registered intents, or return `UNKNOWN` if no trustworthy-by-format claim fit the exact goal. That created an actual dead end even where the task owner had allowed investigation, with no durable work item identifying what must be learned. A generated "research done" response would have been false and unsafe; a standalone monitor/second agent would fragment the original task authority.

## P34 actual runtime implementation, authority boundaries

- `research_on_gap: true` is an **explicit task-owner opt-in** extension of the same `knowledge_intent` schema. Existing P33 tasks without this opt-in retain their original unknown/refusal behavior; no new remote tools, LLM, permissions, budget or production execution rights.
- `src/cognition_agent_os/research_gap.py::classify_research_gap` reopens the exact SHA256-pinned, size-bounded JSON evidence, validates source identity and schema, compares **exact goal key** with registered, prevalidated alternatives; it returns one of `NO_EXACT_GOAL_CLAIM`, `CONFLICTING_CLAIMS`, `WITHDRAWN_CLAIM`, or `UNREGISTERED_ROUTE`. No source, mismatched digest or malformed knowledge fails closed: **never fabricate a missing scholarly claim**. A single applicable active claim continues the old authorized execution path, without unnecessary research.
- When P33's route selection cannot find a valid decision, the existing `run_knowledge_intent` calls `enqueue_research_gap`. Inside the original SQLite `BEGIN IMMEDIATE` claim lock it checks **current claim token, goal revision and write grant**, rereads the source and confirms the exact gap; in one transaction it creates exactly one descendant `research_gap` task, updates the parent to `RESEARCH_NEEDED`, and emits a single `KNOWLEDGE_RESEARCH_REQUESTED` durable event containing issue class, evidence hash and both registered alternatives. Crash before commit cannot leave a half-admitted research task; lease takeover or goal/grant change blocks admission.
- The ordinary `runner.run_once` dispatches this descendant in the very same task/lease/authority. It checks the parent's existing research request and current source evidence; it generates a bounded immutable local `artifacts/<child_task_id>.json` through the previously verified `store_once` writer, without writing any business source or calling a model. The agenda contains the goal, pinned evidence identity, two already-authorized route capabilities/plan hashes, **a concrete discriminating research question**, source freshness/contradiction needs and flags: `status=RESEARCH_REQUEST_NOT_ANSWER`, `source_trust_proven=false`, `business_outcome_verified=false`, `production_effect_authorized=false`. This is an **actionable research demand**, not an assertion that research, choice or user outcome has been completed. The child is `NEEDS_REVIEW`.
- Original `conformance.inspect_conformance` now includes `RESEARCH_NEEDED` as a first-class evidence state and independently checks both parent and unapproved child using read-only `audit_gap`. Verification re-evaluates the current exact-source gap, original task's authorization lineage, only child identity and event, and verifies that a candidate artifact has identical derived content and the originally claimed SHA256. Invalid/withdrawn source or tampered agenda triggers **native task quarantine**, including dependent tasks where justified; no new alert-only subsystem or separate authority.
- The existing `knowledge_dependencies` recheck in `run_once` remains for P33 selected-child tasks. P34 research child performs its own strict parent/knowledge/agenda checks (including inside the original artifact commit lock). Same owner-approved routes, no auto-approval or new registered action.

## Genuine red-first and independent result

Initial **[Actions #39644114850](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39644114850)** on RED test-only source: Linux **366 tests, exactly 3 FAIL**, showing old runner returned `UNKNOWN` rather than auto-enqueue and execute bounded research for missing, conflicting and withdrawn-but-valid knowledge. Goal-revision, missing source and default legacy-refusal controls passed; no 7B run.

First code-pass [Actions #39644664282](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39644664282): Linux **366/366** and real no-network Docker integration PASS after integrating original ledger, runner, knowledge route and conformance (not proof of broad self-learning).

Extended nine P34 assertions are in `tests/test_p34_research_gap.py`. Latest before archive [Actions #39645023720](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39645023720) has Linux **369/369** and real no-network Docker PASS at time of report authoring; final Windows results and fully successful final HEAD must be inspected separately. These tests use a real ephemeral SQLite ledger, original host tick and filesystem artifacts, not fabricated study completions:
1. No exact goal claim -> one durable parent `RESEARCH_NEEDED`, one child `NEEDS_REVIEW`, readable source-preserving agenda; no infinite re-enqueue on restart.
2. Two contradictory applicable claims -> research demand naming conflict, **no selected route**.
3. Withdrawn claim -> research demand, then changed evidence drives native quarantine, not invented research answer.
4. Old non-opted-in `knowledge_intent` -> remains `UNKNOWN` while independent legitimate queued fixture reaches `VERIFIED`.
5. Goal revision before admission -> `BLOCKED`, zero child, no research side effect.
6. Missing pinned source -> `UNKNOWN`, no child.
7. Source changed after parent request but before child execution -> child `UNKNOWN`, independent fixture still progresses, no agenda file.
8. Direct malicious/accidental `research_gap` seeding without genuine parent event -> rejected; no artifact or authority mint.
9. Tampered agenda after generation -> otherwise-idle original host conformance detects and revokes child claim; no business source write.

This P34 path is a **real automatic gap recognition and safe research-work generation from observed task feedback**, rather than a simulation of a model that somehow knows the answer. It is NOT general knowledge discovery or autonomous research of external sources.

## Unsolved edges / next phase

1. The inputs (`goal_key`, exact knowledge file and two authorized routes) are still owner-seeded. The system cannot yet decide **which previously unseen domain knowledge to look for** from arbitrary natural-language goals.
2. `research_gap` creates and reviews a research **agenda**, it does not obtain independent external materials, weigh author reputation/evidence quality, generate verified new claims or re-plan the original goal from acquired sources. Conformance proves mechanical origin and scope, not epistemic truth.
3. The SQLite lock cannot transactionally lock an arbitrary filesystem against sophisticated malicious swaps; accepted staged agenda is only local data. No external accounts, real trades, production writes or owner-host deployment.
4. P35 should make a previously admitted research demand consume **two independent bounded read-only sources** and produce **comparative evidence with traceability and abstention**, before ever allowing an upgraded route. Separate retrieval, source credibility and relevance from decision and grant; reject forged "knowledge learned" from a generated report. Test both a truly useful new source and credible-but-inapplicable near neighbor plus explicit no-learning-needed case. Consider additional cross-disciplinary practices only when they improve measured goal-specific outcomes; do NOT restart foreign GitHub benchmark loops.

Archive HEAD and final post-archive four-platform CI must be checked and attached to existing Draft PR #12 via comment; the report itself must not be treated as a passed CI witness.
