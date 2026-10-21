"""P14 experimental non-metered REAL Ollama coder on native Linux CI.

No monkeypatch, no scripted code proposal, no hidden benchmark labels in
model prompts. This *measurement* is not an assertion of autonomous quality:
0/N hidden success remains a valid, explicit measured outcome if the genuine
installed loopback model generated complete responses.

The model and Docker are preinstalled only in temporary CI runner, never
on owner PC. Docker is used only for actual candidate tests; no host exec.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from cognition_agent_os import local_model
from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.runner import run_once
from cognition_agent_os.repo_repair import audit_repo,review_repo
from cognition_agent_os.repo_refinement import refine_repo_public
from cognition_agent_os.container_lab import run_suite,cases_from_bytes,ContainerUnavailable

# The hosted benchmark tests two independently installed non-metered
# coder weights; accepting an arbitrary model name is deliberately disallowed.
MODEL=os.environ.get("P14_LOCAL_MODEL","qwen2.5-coder:0.5b")
if MODEL not in ("qwen2.5-coder:0.5b","qwen2.5-coder:1.5b",
                 "qwen2.5-coder:3b"):
    raise ValueError("P14 benchmark model is not on explicit local allowlist")
ENTRY=(
    "import json,sys\n"
    "from calculator import calculate\n"
    "print(json.dumps(calculate(json.loads(sys.stdin.read()))))\n"
)
# Authored independently of model outputs; NOT model-generated golden tests.
CASES=[
    {
        "name":"invoice_discount_then_postage",
        "source":(
            "def calculate(data):\n"
            "    subtotal = sum(line['price'] * line['qty'] for line in data['items'])\n"
            "    return {'total': subtotal + data['discount'] + data['postage']}\n"
        ),
        "public":[
            {"input":{"items":[{"price":10,"qty":2}],"discount":3,"postage":4},
             "expected":{"total":21}},
            {"input":{"items":[{"price":7,"qty":3},{"price":2,"qty":2}],
                      "discount":5,"postage":0},"expected":{"total":20}}
        ],
        "hidden":[
            {"input":{"items":[],"discount":0,"postage":9},"expected":{"total":9}},
            {"input":{"items":[{"price":6,"qty":5}],"discount":4,"postage":1},
             "expected":{"total":27}}
        ]
    },
    {
        "name":"distinct_positive_above_threshold",
        "source":(
            "def calculate(data):\n"
            "    values = data['values']\n"
            "    return {'count': len([n for n in values if n >= data['threshold']])}\n"
        ),
        "public":[
            {"input":{"values":[3,3,0,-1,8,12],"threshold":3},
             "expected":{"count":2}},
            {"input":{"values":[1,1,1,2,3,4],"threshold":1},
             "expected":{"count":3}}
        ],
        "hidden":[
            {"input":{"values":[0,0,-4,5,5,7],"threshold":0},
             "expected":{"count":2}},
            {"input":{"values":[],"threshold":8},"expected":{"count":0}}
        ]
    },
]


def sha(b):return hashlib.sha256(b).hexdigest()


def source_cases(root,case):
    fx=root/"fixtures";fx.mkdir()
    ws=root/"workspace";ws.mkdir()
    db=root/"state.sqlite"
    fx.joinpath("main.py").write_text(ENTRY,encoding="utf-8")
    fx.joinpath("calculator.py").write_text(case["source"],encoding="utf-8")
    public=json.dumps(case["public"],sort_keys=True).encode()
    hidden=json.dumps(case["hidden"],sort_keys=True).encode()
    fx.joinpath("visible.json").write_bytes(public)
    fx.joinpath("sealed.json").write_bytes(hidden)
    # P12 accepts an initial whole-file candidate, but no prepared fix.
    # The source's existing broken bytes are a safe non-changing specimen.
    fx.joinpath("seed.json").write_text(json.dumps({"changes":[
        {"path":"calculator.py","content":case["source"]}]}),encoding="utf-8")
    spec={"kind":"repo_container_repair",
          "files":["main.py","calculator.py"],"entrypoint":"main.py",
          "candidate":"seed.json","visible":"visible.json",
          "holdout":"sealed.json","holdout_sha256":sha(hidden)}
    with closing(connect(db)) as con:
        initialize(con)
        tid=create_task(con,spec)
    return fx,ws,db,tid


def only_status(output):
    return {k:v for k,v in output.items()
            if k in ("status","reason","model_called","passes","total",
                     "public_passes","holdout_passes","holdout_total","diagnostic",
                     "validation_failure",
                     "model_candidates_tested")}


def evaluate_one(parent,case):
    root=parent/case["name"]
    root.mkdir()
    fx,ws,db,tid=source_cases(root,case)
    # All golden labels are kept solely in fixture filesystem; only
    # PUBLIC cases can enter the generation prompt.
    baseline_sources={
        "main.py":fx.joinpath("main.py").read_bytes(),
        "calculator.py":fx.joinpath("calculator.py").read_bytes()}
    visible=cases_from_bytes(fx.joinpath("visible.json").read_bytes())
    if run_suite(baseline_sources,{},"main.py",visible)["passes"]==len(visible):
        raise RuntimeError("Benchmark baseline does not reproduce visible failure")
    before={p:sha(b) for p,b in baseline_sources.items()}
    start=time.monotonic()
    # Strictly unmocked existing Ollama admission → localhost request
    # → JSON candidate validation → immutable SQLite artifact.
    planned=run_once(db,ws,fx,planner_mode="ollama-local",local_model=MODEL)
    output={"case":case["name"],"model":MODEL,
            "initial":only_status(planned),"model_called":bool(planned.get("model_called")),
            "candidate_frozen":planned.get("status")=="NEEDS_REVIEW",
            "public_pass":False,"holdout_pass":False,
            "revision_attempts":0,"model_generated_unmodified":True,
            "source_unchanged":False}
    candidate_id=tid
    if output["candidate_frozen"]:
        audit=audit_repo(db,ws,fx,tid)
        if audit["status"]!="REPO_BYTES_MECHANICALLY_VALID":
            raise RuntimeError("Real model candidate frozen without valid hashes")
        # This is the existing independent Docker oracle, never a mock.
        verdict=review_repo(db,ws,fx,tid)
        output["first_review"]=only_status(verdict)
        if verdict["status"]=="REPAIR_LAB_VERIFIED":
            output["public_pass"]=True
            output["holdout_pass"]=True
        elif verdict["status"]=="HOLDOUT_REFUTED":
            output["public_pass"]=True
        elif verdict["status"]=="PUBLIC_REFUTED":
            # One bounded genuine loopback model feedback experiment;
            # refusal/0 success is an honest result, no correct patch fallback.
            refined=refine_repo_public(db,ws,fx,tid,model=MODEL,max_attempts=2)
            output["refinement"]=only_status(refined)
            output["revision_attempts"]=refined.get("model_candidates_tested",
                                                   refined.get("attempts",0))
            if refined["status"]=="REVISED_PUBLIC_CANDIDATE_FROZEN":
                child=refined["child_task_id"]
                candidate_id=child
                reviewed=review_repo(db,ws,fx,child)
                output["refined_review"]=only_status(reviewed)
                if reviewed["status"] in ("HOLDOUT_REFUTED","REPAIR_LAB_VERIFIED"):
                    output["public_pass"]=True
                if reviewed["status"]=="REPAIR_LAB_VERIFIED":
                    output["holdout_pass"]=True
    output["source_unchanged"]=(
        all(sha(fx.joinpath(p).read_bytes())==h for p,h in before.items()))
    if not output["source_unchanged"]:
        raise RuntimeError("Model/worker modified original repository files")
    output["elapsed_seconds"]=round(time.monotonic()-start,2)
    # Never include hidden labels, hidden file bytes, raw free-form
    # model generations or candidate source text in telemetry output.
    return output


def main():
    # No model or network fallback and no auto-pull from application.
    tags=local_model._request("GET","/api/tags",None,10)
    installed={x.get("name") for x in tags.get("models",[])
               if isinstance(x,dict)}
    if MODEL not in installed:
        raise RuntimeError("Required real local model missing: benchmark must not fake success")
    proof=local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":"Reply with the single JSON object {\"probe\":true}.",
        "stream":False,"format":"json","options":{"temperature":0,"num_predict":50},
        "keep_alive":"0"},90)
    if proof.get("done") is not True or not isinstance(proof.get("response"),str):
        raise RuntimeError("Installed model did not complete genuine token generation")
    # A model's content need not be correct to prove genuine inference.
    summary={"status":"REAL_LOCAL_INFERENCE_MEASURED",
             "model":MODEL,"real_ollama_generation_completed":True,
             "using_cloud_api":False,"prewritten_patch_fallback":False,
             "owner_pc_touched":False,"hidden_test_separate":True,
             "testset_digest":sha(json.dumps(CASES,sort_keys=True).encode())}
    with tempfile.TemporaryDirectory(prefix="cognition-p14-real-model-") as temp:
        results=[]
        for case in CASES:
            try:
                result=evaluate_one(Path(temp),case)
            except ContainerUnavailable as exc:
                raise RuntimeError("Native Docker execution required, not fallback") from exc
            results.append(result)
            print(json.dumps({"test":"real_model_case",**result},sort_keys=True),flush=True)
    summary.update({"cases":len(results),
                    "frozen_candidates":sum(bool(x["candidate_frozen"]) for x in results),
                    "public_pass":sum(bool(x["public_pass"]) for x in results),
                    "hidden_pass":sum(bool(x["holdout_pass"]) for x in results),
                    "results":results})
    print(json.dumps({"test":"p14_real_nonmetered_local_model",
                     **summary},sort_keys=True),flush=True)
    # Quality is reported, NOT used to disguise a real-but-bad model as
    # infrastructure failure. A missing model or lack of actual inference
    # is however an infrastructure FAIL (checked above).


if __name__=="__main__":
    main()
