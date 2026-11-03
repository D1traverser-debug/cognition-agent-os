"""Owner-goal-negative, first-hand SQLite/file contracts for shared lifecycle gaps.

Source: frozen Draft PR #62 69c31c4. These regressions are intentionally RED
before fixing the shared creation/renewal/watch/source-commit boundary.
"""
from __future__ import annotations

from contextlib import closing
import math
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import (
    connect, initialize, alter_authority, create_task, claim_one,
    renew_claim, event, finalize_observed, LedgerNotConfigured,
)
from cognition_agent_os.watch import create_watch, poll_due_watches
from cognition_agent_os.runner import run_once
from cognition_agent_os import runner


class SystemicLifecycleAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'task.sqlite'
        self.fixtures = self.root / 'fixtures'
        self.fixtures.mkdir()
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        with closing(connect(self.path)) as db:
            initialize(db)

    def test_lease_renewal_is_monotone_and_preserves_old_worker(self):
        with closing(connect(self.path)) as db:
            task_id = create_task(db, {'kind': 'fixture'}, interval_seconds=0)
            task = claim_one(db, only_task_id=task_id, lease_seconds=3600)
            original_expiry = db.execute('SELECT lease_until FROM tasks WHERE task_id=?', (task_id,)).fetchone()[0]
            self.assertTrue(renew_claim(db, task, lease_seconds=1))
            new_expiry = db.execute('SELECT lease_until FROM tasks WHERE task_id=?', (task_id,)).fetchone()[0]
            self.assertGreaterEqual(new_expiry, original_expiry)

    def test_nonfinite_and_malformed_schedule_rejected_before_write(self):
        with closing(connect(self.path)) as db:
            for due in (float('inf'), float('-inf'), float('nan'), True, 'now'):
                with self.subTest(due=due), self.assertRaises(ValueError):
                    create_task(db, {'kind': 'fixture'}, due_at=due)
            for interval in (float('inf'), float('nan'), True, -1, '60', 1.5):
                with self.subTest(interval=interval), self.assertRaises(ValueError):
                    create_task(db, {'kind': 'fixture'}, interval_seconds=interval)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            # Large, but finite, and valid positive schedule must remain allowed.
            tid = create_task(db, {'kind': 'fixture'}, due_at=9999999999,
                              interval_seconds=86400)
            self.assertIsNotNone(tid)

    def test_legacy_nonfinite_interval_cannot_commit_verified_plus_zombie(self):
        with closing(connect(self.path)) as db:
            tid = create_task(db, {'kind': 'fixture'})
            t = claim_one(db, only_task_id=tid)
            db.execute('UPDATE tasks SET interval_seconds=? WHERE task_id=?',
                       (float('inf'), tid))
            db.commit()
            # Deliberately use the original cached claim: DB can be poisoned
            # by earlier version or corruption after it was claimed.
            result = finalize_observed(db, t, 'VERIFIED', decision='NO_CHANGE')
            self.assertNotEqual(result['status'], 'VERIFIED')
            children = db.execute('SELECT due_at FROM tasks WHERE parent_task=?', (tid,)).fetchall()
            self.assertFalse(children)

    def test_legacy_poisoned_recurring_task_is_quarantined_on_completion(self):
        # Simulate a pre-migration task that was claimed after an invalid
        # interval had already been stored, not only after a row mutation.
        with closing(connect(self.path)) as db:
            tid = create_task(db, {'kind': 'fixture'})
            db.execute('UPDATE tasks SET interval_seconds=? WHERE task_id=?',
                       (float('inf'), tid))
            db.commit()
            task = claim_one(db, only_task_id=tid)
            self.assertIsNotNone(task)
            reply = finalize_observed(db, task, 'VERIFIED', decision='NO_CHANGE')
            self.assertEqual(reply['status'], 'UNKNOWN')
            self.assertEqual(reply.get('reason'), 'INVALID_RECURRING_INTERVAL')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks WHERE parent_task=?',
                                        (tid,)).fetchone()[0], 0)

    def test_valid_recurring_task_remains_eligible(self):
        with closing(connect(self.path)) as db:
            tid = create_task(db, {'kind': 'fixture'}, interval_seconds=60)
            task = claim_one(db, only_task_id=tid)
            reply = finalize_observed(db, task, 'VERIFIED', decision='NO_CHANGE')
            self.assertEqual(reply['status'], 'VERIFIED')
            children = db.execute('SELECT interval_seconds, due_at,state FROM tasks '
                                  'WHERE parent_task=?', (tid,)).fetchall()
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0]['interval_seconds'], 60)
            self.assertEqual(children[0]['state'], 'PENDING')
            self.assertTrue(math.isfinite(children[0]['due_at']))

    def test_direct_watch_poll_is_readonly_on_nonexistent_database(self):
        missing = self.root / 'never_bootstrapped.sqlite'
        try:
            got = poll_due_watches(missing)
        except LedgerNotConfigured:
            got = 'NOT_CONFIGURED'
        self.assertIn(got, ([], 'NOT_CONFIGURED'))
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.joinpath('never_bootstrapped.sqlite-wal').exists())

    def test_revoked_watch_write_does_not_migrate_schema(self):
        with closing(connect(self.path)) as db:
            alter_authority(db, revoke=True)
            with self.assertRaises(PermissionError):
                create_watch(db, 'owner/repo', 'README.md')
            present = [x[0] for x in db.execute('SELECT name FROM sqlite_master WHERE name LIKE "watch_%"')]
            self.assertEqual(present, [])

    def test_failed_watch_registration_never_commits_callers_transaction(self):
        with closing(connect(self.path)) as writer, closing(connect(self.path)) as reader:
            alter_authority(writer, revoke=True)
            event(writer, 'test-owner', 'UNCOMMITTED_PREEXISTING_EVENT')
            self.assertEqual(reader.execute('SELECT count(*) FROM events WHERE kind=?',
                        ('UNCOMMITTED_PREEXISTING_EVENT',)).fetchone()[0], 0)
            with self.assertRaises(PermissionError):
                create_watch(writer, 'owner/repo', 'README.md')
            self.assertEqual(reader.execute('SELECT count(*) FROM events WHERE kind=?',
                        ('UNCOMMITTED_PREEXISTING_EVENT',)).fetchone()[0], 0)
            # The caller still controls rollback of its own unrelated work.
            writer.rollback()
            self.assertEqual(writer.execute('SELECT count(*) FROM events WHERE kind=?',
                        ('UNCOMMITTED_PREEXISTING_EVENT',)).fetchone()[0], 0)

    def test_valid_watch_registration_in_existing_transaction_is_caller_owned(self):
        with closing(connect(self.path)) as writer, closing(connect(self.path)) as reader:
            event(writer, 'test-owner', 'PREEXISTING_EVENT')
            wid = create_watch(writer, 'owner/repo', 'README.md')
            self.assertTrue(wid)
            # Authorized or not, a nested helper must not commit the caller's transaction.
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM events WHERE kind=?',
                        ('PREEXISTING_EVENT',)).fetchone()[0], 0)
            writer.rollback()
            self.assertEqual(writer.execute('SELECT count(*) FROM events WHERE kind=?',
                        ('PREEXISTING_EVENT',)).fetchone()[0], 0)
            self.assertEqual(writer.execute(
                'SELECT COUNT(*) FROM sqlite_master WHERE name="watch_sources"').fetchone()[0], 0)

    def test_initialize_does_not_commit_callers_unrelated_event(self):
        with closing(connect(self.path)) as writer, closing(connect(self.path)) as reader:
            event(writer, 'test-owner', 'UNCOMMITTED_BEFORE_REINITIALIZATION')
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM events WHERE kind=?',
                ('UNCOMMITTED_BEFORE_REINITIALIZATION',)).fetchone()[0], 0)
            with self.assertRaises(RuntimeError):
                initialize(writer)
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM events WHERE kind=?',
                ('UNCOMMITTED_BEFORE_REINITIALIZATION',)).fetchone()[0], 0)
            writer.rollback()

    def test_source_change_before_artifact_write_cannot_stage_unreviewed_output(self):
        old = self.fixtures / 'old.txt'
        new = self.fixtures / 'new.txt'
        old.write_bytes(b'old\n')
        new.write_bytes(b'new\n')
        with closing(connect(self.path)) as db:
            tid = create_task(db, {'kind': 'fixture', 'old': 'old.txt', 'new': 'new.txt'})
        original = runner.propose
        def mutate_after_plan(old_bytes, new_bytes, evidence):
            result = original(old_bytes, new_bytes, evidence)
            self.assertNotEqual(result['decision'], 'NO_CHANGE')
            new.write_bytes(b'changed-again\n')
            return result
        with patch.object(runner, 'propose', side_effect=mutate_after_plan):
            reply = run_once(self.path, self.workspace, self.fixtures,
                             only_task_id=tid)
        self.assertEqual(reply['status'], 'UNKNOWN')
        self.assertFalse((self.workspace / 'artifacts' / (tid + '.json')).exists())
        with closing(connect(self.path)) as db:
            row = db.execute('SELECT state,artifact_hash FROM tasks WHERE task_id=?',
                             (tid,)).fetchone()
            self.assertEqual(row['state'], 'UNKNOWN')
            self.assertIsNone(row['artifact_hash'])

    def test_watch_observe_without_schema_does_not_bootstrap(self):
        from cognition_agent_os.watch import observe_one
        with closing(connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master "
                "WHERE name='watch_sources'").fetchone())
        got = observe_one(self.path, 'a'*32)
        self.assertEqual(got['status'], 'NOT_DUE')
        with closing(connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master "
                "WHERE name='watch_sources'").fetchone())

    def test_watch_invalid_intervals_fail_typed_before_schema(self):
        with closing(connect(self.path)) as db:
            for bad in (True, 900.0, float('inf'), '900', None):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    create_watch(db, 'owner/repo', 'README.md', interval_seconds=bad)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master "
                "WHERE name='watch_sources'").fetchone()[0], 0)

    def test_fresh_no_change_verdict_cannot_ignore_source_drift_before_commit(self):
        old = self.fixtures / 'old.txt'
        new = self.fixtures / 'new.txt'
        old.write_bytes(b'same\n')
        new.write_bytes(b'same\n')
        with closing(connect(self.path)) as db:
            tid = create_task(db, {'kind': 'fixture', 'old': 'old.txt', 'new': 'new.txt'})
        actual = runner.propose
        def change_after_comparison(old_raw, new_raw, evidence):
            result = actual(old_raw, new_raw, evidence)
            self.assertEqual(result['decision'], 'NO_CHANGE')
            new.write_bytes(b'changed-after-read\n')
            return result
        with patch.object(runner, 'propose', side_effect=change_after_comparison):
            response = run_once(self.path, self.workspace, self.fixtures,
                                only_task_id=tid)
        self.assertNotEqual(response['status'], 'VERIFIED')
        with closing(connect(self.path)) as db:
            row = db.execute('SELECT state, decision FROM tasks WHERE task_id=?', (tid,)).fetchone()
            self.assertNotEqual(row['state'], 'VERIFIED')


if __name__ == '__main__':
    unittest.main()
