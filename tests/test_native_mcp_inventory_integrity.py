"""Cold native-goal inventory must not silently drop damaged owner roots.

A malformed registered receipt is NOT trusted original text; the identity
remains visible as UNVERIFIABLE, so a cold caller cannot auto-select an
apparently unique surviving goal and silently abandon an earlier obligation.
This uses the actual initialized SQLite ledger and the original MCP tool body.
"""
from contextlib import closing
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
        self.tools = {}

    def tool(self):
        def register(func):
            self.tools[func.__name__] = func
            return func
        return register


class NativeInventoryIntegrityTests(unittest.TestCase):
    def test_corrupt_original_receipt_is_visible_but_not_trusted(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            db, workspace, sources = root / "ledger.sqlite", root / "work", root / "sources"
            workspace.mkdir()
            sources.mkdir()
            with closing(connect(db)) as connection:
                initialize(connection)
            healthy = register_native_goal(db, "Investigate safe task A")
            broken = register_native_goal(db, "Investigate different task B")
            # Simulate actual persisted-receipt corruption without changing
            # the root source_spec, grant or its native_goal identity.
            with closing(connect(db)) as connection:
                connection.execute(
                    "UPDATE events SET details='{}' WHERE task_id=? "
                    "AND kind='NATIVE_GOAL_REGISTERED'", (broken,))
                connection.commit()
            fake_mcp = types.ModuleType("mcp")
            fake_server = types.ModuleType("mcp.server")
            fake_server.MCPServer = _MCP
            with patch.dict(sys.modules, {"mcp": fake_mcp, "mcp.server": fake_server}):
                service = build_mcp_server(db, workspace, sources)
            inventory = service.tools["native_goal_list"]()
            by_id = {entry["root_task_id"]: entry for entry in inventory["goals"]}
            self.assertEqual(set(by_id), {healthy, broken})
            self.assertEqual(by_id[healthy]["original_goal"], "Investigate safe task A")
            self.assertEqual(by_id[broken]["status"], "NATIVE_GOAL_UNVERIFIABLE")
            self.assertNotIn("original_goal", by_id[broken])
            self.assertFalse(by_id[broken]["owner_outcome_verified"])
            self.assertTrue(inventory["ambiguous"])
            self.assertIsNone(inventory["selected_root_task_id"])
            self.assertFalse(inventory["owner_outcome_verified"])


if __name__ == "__main__":
    unittest.main()
