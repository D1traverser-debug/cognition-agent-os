# cognition-agent-os

**Status: experimental integrated candidate — NOT_READY.** This repository is the implementation of one opt-in cognition parent, not a release claim. Never infer current work from a dated README, cached SHA or old green CI: resolve live GitHub default-branch HEAD and active-PR topology, exact authoritative source, current grants and matching-head evidence first.

## Product objective

Given the owner's complete goal, constraints and lawful authorization, the parent should preserve intent across interruption, decompose and challenge assumptions, research unfamiliar professional methods and tools, compare materially different solutions, execute only allowed effects, independently verify the full owner/child-business result, change method after failure, retain evidence-backed learning and transfer to unfamiliar domains while reducing owner correction burden and unnecessary system complexity.

Current ChatGPT/Codex cognition and the repository Host/SQLite are technical surfaces of the same intended parent, but they are **not automatically connected**. Child systems retain their own task IDs, state, business data, permissions and result oracles. Historical `universal-agent-os` is not the active parent.

## Default context surface

Do not recursively load the repository as context.

- `SESSION_HANDOFF.md` — small bootstrap index only; not a complete work log or authority.
- `AGENTS.md` — current Codex/repository working rules.
- `docs/00-PRODUCT-CONOPS.md` — proposed stable product concept.
- `docs/01-ARCHITECTURE-DECISIONS.md` — current architecture decisions/proposals.
- `docs/02-AUTHORITY-AND-INTERFACES.md` — authority/interface boundaries.
- `docs/04-SECURITY-OPERATIONS.md` — security/operations constraints.
- `docs/06-ZERO-API-CREDIT-POLICY.md` — free-first/no-unapproved-metered-call policy.
- `docs/PRODUCT-READINESS-GATE.md` — current product acceptance gaps and phase priority.

The six `docs/` paths above are the **default specification starting set**, not a ban on other documentation. Additional `docs/` reports and experiments may be relevant evidence for a particular task; their presence does not make them current authority. Retrieve them selectively by purpose and provenance (not by date, size or filename alone). Material under `archive/` is historical by default and retrieved only for relevant prior decisions, failed attempts or source provenance.

Complete engineering provenance belongs in Git commit history, diffs, current code/tests and exact-head CI. Dated audit snapshots and obsolete root P1 instructions are archived; other technical reports retain their original paths until separately classified with link and dependency verification. Directory arrangement alone cannot prove a model selected correct context.

## Local prototype smoke

Python 3.10+:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --no-deps .

cognition-os --db ./trial.sqlite --workspace ./trial-work init
cognition-os --db ./trial.sqlite --workspace ./trial-work status
cognition-os --db ./trial.sqlite --workspace ./trial-work goal-resume

python -c "from pathlib import Path; Path('fixtures').mkdir(exist_ok=True); Path('fixtures/stable.txt').write_text('same', encoding='utf-8')"
cognition-os --db ./trial.sqlite --workspace ./trial-work --fixtures ./fixtures seed-fixture --old stable.txt --new stable.txt
cognition-os --db ./trial.sqlite --workspace ./trial-work --fixtures ./fixtures host-tick --max-jobs 2
cognition-os --db ./trial.sqlite --workspace ./trial-work status
```

Before explicit `init`, commands that require a configured local ledger fail closed rather than silently creating authority. Re-running `init` must not reactivate a revoked grant. A manual Host tick is one invocation, not proof of unattended scheduling. Local fixture success is not a business outcome.

For development:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/verify_assurance_registry.py
```

CI checks the installed CLI, native MCP stdio, Docker isolation, Windows scheduler behavior, context-surface boundaries and other regressions. CI is engineering evidence only; it cannot certify owner-level success or production authorization.

## Evidence and authority rules

- Owner goals/corrections and explicit permissions define desired outcome and allowed action.
- Current source, live runtime state and independent result readback define observed reality.
- GitHub issues, retrieved pages, archived reports, model prose and previous CI are evidence, not grants.
- No merge/release, production deployment, metered model call, owner-device installation, child-repository mutation or external production write is implied by this repository.
- A discovered tool is not automatically safe or executable. New capability must fit the current authorization/effect boundary and be independently validated.
- Product completion requires real unfamiliar-task research/tool selection, lawful execution, independent complete-result verification, failure-driven method change, cross-domain transfer and demonstrably lower owner intervention.

Historical experiments remain available through Git history and `archive/` when needed; they are intentionally excluded from the default cognition surface.
