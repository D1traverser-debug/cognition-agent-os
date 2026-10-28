"""Reproduce the sibling staged-file escape at the actual adapter entrypoints.

The attacker replaces the last staging directory between preliminary path checks
and O_EXCL creation. The test asserts real filesystem effects, not a checker flag.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os.sandbox_effect import _atomic_stage as sandbox_stage
from cognition_agent_os.repair_oracle import _stage_patch as repair_stage
from cognition_agent_os.pipeline_oracle import _stage as pipeline_stage
from cognition_agent_os.repo_repair import _stage as repo_stage


@unittest.skipIf(os.name == "nt", "Windows hostile mutable-root write safety is not yet independently certified")
class SiblingStagingEscapes(unittest.TestCase):
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
            original_open = os.open
            injected = False

            def redirect_staging_before_create(path, flags, *args, **kwargs):
                nonlocal injected
                if (not injected and str(path).endswith(filename)
                    and flags & os.O_CREAT):
                    staging.rmdir()
                    staging.symlink_to(outside, target_is_directory=True)
                    injected = True
                return original_open(path, flags, *args, **kwargs)

            with patch("os.open", redirect_staging_before_create):
                try:
                    operation(workspace, task_id)
                except (OSError, ValueError):
                    pass  # Fail-closed is an acceptable interrupted write.
            self.assertTrue(injected, f"{family}: attack did not run")
            self.assertFalse((outside / filename).exists(),
                             f"{family}: unapproved external file was created")

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


if __name__ == "__main__":
    unittest.main()
