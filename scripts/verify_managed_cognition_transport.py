"""Real MCP client/process/cold restart for the managed session entry.

Explicit operator policies are test inputs. This does NOT measure natural-
language understanding, a ChatGPT account connection or model improvement.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import Client, StdioServerParameters
from cognition_agent_os.effect_contract import install_contract
from cognition_agent_os.intent_planner import compile_intent
from cognition_agent_os.session_cli import provision
from verify_native_mcp_transport import unwrap, admit_with_current_procedure_evidence


async def run():
    with tempfile.TemporaryDirectory(prefix="caos-managed-") as temp:
        state = provision(Path(temp) / "state")
        sources = state / "sources"
        workspace = state / "workspace"
        db = state / "ledger.sqlite"
        (sources / "reference.csv").write_text("id,value\nA,4\n")
        (sources / "observed.csv").write_text("id,value\nA,3\n")
        (sources / "research.txt").write_text("Reference precedes observation.")
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "cognition_agent_os.session_cli", "--state", str(state), "serve"],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
        intent = {"kind": "goal_intent", "objective": "compare_records", "resources": [
            {"role": "reference", "path": "reference.csv"},
            {"role": "observed", "path": "observed.csv"}]}
        goal = "Compare reference.csv with observed.csv and report differences."

        async def inspect(client, root):
            return unwrap(await client.call_tool("cognition_session_inspect", {"root_task_id": root}))

        async def prepare(client, root):
            for name, kind, deps in [("source", "source", []),
                    ("compare", "option", ["source"]), ("defer", "option", ["source"]),
                    ("decision", "decision", ["compare", "defer"])]:
                view = await inspect(client, root)
                refs = [{"path": "research.txt", "quote": "Reference precedes observation.",
                    "sha256": hashlib.sha256((sources / "research.txt").read_bytes()).hexdigest()}] if kind == "source" else []
                node = {"id": name, "kind": kind, "text": name, "depends_on": deps,
                        "source_refs": refs, "supersedes": None, "goal_revision": view["goal_revision"]}
                if kind == "decision":
                    node["action_spec"] = compile_intent(intent)["child_source_spec"]
                unwrap(await client.call_tool("cognition_node_record", {
                    "root_task_id": root, "node": node, "request_id": name,
                    "expected_revision": view["revision_token"]}))

        async def proposal(client, root):
            current = unwrap(await client.call_tool("native_goal_inspect", {"root_task_id": root}))
            return {"selected_intent": intent, "alternative_intent": None,
                "decision_reason": "Compare pinned source counts within operator scope.",
                "alternative_reason": "Deferring cannot establish the discrepancy.",
                "expected_evidence": "Independent SQL recalculation of the report.",
                "observation_sha256": current["observation_sha256"],
                "decision_basis": {"source_refs": [
                    {"path": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
                    for f in sorted(sources.iterdir())],
                    "previous_result_task_id": None,
                    "challenge": "Reference and observation may be reversed.",
                    "falsifier": "Independent recomputation disagrees with the report.",
                    "uncertainty": "Fixture result is not an external business outcome."}}

        async with Client(params) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "cognition_node_record" in names
            assert not any("authorize" in n or "install_contract" in n for n in names)
            created = unwrap(await client.call_tool("native_goal_create", {
                "owner_goal": goal, "client_request_id": "managed-transport-001"}))
            root = created["root_task_id"]
            await prepare(client, root)
            request = await proposal(client, root)
            denied = await client.call_tool("native_decision_admit", {
                "root_task_id": root, "proposal": request})
            assert denied.is_error
            view = await inspect(client, root)
            # Deliberately OUTSIDE the agent-visible MCP tool catalogue.
            install_contract(db, sources, root, {"version": 1,
                "goal_sha256": view["goal_sha256"], "effects": [{
                    "spec": compile_intent(intent)["child_source_spec"], "prerequisites": []}],
                "outcomes": []})
            admitted = await admit_with_current_procedure_evidence(client, root, await proposal(client, root))
            tick = unwrap(await client.call_tool("native_local_tick", {"root_task_id": root}))
            assert tick["target_task_id"] == admitted["child_task_id"]
            outcome = unwrap(await client.call_tool("native_owner_outcome", {"root_task_id": root}))
            assert outcome["local_owner_outcome_verified"] is True, outcome
            root2 = unwrap(await client.call_tool("native_goal_create", {
                "owner_goal": goal + " Keep the source records unchanged.",
                "client_request_id": "managed-transport-002"}))["root_task_id"]
            await prepare(client, root2)
            view2 = await inspect(client, root2)
            install_contract(db, sources, root2, {"version": 1,
                "goal_sha256": view2["goal_sha256"], "effects": [{
                    "spec": compile_intent(intent)["child_source_spec"], "prerequisites": []}],
                "outcomes": []})
            queued2 = await admit_with_current_procedure_evidence(client, root2, await proposal(client, root2))

        # New OS process: no first client's in-memory state survives.
        async with Client(params) as client:
            restored = await inspect(client, root)
            assert restored["goal"]["original"] == goal
            assert restored["node_count"] == 4
            before = await inspect(client, root2)
            unwrap(await client.call_tool("cognition_reopen", {"root_task_id": root2,
                "node_id": "source", "reason": "New experiment contradicts the baseline choice.",
                "request_id": "counterexample-1", "expected_revision": before["revision_token"]}))
            blocked = unwrap(await client.call_tool("native_local_tick", {"root_task_id": root2}))
            assert not (workspace / "artifacts" / (queued2["child_task_id"] + ".json")).exists(), blocked
            changed = await inspect(client, root2)
            assert changed["reopen_count"] == 4, changed
            print(json.dumps({"real_mcp_stdio": True, "cold_process_resume": True,
                "missing_operator_contract_rejected": True, "granted_local_owner_outcome": True,
                "ancestor_reopen_blocks_queued_effect": True, "operator_grant_tool_exposed": False,
                "actual_chatgpt_or_codex_session_connected": False,
                "nl_alignment_benchmark": "NOT_RUN", "product_ready": False}, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
