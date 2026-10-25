# One cognition-agent-os product acceptance — engineering checkpoint 2026-10-25

**Current disposition: NOT_READY for unattended autonomous use.** All six
whole-product gates below are OPEN. No stage name, model response, PR, agent
count, document, passing CI, registered local capability or hash can close a
gate without the corresponding independent owner-outcome evidence.

This is an engineering gate model, not an approved or exhaustive immutable PRD.
Archived G1–G8, R01–R24, OT01–OT14 are historical *proposed* identifiers:
`evaluation/assurance_registry_v1.json` marks stakeholder requirements
incomplete. The user’s current instructions and lawful grants determine goal
and scope; the original complete objective remains the reference throughout.
This file is a dated snapshot, NOT the source of the current Git HEAD, not an
owner approval and not a roadmap that must be repeated after contradictory
evidence. Resolve live branches and exact-HEAD CI on continuation.

## Non-negotiable product definition

Given a legitimate owner goal, constraints, current delegated permissions and
limited budget, ONE durable agent system must autonomously determine remaining
obligations, find/check useful sources and methods, compare alternatives,
execute only permitted effects, independently read back **owner-meaningful
results**, repair or switch approaches when evidence rejects them, resume
after interruption and validate transferable learning on unrelated goals.
It should reduce the owner's work supervising, finding defects and correcting
the agent's execution.

**Parent-system acceptance supersedes generic task-runner acceptance.**
The target product is the cognition PARENT for video/IP
(`video-growth-agent`), financial writing (`financial-writing-agent`),
novel writing (`novel-writing-agent`), A-share analysis/recommendation
(`a-share-event-driven-agent`), and future independent business
subsystems. Each domain retains its canonical product requirements,
IDs, domain authority, business state, sources, assets, work progress,
effect permissions and domain outcome oracle. The parent identifies
and reconciles owner goals, investigates needed knowledge, compares
applicable cross-domain methods, routes advice/work through the child's
admitted interface, coordinates dependencies and reads independent
business outcomes without overwriting child state.

**Old-UAOS migration:** existing child `UAOS_SKILL.md` entries still
bind `universal-agent-os` to parent cognition/governance. That is the
historical parent still in use by those integration documents.
New cognition-agent-os adoption is NOT demonstrated by the current
Draft PR. No child repo edit, UAOS retirement or production cutover is
approved. A parent replacement requires a verified adapter migration,
unchanged legitimate child tasks, regression of both parent and child
state/permission/identity, and explicit owner authorization.

**Do not misclassify ChatGPT/Codex development skills as the business
parent.** Better developer workflows are tools for BUILDING and
auditing this project; Codex Hooks or native Goals cannot serve as
independent evidence that a video episode, article, novel or A-share
business task was guided, improved or independently completed.

A successful local JSON draft or CSV comparison under the original contract
is a real **local scoped** result. It is not a claim that arbitrary owner
goals, remote-provider effects or a finished OS have passed.

## Six end-to-end release gates — same candidate, same original goal

1. **Whole goal -> next legal choice.** With owner requirements (including
   conjunctive clauses), at least two genuinely applicable registered
   capabilities and independent counterevidence, the controller selects an
   executable **different** authorized next method without another chat turn.
   Missing acceptance clauses cannot disappear when delegating.
2. **Choice -> action -> independent correction.** The selected action runs
   through the ONE Host/Worker/SQLite grant and effect fence; source/provider
   state is independently re-read. Rejection causes a bounded alternative or
   evidence-gathering step, not a success claim, duplicate effect or endless
   alert loop. Distinct adverse, unchanged and reversal evidence are tested.
3. **Durable real host.** A real owner-approved schedule repeatedly invokes
   Host work while absent; crash and cold restart preserve exactly the same
   original goal, action identity, authorization and progress. Provider
   acknowledge-loss and retry behavior is tested on a permissioned sandbox.
4. **Correct authority and cross-domain repair.** Current grant, typed adapter
   scope, source trust, lease fencing, attempt/cost ceilings and independent
   readback gate external effects. Systemic defects are repaired at the
   shared responsible contract and tested across legitimate sibling paths;
   reviewer or model text cannot self-authorize or self-certify.
5. **Cross-domain parent-child generalization, not curated fixtures.**
   The SAME parent cognition loop must discover and cooperate with at least
   two distinctly governed real child domains, while honoring independent
   business identity, current domain requirements, permission and source
   authority. Evaluate conflicting/changed child state, parent guidance
   rejection, domain-specific independent readback and cross-domain
   method transfer/non-fit. Audit all four existing domains for no
   unintended authority or routing regressions, and independently
   exercise a NEW previously unregistered domain through a stable
   discovery/adapter contract without product-specific parent-code
   hardcoding. Measure actual child-relevant outcome and user correction
   burden; dry-run/read-only advice is not proof of business execution.
