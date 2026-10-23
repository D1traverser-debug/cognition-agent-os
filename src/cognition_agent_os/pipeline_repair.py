"""P11: Cross-file, multi-stage pure-function repair search.

Given TWO independent source files and a three-input public functional
contract, synthesize a pair of coupled operator edits (or a single edit).
No Python source is executed, imported, eval()'d, or shell-run. The source
grammar is the already-enforced pure one-return AST from P10.4; outputs
are piped between two functions. No hidden holdout bytes are read here.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import itertools
import json
from pathlib import Path

from .repair_search import (
    RepairError, parse_function, visible_cases, _evaluate
)
from .runner import store_once,ArtifactConflict
from .source import safe_fixture
from .ledger import finalize_observed

OPS=(ast.Add,ast.Sub,ast.Mult,ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Eq,ast.NotEq)
SHA=lambda b:hashlib.sha256(b).hexdigest()


def validate_pipeline(spec):
    if (not isinstance(spec,dict) or set(spec)!={
        "kind","stages","visible","holdout","holdout_sha256"} or
        spec["kind"]!="pipeline_code_repair"):
        raise RepairError("Unsupported cross-file repair specification")
    stages=spec["stages"]
    if (not isinstance(stages,list) or len(stages)!=2 or
        not all(isinstance(s,dict) and set(s)=={"source","function"} for s in stages)):
        raise RepairError("Exactly two explicit function stages required")
    file_names=[s["source"] for s in stages]+[spec["visible"],spec["holdout"]]
    for name in file_names:
        if (not isinstance(name,str) or not 1<=len(name)<=100
            or not name.endswith((".py",".json"))
            or "/" in name or "\\" in name or ":" in name
            or name.startswith(".") or name in (".","..")):
            raise RepairError("Only flat explicit input filenames allowed")
    if len(set(file_names))!=4 or any(not s["source"].endswith(".py") for s in stages):
        raise RepairError("Code and evidence files must be separate")
    if not spec["visible"].endswith(".json") or not spec["holdout"].endswith(".json"):
        raise RepairError("Cases must be JSON")
    for stage in stages:
        if (not isinstance(stage["function"],str)
            or not stage["function"].isidentifier()
            or len(stage["function"])>40):
            raise RepairError("Invalid function name")
    h=spec["holdout_sha256"]
    if not isinstance(h,str) or len(h)!=64 or any(c not in "0123456789abcdef" for c in h):
        raise RepairError("Externally fixed hidden case SHA256 mandatory")
    return spec


def _pipeline_cases(raw):
    cases=visible_cases(raw,3)
    # Coupled pipeline has numeric intermediate and numeric final semantics.
    if any(any(type(v) is not int for v in c["args"])
           or type(c["expected"]) is not int for c in cases):
        raise RepairError("Pipeline contract is numeric three-argument only")
    return cases


def _operator(fn):
    expr=fn.body[0].value
    return type(expr.ops[0]) if type(expr) is ast.Compare else type(expr.op)


def _mutated(tree,operator):
    copy_tree=copy.deepcopy(tree)
    expr=copy_tree.body[0].body[0].value
    if isinstance(expr,ast.Compare):
        expr.ops=[operator()]
    else:
        expr.op=operator()
    return copy_tree


def _candidates(raw,func):
    tree,fn,names,allowed=parse_function(raw,func)
    if len(names)!=2:raise RepairError("Both stages must take exactly two args")
    return tree,names,[_mutated(tree,op) for op in allowed]


def _evaluate_pipeline(a,b,case):
    out=_evaluate(a.body[0].body[0].value,
                  [x.arg for x in a.body[0].args.args],case["args"][:2])
    if type(out) is not int:raise RepairError("Non-numeric intermediate")
    return _evaluate(b.body[0].body[0].value,
                     [x.arg for x in b.body[0].args.args],[out,case["args"][2]])


def _score(a,b,cases):
    try:
        return sum(type(actual) is int and actual==case["expected"]
                   for case in cases
                   for actual in [_evaluate_pipeline(a,b,case)])
    except (RepairError,ArithmeticError,TypeError,KeyError,OverflowError):
        return -1


def propose_pipeline(spec,source_a,source_b,visible):
    validate_pipeline(spec)
    if any(len(raw)>4096 for raw in (source_a,source_b)):
        raise RepairError("Stage source too large")
    original_a,names_a,alternatives_a=_candidates(source_a,spec["stages"][0]["function"])
    original_b,names_b,alternatives_b=_candidates(source_b,spec["stages"][1]["function"])
    cases=_pipeline_cases(visible)
    original_score=_score(original_a,original_b,cases)
    if original_score==len(cases):
        return {"status":"FAILURE_NOT_REPRODUCED","public_passes":original_score,
                "public_total":len(cases)}
    choices=[]
    trials=[]
    for a,b in itertools.product(alternatives_a,alternatives_b):
        changed=sum((_operator(original_a.body[0])!=_operator(a.body[0]),
                     _operator(original_b.body[0])!=_operator(b.body[0])))
        if changed==0:continue
        score=_score(a,b,cases)
        descriptor=[
            _operator(original_a.body[0]).__name__+"->"+_operator(a.body[0]).__name__,
            _operator(original_b.body[0]).__name__+"->"+_operator(b.body[0]).__name__
        ]
        trials.append({"changes":descriptor,"public_passes":score})
        if score==len(cases):
            texts=[ast.unparse(a)+"\n",ast.unparse(b)+"\n"]
            choices.append({"changes":descriptor,"patches":texts,
                            "sha256":[SHA(t.encode()) for t in texts]})
    if len(choices)!=1:
        return {"status":"NO_UNIQUE_CROSS_FILE_SOLUTION",
                "public_passes":original_score,"public_total":len(cases),
                "alternatives_checked":len(trials),"solutions":len(choices)}
    return {"status":"UNIQUE_VISIBLE_CANDIDATE",
            "selected":choices[0],"public_passes":original_score,
            "public_total":len(cases),"alternatives_checked":len(trials)}


def run_pipeline_case(db,task,workspace,fixtures):
    tid=task["task_id"]
    try:
        spec=validate_pipeline(json.loads(task["source_spec"]))
        src=[safe_fixture(fixtures,s["source"]) for s in spec["stages"]]
        public=safe_fixture(fixtures,spec["visible"])
        # No open/read for spec["holdout"] anywhere in this planner.
        proposal=propose_pipeline(spec,*src,public)
    except (RepairError,OSError,ValueError,KeyError,TypeError) as exc:
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code="PIPELINE_INPUT_UNSUPPORTED")
        return ({**observed,"diagnostic":type(exc).__name__}
                if observed["status"]=="UNKNOWN" else observed)
    if proposal["status"]!="UNIQUE_VISIBLE_CANDIDATE":
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code=proposal["status"])
        return ({**observed,
                 "alternatives_checked":proposal.get("alternatives_checked",0)}
                if observed["status"]=="UNKNOWN" else observed)
    hashes=[SHA(v) for v in src]
    public_hash=SHA(public)
    record={"task_id":tid,"goal_rev":task["goal_rev"],"source_spec":spec,
            "sources_sha256":hashes,"visible_sha256":public_hash,
            "selected":proposal["selected"],
            "alternatives_checked":proposal["alternatives_checked"],
            "holdout_status":"SEALED_NOT_READ_BY_PROPOSER",
            "status":"PROPOSAL_NOT_APPROVED"}
    data=(json.dumps(record,sort_keys=True,indent=2)+"\n").encode()
    def write():
        if ([SHA(safe_fixture(fixtures,s["source"])) for s in spec["stages"]]!=hashes
            or SHA(safe_fixture(fixtures,spec["visible"]))!=public_hash):
            raise RepairError("Source changed during candidate freeze")
        return store_once(workspace,tid,data)
    try:
        observed=finalize_observed(db,task,"NEEDS_REVIEW",
                                   decision="CROSS_FILE_OPERATOR_REPAIR",
                                   artifact_writer=write)
    except (ArtifactConflict,RepairError,OSError,ValueError):
        return finalize_observed(db,task,"UNKNOWN",
                                 error_code="PIPELINE_PROPOSAL_CONFLICT")
    if observed["status"]!="NEEDS_REVIEW":return observed
    return {**observed,"reason":observed.get("reason"),
            "alternatives_checked":proposal["alternatives_checked"],
            "stages":2,"holdout_seen_by_planner":False,
            "production_write_authorized":False}
