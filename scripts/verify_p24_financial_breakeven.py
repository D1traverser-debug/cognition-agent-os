"""P24: preregistered independent finance monotonic-root repair with real original methods.

Authentic third-party upstream breakeven issue; strict pinned Git blob, original
__init__ and breakeven_analysis AST method bytes, stdlib numerical test adapter.
All candidate code executes ONLY inside existing offline Docker lab.
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"src"))

from cognition_agent_os import local_model
from cognition_agent_os.container_lab import run_suite,cases_from_bytes
from scripts.verify_actual_local_model import MODEL,ENTRY,evaluate_one

UPSTREAM_REPOSITORY="anthropics/claude-cookbooks"
UPSTREAM_COMMIT="a162e0184e71b60290808a43961a6cbc8060123c"
UPSTREAM_PATH="skills/custom_skills/creating-financial-models/sensitivity_analysis.py"
UPSTREAM_GIT_BLOB="9674aad2e435917e60969d5b6daa816ccf7dc5b3"
ISSUE="https://github.com/anthropics/claude-cookbooks/issues/931"
CLASS_NAME="SensitivityAnalyzer"
METHODS=("__init__","breakeven_analysis")
MAX_UPSTREAM_BYTES=16000
PREFIX=(
    "from __future__ import annotations\n"
    "from typing import Any\n"
    "from collections.abc import Callable\n\n"
    "class SensitivityAnalyzer:\n"
)
ADAPTER=(
    "\n\n"
    "def calculate(data):\n"
    "    import math\n"
    "    class Model:\n"
    "        x = 0.0\n"
    "    model = Model()\n"
    "    obj = SensitivityAnalyzer(model)\n"
    "    def setter(value):\n"
    "        model.x = value\n"
    "    form = data['form']\n"
    "    offset = float(data['offset'])\n"
    "    scale = float(data['scale'])\n"
    "    def formula(x):\n"
    "        if form == 'linear':\n"
    "            return offset + scale * x\n"
    "        if form == 'quadratic':\n"
    "            return offset + scale * x * x\n"
    "        raise ValueError('Unknown frozen test form')\n"
    "    goal = float(data['target'])\n"
    "    low = float(data['low'])\n"
    "    high = float(data['high'])\n"
    "    tol = float(data.get('tolerance',0.01))\n"
    "    try:\n"
    "        point = obj.breakeven_analysis(\n"
    "            variable_name='x',variable_update=setter,\n"
    "            output_func=lambda: formula(model.x),\n"
    "            target_value=goal,min_search=low,max_search=high,\n"
    "            tolerance=tol)\n"
    "        point = float(point)\n"
    "    except ValueError:\n"
    "        return {'error':'ValueError'}\n"
    "    threshold = max(0.15,abs(scale)*tol*max(1.0,abs(low),abs(high)))\n"
    "    return {'target_met': bool(math.isfinite(point) and\n"
    "                    abs(formula(point)-goal) <= threshold),\n"
    "            'inside_bounds': bool(math.isfinite(point) and\n"
    "                    low-1e-10 <= point <= high+1e-10)}\n"
)
def row(form,offset,scale,target,low,high,tolerance=0.01):
    return {"input":{"form":form,"offset":offset,"scale":scale,
                     "target":target,"low":low,"high":high,
                     "tolerance":tolerance},
            "expected":{"target_met":True,"inside_bounds":True}}
# Public: 2 descending failures, 2 ascending controls.
PUBLIC=[
    row("linear",100,-10,40,0,10),           # reporter's exact failure
    row("linear",-20,10,40,0,10),           # reporter's increasing control
    row("quadratic",100,-1,36,0,10),        # descending nonlinear
    row("quadratic",0,1,36,0,10),           # ascending nonlinear
]
# Separate independently-authored tests: sign/range direction, negative domain,
# nonlinear polarity, boundaries and distinct numeric coefficients. None is a
# model-generated patch or original-source mutation.
HIDDEN=[
    row("linear",100,-7,58,0,12),
    row("linear",-10,4,18,-5,10),
    row("quadratic",121,-1,72,0,12),
    row("quadratic",0,2,50,0,8),
    row("quadratic",0,1,49,-10,0),
    row("quadratic",100,-1,51,-10,0),
    row("linear",100,-10,100,0,10),
    row("linear",0,4,40,0,10),
    row("linear",0,-3,18,-10,-2),
    row("quadratic",100,0.5,112.5,0,10),
    row("linear",10,0.4,11.6,-10,10),
    row("quadratic",500,-2,450,0,10),
]
GOAL=(
    "Repair the real reported financial breakeven solver bug: given a "
    "continuous monotonic model output and an interval which brackets the "
    "target, find a bounded x for which the model output approaches the "
    "target under the supplied tolerance. This MUST work for both "
    "increasing and decreasing trends, including nonlinear monotonic "
    "functions and targets at the interval endpoints. Preserve the "
    "original class constructor and breakeven method signature; edit "
    "only the breakeven method body, not the frozen JSON adapter."
)

def git_blob_sha1(content: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()

def source_url() -> str:
    return ("https://raw.githubusercontent.com/"+UPSTREAM_REPOSITORY+"/"
            +UPSTREAM_COMMIT+"/"+UPSTREAM_PATH)

def fetch_pinned_source() -> bytes:
    with urlopen(source_url(),timeout=30) as response:
        raw=response.read(MAX_UPSTREAM_BYTES+1)
    if len(raw)>MAX_UPSTREAM_BYTES or git_blob_sha1(raw)!=UPSTREAM_GIT_BLOB:
        raise ValueError("Pinned original financial source unavailable/mismatched")
    return raw

def extract_unmodified_methods(raw:bytes)->str:
    if git_blob_sha1(raw)!=UPSTREAM_GIT_BLOB:
        raise ValueError("Original source Git blob mismatch")
    source=raw.decode("utf-8")
    tree=ast.parse(source)
    klass=[c for c in tree.body if isinstance(c,ast.ClassDef) and c.name==CLASS_NAME]
    if len(klass)!=1:
        raise ValueError("Missing original SensitivityAnalyzer")
    lines=source.splitlines(keepends=True)
    parts=[]
    for method_name in METHODS:
        found=[n for n in klass[0].body
               if isinstance(n,ast.FunctionDef) and n.name==method_name]
        if len(found)!=1:
            raise ValueError("Missing/ambiguous original financial method")
        node=found[0]
        fragment=textwrap.dedent("".join(lines[node.lineno-1:node.end_lineno])).rstrip()+"\n"
        if not isinstance(ast.parse(fragment).body[0],ast.FunctionDef):
            raise ValueError("Malformed original method")
        parts.append(textwrap.indent(fragment,"    "))
    fragment="\n".join(parts)
    if "elif output < target_value" not in fragment:
        raise ValueError("Reported directional search defect missing")
    return fragment

def make_case(raw:bytes)->dict:
    source=PREFIX+extract_unmodified_methods(raw)+ADAPTER
    if len(source.encode())>16384:
        raise ValueError("Original method adapter exceeds existing bound")
    return {
        "name":"p24_finance_bracketed_monotonic",
        "source":source,
        "goal_statement":GOAL,
        "candidate_format":"exact_replace",
        "public":PUBLIC,
        "hidden":HIDDEN,
    }

def manifest(raw:bytes)->str:
    case=make_case(raw)
    data={"upstream_blob":UPSTREAM_GIT_BLOB,"source":case["source"],
          "goal":GOAL,"public":PUBLIC,"hidden":HIDDEN}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

def preserves_scope(candidate:bytes,original:bytes)->bool:
    try:
        raw=candidate.decode("utf-8")
        baseline=make_case(original)["source"]
        if not raw.startswith(PREFIX) or not raw.endswith(ADAPTER):
            return False
        old=ast.parse(baseline)
        new=ast.parse(raw)
        if len(old.body)!=len(new.body):
            return False
        for left,right in zip(old.body,new.body):
            if not isinstance(left,ast.ClassDef):
                if ast.dump(left)!=ast.dump(right):
                    return False
        a=[c for c in old.body if isinstance(c,ast.ClassDef)]
        b=[c for c in new.body if isinstance(c,ast.ClassDef)]
        if len(a)!=1 or len(b)!=1 or a[0].name!=b[0].name:
            return False
        if len(a[0].body)!=2 or len(b[0].body)!=2:
            return False
        original_init,old_fn=a[0].body
        revised_init,new_fn=b[0].body
        if ast.dump(original_init)!=ast.dump(revised_init):
            return False
        if (not isinstance(old_fn,ast.FunctionDef)
            or not isinstance(new_fn,ast.FunctionDef)
            or old_fn.name!=new_fn.name
            or ast.dump(old_fn.args)!=ast.dump(new_fn.args)
            or (ast.dump(old_fn.returns) if old_fn.returns else None)
                != (ast.dump(new_fn.returns) if new_fn.returns else None)
            or [ast.dump(d) for d in old_fn.decorator_list]
                != [ast.dump(d) for d in new_fn.decorator_list]):
            return False
        return ast.dump(old_fn)!=ast.dump(new_fn)
    except (SyntaxError,ValueError,UnicodeError,TypeError):
        return False

def original_baseline(case:dict)->dict:
    source={"main.py":ENTRY.encode("utf-8"),
            "calculator.py":case["source"].encode("utf-8")}
    return run_suite(source,{},"main.py",
                     cases_from_bytes(json.dumps(PUBLIC).encode()))

def independent_scope_review(workspace:Path,case:dict,raw:bytes,result:dict)->dict:
    if not result["holdout_pass"]:
        return {"scope_pass":False,"reason":"NO_HELDOUT_ACCEPTANCE"}
    lab=workspace/case["name"]/"workspace"/"repo_lab"
    if lab.is_symlink() or not lab.is_dir():
        return {"scope_pass":False,"reason":"STAGE_NOT_FOUND"}
    dirs=[p for p in lab.iterdir() if p.is_dir() and not p.is_symlink()]
    if len(dirs)!=1:
        return {"scope_pass":False,"reason":"AMBIGUOUS_STAGE"}
    changed=dirs[0]/"calculator.py"
    if changed.is_symlink() or not changed.is_file() or (dirs[0]/"main.py").exists():
        return {"scope_pass":False,"reason":"ENTRYPOINT_CHANGED"}
    return {"scope_pass":preserves_scope(changed.read_bytes(),raw),
            "reason":"FINANCIAL_METHOD_SCOPE_INDEPENDENT"}

def main():
    baseline_only=os.environ.get("P24_BASELINE_ONLY")=="1"
    if not baseline_only and (MODEL!="qwen2.5-coder:7b"
                              or os.environ.get("P24_ISSUE_OPT_IN")!="1"):
        raise RuntimeError("P24 genuine 7B requires explicit disposable CI opt-in")
    raw=fetch_pinned_source()
    case=make_case(raw)
    baseline=original_baseline(case)
    if baseline["passes"]!=2 or baseline["total"]!=4:
        raise RuntimeError("P24 original source defect baseline did not reproduce 2/4")
    digest=manifest(raw)
    print(json.dumps({"test":"p24_original_financial_baseline",
        "source_blob":UPSTREAM_GIT_BLOB,"manifest":digest,
        "public_pass":2,"public_total":4,
        "mode":"BASELINE_ONLY" if baseline_only else "BEFORE_REAL_MODEL",
        "scope":"REAL_TWO_METHODS_EXTRACTED_NOT_FULL_NUMPY_PANDAS_PACKAGE",
        "issue":ISSUE},sort_keys=True),flush=True)
    if baseline_only:
        return
    tags=local_model._request("GET","/api/tags",None,10)
    if MODEL not in {v.get("name") for v in tags.get("models",[]) if isinstance(v,dict)}:
        raise RuntimeError("Actual installed local model required")
    probe=local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":'Reply with JSON {"probe":true}.',
        "stream":False,"format":"json",
        "options":{"temperature":0,"num_predict":50},
        "keep_alive":"0"},90)
    if probe.get("done") is not True or not isinstance(probe.get("response"),str):
        raise RuntimeError("No genuine 7B generation probe")
    with tempfile.TemporaryDirectory(prefix="cognition-p24-finance-") as tmp:
        root=Path(tmp)
        result=evaluate_one(root,case,goal_statement=GOAL)
        scope=independent_scope_review(root,case,raw,result)
        print(json.dumps({"test":"p24_real_financial_7b_result",
            "issue":ISSUE,"source_blob":UPSTREAM_GIT_BLOB,
            "manifest":digest,"model":MODEL,"real_7b_probe":True,
            "candidate_frozen":result["candidate_frozen"],
            "public_pass":result["public_pass"],
            "heldout_pass":result["holdout_pass"],
            "scope_pass":scope["scope_pass"],"scope_review":scope,
            "outcome":result,
            "upstream_write":False,"owner_machine_touched":False,
            "maintainer_approved":False,"training_contamination_not_ruled_out":True,
            "no_paid_cloud_inference":True},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
