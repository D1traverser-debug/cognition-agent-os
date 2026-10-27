# P33 — Goal-relevant knowledge selects real authorized work, not another repair benchmark

## Why P33 was redirected

Original product definition `docs/00-PRODUCT-CONOPS.md`, especially OT03, OT08 and OT13, and the architecture candidate `docs/01-ARCHITECTURE-DECISIONS.md` specify a **complete autonomous control system**: identify actual capability gaps, learn from evidence, select among permissible actions, execute with a real host and authoritative ledger, independently check outcomes, diagnose and improve without making the owner the internal monitor. The cross-disciplinary Learning Atlas (`/Continuity/General_Learning/INDEX.md`; `2026-10-19/SYSTEM_WIDE_LEARNING_ATLAS_20261019.md`) likewise warns against letting one local research theme swallow the whole mission. These are research and design inputs, not proof that a learned policy is already installed.

P25–P30 runtime conformance fixes were valid localized engineering; P31–P32 external issues were genuine, bounded model experiments but should **not** determine the product roadmap. The user's 2026-10-22 correction exposed this drift. P33 therefore did NOT select another outside code-repair issue, re-run 7B, install owner-host software, or invent a new monitoring service.

## Audited implementation gap, before coding

`host.run_tick` invokes `runner.run_once` and the original single SQLite task authority. `intent_planner.compile_intent` already maps explicitly typed objectives to two registered families (`goal_case` JSON structure repair, `record_reconciliation` CSV discrepancy analysis), but it does not retrieve, challenge or apply the versioned learning library. Existing `goal_intent` always resolves its owner-supplied intent, and P31/P32 issue choices were manually selected outside host.

**P33 bounded slice** connects a content-addressed knowledge observation to **selection between two owner-preauthorized registered intent alternatives**. It does **NOT** solve autonomous scholarly retrieval, knowledge truth, unrestricted model planning, or continuous deployment. Source IDs and `source_ref` are untrusted textual labels; a SHA256 pins bytes and prevents unnoticed substitution but does not authenticate a researcher or prove a claim.

## Actual integrated path

1. An explicitly seeded `knowledge_intent` task specifies an exact `goal_key`, a relative in-scope knowledge fixture path + SHA256 + `source_id`, and **exactly two** typed `goal_intent` alternative routes. The original compiler validates **both** candidate intents before selection. A retrieved claim cannot add capabilities, shell code, arbitrary destinations, permissions, or goals: the task owner must have pre-enumerated the alternatives, and existing grant rules remain authoritative.
2. `knowledge_routing.resolve_knowledge_route` reads the bounded fixture as untrusted JSON; requires exact `goal_key` and `source_id`, a single `active` matching claim, a recognized route, strict keys and original bytes equal to pinned SHA256. Nearby spellings, missing/withdrawn claims, contradictory matches, changed bytes and invalid source paths fail closed. No fuzzy similarity or untrusted instruction following.
3. `runner.run_once` dispatches this new typed task family. `run_knowledge_intent` resolves the route **again inside the original `BEGIN IMMEDIATE` ledger transaction**, checks the current token, goal revision and write grant, creates the chosen already-registered child spec, records `knowledge_dependencies` in **the same original SQLite database**, and commits a `KNOWLEDGE_INTENT_DECOMPOSED` event with selected route, evidence SHA, source reference and plan hash.
4. Before any admitted dependent child enters an executor, `run_once` re-checks the pinned fixture hash. Removed/revised evidence returns `UNKNOWN/KNOWLEDGE_SOURCE_CHANGED`, not an optimistic success. Existing JSON and CSV capability implementations still perform their own independent checks and local-only stage/report semantics.
5. The existing native conformance engine was extended, **not forked**: `audit_knowledge_intent_plan` independently opens a read-only SQLite snapshot, recomputes the knowledge decision against current pinned source, checks the persisted event, exactly one child, matching plan/goal/grant and the child's evidence dependency. On subsequent host ticks, a withdrawn source triggers native conformance quarantine of both the invalid parent and dependent success claims without user prompting.

