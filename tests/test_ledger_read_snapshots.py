"""Real SQLite WAL concurrency proof for the shared read-only snapshot."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cognition_agent_os.ledger import (
    LedgerNotConfigured, connect, initialize, readonly_snapshot,
)


class ReadonlySnapshotTests(unittest.TestCase):
    def test_multi_select_authority_is_consistent_and_fresh_request_rechecks(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "one-ledger.sqlite"
            with closing(connect(path)) as db:
                initialize(db)
                db.commit()

            with readonly_snapshot(path) as reader:
                self.assertTrue(reader.in_transaction)
                first = reader.execute(
                    "SELECT grant_rev,write_allowed FROM authority WHERE singleton=1"
                ).fetchone()
                with closing(sqlite3.connect(str(path), timeout=5)) as writer:
                    writer.execute(
                        "UPDATE authority SET grant_rev=grant_rev+1,"
                        "write_allowed=0 WHERE singleton=1")
                    writer.commit()
                second = reader.execute(
                    "SELECT grant_rev,write_allowed FROM authority WHERE singleton=1"
                ).fetchone()
                self.assertEqual(tuple(first), tuple(second))
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("UPDATE authority SET write_allowed=1")

            with readonly_snapshot(path) as fresh:
                current = fresh.execute(
                    "SELECT grant_rev,write_allowed FROM authority WHERE singleton=1"
                ).fetchone()
                self.assertEqual(current["write_allowed"], 0)
                self.assertEqual(current["grant_rev"], first["grant_rev"] + 1)

    def test_missing_authority_never_creates_sqlite(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "never-bootstrapped.sqlite"
            with self.assertRaises(LedgerNotConfigured):
                with readonly_snapshot(missing):
                    self.fail("Missing ledger must not yield an active snapshot")
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