6. **Evidence attribution and product release.** Every result ties current
   original goal and grants to chosen method, actual executed effect, verifier
   identity, provider/source readback and unchanged/restored conditions.
   Independent reviewers can reproduce the claimed outcome; unknown stays
   unknown. Release still requires explicit owner authorization.

## Architecture decision — compare whole-system alternatives

The 2026-10-25 external reference review found the following:

| Candidate | Benefit | Failure against our owner's requirement | Disposition |
| --- | --- | --- | --- |
| Copy Claude Code Game Studios' 49 specialist prompts, 74 commands and game-studio gates | Strong role separation, adaptive rigor, traceability and delivery-oriented reviews | It is a human-guided Claude Code *workflow template*, not a proven autonomous persistent Host or an independent remote business oracle. A fixed 49-agent organization adds coordination/context cost | **REUSE PRINCIPLES ONLY** |
| Replace the runtime wholesale with a new multi-agent/graph/workflow framework | Richer routing and some durable workflow infrastructure may help unfamiliar goals | Discards the verified single grant/ledger, risks split authority and provider effects, and does not itself prove goal semantics. Requires comparative end-to-end evidence first | **RESERVE IF MEASURED NECESSARY** |
| Keep the one existing Host/Worker/SQLite; add a goal-level planner/decision policy, registered on-demand expert workers, independent effect reviewer and result-driven continuation | Preserves tested authority, durable evidence and current adapters; allows dynamic unfamiliar method selection with bounded effect admission | Existing open_goal, outcome_feedback and bounded_goal_control do not yet compose into this whole-goal cycle | **SELECT AS NEXT CANDIDATE, NOT PRODUCT PASS** |

Design principle: roles are **responsibilities**, not 49 mandatory
model calls. One objective owner/vision check, an architecture/method challenger,
on-demand domain specialist(s), an independent outcome verifier and a durable
coordinator are sufficient logical separations; these should reuse existing
tool/agent contracts and only instantiate separately when isolation measurably
helps. An architecture comparison is required for material uncertainty, not
for a routine typo. Avoid replacing source-grounded work with an ever-larger
review bureaucracy.

Primary references studied:
- https://github.com/Donchitos/Claude-Code-Game-Studios
- https://github.com/Donchitos/Claude-Code-Game-Studios/blob/main/CLAUDE.md
- https://github.com/Donchitos/Claude-Code-Game-Studios/blob/main/.claude/docs/workflow-catalog.yaml
- https://www.anthropic.com/engineering/building-effective-agents
- https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop
- https://developer.nvidia.com/blog/how-to-evaluate-ai-agents-from-tool-calls-to-task-completion

## Evidence and work order after 2026-10-25 review

**Proven in narrow scope, not general proof:** the integrated Draft candidate
(#50 at the recorded checkpoint, before these governance edits) had one
SQLite authority and original Host/Worker, two local result families
(source-grounded CSV discrepancy report, explicitly requested sandbox JSON
draft), effect/source/grant readbacks, duplicate-evidence semantics and
host CLI execution. Source tree `5643aee0b049f3d0de0b5d7ca69e0177bd8fc2c4`
passed [Linux and Windows 652/652 each, all seven required CI jobs](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40169082286).
These checks DO NOT prove owner-level external effects, spontaneous capability
discovery, or complete independent semantic correctness of every file.

**Actual priority (not next isolated local feature):** build the genuine
parent → child read-only discovery/goal reconciliation → competing
source-grounded guidance → child-native admission → independent child-domain
result feedback → parent correction loop on at least one of the existing
domains, preserving the ability to transfer to another; not a CSV/JSON demo.
No child mutation or new paid API is authorized by this acceptance target.

For the shared engine, achieve gate 1 + gate 2
together as one full original-goal vertical slice on the EXISTING Host with
two competing permitted methods, at least one independently falsified choice,
durable next-choice/action, original-criterion effect readback, crash/revoke
cases and whole-goal terminal classification. Implement typed boundaries and
external-source vetting once, then validate the **same decision logic** in a
different sealed domain; if that fails, compare hypotheses, correct the
responsible architecture and repeat the whole-task experiment. Introduce a
provider-neutral external-effect sandbox as the next evidence boundary; do
not infer real provider safety from local files. No metered or production
third-party execution without approval.

**Stop measuring progress in new tests, agents, documents, PR numbers or
completion of a research stage.** Tests prove contracts or discriminate
causes; a completed owner-relevant vertical outcome advances product status.
No approval to merge, release, deploy to user device, spend on models or write
to real external services is given by this document. Maintain NOT_READY until
all six gates are independently satisfied at the same code SHA.
