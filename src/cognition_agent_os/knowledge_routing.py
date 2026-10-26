"""P33 bounded evidence-routed intent in the EXISTING SQLite authority.

This is a first runnable knowledge-to-action slice, not an autonomous learner
or a direct connector to the private ChatGPT Library. Knowledge is untrusted,
content-addressed evidence; it can select only among two to eight owner-seeded,
registered, separately validated capabilities. No instructions are executed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .intent_planner import compile_intent, IntentError
from .ledger import connect, create_task, current_guard, event, finalize_observed
from .source import safe_fixture, SourceUnavailable

_ID=re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SHA=re.compile(r"[a-f0-9]{64}\Z")
_MAX_SPEC=16384
_MAX_KNOWLEDGE=16384

class KnowledgeRoutingError(ValueError):
    def __init__(self,reason:str):
        super().__init__(reason)
        self.reason=reason


def _bound_id(value:object)->bool:
    return isinstance(value,str) and bool(_ID.fullmatch(value))


def _checked_spec(spec:dict)->dict:
    if (not isinstance(spec,dict)
        or set(spec) not in ({"kind","goal_key","knowledge","options"},
                            {"kind","goal_key","knowledge","options","research_on_gap"},
                            {"kind","goal_key","knowledge","options","research_on_gap","research_sources"})
        or ("research_on_gap" in spec and spec["research_on_gap"] is not True)
        or spec["kind"]!="knowledge_intent"
        or not _bound_id(spec["goal_key"])):
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    try:
        if len(json.dumps(spec,sort_keys=True,ensure_ascii=False).encode())>_MAX_SPEC:
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    except (TypeError,ValueError,OverflowError):
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    if "research_sources" in spec:
        sources=spec["research_sources"]
        if (spec.get("research_on_gap") is not True or not isinstance(sources,list)
            or len(sources)!=2 or not all(isinstance(s,dict) and
            (set(s)=={"path","sha256","source_id","publisher_id"} or
             set(s)=={"kind","repo","path","ref","sha256","source_id","publisher_id"}
             and s.get("kind")=="github") for s in sources)):
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
        for item in sources:
            if (not isinstance(item["path"],str) or not item["path"].endswith(".json")
                or len(item["path"])>180 or item["path"].startswith(".")
                or ("kind" not in item and "/" in item["path"])
                or "\\" in item["path"]
                or not isinstance(item["sha256"],str) or not _SHA.fullmatch(item["sha256"])
                or not _bound_id(item["source_id"]) or not _bound_id(item["publisher_id"])):
                raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
        from .source import _REPO_RE, _SHA_RE
        for item in sources:
            if "kind" in item:
                if (not isinstance(item["repo"],str) or not _REPO_RE.fullmatch(item["repo"])
                    or not isinstance(item["ref"],str) or not _SHA_RE.fullmatch(item["ref"])
                    or item["path"].startswith("/") or ".." in item["path"].split("/")
                    or any(not segment or segment=="." for segment in item["path"].split("/"))
                    or not item["path"].endswith(".json")):
                    raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
        if (sources[0]["source_id"]==sources[1]["source_id"] or
            sources[0]["publisher_id"]==sources[1]["publisher_id"] or
            (sources[0]["path"]==sources[1]["path"]
             and sources[0].get("repo")==sources[1].get("repo"))):
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    knowledge=spec["knowledge"]
    if (not isinstance(knowledge,dict)
        or set(knowledge)!={"path","sha256","source_id"}
        or not isinstance(knowledge["path"],str)
        or not 1<=len(knowledge["path"])<=180
        or "/" in knowledge["path"] or "\\" in knowledge["path"]
        or knowledge["path"].startswith(".")
        or not isinstance(knowledge["sha256"],str)
        or not _SHA.fullmatch(knowledge["sha256"])
        or not _bound_id(knowledge["source_id"])):
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    options=spec["options"]
    if not isinstance(options,list) or not 2 <= len(options) <= 8:
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    validated={}
    for entry in options:
        if (not isinstance(entry,dict) or set(entry)!={"route","intent"}
            or not _bound_id(entry["route"]) or entry["route"] in validated):
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
        try:
            validated[entry["route"]]=compile_intent(entry["intent"])
        except (IntentError,TypeError,ValueError,KeyError):
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    return validated


def resolve_knowledge_route(spec:dict,fixtures:Path)->dict:
    """Exact source ID + goal + one unwithdrawn claim; no fuzzy near neighbor."""
    options=_checked_spec(spec)
    contract=spec["knowledge"]
    try:
        raw=safe_fixture(fixtures,contract["path"])
        if len(raw)>_MAX_KNOWLEDGE or hashlib.sha256(raw).hexdigest()!=contract["sha256"]:
            raise KnowledgeRoutingError("KNOWLEDGE_UNAVAILABLE")
        obj=json.loads(raw)
    except (SourceUnavailable,OSError,ValueError,UnicodeError,TypeError):
        raise KnowledgeRoutingError("KNOWLEDGE_UNAVAILABLE")
    if (not isinstance(obj,dict) or set(obj)!={"schema_version","source_id","claims"}
        or obj["schema_version"]!=1 or obj["source_id"]!=contract["source_id"]
        or not isinstance(obj["claims"],list)
        or not 1<=len(obj["claims"])<=16):
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    claims=obj["claims"]
    for claim in claims:
        if (not isinstance(claim,dict)
            or set(claim)!={"goal_key","route","status","source_ref"}
            or not _bound_id(claim["goal_key"])
            or not _bound_id(claim["route"])
            or claim["status"] not in ("active","withdrawn")
            or not isinstance(claim["source_ref"],str)
            or not 1<=len(claim["source_ref"])<=128):
            raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    matches=[x for x in claims if x["goal_key"]==spec["goal_key"]]
    if len(matches)!=1 or matches[0]["status"]!="active":
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    selected=matches[0]
    if selected["route"] not in options:
        raise KnowledgeRoutingError("KNOWLEDGE_NOT_APPLICABLE")
    return {"route":selected["route"],
            "source_ref":selected["source_ref"],
            "knowledge_sha256":contract["sha256"],
            "plan":options[selected["route"]]}


def ensure_dependencies(db:sqlite3.Connection)->None:
    # Same authoritative DB; no second store or self-authorizing monitor.
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge_dependencies(
        task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
        evidence_path TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        source_id TEXT NOT NULL
    )""")


