"""One disposable native model -> real CAOS MCP goal recovery experiment.

No model responses are mocked, rewritten or scored by another model. Only
synthetic CI data is used. This is NOT full cognition or owner acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import urllib.request
from unittest.mock import patch

from cognition_agent_os.client_chat import AppServer, ChatSession, history
from cognition_agent_os.cognitive_session import inspect_session
from cognition_agent_os.ledger import readonly_snapshot
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.session_cli import provision
from verify_codex_app_server import download

MODEL = "qwen3.5:4b-q4_K_M"
EXPERIMENT_PARENT = "1a26cd80d8da44ccf9bba5f78b8e45f3ac11b518"


def preflight():
    """Single new-source attempt on the authorized public repository runner."""
    if (os.environ.get("GITHUB_REPOSITORY") != "D1traverser-debug/cognition-agent-os"
            or os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise ValueError("DISPOSABLE_PUBLIC_CI_FIRST_ATTEMPT_REQUIRED")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event["pull_request"]
    if (event["repository"]["private"] or
            pr["head"]["repo"]["full_name"] != os.environ["GITHUB_REPOSITORY"] or
            "[run-native-app-server]" not in (pr.get("body") or "")):
        raise ValueError("SAME_PUBLIC_REPOSITORY_OPT_IN_REQUIRED")
    parent = subprocess.check_output(["git", "rev-parse", "HEAD^"], text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if parent != EXPERIMENT_PARENT or head != pr["head"]["sha"]:
        raise ValueError("EXPERIMENT_REQUIRES_NEW_REVIEW_OF_CHANGED_SOURCE")
    return head


def workspace_digest(workspace):
    return {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.rglob("*") if p.is_file()}


def judge(*, marker, original, final_original, reply, items, usage, result,
          before_workspace, after_workspace, before_tasks, after_tasks,
          recorded_nodes=None):
    reads = [i for i in items if i.get("type") == "mcpToolCall"
             and i.get("server") == "caos" and i.get("tool") == "cognition_session_inspect"
             and i.get("status") == "completed" and not i.get("error")
             and marker in json.dumps(i.get("result"), ensure_ascii=False)]
    checks = {
        "native_turn_completed": result.get("status") == "CLIENT_TURN_COMPLETED",
        "model_used_real_caos_goal_read": bool(reads),
        "random_marker_recovered": marker in reply,
        "read_only_constraint_recovered": "READ_ONLY" in reply,
        "positive_native_token_usage": usage > 0,
        "original_unchanged": original == final_original,
        "workspace_unchanged": before_workspace == after_workspace,
        "task_inventory_unchanged": before_tasks == after_tasks,
    }
    if recorded_nodes is not None:
        writes = [i for i in items if i.get("type") == "mcpToolCall"
                  and i.get("server") == "caos" and i.get("tool") == "cognition_node_record"
                  and i.get("status") == "completed" and not i.get("error")]
        checks["model_used_real_caos_record"] = bool(writes)
        checks["cold_process_recovered_one_observation"] = (
            len(recorded_nodes) == 1 and recorded_nodes[0].get("kind") == "observation"
            and marker in recorded_nodes[0].get("text", "")
            and "READ_ONLY" in recorded_nodes[0].get("text", "")
            and recorded_nodes[0].get("semantic_truth_verified") is False)
    return {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL",
            "product_ready": False, "owner_account": "NOT_TESTED",
            "cross_task_reasoning_and_evolution": "NOT_TESTED"}


def measure(base, receipt):
    client, provenance = download(base)
    receipt.update(provenance)
    receipt["client_version"] = subprocess.check_output([client, "--version"],
        text=True, encoding="utf-8", timeout=20).strip()
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as response:
        models = json.load(response)["models"]
    installed = [m for m in models if m["name"] == MODEL]
    if len(installed) != 1 or not installed[0].get("digest"):
        raise RuntimeError("EXPECTED_LOCAL_MODEL_NOT_PRESENT")
    receipt["model"] = {k: installed[0][k] for k in ("name", "digest", "size")}
    marker = "CAOS-" + secrets.token_hex(16)
    original = ("Recover the verification marker " + marker +
        " and the workspace constraint READ_ONLY from this original goal. Report both exactly. "
        "Append exactly one observation containing both to the CAOS cognitive ledger. "
        "This local record is permitted; do not change workspace files, amend the goal, "
        "execute business actions or mark the entire product complete.")
    state = provision(base / "synthetic-state")
    root = register_native_goal(state / "ledger.sqlite", original, managed_session=True,
                                client_request_id="native-real-seam-goal")
    original_goal = inspect_session(state / "ledger.sqlite", state / "sources", root)["goal"]
    before_workspace = workspace_digest(state / "workspace")
    with readonly_snapshot(state / "ledger.sqlite") as db:
        before_tasks = [tuple(r) for r in db.execute("SELECT task_id FROM tasks ORDER BY task_id")]
    session = ChatSession(state, root, executable=client, timeout=900,
                          display=lambda _: None,
                          ask=lambda _: (_ for _ in ()).throw(RuntimeError("UNEXPECTED_USER_QUESTION")))
    settings = {
        "model": MODEL, "model_provider": "caos-local-eval",
        "model_providers.caos-local-eval.name": "Disposable local evaluation",
        "model_providers.caos-local-eval.base_url": "http://127.0.0.1:11434/v1/",
        "model_providers.caos-local-eval.wire_api": "responses",
        "model_providers.caos-local-eval.requires_openai_auth": False,
        "model_providers.caos-local-eval.request_max_retries": 0,
        "model_providers.caos-local-eval.stream_max_retries": 0,
        "model_providers.caos-local-eval.stream_idle_timeout_ms": 900000,
        "model_context_window": 65536, "model_auto_compact_token_limit": 50000,
        "web_search": "disabled", "model_reasoning_effort": "low",
    }
    overrides = [part for k, v in settings.items() for part in ("-c", k + "=" + json.dumps(v))]
    session.plan["argv"][-1:-1] = overrides
    items, usage, errors = [], [], []
    original_receive = AppServer.receive

    def observe(connection, deadline):
        message = original_receive(connection, deadline)
        method, params = message.get("method"), message.get("params", {})
        if method == "item/completed":
            items.append(params["item"])
        elif method == "thread/tokenUsage/updated":
            usage.append(params["tokenUsage"]["total"]["totalTokens"])
        elif method == "error":
            errors.append(params)
        return message  # No rewriting, injection, replay or synthetic result.

    result = {}
    try:
        with patch.object(AppServer, "receive", observe):
            result = session.submit("Continue the selected task. Recover its original goal "
                "through cognition_session_inspect, record the permitted observation using "
                "cognition_node_record, then answer with its marker and constraint.",
                request_id="native-real-seam-continuation")
    except Exception as exc:
        receipt["failure"] = type(exc).__name__ + ": " + str(exc)
    finally:
        session.close()
    turns, cursor = [], 0
    while True:
        page = history(state / "ledger.sqlite", root, after_event_id=cursor,
                       limit=100, include_text=True)
        turns.extend(page["turns"])
        cursor = page["next_after_event_id"]
        if cursor is None:
            break
    reply = "\n".join(t.get("assistant_text", "") for t in turns)
    # A fresh CLI process reads durable state after the model/client have exited;
    # neither a successful tool label nor an assistant assertion is sufficient.
    import sys
    view = json.loads(subprocess.check_output([sys.executable, "-m",
        "cognition_agent_os.session_cli", "--state", str(state), "inspect", "--root", root],
        text=True, encoding="utf-8", timeout=20))
    with readonly_snapshot(state / "ledger.sqlite") as db:
        after_tasks = [tuple(r) for r in db.execute("SELECT task_id FROM tasks ORDER BY task_id")]
    receipt.update(judge(marker=marker, original=original_goal, final_original=view["goal"],
        reply=reply, items=items, usage=max(usage, default=0), result=result,
        before_workspace=before_workspace, after_workspace=workspace_digest(state / "workspace"),
        before_tasks=before_tasks, after_tasks=after_tasks, recorded_nodes=view["nodes"]))
    receipt.update({"reply": reply, "native_items": items, "native_errors": errors,
                    "native_token_usage": usage, "delivery": turns, "result": result,
                    "cold_recorded_nodes": view["nodes"], "experiment": "additive-local-record"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    head = preflight()
    if args.preflight_only:
        print(json.dumps({"status": "SINGLE_SOURCE_ATTEMPT_ALLOWED", "source": head}))
        return 0
    if not args.output or args.output.exists():
        parser.error("--output must be a new receipt path")
    receipt = {"source": head, "status": "FAIL", "product_ready": False}
    try:
        with tempfile.TemporaryDirectory(prefix="caos-native-model-") as tmp:
            measure(Path(tmp), receipt)
    except Exception as exc:
        receipt["failure"] = type(exc).__name__ + ": " + str(exc)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"native_items", "delivery"}}, ensure_ascii=False))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
