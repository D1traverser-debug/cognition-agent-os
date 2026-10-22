"""P35: bounded read-only evidence decision from a *real* P34 child.

Review work is a separate explicitly queued task in the existing task ledger.
It never grants a route or starts production work. External source statements
are untrusted even if content-addressed. No network or model API is invoked.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .ledger import finalize_observed
from .runner import store_once, ArtifactConflict
from .research_gap import audit_gap
from .source import safe_fixture, github_public_snapshot, SourceUnavailable

def _evidence(root: Path, contract: dict, goal: str, routes: set[str]):
    if not isinstance(contract, dict) or set(contract) not in ({"path", "sha256", "source_id", "publisher_id"}, {"kind", "repo", "path", "ref", "sha256", "source_id", "publisher_id"}):
        raise ValueError("BAD_CONTRACT")
    name = contract["path"]
    if (not isinstance(name, str) or not name.endswith(".json") or "\\" in name
        or name.startswith(".") or ("kind" not in contract and "/" in name)
        or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("BAD_PATH")
    # Reuse existing source adapters; owner specifies immutable source IDs.
    if contract.get("kind") == "github":
        if not isinstance(contract.get("repo"),str) or not isinstance(contract.get("ref"),str):
            raise ValueError("BAD_GITHUB_CONTRACT")
        try:
            raw = github_public_snapshot(contract["repo"], name, contract["ref"])
        except (SourceUnavailable, OSError) as exc:
            raise ValueError("BAD_GITHUB_SOURCE") from exc
    else:
        if root.is_symlink() or (root / name).is_symlink():
            raise ValueError("BAD_FILE")
        try:
            raw = safe_fixture(root, name)
        except (SourceUnavailable, OSError) as exc:
            raise ValueError("BAD_FILE") from exc
    if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != contract["sha256"]:
        raise ValueError("BAD_HASH")
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"source_id", "publisher_id", "goal_key", "assertions"}:
        raise ValueError("BAD_SCHEMA")
    if data["source_id"] != contract["source_id"] or data["publisher_id"] != contract["publisher_id"] or data["goal_key"] != goal:
        raise ValueError("BAD_IDENTITY")
    statements = data["assertions"]
    if not isinstance(statements, list) or len(statements) != 2:
        raise ValueError("BAD_COVERAGE")
    result = {}
    references = set()
    for s in statements:
        if not isinstance(s, dict) or set(s) != {"route", "stance", "evidence_ref"}:
            raise ValueError("BAD_STATEMENT")
        if s["route"] not in routes or s["route"] in result or s["stance"] not in {"supports", "refutes", "inconclusive"}:
            raise ValueError("BAD_STANCE")
        if not isinstance(s["evidence_ref"], str) or not 1 <= len(s["evidence_ref"]) <= 128:
            raise ValueError("BAD_REFERENCE")
        result[s["route"]] = s["stance"]
        references.add(s["evidence_ref"])
    if set(result) != routes:
        raise ValueError("INCOMPLETE")
    return result, references

def assess(db_path: Path, workspace: Path, fixtures: Path, spec: dict, assessment_id: str) -> dict:
    from contextlib import closing
    import sqlite3
    tid = spec.get("research_task_id")
    sources = spec.get("sources")
    if not isinstance(tid, str) or len(tid) != 32 or any(c not in "0123456789abcdef" for c in tid):
        raise ValueError("BAD_TASK")
    if not isinstance(sources, list) or len(sources) != 2 or not all(isinstance(s, dict) for s in sources):
        raise ValueError("BAD_SOURCES")
    if sources[0].get("source_id") == sources[1].get("source_id") or sources[0].get("publisher_id") == sources[1].get("publisher_id"):
        raise ValueError("INDEPENDENCE_UNKNOWN")
    if not db_path.is_file() or db_path.is_symlink():
        raise ValueError("NO_LEDGER")
    with closing(sqlite3.connect(db_path.resolve(strict=True).as_uri() + "?mode=ro", uri=True)) as check:
        check.row_factory = sqlite3.Row
        assessment=check.execute("SELECT * FROM tasks WHERE task_id=?", (assessment_id,)).fetchone()
        if (assessment is None or assessment["parent_task"]!=tid
            or json.loads(assessment["source_spec"])!=spec):
            raise ValueError("ASSESSMENT_LINEAGE_INVALID")
        child = check.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone()
        if child is None or child["state"] != "NEEDS_REVIEW" or not child["parent_task"]:
            raise ValueError("UNREVIEWABLE")
        parent = check.execute("SELECT * FROM tasks WHERE task_id=?", (child["parent_task"],)).fetchone()
        if not parent or parent["state"] != "RESEARCH_NEEDED" or parent["goal_rev"] != child["goal_rev"] or parent["grant_rev"] != child["grant_rev"]:
            raise ValueError("STALE_PARENT")
        if (assessment["goal_rev"]!=child["goal_rev"]
            or assessment["grant_rev"]!=child["grant_rev"]):
            raise ValueError("ASSESSMENT_AUTHORITY_STALE")
        orig = json.loads(child["source_spec"])
        if orig.get("kind") != "research_gap":
            raise ValueError("BAD_PARENT")
        audit = audit_gap(db_path, fixtures, workspace, child["parent_task"], tid)
        if audit.get("status") != "PLAN_MECHANICALLY_VALID":
            raise ValueError("PROVENANCE_NOT_VERIFIED")
        if orig.get("research_sources") != sources:
            raise ValueError("RESEARCH_SOURCES_NOT_AUTHORIZED")
        receipts=check.execute("SELECT details FROM events WHERE task_id=? AND kind='RESEARCH_REVIEW_ENQUEUED'",(tid,)).fetchall()
        if len(receipts)!=1:
            raise ValueError("REVIEW_ADMISSION_NOT_PROVEN")
        receipt=json.loads(receipts[0]["details"])
        if receipt!={"source_hashes":[s["sha256"] for s in sources],
                     "production_effect_authorized":False}:
            raise ValueError("REVIEW_RECEIPT_MISMATCH")
        siblings=check.execute("SELECT COUNT(*) FROM tasks WHERE parent_task=?",(tid,)).fetchone()[0]
        if siblings!=1:
            raise ValueError("DUPLICATE_REVIEW_NOT_ALLOWED")
        routes = set(orig["routes"])
        if len(routes) != 2:
            raise ValueError("BAD_ROUTES")
        (a, refs_a), (b, refs_b) = (_evidence(fixtures, src, orig["goal_key"], routes) for src in sources)
        if (sources[0].get("kind") == "github" and sources[1].get("kind") == "github"
            and sources[0]["repo"].lower() == sources[1]["repo"].lower()):
            reason, candidate = "SAME_REPOSITORY_NOT_INDEPENDENT", None
        elif refs_a & refs_b:
            reason, candidate = "SHARED_UNDERLYING_EVIDENCE", None
        elif a != b:
            reason, candidate = "CONFLICTING_SOURCE_CLAIMS", None
        elif sorted(a.values()) != ["refutes", "supports"]:
            reason, candidate = "INSUFFICIENT_CAUSAL_DISCRIMINATION", None
        else:
            reason = "CONSENSUS_PENDING_EXTERNAL_SEMANTIC_REVIEW"
            candidate = next(r for r in sorted(routes) if a[r] == "supports")
        return {"status": "RESEARCH_EVIDENCE_NOT_APPROVED", "reason": reason,
                "candidate_route_for_review": candidate,
                "research_task_id": tid, "goal_key": orig["goal_key"],
                "source_hashes": [s["sha256"] for s in sources],
                "source_independence_verified": False,
                "business_outcome_verified": False, "production_effect_authorized": False}

def run_assessment(db, task, db_path: Path, workspace: Path, fixtures: Path):
    try:
        spec = json.loads(task["source_spec"])
        first = assess(db_path, workspace, fixtures, spec, task["task_id"])
        raw = (json.dumps(first, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        def write():
            second = assess(db_path, workspace, fixtures, spec, task["task_id"])
            if second != first:
                raise ValueError("EVIDENCE_CHANGED")
            return store_once(workspace, task["task_id"], raw)
        result = finalize_observed(db, task, "NEEDS_REVIEW",
                                   decision="RESEARCH_NOT_SEMANTICALLY_APPROVED", artifact_writer=write)
        return {**result, "business_outcome_verified": False,
                "production_effect_authorized": False}
    except (ValueError, OSError, TypeError, KeyError, ArtifactConflict):
        return finalize_observed(db, task, "UNKNOWN", error_code="RESEARCH_ASSESSMENT_UNVERIFIABLE")

def audit_assessment(db_path: Path, workspace: Path, fixtures: Path, task_id: str) -> dict:
    """Independent native conformance replays the original pinned evidence.

    Checks the actual committed candidate bytes; no source's claims can grant
    authority. A changed evidence source invalidates the prior review state.
    """
    import sqlite3
    from contextlib import closing
    bad = {"status": "UNVERIFIABLE", "reason": "ASSESSMENT_UNVERIFIABLE"}
    if not isinstance(task_id, str) or len(task_id) != 32 or any(x not in "0123456789abcdef" for x in task_id):
        return bad
    if not db_path.is_file() or db_path.is_symlink() or workspace.is_symlink():
        return bad
    try:
        with closing(sqlite3.connect(db_path.resolve(strict=True).as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["state"] != "NEEDS_REVIEW":
                return bad
            spec = json.loads(row["source_spec"])
            if spec.get("kind") != "research_assessment":
                return bad
            from .runner import verify_artifact
            if not verify_artifact(workspace, dict(row)):
                return bad
            expected = (json.dumps(assess(db_path, workspace, fixtures, spec, task_id),
                                   ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
            path = workspace / "artifacts" / (task_id + ".json")
            if path.is_symlink() or path.read_bytes() != expected:
                return bad
            return {"status": "ASSESSMENT_MECHANICALLY_VALID",
                    "business_outcome_verified": False,
                    "production_effect_authorized": False}
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        return bad
