---
name: goal-grounded-semantic-review
description: Independently investigate ambiguous owner requirements, competing architecture choices, recurrent failures and evidence quality in cognition-agent-os. Use for substantial semantic reviews or conflicting knowledge, not ordinary well-specified edits.
---

# Goal-grounded semantic review

This is an **on-demand method**, not a second controller, standing prompt, grant, release gate or claim that all files were read. Do not trigger just because a task mentions code, a goal or a database. Follow the repo-root `AGENTS.md` and actual owner permissions.

## Start at the original source, not the last summary

1. Resolve the current GitHub integration head, relevant ancestry and exact revision of each file. Retrieve the user's *original* stated objective and later explicit amendments, rejections and constraints. If original private user source is unavailable, say **UNVERIFIED_ORIGINAL_SOURCE**; do not use a paraphrased ConOps as proof.
2. Recover the earliest applicable design decision, genuine failure logs and actual implementation/test diffs. Do not confuse the archived `SESSION_HANDOFF` headings or proposed R/OT/G identifiers with current instructions. Historical claims need date, source, applicability and explicit supersession.
3. Define the smallest meaningful behavior boundary before expanding research: input/goal, authority, state, tool calls, side effects, observable outcome, lawful adjacent operations and failure/recovery paths.

## Multi-failure work: preserve the entire requested problem set

When the owner identifies several defects (including defects in the AI's own workflow), **first enumerate every distinct owner-named failure and every shared causal dependency** from the actual utterances. Keep a per-failure unresolved/outcome ledger *within the current task's existing decision evidence*; do not create a parallel store. A shared root cause is a hypothesis to challenge, not permission to solve only one convenient symptom. Never replace "solve all the following failures" with "choose one small fix." For each issue, independently establish:

- **Ground truth and root-cause contest:** original requested outcome; directly observed failure; which causes are proved vs merely suspected; what adjacent behavior could falsify the leading explanation.
- **Research before commitment:** search relevant primary standards, official implementation source/API semantics, actual GitHub issue/code failures and independent field/community experiences as appropriate; read beyond snippets into operational constraints and counterexamples. Mark source version and applicability. "Searched" is not "learned", and a broad source list is not proof of coverage.
- **Alternatives and second challenge:** compare at least two genuinely distinct viable remedies on completeness, fit, compatibility, safety, cost, reversibility and maintenance; explicitly attack the favored solution with a concrete opposite example **before** mass edits. Reuse existing mechanisms where sufficient; question both the owner's initial suggestions and the assistant's.
- **Act, observe, evolve:** implement within existing authority; observe actual behavior using source-of-truth readback, negative/sibling tests and user-level result; re-diagnose failed outcomes and switch methods when indicated. Retain transferable knowledge as claim + source + scope + disconfirming case + supersession in the relevant *existing* knowledge/decision location; discard invalid routes. Keep UNSOLVED and UNOBSERVED separate from verified, including when tools cannot test a native ChatGPT/Codex session.

Only synthesize a shared abstraction **after** tracing each constituent problem; do not merely relabel the whole set "context pollution", "model limitations", or "process issue". For a new class of failure that lacks empirical proof, propose a bounded, falsifiable trial and avoid promising universal compliance based on editing this Skill.

## Ask four expert questions *before* proposing the solution

1. **Omissions:** Which checks, hidden assumptions, conflicting requirements, failure conditions or alternatives would domain experts raise that the user and agent did not ask for? Distinguish necessary protections from ceremony.
2. **Primary sources:** Which original user utterance, actual source/spec, raw event/trace, independent business observation or published original research supports each material claim? Inspect raw materials rather than relying on derivative summaries.
3. **Methods and tools:** Which already proven approaches apply? Examine official Agent Skills/skill-creator conventions, context engineering, independent evaluation, requirements traceability, stateful/property testing, static analysis and current implementations *as relevant*, not as a rote checklist. Compare reuse vs modification vs deletion vs new mechanism against constraints and actual failure cases. For external or fast-changing claims, check current primary sources.
4. **Independent falsification:** What could prove the selected plan **wrong**, without trusting the implementation author's self-assessment? Establish observable checks, external source readback, negative controls, unseen cases, mutation/state-machine tests and authorized real outcomes as appropriate. State what cannot be proved by available tools.

## Decompose and trace requirements

For each behavioral requirement in scope, identify:

- Stable semantic identifier (never reuse an old identifier for a new meaning), original source/location and owner status.
- Current/superseded/proposed/unknown status, temporal and domain scope, conflicts and explicit precedence basis.
- Preconditions, postconditions, prohibited transitions, invariants and allowed neighboring behaviors.
- Actual entrypoint, all reachable relevant call paths and state/effect authority boundary; linked implementations and tests.
- Independent oracle and counterexamples, observed evidence with exact revision, environment and negative/skip outcomes.
- Disposition: VERIFIED_IN_SCOPE, FALSIFIED, NOT_TESTED, SOURCE_MISSING, SPEC_UNDECIDED or EXTERNAL_VALIDATION_REQUIRED.

For repository-wide requests, enumerate the **entire live tree** and record **individual behavior obligations**, not one pass/fail per filename or SHA. Review docs and scripts as material behavior/sources too; inert binary/assets require classification, not fabricated line semantics. Evidence must be attached to exact revisions. Do not report full coverage when any obligation is missing or unverified.

## Decide the correct root-cause intervention

Fix the actual shared failure and meet the *entire* behavioral requirement. Compare at least two meaningfully different remedies if the choice is material (e.g. original interface, compatible adapter, contract-preserving refactor, removal). Explicitly evaluate effect on external contracts, neighboring legitimate tasks, stale knowledge and recovery. Do not create a standalone authority, agent or documentation ledger merely to satisfy audit formatting.

Preserve source history immutably where possible. Knowledge selection must not equate newest with true, matching words with applicable, or archived text with authority. Model output is evidence/hypothesis until verified and authorized.

## Verify before claiming completion

1. Establish a failing/positive baseline and predeclared acceptance criteria where feasible.
2. Introduce adversarial cases: revoked grant, stale or conflicting source, reused identifiers, cold resume, interrupted effect, failed external acknowledgment, inapplicable method and lawful sibling operation (when relevant to the changed behavior).
3. Run tests against actual entrypoints and observable state; separate synthetic fixture correctness from original-source or real external truth. Independent oracles cannot silently depend on the implementation's own decision logic.
4. Re-run focused and broad regression, cross-platform where applicable. Check exact-HEAD GitHub Actions status, not an earlier successful run.
5. Report: what changed, *why this remedy*, source links, falsifying tests and observed results, unresolved semantics, skipped cases, limits and owner-meaningful outcome. Do not present CI, documentation completeness, repository inventory, or self-issued receipts as full semantic proof.

## Output discipline

Do not generate a new sprawling prompt, parallel task registry or standalone historical report by default. For authorized in-scope work, correct observed failures and rerun tests until the behavioral acceptance criteria are satisfied or an evidenced blocker/permission boundary stops execution. Do not stop at the first code diff, green command or explanation. For routine work, concise decision + diffs + independent receipts suffice. For a genuinely full semantic audit, a per-behavior matrix is required, and any incomplete entry stays explicitly OPEN. If no action is authorized, perform read-only research and identify the blocking boundary instead of pretending execution.

**Empirical skill evaluation:** File presence, YAML validity and regular CI do not prove that Codex loaded this Skill or followed it. Compare real captured agent runs with/without it on positive and negative trigger cases, original-source fidelity, actual outcome, independent verification, unnecessary work and owner correction burden; do not claim stable transfer before those evaluations.
