"""P9 reviewer-pinned, scope-bound relationship declaration.

A SHA256 pinned out-of-band can detect modification/substitution; it cannot
prove that the person who chose the key was a domain expert or that the
declaration reflects business reality. Neither a model assertion nor a file's
self-claimed checksum is accepted as a trust anchor.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .source import safe_fixture
from .reconciliation import ReconciliationError

HEX64=re.compile(r"[0-9a-f]{64}\Z")
KEY_NAME=re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
MAX_CONTRACT_BYTES=8192


def contract_binding(value: object, reference: str, observed: str) -> dict:
    if not isinstance(value,dict) or set(value)!={"path","expected_sha256"}:
        raise ReconciliationError("Contract binding requires path and out-of-band digest")
    path=value["path"]
    digest=value["expected_sha256"]
    if (not isinstance(path,str) or not path or len(path)>200
            or path in (reference,observed) or "/" in path or "\\" in path
            or ":" in path or ".." in Path(path).parts or
            not isinstance(digest,str) or not HEX64.fullmatch(digest)):
        raise ReconciliationError("Invalid scoped contract or expected digest")
    return value


def load_pinned_relationship(spec: dict, fixture_root: Path) -> dict | None:
    binding=spec.get("relationship_contract")
    if binding is None:
        return None
    contract_binding(binding,spec["reference"],spec["observed"])
    raw=safe_fixture(fixture_root,binding["path"])
    if len(raw)>MAX_CONTRACT_BYTES or hashlib.sha256(raw).hexdigest()!=binding["expected_sha256"]:
        raise ReconciliationError("Reviewed relationship manifest differs from expected bytes")
    def reject_duplicate_keys(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ReconciliationError("Duplicate contract keys")
            result[k]=v
        return result
    try:
        obj=json.loads(raw.decode("utf-8"),object_pairs_hook=reject_duplicate_keys)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise ReconciliationError("Malformed pinned relationship manifest") from exc
    if not isinstance(obj,dict) or set(obj)!={
        "schema_version","contract_kind","reference","observed","join_key","justification"
    }:
        raise ReconciliationError("Invalid manifest schema")
    if (type(obj["schema_version"]) is not int or obj["schema_version"]!=1
            or obj["contract_kind"]!="record_relationship"
            or obj["reference"]!=spec["reference"] or obj["observed"]!=spec["observed"]
            or not isinstance(obj["join_key"],str) or not KEY_NAME.fullmatch(obj["join_key"])
            or not isinstance(obj["justification"],str) or
            not 12<=len(obj["justification"])<=500):
        raise ReconciliationError("Pinned relationship scope or rationale invalid")
    return {"key":obj["join_key"],"digest":binding["expected_sha256"],
            "provenance":"CALLER_PINNED_DECLARATION_NOT_EXTERNALLY_ATTESTED"}
