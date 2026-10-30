"""P11 independent coupled-source acceptance using operator-based AST oracle.

Does not trust proposal searcher's scoring result and never executes Python
source. It checks original/patch syntax, exactly one primitive operator
per stage, public failures and independently pinned hidden tests, then
rechecks after staging. File effects remain sandbox-only and create-once.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
from .ledger import readonly_snapshot
from .isolated_filesystem import stage_immutable
import sqlite3
import time

from .repair_search import RepairError,parse_function
from .repair_oracle import _execute_independent,_operator_change
from .pipeline_repair import validate_pipeline,_pipeline_cases
from .source import safe_fixture
from .ledger import connect,event,current_guard


def digest(v):return hashlib.sha256(v).hexdigest()


def independent_pipeline_score(functions,cases):
    f1,n1=functions[0]
    f2,n2=functions[1]
    count=0
    for row in cases:
        intermediate=_execute_independent(f1,n1,row["args"][:2])
        if type(intermediate) is not int or abs(intermediate)>10**9:
            raise RepairError("Intermediate result cannot be used")
        result=_execute_independent(f2,n2,[intermediate,row["args"][2]])
        if type(result) is int and result==row["expected"]:
            count+=1
    return count


def _audit_internal(db_path,workspace,fixtures,tid,*,hidden,staged):
    fail={"task_id":tid,"status":"UNVERIFIABLE",
          "authorizes_source_mutation":False,
          "independent_business_outcome_proven":False}
    if (not db_path.is_file() or db_path.is_symlink()
        or workspace.is_symlink() or not isinstance(tid,str)
        or len(tid)!=32 or any(x not in "0123456789abcdef" for x in tid)):
        return {**fail,"reason":"UNSAFE_AUTHORITY"}
    try:
        with readonly_snapshot(db_path) as db:
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
            if row is None or row["state"] not in ("NEEDS_REVIEW","REPAIR_LAB_VERIFIED"):
                return {**fail,"reason":"REPAIR_CLAIM_NOT_REVIEWABLE"}
            spec=validate_pipeline(json.loads(row["source_spec"]))
            artroot=workspace/"artifacts"
            if not artroot.is_dir() or artroot.is_symlink():
                return {**fail,"reason":"UNSAFE_ARTIFACT_ROOT"}
            proposal=artroot/(tid+".json")
            if not proposal.is_file() or proposal.is_symlink() or proposal.stat().st_size>32000:
                return {**fail,"reason":"PROPOSAL_MISSING"}
            raw=proposal.read_bytes()
            if digest(raw)!=row["artifact_hash"]:
                return {**fail,"reason":"PROPOSAL_HASH_CHANGED"}
            record=json.loads(raw)
            if (record["task_id"]!=tid or record["goal_rev"]!=row["goal_rev"]
                or record["source_spec"]!=spec or record["status"]!="PROPOSAL_NOT_APPROVED"
                or record["holdout_status"]!="SEALED_NOT_READ_BY_PROPOSER"):
                return {**fail,"reason":"PROPOSAL_SCOPE_CHANGED"}
            originals=[safe_fixture(fixtures,s["source"]) for s in spec["stages"]]
            visible=safe_fixture(fixtures,spec["visible"])
            if (record["sources_sha256"]!=[digest(x) for x in originals]
                or record["visible_sha256"]!=digest(visible)):
                return {**fail,"reason":"INPUT_SOURCE_CHANGED"}
            selected=record["selected"]
            patches=selected["patches"]
            hashes=selected["sha256"]
            if (not isinstance(patches,list) or len(patches)!=2
                or not isinstance(hashes,list) or len(hashes)!=2
                or any(not isinstance(t,str) or len(t.encode())>4096
                       or digest(t.encode())!=h for t,h in zip(patches,hashes))):
                return {**fail,"reason":"PROPOSED_PATCH_BYTES_INVALID"}
            actual=[]
            original=[]
            for idx,stage in enumerate(spec["stages"]):
                _,fn,names,_=parse_function(originals[idx],stage["function"])
                _,candidate,new_names,_=parse_function(
                    patches[idx].encode(),stage["function"])
                if names!=new_names or (
                    not _operator_change(fn,candidate) and
                    originals[idx].decode().strip()!=patches[idx].strip()):
                    return {**fail,"reason":"NON_MINIMAL_CROSS_FILE_EDIT"}
                actual.append((candidate,new_names))
                original.append((fn,names))
            if not any(_operator_change(old[0],new[0])
                       for old,new in zip(original,actual)):
                return {**fail,"reason":"NO_ACTUAL_PATCH"}
            cases=_pipeline_cases(visible)
            if (independent_pipeline_score(original,cases)==len(cases)
                or independent_pipeline_score(actual,cases)!=len(cases)):
                return {**fail,"reason":"VISIBLE_CONTRACT_NOT_PROVEN"}
            if not hidden:
                return {**fail,"status":"VISIBLE_PIPELINE_VERIFIED",
                        "public_total":len(cases),
                        "candidate_shas":hashes,"hidden_seen":False}
            data=safe_fixture(fixtures,spec["holdout"])
            if digest(data)!=spec["holdout_sha256"]:
                return {**fail,"reason":"HOLDOUT_PIN_MISMATCH"}
            tests=_pipeline_cases(data)
            passes=independent_pipeline_score(actual,tests)
            if passes!=len(tests):
                return {**fail,"status":"HOLDOUT_REFUTED",
                        "passes":passes,"total":len(tests)}
            if staged:
                dest=workspace/"pipeline_lab"/tid
                if not dest.is_dir() or dest.is_symlink():
                    return {**fail,"reason":"STAGED_DIRECTORY_MISSING"}
                for idx,stage in enumerate(spec["stages"]):
                    p=dest/stage["source"]
                    if p.is_symlink() or not p.is_file() or p.read_bytes()!=patches[idx].encode():
                        return {**fail,"reason":"STAGED_PATCH_MISMATCH"}
                rows=db.execute("""SELECT details FROM events WHERE task_id=?
                    AND kind='PIPELINE_HOLDOUT_ACCEPTED'""",(tid,)).fetchall()
                if len(rows)!=1:
                    return {**fail,"reason":"PIPELINE_RECEIPT_MISSING"}
                receipt=json.loads(rows[0]["details"])
                if (receipt.get("candidate_shas")!=hashes
                    or receipt.get("holdout_sha256")!=spec["holdout_sha256"]):
                    return {**fail,"reason":"PIPELINE_RECEIPT_CONFLICT"}
            return {**fail,"status":"HOLDOUT_ACCEPTED","passes":passes,
                    "total":len(tests),"candidate_shas":hashes}
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,RepairError):
        return {**fail,"reason":"INDEPENDENT_PIPELINE_EVIDENCE_UNAVAILABLE"}


def audit_pipeline(db_path,workspace,fixtures,tid,*,hidden=False,staged=False):
    return _audit_internal(db_path,workspace,fixtures,tid,hidden=hidden,staged=staged)


def _stage(workspace, tid, stage_files, patched):
    """Stage coupled candidates through one authorized local file boundary."""
    for name, data in zip(stage_files, patched):
        stage_immutable(workspace, ("pipeline_lab", tid), name, data)


def review_pipeline(db_path,workspace,fixtures,tid):
    from .conformance import (
        effect_preflight,capability_disabled,REPAIR_LAB_CAPABILITY)
    if (capability_disabled(db_path)
        or capability_disabled(db_path,REPAIR_LAB_CAPABILITY)):
        return {"task_id":tid,"status":"CAPABILITY_DISABLED"}
    before=audit_pipeline(db_path,workspace,fixtures,tid)
    if before["status"]!="VISIBLE_PIPELINE_VERIFIED":
        return {"task_id":tid,"status":"NOT_ADMITTED","reason":before.get("reason")}
    pf=effect_preflight(db_path,workspace,fixtures)
    if not pf["admitted"]:
        return {"task_id":tid,"status":"PREFLIGHT_BLOCKED"}
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
        if not row or row["state"]!="NEEDS_REVIEW":
            db.commit();return {"task_id":tid,"status":"NOT_PENDING_REVIEW"}
        allowed,reason=current_guard(db,dict(row),needs_write=True)
        if not allowed:
            db.commit();return {"task_id":tid,"status":"AUTHORITY_BLOCKED","reason":reason}
        circuit=db.execute("""SELECT 1 FROM conformance_capability_guard
           WHERE disabled=1 AND kind IN ('goal_sandbox_stage',?) LIMIT 1""",
           (REPAIR_LAB_CAPABILITY,)).fetchone()
        if circuit:
            db.commit();return {"task_id":tid,"status":"CAPABILITY_DISABLED"}
        first=audit_pipeline(db_path,workspace,fixtures,tid,hidden=True)
        if first["status"]=="HOLDOUT_REFUTED":
            db.execute("""UPDATE tasks SET state='UNKNOWN',
                error_code='PIPELINE_HOLDOUT_REFUTED',
                state_version=state_version+1 WHERE task_id=?""",(tid,))
            event(db,tid,"PIPELINE_HOLDOUT_REJECTED",{"passes":first["passes"],
                "total":first["total"],"no_source_writes":True})
            db.commit()
            return {"task_id":tid,"status":"HOLDOUT_REFUTED",
                    "production_write_authorized":False}
        if first["status"]!="HOLDOUT_ACCEPTED":
            db.commit()
            return {"task_id":tid,"status":"HOLDOUT_UNVERIFIABLE",
                    "reason":first.get("reason")}
        record=json.loads((workspace/"artifacts"/(tid+".json")).read_bytes())
        spec=json.loads(row["source_spec"])
        try:
            _stage(workspace,tid,[s["source"] for s in spec["stages"]],
                   [s.encode() for s in record["selected"]["patches"]])
        except (OSError,ValueError):
            db.commit()
            return {"task_id":tid,"status":"STAGING_UNVERIFIABLE"}
        post=audit_pipeline(db_path,workspace,fixtures,tid,hidden=True)
        if (post["status"]!="HOLDOUT_ACCEPTED" or
            post["candidate_shas"]!=first["candidate_shas"] or
            post["passes"]!=first["passes"]):
            db.execute("""UPDATE tasks SET state='UNKNOWN',
                error_code='PIPELINE_POST_EFFECT_CHANGED',
                state_version=state_version+1 WHERE task_id=?""",(tid,))
            event(db,tid,"PIPELINE_POST_EFFECT_REJECTED",{
                "reason":post.get("reason",post["status"]),
                "production_write_authorized":False})
            db.commit()
            return {"task_id":tid,"status":"POST_EFFECT_REJECTED"}
        for idx,spec_stage in enumerate(spec["stages"]):
            p=workspace/"pipeline_lab"/tid/spec_stage["source"]
            if p.is_symlink() or p.read_bytes()!=record["selected"]["patches"][idx].encode():
                db.execute("""UPDATE tasks SET state='UNKNOWN',
                   error_code='PIPELINE_STAGED_BYTES_CHANGED',
                   state_version=state_version+1 WHERE task_id=?""",(tid,))
                event(db,tid,"PIPELINE_POST_EFFECT_REJECTED",{
                    "reason":"STAGED_BYTES_CHANGED"})
                db.commit()
                return {"task_id":tid,"status":"POST_EFFECT_REJECTED"}
        db.execute("""UPDATE tasks SET state='REPAIR_LAB_VERIFIED',
                   decision='COUPLED_TWO_STAGE_HOLDOUT_PASS',
                   state_version=state_version+1,
                   error_code=NULL WHERE task_id=?""",(tid,))
        event(db,tid,"PIPELINE_HOLDOUT_ACCEPTED",{
            "candidate_shas":first["candidate_shas"],
            "holdout_sha256":spec["holdout_sha256"],
            "production_write_authorized":False})
        db.commit()
        return {"task_id":tid,"status":"REPAIR_LAB_VERIFIED",
                "stages":2,"holdout_passes":first["passes"],
                "source_files_untouched":True,
                "production_write_authorized":False}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
