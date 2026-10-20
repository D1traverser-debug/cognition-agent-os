"""Bounded, non-destructive goal -> evidence -> alternatives -> candidate -> checker.

This is a deterministic, opt-in local goal family (JSON configuration and CSV
data), not a general LLM-planning agent or independent semantic oracle. The
same existing SQLite task/grant ledger and immutable artifact writer are used.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re

from .ledger import finalize
from .runner import ArtifactConflict, store_once
from .source import safe_fixture, SourceUnavailable

FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
MAX_GOAL_BYTES = 16 * 1024
MAX_SOURCE_BYTES = 64 * 1024
MAX_FIELDS = 16
MAX_ROWS = 200


class GoalError(ValueError):
    pass


class NoSafeCandidate(GoalError):
    pass


def _value(v):
    return v is None or isinstance(v, (str, bool, int)) and (
        not isinstance(v,str) or len(v) <= 256)


def validate_goal(spec: dict) -> dict:
    if not isinstance(spec, dict) or set(spec) != {"kind","goal_type","input","desired"}:
        raise GoalError("Goal has unexpected/missing keys")
    if spec["kind"] != "goal_case" or spec["goal_type"] not in ("json_keys", "csv_columns"):
        raise GoalError("Unsupported bounded goal family")
    source = spec["input"]
    desired = spec["desired"]
    if (not isinstance(source,str) or not 1<=len(source)<=200 or
        not isinstance(desired,dict) or not 1<=len(desired)<=MAX_FIELDS):
        raise GoalError("Invalid goal input or size")
    if any(not isinstance(k,str) or not FIELD.fullmatch(k) for k in desired):
        raise GoalError("Invalid required field")
    if spec["goal_type"] == "json_keys":
        if not all(_value(v) for v in desired.values()):
            raise GoalError("Only bounded literal expected values are allowed")
    else:
        if not all(isinstance(v,str) and len(v)<=128 for v in desired.values()):
            raise GoalError("CSV additions require explicit bounded string defaults")
    if len(json.dumps(spec,ensure_ascii=False).encode("utf-8"))>MAX_GOAL_BYTES:
        raise GoalError("Goal too large")
    return spec


def _unique_pairs(pairs):
    output = {}
    for k,v in pairs:
        if k in output:raise GoalError("Duplicate JSON source key")
        output[k]=v
    return output


def _parse(kind: str, raw: bytes):
    if len(raw)>MAX_SOURCE_BYTES:
        raise GoalError("Input exceeds small local cap")
    try:
        decoded=raw.decode("utf-8")
        if kind=="json_keys":
            obj=json.loads(decoded,object_pairs_hook=_unique_pairs)
            if not isinstance(obj,dict):
                raise GoalError("JSON input must be an object")
            return obj
        rows=list(csv.reader(io.StringIO(decoded,newline=""),strict=True))
    except (UnicodeError,ValueError,csv.Error) as exc:
        raise GoalError("Malformed goal source") from exc
    if not rows or len(rows)>MAX_ROWS+1 or not rows[0] or len(rows[0])>64:
        raise GoalError("CSV row/header bound")
    header=rows[0]
    if (any(not FIELD.fullmatch(s) for s in header) or len(set(header))!=len(header)
        or any(len(row)!=len(header) for row in rows[1:])):
        raise GoalError("CSV headers must be unique; rows rectangular")
    return rows


def _format(kind: str, obj) -> bytes:
    if kind=="json_keys":
        return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode("utf-8")
    out=io.StringIO(newline="")
    writer=csv.writer(out,lineterminator="\n")
    writer.writerows(obj)
    return out.getvalue().encode("utf-8")


def _candidates(kind: str, parsed, desired: dict) -> list[tuple[str,bytes]]:
    candidates=[("NO_OP",None)]
    if kind=="json_keys":
        if any(k in parsed and (type(parsed[k]) is not type(v) or parsed[k]!=v)
               for k,v in desired.items()):
            return candidates
        new=dict(parsed)
        for k,v in desired.items():
            if k not in new:new[k]=v
        candidates.append(("ADD_MISSING_JSON_KEYS",_format(kind,new)))
    else:
        header=parsed[0]
        additional=[k for k in desired if k not in header]
        rows=[header+additional]
        for original in parsed[1:]:
            rows.append(original+[desired[k] for k in additional])
        candidates.append(("ADD_MISSING_CSV_COLUMNS",_format(kind,rows)))
    return candidates


def _check_candidate(kind: str, parsed, desired: dict, candidate: bytes) -> bool:
    """Independent mechanical constraints, not trust in a planner's verdict."""
    try:
        checked=_parse(kind,candidate)
    except (GoalError,ValueError):
        return False
    if kind=="json_keys":
        return (all(k in checked and type(checked[k]) is type(v) and checked[k]==v
                    for k,v in desired.items())
                and all(k in checked and type(checked[k]) is type(v) and checked[k]==v
                        for k,v in parsed.items()))
    header=parsed[0]
    newhead=checked[0]
    if (newhead[:len(header)]!=header or not all(k in newhead for k in desired)
        or len(checked)!=len(parsed)):
        return False
    added=newhead[len(header):]
    if len(set(newhead))!=len(newhead) or added!=[k for k in desired if k not in header]:
        return False
    for oldrow,newrow in zip(parsed[1:],checked[1:]):
        if newrow[:len(header)]!=oldrow or newrow[len(header):]!=[desired[k] for k in added]:
            return False
    return True


