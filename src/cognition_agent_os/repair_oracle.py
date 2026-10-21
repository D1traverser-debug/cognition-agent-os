"""Independent execution oracle and holdout-gated isolated code repair.

Oracle never calls the patch search/scoring function. Both original and
candidate are strictly AST-whitelisted; pure expressions are interpreted
through operator functions, not Python exec/eval or a shell. Reviewer-pinned
holdout bytes are consumed only after the candidate has been frozen.
"""
from __future__ import annotations

import ast
import hashlib
import json
import operator
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from .source import safe_fixture
from .repair_search import parse_function, validate_repair_spec, visible_cases, RepairError
from .ledger import connect,event

CHECKS={
    ast.Lt:operator.lt,ast.LtE:operator.le,
    ast.Gt:operator.gt,ast.GtE:operator.ge,
    ast.Eq:operator.eq,ast.NotEq:operator.ne,
    ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul
}
ID=re.compile(r"[0-9a-f]{32}\Z")


def _execute_independent(fn, names, args):
    expression=fn.body[0].value
    env=dict(zip(names,args))
    def operand(arg):
        if type(arg) is ast.Name:return env[arg.id]
        if type(arg) is ast.Constant:return arg.value
        raise RepairError("Independent oracle rejected nested code")
    if type(expression) is ast.Compare:
        left,right=expression.left,expression.comparators[0]
        operation=type(expression.ops[0])
    elif type(expression) is ast.BinOp:
        left,right=expression.left,expression.right
        operation=type(expression.op)
    else:raise RepairError("Oracle rejected unsupported expression")
    if operation not in CHECKS:raise RepairError("Oracle rejected dangerous operation")
    result=CHECKS[operation](operand(left),operand(right))
    if type(result) is int and abs(result)>10**9:
        raise RepairError("Oracle detected arithmetic overflow")
    return result


def _passes(fn,names,cases):
    return sum(type(value) is type(case["expected"]) and value==case["expected"]
               for case in cases
               for value in [_execute_independent(fn,names,case["args"])])


def _operator_change(before,after):
    expr_a=before.body[0].value
    expr_b=after.body[0].value
    if type(expr_a) is not type(expr_b):return False
    old=type(expr_a.ops[0]) if type(expr_a) is ast.Compare else type(expr_a.op)
    new=type(expr_b.ops[0]) if type(expr_b) is ast.Compare else type(expr_b.op)
    if old is new:return False
    # Independent syntax preservation check. Only the comparison/arithmetic
    # operator may change, never the argument list, constants or names.
    import copy
    clone=copy.deepcopy(before)
    original_expr=clone.body[0].value
    if type(original_expr) is ast.Compare:original_expr.ops=[new()]
    else:original_expr.op=new()
    return ast.dump(clone,include_attributes=False)==ast.dump(
        after,include_attributes=False)


