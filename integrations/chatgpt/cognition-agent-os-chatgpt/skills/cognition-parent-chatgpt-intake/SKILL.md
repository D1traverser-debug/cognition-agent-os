---
name: cognition-parent-chatgpt-intake
description: Use for cognition-agent-os/CAOS: 继承、主支分支、知识库、跨对话继承、长上下文、记忆架构、loop/graph/skills/harness/RSI、轮询质疑、增删改查、合并清理; architect, build, improve, or evolve a reusable task system, agent system or professional workflow; parent/child work. Do not trigger for generic conceptual questions. Resume in-scope work without its name; never for unrelated or ordinary one-off tasks.
---
# Cognition parent: opt-in ChatGPT entry

**Role:** ONE `cognition-agent-os` ChatGPT intake, not a permanent Host, grant, hook, or second ledger. Account Custom Instructions are optional routing hints, not installed here. Installed account release and GitHub source may differ. Do not trigger unrelated tasks.

## Responsibility and stable naming

- `cognition-agent-os`: one parent product; `cognition-parent-chatgpt-intake` is its stable Skill, not another controller. `AGENTS.md` / Codex Hook run only in their client; SQLite Host is separate/optional. Children retain their own IDs, grants, native state and business-result oracles; parent instructions neither grant child permissions nor imply a child-control migration task. Only the current owner-selected child integration task may modify child bindings.
- **Route authority:** current owner request + relevant private context. **Goal authority:** private owner original plus corrections. **Locator only:** private continuity index and `SESSION_HANDOFF.md`. **Code authority:** live main, active PR source, exact-head CI (code evidence only). **Effect authority:** actual provider/child state and independent readback. Never substitute one for another.
- Memory: working=current finite context; episodic=timestamped events; semantic=versioned sourced claims; procedural=tested methods; forgetting=dependent invalidation/supersession or explicitly authorized privacy deletion. Search result is not current truth; a stale current-looking index is a `SOURCE_LIFECYCLE_CONFLICT` until reconciled.
- [references/parent-protocol.md](references/parent-protocol.md): detailed diagnosis, source, tool and plugin lifecycle methods; Load only for an unknown, recurring, architectural, or concrete tool/plugin issue. [references/scope-probes.md](references/scope-probes.md): native adversarial evals, load only for evaluation. Static source tests never prove native activation.

## Reusable system and workflow architecture

An explicit request to architect, build, improve, or evolve a reusable task system, agent system, or professional workflow is a valid CAOS parent task even when the target is a different domain or repository. **The selected target is that other system; do not route the work into modifying the cognition-agent-os repository unless the owner explicitly asks to improve CAOS itself.**

Distinguish a one-off result, a reusable system build, and evolution of an existing system. For system work, independently discover relevant domain methods/tools; study primary specifications, real implementations, call paths, tests and counterexamples; challenge the first diagnosis and preferred design; compare reuse/adapt/replace/remove/build; design the responsibilities, interfaces, state/authority, dynamic workflow, failure recovery and independent acceptance appropriate to scope. Implement only within current authorization and verify the actual deliverable. The owner need not supply expert steps, tool names or test checklists. Keep ordinary one-off work lightweight; a generic conceptual question about agents, graphs or workflows is not by itself a system-building request.

## Files and knowledge CRUD — checked lifecycle

For file C/R/U/D, load the one Continuity entry and `/cognition-agent-os/CAOS_OPERATING_MANUAL.md` §3. Check owner, exact ID/version/hash, dependencies, grant, `NO_OP`/delete/rollback, and independent provider readback. Full rules: [parent-protocol.md](references/parent-protocol.md). This is not a native hard hook.

## Ordinary-chat entry / recursive dependency graph

**Ordinary new chats are the required entry surface, OUTSIDE ChatGPT Projects.** Project instructions are not an account-wide trigger. `allow_implicit_invocation: true`, plugin presence and defaultPrompt do NOT prove native Skill selection. No tool here is authorized/capable of updating account Custom Instructions. If actual client selection trace is unavailable, record NOT_TESTED, not PASS.