def plan_goal(spec: dict, raw: bytes) -> dict:
    spec=validate_goal(spec)
    kind=spec["goal_type"]
    parsed=_parse(kind,raw)
    alternatives=[]
    winner=None
    for name,candidate in _candidates(kind,parsed,spec["desired"]):
        data=raw if candidate is None else candidate
        passes=_check_candidate(kind,parsed,spec["desired"],data)
        alternatives.append({"action":name,"constraints_pass":passes,
                             "candidate_sha256":hashlib.sha256(data).hexdigest()})
        if passes and winner is None:
            winner={"action":name,"payload":data}
    conflict=winner is None
    return {
        "alternatives":alternatives,
        "hypotheses":[
            {"statement":"Current evidence already meets explicit goal",
             "disposition":"SUPPORTED" if alternatives[0]["constraints_pass"] else "REFUTED"},
            {"statement":"A non-destructive authorized candidate may satisfy missing constraints",
             "disposition":"UNKNOWN" if conflict else "SUPPORTED"},
            {"statement":"A semantic requirement/source disagreement may explain the gap",
             "disposition":"UNRESOLVED_REQUIRES_EXTERNAL_EVIDENCE"}
        ],
        "selection": winner, "status":"NEEDS_REVIEW" if winner and winner["action"]!="NO_OP"
                    else "VERIFIED" if winner else "UNKNOWN",
        "limits":"These are candidate diagnoses; none establishes real-world causality"
    }


def run_goal_case(db, task: dict, workspace: Path, fixture_root: Path,
                  *, fail_at: str | None = None) -> dict:
    spec=json.loads(task["source_spec"])
    try:
        validate_goal(spec)
        first=safe_fixture(fixture_root,spec["input"])
        second=safe_fixture(fixture_root,spec["input"])
        if first!=second:raise SourceUnavailable("Input changed during acquisition")
        plan=plan_goal(spec,first)
    except (ValueError,KeyError,TypeError,OSError,SourceUnavailable) as exc:
        finalize(db,task,"UNKNOWN",error_code="GOAL_EVIDENCE_UNAVAILABLE")
        return {"task_id":task["task_id"],"status":"UNKNOWN",
                "reason":"GOAL_EVIDENCE_UNAVAILABLE","diagnostic":type(exc).__name__}
    if plan["selection"] is None:
        finalize(db,task,"UNKNOWN",error_code="NO_SAFE_GOAL_PLAN")
        return {"task_id":task["task_id"],"status":"UNKNOWN",
                "reason":"NO_SAFE_GOAL_PLAN","hypotheses":plan["hypotheses"]}
    if plan["selection"]["action"]=="NO_OP":
        finalize(db,task,"VERIFIED",decision="GOAL_ALREADY_SATISFIED")
        actual=db.execute("SELECT state,error_code FROM tasks WHERE task_id=?",(task["task_id"],)).fetchone()
        return {"task_id":task["task_id"],"status":actual["state"],
                "reason":actual["error_code"],"decision":"GOAL_ALREADY_SATISFIED"}
    payload=plan["selection"]["payload"]
    source_sha=hashlib.sha256(first).hexdigest()
    artifact={
        "task_id":task["task_id"],"goal_rev":task["goal_rev"],
        "source_sha256":source_sha,"goal_spec":spec,
        "chosen_action":plan["selection"]["action"],
        "alternatives":plan["alternatives"],
        "hypotheses":plan["hypotheses"],
        "candidate_text":payload.decode("utf-8"),
        "candidate_sha256":hashlib.sha256(payload).hexdigest(),
        "checker":"MECHANICAL_CONSTRAINTS_ONLY",
        "status":"PROPOSAL_NOT_APPROVED"
    }
    output=(json.dumps(artifact,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode("utf-8")
    def guarded_writer():
        latest=safe_fixture(fixture_root,spec["input"])
        if hashlib.sha256(latest).hexdigest()!=source_sha:
            raise SourceUnavailable("Input became stale at commit")
        if not _check_candidate(spec["goal_type"],_parse(spec["goal_type"],latest),
                                spec["desired"],payload):
            raise GoalError("Independent candidate check failed")
        return store_once(workspace,task["task_id"],output,
                          crash_after_write=fail_at=="after_artifact_before_commit")
    try:
        accepted=finalize(db,task,"NEEDS_REVIEW",decision=plan["selection"]["action"],
                          artifact_writer=guarded_writer)
    except (ArtifactConflict,GoalError,SourceUnavailable,ValueError,OSError):
        finalize(db,task,"UNKNOWN",error_code="GOAL_CANDIDATE_OR_INPUT_CONFLICT")
        return {"task_id":task["task_id"],"status":"UNKNOWN",
                "reason":"GOAL_CANDIDATE_OR_INPUT_CONFLICT"}
    if not accepted:
        return {"task_id":task["task_id"],"status":"STALE_WORKER"}
    actual=db.execute("SELECT state,decision,error_code FROM tasks WHERE task_id=?",
                      (task["task_id"],)).fetchone()
    return {"task_id":task["task_id"],"status":actual["state"],
            "decision":actual["decision"],"reason":actual["error_code"],
            "artifact":f"artifacts/{task['task_id']}.json" if actual["state"]=="NEEDS_REVIEW" else None,
            "external_outcome_verified":False}
