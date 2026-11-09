"""Probe the existing native sandbox before considering general local execution.

Only disposable files are touched. No model, owner state, credentials, account
configuration or production permission is changed. PASS establishes a limited
filesystem boundary, not semantic authorization or a completed CAOS task.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

from cognition_agent_os.client_chat import AppServer
from cognition_agent_os.native_sandbox import verify_readonly_boundary
from verify_codex_app_server import download

DENIED = 73
WRITE_PROBE = (
    "from pathlib import Path\nimport sys,errno\n"
    "try:\n    Path(sys.argv[1]).write_text(sys.argv[2])\n"
    "except OSError as exc:\n"
    "    if exc.errno in (errno.EACCES,errno.EPERM,errno.EROFS): sys.exit(73)\n"
    "    raise\n"
)


def judge(cases):
    """Require an allowed operation AND denied neighbors with independent bytes."""
    checks = {
        "allowed_write_completed": cases["allowed"]["exitCode"] == 0,
        "allowed_bytes_read_back": cases["allowed"]["bytes_match"],
        "readonly_write_rejected": cases["readonly"]["exitCode"] == DENIED,
        "readonly_left_no_file": cases["readonly"]["unchanged"],
        "sibling_write_rejected": cases["sibling"]["exitCode"] == DENIED,
        "sibling_bytes_unchanged": cases["sibling"]["unchanged"],
    }
    if "symlink" in cases:
        checks["symlink_write_rejected"] = cases["symlink"]["exitCode"] == DENIED
        checks["symlink_target_unchanged"] = cases["symlink"]["unchanged"]
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "symlink_boundary": "TESTED" if "symlink" in cases else "NOT_TESTED",
            "model_inference": "NOT_RUN", "product_ready": False,
            "goal_alignment_and_revocation": "NOT_TESTED",
            "network_and_read_confidentiality": "NOT_TESTED"}


def measure(client, base, *, windows_sandbox=None, receipt=None):
    # Retain observations at their boundary even when a later RPC fails.
    # These RPCs contain only this disposable probe's fixed code and paths.
    receipt = receipt if receipt is not None else {}
    receipt["native_rpc_errors"] = []
    class ObservedServer(AppServer):
        def receive(self, deadline):
            message = super().receive(deadline)
            if isinstance(message.get("error"), dict):
                error = message["error"]
                receipt["native_rpc_errors"].append({"code": error.get("code"),
                    "message": str(error.get("message", ""))[:2000]})
            return message
    workspace = base / "candidate workspace 中文"
    workspace.mkdir()
    sibling = base / "protected-sibling.txt"
    original = secrets.token_hex(16).encode()
    sibling.write_bytes(original)
    token = secrets.token_hex(16)
    readonly_target, allowed_target = workspace / "readonly.txt", workspace / "allowed.txt"
    policy = {"type": "workspaceWrite", "writableRoots": [str(workspace)],
              "networkAccess": False, "excludeSlashTmp": True,
              "excludeTmpdirEnvVar": True}
    argv = [client, "app-server", "--listen", "stdio://"]
    if windows_sandbox:
        argv.extend(["-c", 'windows.sandbox=' + json.dumps(windows_sandbox)])
    server = ObservedServer(argv, workspace, timeout=30)
    cases = {}
    receipt["cases"] = cases
    try:
        server.request("initialize", {"clientInfo": {
            "name": "caos_boundary_probe", "version": "0.0.1"}})
        server.send({"method": "initialized", "params": {}})
        try:
            entry_preflight = verify_readonly_boundary(server, workspace)
        except RuntimeError as exc:
            entry_preflight = {"status": "BLOCKED", "reason": str(exc)}
        receipt["production_entry_preflight"] = entry_preflight

        def write(path, selected_policy):
            receipt["last_probe_policy"] = selected_policy
            # Fixed probe code and argv; never execute model/source-provided code.
            result = server.request("command/exec", {
                "command": [sys.executable, "-E", "-P", "-c",
                    WRITE_PROBE,
                    str(path), token],
                "cwd": str(workspace), "sandboxPolicy": selected_policy,
                "timeoutMs": 10000}, timeout=20)
            return {"exitCode": result["exitCode"],
                    "stdout": result.get("stdout", "")[-2000:],
                    "stderr": result.get("stderr", "")[-2000:]}

        cases["readonly"] = {**write(readonly_target, {"type": "readOnly"}),
                             "unchanged": not readonly_target.exists()}
        cases["allowed"] = {**write(allowed_target, policy),
                            "bytes_match": allowed_target.is_file()
                            and allowed_target.read_bytes() == token.encode()}
        cases["sibling"] = {**write(sibling, policy),
                            "unchanged": sibling.read_bytes() == original}
        # A missing symlink facility must not silently become a passed case.
        link = workspace / "escape-link"
        try:
            link.symlink_to(sibling)
        except OSError:
            pass
        else:
            cases["symlink"] = {**write(link, policy),
                                "unchanged": sibling.read_bytes() == original}
    finally:
        server.close()
    return {**judge(cases), "cases": cases, "production_entry_preflight": entry_preflight}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", action="store_true")
    group.add_argument("--client")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--windows-sandbox", choices=["unelevated", "mxc"],
                        help="Explicit disposable experiment only; no saved account change")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new receipt path")
    receipt = {"status": "FAIL", "model_inference": "NOT_RUN", "product_ready": False}
    try:
        with tempfile.TemporaryDirectory(prefix="caos-native-boundary-") as tmp:
            base = Path(tmp)
            if args.download:
                client, provenance = download(base)
                receipt.update(provenance)
            else:
                client = shutil.which(args.client)
                if not client:
                    raise ValueError("CLIENT_NOT_FOUND")
            receipt["client_version"] = subprocess.check_output(
                [client, "--version"], text=True, encoding="utf-8", timeout=20).strip()
            receipt["requested_windows_sandbox"] = args.windows_sandbox
            receipt.update(measure(client, base, windows_sandbox=args.windows_sandbox, receipt=receipt))
    except Exception as exc:
        receipt["failure"] = type(exc).__name__ + ": " + str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
