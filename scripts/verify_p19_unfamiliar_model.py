"""P19 prospective unfamiliar tasks: real local 7B, no prewritten fix.

The task data and sealed gold are committed BEFORE model inference.
A separate task author (this repository change) provides goals and
reference cases; that is not an external human reviewer. Only PUBLIC
examples + buggy source + textual goals enter the Ollama proposer.
All candidate execution and holdout scoring remain inside the existing
P12/P13 offline Docker / SQLite pipeline, not a second runner.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from cognition_agent_os import local_model
from scripts.verify_actual_local_model import MODEL,evaluate_one

# Prospectively authored, distinct from P14/P17/P18 known samples.
# The local model only sees source, goal_statement and public cases,
# NEVER hidden tests, expected labels or these comments/reference checks.
CASES=[
    {
        "name":"dv_latest_retry_per_test",
        "goal_statement":(
            "Each execution record has suite, test, numeric attempt and result. "
            "For each unique suite/test keep the record with the HIGHEST "
            "attempt, regardless of input order. Exactly PASS counts as a "
            "pass; other latest results count as a failure. Return passed "
            "and failed counts, plus sorted latest_failures as suite/test."
        ),
        "source":(
            "def calculate(data):\n"
            "    latest = {}\n"
            "    for row in data['records']:\n"
            "        key = (row['suite'],row['test'])\n"
            "        if key not in latest:\n"
            "            latest[key] = row\n"
            "    failed = sorted(s + '/' + t for (s,t),row in latest.items() "
            "if row['result'] != 'PASS')\n"
            "    return {'passed':len(latest)-len(failed), "
            "'failed':len(failed), 'latest_failures':failed}\n"
        ),
        "public":[
            {"input":{"records":[
                {"suite":"gpio","test":"io","attempt":1,"result":"FAIL"},
                {"suite":"gpio","test":"io","attempt":2,"result":"PASS"},
                {"suite":"pvt","test":"alarm","attempt":1,"result":"FAIL"}]},
             "expected":{"passed":1,"failed":1,
                         "latest_failures":["pvt/alarm"]}},
            {"input":{"records":[
                {"suite":"a","test":"x","attempt":1,"result":"PASS"},
                {"suite":"b","test":"z","attempt":1,"result":"FAIL"},
                {"suite":"b","test":"z","attempt":2,"result":"PASS"},
                {"suite":"a","test":"y","attempt":1,"result":"FAIL"},
                {"suite":"a","test":"x","attempt":2,"result":"FAIL"}]},
             "expected":{"passed":1,"failed":2,
                         "latest_failures":["a/x","a/y"]}}
        ],
        "hidden":[
            {"input":{"records":[]},
             "expected":{"passed":0,"failed":0,"latest_failures":[]}},
            {"input":{"records":[
                {"suite":"x","test":"a","attempt":3,"result":"PASS"},
                {"suite":"x","test":"a","attempt":2,"result":"FAIL"},
                {"suite":"z","test":"b","attempt":1,"result":"PASS"}]},
             "expected":{"passed":2,"failed":0,"latest_failures":[]}},
            {"input":{"records":[
                {"suite":"p","test":"c","attempt":2,"result":"ERROR"},
                {"suite":"p","test":"c","attempt":1,"result":"PASS"},
                {"suite":"p","test":"d","attempt":1,"result":"FAIL"}]},
             "expected":{"passed":0,"failed":2,
                         "latest_failures":["p/c","p/d"]}}
        ]
    },
    {
        "name":"half_open_interval_union",
        "goal_statement":(
            "Compute the total length covered by the UNION of all "
            "half-open integer intervals [start,end). Intervals can "
            "overlap, touch, repeat, be empty or start at negative "
            "positions. Do not double-count overlapping positions. "
            "Return one JSON object with integer key covered."
        ),
        "source":(
            "def calculate(data):\n"
            "    return {'covered': sum(end-start for start,end "
            "in data['intervals'])}\n"
        ),
        "public":[
            {"input":{"intervals":[[1,4],[2,5]]},
             "expected":{"covered":4}},
            {"input":{"intervals":[[0,2],[4,6]]},
             "expected":{"covered":4}}
        ],
        "hidden":[
            {"input":{"intervals":[]},"expected":{"covered":0}},
            {"input":{"intervals":[[-2,1],[0,4]]},
             "expected":{"covered":6}},
            {"input":{"intervals":[[1,3],[3,5],[3,5]]},
             "expected":{"covered":4}},
            {"input":{"intervals":[[5,5],[4,8]]},
             "expected":{"covered":4}}
        ]
    }
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    if MODEL!="qwen2.5-coder:7b":
        raise RuntimeError("P19 requires explicitly opted-in genuine local 7B")
    tags=local_model._request("GET","/api/tags",None,10)
    installed={entry.get("name") for entry in tags.get("models",[])
               if isinstance(entry,dict)}
    if MODEL not in installed:
        raise RuntimeError("P19 model not installed: no auto-download or cloud fallback")
    proof=local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":"Return JSON {\\\"probe\\\":true}.",
        "stream":False,"format":"json",
        "options":{"temperature":0,"num_predict":50},
        "keep_alive":"0"},90)
    if proof.get("done") is not True or not isinstance(proof.get("response"),str):
        raise RuntimeError("Real local model completion not observed")
    digest=sha(json.dumps(CASES,sort_keys=True).encode())
    with tempfile.TemporaryDirectory(prefix="cognition-p19-prospective-") as temp:
        result=[]
        for case in CASES:
            measured=evaluate_one(Path(temp),case,
                                  goal_statement=case["goal_statement"])
            result.append(measured)
            print(json.dumps({"test":"p19_unfamiliar_case",**measured},
                             sort_keys=True),flush=True)
    summary={"test":"p19_unfamiliar_prospective_model",
             "real_ollama_generation_completed":True,
             "model":MODEL,"case_manifest_digest":digest,
             "cases":len(CASES),"frozen_candidates":sum(
                 bool(x["candidate_frozen"]) for x in result),
             "public_pass":sum(bool(x["public_pass"]) for x in result),
             "hidden_pass":sum(bool(x["holdout_pass"]) for x in result),
             "source_unchanged":all(x["source_unchanged"] for x in result),
             "prewritten_patch_fallback":False,
             "owner_machine_touched":False,"paid_model_api_used":False,
             "reference_labels_from_external_human":False}
    print(json.dumps(summary,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
