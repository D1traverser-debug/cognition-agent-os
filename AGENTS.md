# Repository engineering guidance

For complex feature, bug, refactor or architecture work in this repository, consider the real user outcome, current execution entrypoint, existing contracts and competing explanations before changing code. The first plausible repair is a hypothesis, not a conclusion.

Preserve the existing SQLite authority, permissions and previous functions unless the user outcome and real evidence justify a more complete architectural replacement. Green CI alone cannot prove the intended result.

Use the focused engineering-method skill under `.agents/skills/engineering-solution-assessment/SKILL.md` for nontrivial engineering changes. Evaluate primary sources, verify actual runtime activation and independent outcome. When unsure, investigate rather than invent a rule or a new controller.

This file applies only to hosts that actually load repository AGENTS.md. It does not change ChatGPT account instructions or grant deployment authority.
