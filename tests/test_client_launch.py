"""Client wiring is not model authentication or semantic acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.client_launch import launch, prepare_launch
from cognition_agent_os.session_cli import provision
from cognition_agent_os.native_decision import register_native_goal


class ClientLaunch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = provision(Path(self.temp.name) / 'private state & (中文)')
        self.root = register_native_goal(self.state / "ledger.sqlite", "Preserve this original goal",
            managed_session=True, client_request_id="client-launch-test-0001")

    def available(self):
        return patch("cognition_agent_os.client_launch.importlib.util.find_spec", return_value=object())

    def test_paths_are_separate_arguments_and_check_does_not_launch(self):
        with self.available(), patch("cognition_agent_os.client_launch.subprocess.run") as run, \
                patch("cognition_agent_os.client_launch.probe_transport", return_value={"status": "test-double"}) as probe:
            plan = launch(self.state, root=self.root, executable=sys.executable, check=True)
        run.assert_not_called()
        probe.assert_called_once()
        args = plan["argv"]
        settings = dict(x.split("=", 1) for x in args[2:-1:2])
        server = json.loads(settings["mcp_servers.caos.args"])
        self.assertEqual(server[-2:], [str(self.state.resolve()), "serve"])
        self.assertTrue(json.loads(settings["mcp_servers.caos.required"]))
        self.assertIn(self.root, args[-1])
        self.assertFalse(plan["account_config_modified"])
        self.assertEqual(plan["client_connected"], "NOT_OBSERVED")

    def test_client_exit_is_propagated_not_reported_as_connection_success(self):
        with self.available(), patch("cognition_agent_os.client_launch.subprocess.run",
                return_value=subprocess.CompletedProcess([], 7)) as run:
            result = launch(self.state, executable=sys.executable)
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(run.call_args.kwargs, {"check": False})
        self.assertIsInstance(run.call_args.args[0], list)
        self.assertEqual(result["client_connected"], "NOT_ATTESTED_BY_EXIT_CODE")

    def test_no_selected_goal_does_not_choose_newest(self):
        with self.available():
            plan = prepare_launch(self.state, executable=sys.executable)
        self.assertIsNone(plan["root_task_id"])
        self.assertIn("instead of choosing the newest", plan["argv"][-1])

    def test_missing_dependency_fails_before_client_start(self):
        with patch("cognition_agent_os.client_launch.importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(ValueError, "MCP_NOT_INSTALLED"):
                prepare_launch(self.state, executable=sys.executable)

    def test_wrong_root_or_missing_state_cannot_create_a_session(self):
        with self.available():
            with self.assertRaises((ValueError, PermissionError)):
                prepare_launch(self.state, root="0" * 32, executable=sys.executable)
            missing = Path(self.temp.name) / "missing"
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                prepare_launch(missing, executable=sys.executable)
            self.assertFalse(missing.exists())
