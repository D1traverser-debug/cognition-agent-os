# cognition-agent-os

**Status: experimental integrated candidate — NOT READY for unattended autonomous use, external production writes, or business-outcome claims.** The authoritative development candidate is [Draft PR #26](https://github.com/D1traverser-debug/cognition-agent-os/pull/26), not the default `main` branch. No automatic merge, user-device install or paid model API is implied.

## Intended product

Given an owner-approved objective, boundaries and authorization, the eventual system should research unknowns, select legal methods, act through a real durable host, independently verify **owner-meaningful external results**, detect and correct systemic failures, transfer sourced learning, and continue work across sessions without repeated prompts.

This repository currently demonstrates only **bounded components** of that goal. Its model-free local JSON/CSV and reconciliation feedback are not autonomous discovery of unfamiliar methods, and mechanically valid artifacts are not business success.

## Run an isolated, deterministic smoke test

Python 3.10+ is required. Install this **candidate branch**, not the README-only `main`:

```bash
python -m venv .venv
# Activate the venv: source .venv/bin/activate (Linux/macOS)
# or .venv\Scripts\Activate.ps1 (Windows PowerShell).
python -m pip install --no-deps .
cognition-os --db ./trial.sqlite --workspace ./trial-work status
cognition-os --db ./trial.sqlite --workspace ./trial-work goal-resume
python -c "from pathlib import Path; Path('fixtures').mkdir(exist_ok=True); Path('fixtures/stable.txt').write_text('same', encoding='utf-8')"
cognition-os --db ./trial.sqlite --workspace ./trial-work --fixtures ./fixtures seed-fixture --old stable.txt --new stable.txt
cognition-os --db ./trial.sqlite --workspace ./trial-work host-tick --max-jobs 2
cognition-os --db ./trial.sqlite --workspace ./trial-work status
```

On a new database, `goal-resume` intentionally exits with code **4** and `NO_DURABLE_GOAL`; it does not infer owner authorization from a README, chat message or stale handoff. The fixture task is local-only; a Host tick is **one invocation**, not a persistent background agent. Do not put personal secrets or API tokens into this public repository.

For module-level development: `PYTHONPATH=src python -m unittest discover -s tests -v`. CI additionally builds a clean installed console-entrypoint smoke on Linux/Windows and checks Docker isolation, Graphify call paths, and a hosted Windows scheduled task; no test substitutes for a long-running owner machine.

## Architecture and evidence

Current single-task authority is SQLite, with immutable task/evidence receipts and explicit current-grant checks; the shared `control_kernel.py` prevents denied grants from reaching operational callbacks. Domain evaluators remain separate; known feedback capabilities are limited and preregistered.

- [Product ConOps](docs/00-PRODUCT-CONOPS.md) and [candidate ADRs](docs/01-ARCHITECTURE-DECISIONS.md) are proposals, **not final stakeholder acceptance**.
- [Current product readiness gate](docs/PRODUCT-READINESS-GATE.md) is **NOT_READY** pending genuine unknown-task autonomy, independent external business outcome checks, novel knowledge transfer, and owner-host deployment.
- [Architecture A/B machine evidence](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39924435693): seven old-vs-new end-to-end scenarios × three attempts; state parity and independent terminal oracles passed. This demonstrates a reversible refactor, not unique optimality.
- [Live external source and readback](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39925149929): real public GitHub immutable contents tested for change/no change; research sourced from one publisher remains **REVIEW_ONLY**.
- [AOCI vs Graphify tooling assessment](docs/ENGINEERING-COGNITION-TOOLCHAIN.md): Graphify supports AST/call relations only. The one-time signed AOCI bootstrap had **zero valid authored semantic entries**; do not claim full project comprehension.

**Release prohibition:** all product gates require independently attributable, real owner-level outcomes and current lawful authorization. A green CI or signed receipt from the same system is insufficient.
