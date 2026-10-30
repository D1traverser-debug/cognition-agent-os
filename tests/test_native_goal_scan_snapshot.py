"""Regression: a cognitive goal scan cannot pin WAL while model work runs."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.native_local_planner import _iter_native_goal_roots


class NativeGoalScanSnapshotTests(unittest.TestCase):
    def test_generator_releases_each_page_before_exposing_goal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.sqlite"
            with closing(connect(path)) as db:
                initialize(db)
                db.commit()
            root = register_native_goal(
                path, "Review one owner goal without holding a read transaction")
            driver = sqlite3.connect
            closed = []

            class Probe:
                def __init__(self, db):
                    self.db = db

                def execute(self, *args, **kwargs):
                    return self.db.execute(*args, **kwargs)

                def close(self):
                    closed.append(self.db.in_transaction)
                    self.db.close()

            def track(database, *args, **kwargs):
                db = driver(database, *args, **kwargs)
                if isinstance(database, str) and "?mode=ro" in database:
                    return Probe(db)
                return db

            with patch("cognition_agent_os.native_local_planner.sqlite3.connect",
                       side_effect=track):
                scanner = _iter_native_goal_roots(path)
                first = next(scanner)
                self.assertEqual(first[0], root)
                # Crucial discriminator: on the prior generator implementation
                # the connection remained open until the consumer resumed it.
                self.assertEqual(closed, [True])
                scanner.close()

            # Fresh independent read observes the registered root; no writer,
            # extra scheduler or model call was added by the test.
            with closing(driver(str(path))) as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE task_id=?",
                    (root,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
