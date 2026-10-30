"""Independent write-effect checks, not just a path-checker success flag."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os import isolated_filesystem
from cognition_agent_os.runner import store_once


class WorkspaceWriteBoundaryTests(unittest.TestCase):
    def test_directory_swapped_after_precheck_cannot_create_outside_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            top = Path(temp)
            workspace = top / "approved"
            outside = top / "outside"
            workspace.mkdir()
            outside.mkdir()
            task_id = "a" * 32
            filename = task_id + ".json"
            directory = workspace / "artifacts"
            attacked = False

            if os.name == "nt":
                real_create = isolated_filesystem._nt_create_file_relative

                def replace_before_relative_create(parent, name, **kwargs):
                    nonlocal attacked
                    if (not attacked and name == filename
                        and kwargs.get("disposition") == isolated_filesystem._WIN_FILE_CREATE):
                        attacked = True
                        # The artifacts directory handle is held without
                        # FILE_SHARE_DELETE, so this replacement must fail.
                        try:
                            directory.rmdir()
                        except OSError:
                            pass
                        try:
                            directory.symlink_to(outside, target_is_directory=True)
                        except OSError:
                            pass
                    return real_create(parent, name, **kwargs)

                with patch.object(
                    isolated_filesystem,
                    "_nt_create_file_relative",
                    side_effect=replace_before_relative_create,
                ):
                    try:
                        store_once(workspace, task_id, b"authorized artifact bytes")
                    except (OSError, ValueError, FileNotFoundError):
                        pass
            else:
                original_open = os.open

                def change_directory_before_create(path, flags, *args, **kwargs):
                    nonlocal attacked
                    if (not attacked and str(path).endswith(filename)
                        and flags & os.O_CREAT):
                        attacked = True
                        directory.rmdir()
                        directory.symlink_to(outside, target_is_directory=True)
                    return original_open(path, flags, *args, **kwargs)

                with patch("os.open", change_directory_before_create):
                    try:
                        store_once(workspace, task_id, b"authorized artifact bytes")
                    except (OSError, ValueError, FileNotFoundError):
                        pass

            self.assertTrue(attacked, "the hostile race must actually execute")
            self.assertFalse((outside / filename).exists(),
                             "artifact creation must not escape the approved dirfd")
            if os.name == "nt":
                self.assertTrue(directory.is_dir())
                self.assertFalse(directory.is_symlink())
                self.assertTrue((directory / filename).is_file())

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