def check_child_dependency(db:sqlite3.Connection,task_id:str,fixtures:Path)->bool:
    # An open-language owner goal is a model-proposed capability, never a
    # source of new authority. Every file shown to that model stays pinned to
    # the source bytes present when the child was created. This applies to
    # BOTH input files for a selected record comparison, not just one.
    candidate=db.execute(
        "SELECT parent_task,source_spec FROM tasks WHERE task_id=?",
        (task_id,)).fetchone()
    if candidate is None:
        return False
    if candidate["parent_task"] is not None:
        parent=db.execute("SELECT source_spec FROM tasks WHERE task_id=?",
                          (candidate["parent_task"],)).fetchone()
        if parent is None:
            return False
        try:
            parent_spec=json.loads(parent["source_spec"])
        except (ValueError, TypeError):
            return False
        if isinstance(parent_spec,dict) and parent_spec.get("kind")=="open_goal":
            from .open_goal import validate_open_goal, _manifest
            from .intent_planner import compile_intent
            try:
                validate_open_goal(parent_spec)
                proofs=db.execute(
                    "SELECT details FROM events WHERE task_id=? "
                    "AND kind='OPEN_GOAL_DECOMPOSED'",
                    (candidate["parent_task"],)).fetchall()
                compound=db.execute(
                    "SELECT details FROM events WHERE task_id=? "
                    "AND kind='OPEN_GOAL_INDEPENDENT_OBLIGATIONS'",
                    (candidate["parent_task"],)).fetchall()
                if compound:
                    if proofs or len(compound)!=1:
                        return False
                    evidence=json.loads(compound[0]["details"])
                    if (not isinstance(evidence,dict)
                        or evidence.get("semantic_approval") is not False
                        or evidence.get("real_owner_outcome_verified") is not False
                        or evidence.get("original_goal")!=parent_spec["goal"]
                        or not isinstance(evidence.get("obligations"),list)
                        or len(evidence["obligations"])!=2):
                        return False
                    entries=evidence["obligations"]
                    if (not all(isinstance(e,dict) and
                                set(e)=={"child_task_id","clause",
                                        "plan","model_candidate"} for e in entries)
                        or not all(isinstance(e["clause"],str) for e in entries)
                        or parent_spec["goal"].strip().rstrip(".").strip()!=
                           f"{entries[0]['clause']} and {entries[1]['clause']}"):
                        return False
                    siblings=db.execute(
                        "SELECT task_id FROM tasks WHERE parent_task=?",
                        (candidate["parent_task"],)).fetchall()
                    if ({row["task_id"] for row in siblings} !=
                        {e["child_task_id"] for e in entries}
                        or len(siblings)!=2):
                        return False
                    for index,e in enumerate(entries):
                        c=compile_intent(e["model_candidate"]["intent"])
                        objective=("investigate_evidence" if index==0
                                   else "ensure_structure")
                        if (c.get("objective")!=objective
                            or c!=e["plan"]):
                            return False
                        if e["child_task_id"]==task_id:
                            if c["child_source_spec"]!=json.loads(candidate["source_spec"]):
                                return False
                    if task_id not in {e["child_task_id"] for e in entries}:
                        return False
                else:
                    if len(proofs)!=1:
                        return False
                    evidence=json.loads(proofs[0]["details"])
                    if (not isinstance(evidence,dict)
                        or evidence.get("child_task_id")!=task_id
                        or evidence.get("semantic_approval") is not False
                        or not isinstance(evidence.get("source_sha256"),dict)
                        or (not evidence["source_sha256"] and not (
                            parent_spec.get("allow_public_discovery") is True
                            and json.loads(candidate["source_spec"]).get("kind")
                                == "public_tool_discovery"))
                        or not isinstance(evidence.get("model_candidate"),dict)
                        or evidence["model_candidate"].get("intent") is None):
                        return False
                    compiled=compile_intent(evidence["model_candidate"]["intent"])
                    if (compiled!=evidence.get("plan")
                        or compiled["child_source_spec"]!=json.loads(candidate["source_spec"])):
                        return False
                if not isinstance(evidence.get("source_sha256"),dict):
                    return False
                _, complete_hashes = _manifest(
                    fixtures,
                    allow_empty=parent_spec.get("allow_public_discovery") is True)
                # A truncated receipt must not silently unpin late sources.
                if complete_hashes != evidence["source_sha256"]:
                    return False
            except (ValueError,TypeError,KeyError,OSError,SourceUnavailable):
                return False
    row=db.execute(
        "SELECT evidence_path,evidence_sha256 FROM knowledge_dependencies WHERE task_id=?",
        (task_id,)).fetchone()
    if row is None:
        return True
    try:
        raw=safe_fixture(fixtures,row["evidence_path"])
    except (ValueError,OSError,SourceUnavailable):
        return False
    return hashlib.sha256(raw).hexdigest()==row["evidence_sha256"]


