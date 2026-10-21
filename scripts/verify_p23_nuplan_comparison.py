"""P23: preregistered outside NuPlan occupancy-map bug; two real output formats.

The original upstream method is extracted byte-for-byte from a pinned Git blob.
No Shapely execution is claimed: isolated dictionary filtering method only.
PUBLIC gold is supplied to model; HIDDEN gold is for independent Docker review.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cognition_agent_os import local_model
from cognition_agent_os.container_lab import run_suite, cases_from_bytes
from scripts.verify_actual_local_model import MODEL, ENTRY, evaluate_one

UPSTREAM_REPOSITORY = "motional/nuplan-devkit"
UPSTREAM_COMMIT = "e9241677"
UPSTREAM_PATH = "nuplan/planning/simulation/occupancy_map/strtree_occupancy_map.py"
UPSTREAM_GIT_BLOB = "c61a13776fcb1fc55a43daa826a757eb992e4bda"
ISSUE = "https://github.com/motional/nuplan-devkit/issues/429"
MAX_SOURCE_BYTES = 18000
CLASS_NAME = "STRTreeOccupancyMap"
METHOD_NAME = "_get_other_geometries"
PREFIX = (
    "from __future__ import annotations\n"
    "GeometryMap = dict\n\n"
    "class STRTreeOccupancyMap:\n"
    "    def __init__(self, geom_map):\n"
    "        self._geom_map = geom_map\n\n"
)
ADAPTER = (
    "\n\ndef calculate(data):\n"
    "    geom_map = data['geometries']\n"
    "    query_id = data['ignore_id']\n"
    "    result = STRTreeOccupancyMap(geom_map)._get_other_geometries(query_id)\n"
    "    return {'remaining': result}\n"
)
# Control and mismatch cases are frozen BEFORE model inference.
PUBLIC = [
    {"input":{"geometries":{"car_1":10,"car_10":20,"car_2":30},
              "ignore_id":"car_10"},
     "expected":{"remaining":{"car_1":10,"car_2":30}}},
    {"input":{"geometries":{"car_1":10,"car_2":20},
              "ignore_id":"car_1"},
     "expected":{"remaining":{"car_2":20}}},
    {"input":{"geometries":{"obj":1,"object":2,"other":3},
              "ignore_id":"object"},
     "expected":{"remaining":{"obj":1,"other":3}}},
    {"input":{"geometries":{"left":1,"right":2},
              "ignore_id":"unknown"},
     "expected":{"remaining":{"left":1,"right":2}}},
]
HIDDEN = [
    {"input":{"geometries":{"a":1,"ab":2,"abc":3},
              "ignore_id":"abc"},
     "expected":{"remaining":{"a":1,"ab":2}}},
    {"input":{"geometries":{"id":9,"id2":6},
              "ignore_id":"id2"},
     "expected":{"remaining":{"id":9}}},
    {"input":{"geometries":{"alpha":1,"beta":2,"gamma":3},
              "ignore_id":"beta"},
     "expected":{"remaining":{"alpha":1,"gamma":3}}},
    {"input":{"geometries":{"cat":1,"catalog":2},
              "ignore_id":"catalog"},
     "expected":{"remaining":{"cat":1}}},
    {"input":{"geometries":{"x":1},
              "ignore_id":"x"},
     "expected":{"remaining":{}}},
    {"input":{"geometries":{"x":1,"y":2},
              "ignore_id":""},
     "expected":{"remaining":{"x":1,"y":2}}},
    {"input":{"geometries":{"测":1,"测试":2,"z":3},
              "ignore_id":"测试"},
     "expected":{"remaining":{"测":1,"z":3}}},
    {"input":{"geometries":{},
              "ignore_id":"no-id"},
     "expected":{"remaining":{}}},
]
GOAL = (
    "Fix the reported NuPlan STRTreeOccupancyMap._get_other_geometries "
    "behavior: skip exactly the entry whose geometry ID equals ignore_id. "
    "All OTHER dictionary IDs must be retained, including when an ID is a "
    "substring of ignore_id. Preserve original values, empty maps, and "
    "a query ID that is absent. Only change the original method implementation, "
    "not the surrounding isolated class setup or JSON adapter."
)

def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def source_url() -> str:
    return ("https://raw.githubusercontent.com/" + UPSTREAM_REPOSITORY + "/"
            + UPSTREAM_COMMIT + "/" + UPSTREAM_PATH)

def fetch_pinned_source() -> bytes:
    with urlopen(source_url(), timeout=25) as resp:
        content = resp.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES or git_blob_sha1(content) != UPSTREAM_GIT_BLOB:
        raise ValueError("P23 immutable upstream source not available or mismatched")
    return content

def extract_original_method(raw: bytes) -> str:
    if git_blob_sha1(raw) != UPSTREAM_GIT_BLOB:
        raise ValueError("Unpinned NuPlan source")
    text = raw.decode("utf-8")
    tree = ast.parse(text)
    classes = [c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == CLASS_NAME]
    if len(classes) != 1:
        raise ValueError("Original class missing or ambiguous")
    methods = [n for n in classes[0].body
               if isinstance(n, ast.FunctionDef) and n.name == METHOD_NAME]
    if len(methods) != 1:
        raise ValueError("Original method missing or ambiguous")
    method = methods[0]
    lines = text.splitlines(keepends=True)
    method_src = textwrap.dedent("".join(lines[method.lineno-1:method.end_lineno])).rstrip() + "\n"
    if ("not in ignore_id" not in method_src
        or len(method_src.encode()) > 3000
        or len(ast.parse(method_src).body) != 1):
        raise ValueError("Expected original method does not match")
    return textwrap.indent(method_src, "    ")

def make_case(raw: bytes, compact: bool) -> dict:
    original = PREFIX + extract_original_method(raw) + ADAPTER
    if len(original.encode()) >= 16384:
        raise ValueError("Adapted original exceeds existing file bound")
    case = {
        "name": "p23_nuplan_compact" if compact else "p23_nuplan_full",
        "source": original, "goal_statement": GOAL,
        "public": PUBLIC, "hidden": HIDDEN,
    }
    if compact:
        case["candidate_format"] = "exact_replace"
    return case

def preserves_scope(candidate: bytes, original_method: str) -> bool:
    try:
        text = candidate.decode("utf-8")
        if not text.startswith(PREFIX) or not text.endswith(ADAPTER):
            return False
        changed = text[len(PREFIX):-len(ADAPTER)]
        if changed == original_method:
            return False
        old_tree = ast.parse("class STRTreeOccupancyMap:\n" + original_method)
        new_tree = ast.parse("class STRTreeOccupancyMap:\n" + changed)
        a, b = old_tree.body[0].body, new_tree.body[0].body
        if len(a)!=1 or len(b)!=1:
            return False
        old, new = a[0], b[0]
        if not isinstance(old,ast.FunctionDef) or not isinstance(new,ast.FunctionDef):
            return False
        if old.name!=new.name or ast.dump(old.args)!=ast.dump(new.args):
            return False
        if ast.dump(old.returns)!=ast.dump(new.returns):
            return False
        return ast.dump(old)!=ast.dump(new)
    except (ValueError, SyntaxError, UnicodeError, TypeError):
        return False

def independent_scope_review(temp_root: Path, case: dict, raw: bytes, result: dict) -> dict:
    if not result["holdout_pass"]:
        return {"scope_pass":False,"reason":"NO_HELDOUT_ACCEPTANCE"}
    lab=temp_root/case["name"]/"workspace"/"repo_lab"
    if lab.is_symlink() or not lab.is_dir():
        return {"scope_pass":False,"reason":"MISSING_STAGE"}
    dirs=[p for p in lab.iterdir() if p.is_dir() and not p.is_symlink()]
    if len(dirs)!=1:
        return {"scope_pass":False,"reason":"AMBIGUOUS_STAGE"}
    file=dirs[0]/"calculator.py"
    if file.is_symlink() or not file.is_file() or (dirs[0]/"main.py").exists():
        return {"scope_pass":False,"reason":"ENTRYPOINT_CHANGED"}
    return {"scope_pass":preserves_scope(file.read_bytes(),extract_original_method(raw)),
            "reason":"ISOLATED_METHOD_SCOPE_CHECKED"}

def manifest(raw: bytes) -> str:
    contract={"upstream_blob":UPSTREAM_GIT_BLOB,
              "source":make_case(raw,False)["source"],
              "goal":GOAL,"public":PUBLIC,"hidden":HIDDEN}
    return hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()

def original_baseline(case: dict) -> dict:
    return run_suite({"main.py":ENTRY.encode(),"calculator.py":case["source"].encode()},
                     {},"main.py",cases_from_bytes(json.dumps(PUBLIC).encode()))

def main():
    baseline_only=os.getenv("P23_BASELINE_ONLY")=="1"
    if not baseline_only and (MODEL!="qwen2.5-coder:7b"
                              or os.getenv("P23_COMPARISON_OPT_IN")!="1"):
        raise RuntimeError("P23 real A/B requires explicit offline installed 7B opt-in")
    raw=fetch_pinned_source()
    baseline_case=make_case(raw,False)
    baseline=original_baseline(baseline_case)
    if baseline["passes"]!=2 or baseline["total"]!=4:
        raise RuntimeError("P23 original defect baseline does not match")
    digest=manifest(raw)
    print(json.dumps({"test":"p23_original_baseline",
                      "mode":"BASELINE_ONLY" if baseline_only else "BEFORE_LOCAL_MODEL",
                      "issue":ISSUE,"upstream_blob":UPSTREAM_GIT_BLOB,
                      "manifest":digest,"public_pass":2,"public_total":4,
                      "scope":"PINNED_ISOLATED_ORIGINAL_METHOD_NOT_FULL_NUPLAN"},
                     sort_keys=True),flush=True)
    if baseline_only:
        return
    tags=local_model._request("GET","/api/tags",None,10)
    if MODEL not in {x.get("name") for x in tags.get("models",[]) if isinstance(x,dict)}:
        raise RuntimeError("Installed model missing; no implicit install or cloud fallback")
    probe=local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":'Return JSON {"probe":true}.',"stream":False,
        "format":"json","options":{"temperature":0,"num_predict":50},
        "keep_alive":"0"},90)
    if probe.get("done") is not True or not isinstance(probe.get("response"),str):
        raise RuntimeError("Real installed 7B probe incomplete")
    with tempfile.TemporaryDirectory(prefix="cognition-p23-nuplan-") as temp:
        root=Path(temp)
        for compact in (False,True):
            case=make_case(raw,compact)
            result=evaluate_one(root,case,goal_statement=GOAL)
            scope=independent_scope_review(root,case,raw,result)
            print(json.dumps({"test":"p23_real_model_comparison",
                "format":"EXACT_REPLACE" if compact else "WHOLE_FILE",
                "issue":ISSUE,"manifest":digest,
                "real_ollama_probe":True,
                "candidate_frozen":result["candidate_frozen"],
                "public_pass":result["public_pass"],
                "heldout_pass":result["holdout_pass"],
                "scope_pass":scope["scope_pass"],
                "scope":scope,"result":result,
                "upstream_write":False,"owner_machine_touched":False,
                "external_maintainer_acceptance":False,
                "training_leakage_not_ruled_out":True,
                "no_paid_cloud_inference":True},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
