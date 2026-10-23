"""Separate read-only postcondition oracle for bounded one-record JSON/CSV.

It does not call the planner, ledger, controller, or any model. Outcome is only
a LOCAL CANDIDATE, never an external effect or approved business result.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re

_MAX_BYTES=64*1024
_FIELD=re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")


def record_from_bytes(kind: str, data: bytes) -> dict[str,str]:
    if not isinstance(data,bytes) or len(data)>_MAX_BYTES:
        raise ValueError("SOURCE_SIZE")
    if kind=="json_keys":
        def unique(pairs):
            d={}
            for k,v in pairs:
                if k in d:
                    raise ValueError("DUPLICATE_KEY")
                d[k]=v
            return d
        obj=json.loads(data.decode("utf-8"),object_pairs_hook=unique)
        if not isinstance(obj,dict):
            raise ValueError("NOT_RECORD")
        record=obj
    elif kind=="csv_columns":
        rows=list(csv.reader(io.StringIO(data.decode("utf-8"),newline=""),strict=True))
        if len(rows)!=2 or not rows[0] or len(rows[0])!=len(rows[1]) or len(set(rows[0]))!=len(rows[0]):
            raise ValueError("NOT_SINGLE_RECORD")
        record=dict(zip(rows[0],rows[1]))
    else:
        raise ValueError("UNREGISTERED_RECORD_FORMAT")
    if (not 1<=len(record)<=16
        or any(not isinstance(k,str) or not _FIELD.fullmatch(k)
               or not isinstance(v,str) or len(v)>256
               for k,v in record.items())):
        raise ValueError("UNSUPPORTED_RECORD_FIELDS")
    return record


def assess_local_record(*, kind: str, original: bytes, current_sha256: str,
                        pinned_sha256: str, target: dict,
                        candidate: bytes | None) -> dict:
    """Fail closed on unavailable or changed sources.

    PRESERVATION_CONFLICT proves that this append-only method cannot satisfy
    the *fixed* target without overwriting an existing field. Only that exact
    verdict permits switching to another previously registered local method.
    """
    fail={"verdict":"UNVERIFIABLE","business_outcome_verified":False,
          "authorizes_mutation":False}
    try:
        if (not isinstance(target,dict) or not 1<=len(target)<=16
            or any(not isinstance(k,str) or not _FIELD.fullmatch(k)
                   or not isinstance(v,str) or len(v)>256 for k,v in target.items())
            or not isinstance(pinned_sha256,str)
            or not re.fullmatch(r"[0-9a-f]{64}",pinned_sha256)
            or current_sha256!=pinned_sha256
            or hashlib.sha256(original).hexdigest()!=pinned_sha256):
            raise ValueError("CONTRACT_OR_SOURCE_DRIFT")
        old=record_from_bytes(kind,original)
        conflicts=[k for k,v in old.items() if k in target and target[k]!=v]
        if conflicts:
            return {**fail,"verdict":"PRESERVATION_CONFLICT",
                    "conflicting_fields":sorted(conflicts),
                    "original_sha256":pinned_sha256}
        if candidate is None:
            return {**fail,"verdict":"NO_CANDIDATE_EVIDENCE"}
        new=record_from_bytes(kind,candidate)
        if (new!=target or any(k not in new or new[k]!=v for k,v in old.items())):
            return {**fail,"verdict":"TARGET_NOT_MET"}
        return {**fail,"verdict":"LOCAL_CANDIDATE_TARGET_MET",
                "candidate_sha256":hashlib.sha256(candidate).hexdigest(),
                "original_sha256":pinned_sha256}
    except (ValueError,TypeError,KeyError,UnicodeError,csv.Error,OverflowError) as exc:
        return {**fail,"reason":str(exc)[:90]}
