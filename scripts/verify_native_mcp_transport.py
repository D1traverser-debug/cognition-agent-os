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

        def server(*, allow_tick, allow_source_read=False,
                   allow_model_plan=False, public_goal=None):
            args = ["-m", "cognition_agent_os.native_mcp_bridge",
                    "--db", str(db), "--workspace", str(workspace),
                    "--fixtures", str(sources)]
            if allow_tick:
                args.append("--allow-host-tick")
            if allow_source_read:
                args.append("--allow-source-read")
            if allow_model_plan:
                args.append("--allow-local-model-plan")
            if public_goal is not None:
                args.extend(["--public-discovery-goal-sha256", public_goal])
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
            assert "native_source_read" not in tools, tools
            assert "native_local_model_plan" not in tools, tools
            assert {"native_goal_create", "native_goal_inspect",
                    "native_decision_admit", "native_capabilities"} <= tools
            goal = ("Reconcile original supplier evidence, prepare isolated "
                    "handoff after checking source truth, never alter originals.")
            stable_request = "mcp-native-create-lost-ack-0001"
            created = unwrap(await client.call_tool(
                "native_goal_create", {
                    "owner_goal": goal,
                    "client_request_id": stable_request}))
            assert created["status"] == "NATIVE_GOAL_REGISTERED", created
            root = created["root_task_id"]
            # Lost ACK / duplicate transport delivery: same exact goal and
            # client token must recover the identical root, never create a
            # duplicate native goal that later confuses cold discovery.
            replayed = unwrap(await client.call_tool(
                "native_goal_create", {
                    "owner_goal": goal,
                    "client_request_id": stable_request}))
            assert replayed["root_task_id"] == root, (created, replayed)
            wrong_intent = await client.call_tool(
                "native_goal_create", {
                    "owner_goal": goal + " and mutate an unauthorized record",
                    "client_request_id": stable_request})
            assert wrong_intent.is_error, wrong_intent
            observed = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert observed["original_goal"] == goal, observed
            assert observed["decision_count"] == 0, observed
            assert "native_open_research_record" in tools

            # A genuine official MCP client checkpoints an unfamiliar
            # professional research direction with ZERO runnable Host method.
            unknown_goal = (
                "Diagnose humidity-sensitive calibration drift without "
                "modifying the hardware or claiming independent verification.")
            novel = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": unknown_goal}))
            novel_id = novel["root_task_id"]
            novel_state = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": novel_id}))
            research = {
                "observation_sha256": novel_state["observation_sha256"],
                "owner_clause": "without modifying the hardware",
                "unresolved_question": (
                    "Which independent method could distinguish humidity bias "
                    "from temperature drift?"),
                "competing_methods": [
                    {"name": "cross_reference",
                     "applicability": "Compare with separate calibrated sensor.",
                     "failure_mode": "The second sensor may share systematic drift.",
                     "falsifier": "Independent reference disagrees with the pattern."},
                    {"name": "controlled_experiment",
                     "applicability": "Vary humidity while controlling temperature.",
                     "failure_mode": "Hidden chamber gradients can confound results.",
                     "falsifier": "Matched measurements show no humidity dependence."},
                ],
                "source_refs": [],
                "next_research_step": (
                    "Find authoritative calibration procedures and safe measurements."),
                "uncertainty": (
                    "No source, hardware test or independent result is yet observed."),
            }
            saved = unwrap(await client.call_tool(
                "native_open_research_record",
                {"root_task_id": novel_id, "proposal": research}))
            assert saved["status"] == "NATIVE_OPEN_RESEARCH_RECORDED", saved
            assert saved["authorizes_action"] is False
            recovered = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": novel_id}))
            assert recovered["decision_count"] == 0, recovered
            assert recovered["open_research_count"] == 1, recovered
            assert recovered["open_research"][0]["source_status"] == (
                "NO_LOCAL_SOURCES_VERIFIED"), recovered
            assert recovered["owner_outcome_verified"] is False

        # A completely separate MCP stdio process must recover the original
        # professional research proposal, even with NO executable child.
        async with Client(server(allow_tick=False)) as fresh_client:
            cold = unwrap(await fresh_client.call_tool(
                "native_goal_inspect", {"root_task_id": novel_id}))
            assert cold["original_goal"] == unknown_goal, cold
            assert cold["open_research_count"] == 1, cold
            assert cold["open_research"][0]["proposal"]["competing_methods"] == (
                research["competing_methods"]), cold
            assert cold["decision_count"] == 0, cold
            assert cold["owner_outcome_verified"] is False, cold

        # Real MCP transport, not an internal Python caller: more than one
        # model-context page must remain recoverable after a server restart.
        async with Client(server(allow_tick=False)) as client:
            for ordinal in range(17):
                state = unwrap(await client.call_tool(
                    "native_goal_inspect", {"root_task_id": novel_id}))
                proposed = json.loads(json.dumps(research))
                proposed["observation_sha256"] = state["observation_sha256"]
                proposed["next_research_step"] = (
                    "Review separate primary calibration protocol number "
                    + str(ordinal) + " with an independent expert.")
                receipt = unwrap(await client.call_tool(
                    "native_open_research_record", {
                        "root_task_id": novel_id, "proposal": proposed}))
                assert receipt["status"] == "NATIVE_OPEN_RESEARCH_RECORDED", receipt
                assert receipt["authorizes_action"] is False

        # Another fresh stdio process independently rereads two pages.
        async with Client(server(allow_tick=False)) as client:
            first = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": novel_id}))
            assert first["open_research_count"] == 18, first
            assert len(first["open_research"]) == 16, first
            cursor = first["open_research_next_before_event_id"]
            assert type(cursor) is int and cursor > 0, first
            old = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": novel_id,
                                        "research_before_event_id": cursor}))
            assert old["open_research_count"] == 18, old
            assert len(old["open_research"]) == 2, old
            assert old["open_research_next_before_event_id"] is None, old
            all_ids = [x["event_id"] for x in first["open_research"]]
            all_ids += [x["event_id"] for x in old["open_research"]]
            assert len(set(all_ids)) == 18, "MCP_RESEARCH_PAGE_DUPLICATE"
            assert all_ids == sorted(all_ids, reverse=True), all_ids
            assert old["open_research"][-1]["proposal"]["competing_methods"] == (
                research["competing_methods"]), old
            assert first["original_goal"] == unknown_goal
            assert old["original_goal"] == unknown_goal
            assert first["observation_sha256"] == old["observation_sha256"]
            assert not first["owner_outcome_verified"]
            assert not old["owner_outcome_verified"]
            invalid = await client.call_tool(
                "native_goal_inspect", {
                    "root_task_id": novel_id, "research_before_event_id": 0})
            assert invalid.is_error, invalid
            off_page_duplicate = json.loads(json.dumps(research))
            off_page_duplicate["observation_sha256"] = (
                first["observation_sha256"])
            repeated_old = await client.call_tool(
                "native_open_research_record", {
                    "root_task_id": novel_id, "proposal": off_page_duplicate})
            assert repeated_old.is_error, repeated_old
            unchanged = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": novel_id}))
            assert unchanged["observation_sha256"] == (
                first["observation_sha256"]), unchanged
            assert unchanged["decision_count"] == 0, unchanged

        # Genuine optional planning uses only an installed local Ollama
        # provider. It is absent by default. An attempt to select a cloud
        # model/URL is rejected without task admission or provider requests.
        async with Client(server(allow_tick=False, allow_model_plan=True)) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert "native_local_model_plan" in names
            refusal = unwrap(await client.call_tool(
                "native_local_model_plan", {
                    "root_task_id": root, "model": "cloud://not-allowed"}))
            assert refusal["status"] == "NATIVE_LOCAL_MODEL_UNAVAILABLE", refusal
            untouched = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": root}))
            assert untouched["decision_count"] == 0, untouched

        # A model cannot choose outbound disclosure at tool-call time.
        # Only an explicitly configured local server is allowed to register
        # an original root with sanitized GitHub metadata discovery rights.
        authorized_goal = (
            "Research public testbench coverage tools using "
            "sanitized GitHub metadata only.")
        pinned_goal = hashlib.sha256(authorized_goal.encode("utf-8")).hexdigest()
        async with Client(server(
                allow_tick=False, public_goal=pinned_goal)) as client:
            listed = (await client.list_tools()).tools
            create = next(t for t in listed if t.name == "native_goal_create")
            assert "allow_public_discovery" not in create.input_schema["properties"]
            public = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": authorized_goal}))
            public_root = public["root_task_id"]
            capabilities = unwrap(await client.call_tool(
                "native_capabilities", {"root_task_id": public_root}))
            assert capabilities["public_disclosure_authorized"] is True
            assert next(item for item in capabilities["methods"]
                        if item["objective"] == "discover_public_tools"
                        )["currently_eligible"] is True
            not_pinned = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal":
                    "A different owner goal must not inherit outbound permission."}))
            unscoped_root = not_pinned["root_task_id"]
            denied = unwrap(await client.call_tool(
                "native_capabilities", {"root_task_id": unscoped_root}))
            assert denied["public_disclosure_authorized"] is False
            assert next(item for item in denied["methods"]
                        if item["objective"] == "discover_public_tools"
                        )["currently_eligible"] is False
            assert "native_local_tick" not in {t.name for t in listed}

        # A realistic owner objective can exceed an arbitrary short chat
        # headline. The contract must round-trip ALL original clauses,
        # including the final non-mutation and acceptance restrictions.
        long_goal = (
            "Audit a multidisciplinary owner objective with all requirements: "
            + ("preserve independent evidence and challenge assumptions; " * 49)
            + "FINAL RULE: no original source mutation and no completion "
              "claim without independent full-owner outcome verification.")
        assert 2048 < len(long_goal) < 8192
        async with Client(server(allow_tick=False)) as client:
            persisted = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": long_goal}))
            long_root = persisted["root_task_id"]
            recovered_long = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": long_root}))
            assert recovered_long["original_goal"] == long_goal

        # Source content is NOT remotely exposed by default. A separate
        # operator-opted-in process uses the already bounded and anchored
        # source reader. The client can challenge plans using real source
        # text instead of file names and hashes alone.
        async with Client(server(
                allow_tick=False, allow_source_read=True)) as client:
            enabled_names = {x.name for x in (
                await client.list_tools()).tools}
            assert "native_source_read" in enabled_names
            actual = unwrap(await client.call_tool(
                "native_source_read", {
                    "root_task_id": root, "file_name": "reference.csv"}))
            assert actual["status"] == "NATIVE_SOURCE_EXCERPT", actual
            assert actual["excerpt"] == (
                original["reference.csv"].decode("utf-8")), actual
            assert actual["source_sha256"] == hashlib.sha256(
                original["reference.csv"]).hexdigest()
            assert actual["source_trust"] == "UNTRUSTED_DATA"
            forbidden = await client.call_tool("native_source_read", {
                "root_task_id": root, "file_name": "../authority.sqlite"})
            assert forbidden.is_error, forbidden

        async with Client(server(allow_tick=False)) as client:
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
            compound = unwrap(await client.call_tool(
                "native_owner_outcome", {"root_task_id": root}))
            assert compound["status"] == "OWNER_POSTCONDITION_UNVERIFIED", compound
            assert not compound["local_owner_outcome_verified"], compound
            assert {f.name: f.read_bytes() for f in sources.iterdir()} == original
            # Same process must refuse a gratuitous duplicate tick.
            refused = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": root}))
            assert refused["status"] == "NATIVE_TICK_NOT_ADMISSIBLE", refused

        # Complete original local owner goal, including STRICT grammar,
        # through real separate MCP processes and the existing independent
        # postcondition oracle. The earlier compound goal must stay UNKNOWN.
        async with Client(server(allow_tick=True)) as client:
            local_goal = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": (
                    "Compare reference.csv with observed.csv and report differences.")}))
            local_id = local_goal["root_task_id"]
            pre_outcome = unwrap(await client.call_tool(
                "native_owner_outcome", {"root_task_id": local_id}))
            assert not pre_outcome["local_owner_outcome_verified"], pre_outcome
            local_state = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": local_id}))
            local_proposal = json.loads(json.dumps(proposal))
            local_proposal["observation_sha256"] = local_state["observation_sha256"]
            local_queued = unwrap(await client.call_tool(
                "native_decision_admit", {
                    "root_task_id": local_id, "proposal": local_proposal}))
            local_tick = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": local_id}))
            assert local_tick["target_task_id"] == local_queued["child_task_id"]
            owner = unwrap(await client.call_tool(
                "native_owner_outcome", {"root_task_id": local_id}))
            assert owner["status"] == "LOCAL_OWNER_RESULT_VERIFIED", owner
            assert owner["local_owner_outcome_verified"] is True, owner
            assert owner["business_outcome_verified"] is False, owner
            assert owner["real_external_outcome_verified"] is False, owner
            # No cached success: a changed original input invalidates the
            # independently re-read outcome even with the same SQLite state.
            (sources / "observed.csv").write_text(
                "supplier,received\nDelta,999\n", encoding="utf-8")
            stale = unwrap(await client.call_tool(
                "native_owner_outcome", {"root_task_id": local_id}))
            assert stale["local_owner_outcome_verified"] is False, stale
            (sources / "observed.csv").write_bytes(original["observed.csv"])

        # The same REAL MCP surface must complete an explicitly named
        # isolated JSON draft, not stop after a local proposal receipt.
        async with Client(server(allow_tick=True)) as client:
            json_root = unwrap(await client.call_tool(
                "native_goal_create", {"owner_goal": (
                    "Please ensure an isolated draft of handoff.json has "
                    "audit equal to confirmed.")}))["root_task_id"]
            state = unwrap(await client.call_tool(
                "native_goal_inspect", {"root_task_id": json_root}))
            json_proposal = {
                "selected_intent": {
                    "kind": "goal_intent", "objective": "ensure_structure",
                    "resources": [{"role": "input", "path": "handoff.json"}],
                    "requirements": [{"field": "audit", "equals": "confirmed"}]},
                "alternative_intent": None,
                "decision_reason": (
                    "A scoped JSON addition directly meets the named local draft."),
                "alternative_reason": (
                    "CSV comparison cannot satisfy the requested JSON field."),
                "expected_evidence": (
                    "Actual stage-only JSON artifact and independent original readback."),
                "observation_sha256": state["observation_sha256"],
                "decision_basis": {
                    "source_refs": [
                        {"path": n, "sha256": hashlib.sha256(data).hexdigest()}
                        for n, data in sorted(original.items())],
                    "previous_result_task_id": None,
                    "challenge": (
                        "The owner field might already conflict in the source."),
                    "falsifier": (
                        "The sandbox candidate changes a preexisting JSON key."),
                    "uncertainty": (
                        "A local handoff draft is not an external business effect."),
                },
            }
            queued_json = unwrap(await client.call_tool(
                "native_decision_admit", {
                    "root_task_id": json_root, "proposal": json_proposal}))
            observed_json = unwrap(await client.call_tool(
                "native_local_tick", {"root_task_id": json_root}))
            assert observed_json["target_task_id"] == queued_json["child_task_id"]
            assert observed_json["worker_result"]["status"] == "NEEDS_REVIEW"
            assert observed_json["sandbox_result"]["status"] == (
                "SANDBOX_VERIFIED"), observed_json
            accepted_json = unwrap(await client.call_tool(
                "native_owner_outcome", {"root_task_id": json_root}))
            assert accepted_json["status"] == "LOCAL_OWNER_RESULT_VERIFIED", accepted_json
            assert accepted_json["local_owner_outcome_verified"] is True
            assert accepted_json["business_outcome_verified"] is False
            staged_json = (workspace / "sandbox" /
                           (queued_json["child_task_id"] + ".candidate"))
            assert json.loads(staged_json.read_text(encoding="utf-8")) == {
                "retain": "immutable", "audit": "confirmed"}
            assert {f.name: f.read_bytes() for f in sources.iterdir()} == original

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
            # Prospective multi-tenant recovery fault: create more genuine
            # owner roots than one inventory page can hold. This is not an
            # unrelated fixture workload or a fake row with invalid grants.
            from cognition_agent_os.native_decision import register_native_goal
            extra_native_ids = {
                register_native_goal(db, (
                    "Persistent independent native owner goal number "
                    + str(ordinal) + "; preserve the full owner identity."))
                for ordinal in range(62)
            }
            # Fault-injection across ordering and indexing: after page one
            # has been read, ANOTHER writer creates a newer native root.
            # The original keyset cursor must never re-include a first-page
            # root or accidentally make the late root an older-page entry.
            initial_page = unwrap(await client.call_tool(
                "native_goal_list", {}))
            assert initial_page["truncated"] is True, initial_page
            after_first = initial_page["next_after_task_id"]
            first_page_ids = {
                item["root_task_id"] for item in initial_page["goals"]}
            late = unwrap(await client.call_tool(
                "native_goal_create", {
                    "owner_goal": "Late-arriving native root, after page-one read."}))
            late_id = late["root_task_id"]
            extra_native_ids.add(late_id)
            following = unwrap(await client.call_tool(
                "native_goal_list", {"after_task_id": after_first}))
            following_ids = {
                item["root_task_id"] for item in following["goals"]}
            assert not first_page_ids & following_ids, "PAGE_SHIFT_DUPLICATE"
            assert late_id not in following_ids, "LATE_NEWER_GOAL_IN_OLD_PAGE"
            assert late_id in {
                item["root_task_id"] for item in unwrap(
                    await client.call_tool("native_goal_list", {}))["goals"]
            }, "NEWER_GOAL_INVISIBLE_ON_FRESH_DISCOVERY"
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

        # Forty-plus unrelated legacy tasks can be generated between
        # sessions. A page cut BEFORE native type filtering would silently
        # hide all earlier genuine owner goals, causing irreversible drift.
        # These rows are NOT native roots and must never enter the native list.
        from cognition_agent_os.ledger import create_task
        with closing(connect(db)) as ledger:
            for ordinal in range(58):
                create_task(ledger, {
                    "kind": "fixture",
                    "ref": "unrelated-" + str(ordinal),
                }, commit=False)
            ledger.commit()

        # A brand-new client knows NO root id. It rediscovers the original
        # user goals via real SQLite before selecting the one whose exact
        # identity/goal is independently available. Ambiguity is not silently
        # collapsed to the newest row.
        async with Client(server(allow_tick=False)) as client:
            # API-level keyset paging must recover EVERY native original
            # without knowing any ID, even when >50 roots and >50 unrelated
            # task records coexist in the same persistent ledger.
            async def full_inventory():
                seen = {}
                after = None
                pages = 0
                while True:
                    args = {} if after is None else {
                        "after_task_id": after}
                    page = unwrap(await client.call_tool(
                        "native_goal_list", args))
                    assert page["status"] == "NATIVE_GOAL_INVENTORY", page
                    assert page["ambiguous"] is True, page
                    assert page["selected_root_task_id"] is None, page
                    assert len(page["goals"]) <= 50, page
                    for item in page["goals"]:
                        rid = item["root_task_id"]
                        assert rid not in seen, ("DUPLICATE_PAGINATED_ROOT", rid)
                        seen[rid] = item
                    pages += 1
                    assert pages <= 5, "INVENTORY_PAGINATION_LOOP"
                    after = page.get("next_after_task_id")
                    if after is None:
                        assert page["truncated"] is False, page
                        return seen, pages
                    assert page["truncated"] is True, page
                    assert after in seen, ("CURSOR_NOT_IN_PREVIOUS_PAGE", after)
            inventory, page_count = await full_inventory()
            assert page_count >= 2, "OLDER_GOALS_INACCESSIBLE"
            expected = ({root, novel_id, json_root, long_root, local_id,
                         public_root, unscoped_root, other_id, second_id}
                        | extra_native_ids)
            assert set(inventory) == expected, ("OLDER_GOALS_LOST", inventory)
            # Repeating the paginated query after an interrupted client
            # roundtrip must not change membership or execute any task.
            reread, repeat_page_count = await full_inventory()
            assert set(reread) == expected, "PAGINATION_RETRY_CHANGED_GOALS"
            assert repeat_page_count == page_count
            for bad_cursor in ("not_a_valid_root", other_queued["child_task_id"]):
                rejected_cursor = await client.call_tool(
                    "native_goal_list", {"after_task_id": bad_cursor})
                assert rejected_cursor.is_error, rejected_cursor
            discovered = next(
                item for item in inventory.values()
                if item["original_goal"] == goal)
            recovered = unwrap(await client.call_tool(
                "native_goal_inspect",
                {"root_task_id": discovered["root_task_id"]}))
            assert recovered["original_goal"] == goal
            assert recovered["decision_count"] == 1
            assert recovered["decisions"][0]["mechanical_verdict"] == (
                "REPORT_MECHANICALLY_VERIFIED")
            # A still-identifiable original goal with DRIFTED source bytes
            # must appear as unverified, not crash discovery because the
            # read-only native audit intentionally withholds decision_count.
            (sources / "observed.csv").write_text(
                "supplier,received\nDelta,999\n", encoding="utf-8")
            drifted, _ = await full_inventory()
            entry = drifted[root]
            assert entry["status"] == "NATIVE_SOURCE_CHANGED", entry
            assert entry["decision_count"] is None, entry
            assert entry["owner_outcome_verified"] is False, entry
            (sources / "observed.csv").write_bytes(original["observed.csv"])
            # Composite cold-resume failure: a stray temporary file makes
            # the entire evidence manifest unparseable. Valid immutable
            # owner goals must remain discoverable, but no plan/effect may
            # be authorized from that incomplete evidence snapshot.
            stray = sources / "temporary.lock"
            stray.write_text("writer interrupted before atomic rename",
                             encoding="utf-8")
            try:
                outage = unwrap(await client.call_tool(
                    "native_goal_inspect", {"root_task_id": root}))
                assert outage["status"] == "NATIVE_SOURCE_UNAVAILABLE", outage
                assert outage["original_goal"] == goal, outage
                assert "observation_sha256" not in outage, outage
                degraded, _ = await full_inventory()
                assert set(degraded) == expected, "VALID_ROOTS_LOST_WITH_SOURCE"
                assert degraded[root]["original_goal"] == goal
                assert degraded[root]["status"] == (
                    "NATIVE_SOURCE_UNAVAILABLE"), degraded[root]
                still_revoked = await client.call_tool(
                    "native_goal_create", {"owner_goal": goal})
                assert still_revoked.is_error, still_revoked
            finally:
                stray.unlink()
            restored, _ = await full_inventory()
            assert restored[root]["status"] == "NATIVE_GRANT_REVOKED"
        # Same private stdio entry intended for the official Secure MCP
        # Tunnel: independent process + real official MCP client + SAME
        # existing ledger. No tunnel credentials, account connection, API
        # call, network exposure or extra task grants are involved here.
        launcher = Path(__file__).resolve().parent / "chatgpt_private_stdio.py"
        launcher_env = {
            **os.environ,
            "COGNITION_OS_DB": str(db),
            "COGNITION_OS_WORKSPACE": str(workspace),
            "COGNITION_OS_FIXTURES": str(sources),
        }

        async def launch(mode, overrides=None):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(launcher), mode,
                env={**launcher_env, **(overrides or {})},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=35)
            return proc.returncode, stdout, stderr

        code, stdout, stderr = await launch("check")
        assert code == 0, ("PRIVATE_STDIO_PREFLIGHT_FAILED", stderr)
        preflight = json.loads(stdout)
        assert preflight["status"] == "PRIVATE_STDIO_MCP_LOCAL_PREFLIGHT_OK"
        assert preflight["chatgpt_cloud_connected"] is False
        assert "chatgpt_private_stdio.py" in preflight["mcp_command"]

        code, stdout, stderr = await launch("probe")
        assert code == 0, ("PRIVATE_STDIO_LIVE_PROBE_FAILED", stderr)
        probe = json.loads(stdout)
        assert probe["status"] == "PRIVATE_STDIO_MCP_SUBPROCESS_VERIFIED"
        assert probe["native_goal_list_verified"] is True
        assert probe["unprivileged_tools_only"] is True
        assert probe["chatgpt_cloud_connected"] is False

        # An actual separate process is the permission oracle; unlike a
        # self-described "unprivileged" probe it cannot expose write tools.
        with closing(connect(db)) as before_db:
            before_counts = (
                before_db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                before_db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            )
        private_params = StdioServerParameters(
            command=sys.executable, args=[str(launcher), "serve"],
            env=launcher_env)
        async with Client(private_params) as private_client:
            private_tools = {
                tool.name for tool in (await private_client.list_tools()).tools
            }
            assert {"native_goal_list", "native_goal_inspect",
                    "native_owner_outcome", "native_capabilities"} <= private_tools
            assert not ({
                "native_goal_create", "native_hypothesis_record",
                "native_open_research_record", "native_decision_admit",
                "native_local_tick", "native_local_model_plan",
                "native_source_read",
            } & private_tools), ("PRIVATE_STDIO_EXPOSED_WRITE_TOOL", private_tools)
            denied = await private_client.call_tool(
                "native_goal_create",
                {"owner_goal": "unauthorized goal through read-only tunnel"})
            assert denied.is_error, ("PRIVATE_STDIO_WRITES_NOT_REJECTED", denied)
            readback = unwrap(await private_client.call_tool(
                "native_goal_list", {}))
            assert readback["status"] == "NATIVE_GOAL_INVENTORY"
        with closing(connect(db)) as after_db:
            after_counts = (
                after_db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                after_db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            )
        assert after_counts == before_counts, (
            "READ_ONLY_TUNNEL_MUTATED_LEDGER", before_counts, after_counts)

        absent_db = base / "never_initialized_by_bridge.sqlite"
        code, stdout, stderr = await launch(
            "check", {"COGNITION_OS_DB": str(absent_db)})
        assert code == 2, ("MISSING_LEDGER_NOT_REJECTED", stdout, stderr)
        assert not absent_db.exists(), "PRIVATE_BRIDGE_CREATED_LEDGER"
        print(json.dumps({
            "status": "PRIVATE_CHATGPT_STDIO_TARGET_LOCALLY_VERIFIED",
            "ready_for_owner_secure_tunnel": True,
            "actual_chatgpt_cloud_link": False,
            "real_mcp_client": True,
            "missing_db_failed_closed": True,
            "production_effect": False}, sort_keys=True))

        print(json.dumps({
            "status": "LOCAL_MCP_HOST_READBACK_VERIFIED",
            "transport": "OFFICIAL_MCP_STDIO_SUBPROCESS",
            "independent_mechanical_verdict": "REPORT_MECHANICALLY_VERIFIED",
            "cold_process_recovery": True,
            "native_original_goal_independent_local_postcondition": True,
            "native_json_sandbox_owner_goal_verified_by_real_mcp": True,
            "cold_goal_discovery_without_id": True,
            "mixed_ledger_old_goals_not_hidden": True,
            "native_goal_inventory_paginated_cold_resume": True,
            "paginated_inventory_retry_idempotent": True,
            "long_original_owner_clause_exact_roundtrip": True,
            "drifted_goal_inventory_does_not_crash_or_claim_success": True,
            "stale_proposal_rejected": True,
            "default_worker_tool_absent": True,
            "source_text_default_hidden_and_opt_in_read_verified": True,
            "native_local_model_plan_opt_in_and_cloud_rejected": True,
            "external_disclosure_grant_not_model_controlled": True,
            "operator_opt_in_public_research_scope_verified": True,
            "shared_ledger_exact_target_worker": True,
            "revoked_grant_not_reissued": True,
            "owner_outcome_verified": False,
            "production_effect": False}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
