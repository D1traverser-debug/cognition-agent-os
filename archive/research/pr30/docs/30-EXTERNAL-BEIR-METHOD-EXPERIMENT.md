# PR #30 — first external-primary-label retrieval benchmark

**Scope:** isolated read-only research experiment. No method promotion, production deployment, user-host setup, paid model, new orchestration authority or business verification. This intentionally does not run the original user-goal agent, and it must not be mislabeled as an agent evaluation.

## Why the prior experiment was insufficient

PR #29's 16 cases were assistant-authored and then retrospectively re-labeled when source relevance had been conflated with answerability. The source of the answer labels was not independent. On that small exploratory set, prefix overlap achieved 12/16 versus passage BM25 11/16; neither mitigated prompt injection. Choosing the apparent winner on this dataset would be overfitting. A new benchmark must use **externally independently assigned labels and the whole corpus**.

## Primary, separately curated external evidence

Original BEIR NeurIPS 2021 retrieval benchmark, from the official repository https://github.com/beir-cellar/beir; the test qrels were created externally before this code. The script downloads the full original archives from the official UKP Darmstadt dataset host, verifies the BEIR published transport MD5, then **parses all corpus documents and all test judgments**. There is no copy of the dataset or private user material committed to the repo.

| Corpus | Independently published expected archive MD5 | Task |
|---|---|---|
| SciFact | `5f7d1de60b170fc8027bb7898e2efca1` | scientific claim evidence retrieval |
| NFCorpus | `a89dba18a62ef92f7d323ec890a0d38d` | nutritional / biomedical source retrieval |
| ArguAna | `8ad3e3c2a5867cdced806d6503f29b99` | retrieval of counterarguments |

Each dataset has different relevance density and query style. This experiment evaluates a **deterministic, predeclared hash sample of up to 80 positively judged test query IDs per corpus**, not the entire BEIR leaderboard. Be precise: **not official published BEIR nDCG@10**. For full official BEIR leaderboard comparison, score all test queries with the prescribed pipeline.

## Three alternatives — same corpus and query IDs

A. `prefix_overlap`: inexpensive query-token overlap over initial 650 characters of every source.
B. `bm25_document`: lexical BM25 ranking of complete documents, sparse inverted index.
C. `bm25_passage`: overlapping fixed-length token passages, standard BM25 statistics over passages, then maximum passage score per original document.

All three use the same tokenization, no relevance-label input and a fixed top-100 budget. Passage method trades more indexing memory, processing and latency for finer evidence localization. No fine-tuning or cutoff selection on the test labels.

## Evaluation contract and anti-overclaim rules

Score **nDCG@10, Recall@100 and MRR@10**, plus median per-query selection latency; retain missed positive document IDs in the output. Compute paired bootstrap 95% descriptive range for the passage-vs-document nDCG difference. This is not a randomized clinical trial or a certified deployment threshold.

Qrels never enter `rank()`; they are consulted only after returned IDs. Positively labeled test queries were sampled based on **the query IDs alone, before scoring**, not the query text or method returns. Sampling still creates distribution uncertainty. Published datasets have their own imperfect labels and incomplete judgments.

All code is stdlib, real network access only within explicit opt-in **public** GitHub CI, pinned by official archive MD5 with hard failure on missing/mismatched/oversized input. Archives are accessed in memory, not extracted to the file system. Partial measurement records remain marked with missing datasets if a download fails; this must not be reported as a complete experiment.

Reference:
- BEIR original paper: Thakur et al., *BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models* (NeurIPS Datasets & Benchmarks 2021).
- Official reproducible dataset links and checksums: https://github.com/beir-cellar/beir .
- A valid **retrieval** score does NOT verify semantic truth, source reliability, multi-hop completeness, unanswerable question judgment, resistance to prompt injection, business goal attainment, or execution authorization. None of those results is inferred here.

## Commands

`python scripts/measure_external_beir_retrieval.py --smoke`

`python scripts/measure_external_beir_retrieval.py --out evaluation/beir_external_retrieval_results.json`

Full external run is gated by the **opt-in PR-body marker** `[run-beir-external-retrieval]` and persists an Actions artifact, with no extra gate on existing PRs.

**Decision rule:** report per-domain wins and losses including uncertainty, as well as latency. Do not automatically choose the aggregate winner or alter the live runtime based solely on retrieval data. The next experiment must evaluate actual questions and answer correctness with a separately established human/primary-data oracle, and then the causal influence on the original goal loop.