def run_knowledge_intent(db:sqlite3.Connection,task:dict,fixtures:Path)->dict:
    tid=task["task_id"]
    if task.get("parent_task") is not None:
        return finalize_observed(db,task,"UNKNOWN",error_code="KNOWLEDGE_RECURSION_REFUSED")
    try:
        spec=json.loads(task["source_spec"])
        chosen=resolve_knowledge_route(spec,fixtures)
    except KnowledgeRoutingError as exc:
        # Only a *valid, pinned and structurally credible* but undecidable
        # observation may generate research; malformed/missing evidence
        # cannot be converted into fabricated knowledge.
        if (isinstance(spec,dict) and spec.get("research_on_gap") is True
            and exc.reason=="KNOWLEDGE_NOT_APPLICABLE"):
            from .research_gap import classify_research_gap,enqueue_research_gap
            try:
                gap=classify_research_gap(spec,fixtures)
                if gap is not None:
                    return enqueue_research_gap(db,task,fixtures,spec,gap)
            except KnowledgeRoutingError:
                pass
        return finalize_observed(db,task,"UNKNOWN",error_code=exc.reason)
    except (ValueError,TypeError,KeyError):
        return finalize_observed(db,task,"UNKNOWN",error_code="KNOWLEDGE_NOT_APPLICABLE")
    db.execute("BEGIN IMMEDIATE")
    try:
        current=db.execute("SELECT claim_token,state FROM tasks WHERE task_id=?",
                           (tid,)).fetchone()
        if (current is None or current["claim_token"]!=task["claim_token"]
            or current["state"]!="RUNNING"):
            db.commit()
            return {"task_id":tid,"status":"STALE_WORKER"}
        allowed,reason=current_guard(db,task,needs_write=True)
        if not allowed:
            db.execute("""UPDATE tasks SET state='BLOCKED',error_code=?,
                        state_version=state_version+1,lease_until=NULL,claim_token=NULL
                        WHERE task_id=?""",(reason,tid))
            event(db,tid,"KNOWLEDGE_INTENT_BLOCKED",{"reason":reason})
            db.commit()
            return {"task_id":tid,"status":"BLOCKED","reason":reason}
        # SOURCE and exact route must still match after decision and
        # immediately before admitting its selected child under the DB lock.
        try:
            confirmed=resolve_knowledge_route(spec,fixtures)
        except KnowledgeRoutingError as exc:
            db.execute("""UPDATE tasks SET state='UNKNOWN',error_code=?,
                         state_version=state_version+1,lease_until=NULL,claim_token=NULL
                         WHERE task_id=?""",(exc.reason,tid))
            event(db,tid,"KNOWLEDGE_INTENT_REJECTED",{"reason":exc.reason})
            db.commit()
            return {"task_id":tid,"status":"UNKNOWN","reason":exc.reason}
        if confirmed!=chosen:
            raise RuntimeError("Knowledge route changed across independent reads")
        ensure_dependencies(db)
        child=create_task(db,chosen["plan"]["child_source_spec"],parent=tid,commit=False)
        db.execute("""INSERT INTO knowledge_dependencies
            (task_id,evidence_path,evidence_sha256,source_id)
            VALUES(?,?,?,?)""",
            (child,spec["knowledge"]["path"],chosen["knowledge_sha256"],
             spec["knowledge"]["source_id"]))
        db.execute("""UPDATE tasks SET state='DECOMPOSED',decision=?,
                   error_code=NULL,state_version=state_version+1,
                   lease_until=NULL,claim_token=NULL WHERE task_id=?""",
                   ("KNOWLEDGE_ROUTED_REGISTERED_PLAN",tid))
        event(db,tid,"KNOWLEDGE_INTENT_DECOMPOSED",{
            "child_task_id":child,"route":chosen["route"],
            "source_ref":chosen["source_ref"],
            "knowledge_sha256":chosen["knowledge_sha256"],
            "plan_sha256":chosen["plan"]["plan_sha256"],
            "semantic_approval":False})
        db.commit()
        return {"task_id":tid,"status":"DECOMPOSED","route":chosen["route"],
                "child_task_id":child,"capability":chosen["plan"]["capability"],
                "plan_sha256":chosen["plan"]["plan_sha256"],
                "business_outcome_verified":False}
    except BaseException:
        db.rollback()
        raise


