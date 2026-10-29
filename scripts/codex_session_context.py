#!/usr/bin/env python3
"""Codex session startup/compaction context from ORIGINAL durable state.

Read-only, no network, no API keys, no inferred grants, no database creation.
The hook is an entrypoint, not authority: data read here never overrides the
user's current task, authenticated grants or independent effect verification.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DB_ENV = "COGNITION_AGENT_OS_DB"
WORKSPACE_ENV = "COGNITION_AGENT_OS_WORKSPACE"
FIXTURES_ENV = "COGNITION_AGENT_OS_FIXTURES"
# Recognize the Windows Host and private ChatGPT stdio default as well as
# existing older CLI layouts. Multiple distinct ledgers remain ambiguous.
CANDIDATE_NAMES = ("runtime/state.sqlite", "state.sqlite", "ledger.sqlite",
                   ".cognition-agent-os/ledger.sqlite",
                   "agent-state/ledger.sqlite")
MAX_HOOK_INPUT = 32768
# Codex owns model-visible hook context budget. Its positive
# additionalContextLimit spills over-budget output to an on-disk exact file;
# do not apply an independent character cutoff that discards goal/state data.
# A failed native spill can still truncate: trusted-client acceptance is needed.


def _runtime_path(value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve(strict=False)


def _existing_database() -> tuple[Path | None, str]:
    configured = os.getenv(DB_ENV, "").strip()
    legacy = os.getenv("COGNITION_OS_DB", "").strip()
    if configured and legacy and _runtime_path(configured) != _runtime_path(legacy):
        return None, "CONFLICTING_LEDGER_ENV"
    selected = configured or legacy
    if selected:
        target = Path(selected).expanduser()
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
    legacy = os.getenv(env.replace("COGNITION_AGENT_OS_", "COGNITION_OS_"), "").strip()
    if raw and legacy and _runtime_path(raw) != _runtime_path(legacy):
        raise ValueError("CONFLICTING_RUNTIME_RESOURCE_ENV")
    chosen = raw or legacy
    directory = Path(chosen).expanduser() if chosen else ROOT / fallback
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
        "proposed_first_action": candidate,
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
        "source_map": "scripts/architecture_probe.py",
        "parsed_modules": scanned["parsed_count"],
        "parse_errors": [],
        "paths": {
            role: observed[name]["path"]
            for role, (name, _symbol) in contracts.items()
        },
    }


def _project_recovery_when_no_ledger() -> dict:
    """Bounded repository guide, NOT recovered owner text or a task grant.

    Codex may start from integrated main or an active PR without a local SQLite runtime.
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
        "near_term_priority": priority,
        "continuation_index": "SESSION_HANDOFF.md",
        "continuation_policy": "PROGRESSIVE_LIVE_SOURCE_DISCLOSURE",
        "complete_work_log_location": "LIVE_GIT_PROVENANCE_ON_DEMAND",
        "product_readiness_claim": "NOT_VERIFIED",
        "live_default_branch_head_and_ci": "MUST_REFETCH",
        "live_active_pr_metadata": "CHECK_IF_PRESENT",
        "original_user_utterances": "MUST_RECOVER_SEPARATELY",
        "architecture_pivot": _current_architecture_pivot(),
        "live_python_topology": _live_python_topology(),
        "proposed_action": (
            "bootstrap index; live default branch HEAD; task-relevant source; "
            "active PR only if present; specific conflict."
        ),
    }


def _unattested_source(*_args: object) -> str:
    """Never manufacture an observed GitHub HEAD in the offline hook."""
    raise RuntimeError("LIVE_SOURCE_NOT_QUERIED_BY_LOCAL_HOOK")


