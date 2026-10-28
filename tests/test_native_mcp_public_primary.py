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
from cognition_agent_os.native_decision import register_native_goal
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
