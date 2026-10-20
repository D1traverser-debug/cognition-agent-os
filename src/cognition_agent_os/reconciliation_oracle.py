"""Independent SQLite relational oracle for bounded CSV discrepancy proposals.

Does not call the candidate planner, infer via its helpers, invoke a model,
modify source data or mark a business result independently accomplished.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3

_COL=re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")


def _read_rows(data: bytes):
    if len(data)>128*1024:
        raise ValueError("Exceeded oracle byte budget")
    stream=io.StringIO(data.decode("utf-8-sig"),newline="")
    reader=csv.DictReader(stream,restkey="__extra__",restval=None,strict=True)
    fields=reader.fieldnames
    if (not fields or not 1<=len(fields)<=24 or len(set(fields))!=len(fields)
        or any(not isinstance(f,str) or not _COL.fullmatch(f) for f in fields)):
        raise ValueError("Unsupported evidence header")
    rows=list(reader)
    if (len(rows)>250 or any("__extra__" in row or
        any(row[f] is None for f in fields) for row in rows)):
        raise ValueError("Evidence records malformed")
    return fields,rows


def _derive_sql_key(db, headers_a, a, headers_b, b, *, pinned_key=None):
    candidates=[]
    common=sorted(set(headers_a)&set(headers_b))
    identity_columns=[field for field in common if
                      field.lower()=="id" or field.lower().endswith("_id")
                      or field.lower().endswith("_key")]
    for field in common:
        if pinned_key is not None and field!=pinned_key:
            continue
        av=[row[field] for row in a]
        bv=[row[field] for row in b]
        if (not av or not bv or
            any(not item.strip() for item in av+bv)
            or len(set(av))!=len(av) or len(set(bv))!=len(bv)):
            if field in identity_columns or pinned_key is not None:
                return None
            continue
        db.execute("DELETE FROM ids_a")
        db.execute("DELETE FROM ids_b")
        db.executemany("INSERT INTO ids_a(k) VALUES(?)",[(v,) for v in av])
        db.executemany("INSERT INTO ids_b(k) VALUES(?)",[(v,) for v in bv])
        overlap=db.execute("SELECT COUNT(*) FROM ids_a INNER JOIN ids_b USING (k)").fetchone()[0]
        if overlap<1:
            if field in identity_columns:
                return None
            continue
        id_prior=(field.lower()=="id" or field.lower().endswith("_id")
                  or field.lower().endswith("_key"))
        score=(100 if id_prior else 0)+int(100*overlap/max(len(a),len(b)))
        if pinned_key is not None or not identity_columns or field in identity_columns:
            candidates.append((score,field))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    if not candidates or (len(candidates)>1 and candidates[0][0]==candidates[1][0]):
        return None
    return candidates[0][1]


def sql_audit(spec: dict, reference: bytes, observed: bytes, proposal: dict,
              *, pinned: dict | None = None) -> dict:
    """Independently recompute key and *all* differences from original data."""
    if not isinstance(proposal,dict):
        return {"agreement":False,"reason":"INVALID_PROPOSAL"}
    if "relationship_contract" in spec and pinned is None:
        return {"agreement":False,"reason":"UNVERIFIED_RELATIONSHIP"}
    if (proposal.get("relationship_contract_sha256") !=
        (pinned["digest"] if pinned else None)):
        return {"agreement":False,"reason":"RELATIONSHIP_IDENTITY_MISMATCH"}
    try:
        ha,ra=_read_rows(reference)
        hb,rb=_read_rows(observed)
        db=sqlite3.connect(":memory:")
        try:
            db.executescript("""
                CREATE TABLE ids_a(k TEXT PRIMARY KEY);
                CREATE TABLE ids_b(k TEXT PRIMARY KEY);
                CREATE TABLE ref(k TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE obs(k TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            key=_derive_sql_key(db,ha,ra,hb,rb,
                                pinned_key=pinned["key"] if pinned else None)
            if key is None:
                expected={"status":"INSUFFICIENT_KEY_EVIDENCE","selected_key":None,
                          "discrepancies":None}
            else:
                db.executemany("INSERT INTO ref VALUES(?,?)",
                               [(row[key],json.dumps(row,sort_keys=True)) for row in ra])
                db.executemany("INSERT INTO obs VALUES(?,?)",
                               [(row[key],json.dumps(row,sort_keys=True)) for row in rb])
                diffs=[]
                diffs += [{"kind":"missing_observed","key":row[0]} for row in
                          db.execute("""SELECT ref.k FROM ref LEFT JOIN obs USING(k)
                            WHERE obs.k IS NULL ORDER BY ref.k""")]
                diffs += [{"kind":"unexpected_observed","key":row[0]} for row in
                          db.execute("""SELECT obs.k FROM obs LEFT JOIN ref USING(k)
                            WHERE ref.k IS NULL ORDER BY obs.k""")]
                for field in sorted((set(ha)&set(hb))-{key}):
                    path='$."'+field+'"'
                    sql="""SELECT ref.k, json_extract(ref.payload, ?),
                              json_extract(obs.payload, ?) FROM ref
                              INNER JOIN obs USING(k)
                              WHERE json_extract(ref.payload, ?) IS NOT
                                    json_extract(obs.payload, ?)
                              ORDER BY ref.k"""
                    diffs += [{"kind":"field_mismatch","key":k,"field":field,
                               "reference":left,"observed":right} for k,left,right in
                              db.execute(sql,(path,path,path,path))]
                # Compare structured differences order independently of query order.
                diffs.sort(key=lambda d:(d["kind"],d["key"],d.get("field","")))
                extra_a=sorted(set(ha)-set(hb))
                extra_b=sorted(set(hb)-set(ha))
                expected={
                    "status":"DISCREPANCIES_FOUND" if diffs or extra_a or extra_b else "CONSISTENT",
                    "selected_key":key,"discrepancies":diffs,
                    "reference_only_columns":extra_a,
                    "observed_only_columns":extra_b,
                    "rows_reference":len(ra),"rows_observed":len(rb)
                }
            verified=(expected["status"]==proposal.get("status")
                      and expected["selected_key"]==proposal.get("selected_key")
                      and (expected["discrepancies"] is None and proposal.get("discrepancies") is None
                           or isinstance(expected["discrepancies"],list)
                           and isinstance(proposal.get("discrepancies"),list)
                           and expected["discrepancies"]==sorted(
                               proposal["discrepancies"],
                               key=lambda d:(d["kind"],d["key"],d.get("field","")))))
            if key is not None:
                for field in ("reference_only_columns","observed_only_columns",
                              "rows_reference","rows_observed"):
                    verified=verified and expected[field]==proposal.get(field)
            return {"agreement":bool(verified),"key":key,
                    "checker":"SQLITE_SOURCE_RECOMPUTATION",
                    "external_semantic_truth":False}
        finally:db.close()
    except (ValueError,TypeError,KeyError,csv.Error,sqlite3.Error,UnicodeError):
        return {"agreement":False,"reason":"ORACLE_SOURCE_INVALID"}


def audit_stored_report(db_path, workspace, fixture_root, task_id: str) -> dict:
    """Read-only independent post-artifact check; no DB or source mutation."""
    import hashlib
    import re
    from pathlib import Path
    from urllib.parse import quote
    from .source import safe_fixture
    fail={"task_id":task_id,"status":"UNVERIFIABLE",
          "business_outcome_verified":False,"authorizes_mutation":False}
    if not isinstance(task_id,str) or not re.fullmatch(r"[0-9a-f]{32}",task_id):
        return {**fail,"reason":"INVALID_TASK_ID"}
    db_path=Path(db_path)
    workspace=Path(workspace)
    fixture_root=Path(fixture_root)
    if not db_path.is_file() or db_path.is_symlink() or workspace.is_symlink():
        return {**fail,"reason":"UNSAFE_OR_MISSING_LEDGER"}
    try:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with sqlite3.connect(uri,uri=True) as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not row or not owner or row["state"]!="NEEDS_REVIEW":
                return {**fail,"reason":"TASK_NOT_REVIEWABLE"}
            if row["goal_rev"]!=owner["goal_rev"]:
                return {**fail,"reason":"STALE_GOAL"}
            source_spec=json.loads(row["source_spec"])
            if source_spec.get("kind")!="record_reconciliation":
                return {**fail,"reason":"INCORRECT_TASK_TYPE"}
            artifact_dir=workspace/"artifacts"
            artifact=artifact_dir/(task_id+".json")
            if (artifact_dir.is_symlink() or artifact.is_symlink()
                    or not artifact.is_file() or artifact.stat().st_size>150000):
                return {**fail,"reason":"ARTIFACT_MISSING_OR_UNSAFE"}
            data=artifact.read_bytes()
            if (hashlib.sha256(data).hexdigest()!=row["artifact_hash"]):
                return {**fail,"reason":"ARTIFACT_HASH_MISMATCH"}
            document=json.loads(data)
            if (document.get("task_id")!=task_id or
                document.get("source_spec")!=source_spec or
                document.get("status")!="PROPOSAL_NOT_APPROVED"):
                return {**fail,"reason":"ARTIFACT_IDENTITY_MISMATCH"}
            left=safe_fixture(fixture_root,source_spec["reference"])
            right=safe_fixture(fixture_root,source_spec["observed"])
            if document.get("source_sha256")!={
                "reference":hashlib.sha256(left).hexdigest(),
                "observed":hashlib.sha256(right).hexdigest()
            }:
                return {**fail,"reason":"SOURCE_HAS_CHANGED"}
            from .semantic_contract import load_pinned_relationship
            pinned=load_pinned_relationship(source_spec,fixture_root)
            result=sql_audit(source_spec,left,right,document["proposal"],pinned=pinned)
            if not result["agreement"]:
                return {**fail,"reason":"INDEPENDENT_SQL_REJECTION"}
            return {"task_id":task_id,"status":"REPORT_MECHANICALLY_VERIFIED",
                    "independent_sql_recheck":True,"business_outcome_verified":False,
                    "authorizes_mutation":False,
                    "artifact_sha256":row["artifact_hash"]}
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
        return {**fail,"reason":"EVIDENCE_RECHECK_UNAVAILABLE"}
