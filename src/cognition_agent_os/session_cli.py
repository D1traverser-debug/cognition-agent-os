"""Small operator/client entry for the existing CAOS runtime, no account edits."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sys
from zipfile import BadZipFile

from .ledger import connect, initialize, event, readonly_snapshot
from .native_decision import register_native_goal, list_native_goals
from .cognitive_session import (
    inspect_session, record_node, amend_goal, reopen_node, record_input, inspect_inputs)
from .effect_contract import install_contract, inspect_contract_outcome


def provision(directory: Path):
    """Explicit, local provisioning only; never revive/reconfigure existing state."""
    directory = directory.absolute()
    if directory.exists():
        raise ValueError("SESSION_DIRECTORY_EXISTS_USE_EXISTING_STATE")
    directory.mkdir(parents=True, mode=0o700)
    (directory / "sources").mkdir(mode=0o700)
    (directory / "workspace").mkdir(mode=0o700)
    with closing(connect(directory / "ledger.sqlite")) as db:
        initialize(db)
        event(db, "operator", "COGNITION_MANAGED_LEDGER", {"version": 1})
        db.commit()
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(prog="caos", description="CAOS managed interactive session")
    parser.add_argument("--state", required=True, type=Path,
                        help="Private local directory; never commit it to Git")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create a new isolated managed ledger, never reinitialize")
    listing = sub.add_parser("list", help="Recover original goals without assuming a selected root")
    listing.add_argument("--after-task-id")
    create = sub.add_parser("goal", help="Register complete original owner text")
    create.add_argument("--file", type=Path, required=True)
    create.add_argument("--request-id", required=True)
    for name in ("inspect", "outcome", "inputs", "history"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", required=True)
        if name in ("inspect", "inputs", "history"):
            cmd.add_argument("--after-event-id", type=int, default=0)
            cmd.add_argument("--limit", type=int, default=32 if name == "inspect" else 4)
        if name == "history":
            cmd.add_argument("--include-text", action="store_true", help="Read exact untrusted assistant replies")
    for name in ("record", "amend", "reopen", "receive"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", required=True)
        cmd.add_argument("--file", type=Path, required=True, help="JSON request body")
    policy = sub.add_parser("authorize", help="OPERATOR ONLY: bind reviewed effect/outcome contract")
    policy.add_argument("--root", required=True)
    policy.add_argument("--file", required=True, type=Path)
    policy.add_argument("--rebind-pending", action="store_true",
                        help="After reviewing restored sources, explicitly reauthorize only PENDING effects")
    for name in ("snapshot", "restore"):
        sub.add_parser(name).add_argument("--file", type=Path, required=True)
    sub.add_parser("doctor", help="Read local readiness; never claim client installation")
    sub.add_parser("serve", help="Serve MCP for this managed ledger; no account installation")
    client = sub.add_parser("launch", help="Open local Codex with session-scoped CAOS MCP wiring")
    client.add_argument("--root")
    client.add_argument("--client", default="codex", help="Installed Codex executable")
    client.add_argument("--check", action="store_true", help="Validate and print wiring without starting a model")
    chat = sub.add_parser("chat", help="Save plain-language messages before sending them to local Codex")
    selection = chat.add_mutually_exclusive_group()
    selection.add_argument("--root")
    selection.add_argument("--new", action="store_true", help="Start a distinct goal from the first message")
    chat.add_argument("--client", default="codex")
    chat.add_argument("--timeout", type=float, default=600)
    chat.add_argument("--message-file", type=Path, help="One UTF-8 message, no JSON; omit for interactive text")
    chat.add_argument("--request-id", help="Stable delivery ID for a one-message invocation")
    chat.add_argument("--goal-budget", type=int,
                      help="Opt in to the native goal loop with this invocation's token budget")
    chat.add_argument("--resume-client", nargs="?", const="auto", metavar="THREAD_ID",
                      help="Resume a cleanly stopped bound native thread; budget is cumulative")
    args = parser.parse_args(argv)
    state = args.state.absolute()
    db, sources, workspace = state / "ledger.sqlite", state / "sources", state / "workspace"
    try:
        if args.command == "init":
            provision(state)
            result = {"status": "LOCAL_STATE_CREATED", "state": str(state)}
        elif args.command in ("snapshot", "restore"):
            from .session_archive import export_session, restore_session
            result = (export_session(state, args.file) if args.command == "snapshot"
                      else restore_session(args.file, state))
        elif args.command == "goal":
            root = register_native_goal(db, args.file.read_text(encoding="utf-8"),
                                        managed_session=True,
                                        client_request_id=args.request_id)
            result = inspect_session(db, sources, root)
        elif args.command in ("inspect", "inputs"):
            reader = inspect_session if args.command == "inspect" else inspect_inputs
            result = reader(db, sources, args.root,
                                     after_event_id=args.after_event_id, limit=args.limit)
        elif args.command == "list":
            result = list_native_goals(db, workspace, sources, args.after_task_id)
        elif args.command == "outcome":
            result = inspect_contract_outcome(db, sources, workspace, args.root)
        elif args.command == "authorize":
            result = install_contract(db, sources, args.root,
                                      json.loads(args.file.read_text(encoding="utf-8")),
                                      workspace=workspace, rebind_pending=args.rebind_pending)
        elif args.command in ("record", "amend", "reopen", "receive"):
            data = json.loads(args.file.read_text(encoding="utf-8"))
            functions = {"record": record_node, "amend": amend_goal, "reopen": reopen_node,
                         "receive": record_input}
            result = functions[args.command](db, sources, args.root, **data)
        elif args.command == "launch":
            from .client_launch import launch
            result = launch(state, root=args.root, executable=args.client, check=args.check)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return result.get("exit_code", 0)
        elif args.command == "chat":
            from .client_chat import run_chat
            result = run_chat(state, root=args.root, new=args.new, executable=args.client,
                timeout=args.timeout, message_file=args.message_file, request_id=args.request_id,
                goal_budget=args.goal_budget, resume_client=args.resume_client)
            return 0 if result["status"] in {"CLIENT_CLOSED", "CLIENT_TURN_COMPLETED",
                                            "CLIENT_GOAL_COMPLETE"} else 2
        elif args.command == "history":
            from .client_chat import history
            result = history(db, args.root, after_event_id=args.after_event_id, limit=args.limit,
                             include_text=args.include_text)
        elif args.command == "doctor":
            with readonly_snapshot(db) as conn:
                authority = dict(conn.execute("SELECT * FROM authority WHERE singleton=1").fetchone())
                strict = conn.execute("SELECT 1 FROM events WHERE kind='COGNITION_MANAGED_LEDGER'").fetchone() is not None
            try:
                from importlib.metadata import version
                sdk = version("mcp")
            except ImportError:
                sdk = None
            result = {"status": "MANAGED_LOCAL_STATE" if strict else "LEGACY_UNMANAGED_STATE",
                      "authority": authority, "mcp_sdk_version": sdk,
                      "source_directory_exists": sources.is_dir(),
                      "workspace_directory_exists": workspace.is_dir(),
                      "client_connected": "NOT_OBSERVED", "product_ready": False,
                      "codex_stdio_command": [sys.executable, "-m", "cognition_agent_os.session_cli",
                                                "--state", str(state), "serve"]}
        else:
            from .native_mcp_bridge import build_mcp_server
            with readonly_snapshot(db) as conn:
                if conn.execute("SELECT 1 FROM events WHERE kind='COGNITION_MANAGED_LEDGER'").fetchone() is None:
                    raise ValueError("SERVE_REQUIRES_MANAGED_LEDGER")
            server = build_mcp_server(db, workspace, sources, allow_goal_writes=True,
                                      allow_host_tick=True, allow_source_read=True)
            server.run(transport="stdio")
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "INTERRUPTED", "reason": "CHECK_SAVED_INPUT_AND_DELIVERY_HISTORY"}), file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, BadZipFile, EOFError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
