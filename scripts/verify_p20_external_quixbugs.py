"""P20: pinned REAL THIRD-PARTY QuixBugs source and official test rows.

This is a PUBLIC historical software-repair benchmark, NOT an undisclosed
private benchmark or a live reported GitHub issue. All source and expected
values are authored by QuixBugs, not by our agent, and fetched by exact
historical Git commit with Git blob integrity checks. No corrected source
is fetched or provided to the local model.

Only allowed buggy program text, independent upstream specification and
two published rows per task reach the local model. The other four upstream
rows are inaccessible through proposal generation and executed exclusively
by the existing independent Docker review. Since the upstream repo is
public, the model may have memorized answers from training.
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
from scripts.verify_actual_local_model import MODEL,evaluate_one

UPSTREAM_OWNER="jkoppel"
UPSTREAM_REPOSITORY="QuixBugs"
UPSTREAM_COMMIT="4257f44b0ff1181dedaedee6a447e133219fcebf"
# These exact Git blob object IDs were independently read on the pinned
# upstream COMMIT before the FIRST P20 model result.
CASES=(
    {
        "name":"external_gcd",
        "symbol":"gcd",
        "source_path":"python_programs/gcd.py",
        "source_blob":"d0a6618748c438590f33483cde37f82b5b276295",
        "tests_path":"json_testcases/gcd.json",
        "tests_blob":"be94d203ec68e3492eb4a70d00617837f4d630c0",
        "public_rows":(0,3),
        "expected_rows":6,
        "goal_statement":(
            "Implement the greatest common divisor of two nonnegative "
            "integers a and b: return the greatest nonnegative integer "
            "that evenly divides both. This is the upstream QuixBugs "
            "documented output contract. Preserve the JSON adapter."
        ),
    },
    {
        "name":"external_max_sublist_sum",
        "symbol":"max_sublist_sum",
        "source_path":"python_programs/max_sublist_sum.py",
        "source_blob":"b2d79601d42b4f4a7b91c747f2ed184b6853f6e1",
        "tests_path":"json_testcases/max_sublist_sum.json",
        "tests_blob":"ef79f320e9594f2c141aaccf006175cdc26932fc",
        "public_rows":(0,1),
        "expected_rows":6,
        "goal_statement":(
            "Given a list of integers arr, compute the maximum sum of "
            "any contiguous subarray, allowing an empty subarray whose "
            "sum is zero. This is the upstream QuixBugs documented "
            "max-sublist-sum output contract. Preserve the JSON adapter."
        ),
    },
)


def git_blob_sha1(raw:bytes)->str:
    return hashlib.sha1(
        b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw).hexdigest()


def source_url(path:str)->str:
    if path not in {c[k] for c in CASES for k in ("source_path","tests_path")}:
        raise ValueError("Only preregistered source and test file paths allowed")
    return (f"https://raw.githubusercontent.com/{UPSTREAM_OWNER}/"
            f"{UPSTREAM_REPOSITORY}/{UPSTREAM_COMMIT}/{path}")


def fetch_pinned(path:str,blob:str)->bytes:
    if not isinstance(blob,str) or len(blob)!=40:
        raise ValueError("Invalid pinned Git object identity")
    # Only explicitly opted-in CI runner calls this. Never allow a
    # mutable branch URL, cloud LLM API or unbounded response download.
    with urlopen(source_url(path),timeout=18) as response:
        raw=response.read(25001)
    if len(raw)>25000 or git_blob_sha1(raw)!=blob:
        raise ValueError("Upstream file does not match preregistered Git blob")
    return raw


def parse_upstream_test_rows(raw:bytes,expected_rows:int)->list[tuple[list,object]]:
    # QuixBugs official files contain JSONL rows: [function_args, expected].
    # Do not fabricate gold with this Agent's own problem solutions.
    if not raw or len(raw)>16384:
        raise ValueError("External published test file size is invalid")
    lines=raw.decode("utf-8").splitlines()
    if len(lines)!=expected_rows:
        raise ValueError("External official test row count changed")
    out=[]
    for line in lines:
        row=json.loads(line)
        if (not isinstance(row,list) or len(row)!=2
            or not isinstance(row[0],list)
            or type(row[1]) not in (int,float)
            or len(json.dumps(row).encode("utf-8"))>1024):
            raise ValueError("Unsupported official test format")
        out.append((row[0],row[1]))
    return out


def make_case(meta:dict,source:bytes,test_bytes:bytes)->dict:
    if git_blob_sha1(source)!=meta["source_blob"]:
        raise ValueError("Unpinned external source")
    if git_blob_sha1(test_bytes)!=meta["tests_blob"]:
        raise ValueError("Unpinned external test cases")
    rows=parse_upstream_test_rows(test_bytes,meta["expected_rows"])
    public_rows=meta["public_rows"]
    if (len(public_rows)!=2 or len(set(public_rows))!=2
        or any(type(i)!=int or i<0 or i>=len(rows) for i in public_rows)):
        raise ValueError("Invalid preregistered external public case split")
    # Original upstream program's bytes must remain a contiguous prefix.
    # Add only a fixed JSON-data adapter into the isolated experiment file.
    original=source.decode("utf-8")
    if len(source)>12000 or "\0" in original:
        raise ValueError("Unsupported upstream Python module")
    symbol=meta["symbol"]
    if symbol not in ("gcd","max_sublist_sum"):
        raise ValueError("Unauthorized external function")
    wrapper=(
        "\n\n# Local JSON I/O adapter; not a repair, never applied upstream.\n"
        "def calculate(data):\n"
        f"    return {{'value': {symbol}(*data['args'])}}\n"
    )
    def turn(row):
        args,expected=row
        return {"input":{"args":args},"expected":{"value":expected}}
    result={"name":meta["name"],"source":original+wrapper,
            "goal_statement":meta["goal_statement"],
            "public":[turn(rows[i]) for i in public_rows],
            "hidden":[turn(rows[i]) for i in range(len(rows))
                      if i not in public_rows]}
    if len(result["source"].encode())>16384:
        raise ValueError("Upstream candidate source too large")
    return result


def main():
    # Fail before any network activity when called outside a one-time
    # opted-in real 7B job.
    if MODEL!="qwen2.5-coder:7b" or os.environ.get("P20_EXTERNAL_OPT_IN")!="1":
        raise RuntimeError("P20 requires explicit one-time local 7B opt-in")
    tags=local_model._request("GET","/api/tags",None,10)
    installed={entry.get("name") for entry in tags.get("models",[])
               if isinstance(entry,dict)}
    if MODEL not in installed:
        raise RuntimeError("Installed local 7B not found; no auto-download")
    probe=local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":'Return the JSON object {"probe":true}.',
        "stream":False,"format":"json",
        "options":{"temperature":0,"num_predict":50},
        "keep_alive":"0"},90)
    if probe.get("done") is not True or not isinstance(probe.get("response"),str):
        raise RuntimeError("Unmocked local model completion not observed")
    cases=[];provenance=[]
    for meta in CASES:
        source=fetch_pinned(meta["source_path"],meta["source_blob"])
        tests=fetch_pinned(meta["tests_path"],meta["tests_blob"])
        cases.append(make_case(meta,source,tests))
        provenance.append({
            "task":meta["name"],
            "upstream_source_blob":meta["source_blob"],
            "upstream_official_tests_blob":meta["tests_blob"],
            "public_row_indices":list(meta["public_rows"]),
            "hidden_row_count":meta["expected_rows"]-len(meta["public_rows"])})
    manifest=hashlib.sha256(json.dumps(
        cases,sort_keys=True).encode("utf-8")).hexdigest()
    print(json.dumps({"test":"p20_original_external_fixture_provenance",
        "repository":f"{UPSTREAM_OWNER}/{UPSTREAM_REPOSITORY}",
        "commit":UPSTREAM_COMMIT,"manifest_sha256":manifest,
        "sources_verified_against_upstream_git_blobs":True,
        "gold_authored_by_agent":False,"public_upstream_tests":True,
        "training_contamination_possible":True,
        "provenance":provenance},sort_keys=True),flush=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix="cognition-p20-external-") as temp:
        for case in cases:
            result=evaluate_one(Path(temp),case,
                                goal_statement=case["goal_statement"])
            results.append(result)
            print(json.dumps({"test":"p20_external_case",**result},
                             sort_keys=True),flush=True)
    print(json.dumps({
        "test":"p20_external_real_local_model",
        "cases":len(results),
        "model":MODEL,"model_unmocked":True,
        "manifest_sha256":manifest,
        "frozen_candidates":sum(int(x["candidate_frozen"]) for x in results),
        "public_pass":sum(int(x["public_pass"]) for x in results),
        "holdout_pass":sum(int(x["holdout_pass"]) for x in results),
        "sources_unchanged":all(x["source_unchanged"] for x in results),
        "original_repo_modified":False,
        "correct_reference_source_used":False,
        "official_testcases_public_on_internet":True,
        "independently_authored_upstream_expected_values":True,
        "training_memorization_not_ruled_out":True,
        "paid_model_api_used":False,
        "owner_machine_touched":False},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
