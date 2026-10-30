# PR #32: Paired SciFact output-enumeration order causality experiment

**Status:** isolated evidence experiment; not a product acceptance gate or a new autonomous controller.

## Empirical reason to test this

Immutable, expert-labeled SciFact publisher archive SHA-256: `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`. Frozen sampled 24 balanced claim IDs SHA-256: `026fe3d9785461f40433120502c22c7583abdff99304d86c56e11cc141a955a7`.

Baseline Qwen2.5 0.5B (`a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67`) official SciFact dev label accuracy was **12/24 full abstract and 12/24 expert-rationale only**; model predicted SUPPORT on every evidence-present item. No-evidence refusal was **16/24**. Native evidence run [39956864434](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39956864434), artifact `12503415777`.

Qwen2.5 1.5B (`65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`) under identical publisher archive/sample got **13/24 full abstract**, **17/24 expert rationale**, **24/24 no-evidence refusal**. In full-abstract condition it still predicted SUPPORT **23/24**. Native run [39957970827](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39957970827) ran the real-model task successfully, but the overall workflow FAILED because the Docker integration task reported `ISOLATION_UNAVAILABLE / CONTAINER_LAUNCH_OR_TIMEOUT`. That isolated Docker failure is not logically a model-label failure and remains under investigation.

## Competing explanations

- **H1, model-capacity / scientific language**: the model fails to understand negation and expert contradiction.
- **H2, schema-order bias**: a generation grammar that exposes SUPPORT first biases decoding toward this label.
- **H3, prompt-order bias**: the textual instruction lists SUPPORT before CONTRADICT, and this could still bias decoding regardless of the JSON Schema order.
- **H4, task data contamination / incomplete annotations / insufficient reasoning**: original dev expert gold is better than assistant labels but is neither perfect nor a licensed deployment approval.
- **H5, run-to-run stochasticity / CI environment**: apparent changes could be nondeterministic even at temperature 0.

This study **isolates H2**, not H3 or H4/H5 in full.

## Design: within-sample paired counterfactual

Use **one installed, digest-pinned 1.5B model**, the **same pinned original SciFact archive and 24 IDs**, and the **unchanged original claim-evidence prompt**. For each claim and each of three conditions (none/full abstract/expert rationale), run the model twice with identical input/options; only the `format.properties.label.enum` order differs:

A. `[SUPPORT, CONTRADICT, INSUFFICIENT]` (prior original)
B. `[CONTRADICT, SUPPORT, INSUFFICIENT]`

Interleave A/B in an independently deterministic hash-based trial presentation order per claim, to mitigate monotonic temporal effects. Every trial records the external gold label **after inference**, the returned label, exact model digest and latency, with no private user source data. Record **144 real generations** total, plus paired switch count, A-only / B-only correctness, full per-class confusion, and no-evidence abstention. No scoring adjustment or threshold is chosen after seeing outcomes. The exact original dataset and installed model hashes must match prior executed baseline, or the experiment fails without guessing.

If reversed schema reverses SUPPORT-heavy behavior on the same input, H2 is supported. If not, **H2 is not supported** and textual prompt order, model reasoning and annotation alignment remain open. Neither result certifies scientific truth or permission to promote a research candidate.

Full-model and rationale-only differences separately expose distraction vs minimal evidence. No evidence correct rejection is a different outcome and should not be combined into a single headline 'accuracy'.

## Safety and follow-on

No new scheduler, autonomous action, external write, grant issuance, or merged release. Paid model API off. Runs exclusively in a disposable GitHub Linux runner with Ollama loopback; the model weights are downloaded fresh but must match pinned SHA. CI artifact retains all predictions and source provenance.

If prompt-order bias remains plausible, a **separate** cross-counterbalanced prompt/order study is needed. If both biases ruled out, compare better model architectures, calibration and genuinely unanswerable original tasks with negative controls. Any high-scoring scientific oracle study still lacks goal-to-action-to-external-outcome validation.

## Commands

`PYTHONPATH=src python scripts/measure_scifact_enum_order.py --smoke`

Real opt-in job marker: `[run-scifact-enum-order]`

Primary source: [SciFact by Wadden et al. (EMNLP 2020)](https://github.com/allenai/scifact).
