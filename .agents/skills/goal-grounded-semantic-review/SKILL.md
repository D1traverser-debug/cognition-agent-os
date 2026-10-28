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

## Multiple faults are separate obligations until disproved

When the owner names multiple defects or repeatedly corrects the agent, recover **every** item from direct utterances, including formatting, requirement interpretation, method choice, actual client loading and real outcomes. For EACH item record observable failure, competing causes, evidence/search coverage, different remedies, a preferred-route falsifier and acceptance status in the current work evidence—not a new registry. Shared root causes must be **demonstrated**, never assumed from labels like "context pollution." Study original implementations and independent failure cases before comparison; after choosing a remedy challenge it AGAIN with the neglected neighbor case. A remaining item is OPEN, not silently absorbed into a successful subtask.

## Discover, verify, and select unfamiliar methods without waiting for a tool list

Use a **source-discovery funnel**, scaled to the unknown and not a fixed
requirement to call every service on every task:

1. Translate the **owner's actual missing capability / failure invariant**
   into multiple search queries, including alternate project names, source
   categories, counterexamples, migration and security terms. Start from
   first-hand local entrypoints and evidence of the failure, not whichever
   tool the user or model mentioned most recently.
2. **Discover candidates**, not truth: relevant GitHub repositories and
   releases, official MCP registry, package-download and GitHub Trending/
   star-growth lists; niche questions may first surface in Reddit, X,
   小红书 or practitioner issue threads. Record the exact post, date, author
   and link where accessible; if a social post is inaccessible or the
   project's identity is ambiguous, mark UNKNOWN instead of borrowing
   another project's reputation. Stars, downloads, endorsements, demo
   videos and search rank are weak discovery signals, never correctness,
   permissions or safety evidence.
3. **Verify the actual mechanism**: open canonical repository and license,
   current tagged release, source implementation, API/tool schemas,
   official documentation, reproducible tests, unresolved issues,
   vulnerabilities, maintenance status, migrations, known failures and
   deployment/authentication/cost requirements. Distinguish a reference
   MCP test server from production capability, a transient reasoning
   transcript from durable memory, a graph of code calls from semantic
   evidence, and a retrieval result from an independently proved fact.
   Follow promising social leads to these primary sources; do not stop at
   paraphrasing a post or README.
4. **Compare real competing pathways** against the same failure and owner
   outcome: existing tool/interface, adaption of a mature implementation,
   replace a deficient component, add a narrowly authorized adapter, or
   abstain/research further. For each viable option specify the part it
   would replace, how it composes with current grant/Host/SQLite, immutable
   source/version provenance, failure and rollback mode, true usage/hosting
   cost, and the observation that would falsify the choice. Do not
   implicitly prefer a keyword the owner supplied or the newest framework.
5. **Test before promoting reusable knowledge**: use an isolated frozen
   baseline with a previously unseen relevant case, a counterexample and
   an unchanged-evidence/retry case; compare owner-level independent
   outcome, costs and regressions, not just model opinions or green CI.
   Write a concise decision and original links into the EXISTING active
   PR/runtime event evidence with the winning method's applicability,
   competing explanation, verified result, rejected candidate, and
   reopen condition. Never create a second parent memory or permanent
   dependency simply to record a search.

## Primary-source atlas for autonomous Agent research (verified 2026-10-28)

