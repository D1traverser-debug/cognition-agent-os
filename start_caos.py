"""First-use launcher for the existing CAOS entry; no new agent or state store.

Python 3.11+ is required. Setup installs this checkout and MCP into an owned
environment and, only if absent, downloads the checksum-pinned native client.
It never signs in, changes account configuration or buys a model service.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parent
FORMAT = "caos-bootstrap-v1"


def default_state():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "CAOS" / "session"


def source_revision(repo=REPO):
    sha = hashlib.sha256()
    paths = [repo / "pyproject.toml", *sorted((repo / "src").rglob("*.py"))]
    for path in paths:
        sha.update(path.relative_to(repo).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return sha.hexdigest()


def child_environment():
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def runtime_info(runtime):
    marker = runtime / "installation.json"
    if runtime.is_symlink() or marker.is_symlink():
        raise ValueError("运行目录不能是符号链接。")
    if not runtime.exists():
        return None
    if not marker.is_file():
        raise ValueError("该运行目录不属于 CAOS；请选择空的新目录，避免覆盖已有环境。")
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError("运行环境身份不匹配；不会覆盖。")
    return data


def provision_runtime(runtime):
    info = runtime_info(runtime)
    if info is None:
        runtime.mkdir(parents=True, exist_ok=False)
        info = {"format": FORMAT}
        (runtime / "installation.json").write_text(json.dumps(info), encoding="utf-8")
    if (runtime / "venv").is_symlink():
        raise ValueError("运行环境不能指向其他 Python 环境。")
    python = runtime_python(runtime)
    revision = source_revision()
    environment = child_environment()
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(runtime / "venv")],
                       check=True, env=environment)
        info.pop("source_revision", None)
    if info.get("source_revision") != revision:
        print("正在安装本版本及 MCP 依赖；后续源码不变时复用环境。", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                        "--force-reinstall", str(REPO) + "[mcp]"], check=True, env=environment)
        info["source_revision"] = revision
        (runtime / "installation.json").write_text(json.dumps(info), encoding="utf-8")
    return python


def runtime_python(runtime):
    return runtime / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def select_client(runtime, requested):
    selected = shutil.which(requested or "codex")
    if selected:
        return selected
    if requested:
        raise ValueError("找不到指定的 Codex 客户端；不会悄悄改用另一个客户端。")
    marker = runtime / "native-client.json"
    if marker.is_symlink():
        raise ValueError("客户端安装记录不能是符号链接。")
    if marker.is_file():
        record = json.loads(marker.read_text(encoding="utf-8"))
        executable = runtime / record["relative_path"]
        if (not executable.resolve().is_relative_to(runtime.resolve()) or
                not executable.is_file() or
                hashlib.sha256(executable.read_bytes()).hexdigest() != record["executable_sha256"]):
            raise ValueError("缓存客户端与安装记录不匹配；不会执行或覆盖。")
        return str(executable)
    print("未发现 Codex；正在获取经过固定校验的官方客户端。", flush=True)
    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "scripts"))
    from verify_codex_app_server import download
    client_dir = runtime / "native-download"
    if client_dir.is_symlink():
        raise ValueError("客户端下载目录不能指向其他位置。")
    # Incomplete downloads are not executable trusted cache records.
    client_dir.mkdir(exist_ok=True)
    executable, provenance = download(client_dir)
    path = Path(executable)
    marker.write_text(json.dumps({**provenance,
        "relative_path": path.relative_to(runtime).as_posix(),
        "executable_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}), encoding="utf-8")
    return executable


def main(argv=None):
    # Paths and prompts are Unicode even on legacy Windows console code pages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=default_state())
    parser.add_argument("--runtime-dir", type=Path, default=REPO / "runtime" / "bootstrap")
    parser.add_argument("--client", help="Use this installed Codex executable")
    parser.add_argument("--restore", type=Path, help="Restore a private snapshot into a NEW state directory")
    parser.add_argument("--setup-only", action="store_true", help="Install/check entry without inference or login")
    parser.add_argument("--check", action="store_true", help="Read setup state; no installation or inference")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 11):
            raise ValueError("请先安装 Python 3.11 或更高版本。")
        runtime, state = args.runtime_dir.absolute(), args.state.absolute()
        if state.resolve().is_relative_to(REPO):
            raise ValueError("私人会话目录必须位于源码目录之外，防止随代码公开。")
        if state.resolve().is_relative_to(runtime.resolve()) or runtime.resolve().is_relative_to(state.resolve()):
            raise ValueError("私人会话与可重建运行环境必须分开。")
        info = runtime_info(runtime)
        if args.check:
            print(json.dumps({"state": str(state), "state_exists": state.is_dir(),
                "runtime_current": bool(info and runtime_python(runtime).is_file()
                                        and info.get("source_revision") == source_revision()),
                "model_authenticated": "NOT_TESTED", "product_ready": False}, ensure_ascii=False))
            return 0
        python = provision_runtime(runtime)
        client = select_client(runtime, args.client)
        command = [str(python), "-m", "cognition_agent_os.session_cli", "--state", str(state)]
        environment = child_environment()
        if args.restore:
            subprocess.run([*command, "restore", "--file", str(args.restore.absolute())], check=True, env=environment)
        elif not state.exists():
            subprocess.run([*command, "init"], check=True, env=environment)
        subprocess.run([*command, "doctor"], check=True, env=environment,
                       stdout=subprocess.DEVNULL)
        subprocess.run([*command, "launch", "--check", "--client", client],
                       check=True, env=environment, stdout=subprocess.DEVNULL)
        if args.setup_only:
            print(json.dumps({"status": "LOCAL_ENTRY_PREPARED", "state": str(state),
                "client": client, "mcp_transport_verified": True,
                "model_authenticated": "NOT_TESTED", "product_ready": False}, ensure_ascii=False))
            return 0
        print("开始 CAOS 对话。模型沿用 Codex 已配置的账号/提供商；本程序不自动登录。", flush=True)
        return subprocess.run([*command, "chat", "--client", client], env=environment).returncode
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("启动未完成：" + str(exc), file=sys.stderr)
        print("会话不会被重新初始化。可用 --check 检查，或 --setup-only 单独准备入口。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