def build_context(payload: dict, *, include_full_original: bool = False) -> dict:
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
            "Recheck owner goal and live source. No new grant or outcome."
        ),
    }
    db_path, origin = _existing_database()
    context["ledger_discovery"] = origin
    if db_path is None:
        context["status"] = origin
        context["repository_recovery"] = _project_recovery_when_no_ledger()
        return context
    # The registered Windows Host defaults to runtime/workspace but the
    # checkout-root fixtures directory for both new and legacy ledgers.
    # Preserve that one existing Host resource contract across entrypoints.
    # Compare canonical physical locations, not Windows 8.3 vs long names
    # or an explicit old-env DB spelling. A raw alias may designate exactly
    # the Windows Host's runtime ledger while differing as a Path string.
    runtime_layout = (_runtime_path(str(db_path))
                      == _runtime_path("runtime/state.sqlite"))
    try:
        ws = _optional_existing_directory(
            WORKSPACE_ENV, "runtime/workspace" if runtime_layout else "workspace")
        fixtures = _optional_existing_directory(
            FIXTURES_ENV, "fixtures")
    except ValueError:
        context["status"] = "CONFLICTING_RUNTIME_RESOURCE_ENV"
        return context
    if (ws is None) != (fixtures is None):
        ws = fixtures = None
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from cognition_agent_os.continuity import resume_goal
        # The bootstrap itself never fetches GitHub. A remotely pinned goal
        # remains UNVERIFIED until an independently authorized fresh read.
        state = resume_goal(
            db_path, resolve_head=_unattested_source,
            workspace=ws, fixtures=fixtures)
        # One version-bound readback for ALL existing continuity contracts,
        # including legacy registered, multi-registered, mixed and native
        # roots. A digest of the entire verified observation, rather than
        # task IDs alone, rejects stale or revised original clauses.
        state_digest = hashlib.sha256(json.dumps(
            state, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        context["continuity_state_readback"] = {
            "entrypoint": "scripts/codex_session_context.py",
            "arguments": ["--readback-state", state_digest],
            "source_role": "READ_ONLY_EXISTING_SQLITE_RESUME_OBSERVATION",
        }
        if include_full_original:
            # Deliberate, explicit CLI readback receives every original
            # field from the SAME resume_goal source, not a second index.
            # The automatic SessionStart never contains this projection.
            context.update(state)
        for key in (
            "status", "root_task_id", "root_task_ids", "original_goal",
            "original_goals", "goal_id", "goal_ids", "authority_current",
            "original_contract_sha256", "goal_rev", "grant_rev",
            "root_state", "source_of_truth", "next_task_id",
            "child_task_id", "child_state", "chosen_capability",
            "child_task_ids", "original_obligation_progress",
            "sequence_rule", "runnable_task_ids", "waiting_dependency_tasks",
            "next_task_ids", "native_decision_state",
            "native_next_action_authorized",
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
        # A direct, read-only path to the SAME immutable SQLite source.
        # This survives loss of a native hook spill preview without a second
        # memory index, and the caller must recheck both identity and digest.
        if (context["original_goal_verified"]
            and isinstance(context.get("root_task_id"), str)
            and isinstance(context.get("original_contract_sha256"), str)):
            context["original_goal_readback"] = {
                "entrypoint": "scripts/codex_session_context.py",
                "arguments": ["--readback-original",
                              context["root_task_id"],
                              context["original_contract_sha256"]],
                "source_role": "READ_ONLY_EXISTING_SQLITE_GOAL",
            }
            if not include_full_original:
                # Don't put private owner text in native Codex spill temp files.
                # The real text remains in the SAME verified SQLite task.
                context.pop("original_goal", None)
                context["original_goal_omitted_from_hook"] = True
                context["original_goal_available_via_readback"] = True
        if not include_full_original:
            # Do not rely on a valid locator for confidentiality: an invalid
            # registration may still return original words in a partial state.
            context.pop("original_goal", None)
        if not include_full_original and isinstance(
                context.get("native_decision_state"), dict):
            # Native audit contains raw original_goal and private research
            # proposals. Do not embed them in a Codex SessionStart/spill.
            # Only the explicit, checked same-ledger dereference may expose
            # original evidence when the reasoning task actually needs it.
            decision = context["native_decision_state"]
            context["native_decision_state"] = {
                key: decision[key] for key in (
                    "status", "observation_sha256", "decision_count",
                    "open_research_count", "owner_outcome_verified",
                    "business_outcome_verified")
                if key in decision
            }
        if not include_full_original and isinstance(
                context.get("original_obligation_progress"), list):
            # Owner clause wording stays in the canonical task/child source.
            context["original_obligation_progress"] = [{
                key: item[key] for key in (
                    "child_task_id", "task_state", "error_code",
                    "owner_outcome_verified")
                if key in item
            } for item in context["original_obligation_progress"]
                if isinstance(item, dict)]
        if not include_full_original and "original_goals" in context:
            # Ambiguous roots need selection; don't leak all private originals
            # into a startup hook merely because their identities are listed.
            context["ambiguous_goal_count"] = len(context["original_goals"])
            context.pop("original_goals", None)
            ids = context.get("root_task_ids")
            if (isinstance(ids, list) and ids
                and all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{32}", v)
                        for v in ids)):
                # Bind BOTH original identity and original wording. IDs
                # alone survive a source edit and could reveal a different
                # goal under a stale locator.
                identity = hashlib.sha256(json.dumps(
                    sorted(state["original_goals"],
                           key=lambda item: item["root_task_id"]),
                    ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                context["ambiguous_goal_readback"] = {
                    "entrypoint": "scripts/codex_session_context.py",
                    "arguments": ["--readback-ambiguous", identity],
                    "source_role": "READ_ONLY_EXISTING_SQLITE_GOALS",
                }
    except (ImportError, OSError, ValueError, TypeError) as exc:
        context["status"] = "DURABLE_CONTEXT_UNAVAILABLE"
        context["readback_error_class"] = type(exc).__name__
    return context


def _readback_original(root_id: str, expected_digest: str) -> dict:
    """Explicit full-source dereference; never an execution permission."""
    if (not re.fullmatch(r"[0-9a-f]{32}", root_id)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)):
        return {"status": "INVALID_ORIGINAL_READBACK_IDENTITY",
                "original_goal_verified": False}
    state = build_context({"cwd": str(ROOT)}, include_full_original=True)
    if (state.get("root_task_id") != root_id
        or state.get("original_contract_sha256") != expected_digest
        or state.get("original_goal_verified") is not True):
        return {"status": "ORIGINAL_READBACK_IDENTITY_UNVERIFIED",
                "original_goal_verified": False}
    # Return the identical read-only projection, not a separate state store.
    return {"status": "ORIGINAL_READBACK_IDENTITY_MATCHED",
            "readback": state, "scheduling_or_effects_performed": False}



def _readback_ambiguous(expected_digest: str) -> dict:
    """Read *all* attested ambiguous originals without choosing one."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        return {"status": "INVALID_AMBIGUOUS_READBACK_IDENTITY"}
    state = build_context({"cwd": str(ROOT)}, include_full_original=True)
    ids = state.get("root_task_ids")
    if (state.get("status") != "AMBIGUOUS_OPEN_OWNER_GOALS"
        or not isinstance(ids, list) or not ids
        or not isinstance(state.get("original_goals"), list)
        or hashlib.sha256(json.dumps(
            sorted(state["original_goals"],
                   key=lambda item: item["root_task_id"]),
            ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")
        ).hexdigest() != expected_digest):
        return {"status": "AMBIGUOUS_READBACK_IDENTITY_UNVERIFIED"}
    return {"status": "AMBIGUOUS_READBACK_IDENTITY_MATCHED",
            "readback": state, "scheduling_or_effects_performed": False}


def _readback_state(expected_digest: str) -> dict:
    """Read the EXACT current continuity observation, not a stale digest."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        return {"status": "INVALID_CONTINUITY_READBACK_IDENTITY",
                "original_goal_verified": False}
    state = build_context({"cwd": str(ROOT)}, include_full_original=True)
    locator = state.get("continuity_state_readback")
    if (not isinstance(locator, dict)
        or locator.get("arguments") != ["--readback-state", expected_digest]):
        return {"status": "CONTINUITY_STATE_READBACK_STALE",
                "original_goal_verified": False}
    # Readback confirms a pinned observation, not a task/effect grant or
    # independent owner outcome. AUTHORITY_REVOKED stays non-runnable.
    return {"status": "CONTINUITY_STATE_READBACK_MATCHED",
            "readback": state, "scheduling_or_effects_performed": False}


def main(argv: tuple[str, ...] = ()) -> int:
    # Explicit argv decouples the callable hook from embedding processes
    # (unittest/pytest/Codex hosts may have unrelated sys.argv flags).
    # The executable script still receives its real CLI argv at __main__.
    if argv:
        if len(argv) == 2 and argv[0] == "--readback-state":
            result = _readback_state(argv[1])
        elif len(argv) == 3 and argv[0] == "--readback-original":
            result = _readback_original(argv[1], argv[2])
        elif len(argv) == 2 and argv[0] == "--readback-ambiguous":
            result = _readback_ambiguous(argv[1])
        else:
            print(json.dumps({"status": "INVALID_ORIGINAL_READBACK_ARGUMENTS",
                              "original_goal_verified": False}))
            return 2
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
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
    # Pass the full read-only observation to Codex. It, not this script,
    # controls preview versus native disk-backed overflow. This hook never
    # registers a grant, runs an effect, or certifies a business outcome.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": note,
        }
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
