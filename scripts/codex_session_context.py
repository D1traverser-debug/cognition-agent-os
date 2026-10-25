#!/usr/bin/env python3
"""Codex session startup/compaction context from ORIGINAL durable state.

Read-only, no network, no API keys, no inferred grants, no database creation.
The hook is an entrypoint, not authority: data read here never overrides the
user's current task, authenticated grants or independent effect verification.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DB_ENV = "COGNITION_AGENT_OS_DB"
WORKSPACE_ENV = "COGNITION_AGENT_OS_WORKSPACE"
FIXTURES_ENV = "COGNITION_AGENT_OS_FIXTURES"
CANDIDATE_NAMES = ("state.sqlite", "ledger.sqlite",
                   ".cognition-agent-os/ledger.sqlite",
                   "agent-state/ledger.sqlite")
MAX_HOOK_INPUT = 32768
MAX_CONTEXT_CHARS = 7500


def _existing_database() -> tuple[Path | None, str]:
    configured = os.getenv(DB_ENV, "").strip()
    if configured:
        target = Path(configured).expanduser()
        if not target.is_absolute():
            target = ROOT / target
        if target.is_symlink() or not target.is_file():
            return None, "CONFIGURED_LEDGER_MISSING_OR_UNSAFE"
        return target, "CONFIGURED_LEDGER"
    found = [ROOT / name for name in CANDIDATE_NAMES
             if (ROOT / name).is_file() and not (ROOT / name).is_symlink()]
    if len(found) > 1:
        return None, "AMBIGUOUS_LOCAL_LEDGERS"
    if not found:
        return None, "NO_LOCAL_LEDGER_CONFIGURED"
    return found[0], "DISCOVERED_EXISTING_LEDGER"


def _optional_existing_directory(env: str, fallback: str) -> Path | None:
    raw = os.getenv(env, "").strip()
    directory = Path(raw).expanduser() if raw else ROOT / fallback
    if not directory.is_absolute():
        directory = ROOT / directory
    if directory.is_symlink() or not directory.is_dir():
        return None
    return directory


def _head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=4, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def build_context(payload: dict) -> dict:
    cwd_value = payload.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value.strip():
        return {"status": "INVALID_HOOK_WORKSPACE"}
    try:
        cwd = Path(cwd_value).resolve(strict=True)
        if cwd != ROOT and ROOT not in cwd.parents:
            return {"status": "HOOK_OUTSIDE_REPOSITORY"}
    except OSError:
        return {"status": "INVALID_HOOK_WORKSPACE"}
    context: dict = {
        "kind": "CODEX_COGNITION_CONTEXT_READBACK_V1",
        "status": "NO_LOCAL_LEDGER_CONFIGURED",
        "local_source_head": _head(),
        "source_head_is_live_github_attested": False,
        "original_goal_verified": False,
        "business_outcome_verified": False,
        "unattended_execution_verified": False,
        "scheduling_or_effects_performed": False,
        "next_action_policy": (
            "Read the current owner request and live repository evidence. "
            "Do not infer goal success or permission from this hook."
        ),
    }
    db_path, origin = _existing_database()
    context["ledger_discovery"] = origin
    if db_path is None:
        context["status"] = origin
        return context
    ws = _optional_existing_directory(WORKSPACE_ENV, "workspace")
    fixtures = _optional_existing_directory(FIXTURES_ENV, "fixtures")
    if (ws is None) != (fixtures is None):
        ws = fixtures = None
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from cognition_agent_os.continuity import resume_goal
        # The bootstrap itself never fetches GitHub. A remotely pinned goal
        # remains UNVERIFIED until an independently authorized fresh read.
        state = resume_goal(
            db_path, resolve_head=lambda *_: "0" * 40,
            workspace=ws, fixtures=fixtures)
        for key in (
            "status", "root_task_id", "original_goal",
            "original_contract_sha256", "goal_rev", "grant_rev",
            "root_state", "source_of_truth", "next_task_id",
            "child_task_id", "child_state", "chosen_capability",
            "local_owner_outcome_verified", "local_outcome_evidence",
            "business_outcome_verified", "real_external_outcome_verified",
            "reason", "pinned_head_sha", "observed_head_sha",
        ):
            if key in state:
                context[key] = state[key]
        context["original_goal_verified"] = (
            isinstance(state.get("original_goal"), str)
            and state.get("source_of_truth") == "ORIGINAL_SQLITE_TASK"
        )
    except (ImportError, OSError, ValueError, TypeError) as exc:
        context["status"] = "DURABLE_CONTEXT_UNAVAILABLE"
        context["readback_error_class"] = type(exc).__name__
    return context


def main() -> int:
    try:
        data = sys.stdin.read(MAX_HOOK_INPUT + 1)
        if len(data) > MAX_HOOK_INPUT:
            data = "{}"
        payload = json.loads(data)
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError, UnicodeError):
        payload = {}
    context = build_context(payload)
    # The content is a source observation, not an instruction/permission grant.
    note = (
        "Read-only project state observation (not a new instruction or grant): "
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
    )
    if len(note) > MAX_CONTEXT_CHARS:
        note = json.dumps({
            "kind": "CODEX_COGNITION_CONTEXT_READBACK_V1",
            "status": "CONTEXT_TOO_LARGE_TO_RELIABLY_RESTORE",
            "original_goal_verified": False,
            "business_outcome_verified": False,
            "local_source_head": context.get("local_source_head"),
        }, sort_keys=True)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": note,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