def audit_patch(db_path: Path, workspace: Path, fixtures: Path, task_id: str,
                *, reveal_holdout: bool=False, require_staged: bool=False)->dict:
    fail={"task_id":task_id,"status":"UNVERIFIABLE",
          "independent_business_validation":False,
          "authorizes_source_mutation":False}
    if not isinstance(task_id,str) or not ID.fullmatch(task_id):
        return {**fail,"reason":"INVALID_TASK_ID"}
    if (not db_path.is_file() or db_path.is_symlink() or workspace.is_symlink()):
        return {**fail,"reason":"UNSAFE_LEDGER_OR_WORKSPACE"}
    try:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True)) as db:
            db.row_factory=sqlite3.Row
            task=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if not task or task["state"] not in ("NEEDS_REVIEW","REPAIR_LAB_VERIFIED"):
                return {**fail,"reason":"TASK_NOT_REVIEWABLE"}
            spec=validate_repair_spec(json.loads(task["source_spec"]))
            if not (workspace/"artifacts").is_dir() or (workspace/"artifacts").is_symlink():
                return {**fail,"reason":"ARTIFACT_ROOT_UNSAFE"}
            path=workspace/"artifacts"/(task_id+".json")
            if path.is_symlink() or not path.is_file() or path.stat().st_size>32000:
                return {**fail,"reason":"ARTIFACT_NOT_AVAILABLE"}
            artifact_raw=path.read_bytes()
            if hashlib.sha256(artifact_raw).hexdigest()!=task["artifact_hash"]:
                return {**fail,"reason":"ARTIFACT_HASH_MISMATCH"}
            doc=json.loads(artifact_raw)
            if (doc["task_id"]!=task_id or doc["goal_rev"]!=task["goal_rev"]
                or doc["source_spec"]!=spec or doc["status"]!="PROPOSAL_NOT_APPROVED"
                or doc["holdout_status"]!="SEALED_NOT_READ_BY_PROPOSER"):
                return {**fail,"reason":"ARTIFACT_IDENTITY_MISMATCH"}
            original=safe_fixture(fixtures,spec["source"])
            visible=safe_fixture(fixtures,spec["visible"])
            if (hashlib.sha256(original).hexdigest()!=doc["source_sha256"] or
                hashlib.sha256(visible).hexdigest()!=doc["visible_sha256"]):
                return {**fail,"reason":"SOURCE_OR_VISIBLE_CASES_DRIFTED"}
            candidate=doc["selected"]["candidate_text"]
            if (not isinstance(candidate,str) or
                hashlib.sha256(candidate.encode()).hexdigest()!=doc["selected"]["candidate_sha256"]
                or len(candidate.encode())>4096):
                return {**fail,"reason":"CANDIDATE_HASH_OR_SIZE"}
            _,base,names,_=parse_function(original,spec["function"])
            _,patched,names_patch,_=parse_function(candidate.encode(),spec["function"])
            if names!=names_patch or not _operator_change(base,patched):
                return {**fail,"reason":"NON_MINIMAL_SOURCE_PATCH"}
            visible_checks=visible_cases(visible,len(names))
            if (_passes(base,names,visible_checks)==len(visible_checks) or
                _passes(patched,names,visible_checks)!=len(visible_checks)):
                return {**fail,"reason":"VISIBLE_REPRODUCTION_FAILED"}
            if not reveal_holdout and not require_staged:
                return {**fail,"status":"VISIBLE_PATCH_MECHANICALLY_VALID",
                        "candidate_sha256":doc["selected"]["candidate_sha256"],
                        "holdout_evaluated":False}
            hidden=safe_fixture(fixtures,spec["holdout"])
            if hashlib.sha256(hidden).hexdigest()!=spec["holdout_sha256"]:
                return {**fail,"reason":"HOLDOUT_PIN_MISMATCH"}
            hidden_checks=visible_cases(hidden,len(names))
            passing=_passes(patched,names,hidden_checks)
            if passing!=len(hidden_checks):
                return {**fail,"status":"HOLDOUT_REFUTED",
                        "holdout_passes":passing,"holdout_total":len(hidden_checks),
                        "candidate_sha256":doc["selected"]["candidate_sha256"]}
            if require_staged:
                stage_root=workspace/"repair_lab"
                staged=stage_root/(task_id+".py")
                if stage_root.is_symlink() or staged.is_symlink() or not staged.is_file():
                    return {**fail,"reason":"STAGED_PATCH_MISSING"}
                if staged.read_bytes()!=candidate.encode():
                    return {**fail,"reason":"STAGED_PATCH_DIFFERS"}
                rows=db.execute("""SELECT details FROM events WHERE task_id=?
                             AND kind='REPAIR_HOLDOUT_ACCEPTED'""",(task_id,)).fetchall()
                if len(rows)!=1:return {**fail,"reason":"ACCEPTANCE_RECEIPT_MISSING"}
                receipt=json.loads(rows[0]["details"])
                if (receipt.get("candidate_sha256")!=doc["selected"]["candidate_sha256"]
                    or receipt.get("holdout_sha256")!=spec["holdout_sha256"]
                    or receipt.get("scope")!="isolated_repair_lab_only"):
                    return {**fail,"reason":"ACCEPTANCE_RECEIPT_MISMATCH"}
            return {**fail,"status":"HOLDOUT_ACCEPTED",
                    "holdout_passes":passing,"holdout_total":len(hidden_checks),
                    "candidate_sha256":doc["selected"]["candidate_sha256"],
                    "staged_readback":require_staged}
    except (OSError,ValueError,TypeError,KeyError,RepairError,sqlite3.Error):
        return {**fail,"reason":"INDEPENDENT_EVIDENCE_UNAVAILABLE"}


