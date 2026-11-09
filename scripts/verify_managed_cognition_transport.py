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
from cognition_agent_os.effect_contract import install_contract, enforce_admission
from cognition_agent_os.ledger import readonly_snapshot
from cognition_agent_os.intent_planner import compile_intent
from cognition_agent_os.session_cli import provision
from cognition_agent_os.client_launch import prepare_launch, probe_transport
from cognition_agent_os.client_chat import journal
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
            inventory = (await client.list_tools()).tools
            names = {t.name for t in inventory}
            assert "cognition_node_record" in names
            schema = next(t.input_schema for t in inventory if t.name == "cognition_node_record")
            node_schema = schema["properties"]["node"]
            if "$ref" in node_schema:
                node_schema = schema["$defs"][node_schema["$ref"].rsplit("/", 1)[-1]]
            assert set(node_schema.get("required", [])) == {
                "id", "kind", "text", "depends_on", "source_refs", "supersedes", "goal_revision"}
            assert node_schema.get("additionalProperties") is False
            for field, required in {
                    "source_refs": {"path", "sha256", "quote"},
                    "method_refs": {"root_task_id", "node_id", "use"},
                    "input_refs": {"request_id", "sha256"},
                    "claims": {"input_id", "quote", "category", "meaning", "basis"}}.items():
                item_schema = node_schema["properties"][field]["items"]
                if "$ref" in item_schema:
                    item_schema = schema["$defs"][item_schema["$ref"].rsplit("/", 1)[-1]]
                assert set(item_schema.get("required", [])) == required
                assert item_schema.get("additionalProperties") is False
            assert not any("authorize" in n or "install_contract" in n for n in names)
            created = unwrap(await client.call_tool("native_goal_create", {
                "owner_goal": goal, "client_request_id": "managed-transport-001"}))
            root = created["root_task_id"]
            original_view = await inspect(client, root)
            malformed = await client.call_tool("cognition_node_record", {
                "root_task_id": root, "node": {}, "request_id": "missing-fields",
                "expected_revision": original_view["revision_token"]})
            assert malformed.is_error
            assert "depends_on" in " ".join(getattr(p, "text", "") for p in malformed.content)
            valid_shape = {"id": "schema-neighbor", "kind": "observation", "text": "test",
                "depends_on": [], "source_refs": [], "supersedes": None, "goal_revision": 0}
            for change in ({"goal_revision": "0"}, {"undeclared_action": "must not be dropped"},
                           {"source_refs": ["goal/original/sha256/null"]},
                           {"source_refs": [{"path": "research.txt"}]},
                           {"method_refs": [{"root_task_id": root}]},
                           {"input_refs": [{"request_id": "missing-digest"}]},
                           {"claims": [{"meaning": "unsupported"}]}):
                refused = await client.call_tool("cognition_node_record", {
                    "root_task_id": root, "node": valid_shape | change,
                    "request_id": "schema-neighbor", "expected_revision": original_view["revision_token"]})
                assert refused.is_error, "Schema silently coerced/dropped input"
            # Real failed model trace: invented version and incomplete node.
            # The client needs a bounded recovery reason, not a masked crash.
            for bad_root, revision, code, hint in [
                    (root, "0.0", "COGNITION_STALE_REVISION", "revision_token"),
                    (root, original_view["revision_token"], "COGNITION_INVALID_NODE", "goal_revision"),
                    ("0" * 32, "0.0", "COGNITION_ROOT_NOT_FOUND", "native_goal_list")]:
                rejected = await client.call_tool("cognition_node_record", {
                    "root_task_id": bad_root, "node": {"id": "invalid-record",
                        "kind": "invalid-kind", "text": "PRIVATE_ERROR_INPUT_SENTINEL",
                        "depends_on": [], "source_refs": [], "supersedes": None, "goal_revision": 0},
                    "request_id": "invalid-record", "expected_revision": revision})
                assert rejected.is_error
                message = " ".join(getattr(p, "text", "") for p in rejected.content)
                assert code in message and hint in message, message
                assert "PRIVATE_ERROR_INPUT_SENTINEL" not in message
            unknown = await client.call_tool("cognition_node_record", {
                "root_task_id": root, "request_id": "unknown-source-error",
                "expected_revision": original_view["revision_token"],
                "node": {"id": "unsafe-source", "kind": "source", "text": "Untrusted source",
                    "depends_on": [], "supersedes": None, "goal_revision": 0,
                    "source_refs": [{"path": "/PRIVATE_ERROR_INPUT_SENTINEL", "sha256": "0" * 64,
                                     "quote": "PRIVATE_SOURCE_CONTENT_SENTINEL"}]}})
            assert unknown.is_error
            message = " ".join(getattr(p, "text", "") for p in unknown.content)
            assert "COGNITION_SOURCE_UNAVAILABLE" in message
            assert "PRIVATE_ERROR_INPUT_SENTINEL" not in message
            assert "PRIVATE_SOURCE_CONTENT_SENTINEL" not in message
            hidden = await client.call_tool("cognition_node_record", {
                "root_task_id": root, "request_id": "unrecognized-domain-error",
                "expected_revision": original_view["revision_token"],
                "node": {"id": "invented-obligation", "kind": "obligation",
                    "text": "PRIVATE_UNQUOTED_OWNER_CLAIM", "depends_on": [],
                    "supersedes": None, "goal_revision": 0, "source_refs": []}})
            assert hidden.is_error
            masked = " ".join(getattr(p, "text", "") for p in hidden.content)
            assert "PRIVATE_UNQUOTED_OWNER_CLAIM" not in masked
            assert "COGNITION_OBLIGATION_MUST_QUOTE_OWNER" not in masked
            assert (await inspect(client, root))["revision_token"] == original_view["revision_token"]
            raw_input = "Maybe use a graph. This is a suggestion, not a replacement goal."
            unwrap(await client.call_tool("cognition_input_record", {
                "root_task_id": root, "text": raw_input, "origin": "client_user",
                "locator": "MCP transport test", "request_id": "transport-message-001",
                "expected_revision": original_view["revision_token"]}))
            input_view = unwrap(await client.call_tool("cognition_inputs_inspect", {"root_task_id": root}))
            item = input_view["inputs"][0]
            interpretation = {"id": "reading", "kind": "interpretation",
                "text": "A suggested technique still requires comparison.",
                "depends_on": [], "source_refs": [], "supersedes": None, "goal_revision": 0,
                "input_refs": [{"request_id": item["request_id"], "sha256": item["sha256"]}],
                "claims": [{"input_id": item["request_id"], "quote": "Maybe use a graph.",
                    "category": "implementation_suggestion", "basis": "explicit",
                    "meaning": "Consider the graph as a candidate, not as a mandate."}]}
            unwrap(await client.call_tool("cognition_node_record", {
                "root_task_id": root, "node": interpretation, "request_id": "transport-reading-001",
                "expected_revision": input_view["revision_token"]}))
            assert (await inspect(client, root))["goal"] == original_view["goal"]
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
            after_admission = await inspect(client, root2)
            unwrap(await client.call_tool("cognition_input_record", {
                "root_task_id": root2, "text": "Please reconsider the comparison before continuing.",
                "origin": "client_user", "locator": "late correction test",
                "request_id": "late-correction-001",
                "expected_revision": after_admission["revision_token"]}))
            with readonly_snapshot(db) as connection:
                try:
                    enforce_admission(connection, sources, workspace, root2,
                                      compile_intent(intent)["child_source_spec"])
                except PermissionError as exc:
                    assert str(exc) == "COGNITIVE_INPUT_REQUIRES_REDECISION"
                else:
                    raise AssertionError("New user message did not invalidate the queued decision")
            late_view = unwrap(await client.call_tool("cognition_inputs_inspect", {"root_task_id": root2}))
            late = late_view["inputs"][-1]
            late_reading = {"id": "late-reading", "kind": "interpretation",
                "text": "The new request must be considered before execution.",
                "depends_on": [], "source_refs": [], "supersedes": None,
                "goal_revision": view2["goal_revision"],
                "input_refs": [{"request_id": late["request_id"], "sha256": late["sha256"]}],
                "claims": [{"input_id": late["request_id"], "quote": late["text"],
                    "category": "correction", "basis": "explicit", "meaning": "Reconsider the old action."}]}
            unwrap(await client.call_tool("cognition_node_record", {"root_task_id": root2,
                "node": late_reading, "request_id": "late-reading-001",
                "expected_revision": late_view["revision_token"]}))
            with readonly_snapshot(db) as connection:
                try:
                    enforce_admission(connection, sources, workspace, root2,
                                      compile_intent(intent)["child_source_spec"])
                except PermissionError as exc:
                    assert str(exc) == "COGNITIVE_INPUT_REQUIRES_REDECISION"
                else:
                    raise AssertionError("Interpretation alone revived an older decision")
            reviewed = await inspect(client, root2)
            new_decision = {"id": "decision-after-input", "kind": "decision",
                "text": "Reconsidered after the new input for this positive control.",
                "depends_on": ["compare", "defer", "late-reading"], "source_refs": [],
                "supersedes": "decision", "goal_revision": reviewed["goal_revision"],
                "action_spec": compile_intent(intent)["child_source_spec"]}
            unwrap(await client.call_tool("cognition_node_record", {"root_task_id": root2,
                "node": new_decision, "request_id": "decision-after-input-001",
                "expected_revision": reviewed["revision_token"]}))
            with readonly_snapshot(db) as connection:
                assert enforce_admission(connection, sources, workspace, root2,
                    compile_intent(intent)["child_source_spec"])["decision_id"] == "decision-after-input"

        # Exercise the production launcher preflight, not a test-only server
        # configuration. It must work without inherited PYTHONPATH and must
        # neither mutate the ledger nor disclose the private goal in its receipt.
        with readonly_snapshot(db) as connection:
            event_count = connection.execute("SELECT count(*) FROM events").fetchone()[0]
        prepared = prepare_launch(state, root=root, executable=sys.executable)
        preflight = await asyncio.to_thread(probe_transport, prepared)
        assert preflight["status"] == "MCP_TRANSPORT_VERIFIED", preflight
        assert goal not in json.dumps(preflight)
        with readonly_snapshot(db) as connection:
            assert event_count == connection.execute("SELECT count(*) FROM events").fetchone()[0]

        # Delivery bookkeeping stays in the same ledger and is independently
        # recovered through the real MCP server after a process restart.
        journal(state, root, "delivery-probe", "DISPATCHING")
        journal(state, root, "delivery-probe", "DELIVERY_UNKNOWN")

        # New OS process: no first client's in-memory state survives.
        async with Client(params) as client:
            restored = await inspect(client, root)
            assert restored["goal"]["original"] == goal
            assert restored["node_count"] == 5
            recovered_input = unwrap(await client.call_tool("cognition_inputs_inspect", {"root_task_id": root}))
            assert recovered_input["inputs"][0]["text"] == raw_input
            assert recovered_input["inputs"][0]["interpretation_ids"] == ["reading"]
            assert not recovered_input["inputs"][0]["semantic_understanding_verified"]
            delivery = unwrap(await client.call_tool("cognition_client_history", {
                "root_task_id": root, "limit": 1}))
            assert delivery["turns"][0]["status"] == "DISPATCHING"
            delivery = unwrap(await client.call_tool("cognition_client_history", {
                "root_task_id": root, "after_event_id": delivery["next_after_event_id"]}))
            assert delivery["turns"][0]["status"] == "DELIVERY_UNKNOWN"
            assert not delivery["owner_outcome_verified"]
            before = await inspect(client, root2)
            unwrap(await client.call_tool("cognition_reopen", {"root_task_id": root2,
                "node_id": "source", "reason": "New experiment contradicts the baseline choice.",
                "request_id": "counterexample-1", "expected_revision": before["revision_token"]}))
            blocked = unwrap(await client.call_tool("native_local_tick", {"root_task_id": root2}))
            assert not (workspace / "artifacts" / (queued2["child_task_id"] + ".json")).exists(), blocked
            changed = await inspect(client, root2)
            assert changed["reopen_count"] == 5, changed
            print(json.dumps({"real_mcp_stdio": True, "cold_process_resume": True,
                "missing_operator_contract_rejected": True, "granted_local_owner_outcome": True,
                "ancestor_reopen_blocks_queued_effect": True, "operator_grant_tool_exposed": False,
                "input_and_tentative_reading_survive_cold_restart": True,
                "late_input_and_interpretation_require_new_decision": True,
                "reviewed_new_decision_can_be_admitted": True,
                "production_launcher_preflight_readonly": True,
                "client_delivery_history_cold_mcp_readback": True,
                "suggestion_does_not_replace_goal": True,
                "actual_chatgpt_or_codex_session_connected": False,
                "nl_alignment_benchmark": "NOT_RUN", "product_ready": False}, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
