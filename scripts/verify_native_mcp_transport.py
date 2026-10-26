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
            registered = (await client.list_tools()).tools
            tools = {x.name for x in registered}
            create_spec = next(x for x in registered if x.name == "native_goal_create")
            assert "allow_public_discovery" not in (
                create_spec.input_schema["properties"]), create_spec
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
            assert executed["worker_result"]["status"] == "NEEDS_REVIEW"
            assert executed["target_task_id"] == admitted["child_task_id"]
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

        # Multi-owner stress: queue another owner's task FIRST, then
        # request the later second root. The selected worker must claim
        # only its exact child, irrespective of the generic due_at ordering.
        async with Client(server(allow_tick=True)) as client:
            other = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": (
                    "First queued independent supplier evidence objective.")}))
            other_id = other["root_task_id"]
            other_snapshot = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": other_id}))
            other_proposal = json.loads(json.dumps(proposal))
            other_proposal["observation_sha256"] = other_snapshot["observation_sha256"]
            other_queued = unwrap(await client.call_tool(
                "native_decision_admit", {
                    "root_task_id": other_id, "proposal": other_proposal}))
            second = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": (
                    "Independently reconcile a second supplier case "
                    "without touching any other goal.")}))
            second_id = second["root_task_id"]
            new_state = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": second_id}))
            second_proposal = json.loads(json.dumps(proposal))
            second_proposal["observation_sha256"] = new_state["observation_sha256"]
            second_queued = unwrap(await client.call_tool(
                "native_decision_admit", {
                    "root_task_id": second_id, "proposal": second_proposal}))
            selected_tick = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": second_id}))
            assert selected_tick["status"] == "NATIVE_TICK_OBSERVED", selected_tick
            assert selected_tick["target_task_id"] == (
                second_queued["child_task_id"]), selected_tick
            assert selected_tick["worker_result"]["status"] == (
                "NEEDS_REVIEW"), selected_tick
            with closing(connect(db)) as ledger:
                earlier_state = ledger.execute(
                    "SELECT state FROM tasks WHERE task_id=?",
                    (other_queued["child_task_id"],)).fetchone()["state"]
                assert earlier_state == "PENDING", earlier_state
            earlier_tick = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": other_id}))
            assert earlier_tick["target_task_id"] == (
                other_queued["child_task_id"]), earlier_tick
            assert earlier_tick["worker_result"]["status"] == (
                "NEEDS_REVIEW"), earlier_tick
            with closing(connect(db)) as ledger:
                from cognition_agent_os.ledger import alter_authority
                alter_authority(ledger, revoke=True)
            revoked = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": second_id}))
            assert revoked["status"] == "NATIVE_GRANT_REVOKED", revoked
            new_attempt = await client.call_tool(
                "native_goal_create",
                {"owner_goal": "This cannot regrant revoked authority."})
            assert new_attempt.is_error, new_attempt

        # A brand-new client knows NO root id. It rediscovers the original
        # user goals via real SQLite before selecting the one whose exact
        # identity/goal is independently available. Ambiguity is not silently
        # collapsed to the newest row.
        async with Client(server(allow_tick=False)) as client:
            inventory = unwrap(await client.call_tool("native_goal_list", {}))
            assert inventory["status"] == "NATIVE_GOAL_INVENTORY", inventory
            assert inventory["ambiguous"] is True, inventory
            assert inventory["selected_root_task_id"] is None, inventory
            ids = {entry["root_task_id"] for entry in inventory["goals"]}
            assert ids == {root, other_id, second_id}, inventory
            discovered = next(
                item for item in inventory["goals"]
                if item["original_goal"] == goal)
            recovered = unwrap(await client.call_tool(
                "native_goal_inspect",
                {"root_task_id": discovered["root_task_id"]}))
            assert recovered["original_goal"] == goal
            assert recovered["decision_count"] == 1
            assert recovered["decisions"][0]["mechanical_verdict"] == (
                "REPORT_MECHANICALLY_VERIFIED")
        print(json.dumps({
            "status": "LOCAL_MCP_HOST_READBACK_VERIFIED",
            "transport": "OFFICIAL_MCP_STDIO_SUBPROCESS",
            "independent_mechanical_verdict": "REPORT_MECHANICALLY_VERIFIED",
            "cold_process_recovery": True,
            "cold_goal_discovery_without_id": True,
            "stale_proposal_rejected": True,
            "default_worker_tool_absent": True,
            "external_disclosure_grant_not_model_controlled": True,
            "shared_ledger_exact_target_worker": True,
            "revoked_grant_not_reissued": True,
            "owner_outcome_verified": False,
            "production_effect": False}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
