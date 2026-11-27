"""The operator-only global ledger marker must agree at every authority entry.

This is a scope/authorization boundary, not an autonomous cognition test.
"""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.effect_contract import managed
from cognition_agent_os.ledger import (
    connect, create_task, event, initialize, managed_ledger_active)
from cognition_agent_os.session_archive import export_session


class ManagedLedgerMarkerScope(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / "state"
        (self.state / "sources").mkdir(parents=True)
        (self.state / "workspace").mkdir()
        self.db_path = self.state / "ledger.sqlite"
        with closing(connect(self.db_path)) as db:
            initialize(db)

    def test_spoofed_root_event_cannot_switch_ledger_or_other_roots(self):
        with closing(connect(self.db_path)) as db:
            event(db, "unrelated-root", "COGNITION_MANAGED_LEDGER",
                  {"version": 1})
            db.commit()
            self.assertFalse(managed_ledger_active(db))
            self.assertFalse(managed(db, "unrelated-root"))
            self.assertFalse(managed(db, "another-root"))
            # A forged marker must not silently apply the global native-only
            # admission mode to lawful pre-existing legacy API usage.
            self.assertEqual(len(create_task(db, {"kind": "fixture"})), 32)
        with self.assertRaisesRegex(ValueError,
                                    "SNAPSHOT_REQUIRES_MANAGED_LEDGER"):
            export_session(self.state, self.root / "unauthorized.zip")

    def test_canonical_operator_marker_is_global_and_fences_old_writes(self):
        with closing(connect(self.db_path)) as db:
            event(db, "operator", "COGNITION_MANAGED_LEDGER",
                  {"version": 1})
            db.commit()
            self.assertTrue(managed_ledger_active(db))
            self.assertTrue(managed(db, "one-root"))
            self.assertTrue(managed(db, "another-root"))
            with self.assertRaisesRegex(
                    PermissionError, "MANAGED_LEDGER_REQUIRES_NATIVE_ADMISSION"):
                create_task(db, {"kind": "fixture"})

    def test_root_local_marker_never_grants_other_roots(self):
        with closing(connect(self.db_path)) as db:
            event(db, "one-root", "COGNITION_MANAGED", {"version": 1})
            db.commit()
            self.assertFalse(managed_ledger_active(db))
            self.assertTrue(managed(db, "one-root"))
            self.assertFalse(managed(db, "another-root"))


if __name__ == "__main__":
    unittest.main()
