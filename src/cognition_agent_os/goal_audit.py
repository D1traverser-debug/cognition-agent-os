"""Independent *mechanical* P5 artifact auditor; no model or external writes.

An audit does not turn NEEDS_REVIEW into an approved modification. This checker
is separately implemented from the goal proposal builder and reads actual
SQLite+source+artifact bytes, failing closed on mismatches.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from .source import safe_fixture
from .ledger import lineage_guard

TASK_ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_BYTES = 128 * 1024


def _reject(reason: str, task_id: str) -> dict:
    return {"task_id":task_id, "status":reason,
            "mechanical_audit":False, "semantic_goal_achieved":False,
            "authorizes_source_mutation":False}


def _read_only(db_path: Path, task_id: str):
    if not db_path.is_file() or db_path.is_symlink():
        return None
    uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.row_factory=sqlite3.Row
        task=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
        authority=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        return (dict(task) if task else None, dict(authority) if authority else None,
                lineage_guard(db, dict(task)) if task else False)


def _parse_json(bytestring: bytes):
    def unique(pairs):
        d={}
        for key,value in pairs:
            if key in d:raise ValueError("Duplicate JSON field")
            d[key]=value
        return d
    obj=json.loads(bytestring.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(obj,dict):
        raise ValueError("Expected JSON object")
    return obj


def _parse_csv(bytestring: bytes):
    rows=list(csv.reader(io.StringIO(bytestring.decode("utf-8"),newline=""),strict=True))
    if not rows or not rows[0] or len(rows)>201 or len(set(rows[0]))!=len(rows[0]):
        raise ValueError("Invalid source table")
    if any(len(row)!=len(rows[0]) for row in rows):
        raise ValueError("Non-rectangular CSV")
    return rows


def _constraints(spec: dict, before: bytes, after: bytes) -> bool:
    if spec["goal_type"]=="json_keys":
        original=_parse_json(before)
        candidate=_parse_json(after)
        for key,value in original.items():
            if key not in candidate or type(candidate[key]) is not type(value) or candidate[key]!=value:
                return False
        return (set(candidate) == set(original) | set(spec["desired"])
                and all(key in candidate and type(candidate[key]) is type(value)
                        and candidate[key]==value for key,value in spec["desired"].items()))
    if spec["goal_type"]=="csv_columns":
        original=_parse_csv(before)
        candidate=_parse_csv(after)
        original_header=original[0]
        header=candidate[0]
        required=spec["desired"]
        if (len(candidate)!=len(original) or header[:len(original_header)]!=original_header
            or len(header)!=len(set(header)) or not all(key in header for key in required)):
            return False
        added=[key for key in required if key not in original_header]
        if header[len(original_header):]!=added:return False
        return all(row[:len(original_header)]==old
                   and row[len(original_header):]==[required[key] for key in added]
                   for old,row in zip(original[1:],candidate[1:]))
    return False


def audit_goal(db_path: Path, workspace: Path, fixture_root: Path, task_id: str) -> dict:
    if not isinstance(task_id,str) or not TASK_ID.fullmatch(task_id):
        return _reject("INVALID_TASK_ID",str(task_id)[:64])
    try:
        fetched=_read_only(db_path,task_id)
        if not fetched or not fetched[0] or not fetched[1]:
            return _reject("TASK_NOT_FOUND",task_id)
        task,authority,lineage_valid=fetched
        if not lineage_valid:
            return _reject("UPSTREAM_TASK_INVALID",task_id)
        if task["state"]!="NEEDS_REVIEW":
            return _reject("TASK_NOT_PENDING_REVIEW",task_id)
        spec=json.loads(task["source_spec"])
        if not isinstance(spec,dict) or spec.get("kind")!="goal_case":
            return _reject("NOT_GOAL_CASE",task_id)
        if (task["goal_rev"]!=authority["goal_rev"]
            or task["grant_rev"]!=authority["grant_rev"] or not authority["write_allowed"]):
            return _reject("STALE_AUTHORITY",task_id)
        if workspace.is_symlink() or (workspace/"artifacts").is_symlink():
            return _reject("UNSAFE_WORKSPACE",task_id)
        artifact=workspace/"artifacts"/(task_id+".json")
        if (artifact.is_symlink() or not artifact.is_file()
            or artifact.stat().st_size>MAX_BYTES):
            return _reject("ARTIFACT_UNAVAILABLE",task_id)
        raw_artifact=artifact.read_bytes()
        if (len(raw_artifact)>MAX_BYTES or
            hashlib.sha256(raw_artifact).hexdigest()!=task["artifact_hash"]):
            return _reject("ARTIFACT_HASH_MISMATCH",task_id)
        doc=json.loads(raw_artifact)
        if not isinstance(doc,dict) or doc.get("task_id")!=task_id or doc.get("goal_spec")!=spec:
            return _reject("ARTIFACT_IDENTITY_MISMATCH",task_id)
        if doc.get("status")!="PROPOSAL_NOT_APPROVED" or not isinstance(doc.get("candidate_text"),str):
            return _reject("INVALID_PROPOSAL",task_id)
        candidate=doc["candidate_text"].encode("utf-8")
        if (len(candidate)>MAX_BYTES or
            hashlib.sha256(candidate).hexdigest()!=doc.get("candidate_sha256")):
            return _reject("CANDIDATE_HASH_MISMATCH",task_id)
        source=safe_fixture(fixture_root,spec["input"])
        if hashlib.sha256(source).hexdigest()!=doc.get("source_sha256"):
            return _reject("SOURCE_CHANGED_SINCE_PROPOSAL",task_id)
        if not _constraints(spec,source,candidate):
            return _reject("CANDIDATE_CONSTRAINTS_FAILED",task_id)
        return {"task_id":task_id,"status":"CANDIDATE_MECHANICALLY_VALID",
                "mechanical_audit":True,"semantic_goal_achieved":False,
                "authorizes_source_mutation":False,
                "artifact_sha256":task["artifact_hash"],
                "source_sha256":doc["source_sha256"],
                "note":"Proposal preservation verified, not applied; no semantic approval"}
    except (ValueError,TypeError,KeyError,UnicodeError,sqlite3.Error,OSError):
        return _reject("AUDIT_UNVERIFIABLE",task_id)
