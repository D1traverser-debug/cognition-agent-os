"""Prevent runtime SQLite bootstrap after a successful authority preflight.

The SQLite create-if-missing helper is permitted only for explicit session
provisioning. Native admission, Worker, and review paths must reopen an
existing ledger with mode=rw, including under file-disappearance races.
"""
from contextlib import closing
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import (
    LedgerNotConfigured, connect, initialize, require_initialized_ledger)
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.runner import run_once


class RuntimeExistingLedgerOnly(unittest.TestCase):
    def _state(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "ledger.sqlite"
        with closing(connect(path)) as db:
            initialize(db)
        return path

    def _drop_after_positive_preflight(self, path: Path) -> None:
        require_initialized_ledger(path)
        path.rename(path.with_name("ledger-disappeared.sqlite"))

    def test_native_registration_cannot_create_ghost_ledger_after_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._state(Path(tmp) / "state")
            with patch("cognition_agent_os.native_decision.require_initialized_ledger",
                       side_effect=self._drop_after_positive_preflight):
                with self.assertRaises(LedgerNotConfigured):
                    register_native_goal(path, "Check this original owner goal")
            self.assertFalse(path.exists(), "runtime minted an uninitialized ledger")
            self.assertTrue(path.with_name("ledger-disappeared.sqlite").exists())

    def test_worker_cannot_create_ghost_ledger_after_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "state"
            path = self._state(folder)
            with patch("cognition_agent_os.runner.require_initialized_ledger",
                       side_effect=self._drop_after_positive_preflight):
                with self.assertRaises(LedgerNotConfigured):
                    run_once(path, folder, folder)
            self.assertFalse(path.exists(), "Worker minted a database on missing authority")
            self.assertTrue(path.with_name("ledger-disappeared.sqlite").exists())

    def test_explicit_provision_and_existing_runtime_remain_legal(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "state"
            path = self._state(folder)
            self.assertEqual(run_once(path, folder, folder)["status"], "IDLE")
            task = register_native_goal(path, "Check this original owner goal")
            self.assertEqual(len(task), 32)
            self.assertEqual(len(register_native_goal(
                path, "Investigate a distinct owner goal")), 32)

    def test_no_runtime_imports_creation_connector(self):
        source = Path(__file__).resolve().parents[1] / "src" / "cognition_agent_os"
        # The CLI and session CLI alone keep the explicit-provisioning helper;
        # all other runtime modules can use the guarded existing-ledger API.
        approved_provisioners = {"cli.py", "session_cli.py", "ledger.py"}
        offenders = []
        for path in source.glob("*.py"):
            if path.name in approved_provisioners:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.ImportFrom)
                        and node.level == 1 and node.module == "ledger"):
                    for imported in node.names:
                        if imported.name == "connect":
                            offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [],
                         "runtime reintroduced a DB-creating connection")


if __name__ == "__main__":
    unittest.main()
