"""Resumable interactive cognition over the existing native goal/event ledger.

The client supplies hypotheses, alternatives and research, never truth or grants.
This module supplies versioned dependencies, stale-evidence rejection and bounded
readback. It neither runs a model nor intercepts another provider's tools.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re

from .ledger import connect_existing, readonly_snapshot, event
from .native_decision import _registered_native_contract_matches
from .source import safe_fixture, SourceUnavailable

KINDS = frozenset({"obligation", "hypothesis", "source", "option", "decision",
                   "observation", "method"})
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}\Z")
MAX_NODES = 512
MAX_EVENTS = 4096


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def _identity(db, root_id: str, *, write=False):
    row = db.execute("SELECT * FROM tasks WHERE task_id=?", (root_id,)).fetchone()
    if row is None or row["parent_task"] is not None:
        raise ValueError("COGNITION_ROOT_NOT_FOUND")
    spec = json.loads(row["source_spec"])
    if not _registered_native_contract_matches(db, root_id, spec):
        raise ValueError("COGNITION_ORIGINAL_GOAL_UNVERIFIABLE")
    auth = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
    current = bool(auth and auth["write_allowed"] == 1
                   and (row["goal_rev"], row["grant_rev"])
                   == (auth["goal_rev"], auth["grant_rev"])
                   and row["state"] == "DECOMPOSED")
    if write and not current:
        raise PermissionError("COGNITION_GRANT_REVOKED")
    return spec, current


def _events(db, root_id):
    rows = db.execute("SELECT event_id,kind,details FROM events WHERE task_id=? "
                      "AND kind LIKE 'COGNITION_%' ORDER BY event_id LIMIT ?",
                      (root_id, MAX_EVENTS + 1)).fetchall()
    if len(rows) > MAX_EVENTS:
        raise ValueError("COGNITION_HISTORY_LIMIT_EXPORT_REQUIRED")
    return [{"event_id": r[0], "kind": r[1], "data": json.loads(r[2])} for r in rows]


def _source_check(sources: Path, ref: dict):
    if (not isinstance(ref, dict) or set(ref) != {"path", "sha256", "quote"}
            or not all(isinstance(v, str) for v in ref.values())
            or not 1 <= len(ref["quote"]) <= 4000):
        raise ValueError("COGNITION_INVALID_SOURCE_REF")
    raw = safe_fixture(sources, ref["path"])
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("COGNITION_SOURCE_CHANGED")
    if ref["quote"] not in raw.decode("utf-8"):
        raise ValueError("COGNITION_QUOTE_NOT_FOUND")


def _project(db, sources: Path, root_id: str):
    spec, current = _identity(db, root_id)
    history = _events(db, root_id)
    amendments = [e for e in history if e["kind"] == "COGNITION_AMENDMENT"]
    revision = len(amendments)
    nodes = {}
    invalid = {}
    for e in history:
        data = e["data"]
        if e["kind"] == "COGNITION_NODE":
            node = {**data["node"], "event_id": e["event_id"], "status": "CURRENT"}
            if node["id"] in nodes:
                raise ValueError("COGNITION_DUPLICATE_NODE")
            nodes[node["id"]] = node
            if node["supersedes"]:
                invalid[node["supersedes"]] = "SUPERSEDED"
        elif e["kind"] == "COGNITION_REOPEN":
            invalid[data["node_id"]] = "REOPENED"
    for node_id, node in nodes.items():
        if node["goal_revision"] != revision:
            invalid.setdefault(node_id, "GOAL_AMENDED")
        try:
            for ref in node["source_refs"]:
                _source_check(sources, ref)
        except (OSError, ValueError, UnicodeError, SourceUnavailable):
            invalid.setdefault(node_id, "SOURCE_UNAVAILABLE_OR_CHANGED")
        for parent in node["depends_on"]:
            if parent not in nodes or nodes[parent]["event_id"] >= node["event_id"]:
                raise ValueError("COGNITION_BROKEN_DEPENDENCY")
            if parent in invalid:
                invalid.setdefault(node_id, "DEPENDENCY_INVALIDATED")
    # Supersession may be recorded after descendants: propagate to a fixed point.
    for _ in range(len(nodes)):
        prior = len(invalid)
        for node_id, node in nodes.items():
            if any(parent in invalid for parent in node["depends_on"]):
                invalid.setdefault(node_id, "DEPENDENCY_INVALIDATED")
        if len(invalid) == prior:
            break
    for node_id, node in nodes.items():
        node["status"] = invalid.get(node_id, "CURRENT")
        node["semantic_truth_verified"] = False
    goal = {"original": spec["goal"],
            "amendments": [e["data"]["text"] for e in amendments]}
    result = {"root_task_id": root_id, "goal": goal, "goal_revision": revision,
              "goal_sha256": digest(goal), "grant_current": current,
              "nodes": list(nodes.values()),
              "reopen": [{"node_id": key, "reason": value}
                         for key, value in invalid.items()],
              "authorizes_external_tools": False, "owner_outcome_verified": False}
    # A full content/version fingerprint, including amendments/reopens, not a summary.
    result["revision_token"] = digest({"history": history, "view": result})
    return result


def inspect_session(db_path: Path, sources: Path, root_id: str, *,
                    after_event_id: int = 0, limit: int = 32) -> dict:
    if type(after_event_id) is not int or after_event_id < 0 or type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError("INVALID_COGNITION_PAGE")
    with readonly_snapshot(db_path) as db:
        view = _project(db, sources, root_id)
    remaining = [n for n in view["nodes"] if n["event_id"] > after_event_id]
    page = remaining[:limit]
    visible = {n["id"] for n in page}
    return {**view, "nodes": page, "node_count": len(view["nodes"]),
            "reopen": [r for r in view["reopen"] if r["node_id"] in visible],
            "reopen_count": len(view["reopen"]),
            "next_after_event_id": page[-1]["event_id"] if len(remaining) > len(page) else None}


def _append(db_path, sources, root_id, request_id, expected_revision, kind, data):
    if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
        raise ValueError("COGNITION_REQUEST_ID_INVALID")
    payload = {**data, "request_id": request_id}
    with closing(connect_existing(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _identity(db, root_id, write=True)
            history = _events(db, root_id)
            matches = [e for e in history if e["data"].get("request_id") == request_id]
            if matches:
                if len(matches) != 1 or matches[0]["kind"] != kind or matches[0]["data"] != payload:
                    raise ValueError("COGNITION_REQUEST_ID_CONFLICT")
                db.commit()
                return {"status": "REPLAYED", "event_id": matches[0]["event_id"]}
            view = _project(db, sources, root_id)
            if expected_revision != view["revision_token"]:
                raise ValueError("COGNITION_STALE_REVISION")
            if len(history) >= MAX_EVENTS:
                raise ValueError("COGNITION_HISTORY_LIMIT_EXPORT_REQUIRED")
            if kind == "COGNITION_NODE":
                _validate_node(payload["node"], view, sources)
            elif kind == "COGNITION_REOPEN":
                if payload["node_id"] not in {n["id"] for n in view["nodes"]}:
                    raise ValueError("COGNITION_UNKNOWN_NODE")
            event(db, root_id, kind, payload)
            event_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()
            return {"status": "RECORDED", "event_id": event_id}
        except BaseException:
            db.rollback()
            raise


def _validate_node(node, view, sources):
    required = {"id", "kind", "text", "depends_on", "source_refs", "supersedes", "goal_revision"}
    if (not isinstance(node, dict) or not required <= set(node)
            or set(node) - required - {"action_spec"}
            or not isinstance(node["id"], str) or not _ID.fullmatch(node["id"])
            or not isinstance(node["kind"], str) or node["kind"] not in KINDS
            or not isinstance(node["text"], str) or not 1 <= len(node["text"]) <= 12000
            or type(node["goal_revision"]) is not int
            or node["goal_revision"] != view["goal_revision"]):
        raise ValueError("COGNITION_INVALID_NODE")
    if len(json.dumps(node, ensure_ascii=False)) > 32000:
        raise ValueError("COGNITION_NODE_TOO_LARGE")
    digest(node)  # Action specs must be finite JSON before persistence.
    by_id = {n["id"]: n for n in view["nodes"]}
    if node["id"] in by_id or len(by_id) >= MAX_NODES:
        raise ValueError("COGNITION_DUPLICATE_NODE_OR_LIMIT")
    deps = node["depends_on"]
    if (not isinstance(deps, list) or len(deps) > 32
            or any(not isinstance(p, str) for p in deps) or len(set(deps)) != len(deps)
            or any(p not in by_id or by_id[p]["status"] != "CURRENT" for p in deps)):
        raise ValueError("COGNITION_DEPENDENCY_NOT_CURRENT")
    if (node["supersedes"] is not None
            and (not isinstance(node["supersedes"], str)
                 or node["supersedes"] not in by_id or node["supersedes"] in deps)):
        raise ValueError("COGNITION_INVALID_SUPERSESSION")
    refs = node["source_refs"]
    if not isinstance(refs, list) or len(refs) > 16:
        raise ValueError("COGNITION_INVALID_SOURCE_REFS")
    for ref in refs:
        _source_check(sources, ref)
    if node["kind"] == "source" and not refs:
        raise ValueError("COGNITION_SOURCE_BYTES_REQUIRED")
    if node["kind"] == "obligation":
        originals = [view["goal"]["original"], *view["goal"]["amendments"]]
        if not any(node["text"] in text for text in originals):
            raise ValueError("COGNITION_OBLIGATION_MUST_QUOTE_OWNER")
    if node["kind"] == "decision":
        # Structural minimum, explicitly NOT evidence the comparison is correct.
        if len([p for p in deps if by_id[p]["kind"] == "option"]) < 2:
            raise ValueError("COGNITION_DECISION_NEEDS_COMPETING_OPTIONS")
        if node.get("action_spec") is not None and not isinstance(node["action_spec"], dict):
            raise ValueError("COGNITION_INVALID_DECISION_ACTION")
    elif "action_spec" in node:
        raise ValueError("COGNITION_ACTION_BELONGS_TO_DECISION")


def record_node(db_path: Path, sources: Path, root_id: str, node: dict, *,
                request_id: str, expected_revision: str) -> dict:
    return _append(db_path, sources, root_id, request_id, expected_revision,
                   "COGNITION_NODE", {"node": node})


def amend_goal(db_path: Path, sources: Path, root_id: str, text: str, *,
               request_id: str, expected_revision: str) -> dict:
    """Preserve a supplied correction; client attribution is not authentication.

    All derived nodes and effect contracts become stale. Original owner bytes
    survive; an amendment cannot enlarge any local or external grant.
    """
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 32000:
        raise ValueError("COGNITION_INVALID_AMENDMENT")
    return _append(db_path, sources, root_id, request_id, expected_revision,
                   "COGNITION_AMENDMENT", {"text": text,
                   "origin": "client_supplied_correction_not_authenticated_owner"})


def reopen_node(db_path: Path, sources: Path, root_id: str, node_id: str,
                reason: str, *, request_id: str, expected_revision: str) -> dict:
    if not isinstance(reason, str) or not 1 <= len(reason) <= 4000:
        raise ValueError("COGNITION_REOPEN_REASON_REQUIRED")
    return _append(db_path, sources, root_id, request_id, expected_revision,
                   "COGNITION_REOPEN", {"node_id": node_id, "reason": reason})
