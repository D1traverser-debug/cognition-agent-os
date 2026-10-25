---
name: cognition-parent-chatgpt-intake
description: Restore and execute cognition-agent-os parent-system work in ChatGPT, especially after "继续" or "继承", owner corrections, architecture decisions, or a failure to select/verify the right tools. Scope includes project instructions, connected GitHub, tool and skill capabilities, original requirements, and independent outcomes; NOT video/novel child integrations by default.
---

# Cognition Parent: ChatGPT Native Intake and Recovery

This skill addresses the ChatGPT conversational/control surface of the ONE cognition parent. The repository implements its prospective persistent runtime. **Installing this skill does not modify model weights, create a background controller, load Codex-only hooks, or connect an undeployed Host/API.** Tool execution must be observed before treating a bridge as working.

## Resolve the actual user goal before choosing work

1. Treat the **current user's corrections and explicitly authorized objective** as the scope authority. Recover earlier original user messages when missing (search prior conversations, private continuity files), and classify prior assistant advice as *unapproved hypotheses* unless the user adopted it. Mark unretrievable originals unknown.
2. Ask yourself whether terms such as "联调", "父系统", "自身能力", "接口" refer to the **ChatGPT conversation, Project instructions, native plugin skills, Codex, API, repository Host, or business child systems**. Do not silently replace one surface with another. Scope corrections invalidate older assistant plans.
3. The first substantive action on a new engineering continuation is a **real tool observation**, not another instruction rewrite or roadmap.

## Runtime observation and tool selection

4. Inspect the available tool actions in this ChatGPT session. Prefer an **already connected** source of truth. GitHub tasks: read the actual open integration Draft PR (currently #50 unless superseded), HEAD, exactly HEAD-matching CI, implementation and failing traces. Recover evidence of successor PR ancestry before switching. Do not borrow older runs.
5. Repository `AGENTS.md`, Codex Hooks and repository `.agents/skills` are NOT native ChatGPT runtime instructions. A native ChatGPT skill must appear among actually installed skills and be observed invoked. Project instructions can be active without making every mandated tool call happen. A plugin provides workflow; MCP tools provide data/actions and permissions.
6. For current or niche design facts read official primary docs and raw original materials. Find credible alternatives, counterevidence, omitted expert checks, failure examples and true outcome oracles. Compare applicable methods, not popularity or prompt length. Stop expanding research when more is unlikely to change the action, while marking limits.

## Act, test, challenge again

7. Identify ONE highest-value legal next action that advances the corrected user goal. Use available tools to perform it in this turn. Normal editing, testing and correction do not need repeated user decisions. Never self-authorize paid API calls, deployment, merge, production effects or unrelated business child writes.
8. Before declaring progress, retrieve the **external observation** (tool log, source reread, actual UI behavior, raw real-model output); distinguish that from green CI, local synthetic tests, tool installation, or self-review. If an approach fails, change the selected mechanism and retest. Do not use skepticism as a reason to stop action.
9. Record evidence-based reusable method changes and failures in the appropriate durable state; keep private user source in private storage and public code free of private material. Never assert that this writes native GPT memory, changes model weights, or guarantees invocation in the next conversation.

## Specific first-mile capability probes

- **Cold conversation / "继续":** original user goal recovered, source unknowns named, live Draft HEAD/CI reread, one actual next task performed.
- **Owner corrects "联调":** stop child interface work; verify ChatGPT Project/custom instruction/native skill/GitHub/API capabilities instead. Show changed action, not only corrected wording.
- **Skill exists only in GitHub:** report native availability **UNVERIFIED** until installed-skill inventory and live invocation prove otherwise.
- **Prompt-only success claim:** show a separate external oracle or keep result open.
- **Tool or connector missing:** discover a supported native integration, prepare what can be done offline, and ask the user only for real app installation, account authentication or resource authorization.

**Acceptance:** For a set of previously unseen owner tasks and corrections, compare raw ChatGPT tool traces *with and without this installed skill*: original-goal retention, tool/skill invocation, source coverage, alternative comparison, action completion, independent outcome, number of owner corrections, cost and side-effect containment. A passing file lint or simulated transcript alone does not prove better cognition.
