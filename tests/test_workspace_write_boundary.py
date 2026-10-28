"""Independent write-effect checks, not just a path-checker success flag."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os.runner import store_once


class WorkspaceWriteBoundaryTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Windows relative-handle creation remains an explicit release blocker")
    def test_directory_swapped_after_precheck_cannot_create_outside_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            top = Path(temp)
            workspace = top / "approved"
            outside = top / "outside"
            outside.mkdir()
            task_id = "a" * 32
            filename = task_id + ".json"
            original_open = os.open
            attacked = False

            def change_directory_before_create(path, flags, *args, **kwargs):
                nonlocal attacked
                if (not attacked and str(path).endswith(filename)
                    and flags & os.O_CREAT):
                    directory = workspace / "artifacts"
                    directory.rmdir()
                    directory.symlink_to(outside, target_is_directory=True)
                    attacked = True
                return original_open(path, flags, *args, **kwargs)

            with patch("os.open", change_directory_before_create):
                try:
                    store_once(workspace, task_id, b"authorized artifact bytes")
                except (OSError, ValueError, FileNotFoundError):
                    pass  # An interrupted safe write must fail closed.
            self.assertTrue(attacked, "the hostile race must actually execute")
            self.assertFalse((outside / filename).exists(),
                             "artifact creation must not escape the approved dirfd")

    def test_normal_bounded_write_and_immutable_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "approved"
            task_id = "b" * 32
            before = b"canonical artifact"
            digest = store_once(workspace, task_id, before)
            self.assertEqual(digest, store_once(workspace, task_id, before))
            self.assertEqual((workspace / "artifacts" / (task_id + ".json")).read_bytes(), before)
            with self.assertRaises(Exception):
                store_once(workspace, task_id, b"tampered")
