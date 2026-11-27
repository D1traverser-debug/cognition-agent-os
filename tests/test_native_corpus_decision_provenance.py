"""Real MCP/SQLite provenance boundary for source-free typed resource lists.

A corpus-wide local method still consumes evidence; the decision graph must
not silently certify a source-free comparison. Public metadata methods are
separate: they do not claim to have read local corpus content.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from cognition_agent_os.cognitive_session import inspect_session
from cognition_agent_os.effect_contract import enable_managed_session
from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.native_mcp_bridge import build_mcp_server


class _MCP:
    def __init__(self, name):
        self.tools = {}

    def tool(self, **metadata):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class CorpusDecisionProvenance(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db, self.workspace, self.sources = (
            root / "ledger.sqlite", root / "workspace", root / "sources")
        self.workspace.mkdir()
        self.sources.mkdir()
        self.source = self.sources / "evidence.md"
        self.source.write_text(
            "The first source supports hypothesis A.\n"
            "A different method may overturn it.\n", encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
        self.goal = register_native_goal(
            self.db, "Investigate the original local source evidence before comparing methods.")
        enable_managed_session(self.db, self.goal)

        fake_mcp = types.ModuleType("mcp")
        fake_server = types.ModuleType("mcp.server")
        fake_server.MCPServer = _MCP
        with patch.dict(sys.modules, {
                "mcp": fake_mcp, "mcp.server": fake_server}):
            self.server = build_mcp_server(
                self.db, self.workspace, self.sources,
                allow_goal_writes=True, allow_source_read=True)

    def _record(self):
        intent = {
            "kind": "goal_intent",
            "objective": "investigate_evidence",
            "resources": [],
            "question": "What does the original source substantiate?",
        }
        return self.server.tools["cognition_decision_bundle_record"](
            self.goal, json.dumps(intent),
            "Investigate local source statements",
            "Defer judgment until primary sources can be read",
            "The question requires a source-grounded comparison.")

    def test_corpus_wide_decision_requires_a_real_preceding_source_read(self):
        before = self.server.tools["cognition_session_inspect"](self.goal)
        self.assertEqual(before["nodes"], [])
        with self.assertRaisesRegex(ValueError, "COGNITION_EVIDENCE_NOT_READ"):
            self._record()
        unchanged = inspect_session(self.db, self.sources, self.goal)
        self.assertEqual(unchanged["revision_token"], before["revision_token"])
        self.assertEqual(unchanged["nodes"], [])

        excerpt = self.server.tools["native_source_read"](self.goal, "evidence.md")
        self.assertEqual(excerpt["status"], "NATIVE_SOURCE_EXCERPT")
        result = self._record()
        self.assertEqual(result["status"], "RECORDED")
        view = inspect_session(self.db, self.sources, self.goal)
        self.assertEqual([node["kind"] for node in view["nodes"]],
                         ["option", "option", "decision"])
        expected_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        for node in view["nodes"]:
            self.assertEqual(node["source_refs"][0]["path"], "evidence.md")
            self.assertEqual(node["source_refs"][0]["sha256"], expected_sha)
        # This is a sourced decision record, not an admitted effect or outcome.
        self.assertFalse(result["owner_outcome_verified"])
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM tasks WHERE parent_task=?",
                (self.goal,)).fetchone()[0], 0)

    def test_drift_after_read_rejects_without_partial_graph(self):
        before = self.server.tools["cognition_session_inspect"](self.goal)
        self.server.tools["native_source_read"](self.goal, "evidence.md")
        self.source.write_text("Source content changed after the MCP read.\n",
                               encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "COGNITION_SOURCE_CHANGED"):
            self._record()
        view = inspect_session(self.db, self.sources, self.goal)
        self.assertEqual(view["revision_token"], before["revision_token"])
        self.assertEqual(view["nodes"], [])


if __name__ == "__main__":
    unittest.main()
