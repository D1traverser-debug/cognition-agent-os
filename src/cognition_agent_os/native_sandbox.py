"""Fail closed before model dispatch when native read-only enforcement is absent."""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

DENIAL_ERRNOS = frozenset({errno.EACCES, errno.EPERM, errno.EROFS})
READONLY_PROBE = (
    "from pathlib import Path\nimport json,sys\n"
    "nonce=Path(sys.argv[1]).read_text()\n"
    "try:\n    Path(sys.argv[2]).write_text('disposable sandbox probe')\n"
    "except OSError as exc:\n    print(json.dumps({'nonce':nonce,'errno':exc.errno}))\n"
    "else:\n    print(json.dumps({'nonce':nonce,'errno':None}))\n"
)


def verify_readonly_boundary(server, workspace: Path):
    """No inference or owner-file changes; only disposable canaries are created.

    This checks actual filesystem enforcement, not semantic goal alignment,
    confidentiality or network isolation. Never set up an account or silently
    select a weaker native sandbox to turn a rejection into success.
    """
    if os.name == "nt":
        status = server.request("windowsSandbox/readiness", None)
        if status.get("status") != "ready":
            raise RuntimeError("NATIVE_WINDOWS_SANDBOX_SETUP_REQUIRED: 请先在原生 Codex 中完成 Windows 沙箱配置；消息已保留，尚未发送模型。")
    with tempfile.TemporaryDirectory(prefix=".caos-sandbox-check-", dir=workspace) as tmp:
        probe = Path(tmp)
        original, target = probe / "read.txt", probe / "blocked.txt"
        nonce = secrets.token_hex(16)
        original.write_text(nonce, encoding="utf-8")
        result = server.request("command/exec", {
            "command": [sys.executable, "-E", "-P", "-c", READONLY_PROBE,
                        str(original), str(target)],
            "cwd": str(workspace), "sandboxPolicy": {"type": "readOnly"},
            "timeoutMs": 10000}, timeout=20)
        try:
            observed = json.loads(result.get("stdout", ""))
        except (ValueError, TypeError):
            observed = {}
        if (result.get("exitCode") != 0 or not isinstance(observed, dict)
                or observed.get("nonce") != nonce
                or type(observed.get("errno")) is not int
                or observed["errno"] not in DENIAL_ERRNOS
                or target.exists() or target.is_symlink()
                or original.read_text(encoding="utf-8") != nonce):
            raise RuntimeError("NATIVE_READONLY_BOUNDARY_UNVERIFIED: 未能确认原生只读隔离，已停止发送模型；消息已保留。")
    return {"status": "READONLY_FILESYSTEM_PROBE_PASSED", "model_inference": "NOT_RUN"}
