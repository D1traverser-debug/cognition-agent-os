# Evidence relevance, refusal and adversarial-source experiment (PR #29)

Status: research experiment only. The canonical product remains NOT_READY.
No new scheduler, grant, daemon or production effect.

## Original evidence and methods
- Owner research requirements: original G1–G8, R01–R24, OT01–OT14 in the two privately held CONOPS originals. **Those originals are not to be copied to the public repository.**
- BM25 mechanism: Robertson & Zaragoza, *Probabilistic Relevance Framework*, doi:10.1561/1500000019.
- Evidence retrieval comparison: Anthropic, *Contextual Retrieval* (2024): chunking, sparse+semantic recall and reranking are competing approaches, not automatic correct-answer certificates.
- Refusal: Rajpurkar/Jia/Liang (ACL 2018) SQuAD2, and Peng et al. (ACL 2025) UAEval4RAG. Retrieval ranking does not itself answer the question or estimate calibrated probability.
- Injection: OWASP LLM01 2025 and microsoft/BIPIA pinned main commit `a004b69ec0dd446e0afd461d98cb5e96e120a5d0`. Three individual unchanged short BIPIA test attack lines are used as untrusted document DATA, not as program instructions.
- NIST AI RMF 600-1 MP-2.3-001: separate quality/suitability tests and compare against known ground truth and human oversight.

## Architecture decision and alternatives
Keep the current single SQLite authority and execution/evaluation lifecycle. Compare **A** prefix-only lexical retrieval (cheap incumbent information limitation), **B** bounded overlapping-window BM25 (full-source lexical relevance), with optional future **C** model-retrieval/reranking. No choice here approves or replaces the model selection path. Every retrieved document remains untrusted. The verifier can prove that a quote appears in a source, not that the source is relevant or truthful.

## Pre-registration and avoiding false success
The untouched previous 8 public model-eval cases are DEVELOPMENT. The 16 hand-authored, independently label-separated, model-unseen HOLDOUT cases are versioned in `evaluation/evidence_selection_holdout_v1.json`. Gold labels are never passed to retrieval functions. This is not externally adjudicated truth; the three borrowed BIPIA injection sentences originate from a real external primary benchmark.

Calibrate only a *predeclared* small list of thresholds on DEVELOPMENT, freeze the choice, score both methods on HOLDOUT. Report BOTH development and holdout outcomes, false source selection, misses, false abstention, false answerability, injection contamination, family-level results and latency. **Do not select the winner on holdout and then call that holdout score unbiased**. 16 cases are not enough for deploy-grade confidence; furthermore synthetic task labels can be flawed. Do not infer production or domain-agnostic performance.

This benchmark tests RETRIEVAL only, not model reasoning/answer faithfulness, question-answer correctness, agent cross-task learning, authorization or business results. A method with high scores is still NOT a permission to promote source content to instructions or automatically execute an external write. Follow-on prospective tests must use external primary data, independently held-out tasks and an actual model, with cost and human corrections recorded.

## Reproduction
`PYTHONPATH=src:. python scripts/evaluate_evidence_retrieval.py`
`PYTHONPATH=src:. python -m unittest discover -s tests -v`

Not a merge criterion or a new mandatory gate.
