"""Adversarial cross-entrypoint proof: no execution entry may mint authority.

A test authored independently from the runner implementation: the public
run_once path must not bootstrap a fresh or malformed ledger. The host and CLI
already treat initialization as an explicit authority-bearing operation.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from cognition_agent_os.host import HostNotConfigured, run_tick
from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.runner import run_once


class ExplicitAuthorizationAtEveryEntrypoint(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "new" / "state.sqlite"
        self.workspace = self.root / "workspace"
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()

    def test_direct_runner_never_creates_ledger_or_default_grant(self):
        with self.assertRaisesRegex(RuntimeError, "initialized|configured|authority"):
            run_once(self.db, self.workspace, self.fixtures)
        self.assertFalse(self.db.exists())
        self.assertFalse(self.db.parent.exists())

    def test_existing_empty_sqlite_file_is_not_upgraded_on_execution(self):
        self.db.parent.mkdir()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE preexisting (id INTEGER)")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "initialized|configured|authority"):
            run_once(self.db, self.workspace, self.fixtures)
        with closing(sqlite3.connect(self.db)) as db:
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"preexisting"})

    def test_initialized_database_continues_to_run_and_idle(self):
        with closing(connect(self.db)) as db:
            initialize(db)
        self.assertEqual(run_once(self.db, self.workspace, self.fixtures)["status"], "IDLE")
        self.assertEqual(run_tick(self.db, self.workspace, self.fixtures)["status"], "IDLE")

    def test_revocation_not_reenabled_by_direct_runner_or_host(self):
        with closing(connect(self.db)) as db:
            initialize(db)
            alter_authority(db, revoke=True)
        self.assertEqual(run_once(self.db, self.workspace, self.fixtures)["status"], "IDLE")
        self.assertEqual(run_tick(self.db, self.workspace, self.fixtures)["status"], "IDLE")
        with closing(sqlite3.connect(self.db)) as db:
            grant = db.execute("SELECT write_allowed,grant_rev FROM authority WHERE singleton=1").fetchone()
        self.assertEqual(grant, (0, 2))


if __name__ == "__main__":
    unittest.main()