These are a **causal runtime route and enforced evidence-dependency contract**, not a passive alert, another tool catalog or independently authoritative agent. Effects remain local/sandbox-only and `host.run_tick` still honestly states `semantic_outcome_verified=false`.

## Independent falsification and regression

**Red-first** test-only [Actions #39640622223](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39640622223) on older runtime, 359 Linux tests: five new failures and one error across six new knowledge-routing tests. The original worker did not know the new typed task, so returned `UNKNOWN` / source unavailable rather than executing the chosen route. This is capability absence, not evidence of a production learner silently making incorrect decisions.

**Integration fault exposed by tests:** intermediate [Actions #39640980552](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39640980552) had two test errors even after routing worked. The original conformance engine audited all `DECOMPOSED` tasks through old `audit_intent_plan` and quarantined the new task incorrectly; stage could not proceed and a later task was no longer due. Added **independent provenance audit** and integrated it into the same conformance path; also initialized the actual sandbox fixture workspace.

**Final pre-archive [Actions #39642076498](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39642076498) COMPLETED/SUCCESS:** Linux **360/360** tests with **seven P33 cases PASS**, Windows offline regression PASS, real no-network Docker integration PASS, hosted Windows native user-scoped Scheduled Task PASS; all optional real 7B/live-source model jobs SKIPPED.

Seven tests `tests/test_p33_knowledge_routing.py` cover:
- Pinned evidence selects `ensure_structure`; full real host calls original compiler, JSON goal worker and sandbox, producing readable candidate `{"keep":"value","owner":"ops"}` without modifying the input source.
- Distinct pinned evidence selects the **other** registered `compare_records` capability, producing a real reconciliation result with one observed discrepancy; no JSON sandbox side effect.
- Two negative claims (near-neighbor goal key and withdrawn source) fail closed while a queued **independent legitimate task still reaches VERIFIED**.
- Contradictory active claims cannot silently pick the first match.
- Original selected evidence changes between host ticks: dependent child cannot execute.
- Authority `goal_rev` rotates during knowledge resolution: no child is admitted; task is `BLOCKED/STALE_GOAL`.
- **No new task required:** after a staged, mechanically verified JSON child, knowledge evidence is withdrawn; the next default host conformance scan independently revokes the parent and dependent successful state, preserving source bytes.

No model success rate, source credibility or real business acceptance is inferred from this fixture-bounded experiment. The Library's full learning collection is **not directly accessible from this standalone GitHub runner** and was not silently connected; manually supplied structured evidence is an explicit integration seam. The sandbox result is a *local candidate*, not a production write.

## Remaining highest-impact gaps

- **Automatic gap discovery and actual scholarly research** are not yet implemented. Current `knowledge_intent` and vetted routes must be explicitly seeded by a trustworthy caller. Selecting a pre-existing claim does not constitute self-learning.
- **Authenticating/evaluating external knowledge** beyond exact bytes remains open: content hashes are identity, not truth. Contradictory/withdrawn source and unrelated-neighbor rejection are mechanical safeguards, not source epistemology.
- **Knowledge/goal lineage across every existing task family and effect boundary**, not just P33 registered child paths, is not proven. Arbitrary in-flight filesystem swaps cannot be made atomic merely by SQLite.
- **Outcome-level user goals and correction burden** still require real cross-domain pilot/workflows, not CI count or static fixtures. No real continuous owner host deployment, finance trading authority, or production actions were requested or granted.

Next P34 candidate (not automatic scope expansion): derive a **bounded research-needed task** from an actual unhandled or contradictory knowledge requirement in normal host operation, compare useful alternatives from independently sourced material, verify the selected legal action and revise the knowledge dependency graph. First prove the existing runtime decision fails on a goal-relevant unseen case; avoid external GitHub benchmark inertia and new duplicate authority. Only broaden model autonomy after independent limits/risks are evaluated.

Final-head CI after this report and `SESSION_HANDOFF.md` must be verified separately; record the result as a PR comment, not another self-triggering source commit.
