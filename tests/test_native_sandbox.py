import errno
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.native_sandbox import verify_readonly_boundary
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from measure_native_execution_boundary import WRITE_PROBE


class BoundaryChecks(unittest.TestCase):
    def test_real_probe_classifies_only_permission_and_readonly_denials(self):
        for number in (errno.EACCES, errno.EPERM, errno.EROFS, errno.ENOENT, errno.ENOSPC):
            with self.subTest(errno=number):
                prefix = "from pathlib import Path\n" + (
                    "def reject(*a,**k): raise OSError(%d,'test')\n" % number) + "Path.write_text=reject\n"
                result = subprocess.run([sys.executable, "-c", prefix + WRITE_PROBE, "ignored", "x"],
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 73, number in (errno.EACCES, errno.EPERM, errno.EROFS))

    def test_counterfeit_success_crash_and_unknown_errno_fail_closed(self):
        for mode in ("legal", "write_then_deny", "crash", "unknown_errno", "wrong_nonce"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                class Peer:
                    def request(self, method, params, **kwargs):
                        if method == "windowsSandbox/readiness":
                            return {"status": "ready"}
                        original, target = map(Path, params["command"][-2:])
                        if mode == "write_then_deny":
                            target.write_text("unexpected")
                        return {"exitCode": 1 if mode == "crash" else 0,
                                "stdout": json.dumps({"nonce": "wrong" if mode == "wrong_nonce" else original.read_text(),
                                    "errno": errno.ENOSPC if mode == "unknown_errno" else errno.EROFS})}
                if mode == "legal":
                    self.assertEqual(verify_readonly_boundary(Peer(), Path(tmp))["status"],
                                     "READONLY_FILESYSTEM_PROBE_PASSED")
                else:
                    with self.assertRaisesRegex(RuntimeError, "NATIVE_READONLY_BOUNDARY_UNVERIFIED"):
                        verify_readonly_boundary(Peer(), Path(tmp))
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_windows_without_ready_sandbox_never_executes_probe_or_setup(self):
        class Peer:
            calls = []
            def request(self, method, params, **kwargs):
                self.calls.append(method)
                return {"status": "notConfigured"}
        peer = Peer()
        workspace = Path(".")
        with patch("cognition_agent_os.native_sandbox.os.name", "nt"), \
                self.assertRaisesRegex(RuntimeError, "NATIVE_WINDOWS_SANDBOX_SETUP_REQUIRED"):
            verify_readonly_boundary(peer, workspace)
        self.assertEqual(peer.calls, ["windowsSandbox/readiness"])


if __name__ == "__main__":
    unittest.main()
