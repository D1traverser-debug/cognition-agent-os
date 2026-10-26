"""Optional local MCP adapter for the EXISTING cognition-agent-os ledger/Host.

MCP provides an agent with typed tools, not a second scheduler or authority.
The stdio process is local only. It does not deploy an HTTPS endpoint, confer a
ChatGPT account connection, install models, or certify owner-level outcomes.
The official MCP SDK is imported only when the optional local adapter is used.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .host import _admit_existing_ledger, run_tick
from .ledger import require_initialized_ledger
from .native_decision import (
    admit_native_decision, capability_catalog, inspect_native_goal,
    record_native_hypothesis, register_native_goal,
)


def _read_only_ledger(db_path: Path) -> sqlite3.Connection:
    """A model-visible read must never create or silently revive the ledger."""
    require_initialized_ledger(db_path)
    uri = db_path.resolve(strict=True).as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def build_mcp_server(db_path: Path, workspace: Path, fixtures: Path, *,
                     allow_host_tick: bool = False):
    """Expose only the existing, audited native-goal contract as MCP tools."""
    from mcp.server import MCPServer

    _admit_existing_ledger(db_path)
    if (not workspace.is_dir() or workspace.is_symlink()
        or not fixtures.is_dir() or fixtures.is_symlink()):
        raise ValueError("LOCAL_MCP_PATHS_MUST_ALREADY_EXIST")
    mcp = MCPServer("cognition-agent-os-local")

    @mcp.tool()
    def native_goal_create(owner_goal: str) -> dict:
        """Register exact original owner goal in existing granted SQLite ledger.

        State creation needs an already-current local grant; this does not grant
        external write rights, install a model, or claim the goal is finished.
        """
        # MCP callers cannot upgrade a goal into external public disclosure.
        # The native trusted owner interface can separately grant that scope.
        root = register_native_goal(
            db_path, owner_goal, allow_public_discovery=False)
        return {"status": "NATIVE_GOAL_REGISTERED", "root_task_id": root,
                "owner_outcome_verified": False}

    @mcp.tool()
    def native_goal_list() -> dict:
        """Discover existing original native goals for cold-process continuation.

        This is read-only and never chooses the newest task on the user's
        behalf. Foreign/invalid roots are not reinterpreted as native goals.
        """
        with closing(_read_only_ledger(db_path)) as db:
            rows = db.execute(
                "SELECT task_id FROM tasks WHERE parent_task IS NULL "
                "ORDER BY created_at DESC,task_id DESC LIMIT 51").fetchall()
        recovered = []
        for row in rows[:50]:
            state = inspect_native_goal(
                db_path, workspace, fixtures, row["task_id"])
            if (state.get("status") == "NATIVE_GOAL_UNVERIFIABLE"
                or not isinstance(state.get("original_goal"), str)):
                continue
            recovered.append({
                "root_task_id": row["task_id"],
                "original_goal": state["original_goal"],
                "status": state["status"],
                "decision_count": state["decision_count"],
                "owner_outcome_verified": False,
            })
        return {"status": "NATIVE_GOAL_INVENTORY",
                "goals": recovered, "truncated": len(rows) > 50,
                "ambiguous": len(recovered) > 1,
                "selected_root_task_id": None,
                "owner_outcome_verified": False}

    @mcp.tool()
    def native_goal_inspect(root_task_id: str) -> dict:
        """Read original owner goal, prior independently audited work and CAS state."""
        return inspect_native_goal(db_path, workspace, fixtures, root_task_id)

    @mcp.tool()
    def native_capabilities(root_task_id: str) -> dict:
        """Discover live registered tools, current sources, and bounded effects."""
        observed = inspect_native_goal(
            db_path, workspace, fixtures, root_task_id)
        if observed["status"] == "NATIVE_GOAL_UNVERIFIABLE":
            return observed
        with closing(_read_only_ledger(db_path)) as db:
            row = db.execute(
                "SELECT source_spec FROM tasks WHERE task_id=? AND parent_task IS NULL",
                (root_task_id,)).fetchone()
            if row is None:
                return {"status": "NATIVE_GOAL_UNVERIFIABLE",
                        "owner_outcome_verified": False}
            spec = json.loads(row["source_spec"])
        return capability_catalog(
            fixtures, allow_public_discovery=spec["allow_public_discovery"])

    @mcp.tool()
    def native_hypothesis_record(root_task_id: str, origin: str, idea: str,
                                 observation_sha256: str) -> dict:
        """Record a user/agent method idea as an untrusted, non-authorizing hypothesis."""
        return record_native_hypothesis(
            db_path, workspace, fixtures, root_task_id,
            origin=origin, idea=idea,
            observation_sha256=observation_sha256)

    @mcp.tool()
    def native_decision_admit(root_task_id: str, proposal: dict) -> dict:
        """Admit one compared typed method; fresh source/authority/lineage CAS required.

        The client researches and proposes options. This tool independently
        checks provenance and queues ONE registered local child, never raw code,
        unrestricted shell commands, external effects or self-declared success.
        """
        return admit_native_decision(
            db_path, workspace, fixtures, root_task_id, proposal)

    if allow_host_tick:
        @mcp.tool()
        def native_local_tick(root_task_id: str) -> dict:
            """OPT-IN isolated ledger only: execute one previously admitted child.

            This is intentionally unavailable by default. This server must have
            exactly one native root and no other tasks; otherwise advancing a
            generic Host tick might run an unrelated user's pending operation.
            The original Worker still checks grants, source pins and receipts.
            """
            observed = inspect_native_goal(
                db_path, workspace, fixtures, root_task_id)
            if observed["status"] != "NATIVE_AWAITING_WORKER":
                return {"status": "NATIVE_TICK_NOT_ADMISSIBLE",
                        "reason": observed["status"],
                        "owner_outcome_verified": False}
            with closing(_read_only_ledger(db_path)) as db:
                rows = db.execute(
                    "SELECT task_id,parent_task FROM tasks").fetchall()
                isolated = all(
                    (row["task_id"] == root_task_id
                     and row["parent_task"] is None)
                    or row["parent_task"] == root_task_id
                    for row in rows)
            if not isolated:
                return {"status": "NATIVE_TICK_SHARED_LEDGER_REFUSED",
                        "owner_outcome_verified": False}
            result = run_tick(db_path, workspace, fixtures, max_jobs=1)
            return {"status": "NATIVE_TICK_OBSERVED", "host_result": result,
                    "native_goal_readback": inspect_native_goal(
                        db_path, workspace, fixtures, root_task_id),
                    "owner_outcome_verified": False}

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local stdio MCP adapter; existing SQLite grant required.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--allow-host-tick", action="store_true",
                        help="Explicitly allow one native child per call in an isolated ledger")
    args = parser.parse_args(argv)
    mcp = build_mcp_server(
        args.db, args.workspace, args.fixtures,
        allow_host_tick=args.allow_host_tick)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
