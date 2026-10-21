"""Bounded source-code repair search without running untrusted Python.

Only a single pure function of 1-3 integer/bool arguments and ONE return
expression is admissible. AST operators are evaluated manually: no exec,
eval, import, attributes, globals, calls, loops, assignments or host I/O.
Visible failures select a unique operator mutation; sealed holdout is not
read or used for selection here.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path

from .ledger import finalize_observed
from .runner import ArtifactConflict, store_once
from .source import safe_fixture

MAX_SOURCE=4096
MAX_CASES=48
MAX_CASE_FILE=16384
NAME=re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,40}\Z")
HEX=re.compile(r"[a-f0-9]{64}\Z")
COMPARE=(ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Eq,ast.NotEq)
ARITHMETIC=(ast.Add,ast.Sub,ast.Mult)


class RepairError(ValueError):pass


def validate_repair_spec(spec: dict)->dict:
    if not isinstance(spec,dict) or set(spec)!={
        "kind","source","function","visible","holdout","holdout_sha256"
    } or spec.get("kind")!="pure_code_repair":
        raise RepairError("Unsupported pure repair task")
    for k in ("source","visible","holdout"):
        name=spec[k]
        if not isinstance(name,str) or not 1<=len(name)<=120 or "/" in name or "\\" in name or ":" in name or name in (".",".."):
            raise RepairError("Input must be a flat approved local file")
    if len({spec["source"],spec["visible"],spec["holdout"]})!=3:
        raise RepairError("Evidence and code files must be distinct")
    if not isinstance(spec["function"],str) or not NAME.fullmatch(spec["function"]):
        raise RepairError("Invalid function")
    if not isinstance(spec["holdout_sha256"],str) or not HEX.fullmatch(spec["holdout_sha256"]):
        raise RepairError("A separately pinned holdout digest is mandatory")
    return spec


def parse_function(raw: bytes, name: str):
    if len(raw)>MAX_SOURCE:raise RepairError("Source too large")
    try: tree=ast.parse(raw.decode("utf-8"))
    except (SyntaxError,UnicodeError) as exc:raise RepairError("Invalid source syntax") from exc
    if len(tree.body)!=1 or type(tree.body[0]) is not ast.FunctionDef:
        raise RepairError("Only one function is accepted")
    fn=tree.body[0]
    if (fn.name!=name or fn.decorator_list or fn.returns is not None
        or fn.type_comment or fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs
        or fn.args.posonlyargs or fn.args.defaults or fn.args.kw_defaults
        or not 1<=len(fn.args.args)<=3
        or len(fn.body)!=1 or type(fn.body[0]) is not ast.Return
        or any(a.annotation is not None for a in fn.args.args)):
        raise RepairError("Only a pure single-return function is accepted")
    names=[a.arg for a in fn.args.args]
    if len(names)!=len(set(names)) or any(not NAME.fullmatch(n) for n in names):
        raise RepairError("Invalid argument declarations")
    expr=fn.body[0].value
    if type(expr) is ast.Compare:
        if len(expr.ops)!=1 or len(expr.comparators)!=1 or type(expr.ops[0]) not in COMPARE:
            raise RepairError("Compare form unsupported")
        allowed=COMPARE
        operands=[expr.left,expr.comparators[0]]
    elif type(expr) is ast.BinOp:
        if type(expr.op) not in ARITHMETIC:raise RepairError("Arithmetic form unsupported")
        allowed=ARITHMETIC
        operands=[expr.left,expr.right]
    else:
        raise RepairError("Only a single compare or arithmetic expression")
    for operand in operands:
        if type(operand) is ast.Name:
            if operand.id not in names:raise RepairError("Unknown source variable")
        elif type(operand) is ast.Constant:
            if type(operand.value) not in (int,bool) or abs(int(operand.value))>1000000:
                raise RepairError("Source constant exceeds pure numeric bound")
        else:raise RepairError("Nested operations or executable syntax rejected")
    return tree,fn,names,allowed


def visible_cases(raw: bytes, argc: int)->list[dict]:
    if len(raw)>MAX_CASE_FILE:raise RepairError("Visible cases exceed size")
    try: obj=json.loads(raw)
    except (UnicodeError,ValueError) as exc:raise RepairError("Invalid case JSON") from exc
    if not isinstance(obj,list) or not 2<=len(obj)<=MAX_CASES:
        raise RepairError("Insufficient or excessive cases")
    seen={}
    for case in obj:
        if (not isinstance(case,dict) or set(case)!={"args","expected"}
            or not isinstance(case["args"],list) or len(case["args"])!=argc
            or any(type(v) not in (int,bool) or abs(int(v))>1000000 for v in case["args"])
            or type(case["expected"]) not in (int,bool)
            or abs(int(case["expected"]))>10**9):
            raise RepairError("Invalid bounded typed test case")
        args=tuple((type(v).__name__,v) for v in case["args"])
        verdict=(type(case["expected"]).__name__,case["expected"])
        if args in seen and seen[args]!=verdict:
            raise RepairError("Contradictory visible test labels")
        seen[args]=verdict
    return obj


def _evaluate(expr, names, args):
    bindings=dict(zip(names,args))
    def value(node):
        if type(node) is ast.Name:return bindings[node.id]
        if type(node) is ast.Constant:return node.value
        raise RepairError("Unexpected expression argument")
    if type(expr) is ast.Compare:
        a,b=value(expr.left),value(expr.comparators[0])
        op=type(expr.ops[0])
        return (a<b if op is ast.Lt else a<=b if op is ast.LtE else
                a>b if op is ast.Gt else a>=b if op is ast.GtE else
                a==b if op is ast.Eq else a!=b)
    a,b=value(expr.left),value(expr.right)
    op=type(expr.op)
    result=a+b if op is ast.Add else a-b if op is ast.Sub else a*b
    if abs(result)>10**9:raise RepairError("Numeric output bound")
    return result


def _passing(tree, fn, names, cases):
    expr=fn.body[0].value
    return sum(type(actual) is type(case["expected"]) and actual==case["expected"]
               for case in cases for actual in [_evaluate(expr,names,case["args"])])


def propose_patch(spec: dict, source: bytes, visible: bytes)->dict:
    validate_repair_spec(spec)
    tree,fn,names,operators=parse_function(source,spec["function"])
    cases=visible_cases(visible,len(names))
    original_score=_passing(tree,fn,names,cases)
    evidence={"original_passes":original_score,"visible_total":len(cases),
              "hypotheses":[],"selected":None}
    if original_score==len(cases):
        evidence["reason"]="FAILURE_NOT_REPRODUCED"
        return evidence
    full=[]
    for candidate_op in operators:
        expr=fn.body[0].value
        old=type(expr.ops[0]) if type(expr) is ast.Compare else type(expr.op)
        if candidate_op is old:continue
        clone=copy.deepcopy(tree)
        changed=clone.body[0].body[0].value
        if type(changed) is ast.Compare:changed.ops=[candidate_op()]
        else:changed.op=candidate_op()
        score=_passing(clone,clone.body[0],names,cases)
        hypothesis={"mechanism":old.__name__+"->"+candidate_op.__name__,
                    "visible_passes":score,"visible_total":len(cases)}
        evidence["hypotheses"].append(hypothesis)
        if score==len(cases):
            full.append((hypothesis["mechanism"],ast.unparse(clone)+"\n"))
    if len(full)!=1:
        evidence["reason"]="NO_UNAMBIGUOUS_VISIBLE_REPAIR"
        return evidence
    mechanism,patch=full[0]
    evidence["selected"]={"mechanism":mechanism,"candidate_text":patch,
                          "candidate_sha256":hashlib.sha256(patch.encode()).hexdigest()}
    evidence["reason"]="VISIBLE_CASES_SUPPORT_ONE_OPERATOR_CHANGE"
    return evidence


def run_repair_case(db,task:dict,workspace:Path,fixtures:Path)->dict:
    tid=task["task_id"]
    try:
        spec=validate_repair_spec(json.loads(task["source_spec"]))
        original=safe_fixture(fixtures,spec["source"])
        cases=safe_fixture(fixtures,spec["visible"])
        # Independent re-reads: no holdout file read in the proposer path.
        if (original!=safe_fixture(fixtures,spec["source"])
            or cases!=safe_fixture(fixtures,spec["visible"])):
            raise RepairError("Unstable observed source")
        plan=propose_patch(spec,original,cases)
    except (RepairError,OSError,ValueError,TypeError,KeyError) as exc:
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code="REPAIR_SOURCE_UNAVAILABLE")
        return ({**observed,"diagnostic":type(exc).__name__}
                if observed["status"]=="UNKNOWN" else observed)
    if not plan["selected"]:
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code=plan["reason"])
        return ({**observed,"hypotheses":plan["hypotheses"]}
                if observed["status"]=="UNKNOWN" else observed)
    sh=hashlib.sha256(original).hexdigest()
    vh=hashlib.sha256(cases).hexdigest()
    # This is conservative *method feedback*, not leakage of withheld labels:
    # never replay the exact same previously falsified operator hypothesis
    # against identical public evidence and same independently pinned oracle.
    earlier=db.execute("""SELECT 1 FROM events
        WHERE kind='REPAIR_HOLDOUT_REJECTED'
          AND json_extract(details,'$.source_sha256')=?
          AND json_extract(details,'$.visible_sha256')=?
          AND json_extract(details,'$.holdout_sha256')=?
          AND json_extract(details,'$.mechanism')=? LIMIT 1""",
        (sh,vh,spec["holdout_sha256"],plan["selected"]["mechanism"])).fetchone()
    if earlier:
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code="IDENTICAL_REPAIR_PREVIOUSLY_REFUTED")
        return ({**observed,
                 "method_action":"DO_NOT_REPLAY_FAILED_HYPOTHESIS",
                 "external_business_outcome_verified":False}
                if observed["status"]=="UNKNOWN" else observed)
    # Outcome correction from a genuinely signed, manually imported review
    # has a different provenance from a local holdout mismatch. Both are
    # exact-scope negatives. Never turn an externally signed ACCEPT into
    # automatic authorization to apply an operator patch.
    from .signed_feedback import (
        previously_signed_rejected,HistoricalFeedbackUnverifiable)
    candidate_sha=plan["selected"]["candidate_sha256"]
    method=plan["selected"]["mechanism"]
    try:
        rejected=previously_signed_rejected(db,workspace,
                  original_sha256=sh,visible_sha256=vh,
                  holdout_sha256=spec["holdout_sha256"],
                  candidate_sha256=candidate_sha,mechanism=method)
    except (HistoricalFeedbackUnverifiable,OSError,ValueError) as exc:
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code="SIGNED_FEEDBACK_PROOF_UNVERIFIABLE")
        return ({**observed,
                 "untrusted_memory_did_not_change_method":True,
                 "diagnostic":type(exc).__name__}
                if observed["status"]=="UNKNOWN" else observed)
    if rejected:
        observed=finalize_observed(db,task,"UNKNOWN",
                                   error_code="SIGNED_REVIEW_PREVIOUSLY_REJECTED")
        return ({**observed,
                 "method_action":"REJECT_EXACT_CRYPTOGRAPHICALLY_VERIFIED_PATCH",
                 "production_write_authorized":False}
                if observed["status"]=="UNKNOWN" else observed)
    artifact={"task_id":tid,"goal_rev":task["goal_rev"],"source_spec":spec,
              "source_sha256":sh,"visible_sha256":vh,
              "selected":plan["selected"],"hypotheses":plan["hypotheses"],
              "holdout_status":"SEALED_NOT_READ_BY_PROPOSER",
              "status":"PROPOSAL_NOT_APPROVED"}
    data=(json.dumps(artifact,sort_keys=True,ensure_ascii=False,indent=2)+"\n").encode()
    def write():
        if (hashlib.sha256(safe_fixture(fixtures,spec["source"])).hexdigest()!=sh or
            hashlib.sha256(safe_fixture(fixtures,spec["visible"])).hexdigest()!=vh):
            raise RepairError("Source drifted before immutable proposal commit")
        # The SQLite write lock is held by finalize(). A concurrently
        # imported signed rejection cannot race between this check and
        # the immutable proposal's file+task commit.
        try:
            rejected_under_lock=previously_signed_rejected(
                db,workspace,original_sha256=sh,visible_sha256=vh,
                holdout_sha256=spec["holdout_sha256"],
                candidate_sha256=candidate_sha,mechanism=method)
        except HistoricalFeedbackUnverifiable as exc:
            raise RepairError("External review proof became unverifiable") from exc
        if rejected_under_lock:
            raise RepairError("Signed external rejection arrived before commit")
        return store_once(workspace,tid,data)
    try:
        observed=finalize_observed(db,task,"NEEDS_REVIEW",
                                   decision="BOUNDED_CODE_PATCH_PROPOSAL",
                                   artifact_writer=write)
    except (ArtifactConflict,RepairError,OSError,ValueError):
        return finalize_observed(db,task,"UNKNOWN",
                                 error_code="REPAIR_PROPOSAL_CONFLICT")
    if observed["status"]!="NEEDS_REVIEW":return observed
    return {**observed,"mechanism":plan["selected"]["mechanism"],
            "alternatives_compared":len(plan["hypotheses"]),
            "holdout_seen_by_planner":False,"authorizes_code_application":False}
