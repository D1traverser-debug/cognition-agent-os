"""Public MCP must not expose the legacy unbound execution path.

No semantic classifier is mocked or claimed: positive execution requires the
separate operator contract already tested by the real MCP transport suite.
"""
from contextlib import closing
import unittest
from unittest.mock import patch

import test_memory_mcp_boundary as fixture_module
from cognition_agent_os.effect_contract import managed
from cognition_agent_os.ledger import connect, create_task
from cognition_agent_os.native_decision import register_native_goal


class McpExecutionBoundary(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.MemoryMcpToolTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.server = self.fixture.server(allow_goal_writes=True,
            allow_host_tick=True, allow_local_model_plan=True, allow_source_read=True)

    def test_mcp_creation_is_managed_without_an_agent_selected_toggle(self):
        created = self.server.tools["native_goal_create"]("Investigate without executing", "boundary-create-001")
        with closing(connect(self.fixture.db)) as db:
            self.assertTrue(managed(db, created["root_task_id"]))
            self.assertEqual(db.execute("SELECT count(*) FROM tasks WHERE parent_task=?",
                (created["root_task_id"],)).fetchone()[0], 0)
        replay = self.server.tools["native_goal_create"]("Investigate without executing", "boundary-create-001")
        self.assertEqual(created["root_task_id"], replay["root_task_id"])

    def test_legacy_root_cannot_reach_any_public_effect_entry(self):
        root = self.fixture.goal
        with patch("cognition_agent_os.native_mcp_bridge.admit_native_decision") as admit, \
             patch("cognition_agent_os.native_mcp_bridge.run_once") as worker, \
             patch("cognition_agent_os.native_local_planner.advance_native_local_once") as model:
            calls = [("native_decision_admit", (root, {})),
                     ("native_local_tick", (root,)),
                     ("native_local_model_plan", (root, "unused-model"))]
            for name, args in calls:
                with self.subTest(tool=name), self.assertRaisesRegex(PermissionError, "UNMANAGED_NATIVE_EFFECTS_DISABLED"):
                    self.server.tools[name](*args)
            admit.assert_not_called()
            worker.assert_not_called()
            model.assert_not_called()
        # Legacy state remains discoverable; blocking effects must not erase
        # the original goal or shut down read-only investigation.
        view = self.server.tools["cognition_session_inspect"](root)
        self.assertEqual(view["goal"]["amendments"], [])
        self.assertEqual(view["node_count"], 0)
        with closing(connect(self.fixture.db)) as db:
            self.assertFalse(managed(db, root))

    def test_keyed_replay_can_restrict_unused_legacy_root_without_new_identity(self):
        root = register_native_goal(self.fixture.db, "Research this goal", client_request_id="unused-legacy-0001")
        result = self.server.tools["native_goal_create"]("Research this goal", "unused-legacy-0001")
        self.assertEqual(root, result["root_task_id"])
        with closing(connect(self.fixture.db)) as db:
            self.assertTrue(managed(db, root))

    def test_failed_managed_registration_rolls_back_the_entire_new_root(self):
        with closing(connect(self.fixture.db)) as db:
            before = db.execute("SELECT count(*) FROM tasks").fetchone()[0]
        with patch("cognition_agent_os.effect_contract._enable_managed",
                   side_effect=ValueError("test registration failure")):
            with self.assertRaisesRegex(ValueError, "registration failure"):
                self.server.tools["native_goal_create"]("Atomic new root", "atomic-root-0001")
        with closing(connect(self.fixture.db)) as db:
            self.assertEqual(before, db.execute("SELECT count(*) FROM tasks").fetchone()[0])
            self.assertIsNone(db.execute("SELECT 1 FROM events WHERE details LIKE ?",
                                        ('%atomic-root-0001%',)).fetchone())

    def test_legacy_pending_effect_is_not_adopted_as_a_managed_binding(self):
        root = register_native_goal(self.fixture.db, "Old scoped work", client_request_id="used-legacy-0001")
        with closing(connect(self.fixture.db)) as db:
            child = create_task(db, {"kind": "record_reconciliation",
                "reference": "reference.csv", "observed": "observed.csv"}, parent=root)
        with self.assertRaisesRegex(ValueError, "NO_PRIOR_EFFECTS"):
            self.server.tools["native_goal_create"]("Old scoped work", "used-legacy-0001")
        with closing(connect(self.fixture.db)) as db:
            self.assertFalse(managed(db, root))
            self.assertEqual(db.execute("SELECT state FROM tasks WHERE task_id=?", (child,)).fetchone()[0], "PENDING")


if __name__ == "__main__":
    unittest.main()