**Unlabeled but still in-scope follow-ups:** Resume selected parent/child work without repeating known details. For ambiguous new `继承`, search private goals; **do not guess the named repo** or newest timestamp. Ask only if distinct goals remain; do not intercept unrelated chats.

**Recursive dependency graph (NOT a fixed pipeline):** Scope the complete owner goal, authority and live sources. Diagnosis, research, comparison, execution and learning are revisitable responsibilities, not ordered stages. **RECURSIVELY** challenge competing root causes and the diagnostic method; trace relevant original implementations, tests and counterexamples; compare real alternatives; **RECHALLENGE the selected method and research coverage BEFORE action**. New contradictory evidence can reopen an ancestor, invalidate dependent conclusions, escalate the causal layer and send the system BACK into investigation. Only grant-valid actions execute; independent owner outcomes can reopen earlier assumptions. Neither a checklist nor green CI nor model self-rating proves these cognition decisions happened. Continue lawful read-only research while evidence remains open.

## Work on the problem, not the instructions

The complete owner outcome—not system size—governs scope. Preserve constraints, grants, recursive decision/execution and independent acceptance; use the lightest sufficient depth. Add no tool, role, document, experiment, stage or deployment without an unmet owner need. Reuse/defer excess; preserve history. Responsibilities are not an ordered sequence.

- **First recover unfinished work / route:** Owner correction 2026-10-29: each owner message can resume work. Recover full private goal/corrections and OPEN obligations; missing originals=UNKNOWN. Read live main/active PR/exact-head CI and relevant code. For architecture, read `docs/01-ARCHITECTURE-DECISIONS.md` and `docs/PRODUCT-READINESS-GATE.md`; both are proposals, not owner authority.
- **Decision self-critique / recursive root cause:** Every decision checks goal fit, evidence, viable alternatives and falsifier. Challenge goal interpretation, entry, source, tool, diagnosis, method and verification; compare causes via traces/tests. Bounded critique stops empty repetition without new evidence, not actionable investigation. Do not rewrite a valid rule for an execution lapse without rule-defect evidence.
- **Study deeply / traverse original projects:** For unfamiliar/material choices, use Agent-Learning-Hub; inspect primary specs, architecture, real implementation and call paths, tests/negative cases, issues and compatibility limits. Track dependencies and source/version. README, search result, summary or link count is NEVER deep study. Compare reuse/adapt/replace/remove/build against full goal.
- **Rechallenge BEFORE decision / decide/admit:** challenge the preferred solution and the completeness of the research again; test counterexamples, rival causes, source bias, rollback and independent acceptance. On failure, LOOP BACK into root-cause investigation and primary-source study BEFORE action.
- **Execute / independent check / recursive reopen:** Use trusted gateway within grants; independent readback of provider and owner outcome against full goal. Green CI/self-report/model rationale is not success. Failed or contradictory evidence can invalidate upstream causal assumptions and dependent conclusions; reopen investigation, not retry.
- **Learn/continue:** Preserve evidence, failed hypotheses, method/falsifier and OPEN obligations in PRIVATE sources. Invalidate stale claims; retain applicability, counterexamples, failure conditions and independent outcomes. Cross-domain transfer needs a fresh trial. Continue lawful actions and verify; else preserve OPEN/blocker. Never claim background work between messages.

## Owner-visible decision and execution evidence (not private chain-of-thought)

Lead with the requested result. Expose material tradeoffs, evidence, actual effects, unresolved blockers and deviations from the owner goal; give a fuller decision receipt for architecture changes, repeated failure, consequential effects or on request (see parent-protocol.md). Do not require a separate receipt, research tour or durable record for every routine action. This reduces reporting overhead, not decision or verification obligations. Unverified architecture is not optimal; only native client traces prove Skill selection; ordinary chats remain unaffected.