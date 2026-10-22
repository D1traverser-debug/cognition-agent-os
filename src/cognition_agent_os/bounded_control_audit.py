"""Read-only, separate recomputation of a bounded controller's local result.

This is NOT a business oracle. It independently checks exact SQLite lineage,
events, pinned sources, child evidence and canonical local postcondition.
Never imports controller transition code or mutates ledger/source.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from .bounded_outcome_oracle import assess_local_record
from .goal_audit import audit_goal
from .source import safe_fixture


def audit_controlled_candidate(db_path:Path,workspace:Path,
                               fixtures:Path,root_id:str)->dict:
    fail={"root_task_id":root_id,"status":"UNVERIFIABLE",
          "mechanical_audit":False,"business_outcome_verified":False,
          "authorizes_mutation":False}
    if not isinstance(root_id,str) or not re.fullmatch(r"[0-9a-f]{32}",root_id):
        return {**fail,"reason":"BAD_ROOT_ID"}
    if not db_path.is_file() or db_path.is_symlink():
        return {**fail,"reason":"MISSING_LEDGER"}
    try:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
            db.row_factory=sqlite3.Row
            root=db.execute("SELECT * FROM tasks WHERE task_id=?",(root_id,)).fetchone()
            if not root or root["state"]!="CONTROL_CANDIDATE_MATCHED":
                return {**fail,"reason":"NOT_MATCHED"}
            spec=json.loads(root["source_spec"])
            if (not isinstance(spec,dict) or spec.get("kind")!="bounded_local_controller"
                or spec.get("schema_version")!=1
                or spec.get("max_attempts")!=2
                or spec.get("allowed_effect")!="LOCAL_CANDIDATE_ONLY"
                or not isinstance(spec.get("alternatives"),list)
                or len(spec["alternatives"])!=2
                or not isinstance(spec.get("target"),dict)):
                return {**fail,"reason":"ROOT_CONTRACT_INVALID"}
            attempts=db.execute("""SELECT ordinal,child_task_id FROM bounded_goal_attempts
                    WHERE root_task_id=? ORDER BY ordinal""",(root_id,)).fetchall()
            if len(attempts) not in (1,2) or [x["ordinal"] for x in attempts]!=list(range(len(attempts))):
                return {**fail,"reason":"INVALID_ATTEMPT_SEQUENCE"}
            all_children=db.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                                    (root_id,)).fetchone()[0]
            if all_children!=len(attempts):
                return {**fail,"reason":"HIDDEN_OR_MISSING_CHILD"}
            admitted=[json.loads(x["details"]) for x in db.execute(
                "SELECT details FROM events WHERE task_id=? AND kind='BOUNDED_CONTROLLER_ADMITTED' ORDER BY event_id",
                (root_id,)).fetchall()]
            decided=[json.loads(x["details"]) for x in db.execute(
                "SELECT details FROM events WHERE task_id=? AND kind='BOUNDED_CONTROLLER_DECIDED'",
                (root_id,)).fetchall()]
            if len(admitted)!=len(attempts) or len(decided)!=1:
                return {**fail,"reason":"CONTROL_RECEIPTS_MISSING"}
            final=decided[0]
            if (final.get("state")!="CONTROL_CANDIDATE_MATCHED"
                or final.get("reason")!="PINNED_LOCAL_POSTCONDITION"
                or final.get("business_outcome_verified") is not False
                or final.get("authorizes_mutation") is not False):
                return {**fail,"reason":"FAKE_COMPLETION_RECEIPT"}
            for index,item in enumerate(attempts):
                child=db.execute("SELECT * FROM tasks WHERE task_id=?",
                                 (item["child_task_id"],)).fetchone()
                c=spec["alternatives"][index]
                proposal=c["task_spec"]
                receipt=admitted[index]
                if (not child or child["parent_task"]!=root_id
                    or child["goal_rev"]!=root["goal_rev"]
                    or child["grant_rev"]!=root["grant_rev"]
                    or json.loads(child["source_spec"])!=proposal
                    or receipt.get("ordinal")!=index
                    or receipt.get("child_task_id")!=child["task_id"]
                    or receipt.get("input_sha256")!=c["input_sha256"]
                    or receipt.get("method")!=proposal["goal_type"]
                    or receipt.get("goal_rev")!=root["goal_rev"]
                    or receipt.get("grant_rev")!=root["grant_rev"]
                    or receipt.get("business_outcome_verified") is not False):
                    return {**fail,"reason":"ATTEMPT_PROVENANCE_MISMATCH"}
                original=safe_fixture(fixtures,proposal["input"])
                digest=hashlib.sha256(original).hexdigest()
                if digest!=c["input_sha256"]:
                    return {**fail,"reason":"SOURCE_PIN_MISMATCH"}
                if index<len(attempts)-1:
                    # A narrower capability can report VERIFIED (e.g. a CSV
                    # column exists) while the pinned owner-level VALUE goal
                    # remains impossible under preservation-only semantics.
                    # Never adopt the child self-verdict as the goal oracle.
                    legitimate_failure=(
                        (child["state"]=="UNKNOWN" and
                         child["error_code"]=="NO_SAFE_GOAL_PLAN") or
                        (child["state"]=="VERIFIED" and
                         child["decision"]=="GOAL_ALREADY_SATISFIED"))
                    if not legitimate_failure:
                        return {**fail,"reason":"UNSUPPORTED_SWITCH_CAUSE"}
                    result=assess_local_record(kind=proposal["goal_type"],
                        original=original,current_sha256=digest,pinned_sha256=digest,
                        target=spec["target"],candidate=None)
                    if result["verdict"]!="PRESERVATION_CONFLICT":
                        return {**fail,"reason":"NO_INDEPENDENT_CONFLICT"}
                else:
                    if child["state"]=="NEEDS_REVIEW":
                        proof=audit_goal(db_path,workspace,fixtures,child["task_id"])
                        if proof["status"]!="CANDIDATE_MECHANICALLY_VALID":
                            return {**fail,"reason":"CHILD_ARTIFACT_REJECTED"}
                        artifact=workspace/"artifacts"/(child["task_id"]+".json")
                        if artifact.is_symlink():
                            return {**fail,"reason":"ARTIFACT_SYMLINK"}
                        independently_read=artifact.read_bytes()
                        if hashlib.sha256(independently_read).hexdigest()!=child["artifact_hash"]:
                            return {**fail,"reason":"ARTIFACT_CHANGED_AFTER_AUDIT"}
                        candidate=json.loads(independently_read)["candidate_text"].encode("utf-8")
                    elif child["state"]=="VERIFIED" and child["decision"]=="GOAL_ALREADY_SATISFIED":
                        candidate=original
                    else:
                        return {**fail,"reason":"UNSUPPORTED_FINAL_CHILD"}
                    result=assess_local_record(kind=proposal["goal_type"],
                        original=original,current_sha256=digest,pinned_sha256=digest,
                        target=spec["target"],candidate=candidate)
                    if (result["verdict"]!="LOCAL_CANDIDATE_TARGET_MET"
                        or final.get("ordinal")!=index
                        or final.get("child_task_id")!=child["task_id"]
                        or final.get("candidate_sha256")!=result["candidate_sha256"]):
                        return {**fail,"reason":"FINAL_POSTCONDITION_MISMATCH"}
            return {**fail,"status":"CONTROL_LOCAL_RECEIPT_VERIFIED",
                    "mechanical_audit":True,"attempts":len(attempts),
                    "candidate_sha256":final["candidate_sha256"]}
    except (sqlite3.Error,ValueError,KeyError,TypeError,OSError,UnicodeError,
            IndexError):
        return {**fail,"reason":"CONTROL_AUDIT_UNAVAILABLE"}
