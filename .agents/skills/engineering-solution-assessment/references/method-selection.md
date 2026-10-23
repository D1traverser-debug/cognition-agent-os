# Compare methods, not acronyms

These are researched **candidate methods**, not globally optimal recipes or installed project authorities. The original source must be checked at the point of use and fitness must be demonstrated on the current task.

| Signal | Viable methods | Best-fit question and known limitation | Primary source |
|---|---|---|---|
| Unclear new user feature/requirements | GitHub Spec Kit, explicit contract/examples, direct change | Are requirements ambiguous across users/versions? SDD clarifies what/why but does not prove the requirements were right. | https://github.com/github/spec-kit/blob/main/docs/reference/agentic-sdd.md |
| Unknown bug or repeated failure | Superpowers systematic debugging, trace/fault injection, TDD | Can a competing causal hypothesis explain the observation? TDD can reproduce *wrong* requirements. | https://github.com/obra/superpowers |
| Wrong ownership/interface boundaries | DDD bounded contexts, dependency graph, architectural decision record | Is domain language or responsibility mismatched? DDD does not mandate microservices. | https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis |
| Hard-to-reverse architecture tradeoff | ADR with rejected alternatives, real scenario walkthrough | What breaks when the requirement changes? A decision document is not execution proof. | https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record |
| Recurring structural regression | Architecture fitness functions, property/stateful tests, API compatibility tests | Can the *actual invariant* be mechanically falsified? A static dependency check cannot prove final user value. | https://www.thoughtworks.com/content/dam/thoughtworks/documents/books/bk_building_evolutionary_architectures_second_edition_free_chapter.pdf |
| Incompatible legacy upgrade | Strangler migration, anti-corruption layer, expand-contract rollout, justified breaking version | Can old/new callers coexist, roll back and later retire old authority? Never make two permanent owners for one truth. | https://martinfowler.com/bliki/OriginalStranglerFigApplication.html |
| Agent repeatedly chooses easy local patch | AGENTS.md, focused SKILL, Codex instruction-source inspection, agent behavior eval | Did the actual host load the instructions? No MD file physically forces model decisions. | https://learn.chatgpt.com/docs/agent-configuration/agents-md |
| Skill neglect, instruction bloat | Focused triggering description, progressive disclosure, actual skill eval | Can skill be selected for relevant tasks and ignored otherwise, and improve outcomes? More rules can worsen routing. | https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra |
| Actions succeed locally but goal fails | Independent outcome oracle, real CLI/Host, metamorphic negative tests | Does the final environment meet the original target; were normal users affected? | https://github.com/microsoft/eval-guide |
| Sequence-dependent or interrupted execution | Hypothesis state machines, replay, invariant/lease tests | Are failures caused by specific action orders? Random tests alone do not establish semantics. | https://hypothesis.readthedocs.io/en/latest/stateful.html |

### Why this is not a mandatory ten-tool pipeline

For each significant task evaluate at least the **current/no-change** path and relevant compatible vs architectural paths. Absent material uncertainty, reject an irrelevant technique immediately with evidence. With high impact or unknown domain, enlarge search across original standards, academic research, real failures and technology-specific tools until new sources no longer meaningfully change decision boundaries.

The *same model* choosing and judging a design is not an independent oracle. Prefer runtime behavior, reviewer-held target, compatibility check and external source verification. Score later **unfamiliar tasks** to validate learning transfer.
