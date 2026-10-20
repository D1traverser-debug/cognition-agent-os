"""P3 source-watch behavioral tests with independent SQLite connections and fault injection."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.source import SourceUnavailable, git_blob_sha, github_public_branch_head
from cognition_agent_os.watch import create_watch, observe_one, poll_due_watches

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.db_path = self.base / "tasks.sqlite"
        db = connect(self.db_path)
        initialize(db)
        db.close()
        self.watch_id = self.seed()

    def seed(self, **opts):
        db = connect(self.db_path)
        try:
            return create_watch(db, "D1traverser-debug/cognition-agent-os",
                                "README.md", "main", **opts)
        finally:
            db.close()

    def db_state(self):
        db = connect(self.db_path)
        try:
            watch = dict(db.execute("SELECT * FROM watch_sources").fetchone())
            tasks = [dict(row) for row in db.execute("SELECT * FROM tasks")]
            observed = [dict(row) for row in db.execute("SELECT * FROM watch_observations")]
            return watch, tasks, observed
        finally:
            db.close()

    def due(self):
        db = connect(self.db_path)
        db.execute("UPDATE watch_sources SET due_at=0")
        db.commit()
        db.close()

    def poll(self, sha, data, *, due=False):
        if due:
            self.due()
        with patch("cognition_agent_os.watch.github_public_branch_head", return_value=sha):
            with patch("cognition_agent_os.watch.github_public_snapshot", return_value=data):
                return observe_one(self.db_path, self.watch_id)

    def test_baseline_same_content_new_commit_and_content_change(self):
        self.assertEqual(self.poll(SHA_A, b"v1")["status"], "BASELINED")
        self.assertEqual(self.poll(SHA_B, b"v1", due=True)["status"], "NO_CONTENT_CHANGE")
        result = self.poll(SHA_C, b"v2", due=True)
        self.assertEqual(result["status"], "TASK_ENQUEUED")
        current, tasks, observed = self.db_state()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(observed), 3)
        self.assertEqual(current["baseline_ref"], SHA_C)
        self.assertEqual(current["baseline_blob"], git_blob_sha(b"v2"))
        self.assertEqual(json.loads(tasks[0]["source_spec"]), {
            "kind": "github", "repo": "D1traverser-debug/cognition-agent-os",
            "path": "README.md", "old_ref": SHA_B, "new_ref": SHA_C})
        # A second tick or restart must not emit a duplicate proposal.
        self.assertEqual(self.poll(SHA_C, b"v2")["status"], "NOT_DUE")
        self.assertEqual(len(self.db_state()[1]), 1)

    def test_restart_worker_executes_pinned_change_and_no_duplicate(self):
        self.poll(SHA_A, b"v1")
        self.poll(SHA_B, b"v2", due=True)
        self.due()
        with patch("cognition_agent_os.watch.github_public_branch_head", return_value=SHA_B), \
             patch("cognition_agent_os.watch.github_public_snapshot", return_value=b"v2"), \
             patch("cognition_agent_os.source.github_public_snapshot",
                   side_effect=lambda repo, path, sha: b"v1" if sha == SHA_A else b"v2"):
            output = run_tick(self.db_path, self.base / "workspace", self.base / "fx")
            self.assertEqual(output["processed"], 1)
            self.assertEqual(output["tasks"][0]["status"], "NEEDS_REVIEW")
            again = run_tick(self.db_path, self.base / "workspace", self.base / "fx")
            self.assertEqual(again["processed"], 0)
        self.assertEqual(len(self.db_state()[1]), 1)

    def test_source_failure_keeps_cursor_and_later_recovers(self):
        self.poll(SHA_A, b"v1")
        self.due()
        with patch("cognition_agent_os.watch.github_public_branch_head",
                   side_effect=SourceUnavailable("429")):
            failed = observe_one(self.db_path, self.watch_id)
        self.assertEqual(failed["status"], "SOURCE_UNAVAILABLE")
        self.assertEqual(self.db_state()[0]["baseline_ref"], SHA_A)
        self.assertEqual(len(self.db_state()[1]), 0)
        self.assertEqual(self.poll(SHA_B, b"v2", due=True)["status"], "TASK_ENQUEUED")
        self.assertEqual(len(self.db_state()[1]), 1)

    def test_revocation_before_poll_and_during_fetch(self):
        self.poll(SHA_A, b"v1")
        self.due()

        def revoke_then_return(*args):
            db = connect(self.db_path)
            alter_authority(db, revoke=True)
            db.close()
            return SHA_B

        with patch("cognition_agent_os.watch.github_public_branch_head", side_effect=revoke_then_return), \
             patch("cognition_agent_os.watch.github_public_snapshot", return_value=b"v2"):
            outcome = observe_one(self.db_path, self.watch_id)
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(self.db_state()[0]["baseline_ref"], SHA_A)
        self.assertEqual(len(self.db_state()[1]), 0)
        with patch("cognition_agent_os.watch.github_public_branch_head",
                   side_effect=AssertionError("revoked watch must not poll")):
            self.assertEqual(observe_one(self.db_path, self.watch_id)["status"], "BLOCKED")

    def test_goal_change_blocks_current_watch(self):
        self.poll(SHA_A, b"v1")
        self.due()
        db = connect(self.db_path)
        alter_authority(db, goal_change=True)
        db.close()
        self.assertEqual(observe_one(self.db_path, self.watch_id)["status"], "BLOCKED")
        self.assertEqual(len(self.db_state()[1]), 0)

    def test_atomic_rollback_on_queue_failure_then_retry_once(self):
        self.poll(SHA_A, b"v1")
        self.due()
        import cognition_agent_os.watch as watcher
        original = watcher.create_task

        def queue_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("crash before commit")

        with patch.object(watcher, "github_public_branch_head", return_value=SHA_B), \
             patch.object(watcher, "github_public_snapshot", return_value=b"v2"), \
             patch.object(watcher, "create_task", side_effect=queue_then_fail):
            with self.assertRaises(RuntimeError):
                observe_one(self.db_path, self.watch_id)
        watch, tasks, observed = self.db_state()
        self.assertEqual(watch["baseline_ref"], SHA_A)
        self.assertEqual(len(tasks), 0)
        self.assertEqual(len(observed), 1)
        self.assertEqual(self.poll(SHA_B, b"v2")["status"], "TASK_ENQUEUED")

    def test_concurrent_poll_never_duplicates_or_regresses(self):
        self.poll(SHA_A, b"v1")
        self.due()
        barrier = threading.Barrier(2)
        results = []
        failures = []

        def fake_snapshot(*args):
            barrier.wait(timeout=5)
            return b"v2"

        def worker():
            try:
                r = observe_one(self.db_path, self.watch_id)
                results.append(r["status"])
            except BaseException as exc:
                failures.append(exc)

        with patch("cognition_agent_os.watch.github_public_branch_head", return_value=SHA_B), \
             patch("cognition_agent_os.watch.github_public_snapshot", side_effect=fake_snapshot):
            a = threading.Thread(target=worker)
            b = threading.Thread(target=worker)
            a.start()
            b.start()
            a.join(timeout=10)
            b.join(timeout=10)
        self.assertFalse(failures)
        self.assertEqual(sorted(results), ["STALE_OBSERVATION", "TASK_ENQUEUED"])
        self.assertEqual(len(self.db_state()[1]), 1)

    def test_corruption_same_commit_new_content_refused(self):
        self.poll(SHA_A, b"v1")
        result = self.poll(SHA_A, b"tampered", due=True)
        self.assertEqual(result["status"], "INTEGRITY_CONFLICT")
        self.assertEqual(self.db_state()[0]["baseline_blob"], git_blob_sha(b"v1"))
        self.assertEqual(len(self.db_state()[1]), 0)

    def test_limits_and_input_validation(self):
        db = connect(self.db_path)
        try:
            for branch in ["../main", "feature/path", "weird:ref", "bad..ref"]:
                with self.assertRaises(ValueError):
                    create_watch(db, "owner/repo", "README.md", branch)
            with self.assertRaises(ValueError):
                create_watch(db, "owner/repo", "../secret", "main")
            with self.assertRaises(ValueError):
                create_watch(db, "owner/repo", "README.md", "main", interval_seconds=10)
            create_watch(db, "org/a", "readme", "main")
            create_watch(db, "org/b", "readme", "main")
            create_watch(db, "org/c", "readme", "main")
            with self.assertRaises(ValueError):
                create_watch(db, "org/d", "readme", "main")
        finally:
            db.close()

    def test_branch_head_json_is_identity_checked(self):
        from cognition_agent_os import source
        from unittest.mock import MagicMock
        good = json.dumps({"name":"main", "commit":{"sha":SHA_A}}).encode()
        bad = json.dumps({"name":"evil", "commit":{"sha":SHA_A}}).encode()
        def response(raw):
            ctx = MagicMock()
            ctx.__enter__.return_value.read.return_value = raw
            return ctx
        with patch.object(source, "urlopen", return_value=response(good)):
            self.assertEqual(github_public_branch_head("owner/repo", "main"), SHA_A)
        with patch.object(source, "urlopen", return_value=response(bad)):
            with self.assertRaises(SourceUnavailable):
                github_public_branch_head("owner/repo", "main")

    def test_poll_due_watches_only_once_in_same_host_cycle(self):
        with patch("cognition_agent_os.watch.github_public_branch_head", return_value=SHA_A), \
             patch("cognition_agent_os.watch.github_public_snapshot", return_value=b"v1"):
            result = poll_due_watches(self.db_path)
        self.assertEqual([v["status"] for v in result], ["BASELINED"])
        self.assertEqual(poll_due_watches(self.db_path), [])


if __name__ == "__main__":
    unittest.main()
