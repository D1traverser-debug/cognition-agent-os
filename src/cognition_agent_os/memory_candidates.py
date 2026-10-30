"""Bounded, provenance-pinned *candidate* memory on the EXISTING SQLite ledger.

No new controller, no inferred owner identity, no semantic truth or grant promotion.
Read-side source and dependency validity is recomputed from real bytes. Working
memory stays in the caller's context; episodic actions use the ledger events.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from .ledger import connect, require_initialized_ledger
from .source import safe_fixture

_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST = re.compile(r"[a-z0-9][a-z0-9._:-]{7,95}\Z")
_KINDS = frozenset({"semantic", "procedural"})
_MAX_NODES = 256
_MAX_EDGES = 16
_MAX_QUOTE = 1024
_MAX_NOTE = 2000


class MemoryContractError(ValueError):
    """Invalid scope, missing evidence, revoked grant, or ambiguous lineage."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _tables(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge_candidates (
        memory_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        root_task_id TEXT NOT NULL REFERENCES tasks(task_id),
        kind TEXT NOT NULL CHECK(kind IN ('semantic','procedural')),
        origin TEXT NOT NULL CHECK(origin='untrusted_quoted_source'),
        source_rel TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        quote TEXT NOT NULL,
        interpretation TEXT NOT NULL,
        goal_rev INTEGER NOT NULL,
        grant_rev INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge_candidate_edges (
        child_id TEXT NOT NULL REFERENCES knowledge_candidates(memory_id),
        parent_id TEXT NOT NULL REFERENCES knowledge_candidates(memory_id),
        PRIMARY KEY(child_id,parent_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge_candidate_supersessions (
        old_id TEXT PRIMARY KEY REFERENCES knowledge_candidates(memory_id),
        new_id TEXT NOT NULL REFERENCES knowledge_candidates(memory_id)
    )""")


def record_candidate(db_path: Path, source_root: Path, *,
                     root_task_id: str, request_id: str, kind: str,
                     source_rel: str, expected_sha256: str,
                     quote: str, interpretation: str,
                     parent_ids: tuple[str, ...] = (),
                     supersedes_id: str | None = None) -> dict:
    """Safely capture a cited quote + *unverified* interpretation.

    A caller's claimed 'owner' or 'system' text cannot set trusted origin.
    An eligible grant is needed, even though no candidate is executable.
    Same request ID with different fields fails closed; lost acknowledgements
    replay the identical memory ID. No deletion or publication occurs.
    """
    if (kind not in _KINDS
        or not isinstance(root_task_id, str) or not _ID.fullmatch(root_task_id)
        or not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id)
        or not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256)
        or not isinstance(source_rel, str) or not 1 <= len(source_rel) <= 240
        or not isinstance(quote, str) or not 1 <= len(quote) <= _MAX_QUOTE
        or not isinstance(interpretation, str)
        or not 1 <= len(interpretation) <= _MAX_NOTE
        or not isinstance(parent_ids, tuple) or len(parent_ids) > _MAX_EDGES
        or len(set(parent_ids)) != len(parent_ids)
        or any(not isinstance(x, str) or not _ID.fullmatch(x) for x in parent_ids)
        or (supersedes_id is not None
            and (not isinstance(supersedes_id, str) or not _ID.fullmatch(supersedes_id)))):
        raise MemoryContractError("INVALID_MEMORY_CANDIDATE")
    if supersedes_id is not None and supersedes_id in parent_ids:
        raise MemoryContractError("SUPERSEDED_PARENT_IS_NOT_EVIDENCE")
    require_initialized_ledger(db_path)
    raw = safe_fixture(source_root, source_rel)
    if _sha(raw) != expected_sha256:
        raise MemoryContractError("MEMORY_SOURCE_REVISION_CHANGED")
    try:
        source_text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MemoryContractError("SOURCE_NOT_UTF8") from exc
    if quote not in source_text:
        raise MemoryContractError("QUOTE_NOT_IN_PINNED_SOURCE")
    fields = (root_task_id, kind, source_rel, expected_sha256, quote,
              interpretation)
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            grant = db.execute(
                "SELECT goal_rev,grant_rev,write_allowed FROM authority "
                "WHERE singleton=1").fetchone()
            root = db.execute(
                "SELECT task_id,parent_task,goal_rev,grant_rev,state FROM tasks "
                "WHERE task_id=?", (root_task_id,)).fetchone()
            if (grant is None or grant["write_allowed"] != 1 or root is None
                or root["parent_task"] is not None
                or root["state"] in ("BLOCKED", "REJECTED", "CANCELLED", "DELETED")
                or (root["goal_rev"], root["grant_rev"]) !=
                   (grant["goal_rev"], grant["grant_rev"])):
                raise MemoryContractError("MEMORY_GRANT_OR_ROOT_UNAVAILABLE")
            # The transaction has one writer; verify source again after the
            # lock, not only at preflight. Remote mirrors remain out of scope.
            second = safe_fixture(source_root, source_rel)
            if _sha(second) != expected_sha256 or quote not in second.decode("utf-8"):
                raise MemoryContractError("MEMORY_SOURCE_CHANGED_DURING_ADMISSION")
            _tables(db)
            existing = db.execute(
                "SELECT * FROM knowledge_candidates WHERE request_id=?",
                (request_id,)).fetchone()
            if existing is not None:
                edges = tuple(row["parent_id"] for row in db.execute(
                    "SELECT parent_id FROM knowledge_candidate_edges "
                    "WHERE child_id=? ORDER BY parent_id", (existing["memory_id"],)))
                prior_supersedes = db.execute(
                    "SELECT old_id FROM knowledge_candidate_supersessions "
                    "WHERE new_id=?", (existing["memory_id"],)).fetchone()
                if (tuple(existing[f] for f in
                    ("root_task_id", "kind", "source_rel", "source_sha256",
                     "quote", "interpretation")) != fields
                    or edges != tuple(sorted(parent_ids))
                    or (prior_supersedes["old_id"] if prior_supersedes else None)
                    != supersedes_id):
                    raise MemoryContractError("MEMORY_IDEMPOTENCY_CONFLICT")
                db.commit()
                return {"status": "UNVERIFIED_CANDIDATE_REPLAY",
                        "memory_id": existing["memory_id"],
                        "authorizes_action": False}
            for parent_id in (*parent_ids,
                              *((supersedes_id,) if supersedes_id else ())):
                parent = db.execute(
                    "SELECT root_task_id FROM knowledge_candidates WHERE memory_id=?",
                    (parent_id,)).fetchone()
                if parent is None or parent["root_task_id"] != root_task_id:
                    raise MemoryContractError("INVALID_MEMORY_PARENT_SCOPE")
                if db.execute(
                    "SELECT 1 FROM knowledge_candidate_supersessions "
                    "WHERE old_id=?", (parent_id,)).fetchone() is not None:
                    raise MemoryContractError("MEMORY_PARENT_ALREADY_SUPERSEDED")
            memory_id = uuid.uuid4().hex
            db.execute("""INSERT INTO knowledge_candidates
                (memory_id,request_id,root_task_id,kind,origin,source_rel,
                 source_sha256,quote,interpretation,goal_rev,grant_rev)
                VALUES(?,?,?,?,'untrusted_quoted_source',?,?,?,?,?,?)""",
                (memory_id, request_id, root_task_id, kind, source_rel,
                 expected_sha256, quote, interpretation,
                 grant["goal_rev"], grant["grant_rev"]))
            for parent_id in parent_ids:
                db.execute("INSERT INTO knowledge_candidate_edges VALUES(?,?)",
                           (memory_id, parent_id))
            if supersedes_id:
                db.execute("INSERT INTO knowledge_candidate_supersessions "
                           "VALUES(?,?)", (supersedes_id, memory_id))
            db.commit()
            return {"status": "UNVERIFIED_CANDIDATE_STORED",
                    "memory_id": memory_id, "authorizes_action": False}
        except BaseException:
            db.rollback()
            raise


def inspect_candidates(db_path: Path, source_root: Path, *,
                       root_task_id: str,
                       after_memory_id: str | None = None,
                       limit: int = 50) -> dict:
    """Read-only keyset page with complete bounded dependency ancestry.

    Every returned candidate must be checked against its *full* source and
    ancestors, including those outside this page. Never infer verified truth.
    Individual pages are consistent SQLite snapshots, not a frozen snapshot
    across separate client requests.
    """
    if (not isinstance(root_task_id, str) or not _ID.fullmatch(root_task_id)
        or (after_memory_id is not None and
            (not isinstance(after_memory_id, str)
             or not _ID.fullmatch(after_memory_id)))
        or type(limit) is not int or not 1 <= limit <= 50):
        raise MemoryContractError("INVALID_MEMORY_CURSOR_OR_LIMIT")
    require_initialized_ledger(db_path)
    uri = db_path.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='knowledge_candidates' "
            "AND type='table'").fetchone()
        if not exists:
            return {"status": "NO_MEMORY_CANDIDATES", "items": [],
                    "any_semantic_truth_verified": False}
        authority = db.execute(
            "SELECT goal_rev,grant_rev,write_allowed FROM authority "
            "WHERE singleton=1").fetchone()
        root = db.execute(
            "SELECT goal_rev,grant_rev,state FROM tasks "
            "WHERE task_id=? AND parent_task IS NULL", (root_task_id,)).fetchone()
        if authority is None or root is None:
            return {"status": "MEMORY_ROOT_UNVERIFIABLE", "items": [],
                    "any_semantic_truth_verified": False}
        scope_current = (authority["write_allowed"] == 1
                         and root["state"] not in
                             ("BLOCKED", "REJECTED", "CANCELLED", "DELETED")
                         and (authority["goal_rev"], authority["grant_rev"])
                             == (root["goal_rev"], root["grant_rev"]))
        if after_memory_id is not None and db.execute(
            "SELECT 1 FROM knowledge_candidates WHERE root_task_id=? "
            "AND memory_id=?", (root_task_id, after_memory_id)
        ).fetchone() is None:
            raise MemoryContractError("CURSOR_NOT_IN_OWNER_ROOT")
        q = ("SELECT * FROM knowledge_candidates WHERE root_task_id=? "
             + ("AND memory_id>? " if after_memory_id is not None else "")
             + "ORDER BY memory_id LIMIT ?")
        params = ((root_task_id, after_memory_id, limit + 1)
                  if after_memory_id is not None else (root_task_id, limit + 1))
        observed = db.execute(q, params).fetchall()
        more = len(observed) > limit
        page = observed[:limit]
        if not page:
            return {"status": "READ_ONLY_CANDIDATES", "items": [],
                    "has_more": False, "next_after_memory_id": None,
                    "any_semantic_truth_verified": False,
                    "cross_page_snapshot_pinned": False}
        all_rows = {row["memory_id"]: row for row in page}
        parents = {key: [] for key in all_rows}
        frontier = list(all_rows)
        # Bounded exact ancestor closure: do not validate a dependent method
        # while silently omitting its source knowledge on another page.
        while frontier:
            if len(all_rows) > _MAX_NODES:
                return {"status": "MEMORY_LINEAGE_TOO_LARGE", "items": [],
                        "any_semantic_truth_verified": False}
            next_frontier = set()
            for i in range(0, len(frontier), 80):
                subset = frontier[i:i + 80]
                placeholders = ",".join("?" for _ in subset)
                query = ("SELECT child_id,parent_id FROM knowledge_candidate_edges "
                         "WHERE child_id IN (" + placeholders + ")")
                for edge in db.execute(query, subset):
                    child, parent = edge["child_id"], edge["parent_id"]
                    parents[child].append(parent)
                    if parent not in all_rows:
                        next_frontier.add(parent)
            if not next_frontier:
                break
            if len(all_rows) + len(next_frontier) > _MAX_NODES:
                return {"status": "MEMORY_LINEAGE_TOO_LARGE", "items": [],
                        "any_semantic_truth_verified": False}
            newly = []
            sorted_ids = sorted(next_frontier)
            for i in range(0, len(sorted_ids), 80):
                ids = sorted_ids[i:i + 80]
                placeholders = ",".join("?" for _ in ids)
                query = ("SELECT * FROM knowledge_candidates WHERE memory_id IN ("
                         + placeholders + ")")
                newly.extend(db.execute(query, ids))
            if len(newly) != len(sorted_ids) or any(
                row["root_task_id"] != root_task_id for row in newly
            ):
                return {"status": "MEMORY_LINEAGE_CORRUPT", "items": [],
                        "any_semantic_truth_verified": False}
            frontier = [row["memory_id"] for row in newly]
            for row in newly:
                all_rows[row["memory_id"]] = row
                parents[row["memory_id"]] = []

        all_ids = tuple(sorted(all_rows))
        superseded = set()
        for i in range(0, len(all_ids), 80):
            ids = all_ids[i:i + 80]
            placeholders = ",".join("?" for _ in ids)
            query = ("SELECT old_id,new_id FROM knowledge_candidate_supersessions "
                     "WHERE old_id IN (" + placeholders + ")")
            for link in db.execute(query, ids):
                referenced = db.execute(
                    "SELECT root_task_id FROM knowledge_candidates "
                    "WHERE memory_id=?", (link["new_id"],)).fetchone()
                if referenced is None or referenced["root_task_id"] != root_task_id:
                    return {"status": "MEMORY_LINEAGE_CORRUPT", "items": [],
                            "any_semantic_truth_verified": False}
                superseded.add(link["old_id"])

        source_state: dict[tuple[str, str], str | None] = {}
        for row in all_rows.values():
            identity = (row["source_rel"], row["source_sha256"])
            if identity not in source_state:
                try:
                    raw = safe_fixture(source_root, identity[0])
                    source_state[identity] = (
                        raw.decode("utf-8") if _sha(raw) == identity[1] else None)
                except (OSError, ValueError, UnicodeDecodeError):
                    source_state[identity] = None
        statuses = {}
        for key, row in all_rows.items():
            source = source_state[(row["source_rel"], row["source_sha256"])]
            statuses[key] = (
                "SUPERSEDED" if key in superseded else
                "SOURCE_CHANGED_OR_UNAVAILABLE"
                if source is None or row["quote"] not in source else
                "GRANT_OR_GOAL_REVISION_STALE"
                if not scope_current or
                   (row["goal_rev"], row["grant_rev"]) !=
                       (root["goal_rev"], root["grant_rev"]) else
                "CANDIDATE_UNVERIFIED")
        # Kahn evaluation: a cycle (including forged cross-edge) must not
        # become a false clean candidate simply because every source exists.
        remaining = {key: len(deps) for key, deps in parents.items()}
        children = {key: [] for key in all_rows}
        for child, deps in parents.items():
            for parent in deps:
                if parent not in children:
                    return {"status": "MEMORY_LINEAGE_CORRUPT", "items": [],
                            "any_semantic_truth_verified": False}
                children[parent].append(child)
        ready = [key for key, count in remaining.items() if count == 0]
        visited = 0
        while ready:
            parent = ready.pop()
            visited += 1
            for child in children[parent]:
                if (statuses[child] == "CANDIDATE_UNVERIFIED"
                    and statuses[parent] != "CANDIDATE_UNVERIFIED"):
                    statuses[child] = "DEPENDENCY_INVALIDATED"
                remaining[child] -= 1
                if remaining[child] == 0:
                    ready.append(child)
        if visited != len(all_rows):
            return {"status": "MEMORY_LINEAGE_CORRUPT", "items": [],
                    "any_semantic_truth_verified": False}
        items = []
        for row in page:
            key = row["memory_id"]
            valid = statuses[key] == "CANDIDATE_UNVERIFIED"
            items.append({
                "memory_id": key, "kind": row["kind"],
                "source_rel": row["source_rel"],
                "source_sha256": row["source_sha256"],
                "status": statuses[key], "origin": row["origin"],
                # Stale / superseded text cannot be silently re-injected.
                "quote": row["quote"] if valid else None,
                "interpretation": row["interpretation"] if valid else None,
                "untrusted_data": True,
                "authorizes_action": False
            })
        return {"status": "READ_ONLY_CANDIDATES",
                "items": items, "has_more": more,
                "next_after_memory_id": page[-1]["memory_id"] if more else None,
                "any_semantic_truth_verified": False,
                "cross_page_snapshot_pinned": False}
