# PR #31 — External expert-labeled scientific evidence interpretation

Status: **not product acceptance**, isolated, opt-in and read-only. This follows PR #30's full-corpus retrieval comparison but measures a DIFFERENT capability. Retrieval gains do not imply correct interpretation or safe refusal.

## Primary source, methodology and independent ground truth

Use the official Allen Institute for AI SciFact original dataset and schema: https://github.com/allenai/scifact and Wadden et al., *Fact or Fiction: Verifying Scientific Claims* (EMNLP 2020). Claims in `claims_dev.jsonl` contain externally annotated `SUPPORT` or `CONTRADICT` rationales with sentence indexes; `corpus.jsonl` contains abstracts. Official dev is labeled; the official SciFact test labels are **not publicly released**, and we do not pretend that this pilot is the held-out test or leaderboard result.

Download from the publisher's official `release/latest/data.tar.gz` URL. Record the archive SHA-256, original claim/corpus counts, exact sample claim IDs hash and installed local-model digest. Original SciFact is noncommercial/research licensed; use a temporary public CI runner, do not redistribute the corpus or use it in a paid product. The `latest` archive URL is mutable: **the SHA recorded in the first run is provenance, not pre-pinned immutability**. Before repeated comparisons, pin the observed archive digest explicitly or use an immutable mirror.

## Causal decomposition: which part of the cognition chain?

Previously the system could generate correct-looking quotations while making semantically wrong source choices, including malicious injected materials. This test asks a different, narrowly falsifiable question: **can an actual installed model judge whether supplied original scientific evidence supports or refutes a claim, and refuse judgment when there is no supplied evidence?**

Oracle evidence selection is intentionally used to isolate model reasoning from retriever error. In real autonomous operation, the evidence would first have to be discovered safely; these scores must not be interpreted as end-to-end performance.

Fix `qwen2.5:0.5b`, 12 externally labeled `SUPPORT` and 12 `CONTRADICT` examples, deterministically selected by claim ID hash only. Each claim has three conditions under the same model, temperature and structured-output schema:

1. `no_evidence`: reveal claim but no supporting document; correct evidence-limited behavior is `INSUFFICIENT` regardless of whether model happens to have world knowledge.
2. `full_abstract`: present the original correctly labeled abstract; measure accuracy against external annotator's SUPPORT/CONTRADICT label.
3. `oracle_rationale`: present only the gold annotated rationale sentence(s); an optimistic upper bound that **cannot be used unchanged in production**, because it uses expert gold segmentation unavailable for unfamiliar tasks.

Report all 72 raw per-claim outputs, label confusion and full source-data/model digests. Do not merge or promote an agent based on performance here. The evaluator sees external claim gold labels, the model does NOT.

## Remaining product acceptance boundaries

Truth labels and evidence rationales are external, but the evaluator is a script we author, not an independent human sign-off of deployment. This experiment checks scientific evidence interpretation only, not multi-hop evidence acquisition, prompt-injection resilience, cross-domain transfer, human correction burden, owner authority, or verified external business goal outcomes. Unattended user-host deployment remains deferred. No paid model API or unsafe write tool.

Research oracles are deliberately separate from the production runtime; no new scheduler, tool planner, human-approval bypass or autonomous write path.

## Reproducibility

`python scripts/measure_external_scifact_claim_judgment.py --smoke`

Full real-model run is opt-in with PR description marker `[run-scifact-real-judgment]`. Artifacts contain the annotated label comparisons and model outputs, not all copyrighted source text.