The owner-provided [Datawhale Agent-Learning-Hub](https://github.com/datawhalechina/Agent-Learning-Hub/tree/dddf777dde6788228136862f270203424a28efbc) is the **discovery map**, NOT a substitute for reading implementations or an authority to install/execute tools. At this pinned revision its entire Git tree has **five files** (`README.md`, `index.html`, `CONTRIBUTING.md`, `LICENSE`, `.gitignore`), with **96 unique links in README**. The HTML mostly presents the same materials. We inspected both main content files and contribution quality rules. All 96 links were inventoried; **NOT all 96 external destinations have been studied**. This scope distinction is part of source provenance, not a reason to stop relevant research.

Route **by the actual failing invariant**, never by a vendor name or star count. These are code/doc primary-source starting points at pinned revisions, not universal solutions:

| Observed missing behavior | Read actual mechanism, then probe its limitations | Reuse decision for cognition-agent-os |
| --- | --- | --- |
| Tool-call loop returns a final answer while owner obligations remain OPEN | [learn-claude-code s17 Goal Loop](https://github.com/shareAI-lab/learn-claude-code/blob/7226f555d48900076eba126acf37c9ed5f002b5d/s17_goal_loop/code.py): `GoalController.evaluate_after_turn` blocks completion and sends unfinished evidence back; `PromptGoalEvaluator` has **no tools** and relies on a second model reading the transcript. Check [its tests](https://github.com/shareAI-lab/learn-claude-code/tree/7226f555d48900076eba126acf37c9ed5f002b5d/tests). | Adapt a bounded post-action stop check **using independent owner/postcondition evidence**, not a second LLM's self-assessment as business truth. A ChatGPT Skill cannot install a native Stop hook by itself. |
| Unknown tool or MCP advertised capability | [learn-claude-code s14](https://github.com/shareAI-lab/learn-claude-code/blob/7226f555d48900076eba126acf37c9ed5f002b5d/s14_mcp_plugin/code.py): `connect_mcp` expands a tool pool; its `MCPClient` is explicitly an **in-process stand-in**, not proof of a real network MCP transport. See the [official MCP security specification](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices). | Separate candidate discovery, schema inspection, actual client/server capability, account consent, Host grant, effect and independent readback. Do not turn a research lead into an executor. |
| Prior research, corrections or context are lost on next turn | [learn-claude-code s09](https://github.com/shareAI-lab/learn-claude-code/blob/7226f555d48900076eba126acf37c9ed5f002b5d/s09_memory/code.py): memory files + compact index + relevant retrieval + fallback; [Hello-Agents ch8](https://github.com/datawhalechina/hello-agents/blob/36f583c233ea5cee4537ef93455702b55053af18/docs/chapter8/%E7%AC%AC%E5%85%AB%E7%AB%A0%20%E8%AE%B0%E5%BF%86%E4%B8%8E%E6%A3%80%E7%B4%A2.md) and [ch9](https://github.com/datawhalechina/hello-agents/blob/36f583c233ea5cee4537ef93455702b55053af18/docs/chapter9/%E7%AC%AC%E4%B9%9D%E7%AB%A0%20%E4%B8%8A%E4%B8%8B%E6%96%87%E5%B7%A5%E7%A8%8B.md): separate memory, retrieval, working context and source exploration. | Keep the existing authoritative SQLite/goal events and short evidence-index retrieval; replay exact original goal and contrary findings. No second ungrounded memory database or unverified semantic-memory promotion. |
| Interrupted or concurrent long-running job | [learn-claude-code s16](https://github.com/shareAI-lab/learn-claude-code/blob/7226f555d48900076eba126acf37c9ed5f002b5d/s16_workflow_runtime/code.py): append-only semantic-key journal and replay; [claw0 s07](https://github.com/shareAI-lab/claw0/blob/0fbf0eb1bd6515fa5b8faf90067b47128df8f45a/sessions/zh/s07_heartbeat_cron.py), [s09](https://github.com/shareAI-lab/claw0/blob/0fbf0eb1bd6515fa5b8faf90067b47128df8f45a/sessions/zh/s09_resilience.py), [s10](https://github.com/shareAI-lab/claw0/blob/0fbf0eb1bd6515fa5b8faf90067b47128df8f45a/sessions/zh/s10_concurrency.py): heartbeat, failure-class-specific retry/compaction and generation-fenced named queues. | Check the current Host lease/idempotency/recovery FIRST. Reuse bounded action/effect replay; never assume cached model output means an external effect occurred exactly once. No unauthorized always-on process or paid key rotation. |
| Loading a skill might silently become execution | [CyberClaw `skill_loader.py`](https://github.com/ttguy0707/CyberClaw/blob/12b7c6d52fcc38e134cd0f1aeb7aba420ad23274/cyberclaw/core/skill_loader.py): one-use, expiring, session+source-version-bound help→run credential; `README.md` explicitly says it proves **manual delivery, not user consent**. | Borrow version/stale/replay falsifiers only where current Host grant lacks them. Reading a Skill or knowing its name never grants shell or domain actions. |
| Persisted state is mistaken for durable knowledge, or green tests for owner success | [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) distinguishes **per-thread checkpoints** from **cross-thread stores**; [Hello-Agents ch12](https://github.com/datawhalechina/hello-agents/blob/36f583c233ea5cee4537ef93455702b55053af18/docs/chapter12/%E7%AC%AC%E5%8D%81%E4%BA%8C%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E6%80%A7%E8%83%BD%E8%AF%84%E4%BC%B0.md) covers function-calling/evaluation benchmarks. | Preserve task checkpoint vs reusable *verified* research distinction. Compare genuine owner outcomes, repeated-run reliability, tool traces, legal negative cases and correction burden; neither a checkpoint nor BFCL/CI is the real business oracle. |

**Knowledge-promotion rule:** Capture one causal claim with `source_url`, immutable source SHA/ref, observed implementation/test section, applicable owner failure, competing explanation, demonstrated counterexample, independent result and `UNTESTED` status where appropriate. A source is a *lead* until compared with a second meaningful alternative and exercised against the target's actual entrypoint. Revalidate upstream HEAD before reuse. Avoid copying entire third-party repos or flooding the model context. The pinned map makes source discovery reproducible; it does not mean ChatGPT's private memory, the Codex session, or the product's Host SQLite has been automatically synchronized.

For **unfamiliar professional business domains**, this hub supplies **Agent engineering methods**, not veterinary/financial/legal/engineering domain truth. Follow the learning method into the relevant discipline's standards, primary data, tools and independent expert/biz oracles. If the allowed runtime has no lawful research/action surface, record that boundary as OPEN rather than manufacturing a plan or asking the owner for a tool catalogue.

Practical role distinctions: AOCI-like governed indices and Graphify-like
AST dependency graphs can locate source/code context but not judge an
external business result. Filesystem MCP is an effect-capable file
interface requiring scoped path grants. Sequential Thinking is a
revision/branching aid, not independently verified research or durable
cross-session state by itself. Memory MCP, Hindsight or RAG can RETRIEVE
potential knowledge but cannot authorize a changed action. Everything is
a protocol conformance server; n8n-MCP needs real workflow credentials
and an effect boundary. Harness-RSI-style candidate trials require a
frozen independent evaluator and keep/revert, not recursive self-approval.
These are research examples, **not installation decisions**. Compare
fresh releases and first-hand evidence whenever materially relevant.

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

## Evidence-driven recursive challenge and transferable method

On EVERY substantive decision, question the current diagnosis AND the method
used to reach it. Do not guess whether an issue is "local", "upper" or
"architectural" beforehand: inspect competing causes and escalate across
boundaries when observations warrant it. Repeated objections with no new source,
counterexample, outcome feedback or changed executable plan are not research
progress. A resource limit is not an epistemic stopping criterion: preserve
the unproved owner obligation and the verified evidence needed to continue.

After a contradicted hypothesis, explicitly compare whether to investigate
more original evidence, change the method, revise the workflow, or challenge
a governing design assumption. Research new domains and alternatives at the
original implementation level before selection, then challenge the preferred
adaptation AGAIN. Record reusable methods only with exact source provenance,
applicability conditions, counterexamples, failure/rollback conditions and an
independent result; transfer to a different domain is still NOT_TESTED until
that domain actually verifies it. Do not promote a successful single fixture
or a model-authored summary to universal SOP.

## Verify before claiming completion

1. Establish a failing/positive baseline and predeclared acceptance criteria where feasible.
2. Introduce adversarial cases: revoked grant, stale or conflicting source, reused identifiers, cold resume, interrupted effect, failed external acknowledgment, inapplicable method and lawful sibling operation (when relevant to the changed behavior).
3. Run tests against actual entrypoints and observable state; separate synthetic fixture correctness from original-source or real external truth. Independent oracles cannot silently depend on the implementation's own decision logic.
4. Re-run focused and broad regression, cross-platform where applicable. Check exact-HEAD GitHub Actions status, not an earlier successful run.
5. Report: what changed, *why this remedy*, source links, falsifying tests and observed results, unresolved semantics, skipped cases, limits and owner-meaningful outcome. Do not present CI, documentation completeness, repository inventory, or self-issued receipts as full semantic proof.

## Output discipline

Do not generate a new sprawling prompt, parallel task registry or standalone historical report by default. For authorized in-scope work, correct observed failures and rerun tests until the behavioral acceptance criteria are satisfied or an evidenced blocker/permission boundary stops execution. Do not stop at the first code diff, green command or explanation. For routine work, concise decision + diffs + independent receipts suffice. For a genuinely full semantic audit, a per-behavior matrix is required, and any incomplete entry stays explicitly OPEN. If no action is authorized, perform read-only research and identify the blocking boundary instead of pretending execution.

**Empirical skill evaluation:** File presence, YAML validity and regular CI do not prove that Codex loaded this Skill or followed it. Compare real captured agent runs with/without it on positive and negative trigger cases, original-source fidelity, actual outcome, independent verification, unnecessary work and owner correction burden; do not claim stable transfer before those evaluations.
