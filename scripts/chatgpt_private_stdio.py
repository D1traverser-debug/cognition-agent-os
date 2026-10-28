"""Private ChatGPT tunnel's stdio target; reuses the existing Host/ledger.

Runs on the machine holding the initialized SQLite ledger. It is NOT a new
controller, a tunnel daemon, an account install or a permission grant.
No SQLite data is ever created by this file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))


def _paths() -> tuple[Path, Path, Path]:
    # Both entrypoints must resolve the SAME Host identity. Preserve older
    # COGNITION_OS_* tunnel configurations, but never silently choose between
    # two conflicting configured resources.
    def configured(name: str, fallback: str) -> Path:
        current = os.environ.get("COGNITION_AGENT_OS_" + name, "").strip()
        legacy = os.environ.get("COGNITION_OS_" + name, "").strip()

        def resolved(value: str) -> Path:
            path = Path(value).expanduser()
            return (path if path.is_absolute() else _REPO / path).resolve(strict=False)

        if current and legacy and resolved(current) != resolved(legacy):
            raise ValueError("CONFLICTING_RUNTIME_RESOURCE_ENV")
        return resolved(current or legacy or fallback)

    return (
        configured("DB", "runtime/state.sqlite"),
        configured("WORKSPACE", "runtime/workspace"),
        configured("FIXTURES", "runtime/fixtures"),
    )


def _server():
    from cognition_agent_os.native_mcp_bridge import build_mcp_server

    db, workspace, fixtures = _paths()
    # build_mcp_server verifies existing ledger initialization and paths.
    # The optional model / worker / source-disclosure tools are OFF.
    # An observation-only tunnel must not expose SQLite mutations or queued
    # actions. The separate native CLI retains its explicitly configured
    # write-capable profile under the original initialized Host grant.
    return build_mcp_server(db, workspace, fixtures, allow_goal_writes=False)


def _mcp_command() -> str:
    argv = [sys.executable, str(Path(__file__).resolve()), "serve"]
    # tunnel-client accepts a command string, not an argv list.
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def _read_result(result) -> dict:
    if result.is_error:
        raise RuntimeError("MCP_READ_ONLY_PROBE_REJECTED")
    value = result.structured_content
    if isinstance(value, dict):
        if "status" in value:
            return value
        if isinstance(value.get("result"), dict):
            return value["result"]
    for item in result.content:
        raw = getattr(item, "text", None)
        if isinstance(raw, str):
            try:
                value = json.loads(raw)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    raise RuntimeError("MCP_READ_ONLY_PROBE_HAS_NO_VERIFIABLE_RESULT")


async def _probe() -> dict:
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve()), "serve"],
        env=dict(os.environ),
    )
    async with Client(params) as client:
        tools = await client.list_tools()
        names = {item.name for item in tools.tools}
        required = {"native_goal_list", "native_goal_inspect"}
        if not required <= names:
            raise RuntimeError("EXPECTED_NATIVE_GOAL_TOOLS_MISSING")
        forbidden = {"native_local_tick", "native_local_model_plan",
                     "native_source_read", "native_goal_create",
                     "native_hypothesis_record", "native_open_research_record",
                     "native_decision_admit"}
        if forbidden & names:
            raise RuntimeError("UNAUTHORIZED_MCP_TOOL_EXPOSED")
        page = _read_result(await client.call_tool("native_goal_list", {}))
        if page.get("status") != "NATIVE_GOAL_INVENTORY":
            raise RuntimeError("NATIVE_GOAL_INVENTORY_UNVERIFIED")
        # Do not report user goals, task IDs, source bodies or secrets.
        return {
            "status": "PRIVATE_STDIO_MCP_SUBPROCESS_VERIFIED",
            "native_goal_list_verified": True,
            "unprivileged_tools_only": True,
            "inventory_has_more_pages": bool(page.get("next_after_task_id")),
            "chatgpt_cloud_connected": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Existing cognition Host as an observation-only stdio MCP target.")
    parser.add_argument("mode", choices=("check", "probe", "serve"),
                        help="check paths; probe real MCP; or serve over stdio")
    args = parser.parse_args()
    try:
        if args.mode == "serve":
            _server().run(transport="stdio")
            return 0
        _server()  # fail closed if ledger, paths, or SDK are missing
        if args.mode == "probe":
            result = asyncio.run(_probe())
        else:
            result = {
                "status": "PRIVATE_STDIO_MCP_LOCAL_PREFLIGHT_OK",
                "mcp_command": _mcp_command(),
                "existing_ledger_only": True,
                "chatgpt_cloud_connected": False,
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        # Do not print exception repr: paths or account details may be private.
        print("PRIVATE_STDIO_MCP_NOT_READY: " + type(error).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
