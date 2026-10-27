# P23 — Outside NuPlan bug, preregistered whole-file vs exact-replace comparison

## Governing outcome and what is NOT claimed

The user wants a **real, independently assessed, useful local code-repair Agent**, without paid/finite-credit LLM APIs, hidden-answer leakage, automatic main merge, upstream writes or unapproved owner Windows deployment. P21 and P22 each failed to produce valid effective repaired candidates on outside issues. P22b introduced an opt-in compact literal edit transport, but only offline regressions had passed. It is a candidate mechanism, NOT observed local-model success.

P23 prospectively evaluates a NEW externally authored defect, not another tuning of P21 or P22. It reuses the original SQLite task authority, immutable candidate freeze, trusted deterministic expansion, real no-network non-root Docker executor, original PUBLIC review, independently sealed HIDDEN evaluation and method-scope reviewer. The only experimentally varied parameter is the output representation: existing full-file \`changes\` vs opt-in \`candidate_format="exact_replace"\` short \`edits\`. One run per format, both real installed Qwen2.5-Coder 7B, with no scripted/known-correct patch fallback. The model receives identical original source, intended goal, public test inputs and public expected values. In this experiment, generation budgets differ according to the previously implemented format contracts: full-file \`num_predict=3500\` and compact \`num_predict=1800\`; therefore observed differences cannot be attributed uniquely to representation. The total time cap remains bounded at 180s per local model request by default.

## External provenance, scope and caveats

Third-party public [motional/nuplan-devkit Issue #429](https://github.com/motional/nuplan-devkit/issues/429), about \`STRTreeOccupancyMap._get_other_geometries\` misclassifying a different geometry ID as ignored when its ID is a substring of \`ignore_id\`. Original pinned upstream source: \`motional/nuplan-devkit@e9241677:nuplan/planning/simulation/occupancy_map/strtree_occupancy_map.py\`; independently connector-verified Git blob \`c61a13776fcb1fc55a43daa826a757eb992e4bda\` before preregistration. Never fall back to mutable master when fetching source. \`scripts/verify_p23_nuplan_comparison.py\` reconstructs an isolated Python class from the exact original method AST source and a tiny **non-upstream** adapter that converts a JSON geometry map into the original filter result. The test is **not a complete NuPlan/Shapely nearest-neighbor integration** and never asserts that wider behavior is repaired.

The public issue itself already contains a suggested source fix, so this is not a blind, unknown-to-model benchmark. The proposer receives only the reporter-compatible outcome statement and public examples, not the issue's supplied solution; nonetheless public or training contamination cannot be ruled out, and human maintainer acceptance is absent.

## Frozen method/gold before any real inference

\`PUBLIC=4\`: two substring-collision failures and two correct controls. Original isolated upstream bug must reproduce precisely **2/4**. \`HIDDEN=8\` Agent-authored, independent-key-equality expected values: nested prefix IDs, missing ID, empty map, Unicode, a longer ID, ordinary unrelated tokens and single-entry behavior. Hidden labels remain solely in local fixture material and independent real Docker reviewer; no adapter exposes them to model generation or public feedback.

The compared full and compact tasks share identical source, goal, PUBLIC cases and HIDDEN cases; only task ID and \`candidate_format\` differ. The final digest \`manifest(raw)\` hashes upstream blob, extracted original source, goal, PUBLIC and HIDDEN before the local model request. Test \`tests/test_p23_nuplan_comparison.py\` verifies exact pin, frozen gold, deliberate baseline mismatch, extraction refusal on tampered bytes, format parity, scope constraints and scope-vs-semantics separation.

Beyond Docker PUBLIC 4/4 and HIDDEN 8/8, any accepted result requires independent staged-output verification: the upstream original isolated method signature and class setup may not change except method implementation, and the JSON adapter plus main entrypoint must remain byte-identical. Positive scope does not imply business semantic success. The upstream original source and external repository must remain unchanged. Test records separately whether a model finished generation, source was frozen, PUBLIC passed, HIDDEN passed, scope passed and real maintainer accepted. No model/no candidate/timeouts are **UNMEASURED SEMANTIC REPAIR**, not fictitious patched-code failures.

## Workflow and stop rules

Ordinary Draft CI includes a no-model original-source baseline against immutable upstream bytes; Linux, Windows, Docker and Windows-native Scheduler must be green before the one-time real 7B experiment. \`.github/workflows/ci.yml\` contains a **strict PR-body opt-in** \`[run-p23-nuplan-ab]\` for temporary public GitHub-hosted Ollama with open Qwen2.5-Coder 7B and Docker. The owner machine and upstream repository are untouched; no metered model or expiring AI service credits.

After experimental evidence: remove PR marker, append the ACTUAL result (including refusal, timeout or missed gold), and recheck ordinary final HEAD CI with real model experiment SKIPPED. A single easy isolated case cannot prove broader unfamiliar-repo autonomy; no production merge/release or operating-system trust-root permission follows.

## P23 admission before first real model proposal (2026-10-21)

Immutable NuPlan original-source Docker baseline **actually passed** (expected broken 2/4 PUBLIC), with manifest SHA256 `8c60b11e315e9aed378228b030e3e8704a64247c0e5eccd5744a3848424aa8c8` printed by CI. Original Git blob `c61a13776fcb1fc55a43daa826a757eb992e4bda` was checked at the pinned upstream `e9241677`. Entire no-model preflight [Actions #39597456905](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39597456905) **COMPLETED/SUCCESS** for Linux, Windows, native Docker and hosted Windows Task Scheduler. Other local-model experiments SKIPPED. This document-only commit is a one-time trigger for the exact preregistered P23 local-7B comparison using the temporary PR-body opt-in; no changed benchmark/test gold/source or production source, no external/upstream writing. The model result is **not yet known**, regardless of experiment job conclusion. Remove the opt-in after confirming run dispatch.


## Observed authentic P23 7B A/B result — both source formats pass (2026-10-21)

Actual unmocked, single opt-in [GitHub Actions #39597947150](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39597947150), candidate experimental HEAD `ef15f09e674eecb999eba174d7710a9284473298`: workflow **COMPLETED/SUCCESS**, including Linux offline regressions, native Windows regressions, actual no-network Docker integration, real hosted Windows native Scheduler, and the one-time genuine Ollama 7B experiment. The one-time PR body trigger has already been **REMOVED**; subsequent normal pushes must SKIP model downloads.

At job startup both the no-model and installed-model baselines reproduced original pinned NuPlan method failure as **2/4 PUBLIC passed**, with matching pre-registered manifest SHA256 `8c60b11e315e9aed378228b030e3e8704a64247c0e5eccd5744a3848424aa8c8`, source Git blob `c61a13776fcb1fc55a43daa826a757eb992e4bda`. Actual installed loopback Qwen2.5-Coder 7B completed its genuine generation probe. Neither format used a prepared correct patch, hidden answer feedback, cloud LLM inference, owner Windows machine, or third-party source writes.

| Independent outcome | Whole-file `changes` | Compact `exact_replace` |
| --- | --- | --- |
| Frozen changed candidate | YES, first attempt | YES, first attempt |
| Genuine Docker PUBLIC | 4/4 | 4/4 |
| Sealed independent Docker HIDDEN | 8/8 | 8/8 |
| Original-method-only staged scope | PASS | PASS |
| Model refinement attempts | 0 | 0 |
| Full case elapsed | 56.95 s | 43.17 s |
| Existing SQLite review disposition | `REPAIR_LAB_VERIFIED` | `REPAIR_LAB_VERIFIED` |
| External maintainer signoff | NONE | NONE |

**Causal limits:** This is one deliberately isolated, small method, not a complete NuPlan integration or true production repair. The third-party public issue includes a suggested fix; model pretraining/issue contamination cannot be ruled out. Both formats succeeded, so this experiment does **not** demonstrate improved task success probability; one 43.17s vs 56.95s elapsed pair cannot justify latency superiority either. Different output-token limits and candidate sizes are part of the contracts; the time delta is observational. Positive evidence supports only that the existing compact representation can produce and admit a valid real model repair while retaining the existing offline Docker and scope gates. Continue with *distinct* prospectively frozen, harder outside work plus external acceptance; do not repeatedly tune NuPlan or promote to main automatically.

After these documentation-only and durable handoff writes, obtain a fresh final-head ordinary CI **with real 7B SKIPPED** before claiming the new HEAD regression-green. Production merge/release, user-PC install and upstream commit remain unapproved.
