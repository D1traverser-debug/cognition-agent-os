"""Paired causal probe of SciFact classification enum-order bias (REAL local model).

Built on exact original SciFact publisher archive and independent original
dev annotations from PR #31. Compare TWO prompts with exactly the same claim,
evidence, model weights, sampling configuration and schema grammar, differing
ONLY in label enum ordering; alternate presentation order per claim to control
run-time order effects. The model sees NO expert label metadata.

This is a diagnostic of tool-schema induced output bias, NOT an approved
scientific claim verifier, independent truth certification or business result.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import measure_external_scifact_claim_judgment as original  # noqa: E402

OUT = ROOT / "evaluation" / "scifact_label_order_causal_results.json"
ORDERS = {
    "support_first": ("SUPPORT", "CONTRADICT", "INSUFFICIENT"),
    "contradict_first": ("CONTRADICT", "SUPPORT", "INSUFFICIENT"),
}
MODEL = "qwen2.5:1.5b"
EXPECTED_SHA = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"
EXPECTED_CLAIM_IDS = "026fe3d9785461f40433120502c22c7583abdff99304d86c56e11cc141a955a7"
EXPECTED_MODEL_DIGEST = "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"
CONDITIONS = original.CONDITIONS


def ordered_schema(order: str) -> dict:
    if order not in ORDERS:
        raise ValueError("Unknown pre-registered enum permutation")
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "label": {
                "type": "string", "enum": list(ORDERS[order])
            }
        },
        "required": ["label"],
    }


def infer_claim(prompt: str, order: str) -> dict:
    from cognition_agent_os import local_model
    started = time.monotonic()
    # Same Ollama endpoint/options as PR #31 original _infer, with only
    # ordered_schema varying. No other prompt/path transformation.
    response = local_model._request("POST", "/api/generate", {
        "model": MODEL, "prompt": prompt, "stream": False,
        "format": ordered_schema(order),
        "options": {"temperature": 0, "num_predict": 100},
        "keep_alive": "0",
    }, 120)
    seconds = round(time.monotonic() - started, 2)
    if response.get("done") is not True:
        return {"prediction": "INVALID", "error": "INCOMPLETE", "latency_s": seconds}
    try:
        decoded = json.loads(response["response"])
    except (KeyError, ValueError, TypeError):
        return {"prediction": "INVALID", "error": "INVALID_JSON", "latency_s": seconds}
    if (not isinstance(decoded, dict) or set(decoded) != {"label"}
        or decoded["label"] not in original.LABELS):
        return {"prediction": "INVALID", "error": "INVALID_SCHEMA_LABEL",
                "latency_s": seconds}
    return {"prediction": decoded["label"], "latency_s": seconds}


def score(records: list[dict]) -> dict:
    comparison = {}
    for order in ORDERS:
        for condition in CONDITIONS:
            rows = [x for x in records if x["order"] == order
                    and x["condition"] == condition]
            if len(rows) != original.BALANCED_PER_LABEL * 2:
                raise ValueError("Insufficient paired experimental rows")
            baseline = condition == "no_evidence"
            correct = sum(
                x["prediction"] == ("INSUFFICIENT" if baseline else x["external_gold"])
                for x in rows
            )
            comparison[order + "/" + condition] = {
                "total": len(rows), "correct": correct,
                "rate": round(correct / len(rows), 4),
                "prediction_histogram": dict(Counter(x["prediction"] for x in rows)),
                "gold_by_prediction": {
                    label: dict(Counter(x["prediction"] for x in rows
                                        if x["external_gold"] == label))
                    for label in ("SUPPORT", "CONTRADICT")},
                "mean_seconds": round(statistics.mean(x["latency_s"] for x in rows), 2),
            }
    flips = {}
    for condition in CONDITIONS:
        bykey = {
            (x["claim_id"], x["order"]): x for x in records
            if x["condition"] == condition
        }
        ids = {x["claim_id"] for x in records if x["condition"] == condition}
        pairs = []
        for id_ in sorted(ids):
            a=bykey[(id_,"support_first")]
            b=bykey[(id_,"contradict_first")]
            correct = "INSUFFICIENT" if condition == "no_evidence" else a["external_gold"]
            if a["external_gold"] != b["external_gold"]:
                raise ValueError("Pair has changed external label")
            pairs.append({
                "claim_id": id_, "gold": a["external_gold"],
                "support_first": a["prediction"],
                "contradict_first": b["prediction"],
                "same": a["prediction"] == b["prediction"],
                "only_support_first_correct":
                    (a["prediction"] == correct and b["prediction"] != correct),
                "only_contradict_first_correct":
                    (a["prediction"] != correct and b["prediction"] == correct),
            })
        flips[condition] = {
            "same_prediction": sum(x["same"] for x in pairs),
            "changed_prediction": sum(not x["same"] for x in pairs),
            "only_support_first_correct": sum(
                x["only_support_first_correct"] for x in pairs),
            "only_contradict_first_correct": sum(
                x["only_contradict_first_correct"] for x in pairs),
            "paired_outcomes": pairs,
        }
    return {"by_order_condition": comparison, "within_claim_order_effect": flips}


def _validate_independent_inputs():
    from cognition_agent_os import local_model
    tags=local_model._request("GET","/api/tags",None,15)
    model_digest={x.get("name"): x.get("digest")
                  for x in tags.get("models",[]) if isinstance(x,dict)}.get(MODEL)
    if model_digest != EXPECTED_MODEL_DIGEST:
        raise ValueError("Original model weight digest mismatch; capacity and "
                         "enum-order comparison would be confounded")
    corpus, claims, provenance = original._load_official()
    if provenance["source_archive_sha256"] != EXPECTED_SHA:
        raise ValueError("Publisher dataset digest changed")
    sampled=original._balanced_sample(original._candidates(corpus,claims),
                                      per_label=original.BALANCED_PER_LABEL)
    actual=hashlib.sha256("\n".join(x["id"] for x in sampled).encode()).hexdigest()
    if actual != EXPECTED_CLAIM_IDS:
        raise ValueError("Sample claims drifted; cannot compare with previous runs")
    return sampled, provenance


def run(*, out: Path=OUT):
    sampled, provenance = _validate_independent_inputs()
    results = {
        "status": "SCHEMA_ORDER_BIAS_PROBE_NOT_PRODUCT_ACCEPTANCE",
        "hypothesis": "The original fixed support-first enum grammar biases response category",
        "dataset_provenance": provenance,
        "model": MODEL, "model_digest": EXPECTED_MODEL_DIGEST,
        "sample_claim_ids_sha256": EXPECTED_CLAIM_IDS,
        "schema_enums": {name:list(values) for name,values in ORDERS.items()},
        "same_prompt_model_and_inference_settings": True,
        "within_claim_order_counterbalanced": True,
        "annotation_never_supplied_to_model": True,
        "ground_truth_origin": "Original AllenAI SciFact dev annotator",
        "business_outcome_verified": False,
        "autonomous_action_authorized": False,
        "expected_real_model_calls": original.BALANCED_PER_LABEL * 2 * len(CONDITIONS) * 2,
        "trials": [],
        "scores": None,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    for claim in sampled:
        # Deterministic balancing of actual call order. This is separate
        # from the classifier label enum ordering under test.
        digest=hashlib.sha256(("COUNTERBALANCE|" + claim["id"]).encode()).digest()
        call_orders=("support_first","contradict_first") if digest[0]%2==0 else (
            "contradict_first","support_first")
        for condition in CONDITIONS:
            prompt=original._prompt(claim,condition)
            for order in call_orders:
                obs=infer_claim(prompt, order)
                row={**obs, "claim_id":claim["id"],"condition":condition,
                     "order":order,"external_gold":claim["label"],
                     "source_document_id":claim["evidence_doc_id"],
                     "gold_evidence_hash":hashlib.sha256(
                         claim["gold_rationale"].encode()).hexdigest()}
                results["trials"].append(row)
                print("TRIAL "+json.dumps(row,sort_keys=True),flush=True)
                out.write_text(json.dumps(results,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
    results["scores"]=score(results["trials"])
    out.write_text(json.dumps(results,sort_keys=True,indent=2)+"\n",
                   encoding="utf-8")
    summary={key:{"correct":item["correct"],"total":item["total"],
                  "histogram":item["prediction_histogram"]}
             for key,item in results["scores"]["by_order_condition"].items()}
    effects={key:{k:v for k,v in item.items() if k!="paired_outcomes"}
             for key,item in results["scores"]["within_claim_order_effect"].items()}
    print("RESULT "+json.dumps({"score":summary,"order_effect":effects},
                                sort_keys=True),flush=True)
    return results


def smoke():
    assert ordered_schema("support_first")["properties"]["label"]["enum"][0] == "SUPPORT"
    assert ordered_schema("contradict_first")["properties"]["label"]["enum"][0] == "CONTRADICT"
    try:
        ordered_schema("user_defined")
    except ValueError:
        pass
    else:
        raise AssertionError("Unapproved enum order accepted")
    toy=[]
    for condition in CONDITIONS:
        for label in ("SUPPORT","CONTRADICT"):
            for order in ORDERS:
                toy.append({
                    "condition":condition,"external_gold":label,
                    "claim_id":label,"order":order,
                    "prediction":"INSUFFICIENT" if condition=="no_evidence" else label,
                    "latency_s":0.01})
    # Full scoring expects exactly 24 cases/condition/order; use mock
    # construction for deterministic safety, not model-result validation.
    populated=[dict(x,claim_id=x["claim_id"]+str(i))
               for i in range(original.BALANCED_PER_LABEL)
               for x in toy]
    scores=score(populated)
    for key,val in scores["by_order_condition"].items():
        assert val["correct"]==24,(key,val)
    print("SCIFACT_LABEL_ORDER_SMOKE_PASS")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--out",type=Path,default=OUT)
    args=parser.parse_args()
    if args.smoke:
        smoke()
    else:
        run(out=args.out)
