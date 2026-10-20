"""P8: infer a record join hypothesis and propose an evidence-grounded audit.

Constrained data-reconciliation goal, not free-form language understanding.
Source bytes are treated as data, never commands; no originals are changed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from .ledger import finalize
from .runner import ArtifactConflict, store_once
from .source import safe_fixture, SourceUnavailable

IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_-]{0,63}\Z")
MAX_ROWS = 250
MAX_COLS = 24
MAX_BYTES = 128*1024
MAX_DISCREPANCIES = 1200


class ReconciliationError(ValueError):
    pass


def validate_reconciliation(spec: dict) -> dict:
    if (not isinstance(spec, dict) or
            set(spec) not in ({"kind","reference","observed","objective"},
                             {"kind","reference","observed","objective","relationship_contract"})
            or spec.get("kind")!="record_reconciliation"
            or spec.get("objective")!="identify_discrepancies"):
        raise ReconciliationError("Unsupported record reconciliation contract")
    for key in ("reference","observed"):
        value=spec[key]
        if (not isinstance(value,str) or not 1<=len(value)<=200 or
                Path(value).is_absolute() or ".." in Path(value).parts or
                "\\" in value or "/" in value):
            raise ReconciliationError("Invalid local source path")
    if spec["reference"]==spec["observed"]:
        raise ReconciliationError("Two distinct original sources are required")
    if "relationship_contract" in spec:
        from .semantic_contract import contract_binding
        contract_binding(spec["relationship_contract"],spec["reference"],spec["observed"])
    return spec


def parse_table(raw: bytes) -> tuple[list[str],list[dict[str,str]]]:
    if len(raw)>MAX_BYTES:
        raise ReconciliationError("CSV source exceeds bound")
    try:
        text=raw.decode("utf-8-sig")
        rows=list(csv.reader(io.StringIO(text,newline=""),strict=True))
    except (UnicodeError,csv.Error) as exc:
        raise ReconciliationError("Invalid CSV evidence") from exc
    if not rows or not 1<=len(rows[0])<=MAX_COLS or len(rows)>MAX_ROWS+1:
        raise ReconciliationError("Missing header, too many columns or records")
    fields=rows[0]
    if (len(set(fields))!=len(fields) or
            any(not IDENTIFIER.fullmatch(field) for field in fields) or
            any(len(row)!=len(fields) for row in rows[1:])):
        raise ReconciliationError("Invalid duplicate/header/non-rectangular CSV")
    return fields,[dict(zip(fields,row)) for row in rows[1:]]


def hypothesis_keys(headers_a: list[str], rows_a: list[dict],
                    headers_b: list[str], rows_b: list[dict]) -> list[dict]:
    common=sorted(set(headers_a)&set(headers_b))
    hypotheses=[]
    for field in common:
        lhs=[row[field] for row in rows_a]
        rhs=[row[field] for row in rows_b]
        valid=(bool(lhs) and bool(rhs) and
               all(value.strip() for value in lhs+rhs) and
               len(set(lhs))==len(lhs) and len(set(rhs))==len(rhs))
        overlap=len(set(lhs)&set(rhs)) if valid else 0
        # Key naming is a *fallible hypothesis prior*, not evidence of truth.
        id_name=field.lower()=="id" or field.lower().endswith("_id") or field.lower().endswith("_key")
        score=(100 if id_name else 0)+int(100*overlap/max(len(lhs),len(rhs))) if valid and overlap else -1
        hypotheses.append({"column":field,"uniqueness_supported":valid,
                           "shared_identifiers":overlap,"key_name_prior":id_name,
                           "score":score})
    return sorted(hypotheses,key=lambda x:(-x["score"],x["column"]))


def propose_reconciliation(spec: dict, a: bytes, b: bytes,
                           *, pinned: dict | None = None) -> dict:
    validate_reconciliation(spec)
    ha,ra=parse_table(a)
    hb,rb=parse_table(b)
    hypotheses=hypothesis_keys(ha,ra,hb,rb)
    if "relationship_contract" in spec and pinned is None:
        raise ReconciliationError("Pinned manifest must be resolved from trusted input")
    named=[item for item in hypotheses if item["key_name_prior"]]
    # Invalid explicit-looking identities cannot be silently replaced with
    # unrelated unique amounts/statuses. Request stronger linkage evidence.
    identity_invalid=bool(named) and any(item["score"]<0 for item in named)
    plausible=[item for item in hypotheses if item["score"]>=0]
    if pinned is not None:
        plausible=[item for item in plausible if item["column"]==pinned["key"]]
        identity_invalid=False
    elif named:
        plausible=[item for item in plausible if item["key_name_prior"]]
    if identity_invalid or not plausible or (len(plausible)>1 and plausible[0]["score"]==plausible[1]["score"]):
        return {"status":"INSUFFICIENT_KEY_EVIDENCE",
                "hypotheses":hypotheses,"selected_key":None,"discrepancies":None,
                "relationship_contract_sha256":pinned["digest"] if pinned else None,
                "warning":"Cannot infer an unambiguous relationship; no invented join key"}
    key=plausible[0]["column"]
    ea={row[key]:row for row in ra}
    ob={row[key]:row for row in rb}
    fieldset=sorted((set(ha)&set(hb))-{key})
    discrepancies=[]
    for identity in sorted(ea.keys()-ob.keys()):
        discrepancies.append({"kind":"missing_observed","key":identity})
    for identity in sorted(ob.keys()-ea.keys()):
        discrepancies.append({"kind":"unexpected_observed","key":identity})
    for identity in sorted(ea.keys()&ob.keys()):
        for field in fieldset:
            if ea[identity][field]!=ob[identity][field]:
                discrepancies.append({"kind":"field_mismatch","key":identity,
                                      "field":field,
                                      "reference":ea[identity][field],
                                      "observed":ob[identity][field]})
    extra_fields_a=sorted(set(ha)-set(hb))
    extra_fields_b=sorted(set(hb)-set(ha))
    if len(discrepancies)>MAX_DISCREPANCIES:
        raise ReconciliationError("Differences exceed finite review budget")
    return {"status":"DISCREPANCIES_FOUND" if discrepancies or extra_fields_a or extra_fields_b
            else "CONSISTENT",
            "selected_key":key,"hypotheses":hypotheses,
            "relationship_contract_sha256":pinned["digest"] if pinned else None,
            "reference_only_columns":extra_fields_a,"observed_only_columns":extra_fields_b,
            "discrepancies":discrepancies,
            "rows_reference":len(ra),"rows_observed":len(rb),
            "warning":"Inferred relational key is mechanical evidence, not semantic certification"}


def run_reconciliation(db,task: dict,workspace: Path,fixture_root: Path) -> dict:
    tid=task["task_id"]
    try:
        spec=validate_reconciliation(json.loads(task["source_spec"]))
        before_a=safe_fixture(fixture_root,spec["reference"])
        before_b=safe_fixture(fixture_root,spec["observed"])
        from .semantic_contract import load_pinned_relationship
        pinned=load_pinned_relationship(spec,fixture_root)
        plan=propose_reconciliation(spec,before_a,before_b,pinned=pinned)
        # A distinct SQL/CSV implementation independently verifies the full
        # report before the task may be labelled consistent or auditable.
        from .reconciliation_oracle import sql_audit
        oracle=sql_audit(spec,before_a,before_b,plan,pinned=pinned)
        if not oracle["agreement"]:
            raise ReconciliationError("Independent SQL source oracle disagreement")
        if plan["status"]=="INSUFFICIENT_KEY_EVIDENCE":
            finalize(db,task,"UNKNOWN",error_code="JOIN_KEY_AMBIGUOUS")
            return {"task_id":tid,"status":"UNKNOWN","reason":"JOIN_KEY_AMBIGUOUS",
                    "hypotheses":plan["hypotheses"]}
        sha_a=hashlib.sha256(before_a).hexdigest()
        sha_b=hashlib.sha256(before_b).hexdigest()
        def guard_inputs():
            return (hashlib.sha256(safe_fixture(fixture_root,spec["reference"])).hexdigest()==sha_a
                    and hashlib.sha256(safe_fixture(fixture_root,spec["observed"])).hexdigest()==sha_b
                    and load_pinned_relationship(spec,fixture_root)==pinned)
        if plan["status"]=="CONSISTENT":
            # No artifact needed; still revalidate under finalizing write lock.
            def check_only():
                if not guard_inputs(): raise ReconciliationError("Inputs drifted before result commit")
                return None
            committed=finalize(db,task,"VERIFIED",decision="RECORD_SETS_CONSISTENT",
                               artifact_writer=check_only)
        else:
            artifact={
                "task_id":tid,"goal_rev":task["goal_rev"],"source_spec":spec,
                "source_sha256":{"reference":sha_a,"observed":sha_b},
                "proposal":plan,"oracle":"INDEPENDENT_SQL_REFERENCE_COMPARISON",
                "status":"PROPOSAL_NOT_APPROVED"
            }
            data=(json.dumps(artifact,sort_keys=True,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
            def store():
                if not guard_inputs(): raise ReconciliationError("Inputs drifted before result commit")
                if not sql_audit(spec,before_a,before_b,plan,pinned=pinned)["agreement"]:
                    raise ReconciliationError("Source/oracle result mismatch")
                return store_once(workspace,tid,data)
            committed=finalize(db,task,"NEEDS_REVIEW",decision="RECORD_DISCREPANCIES_FOUND",
                               artifact_writer=store)
        if not committed:
            return {"task_id":tid,"status":"STALE_WORKER"}
        actual=db.execute("SELECT state,decision,error_code FROM tasks WHERE task_id=?",(tid,)).fetchone()
        return {"task_id":tid,"status":actual["state"],"decision":actual["decision"],
                "error_code":actual["error_code"],
                "selected_key":plan["selected_key"],
                "discrepancies_count":len(plan["discrepancies"]),
                "business_outcome_verified":False}
    except (ReconciliationError,SourceUnavailable,ValueError,KeyError,TypeError,OSError,ArtifactConflict) as exc:
        finalize(db,task,"UNKNOWN",error_code="RECONCILIATION_UNVERIFIABLE")
        return {"task_id":tid,"status":"UNKNOWN","reason":"RECONCILIATION_UNVERIFIABLE",
                "diagnostic":type(exc).__name__}
