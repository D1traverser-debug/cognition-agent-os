"""Reproduce staging-directory replacement at the actual adapter entrypoints.

The attacker attempts to remove and replace the last staging directory between
its open and the final create. POSIX must remain anchored to its dirfd. Windows
must keep the directory handle open without FILE_SHARE_DELETE and create the
file relative to that handle.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os import isolated_filesystem
from cognition_agent_os.sandbox_effect import _atomic_stage as sandbox_stage
from cognition_agent_os.repair_oracle import _stage_patch as repair_stage
from cognition_agent_os.pipeline_oracle import _stage as pipeline_stage
from cognition_agent_os.repo_repair import _stage as repo_stage


class SiblingStagingEscapes(unittest.TestCase):
    def _attempt_swap_before_create(self, staging: Path, outside: Path,
                                    filename: str, operation) -> bool:
        injected = False
        if os.name == "nt":
            real_create = isolated_filesystem._nt_create_file_relative

            def replace_before_relative_create(parent, name, **kwargs):
                nonlocal injected
                if (not injected and name == filename
                    and kwargs.get("disposition") == isolated_filesystem._WIN_FILE_CREATE):
                    injected = True
                    # On Windows the pinned directory handle intentionally
                    # denies FILE_SHARE_DELETE, so this path replacement must
                    # fail while the native create still succeeds in-place.
                    try:
                        staging.rmdir()
                    except OSError:
                        pass
                    try:
                        staging.symlink_to(outside, target_is_directory=True)
                    except OSError:
                        pass
                return real_create(parent, name, **kwargs)

            with patch.object(
                isolated_filesystem,
                "_nt_create_file_relative",
                side_effect=replace_before_relative_create,
            ):
                try:
                    operation()
                except (OSError, ValueError):
                    pass
        else:
            original_open = os.open

            def redirect_staging_before_create(path, flags, *args, **kwargs):
                nonlocal injected
                if (not injected and str(path).endswith(filename)
                    and flags & os.O_CREAT):
                    injected = True
                    staging.rmdir()
                    staging.symlink_to(outside, target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)

            with patch("os.open", redirect_staging_before_create):
                try:
                    operation()
                except (OSError, ValueError):
                    pass

        return injected

    def _assert_no_escape(self, family: str, filename: str, operation):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workspace = base / "approved"
            outside = base / "outside"
            workspace.mkdir()
            outside.mkdir()
            task_id = "e" * 32
            parts = {
                "sandbox": ["sandbox"],
                "repair_lab": ["repair_lab"],
                "pipeline_lab": ["pipeline_lab", task_id],
                "repo_lab": ["repo_lab", task_id],
            }[family]
            staging = workspace.joinpath(*parts)

            injected = self._attempt_swap_before_create(
                staging, outside, filename,
                lambda: operation(workspace, task_id),
            )
            self.assertTrue(injected, f"{family}: attack did not reach final create")
            self.assertFalse((outside / filename).exists(),
                             f"{family}: unapproved external file was created")
            if os.name == "nt":
                self.assertTrue(staging.is_dir(), f"{family}: pinned staging directory was replaced")
                self.assertFalse(staging.is_symlink(), f"{family}: staging path became a symlink")
                self.assertTrue((staging / filename).is_file(),
                                f"{family}: approved relative create did not complete")
            else:
                self.assertTrue(staging.is_symlink(),
                                f"{family}: POSIX attack did not replace the path")

    def test_sandbox_effect_cannot_escape(self):
        self._assert_no_escape(
            "sandbox", "e" * 32 + ".candidate",
            lambda w, tid: sandbox_stage(w, tid, b"candidate"))

    def test_repair_oracle_cannot_escape(self):
        self._assert_no_escape(
            "repair_lab", "e" * 32 + ".py",
            lambda w, tid: repair_stage(w, tid, b"candidate"))

    def test_pipeline_oracle_cannot_escape(self):
        self._assert_no_escape(
            "pipeline_lab", "left.py",
            lambda w, tid: pipeline_stage(w, tid, ["left.py"], [b"candidate"]))

    def test_repo_repair_cannot_escape(self):
        self._assert_no_escape(
            "repo_lab", "left.py",
            lambda w, tid: repo_stage(w, tid, {"left.py": b"candidate"}))

    def test_preexisting_reparse_staging_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workspace = base / "approved"
            outside = base / "outside"
            workspace.mkdir()
            outside.mkdir()
            staging = workspace / "sandbox"
            try:
                staging.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink creation unavailable: {exc}")

            task_id = "f" * 32
            with self.assertRaises(OSError):
                sandbox_stage(workspace, task_id, b"candidate")
            self.assertFalse((outside / (task_id + ".candidate")).exists())


if __name__ == "__main__":
    unittest.main()