def _stage_patch(workspace: Path,task_id: str,content: bytes)->str:
    if not workspace.is_dir() or workspace.is_symlink():raise OSError("Unsafe workspace")
    folder=workspace/"repair_lab"
    if folder.is_symlink():raise OSError("Unsafe staging directory")
    folder.mkdir(exist_ok=True)
    dest=folder/(task_id+".py")
    try:
        fd=os.open(str(dest),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        if dest.is_symlink() or not dest.is_file() or dest.read_bytes()!=content:
            raise OSError("Existing repair candidate differs: refuse overwrite")
    else:
        with os.fdopen(fd,"wb") as out:
            out.write(content);out.flush();os.fsync(out.fileno())
    if dest.read_bytes()!=content:raise OSError("Independent stage readback mismatch")
    return hashlib.sha256(content).hexdigest()


def review_patch(db_path: Path,workspace: Path,fixtures: Path,task_id:str,
                 *,fault_after_effect:bool=False)->dict:
    # A preliminary check minimizes transactions; every decision is rechecked
    # under the single SQLite write lock before an effect or state change.
    from .conformance import (
        capability_disabled,effect_preflight,REPAIR_LAB_CAPABILITY)
    if capability_disabled(db_path) or capability_disabled(db_path,REPAIR_LAB_CAPABILITY):
        return {"task_id":task_id,"status":"CAPABILITY_DISABLED"}
    first=audit_patch(db_path,workspace,fixtures,task_id,reveal_holdout=False)
    if first["status"]!="VISIBLE_PATCH_MECHANICALLY_VALID":
        return {"task_id":task_id,"status":"NOT_ADMITTED",
                "reason":first.get("reason",first["status"])}
    preflight=effect_preflight(db_path,workspace,fixtures)
    if not preflight["admitted"]:
        return {"task_id":task_id,"status":"PREFLIGHT_BLOCKED",
                "reason":preflight["reason"]}
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        circuit=db.execute("""SELECT 1 FROM conformance_capability_guard
              WHERE disabled=1 AND kind IN (?,?) LIMIT 1""",
              ("goal_sandbox_stage",REPAIR_LAB_CAPABILITY)).fetchone()
        if circuit:
            db.commit()
            return {"task_id":task_id,"status":"CAPABILITY_DISABLED"}
        if not row or row["state"]!="NEEDS_REVIEW":
            db.commit()
            return {"task_id":task_id,"status":"NOT_PENDING_REVIEW"}
        if (not authority or not authority["write_allowed"] or
            authority["grant_rev"]!=row["grant_rev"] or
            authority["goal_rev"]!=row["goal_rev"]):
            db.commit()
            return {"task_id":task_id,"status":"AUTHORITY_BLOCKED"}
        decision=audit_patch(db_path,workspace,fixtures,task_id,reveal_holdout=True)
        if decision["status"]=="HOLDOUT_REFUTED":
            frozen=json.loads((workspace/"artifacts"/(task_id+".json")).read_bytes())
            frozen_spec=json.loads(row["source_spec"])
            db.execute("""UPDATE tasks SET state='UNKNOWN',error_code='REPAIR_HOLDOUT_REFUTED',
                lease_until=NULL,claim_token=NULL,state_version=state_version+1 WHERE task_id=?""",
                (task_id,))
            event(db,task_id,"REPAIR_HOLDOUT_REJECTED",{
                "candidate_sha256":decision["candidate_sha256"],
                "source_sha256":frozen["source_sha256"],
                "visible_sha256":frozen["visible_sha256"],
                "holdout_sha256":frozen_spec["holdout_sha256"],
                "mechanism":frozen["selected"]["mechanism"],
                "visible_only_selection":"REJECTED_BY_INDEPENDENT_HOLDOUT",
                "holdout_passes":decision["holdout_passes"],
                "holdout_total":decision["holdout_total"],
                "method_action":"DO_NOT_PROMOTE_OPERATOR_REWRITE"})
            db.commit()
            return {"task_id":task_id,"status":"HOLDOUT_REFUTED",
                    "authorizes_source_mutation":False}
        if decision["status"]!="HOLDOUT_ACCEPTED":
            attempts=db.execute("""SELECT COUNT(*) FROM events
              WHERE task_id=? AND kind='REPAIR_HOLDOUT_UNAVAILABLE'""",
              (task_id,)).fetchone()[0]+1
            event(db,task_id,"REPAIR_HOLDOUT_UNAVAILABLE",{
                "attempt":attempts,"reason":decision.get("reason"),
                "outcome":"INSUFFICIENT_EVIDENCE_NOT_ACCEPTED"})
            if attempts>=3:
                db.execute("""UPDATE tasks SET state='UNKNOWN',
                    error_code='REPAIR_HOLDOUT_UNAVAILABLE_EXHAUSTED',
                    state_version=state_version+1 WHERE task_id=?""",(task_id,))
            else:
                db.execute("UPDATE tasks SET due_at=due_at+900 WHERE task_id=?",
                           (task_id,))
            db.commit()
            return {"task_id":task_id,
                    "status":"HOLDOUT_RETRY_EXHAUSTED" if attempts>=3 else "HOLDOUT_UNVERIFIABLE",
                    "attempts":attempts,"reason":decision.get("reason")}
        artifact=json.loads((workspace/"artifacts"/(task_id+".json")).read_bytes())
        try:
            patch_sha=_stage_patch(workspace,task_id,
                                   artifact["selected"]["candidate_text"].encode())
        except (OSError,ValueError):
            db.commit()
            return {"task_id":task_id,"status":"LAB_EFFECT_UNKNOWN"}
        if fault_after_effect:
            os._exit(82)
        # The approval was obtained *before* writing the lab file. Fixture
        # bytes, hidden cases, or an artifact can change concurrently even
        # while SQLite serializes task claims. Re-evaluate the entire source
        # and held-out contract AFTER the effect; don't turn a stale approval
        # into a durable trusted receipt.
        post=audit_patch(db_path,workspace,fixtures,task_id,reveal_holdout=True)
        staged_file=workspace/"repair_lab"/(task_id+".py")
        try:
            staged_consistent=(not staged_file.is_symlink() and
                               staged_file.is_file() and
                               staged_file.stat().st_size<=4096 and
                               hashlib.sha256(staged_file.read_bytes()).hexdigest()==patch_sha)
        except OSError:
            staged_consistent=False
        if (post["status"]!="HOLDOUT_ACCEPTED"
            or post.get("candidate_sha256")!=patch_sha
            or post.get("holdout_passes")!=decision.get("holdout_passes")
            or post.get("holdout_total")!=decision.get("holdout_total")
            or not staged_consistent):
            db.execute("""UPDATE tasks SET state='UNKNOWN',
                error_code='REPAIR_POST_EFFECT_EVIDENCE_CHANGED',
                lease_until=NULL,claim_token=NULL,
                state_version=state_version+1 WHERE task_id=?""",(task_id,))
            event(db,task_id,"REPAIR_POST_EFFECT_REJECTED",{
                "status_after_write":post["status"],
                "reason":post.get("reason"),
                "candidate_sha256_before":decision.get("candidate_sha256"),
                "candidate_sha256_after":post.get("candidate_sha256"),
                "staged_bytes_consistent":staged_consistent,
                "orphaned_lab_file_unapproved":True,
                "external_outcome_verified":False})
            db.commit()
            return {"task_id":task_id,"status":"POST_EFFECT_REJECTED",
                    "reason":"REPAIR_POST_EFFECT_EVIDENCE_CHANGED",
                    "authorizes_source_mutation":False}
        db.execute("""UPDATE tasks SET state='REPAIR_LAB_VERIFIED',
            decision='ISOLATED_OPERATOR_PATCH_HOLDOUT_PASS',
            lease_until=NULL,claim_token=NULL,error_code=NULL,
            state_version=state_version+1 WHERE task_id=?""",(task_id,))
        event(db,task_id,"REPAIR_HOLDOUT_ACCEPTED",{
            "candidate_sha256":patch_sha,
            "holdout_sha256":json.loads(row["source_spec"])["holdout_sha256"],
            "scope":"isolated_repair_lab_only",
            "business_goal_verified":False})
        db.commit()
        return {"task_id":task_id,"status":"REPAIR_LAB_VERIFIED",
                "holdout_passes":decision["holdout_passes"],
                "holdout_total":decision["holdout_total"],
                "source_unchanged":True,"authorizes_source_mutation":False}
    except BaseException:
        db.rollback();raise
    finally:db.close()


def review_due_repairs(db_path: Path,workspace: Path,fixtures: Path,
                       *,limit:int=4)->list[dict]:
    if not 1<=limit<=8:raise ValueError("Invalid repair review budget")
    db=connect(db_path)
    try:
        rows=db.execute("""SELECT task_id,CASE WHEN json_valid(source_spec)
              THEN json_extract(source_spec,'$.kind') ELSE NULL END FROM tasks
              WHERE state='NEEDS_REVIEW' AND due_at<=?
                AND CASE WHEN json_valid(source_spec)
                  THEN json_extract(source_spec,'$.kind')
                  ELSE NULL END IN ('pure_code_repair','pipeline_code_repair')
              ORDER BY due_at,created_at LIMIT ?""",
              (__import__("time").time(),limit)).fetchall()
        tasks=[(r[0],r[1]) for r in rows]
    finally:db.close()
    from .pipeline_oracle import review_pipeline
    return [(review_pipeline(db_path,workspace,fixtures,tid)
             if kind=="pipeline_code_repair"
             else review_patch(db_path,workspace,fixtures,tid))
            for tid,kind in tasks]