def audit_knowledge_intent_plan(db_path:Path,fixtures:Path,task_id:str)->dict:
    """Independent read-only source/route/child/receipt provenance check.

    It is not a semantic proof that a user's desired business effect occurred
    and does not turn retrieved knowledge into a new authorization authority.
    """
    fail={"task_id":task_id,"status":"UNVERIFIABLE",
          "business_outcome_verified":False}
    if not isinstance(task_id,str) or not re.fullmatch(r"[0-9a-f]{32}",task_id):
        return {**fail,"reason":"INVALID_TASK_ID"}
    if not db_path.is_file() or db_path.is_symlink():
        return {**fail,"reason":"MISSING_LEDGER"}
    try:
        # A verifier is read-only and cannot create, upgrade or re-own
        # a DB while the conformance sweep holds its original transaction.
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        db=sqlite3.connect(uri,uri=True,timeout=5)
        db.row_factory=sqlite3.Row
        try:
            root=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if root is None or root["state"]!="DECOMPOSED":
                return {**fail,"reason":"PLAN_EVENT_UNAVAILABLE"}
            spec=json.loads(root["source_spec"])
            try:
                chosen=resolve_knowledge_route(spec,fixtures)
            except KnowledgeRoutingError as exc:
                return {**fail,"reason":exc.reason}
            events=db.execute("""SELECT details FROM events WHERE task_id=?
                AND kind='KNOWLEDGE_INTENT_DECOMPOSED'""",(task_id,)).fetchall()
            if len(events)!=1:
                return {**fail,"reason":"KNOWLEDGE_RECEIPT_INVALID"}
            receipt=json.loads(events[0]["details"])
            if (not isinstance(receipt,dict)
                or set(receipt)!={"child_task_id","route","source_ref",
                                  "knowledge_sha256","plan_sha256","semantic_approval"}
                or receipt["semantic_approval"] is not False
                or receipt["route"]!=chosen["route"]
                or receipt["source_ref"]!=chosen["source_ref"]
                or receipt["knowledge_sha256"]!=chosen["knowledge_sha256"]
                or receipt["plan_sha256"]!=chosen["plan"]["plan_sha256"]):
                return {**fail,"reason":"KNOWLEDGE_RECEIPT_INVALID"}
            child=db.execute("SELECT * FROM tasks WHERE task_id=?",
                             (receipt["child_task_id"],)).fetchone()
            dependent=db.execute("""SELECT evidence_path,evidence_sha256,source_id
                FROM knowledge_dependencies WHERE task_id=?""",
                (receipt["child_task_id"],)).fetchone()
            count=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                             (task_id,)).fetchone()[0]
            if (not child or count!=1 or child["parent_task"]!=task_id
                or child["goal_rev"]!=root["goal_rev"]
                or child["grant_rev"]!=root["grant_rev"]
                or json.loads(child["source_spec"])!=chosen["plan"]["child_source_spec"]
                or not dependent or
                (dependent["evidence_path"],dependent["evidence_sha256"],
                 dependent["source_id"])
                !=(spec["knowledge"]["path"],chosen["knowledge_sha256"],
                   spec["knowledge"]["source_id"])):
                return {**fail,"reason":"KNOWLEDGE_CHILD_DEPENDENCY_MISMATCH"}
            return {"task_id":task_id,"status":"PLAN_MECHANICALLY_VALID",
                    "route":chosen["route"],
                    "child_task_id":receipt["child_task_id"],
                    "knowledge_sha256":chosen["knowledge_sha256"],
                    "business_outcome_verified":False,
                    "authorizes_production_mutation":False}
        finally:
            db.close()
    except (OSError,sqlite3.Error,TypeError,KeyError,ValueError):
        return {**fail,"reason":"KNOWLEDGE_AUDIT_UNAVAILABLE"}
