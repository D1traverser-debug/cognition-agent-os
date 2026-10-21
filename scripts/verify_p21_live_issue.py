"""P21: open real externally reported GitHub issue -> pinned actual code -> Docker.

Upstream: more-itertools/more-itertools issue #1332, opened 2026-10-15,
state OPEN at source reconnaissance on 2026-10-21. The 2026-10-14 code
was published before the complaint. This is a real issue, NOT a
maintainer-accepted pull request or a private blind problem.

We extract only the exact self-contained upstream set_partitions function
from a checked full Git-blob snapshot; the original 175KB module cannot
be passed into the existing <=16KB lab unchanged. That extraction is a
declared *scope restriction*, not whole-repository repair. The proposer
never sees private gold or any upstream corrected source.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"src"))

from cognition_agent_os import local_model
from cognition_agent_os.container_lab import run_suite,cases_from_bytes
from scripts.verify_actual_local_model import MODEL,evaluate_one,ENTRY

UPSTREAM_REPOSITORY="more-itertools/more-itertools"
UPSTREAM_COMMIT="4aeb4338ae1407d8da9723e86da99efeb446f719"
UPSTREAM_PATH="more_itertools/more.py"
UPSTREAM_GIT_BLOB="9c56ab37558733ece94d676f71d502d8048bc1d5"
ISSUE_NUMBER=1332
ISSUE_URL="https://github.com/more-itertools/more-itertools/issues/1332"
ISSUE_CREATED="2026-10-15T10:03:18Z"
START_MARKER="\ndef set_partitions("
END_MARKER="\n\nclass time_limited:"
MAX_ORIGINAL_BYTES=225000
# Reporter says [] -> [[]] and the n=0 Bell number should be 1;
# explicit k=1 still yields none and k=0 still raises ValueError.
# These acceptance cases are Agent-expanded from the REAL issue report,
# not externally supplied private tests or maintainer verdicts.
PUBLIC=[
    {"input":{"items":[]},"expected":{"count":1,"has_empty_partition":True}},
    {"input":{"items":["a","b"]},"expected":
        {"count":2,"has_empty_partition":False}},
]
HIDDEN=[
    {"input":{"items":[],"k":1},"expected":
        {"count":0,"has_empty_partition":False}},
    {"input":{"items":[],"k":0},"expected":{"error":"ValueError"}},
    {"input":{"items":["a"]},"expected":
        {"count":1,"has_empty_partition":False}},
    {"input":{"items":["a","b","c"]},"expected":
        {"count":5,"has_empty_partition":False}},
    {"input":{"items":[],"min_size":2},"expected":
        {"count":1,"has_empty_partition":True}},
    {"input":{"items":["a","b","c"],"k":2},"expected":
        {"count":3,"has_empty_partition":False}},
    {"input":{"items":[0,1,2,3]},"expected":
        {"count":15,"has_empty_partition":False}},
    {"input":{"items":[0,1,2,3,4]},"expected":
        {"count":52,"has_empty_partition":False}},
]
GOAL_STATEMENT=(
    "Repair more-itertools set_partitions, as requested in live GitHub "
    "Issue #1332: an empty iterable with k unspecified must yield the "
    "one empty partition [[]], not yield nothing. Explicit k=1 for "
    "empty input must still yield no partitions, and k=0 must still "
    "raise ValueError. Preserve all non-empty Bell-number behavior "
    "and min/max block-size filtering; an empty partition has no "
    "blocks so size limits do not remove it. Avoid modifying the "
    "JSON adapter or bypassing actual upstream function execution."
)


def git_blob_sha1(raw:bytes)->str:
    return hashlib.sha1(
        b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw).hexdigest()


def source_url()->str:
    return (f"https://raw.githubusercontent.com/{UPSTREAM_REPOSITORY}/"
            f"{UPSTREAM_COMMIT}/{UPSTREAM_PATH}")


def fetch_pinned_source()->bytes:
    with urlopen(source_url(),timeout=25) as response:
        raw=response.read(MAX_ORIGINAL_BYTES+1)
    if (len(raw)>MAX_ORIGINAL_BYTES
        or git_blob_sha1(raw)!=UPSTREAM_GIT_BLOB):
        raise ValueError("Original upstream source Git blob differs from pin")
    return raw


def extract_unmodified_function(raw:bytes)->str:
    if git_blob_sha1(raw)!=UPSTREAM_GIT_BLOB:
        raise ValueError("Cannot extract from changed external source")
    content=raw.decode("utf-8")
    if content.count(START_MARKER)!=1 or content.count(END_MARKER)!=1:
        raise ValueError("Original upstream function boundaries missing")
    first=content.index(START_MARKER)+1
    last=content.index(END_MARKER,first)
    if last<=first:
        raise ValueError("Upstream function boundary order invalid")
    code=content[first:last].rstrip()+"\n"
    if (len(code.encode("utf-8"))>12000
        or not code.startswith("def set_partitions(")
        or "def set_partitions_helper(" not in code
        or "for k in range(1, n + 1):" not in code):
        raise ValueError("Unexpected upstream function scope")
    return code


def prepare_case(raw:bytes)->dict:
    original=extract_unmodified_function(raw)
    # Adapter reads JSON and measures WHAT the original function yields.
    # It cannot grant the model authority to edit the upstream repository.
    adapter=(
        "\n\ndef calculate(data):\n"
        "    try:\n"
        "        groups = list(set_partitions(\n"
        "            data['items'], data.get('k'),\n"
        "            data.get('min_size'), data.get('max_size')))\n"
        "    except ValueError:\n"
        "        return {'error': 'ValueError'}\n"
        "    return {'count': len(groups),\n"
        "            'has_empty_partition': [] in groups}\n"
    )
    result={"name":"external_live_issue_1332_empty_set_partitions",
            "source":original+adapter,
            "goal_statement":GOAL_STATEMENT,
            "public":PUBLIC,
            "hidden":HIDDEN}
    if len(result["source"].encode("utf-8"))>16384:
        raise ValueError("Adapted upstream function exceeds lab limit")
    return result


def candidate_preserves_adapter(candidate:bytes,original_function:str,
                                adapter:str)->bool:
    # A Docker PASS alone would also accept a rewritten test adapter.
    # Require the candidate to change the isolated upstream function
    # while retaining the original test/input conversion verbatim.
    try:
        body=candidate.decode("utf-8")
    except UnicodeError:
        return False
    return (body.startswith("def set_partitions(")
            and body.count("def calculate(data):")==1
            and body.endswith(adapter)
            and body[:-len(adapter)]!=original_function)


def check_independent_patch_scope(root:Path,case:dict,raw:bytes)->dict:
    old=extract_unmodified_function(raw)
    suffix=case["source"][len(old):]
    staged=root/case["name"]/"workspace"/"repo_lab"
    if staged.is_symlink() or not staged.is_dir():
        return {"scope_verified":False,"reason":"NO_ACCEPTED_STAGED_PATCH"}
    # One original worker, at most one accepted child per P13
    # lineage. No data from PRIVATE holdout reaches proposer.
    dirs=[p for p in staged.iterdir() if p.is_dir() and not p.is_symlink()]
    if len(dirs)!=1:
        return {"scope_verified":False,"reason":"AMBIGUOUS_STAGED_PATCH"}
    candidate=dirs[0]/"calculator.py"
    if (candidate.is_symlink() or not candidate.is_file()
        or (dirs[0]/"main.py").exists()):
        return {"scope_verified":False,"reason":"PATCH_REWROTE_ENTRYPOINT_OR_NO_FUNCTION"}
    if not candidate_preserves_adapter(candidate.read_bytes(),old,suffix):
        return {"scope_verified":False,"reason":"PATCH_CHANGED_ADAPTER_OR_NOT_UPSTREAM_FUNCTION"}
    return {"scope_verified":True,"reason":"FUNCTION_ONLY_PATCH_AND_ADAPTER_UNCHANGED"}


def main():
    # No silent model download and no external GitHub source read except
    # when P21 explicitly opted into one temporary 7B experiment.
    if MODEL!="qwen2.5-coder:7b" or os.environ.get("P21_ISSUE_OPT_IN")!="1":
        raise RuntimeError("P21 requires one-time explicitly approved local 7B CI")
    raw=fetch_pinned_source()
    case=prepare_case(raw)
    manifest=hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest()
    # Baseline failure is actual executed old upstream behavior in Docker,
    # NOT our explanation about what the buggy function might have done.
    baseline={"main.py":ENTRY.encode(),
              "calculator.py":case["source"].encode()}
    baseline_public=run_suite(baseline,{},"main.py",
                              cases_from_bytes(json.dumps(PUBLIC).encode()))
    if baseline_public["passes"]!=1 or baseline_public["total"]!=2:
        raise RuntimeError("External issue's baseline defect is not reproduced")
    print(json.dumps({
        "test":"p21_external_reported_issue_baseline",
        "issue":ISSUE_URL,"issue_reported_open_as_of":"2026-10-21",
        "issue_created":ISSUE_CREATED,
        "upstream_repository":UPSTREAM_REPOSITORY,
        "upstream_commit":UPSTREAM_COMMIT,
        "upstream_blob_verified":git_blob_sha1(raw)==UPSTREAM_GIT_BLOB,
        "scope":"EXACT_UPSTREAM_FUNCTION_EXTRACT_NOT_ENTIRE_PROJECT",
        "original_function_sha256":hashlib.sha256(
            extract_unmodified_function(raw).encode()).hexdigest(),
        "manifest_sha256":manifest,
        "public_failing_baseline":baseline_public["total"]-
                                    baseline_public["passes"],
        "public_total":baseline_public["total"],
        "gold_source":"REPORTER_OWNED_VISIBLE_EXPECTATION_PLUS_AGENT_DERIVED_EDGE_CASES",
        "external_maintainer_acceptance":False,
        "no_upstream_repair_write":True
    },sort_keys=True),flush=True)
    installed=local_model._request("GET","/api/tags",None,10)
    models={m.get("name") for m in installed.get("models",[])
            if isinstance(m,dict)}
    if MODEL not in models:
        raise RuntimeError("Local 7B model unavailable; no auto-pull")
    probe=local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":'Return the JSON object {"probe":true}.',
        "stream":False,"format":"json",
        "options":{"temperature":0,"num_predict":50},"keep_alive":"0"},90)
    if probe.get("done") is not True or not isinstance(probe.get("response"),str):
        raise RuntimeError("No real Ollama model token generation observed")
    with tempfile.TemporaryDirectory(prefix="cognition-p21-real-issue-") as temp:
        root=Path(temp)
        result=evaluate_one(root,case,
                            goal_statement=case["goal_statement"])
        patch_scope=(check_independent_patch_scope(root,case,raw)
                     if result["holdout_pass"] else
                     {"scope_verified":False,"reason":"HOLDOUT_NOT_ACCEPTED"})
    print(json.dumps({"test":"p21_real_reported_issue_result",
        "issue":ISSUE_URL,"manifest_sha256":manifest,
        "model":MODEL,"model_completion_genuine":True,
        "frozen_candidate":result["candidate_frozen"],
        "public_pass":result["public_pass"],
        "heldout_pass":result["holdout_pass"],
        "function_only_contract_pass":result["holdout_pass"] and
                                      patch_scope["scope_verified"],
        "patch_scope":patch_scope,
        "heldout_case_count":len(HIDDEN),
        "revision_attempts":result["revision_attempts"],
        "original_source_unchanged":result["source_unchanged"],
        "external_upstream_repo_modified":False,
        "maintainer_reviewed_or_merged":False,
        "training_leakage_not_ruled_out":True,
        "owner_windows_machine_touched":False,
        "paid_cloud_inference_used":False,
        "result":result},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
