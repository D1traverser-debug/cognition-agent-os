"""MCP operator-pinned public-source reads are not metadata or action grants.

The MCP SDK registration shim is a test double; the actual ledger, source
identity, grants, original goal checks and response bytes are exercised.
The provider transport is isolated so CI never leaks the synthetic goal.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.host import run_tick
from cognition_agent_os.native_decision import (
    admit_native_decision, inspect_native_goal, register_native_goal)
from cognition_agent_os.native_mcp_bridge import build_mcp_server


class _MCP:
    def __init__(self, name):
        self.name = name
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class NativeMcpPublicPrimaryEvidenceTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        home = Path(td.name)
        self.db, self.ws, self.fx = (
            home / "ledger.sqlite", home / "workspace", home / "sources")
        self.ws.mkdir()
        self.fx.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)
        self.owner_goal = (
            "Investigate independent agent source evidence without giving "
            "external research content authority to execute code."
        )
        self.root = register_native_goal(
            self.db, self.owner_goal, allow_public_source_read=True)
        self.scope = hashlib.sha256(self.owner_goal.encode()).hexdigest()
        self.remote = (
            "datawhalechina/Agent-Learning-Hub", "README.md",
            "dddf777dde6788228136862f270203424a28efbc")

    def server(self, **kwargs):
        fake_mcp = types.ModuleType("mcp")
        fake_server = types.ModuleType("mcp.server")
        fake_server.MCPServer = _MCP
        with patch.dict(sys.modules, {
                "mcp": fake_mcp, "mcp.server": fake_server}):
            return build_mcp_server(
                self.db, self.ws, self.fx, **kwargs)

    def _native_root_with_failure(self, failure):
        """Build a real native decision, then introduce one independent fault."""
        for name, data in {
            "expected.csv": b"supplier,received\nDelta,8\n",
            "observed.csv": b"supplier,received\nDelta,6\n",
            "handoff.json": b'{"retain":"immutable"}\n',
        }.items():
            path = self.fx / name
            if not path.exists():
                path.write_bytes(data)
        goal = (
            "Reconcile the supplier records and prepare a provenance-labelled "
            "local handoff without editing original sources.")
        root = register_native_goal(self.db, goal)
        observed = inspect_native_goal(self.db, self.ws, self.fx, root)
        refs = [
            {"path": path.name,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(self.fx.iterdir(), key=lambda p: p.name)
        ]
        proposal = {
            "observation_sha256": observed["observation_sha256"],
            "selected_intent": {
                "kind": "goal_intent", "objective": "compare_records",
                "resources": [
                    {"role": "reference", "path": "expected.csv"},
                    {"role": "observed", "path": "observed.csv"}]},
            "alternative_intent": {
                "kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "handoff.json"}],
                "requirements": [{"field": "audit", "equals": "confirmed"}]},
            "decision_reason": "Compare the original supplier records first.",
            "alternative_reason": "The handoff structure is a separate later obligation.",
            "expected_evidence": "An independently audited local reconciliation report.",
            "decision_basis": {
                "source_refs": refs, "previous_result_task_id": None,
                "challenge": "The selected comparison may not cover the handoff clause.",
                "falsifier": "An independent report audit may reject the computed discrepancy.",
                "uncertainty": "Neither local mechanical success nor a report proves the whole owner outcome.",
            },
        }
        admitted = admit_native_decision(
            self.db, self.ws, self.fx, root, proposal)
        tick = run_tick(self.db, self.ws, self.fx, max_jobs=1)
        self.assertEqual(tick["tasks"][0]["task_id"], admitted["child_task_id"])
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW")
        if failure == "source":
            (self.fx / "observed.csv").write_text(
                "supplier,received\nDelta,999\n", encoding="utf-8")
            expected_status = "NATIVE_SOURCE_CHANGED"
        elif failure == "evidence":
            artifact = self.ws / "artifacts" / (
                admitted["child_task_id"] + ".json")
            artifact.write_bytes(artifact.read_bytes() + b" corrupt evidence")
            expected_status = "NATIVE_EVIDENCE_UNVERIFIABLE"
        else:
            raise AssertionError("unknown injected failure")
        self.assertEqual(
            inspect_native_goal(self.db, self.ws, self.fx, root)["status"],
            expected_status)
        return root, expected_status

    def test_observation_only_profile_excludes_every_mutating_tool(self):
        reader = self.server(allow_goal_writes=False)
        exposed = set(reader.tools)
        self.assertTrue({
            "native_goal_list", "native_goal_inspect", "native_capabilities",
            "native_owner_outcome",
        } <= exposed)
        self.assertFalse({
            "native_goal_create", "native_hypothesis_record",
            "native_open_research_record", "native_decision_admit",
            "native_local_tick", "native_local_model_plan",
        } & exposed)
        with closing(connect(self.db)) as db:
            before = (
                db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            )
        inventory = reader.tools["native_goal_list"]()
        self.assertEqual(inventory["goals"][0]["original_goal"], self.owner_goal)
        with closing(connect(self.db)) as db:
            after = (
                db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            )
        self.assertEqual(after, before)

    def test_observation_only_profile_rejects_mixed_write_flags(self):
        for flag in ("allow_host_tick", "allow_local_model_plan"):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(
                        ValueError, "READ_ONLY_MCP_CANNOT_ENABLE"):
                    self.server(allow_goal_writes=False, **{flag: True})
        self.assertNotIn("native_goal_create", self.server().tools)
        self.assertNotIn("native_decision_admit", self.server().tools)
        self.assertIn("native_goal_create", self.server(allow_goal_writes=True).tools)
        self.assertIn("native_decision_admit", self.server(allow_goal_writes=True).tools)

    def test_public_read_requires_explicit_runtime_opt_in(self):
        self.assertNotIn("native_public_primary_source_read",
                         self.server().tools)
        self.assertIn("native_public_primary_source_read",
                      self.server(
                          public_source_goal_sha256=self.scope).tools)

    def test_real_original_bytes_in_excerpt_but_not_an_action(self):
        server = self.server(public_source_goal_sha256=self.scope)
        source = b"# Agent Loop\n" + b"README evidence, not an executable tool.\n"
        with patch("cognition_agent_os.source.github_public_snapshot",
                   return_value=source) as fetch:
            result = server.tools["native_public_primary_source_read"](
                self.root, *self.remote, offset_chars=5)
        self.assertEqual(fetch.call_args.args, self.remote)
        self.assertEqual(result["excerpt"], source.decode()[5:])
        self.assertEqual(result["source_sha256"],
                         hashlib.sha256(source).hexdigest())
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["new_tool_execution_authorized"])
        self.assertEqual(result["source_trust"],
                         "UNTRUSTED_ORIGINAL_BYTES_NOT_SEMANTIC_TRUTH")
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (self.root,)).fetchone()[0], 0)

    def test_other_goals_and_metadata_only_scope_cannot_use_source_tool(self):
        other = register_native_goal(
            self.db, "Investigate a different local task.",
            allow_public_source_read=True)
        metadata_only = register_native_goal(
            self.db, "Investigate public repo metadata.",
            allow_public_discovery=True)
        reader = self.server(
            public_source_goal_sha256=self.scope).tools[
                "native_public_primary_source_read"]
        with patch("cognition_agent_os.source.github_public_snapshot",
                   side_effect=AssertionError("forbidden network call")):
            with self.assertRaisesRegex(
                    PermissionError, "PUBLIC_SOURCE_GOAL_SCOPE_MISMATCH"):
                reader(other, *self.remote)
            with self.assertRaises(PermissionError):
                reader(metadata_only, *self.remote)

    def test_revoked_grant_during_source_fetch_cannot_return_content(self):
        reader = self.server(
            public_source_goal_sha256=self.scope).tools[
                "native_public_primary_source_read"]
        def revoke(repo, path, sha):
            with closing(connect(self.db)) as db:
                db.execute("UPDATE authority SET grant_rev=grant_rev+1 "
                           "WHERE singleton=1")
                db.commit()
            return b"private-after-revocation"
        with patch("cognition_agent_os.source.github_public_snapshot",
                   side_effect=revoke):
            with self.assertRaisesRegex(
                    PermissionError, "PUBLIC_SOURCE_GRANT_CHANGED_DURING_READ"):
                reader(self.root, *self.remote)

    def test_local_source_read_refuses_revoked_goal_before_disclosing_bytes(self):
        (self.fx / "private.md").write_text("owner-pinned source", encoding="utf-8")
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        self.assertEqual(reader(self.root, "private.md")["excerpt"],
                         "owner-pinned source")
        with closing(connect(self.db)) as db:
            db.execute("UPDATE authority SET grant_rev=grant_rev+1 "
                       "WHERE singleton=1")
            db.commit()
        # An opt-in operator flag alone is not a still-current goal grant.
        with self.assertRaisesRegex(
                PermissionError, "LOCAL_SOURCE_READ_NOT_ADMISSIBLE"):
            reader(self.root, "private.md")

    def test_local_source_read_refuses_revocation_during_bounded_read(self):
        (self.fx / "private.md").write_text("must not leak", encoding="utf-8")
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        from cognition_agent_os import native_mcp_bridge as bridge
        original_read = bridge.safe_fixture
        def revoke_during_fetch(root, relative):
            raw = original_read(root, relative)
            with closing(connect(self.db)) as db:
                db.execute("UPDATE authority SET grant_rev=grant_rev+1 "
                           "WHERE singleton=1")
                db.commit()
            return raw
        # _sources() is a distinct source-layer read: revoke only at the
        # actual local tool disclosure boundary after the first admission.
        with patch.object(bridge, "safe_fixture",
                          side_effect=revoke_during_fetch):
            with self.assertRaisesRegex(
                    PermissionError, "LOCAL_SOURCE_GRANT_CHANGED_DURING_READ"):
                reader(self.root, "private.md")

    def test_local_source_read_allows_scoped_investigation_during_source_or_evidence_failure(self):
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        for failure in ("source", "evidence"):
            with self.subTest(failure=failure):
                root, expected = self._native_root_with_failure(failure)
                self.assertEqual(
                    inspect_native_goal(self.db, self.ws, self.fx, root)["status"],
                    expected)
                result = reader(root, "handoff.json")
                self.assertEqual(result["status"], "NATIVE_SOURCE_EXCERPT")
                self.assertEqual(result["excerpt"], '{"retain":"immutable"}' + chr(10))
                self.assertFalse(result["new_tool_execution_authorized"])
                self.assertFalse(result["owner_outcome_verified"])

    def test_local_source_read_during_failure_refuses_revoked_grant_before_read(self):
        root, _ = self._native_root_with_failure("evidence")
        with closing(connect(self.db)) as db:
            db.execute("UPDATE authority SET grant_rev=grant_rev+1 "
                       "WHERE singleton=1")
            db.commit()
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        with self.assertRaisesRegex(
                PermissionError, "LOCAL_SOURCE_READ_NOT_ADMISSIBLE"):
            reader(root, "handoff.json")

    def test_local_source_read_during_failure_refuses_revocation_during_read(self):
        root, _ = self._native_root_with_failure("evidence")
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        from cognition_agent_os import native_mcp_bridge as bridge
        original = bridge.safe_fixture

        def revoke_after_read(root_path, relative):
            raw = original(root_path, relative)
            with closing(connect(self.db)) as db:
                db.execute("UPDATE authority SET grant_rev=grant_rev+1 "
                           "WHERE singleton=1")
                db.commit()
            return raw

        with patch.object(bridge, "safe_fixture", side_effect=revoke_after_read):
            with self.assertRaisesRegex(
                    PermissionError, "LOCAL_SOURCE_GRANT_CHANGED_DURING_READ"):
                reader(root, "handoff.json")

    def test_local_source_read_during_failure_rechecks_exact_source_digest(self):
        root, _ = self._native_root_with_failure("evidence")
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        from cognition_agent_os import native_mcp_bridge as bridge
        original = bridge.safe_fixture
        source = self.fx / "handoff.json"

        def mutate_after_read(root_path, relative):
            raw = original(root_path, relative)
            source.write_text('{"retain":"changed during disclosure"}\\n',
                              encoding="utf-8")
            return raw

        with patch.object(bridge, "safe_fixture", side_effect=mutate_after_read):
            with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED_DURING_READ"):
                reader(root, "handoff.json")

    def test_local_read_receipt_reports_exact_window_not_semantic_acceptance(self):
        source = "A" * 4096 + "LAST_SENTENCE"
        (self.fx / "private.md").write_text(source, encoding="utf-8")
        reader = self.server(allow_source_read=True).tools["native_source_read"]
        first = reader(self.root, "private.md")
        second = reader(self.root, "private.md",
                        offset_chars=first["next_offset_chars"])
        self.assertEqual(first["offset_chars"], 0)
        self.assertEqual(second["offset_chars"], 4096)
        self.assertEqual(first["source_sha256"], second["source_sha256"])
        self.assertEqual(first["total_chars"], len(source))
        self.assertEqual(first["excerpt"] + second["excerpt"], source)
        self.assertIsNone(second["next_offset_chars"])
        self.assertFalse(second["owner_outcome_verified"])

    def test_invalid_input_and_binary_rejected_without_claiming_truth(self):
        reader = self.server(
            public_source_goal_sha256=self.scope).tools[
                "native_public_primary_source_read"]
        with self.assertRaisesRegex(ValueError, "INVALID_PUBLIC_SOURCE_OFFSET"):
            reader(self.root, *self.remote, offset_chars=-1)
        with patch("cognition_agent_os.source.github_public_snapshot",
                   return_value=b"\x00binary"):
            with self.assertRaisesRegex(ValueError, "PUBLIC_SOURCE_NOT_PLAIN_TEXT"):
                reader(self.root, *self.remote)


if __name__ == "__main__":
    unittest.main()
