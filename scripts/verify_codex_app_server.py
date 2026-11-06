"""Real native Codex -> CAOS MCP wiring, without sending any model turn.

--download explicitly fetches a checksum-pinned official release into a temporary
directory (used by public CI). It never installs into an owner's account.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

from cognition_agent_os.client_chat import ChatSession
from cognition_agent_os.ledger import readonly_snapshot
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.session_cli import provision

TAG = "rust-v0.167.0"
RELEASES = {
    "nt": ("codex-package-x86_64-pc-windows-msvc.tar.gz",
           "60567ca940bbaf6c10501805d9909d1328179231e2d47a0deec7a1368bb21641"),
    "posix": ("codex-package-x86_64-unknown-linux-musl.tar.gz",
              "3bbf75e83de6b58aed28f2cf6e33ad423ec31fd4700a1457b94be557ea5a7c6e"),
}


def download(directory: Path):
    import platform
    if platform.machine().lower() not in {"amd64", "x86_64"} or platform.system() not in {"Windows", "Linux"}:
        raise RuntimeError("UNSUPPORTED_RELEASE_PLATFORM")
    name, expected = RELEASES[os.name]
    url = f"https://github.com/openai/codex/releases/download/{TAG}/{name}"
    archive = directory / name
    sha, size = hashlib.sha256(), 0
    with urllib.request.urlopen(url, timeout=120) as source, archive.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > 256 * 1024 * 1024:
                raise RuntimeError("RELEASE_SIZE_EXCEEDED")
            sha.update(chunk)
            target.write(chunk)
    if sha.hexdigest() != expected:
        raise RuntimeError("RELEASE_CHECKSUM_MISMATCH")
    destination = directory / "client"
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")
    executable = "codex.exe" if os.name == "nt" else "codex"
    candidates = [p for p in destination.rglob(executable) if p.is_file()]
    if len(candidates) != 1:
        raise RuntimeError("EXPECTED_ONE_CODEX_EXECUTABLE")
    return str(candidates[0]), {"release_tag": TAG, "asset": name, "sha256": expected}


def unwrap(result):
    if result.get("isError"):
        raise AssertionError("NATIVE_MCP_CALL_REJECTED")
    data = result.get("structuredContent")
    if isinstance(data, dict):
        return data.get("result", data)
    for part in result.get("content", []):
        if part.get("type") == "text":
            return json.loads(part["text"])
    raise AssertionError("NATIVE_MCP_RESULT_MISSING")


def verify(client: str, base: Path):
    state = provision(base / "private state 中文")
    original = "Recover this exact goal; no model inference or external effects are authorized."
    root = register_native_goal(state / "ledger.sqlite", original, managed_session=True,
                                client_request_id="native-protocol-ci-0001")
    with readonly_snapshot(state / "ledger.sqlite") as db:
        before = db.execute("SELECT count(*) FROM events").fetchone()[0]
    session = ChatSession(state, root, executable=client, display=lambda _: None)
    try:
        session._start()  # Same production initialization/MCP settings as caos chat.
        inventory = session.server.request("mcpServerStatus/list", {
            "threadId": session.thread, "serverName": "caos", "limit": 100})
        servers = [s for s in inventory["data"] if s["name"] == "caos"]
        assert len(servers) == 1, "CAOS_NATIVE_MCP_SERVER_MISSING"
        names = {t["name"] for t in servers[0]["tools"].values()}
        assert {"cognition_session_inspect", "cognition_client_history", "cognition_input_record"} <= names
        read = unwrap(session.server.request("mcpServer/tool/call", {
            "threadId": session.thread, "server": "caos", "tool": "cognition_session_inspect",
            "arguments": {"root_task_id": root}}))
        assert read["root_task_id"] == root and read["goal"]["original"] == original
    finally:
        session.close()
    # Negative neighbor: required MCP failure must stop native thread startup.
    broken = ChatSession(state, root, executable=client, display=lambda _: None)
    argv = broken.plan["argv"]
    index = next(i for i, arg in enumerate(argv) if arg.startswith("mcp_servers.caos.args="))
    argv[index] = "mcp_servers.caos.args=" + json.dumps(["-c", "raise SystemExit(7)"])
    rejected = False
    try:
        broken._start()
    except RuntimeError as exc:
        rejected = str(exc).startswith("CLIENT_RPC_REJECTED:thread/start")
    finally:
        broken.close()
    assert rejected, "REQUIRED_MCP_FAILURE_DID_NOT_REJECT_THREAD"
    with readonly_snapshot(state / "ledger.sqlite") as db:
        assert before == db.execute("SELECT count(*) FROM events").fetchone()[0]
    return {"native_thread_started": True, "native_mcp_goal_readback": True,
            "missing_required_mcp_rejected": True, "ledger_unchanged": True,
            "tool_count": len(names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", action="store_true")
    group.add_argument("--client")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new receipt path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"status": "FAIL", "model_inference": "NOT_RUN", "owner_account": "NOT_TESTED",
               "product_ready": False}
    try:
        with tempfile.TemporaryDirectory(prefix="caos-native-client-") as tmp:
            base = Path(tmp)
            if args.download:
                client, provenance = download(base)
                receipt.update(provenance)
            else:
                client = shutil.which(args.client)
                if client is None:
                    raise RuntimeError("CLIENT_NOT_FOUND")
            receipt["client_version"] = subprocess.check_output([client, "--version"],
                text=True, encoding="utf-8", timeout=20).strip()
            receipt.update(verify(client, base))
            receipt["status"] = "PASS"
    except Exception as exc:
        receipt["failure"] = type(exc).__name__ + ": " + str(exc)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
