"""Pre-registered A/B/C study, with labels outside the retrieval methods.

Calibrate cutoffs on the 8 existing public DEV tasks ONLY. Then score the 16
versioned evidence-role HOLDOUT tasks unchanged. Synthetic reviewer-authored labels are
independent of method return values, but NOT expert truth for real-world use.

Outputs honest failure/abstention/injection/temporal/multilingual metrics.
No external model, provider, API cost, production write, or second agent loop.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import time

from cognition_agent_os.evidence_ranker import select_docs
from scripts.measure_real_investigation import CASES as DEV_CASES

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "evaluation" / "evidence_roles_holdout_v2.json"
OUT = ROOT / "evaluation" / "evidence_selection_ab_results.json"
METHODS = ("prefix_overlap", "chunk_bm25")
# DEV relevance labels amend one formerly no-answer case. This calibration
# correction is declared explicitly, separately from the held-out V2 labels.
DEV_RELEVANCE_OVERRIDE = {
    "unknown_machine_serial": ["document-b.md", "document-c.md"],
}
CUTOFFS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0)


def _evaluate_one(row: dict, *, method: str, cutoff: float) -> dict:
    docs = row["docs"]
    start = time.perf_counter()
    chosen = select_docs(row["question"], docs, method=method, cutoff=cutoff)
    ms = round((time.perf_counter() - start) * 1000, 3)
    gold = set(row["relevant_sources"])
    pred = set(chosen)
    fp, fn = pred - gold, gold - pred
    return {
        "id": row["id"], "family": row.get("family", "development"),
        "selected": chosen, "gold": sorted(gold),
        "exact": pred == gold,
        "false_source_count": len(fp),
        "missed_source_count": len(fn),
        # Retrieval no-results is a miss when relevant evidence exists, even
        # if the requested final answer is unavailable. Answerability is a
        # separate consumer decision and MUST NOT be scored here.
        "retrieval_empty_with_evidence": bool(gold and not chosen),
        "reference_answerable": row["answerable"],
        "unresolved_contradiction": row.get("unresolved_contradiction", False),
        "attack_contamination": bool(
            "injection" in row.get("family", "") and fp),
        "latency_ms": ms,
    }


def _weighted_dev_loss(rows: list[dict]) -> int:
    # Pre-registered, no source content or heldout label in tuning.
    # A false assertion about unavailable/contaminated evidence costs
    # more than an honest refusal. Avoid an always-abstain winner via FN.
    return sum(4 * x["false_source_count"] +
               2 * x["missed_source_count"] +
               int(x["retrieval_empty_with_evidence"]) for x in rows)


def _summarize(rows: list[dict]) -> dict:
    families = defaultdict(list)
    for r in rows:
        families[r["family"]].append(r)
    def acc(items):
        return round(sum(v["exact"] for v in items) / len(items), 4)
    return {
        "total": len(rows),
        "exact": sum(x["exact"] for x in rows),
        "exact_rate": acc(rows),
        "false_source_count": sum(x["false_source_count"] for x in rows),
        "missing_source_count": sum(x["missed_source_count"] for x in rows),
        "retrieval_empty_with_evidence": sum(
            x["retrieval_empty_with_evidence"] for x in rows),
        "reference_unanswerable_cases": sum(
            not x["reference_answerable"] for x in rows),
        "reference_unresolved_conflicts": sum(
            x["unresolved_contradiction"] for x in rows),
        # This score never claims to measure answer-generation/refusal quality.
        "answerability_predicted": False,
        "contamination_cases": sum(x["attack_contamination"] for x in rows),
        "p50_latency_ms": round(statistics.median(x["latency_ms"] for x in rows), 3),
        "per_family": {fam: {"n": len(items), "exact": sum(i["exact"] for i in items)}
                       for fam, items in sorted(families.items())},
        "case_results": rows,
    }


def run(*, output: Path = OUT) -> dict:
    payload_bytes = HOLDOUT.read_bytes()
    dataset = json.loads(payload_bytes)
    if (dataset["schema"] != "cognition-evidence-roles-holdout-v2"
        or dataset["created_before_v2_method_evaluation"] is not True
        or len(dataset["cases"]) != 16):
        raise ValueError("Holdout manifest changed; stop and version explicitly")
    dev = tuple({
        **row, "answerable": row["id"] != "unknown_machine_serial",
        "unresolved_contradiction": row["id"] == "conflicting_alarm_reports",
        "relevant_sources": DEV_RELEVANCE_OVERRIDE.get(
            row["id"], list(row["gold_sources"]))
    } for row in DEV_CASES)
    holdout = tuple(dataset["cases"])
    if any("relevant_sources" not in x or "answerable" not in x
           for x in (*dev, *holdout)):
        raise ValueError("Evidence/answerability contract absent")
    if set(v["id"] for v in dev) & set(v["id"] for v in holdout):
        raise ValueError("Leak: overlapping case IDs")
    if len({v["id"] for v in holdout}) != len(holdout):
        raise ValueError("Duplicated holdout case")
    # No external source is allowed to self-label "approved"; the grader
    # uses case-level gold fixed before running candidate methods.
    methods = {}
    for method in METHODS:
        calibration = []
        for cutoff in CUTOFFS:
            observed = [_evaluate_one(row, method=method, cutoff=cutoff)
                        for row in dev]
            calibration.append(( _weighted_dev_loss(observed), -sum(x["exact"] for x in observed),
                                 cutoff, observed))
        loss, _neg_exact, cutoff, dev_rows = min(calibration, key=lambda v: v[:3])
        holdout_rows = [_evaluate_one(row, method=method, cutoff=cutoff)
                        for row in holdout]
        methods[method] = {
            "dev_cutoff_calibrated": cutoff,
            "dev_weighted_loss": loss,
            "development": _summarize(dev_rows),
            "holdout": _summarize(holdout_rows),
        }
    result = {
        "status": "INDEPENDENT_SYNTHETIC_RETRIEVAL_EXPERIMENT_NOT_PRODUCT_APPROVAL",
        "protocol": "v2-dev-relevance-calibrate-on-8, v2-holdout-relevance-evaluate-on-16",
        "source_manifest_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "source_registry": dataset["external_upstream"],
        "training_gold_visible_to_methods": False,
        "holdout_gold_visible_to_methods": False,
        "all_calibration_cutoffs": list(CUTOFFS),
        "answerability_is_not_inferred_by_retrieval": True,
        "v1_amendment": "Old empty source labels rewarded skipping relevant unanswerable evidence; v2 scores retrieval separately.",
        "model_inference_executed": False,
        "business_outcome_verified": False,
        "release_authorized": False,
        "methods": methods,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                 sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "holdout_sha256": result["source_manifest_sha256"],
        "methods": {k: {"cutoff": v["dev_cutoff_calibrated"],
                        "dev_exact": v["development"]["exact"],
                        "holdout_exact": v["holdout"]["exact"],
                        "holdout_empty_with_evidence": v["holdout"]["retrieval_empty_with_evidence"],
                        "holdout_contamination": v["holdout"]["contamination_cases"]}
                    for k, v in methods.items()},
    }, ensure_ascii=False, sort_keys=True))
    return result


if __name__ == "__main__":
    run()
