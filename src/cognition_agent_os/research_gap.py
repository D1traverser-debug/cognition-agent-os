"""P34 actual task-feedback research-gap admission in existing authoritative ledger.

Does not claim to have researched or solved an unknown problem. A valid
knowledge miss is converted into ONE bounded, independent-reviewable action
containing alternatives and evidence questions. Unavailable/malformed/policy-
breaking knowledge never becomes invented guidance or an executable route.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .ledger import open_readonly_snapshot
from .ledger import create_task,current_guard,event,finalize_observed
from .source import safe_fixture,SourceUnavailable
from .runner import store_once,ArtifactConflict
from .knowledge_routing import _checked_spec,KnowledgeRoutingError

_ALLOWED_GAPS=frozenset(("NO_EXACT_GOAL_CLAIM","CONFLICTING_CLAIMS",
                         "WITHDRAWN_CLAIM","UNREGISTERED_ROUTE"))
_QUESTIONS={
    "NO_EXACT_GOAL_CLAIM":"Which authorized route fits this exact goal, and what disconfirms it?",
    "CONFLICTING_CLAIMS":"Which competing route is supported by independent source evidence?",
    "WITHDRAWN_CLAIM":"Which source replaces the withdrawn claim, if any?",
    "UNREGISTERED_ROUTE":"Is any existing authorized route justified, or is new approval needed?",
}
_TASK_ID=re.compile(r"[0-9a-f]{32}\Z")

def classify_research_gap(spec:dict,fixtures:Path)->dict|None:
    """Return a bounded falsifiable gap only from authenticated-by-hash bytes.

    Not a semantic credibility claim: sha256 pins content identity only.
    """
    options=_checked_spec(spec)
    contract=spec["knowledge"]
    try:
        raw=safe_fixture(fixtures,contract["path"])
    except (OSError,SourceUnavailable,ValueError) as exc:
        raise KnowledgeRoutingError("KNOWLEDGE_UNAVAILABLE") from exc
    if len(raw)>16384 or hashlib.sha256(raw).hexdigest()!=contract["sha256"]:
        raise KnowledgeRoutingError("KNOWLEDGE_UNAVAILABLE")
    try:doc=json.loads(raw)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE") from exc
    if (not isinstance(doc,dict)
        or set(doc)!={"schema_version","source_id","claims"}
        or doc["schema_version"]!=1
        or doc["source_id"]!=contract["source_id"]
        or not isinstance(doc["claims"],list)
        or not 1<=len(doc["claims"])<=16):
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    from .knowledge_routing import _bound_id
    claims=doc["claims"]
    for claim in claims:
        if (not isinstance(claim,dict)
            or set(claim)!={"goal_key","route","status","source_ref"}
            or not _bound_id(claim["goal_key"]) or not _bound_id(claim["route"])
            or claim["status"] not in ("active","withdrawn")
            or not isinstance(claim["source_ref"],str)
            or not 1<=len(claim["source_ref"])<=128):
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    matching=[c for c in claims if c["goal_key"]==spec["goal_key"]]
    if not matching:
        kind="NO_EXACT_GOAL_CLAIM"
    elif len(matching)>1:
        kind="CONFLICTING_CLAIMS"
    elif matching[0]["status"]=="withdrawn":
        kind="WITHDRAWN_CLAIM"
    elif matching[0]["route"] not in options:
        kind="UNREGISTERED_ROUTE"
    else:
        return None
    result={
        "goal_key":spec["goal_key"],"gap_kind":kind,
        "knowledge":dict(contract),
        "routes":{route:{"capability":plan["capability"],
                         "plan_sha256":plan["plan_sha256"]}
                  for route,plan in sorted(options.items())},
    }
    if "research_sources" in spec:
        result["research_sources"]=[dict(x) for x in spec["research_sources"]]
    return result

def _child_spec(parent_id:str,gap:dict)->dict:
    result={"kind":"research_gap","parent_id":parent_id,
            "goal_key":gap["goal_key"],"gap_kind":gap["gap_kind"],
            "knowledge":gap["knowledge"],"routes":gap["routes"]}
    if "research_sources" in gap:
        result["research_sources"]=gap["research_sources"]
    return result

def _agenda(spec:dict)->dict:
    return {"status":"RESEARCH_REQUEST_NOT_ANSWER",
            "goal_key":spec["goal_key"],"gap_kind":spec["gap_kind"],
            "knowledge_sha256":spec["knowledge"]["sha256"],
            "source_id":spec["knowledge"]["source_id"],
            "routes":spec["routes"],
            "question":_QUESTIONS[spec["gap_kind"]],
            "required_evidence":[
                "independently sourced applicability to the exact goal",
                "disconfirming case for each already authorized route",
                "source identity, freshness, and authorization recheck before action"
            ],"source_trust_proven":False,
            "business_outcome_verified":False,
            "production_effect_authorized":False}

def enqueue_research_gap(db:sqlite3.Connection,task:dict,fixtures:Path,
                         original_spec:dict,first_gap:dict)->dict:
    """One recovery task and receipt atomically from existing claim and grant."""
    tid=task["task_id"]
    db.execute("BEGIN IMMEDIATE")
    try:
        row=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
        if (not row or row["claim_token"]!=task["claim_token"]
            or row["state"]!="RUNNING"):
            db.commit();return {"task_id":tid,"status":"STALE_WORKER"}
        ok,reason=current_guard(db,task,needs_write=True)
        if not ok:
            db.execute("""UPDATE tasks SET state='BLOCKED',error_code=?,
                state_version=state_version+1,lease_until=NULL,claim_token=NULL
                WHERE task_id=?""",(reason,tid))
            event(db,tid,"RESEARCH_GAP_BLOCKED",{"reason":reason})
            db.commit()
            return {"task_id":tid,"status":"BLOCKED","reason":reason}
        try:confirmed=classify_research_gap(original_spec,fixtures)
        except KnowledgeRoutingError:
            confirmed=None
        if confirmed!=first_gap:
            # Evidence or decision was changed between observations.
            db.execute("""UPDATE tasks SET state='UNKNOWN',error_code='RESEARCH_GAP_EVIDENCE_CHANGED',
                state_version=state_version+1,lease_until=NULL,claim_token=NULL
                WHERE task_id=?""",(tid,))
            event(db,tid,"RESEARCH_GAP_REJECTED",
                  {"reason":"RESEARCH_GAP_EVIDENCE_CHANGED"})
            db.commit()
            return {"task_id":tid,"status":"UNKNOWN","reason":"RESEARCH_GAP_EVIDENCE_CHANGED"}
        child_spec=_child_spec(tid,confirmed)
        child=create_task(db,child_spec,parent=tid,commit=False)
        db.execute("""UPDATE tasks SET state='RESEARCH_NEEDED',
                   decision='GAP_REQUIRES_INDEPENDENT_STUDY',
                   error_code=NULL,state_version=state_version+1,
                   lease_until=NULL,claim_token=NULL WHERE task_id=?""",(tid,))
        event(db,tid,"KNOWLEDGE_RESEARCH_REQUESTED",{
            "child_task_id":child,"gap_kind":confirmed["gap_kind"],
            "knowledge_sha256":confirmed["knowledge"]["sha256"],
            "routes":confirmed["routes"],
            "business_outcome_verified":False})
        db.commit()
        return {"task_id":tid,"status":"RESEARCH_NEEDED",
                "research_task_id":child,"gap_kind":confirmed["gap_kind"],
                "business_outcome_verified":False}
    except BaseException:
        db.rollback();raise

def _readback(db:sqlite3.Connection,parent_id:str,child_id:str,fixtures:Path)->tuple[dict|None,str]:
    parent=db.execute("SELECT * FROM tasks WHERE task_id=?",(parent_id,)).fetchone()
    child=db.execute("SELECT * FROM tasks WHERE task_id=?",(child_id,)).fetchone()
    if not parent or not child or parent["state"]!="RESEARCH_NEEDED":
        return None,"RESEARCH_PARENT_UNAVAILABLE"
    try:
        parent_spec=json.loads(parent["source_spec"])
        child_spec=json.loads(child["source_spec"])
        if (parent_spec.get("kind")!="knowledge_intent"
            or parent_spec.get("research_on_gap") is not True
            or child_spec.get("kind")!="research_gap"
            or child["parent_task"]!=parent_id
            or child["goal_rev"]!=parent["goal_rev"]
            or child["grant_rev"]!=parent["grant_rev"]):
            return None,"RESEARCH_SPEC_MISMATCH"
        gap=classify_research_gap(parent_spec,fixtures)
        if gap is None or _child_spec(parent_id,gap)!=child_spec:
            return None,"RESEARCH_GAP_NO_LONGER_PROVEN"
        receipts=db.execute("""SELECT details FROM events WHERE task_id=?
                AND kind='KNOWLEDGE_RESEARCH_REQUESTED'""",(parent_id,)).fetchall()
        children=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                            (parent_id,)).fetchone()[0]
        if len(receipts)!=1 or children!=1:
            return None,"RESEARCH_RECEIPT_MISMATCH"
        receipt=json.loads(receipts[0][0])
        if receipt!={"child_task_id":child_id,
            "gap_kind":gap["gap_kind"],
            "knowledge_sha256":gap["knowledge"]["sha256"],
            "routes":gap["routes"],
            "business_outcome_verified":False}:
            return None,"RESEARCH_RECEIPT_MISMATCH"
        return child_spec,"MECHANICALLY_VALID"
    except (KnowledgeRoutingError,KeyError,ValueError,TypeError,OSError):
        return None,"RESEARCH_SOURCE_UNAVAILABLE"

def run_research_gap(db:sqlite3.Connection,task:dict,workspace:Path,fixtures:Path)->dict:
    tid=task["task_id"]
    parent_id=task["parent_task"]
    if not isinstance(parent_id,str) or not _TASK_ID.fullmatch(parent_id):
        return finalize_observed(db,task,"UNKNOWN",error_code="RESEARCH_PARENT_UNAVAILABLE")
    spec,reason=_readback(db,parent_id,tid,fixtures)
    if reason!="MECHANICALLY_VALID":
        return finalize_observed(db,task,"UNKNOWN",error_code=reason)
    payload=(json.dumps(_agenda(spec),sort_keys=True,indent=2,ensure_ascii=False)+"\n").encode()
    def writer():
        current,reason=_readback(db,parent_id,tid,fixtures)
        if reason!="MECHANICALLY_VALID" or current!=spec:
            raise KnowledgeRoutingError("RESEARCH_SOURCE_UNAVAILABLE")
        effect=store_once(workspace,tid,payload)
        # Filesystem cannot share SQLite lock: never accept receipt if
        # source has changed while writing an immutable local agenda.
        current,reason=_readback(db,parent_id,tid,fixtures)
        if reason!="MECHANICALLY_VALID" or current!=spec:
            raise KnowledgeRoutingError("RESEARCH_SOURCE_UNAVAILABLE")
        # Same authoritative transaction: agenda and explicitly consented
        # bounded read-only evidence review are admitted together. No external
        # tools, grant or autonomous business effect is added.
        if "research_sources" in spec:
            existing=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                                (tid,)).fetchone()[0]
            if existing!=0:
                raise ValueError("RESEARCH_REVIEW_DUPLICATED")
            review_spec={"kind":"research_assessment","research_task_id":tid,
                         "sources":spec["research_sources"]}
            create_task(db,review_spec,parent=tid,commit=False)
            event(db,tid,"RESEARCH_REVIEW_ENQUEUED",{
                "source_hashes":[x["sha256"] for x in spec["research_sources"]],
                "production_effect_authorized":False})
        return effect
    try:
        result=finalize_observed(db,task,"NEEDS_REVIEW",
             decision="RESEARCH_AGENDA_NOT_ANSWERED",artifact_writer=writer)
    except (KnowledgeRoutingError,ArtifactConflict,OSError,ValueError):
        return finalize_observed(db,task,"UNKNOWN",error_code="RESEARCH_SOURCE_UNAVAILABLE")
    if result["status"]=="NEEDS_REVIEW":
        return {**result,"artifact":f"artifacts/{tid}.json",
                "business_outcome_verified":False,"research_completed":False}
    return result

def audit_gap(db_path:Path,fixtures:Path,workspace:Path,parent_id:str,child_id:str|None=None)->dict:
    fail={"status":"UNVERIFIABLE","business_outcome_verified":False}
    if not isinstance(parent_id,str) or not _TASK_ID.fullmatch(parent_id):
        return {**fail,"reason":"INVALID_TASK_ID"}
    if not db_path.is_file() or db_path.is_symlink():
        return {**fail,"reason":"MISSING_LEDGER"}
    try:
        db=open_readonly_snapshot(db_path)
        try:
            if child_id is None:
                children=db.execute("SELECT task_id FROM tasks WHERE parent_task=?",
                                    (parent_id,)).fetchall()
                if len(children)!=1:return {**fail,"reason":"RESEARCH_CHILD_MISMATCH"}
                child_id=children[0][0]
            spec,reason=_readback(db,parent_id,child_id,fixtures)
            if reason!="MECHANICALLY_VALID":
                return {**fail,"reason":reason}
            if child_id is not None:
                row=db.execute("SELECT * FROM tasks WHERE task_id=?",(child_id,)).fetchone()
                if row["state"]=="NEEDS_REVIEW":
                    from .runner import verify_artifact
                    if not verify_artifact(workspace,dict(row)):
                        return {**fail,"reason":"RESEARCH_ARTIFACT_MISMATCH"}
                    path=workspace/"artifacts"/(child_id+".json")
                    if path.is_symlink() or path.read_bytes()!=(
                         json.dumps(_agenda(spec),sort_keys=True,indent=2,
                                    ensure_ascii=False)+"\n").encode():
                        return {**fail,"reason":"RESEARCH_AGENDA_MISMATCH"}
            return {"status":"PLAN_MECHANICALLY_VALID",
                    "research_task_id":child_id,
                    "business_outcome_verified":False}
        finally:
            db.close()
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
        return {**fail,"reason":"RESEARCH_AUDIT_UNAVAILABLE"}
