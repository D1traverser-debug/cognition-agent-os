"""Offline policy tests for the optional A/B/C MCP architecture screen."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_compound_ab_c as harness


class CompoundAbcHarnessTests(unittest.TestCase):
    def test_sdk_allowlist_exposes_only_scoped_native_tools(self):
        self.assertEqual(set(harness.SDK_TOOL_ALLOWLIST), {
            "native_goal_inspect",
            "native_procedure_evidence",
            "native_capabilities",
            "native_source_read",
            "native_decision_admit",
        })
        self.assertEqual(harness.HARNESS_EXECUTION_TOOL, "native_local_tick")
        self.assertNotIn(harness.HARNESS_EXECUTION_TOOL, harness.SDK_TOOL_ALLOWLIST)
        for forbidden in (
            "native_goal_create",
            "native_local_tick",
            "native_owner_outcome",
            "native_local_model_plan",
            "native_memory_candidate_record",
            "native_public_primary_source_read",
            "cognition_shell",
        ):
            self.assertNotIn(forbidden, harness.SDK_TOOL_ALLOWLIST)

    def test_decision_protocol_keeps_cas_and_lineage_tokens_in_the_bridge(self):
        protocol = harness.SDK_DECISION_PROTOCOL
        self.assertIn("ONLY JSON null permitted", protocol)
        self.assertIn("alternative_reason MUST always be", protocol)
        self.assertIn("EVEN WHEN alternative_intent is null", protocol)
        normalized_protocol = " ".join(protocol.lower().split())
        self.assertIn("do not include any of those three fields", normalized_protocol)
        self.assertIn("native_goal_inspect and native_procedure_evidence", protocol)

    def test_tool_argument_shape_decodes_json_structure_without_values(self):
        raw = json.dumps({
            "proposal": {
                "alternative_intent": None,
                "alternative_reason": None,
                "observation_sha256": None,
                "decision_basis": {
                    "source_refs": [{
                        "path": "private-source.csv",
                        "sha256": "a" * 64,
                    }],
                },
            },
        })
        shape = harness._safe_argument_shape(raw)
        rendered = json.dumps(shape, sort_keys=True)
        self.assertIn('"alternative_reason": {"type": "null"}', rendered)
        self.assertIn('"observation_sha256": {"type": "null"}', rendered)
        self.assertNotIn("private-source.csv", rendered)
        self.assertNotIn("a" * 64, rendered)

    def test_agents_sdk_provider_is_loopback_only(self):
        self.assertEqual(
            harness.local_openai_base_url("127.0.0.1:11434"),
            "http://127.0.0.1:11434/v1")
        self.assertEqual(
            harness.local_openai_base_url("http://localhost:11434/"),
            "http://localhost:11434/v1")
        for remote in (
            "https://api.openai.com/v1",
            "http://192.0.2.10:11434",
            "http://127.0.0.1:11434/proxy",
        ):
            with self.subTest(remote=remote), self.assertRaisesRegex(
                    ValueError, "LOOPBACK_HTTP"):
                harness.local_openai_base_url(remote)

    def test_no_model_bridge_admits_grounded_first_clause(self):
        """Discriminate protocol/bridge failure from a model's inability to use it.

        The probe uses the same real SQLite, local fixtures, scoped contract
        and native MCP decision body as the B/C screen; it deliberately does
        not infer model cognition or an independent owner-outcome PASS.
        """
        from cognition_agent_os.native_decision import (
            inspect_native_goal, register_native_goal,
        )
        from cognition_agent_os.native_mcp_bridge import build_mcp_server
        from cognition_agent_os.intent_planner import compile_intent

        class _FakeMcp:
            def __init__(self, name):
                self.tools = {}

            def tool(self, **metadata):
                def register(fn):
                    self.tools[fn.__name__] = fn
                    return fn
                return register

        with tempfile.TemporaryDirectory(prefix="caos-s2-bridge-control-") as home:
            db, workspace, fixtures, before = harness.benchmark._prepare(
                Path(home), harness.CASE["files"])
            root = register_native_goal(db, harness.OWNER_GOAL,
                                        managed_session=True)
            harness.bind_compound_effect_contract(
                db, fixtures, workspace, root, before)
            fake_mcp = types.ModuleType("mcp")
            fake_server = types.ModuleType("mcp.server")
            fake_server.MCPServer = _FakeMcp
            with patch.dict(sys.modules, {
                    "mcp": fake_mcp, "mcp.server": fake_server}):
                server = build_mcp_server(
                    db, workspace, fixtures,
                    allow_goal_writes=True,
                    allow_host_tick=True,
                    allow_source_read=True)
            tools = server.tools
            inspected = tools["native_goal_inspect"](root)
            self.assertEqual(
                inspected["status"], "NATIVE_NEXT_DECISION_ADMISSIBLE")
            tools["native_capabilities"](root)
            tools["native_procedure_evidence"](root)
            refs = []
            for source in ("baseline.csv", "actual.csv"):
                read = tools["native_source_read"](root, source)
                self.assertEqual(read["status"], "NATIVE_SOURCE_EXCERPT")
                refs.append({
                    "path": read["file_name"],
                    "sha256": read["source_sha256"],
                })
            # A valid effect requires a CURRENT cognition decision bound
            # to the exact executable action, not merely a native proposal.
            # Use existing cognition MCP tools instead of bypassing the gate.
            decision_intent = {
                "kind": "goal_intent",
                "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": "baseline.csv"},
                    {"role": "observed", "path": "actual.csv"},
                ],
            }
            action_spec = compile_intent(decision_intent)["child_source_spec"]
            source_quote = (
                tools["native_source_read"](root, "baseline.csv")["excerpt"]
                .splitlines()[0])
            cognition_nodes = [
                ("baseline-source", "source", [],
                 [{"path": "baseline.csv", "sha256": refs[0]["sha256"],
                   "quote": source_quote}], "Original baseline CSV evidence."),
                ("option-compare", "option", ["baseline-source"], [],
                 "Compare CSV records before changing JSON draft."),
                ("option-draft-first", "option", ["baseline-source"], [],
                 "Draft the JSON settings first, leaving CSV unexplained."),
                ("decision-compare", "decision",
                 ["option-compare", "option-draft-first"], [],
                 "Select CSV comparison first, challenge draft-first."),
            ]
            for name, kind, deps, source_refs, explanation in cognition_nodes:
                session = tools["cognition_session_inspect"](root)
                node = {
                    "id": name, "kind": kind, "text": explanation,
                    "depends_on": deps, "source_refs": source_refs,
                    "supersedes": None,
                    "goal_revision": session["goal_revision"],
                }
                if kind == "decision":
                    node["action_spec"] = action_spec
                written = tools["cognition_node_record"](
                    root, node, "s2-bridge-control-" + name,
                    session["revision_token"])
                self.assertEqual(written["status"], "RECORDED")
            # Required second inspection refreshes CAS after cognition writes.
            tools["native_goal_inspect"](root)
            tools["native_procedure_evidence"](root)
            proposal = {
                "selected_intent": decision_intent,
                "alternative_intent": None,
                "decision_reason":
                    "Compare the original and observed CSV records first.",
                "alternative_reason":
                    "A JSON draft cannot establish the requested CSV differences.",
                "expected_evidence":
                    "An independently inspectable local discrepancy artifact.",
                "decision_basis": {
                    "source_refs": refs,
                    "challenge":
                        "The CSV rows may not represent all original clauses.",
                    "falsifier":
                        "A source mismatch or independent discrepancy audit could reverse the choice.",
                    "uncertainty":
                        "A CSV comparison cannot prove the JSON draft is complete.",
                },
            }
            admitted = tools["native_decision_admit"](root, proposal)
            self.assertEqual(
                admitted["status"], "NATIVE_METHOD_ENQUEUED", admitted)
            state = inspect_native_goal(db, workspace, fixtures, root)
            self.assertEqual(state["decision_count"], 1)
            self.assertEqual(state["status"], "NATIVE_AWAITING_WORKER")
            self.assertFalse(state["owner_outcome_verified"])

    def test_independent_contract_pins_exact_goal_and_all_source_bytes(self):
        source_hashes = {
            "baseline.csv": hashlib.sha256(b"baseline").hexdigest(),
            "actual.csv": hashlib.sha256(b"actual").hexdigest(),
            "settings.json": hashlib.sha256(b"settings").hexdigest(),
        }
        contract = harness.build_contract(harness.OWNER_GOAL, source_hashes)
        self.assertEqual(
            contract["owner_goal_sha256"],
            hashlib.sha256(harness.OWNER_GOAL.encode("utf-8")).hexdigest())
        self.assertEqual(contract["source_sha256"], source_hashes)
        self.assertEqual(contract["allowed_effect"], "LOCAL_CANDIDATES_ONLY")
        with self.assertRaisesRegex(ValueError, "SOURCE_MANIFEST_MISMATCH"):
            harness.build_contract(harness.OWNER_GOAL, {
                "baseline.csv": source_hashes["baseline.csv"]})


if __name__ == "__main__":
    unittest.main()
