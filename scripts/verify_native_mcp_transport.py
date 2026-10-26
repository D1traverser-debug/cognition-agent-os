"""Actual official-MCP-client -> stdio process -> SQLite Host -> readback.

Runs only in a disposable directory with intentionally initialized local grant.
No model API, external business state, ChatGPT account or production effect.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import Client, StdioServerParameters

from cognition_agent_os.ledger import connect, initialize


def unwrap(result):
    if result.is_error:
        raise AssertionError("MCP tool call rejected: " + repr(result.content))
    structured = result.structured_content
    if isinstance(structured, dict):
        if "status" in structured or "root_task_id" in structured:
            return structured
        if isinstance(structured.get("result"), dict):
            return structured["result"]
    for part in result.content:
        text = getattr(part, "text", None)
        if isinstance(text, str):
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError("No structured, verifiable MCP tool result")


async def run():
    with tempfile.TemporaryDirectory() as home:
        base = Path(home)
        db = base / "authority.sqlite"
        sources = base / "sources"
        workspace = base / "workspace"
        sources.mkdir()
        workspace.mkdir()
        (sources / "reference.csv").write_text(
            "supplier,received\nDelta,8\n", encoding="utf-8")
        (sources / "observed.csv").write_text(
            "supplier,received\nDelta,6\n", encoding="utf-8")
        (sources / "handoff.json").write_text(
            '{"retain":"immutable"}\n', encoding="utf-8")
        original = {f.name: f.read_bytes() for f in sources.iterdir()}
        with closing(connect(db)) as ledger:
            initialize(ledger)

        def server(*, allow_tick):
            args = ["-m", "cognition_agent_os.native_mcp_bridge",
                    "--db", str(db), "--workspace", str(workspace),
                    "--fixtures", str(sources)]
            if allow_tick:
                args.append("--allow-host-tick")
            return StdioServerParameters(
                command=sys.executable, args=args,
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})

        # Real negotiated MCP transport, not a direct Python function test.
        async with Client(server(allow_tick=False)) as client:
            tools = {x.name for x in (await client.list_tools()).tools}
            assert "native_local_tick" not in tools, tools
            assert {"native_goal_create", "native_goal_inspect",
                    "native_decision_admit", "native_capabilities"} <= tools
            goal = ("Reconcile original supplier evidence, prepare isolated "
                    "handoff after checking source truth, never alter originals.")
            created = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": goal}))
            assert created["status"] == "NATIVE_GOAL_REGISTERED", created
            root = created["root_task_id"]
            observed = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert observed["original_goal"] == goal, observed
            assert observed["decision_count"] == 0, observed
            options = unwrap(await client.call_tool(
                "native_capabilities", {"root_task_id": root}))
            catalog = {x["objective"]: x for x in options["methods"]}
            assert catalog["compare_records"]["currently_eligible"]
            assert catalog["ensure_structure"]["currently_eligible"]
            assert not catalog["discover_public_tools"]["currently_eligible"]
            refs = [
                {"path": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
                for f in sorted(sources.iterdir())]
            proposal = {
                "selected_intent": {
                    "kind": "goal_intent", "objective": "compare_records",
                    "resources": [
                        {"role": "reference", "path": "reference.csv"},
                        {"role": "observed", "path": "observed.csv"}]},
                "alternative_intent": {
                    "kind": "goal_intent", "objective": "ensure_structure",
                    "resources": [{"role": "input", "path": "handoff.json"}],
                    "requirements": [{"field": "audit", "equals": "confirmed"}]},
                "decision_reason": "Read the original record evidence first.",
                "alternative_reason": "Structural conformance does not reconcile raw supplier values.",
                "expected_evidence": "Independent source recomputation and immutable discrepancy report.",
                "observation_sha256": observed["observation_sha256"],
                "decision_basis": {
                    "source_refs": refs,
                    "previous_result_task_id": None,
                    "challenge": "A different join key may explain the apparent shortage.",
                    "falsifier": "Independent source recomputation contradicts the proposed discrepancy.",
                    "uncertainty": "A valid local report cannot prove upstream business resolution.",
                },
            }
            bad = json.loads(json.dumps(proposal))
            bad["decision_basis"]["source_refs"][0]["sha256"] = "f" * 64
            rejected = await client.call_tool(
                "native_decision_admit", {"root_task_id": root, "proposal": bad})
            assert rejected.is_error, rejected
            still = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert still["decision_count"] == 0, still
            admitted = unwrap(await client.call_tool(
                "native_decision_admit", {"root_task_id": root,
                                          "proposal": proposal}))
            assert admitted["status"] == "NATIVE_METHOD_ENQUEUED", admitted
            queued = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert queued["status"] == "NATIVE_AWAITING_WORKER", queued

        # New subprocess, SAME on-disk ledger/grant. A real Worker does its
        # originally registered action and a separate oracle rereads evidence.
        async with Client(server(allow_tick=True)) as client:
            executed = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": root}))
            assert executed["status"] == "NATIVE_TICK_OBSERVED", executed
            assert executed["host_result"]["tasks"][0]["status"] == "NEEDS_REVIEW"
            after = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert after["decision_count"] == 1, after
            assert after["decisions"][0]["mechanical_verdict"] == (
                "REPORT_MECHANICALLY_VERIFIED"), after
            assert after["owner_outcome_verified"] is False, after
            assert {f.name: f.read_bytes() for f in sources.iterdir()} == original
            # Same process must refuse a gratuitous duplicate tick.
            refused = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": root}))
            assert refused["status"] == "NATIVE_TICK_NOT_ADMISSIBLE", refused

        # A read-only second restart demonstrates real state continuity.
        async with Client(server(allow_tick=False)) as client:
            recovered = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert recovered["original_goal"] == goal
            assert recovered["decision_count"] == 1
            assert recovered["decisions"][0]["mechanical_verdict"] == (
                "REPORT_MECHANICALLY_VERIFIED")
        print(json.dumps({
            "status": "LOCAL_MCP_HOST_READBACK_VERIFIED",
            "transport": "OFFICIAL_MCP_STDIO_SUBPROCESS",
            "independent_mechanical_verdict": "REPORT_MECHANICALLY_VERIFIED",
            "cold_process_recovery": True,
            "stale_proposal_rejected": True,
            "default_worker_tool_absent": True,
            "owner_outcome_verified": False,
            "production_effect": False}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
