"""Actual ledger + MCP admission tests for source-scoped memory tools."""
from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.native_mcp_bridge import build_mcp_server


class _MCP:
    def __init__(self, name):
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class MemoryMcpToolTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.db, self.ws, self.fx = root / "existing.sqlite", root / "ws", root / "sources"
        self.ws.mkdir()
        self.fx.mkdir()
        self.source = self.fx / "evidence.md"
        self.source.write_text("A real observation.\nA method candidate.\n", encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
        self.goal = register_native_goal(self.db, "Investigate source evidence and compare competing methods")

    def server(self, **kwargs):
        fake_mcp = types.ModuleType("mcp")
        fake_server = types.ModuleType("mcp.server")
        fake_server.MCPServer = _MCP
        with patch.dict(sys.modules, {"mcp": fake_mcp, "mcp.server": fake_server}):
            return build_mcp_server(self.db, self.ws, self.fx, **kwargs)

    def pin(self):
        return hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_default_profile_has_no_memory_disclosure_or_write(self):
        s = self.server()
        self.assertNotIn("native_memory_candidates_inspect", s.tools)
        self.assertNotIn("native_memory_candidate_record", s.tools)
        # Disclosing source content remains a separate, explicit operator toggle.
        read = self.server(allow_source_read=True)
        self.assertIn("native_memory_candidates_inspect", read.tools)
        self.assertNotIn("native_memory_candidate_record", read.tools)
        self.assertNotIn("native_memory_candidates_inspect",
                         self.server(allow_goal_writes=True).tools)
        self.assertNotIn("native_method_experience_inspect", s.tools)
        self.assertIn("native_method_experience_inspect", read.tools)
        self.assertNotIn("native_method_experience_inspect",
                         self.server(allow_goal_writes=True).tools)
        before = self._ledger_counts()
        result = read.tools["native_method_experience_inspect"](self.goal)
        self.assertEqual(result["status"], "NO_REPLICATED_LOCAL_METHOD_EXPERIENCE")
        self.assertFalse(result["authorizes_action"])
        self.assertFalse(result["business_outcome_verified"])
        self.assertEqual(self._ledger_counts(), before)

    def _ledger_counts(self):
        with closing(connect(self.db)) as db:
            return (
                db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            )

    def test_method_experience_refuses_revoked_or_unverifiable_root(self):
        reader = self.server(allow_source_read=True)
        tool = reader.tools["native_method_experience_inspect"]
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        result = tool(self.goal)
        self.assertEqual(result["status"], "METHOD_EXPERIENCE_UNAVAILABLE")
        self.assertFalse(result["authorizes_action"])

    def test_only_dual_operator_optin_allows_untrusted_candidate(self):
        s = self.server(allow_source_read=True, allow_goal_writes=True)
        self.assertIn("native_memory_candidate_record", s.tools)
        rec = s.tools["native_memory_candidate_record"](
            self.goal, "mcp-memory-0001", "semantic", "evidence.md",
            self.pin(), "A real observation.", "Untrusted interpretation")
        self.assertEqual(rec["status"], "UNVERIFIED_CANDIDATE_STORED")
        self.assertFalse(rec["authorizes_action"])
        inspected = s.tools["native_memory_candidates_inspect"](self.goal)
        self.assertEqual(inspected["status"], "READ_ONLY_CANDIDATES")
        self.assertFalse(inspected["any_semantic_truth_verified"])

    def test_source_change_and_revocation_are_not_bypassable(self):
        s = self.server(allow_source_read=True, allow_goal_writes=True)
        original_sha = self.pin()
        s.tools["native_memory_candidate_record"](
            self.goal, "mcp-memory-0002", "semantic", "evidence.md",
            original_sha, "A real observation.", "Candidate")
        self.source.write_text("A changed observation.\n", encoding="utf-8")
        state = s.tools["native_memory_candidates_inspect"](self.goal)
        self.assertEqual(state["items"][0]["status"], "SOURCE_CHANGED_OR_UNAVAILABLE")
        with self.assertRaises(ValueError):
            s.tools["native_memory_candidate_record"](
                self.goal, "mcp-memory-0003", "semantic", "evidence.md",
                original_sha, "A real observation.", "Candidate")
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaises((ValueError, PermissionError)):
            s.tools["native_memory_candidate_record"](
                self.goal, "mcp-memory-0004", "semantic", "evidence.md",
                self.pin(), "A changed observation.", "Candidate")
        self.assertEqual(len(s.tools["native_memory_candidates_inspect"](self.goal)["items"]), 1)


if __name__ == "__main__":
    unittest.main()
