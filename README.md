# cognition-agent-os

**Status: unified experimental Draft integration — NOT_READY for unattended autonomy, third-party writes or business-outcome claims.** Do not infer live code from this dated README. Resolve live GitHub open Draft PRs and actual HEADs, ancestry, grants and matching-head CI before resuming. The 2026-10-25 review surface is [Draft PR #50](https://github.com/D1traverser-debug/cognition-agent-os/pull/50) based on unchanged placeholder `main`; any later PR can supersede this observation. Compacted history is retained in `archive/pre-consolidation-cognition-20261025`. No merge, deployment or paid model is authorized by a PR.

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
# Only an explicit init may create the local prototype ledger.
cognition-os --db ./trial.sqlite --workspace ./trial-work init
cognition-os --db ./trial.sqlite --workspace ./trial-work status
cognition-os --db ./trial.sqlite --workspace ./trial-work goal-resume
python -c "from pathlib import Path; Path('fixtures').mkdir(exist_ok=True); Path('fixtures/stable.txt').write_text('same', encoding='utf-8')"
cognition-os --db ./trial.sqlite --workspace ./trial-work --fixtures ./fixtures seed-fixture --old stable.txt --new stable.txt
cognition-os --db ./trial.sqlite --workspace ./trial-work host-tick --max-jobs 2
cognition-os --db ./trial.sqlite --workspace ./trial-work status
```

Before `init`, `status` and task seeding exit with code **4** and `HOST_NOT_CONFIGURED`, without creating a database or local write grant. After explicit `init`, a `goal-resume` without a registered owner goal exits with code **4** and `NO_DURABLE_GOAL`; it does not infer owner authorization from a README, chat message or stale handoff. Repeating `init` on an existing ledger is non-destructive and must never reactivate a revoked grant. The `init` command explicitly enables the current **local prototype** workflow, not third-party production writes or independent business acceptance. The fixture task is local-only; a Host tick is **one invocation**, not a persistent background agent. Do not put personal secrets or API tokens into this public repository.

For module-level development: `PYTHONPATH=src python -m unittest discover -s tests -v`. CI additionally builds a clean installed console-entrypoint smoke on Linux/Windows and checks Docker isolation, Graphify call paths, and a hosted Windows scheduled task; no test substitutes for a long-running owner machine.

## Historical 2026-10-24 integrated baseline: capability and evidence boundaries

At the dated 2026-10-24 baseline, an earlier development trunk was the stacked candidate **PR #26 → #27 → #28 → #33 → #34 → #35 → #36**. Later Draft PR branches are not included in that historical list; fetch the live PR graph before using it. PRs #29–#32 form a **parallel retrieval/model research branch**, not an already-integrated production inference stack. PRs #1–#25 and historical P-label experiment notes remain evidence, not active deployment configurations. Branch membership and source SHA, rather than filenames or old "CURRENT" headings, determine actual implementation.

The implemented trunk contains one SQLite task/grant authority and shared `control_kernel`; Host/Worker scheduling, explicit local capability registration, source-pinned research and read-only knowledge routing, finite counterexample/retry handling, Docker-contained repair experiments, signed-review input, and the opt-in **local sandbox** shared-goal post-effect check. The latter verifies staged bytes under a frozen exact-record postcondition, not a real external provider effect. Neither natural-language open-ended unknown-method discovery nor validated cross-task autonomous learning is proven by the fixed JSON/CSV controller, optional model work, or past external code-repair experiments.

**Requirement interpretation:** Original ConOps goal labels G1–G8 and R01–R24/OT01–OT14 are *historical proposed trace identifiers*, not a frozen approved PRD or sufficient list of current work. The latest explicit user constraints and authorized goal override derived documents. The six numbered items in [the release gate](docs/PRODUCT-READINESS-GATE.md) are separate acceptance-gate labels, not the same G1–G8. Before implementation, inspect actual branch ancestry, changed code, counterexamples and negative results; do not restart discarded historical experiments or invent another control plane.

## Architecture and evidence

Current single-task authority is SQLite, with immutable task/evidence receipts and explicit current-grant checks; the shared `control_kernel.py` prevents denied grants from reaching operational callbacks. Domain evaluators remain separate; known feedback capabilities are limited and preregistered.

- [Product ConOps](docs/00-PRODUCT-CONOPS.md) and [candidate ADRs](docs/01-ARCHITECTURE-DECISIONS.md) are proposals, **not final stakeholder acceptance**.
- [Current product readiness gate](docs/PRODUCT-READINESS-GATE.md) is **NOT_READY** pending genuine unknown-task autonomy, independent external business outcome checks, novel knowledge transfer, and owner-host deployment.
- [Architecture A/B machine evidence](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39924435693): seven old-vs-new end-to-end scenarios × three attempts; state parity and independent terminal oracles passed. This demonstrates a reversible refactor, not unique optimality.
- [Live external source and readback](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39925149929): real public GitHub immutable contents tested for change/no change; research sourced from one publisher remains **REVIEW_ONLY**.
- [AOCI vs Graphify tooling assessment](docs/ENGINEERING-COGNITION-TOOLCHAIN.md): Graphify supports AST/call relations only. The one-time signed AOCI bootstrap had **zero valid authored semantic entries**; do not claim full project comprehension.

**Release prohibition:** all product gates require independently attributable, real owner-level outcomes and current lawful authorization. A green CI or signed receipt from the same system is insufficient.
