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


def _current_architecture_pivot() -> dict:
    """Read the existing ADR's adopted experimental path, not a copied plan.

    This is repository PROPOSAL evidence, never original user consent.
    The actual owner may supersede this at any time.
    """
    relative = "docs/01-ARCHITECTURE-DECISIONS.md"
    source = ROOT / relative
    if not source.is_file() or source.is_symlink():
        return {"status": "ARCHITECTURE_PIVOT_UNVERIFIABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"status": "ARCHITECTURE_PIVOT_UNVERIFIABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    title = "### 优先级反转（约束后续工程行为）"
    if title not in content or len(content) > 80_000:
        return {"status": "ARCHITECTURE_PIVOT_UNVERIFIABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    section = content.split(title, 1)[1].split("\n### ", 1)[0]
    candidate = next(
        (line[3:].strip() for line in section.splitlines()
         if line.startswith("1. ")), None)
    if (not isinstance(candidate, str)
        or not 60 <= len(candidate) <= 800
        or "ChatGPT/Codex" not in candidate):
        return {"status": "ARCHITECTURE_PIVOT_UNVERIFIABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    return {
        "status": "REPO_PROPOSAL_NOT_OWNER_OR_GRANT",
        "source_path": relative,
        "proposed_first_action": candidate[:130] + ("…" if len(candidate) > 130 else ""),
    }


def _live_python_topology() -> dict:
    """Select module LOCATORS from current AST; no semantic graph claim."""
    try:
        from architecture_probe import inspect
        scanned = inspect(ROOT)
    except (ImportError, ValueError, OSError, SyntaxError):
        return {"kind": "CURRENT_SOURCE_TOPOLOGY_UNVERIFIABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    observed = {m["name"]: m for m in scanned["modules"]}
    contracts = {
        "decision": ("native_decision", "admit_native_decision"),
        "effect": ("runner", "run_once"),
        "recovery": ("continuity", "resume_goal"),
        "client_adapter": ("native_mcp_bridge", "build_mcp_server"),
        "independent_local_result": (
            "owner_postcondition", "inspect_owner_local_outcome"),
    }
    if (scanned["parse_errors"]
        or scanned["parsed_count"] != scanned["file_count"]
        or any(name not in observed
               or symbol not in observed[name]["definitions"]
               for name, symbol in contracts.values())):
        return {"kind": "CURRENT_SOURCE_TOPOLOGY_UNVERIFIABLE",
                "source_role": "NOT_OWNER_OR_GRANT",
                "parse_errors": scanned["parse_errors"][:3]}
    return {
        "kind": "CURRENT_CHECKOUT_AST_NOT_RUNTIME_PROOF",
        "parsed_modules": scanned["parsed_count"],
        "parse_errors": [],
        "paths": {
            role: observed[name]["path"]
            for role, (name, _symbol) in contracts.items()
        },
    }


def _project_recovery_when_no_ledger() -> dict:
    """Bounded repository guide, NOT recovered owner text or a task grant.

    Codex frequently edits a GitHub Draft without a local SQLite runtime.
    An empty runtime must not erase the product mission or silently turn
    a historical CI/checkpoint into current task authority. Reuse the
    EXISTING near-term gate instead of duplicating a second roadmap.
    """
    relative = "docs/PRODUCT-READINESS-GATE.md"
    path = ROOT / relative
    if not path.is_file() or path.is_symlink():
        return {"status": "PROJECT_GUIDANCE_UNAVAILABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"status": "PROJECT_GUIDANCE_UNAVAILABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    if len(text) > 80_000 or "**Near-term priority:**" not in text:
        return {"status": "PROJECT_GUIDANCE_UNAVAILABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    paragraph = text.split("**Near-term priority:**", 1)[1].split("\n\n", 1)[0]
    priority = " ".join(paragraph.split())
    if not 40 <= len(priority) <= 800:
        return {"status": "PROJECT_GUIDANCE_UNAVAILABLE",
                "source_role": "NOT_OWNER_OR_GRANT"}
    return {
        "status": "PROJECT_GUIDANCE_FOUND",
        "source_path": relative,
        "source_role": "REPO_PROPOSAL_NOT_OWNER_OR_GRANT",
        "near_term_priority": priority[:85] + ("…" if len(priority) > 85 else ""),
        "continuation_index": "SESSION_HANDOFF.md",
        "continuation_policy": "PROGRESSIVE_LIVE_SOURCE_DISCLOSURE",
        "complete_work_log_location": "LIVE_GIT_COMMIT_HISTORY_AND_DIFF",
        "product_readiness_claim": "NOT_VERIFIED",
        "live_pr_head_and_ci": "MUST_REFETCH",
        "original_user_utterances": "MUST_RECOVER_SEPARATELY",
        "architecture_pivot": _current_architecture_pivot(),
        "live_python_topology": _live_python_topology(),
        "proposed_action": (
            "Use SESSION_HANDOFF.md as bootstrap index only; recover "
            "owner originals, live PR/HEAD/CI and commit history/diff."
        ),
    }


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
        context["repository_recovery"] = _project_recovery_when_no_ledger()
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
    prefix = "Read-only project state observation (not a new instruction or grant): "
    note = prefix + json.dumps(context, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
    if len(note) > MAX_CONTEXT_CHARS:
        # This is a *valid* previously read SQLite goal whose full context
        # exceeds the hook transport budget. Do not erase its stable locator:
        # a long original owner goal must remain retrievable without treating
        # a summary, hook status, or shortened goal as runnable authority.
        compact = {
            "kind": "CODEX_COGNITION_CONTEXT_READBACK_V1",
            "status": "FULL_LEDGER_READBACK_REQUIRED",
            "observed_runtime_status": context.get("status"),
            "ledger_discovery": context.get("ledger_discovery"),
            "root_task_id": context.get("root_task_id"),
            "original_contract_sha256": context.get("original_contract_sha256"),
            "goal_rev": context.get("goal_rev"),
            "grant_rev": context.get("grant_rev"),
            "root_state": context.get("root_state"),
            "source_of_truth": context.get("source_of_truth"),
            "local_source_head": context.get("local_source_head"),
            "source_head_is_live_github_attested": False,
            "original_goal_verified": False,
            "business_outcome_verified": False,
            "scheduling_or_effects_performed": False,
            "next_action_policy": (
                "Read the complete owner goal again from the configured "
                "existing SQLite ledger via cognition_agent_os.continuity."
                "resume_goal, then independently recheck the root task ID, "
                "contract digest and current grant. Do not execute from this "
                "bounded hook receipt or infer owner/business completion."
            ),
        }
        if (context.get("original_goal_verified") is True
                and isinstance(context.get("original_goal"), str)):
            compact["original_goal"] = context["original_goal"]
            compact["original_goal_verified"] = True
        note = prefix + json.dumps(compact, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
        if len(note) > MAX_CONTEXT_CHARS:
            # No partial owner-goal text is ever substituted for the original.
            compact.pop("original_goal", None)
            compact["original_goal_verified"] = False
            compact["original_goal_omitted_from_hook"] = True
            compact["original_goal_persisted_in_ledger"] = (
                context.get("source_of_truth") == "ORIGINAL_SQLITE_TASK"
            )
            note = prefix + json.dumps(compact, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": note,
        }
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
