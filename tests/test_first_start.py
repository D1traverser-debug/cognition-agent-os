"""Bootstrap ownership and repeat-start invariants; no downloads in unit tests."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("caos_first_start", ROOT / "start_caos.py")
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


class FirstStartTests(unittest.TestCase):
    def test_readonly_check_does_not_create_runtime_or_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, runtime = Path(tmp) / "private 中文", Path(tmp) / "runtime"
            result = subprocess.run([sys.executable, str(ROOT / "start_caos.py"),
                "--state", str(state), "--runtime-dir", str(runtime), "--check"],
                capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["runtime_current"])
            self.assertFalse(state.exists())
            self.assertFalse(runtime.exists())

    def test_existing_unowned_runtime_is_never_repurposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "owner-file").write_text("keep")
            with self.assertRaisesRegex(ValueError, "不属于"):
                start.provision_runtime(path)
            self.assertEqual((path / "owner-file").read_text(), "keep")

    def test_source_match_reuses_environment_but_missing_python_repairs_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "installation.json").write_text(json.dumps({
                "format": start.FORMAT, "source_revision": start.source_revision()}))
            python = start.runtime_python(runtime)
            python.parent.mkdir(parents=True)
            python.write_text("test stub, never executed")
            with patch.object(start.subprocess, "run") as run, patch("builtins.print"):
                start.provision_runtime(runtime)
                run.assert_not_called()
                python.unlink()
                start.provision_runtime(runtime)
                self.assertEqual(run.call_count, 2)  # recreate environment AND install package
                self.assertIn("--force-reinstall", run.call_args_list[-1].args[0])

    def test_rejected_client_does_not_fall_back_or_download(self):
        with patch.object(start.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "指定"):
                start.select_client(Path("unused"), "explicit-missing-client")

    def test_cached_client_damage_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(start.shutil, "which", return_value=None):
            runtime = Path(tmp)
            (runtime / "client").write_bytes(b"changed")
            (runtime / "native-client.json").write_text(json.dumps({
                "relative_path": "client", "executable_sha256": "0" * 64}))
            with self.assertRaisesRegex(ValueError, "不匹配"):
                start.select_client(runtime, None)

    def test_private_state_cannot_be_inside_git_checkout(self):
        with patch.object(start, "provision_runtime") as provision:
            self.assertEqual(start.main(["--state", str(ROOT / "unsafe-private"), "--check"]), 2)
            provision.assert_not_called()

    def test_child_python_does_not_inherit_path_injection(self):
        with patch.dict(os.environ, {"PYTHONPATH": "old-package", "PYTHONHOME": "old-home"}):
            env = start.child_environment()
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["PYTHONUTF8"], "1")


if __name__ == "__main__":
    unittest.main()
