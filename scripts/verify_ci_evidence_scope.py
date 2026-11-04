"""A machine-readable explanation of what a green GitHub workflow DIDN'T test.

Uses GitHub's native 'needs' job results (no self-score or external API).
Does not pretend that source or CI proves a user's business result.
"""
import argparse
import json
import os
from pathlib import Path

CORE = (
    "pr_merge_compatibility",
    "offline_regression",
    "windows_offline_regression",
    "installed_cli_cross_platform",
    "native_mcp_stdio_integration",
    "windows_native_scheduler",
    "repo_container_integration",
    "graphify_official_code_inventory",
)
OPTIONAL = (
    "architecture_ab_equivalence",
    "native_feedback_seam_ab",
    "experimental_real_local_model",
    "experimental_public_feedback_model",
    "experimental_local_7b_capacity",
    "live_public_source",
    "aoci_official_bootstrap_probe",
    "chatgpt_plugin_release_bundle",
    "experimental_real_native_cognition",
    "experimental_live_open_goal_method",
    "experimental_open_goal_relevance",
    "native_child_readonly_holdout",
)


def classify_needs(needs: dict) -> tuple[dict, bool]:
    expected = set(CORE) | set(OPTIONAL)
    missing = sorted(expected - set(needs))
    if missing:
        raise ValueError("Missing job result source: " + ",".join(missing))
    outcomes = {}
    for name in (*CORE, *OPTIONAL):
        state = needs[name]
        if not isinstance(state, dict):
            raise ValueError("Malformed GitHub job result for " + name)
        result = state.get("result")
        if result not in ("success", "failure", "cancelled", "skipped"):
            raise ValueError("Unknown job result for " + name + ": " + repr(result))
        outcomes[name] = result
    blocked = {name: outcomes[name] for name in CORE
               if outcomes[name] != "success"}
    receipt = {
        "schema": "cognition-ci-evidence-scope-v1",
        "status": "ENGINEERING_GATES_PASSED" if not blocked else "CORE_GATE_UNVERIFIED",
        "source_revision_checked_separately_in_all_jobs": True,
        "pr_merge_integration_checked_separately": outcomes["pr_merge_compatibility"] == "success",
        "core_jobs": {name: outcomes[name] for name in CORE},
        "core_blockers": blocked,
        "optional_jobs": {name: outcomes[name] for name in OPTIONAL},
        "optional_skipped": sorted(n for n in OPTIONAL if outcomes[n] == "skipped"),
        "owner_original_goal_verification": "NOT_TESTED_BY_GITHUB_CI",
        "chatgpt_skill_auto_trigger": "NOT_TESTED_BY_GITHUB_CI",
        "codex_real_session_inheritance": "NOT_TESTED_BY_GITHUB_CI",
        "new_domain_autonomous_research_and_business_outcome": "NOT_TESTED_BY_GITHUB_CI",
        "product_ready": False,
    }
    return receipt, not blocked



# Prior first-hand, unmocked comparison (two Ollama models and independent
# local owner readback), NOT a product/biz result. Verified before this rule
# was introduced; see PR #50 comment #6442492450 and Actions #40506810543.
# Do not spend another model/runner call on the same question just because
# someone can type an opt-in marker. The CI runner has no semantic judgment
# authority: it can only validate concrete changes to experiment input/method.
PRIOR_NATIVE_EXPERIMENT_SHA = "f6355d3cc47155c0c7dbb01a0db5f22ad68bd8fa"
PRIOR_NATIVE_EXPERIMENT_RUN = 40506810543
_NATIVE_RETEST = {
    "[native-retest:changed-model-method]": (
        "src/cognition_agent_os/native_local_planner.py",
        "src/cognition_agent_os/native_decision.py",
        "src/cognition_agent_os/local_model.py",
    ),
    "[native-retest:changed-execution-oracle]": (
        "src/cognition_agent_os/host.py",
        "src/cognition_agent_os/owner_postcondition.py",
        "evaluation/owner_outcome_oracle.py",
    ),
    "[native-retest:new-owner-cases]": (
        "scripts/measure_real_native_goal.py",
    ),
}


def _semantic_python_source(source: str) -> str:
    """Compare Python executable AST, not comments or moved prose docstrings."""
    import ast
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(
                    first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body.pop(0)
    return ast.dump(tree, include_attributes=False)


def _native_cases(source: str) -> list:
    """Owner tasks and hidden labels, not a filename/change-count proxy."""
    import ast
    tree = ast.parse(source)
    matches = [node.value for node in tree.body
               if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "CASES"
                       for target in node.targets)]
    if len(matches) != 1:
        raise ValueError("NATIVE_EXPERIMENT_CASES_NOT_RECOVERABLE")
    cases = ast.literal_eval(matches[0])
    if not isinstance(cases, list) or not cases:
        raise ValueError("NATIVE_EXPERIMENT_CASES_NOT_RECOVERABLE")
    return cases


def native_experiment_admission(body: str, read_revision):
    """Actual pre-action gate for optional REAL model inference.

    read_revision(relative_path, revision) returns canonical file bytes/text.
    A typed re-test hypothesis must correspond to a demonstrably changed
    model/Host behavior or independently frozen goal cases; text-only or
    unrelated changes cannot allow another model run. Admission is NOT a
    reason to claim the new method is correct or the full owner goal is done.
    """
    if not isinstance(body, str) or "[run-real-native-schema]" not in body:
        raise ValueError("NATIVE_EXPERIMENT_EXPLICIT_OPT_IN_REQUIRED")
    motives = [name for name in _NATIVE_RETEST if name in body]
    if len(motives) != 1:
        raise ValueError(
            "REUSE_PRIOR_NATIVE_EVIDENCE_UNLESS_ONE_FALSIFIABLE_RETEST_CHANGE: "
            "PR #50 #6442492450 / Actions #40506810543")
    reason = motives[0]
    changed = []
    for path in _NATIVE_RETEST[reason]:
        previous = read_revision(path, PRIOR_NATIVE_EXPERIMENT_SHA)
        just_before = read_revision(path, "HEAD^")
        current = read_revision(path, "HEAD")
        if isinstance(previous, bytes):
            previous = previous.decode("utf-8")
        if isinstance(just_before, bytes):
            just_before = just_before.decode("utf-8")
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        if reason == "[native-retest:new-owner-cases]":
            # Reusing an already accepted experiment delta on a later
            # unrelated commit must not buy an unlimited retry budget.
            distinct_past = _native_cases(previous) != _native_cases(current)
            distinct_now = _native_cases(just_before) != _native_cases(current)
        else:
            now = _semantic_python_source(current)
            distinct_past = _semantic_python_source(previous) != now
            distinct_now = _semantic_python_source(just_before) != now
        if distinct_past and distinct_now:
            changed.append(path)
    if not changed:
        raise ValueError("REUSE_PRIOR_NATIVE_EVIDENCE_NO_FRESH_COMMIT_DELTA")
    return {
        "status": "NEW_NATIVE_EXPERIMENT_PROBE_ADMISSIBLE_NOT_VALIDATED",
        "prior_run": PRIOR_NATIVE_EXPERIMENT_RUN,
        "prior_source": PRIOR_NATIVE_EXPERIMENT_SHA,
        "requested_falsifier": reason,
        "fresh_commit_scoped_delta": True,
        "changed_executable_or_owner_case_sources": changed,
        "real_model_ran": False,
        "owner_outcome_verified": False,
        "product_ready": False,
    }


def _git_source_reader(repo: Path):
    import subprocess
    root = repo.resolve()
    def read(path: str, revision: str):
        command = ["git", "-C", str(root), "show", revision + ":" + path]
        result = subprocess.run(command, capture_output=True, timeout=8,
                                check=False)
        if result.returncode:
            raise ValueError("PRIOR_OR_CURRENT_SOURCE_NOT_ACCESSIBLE:" + path)
        return result.stdout
    return read


def _codex_pretool() -> int:
    """Best-effort earlier Codex guard; CI preflight is authoritative here.

    Codex hooks must be actually trusted/loaded. ChatGPT is a separate
    invocation surface with no account-level hook installed by this repo.
    """
    import sys
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
        if event.get("hook_event_name") != "PreToolUse":
            return 0
        tool = event.get("tool_name")
        args = event.get("tool_input")
        if (tool != "mcp__GitHub__update_pull_request"
            or not isinstance(args, dict)
            or args.get("repository_full_name") !=
               "D1traverser-debug/cognition-agent-os"
            or args.get("pr_number") != 50):
            return 0
        body = args.get("body", "")
        if not isinstance(body, str) or "[run-real-native-schema]" not in body:
            return 0
        # Editing a PR body only prepares an intent. It cannot itself
        # download a model. Require one explicit prior-evidence comparison
        # reason here; the ACTUAL GitHub Actions effect entry independently
        # checks the prior source and fresh commit-specific executable delta.
        # Requiring that delta before the intent can be configured would
        # deadlock a legal 'set opt-in, then push correction' workflow.
        motives = [name for name in _NATIVE_RETEST if name in body]
        if len(motives) != 1:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "REUSE_PRIOR_NATIVE_EVIDENCE_UNLESS_ONE_FALSIFIABLE_"
                        "RETEST_CHANGE: PR #50 #6442492450"),
                }
            }))
        else:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        "Experiment intent prepared only. The real CI "
                        "pre-download gate must still verify fresh executable "
                        "or owner-case delta on the triggering commit; this "
                        "PR edit never certifies novelty or owner success."),
                }
            }))
        return 0
    except (ValueError, TypeError, OSError, json.JSONDecodeError):
        # Hook failure is not a trusted authority check; CI has the final
        # actual model download barrier and will fail closed.
        return 0


def _native_experiment_preflight() -> int:
    import sys
    try:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path or os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
            raise ValueError("NATIVE_EXPERIMENT_REQUIRES_PR_EVENT")
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        body = event["pull_request"]["body"]
        candidate = native_experiment_admission(
            body, _git_source_reader(Path(__file__).resolve().parents[1]))
        print("NATIVE_EXPERIMENT_PREFLIGHT " + json.dumps(candidate, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, TimeoutError) as exc:
        print("NATIVE_EXPERIMENT_PREFLIGHT_REJECTED " + str(exc), file=sys.stderr)
        return 1

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-experiment-preflight", action="store_true")
    parser.add_argument("--codex-pretool", action="store_true")
    args = parser.parse_args()
    if args.native_experiment_preflight:
        raise SystemExit(_native_experiment_preflight())
    if args.codex_pretool:
        raise SystemExit(_codex_pretool())
    if args.output is None:
        parser.error("--output is required for evidence scope")
    raw = os.environ.get("COGNITION_CI_NEEDS")
    if not raw:
        raise ValueError("missing native GitHub Actions needs results")
    result, ok = classify_needs(json.loads(raw))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("CI_SCOPE_RECEIPT " + json.dumps(result, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as out:
            out.write("## cognition-agent-os: CI evidence scope, NOT product acceptance\n\n")
            out.write("Core gate: **" + result["status"] + "**\n\n")
            out.write("Opt-in jobs not run: " +
                      ", ".join(result["optional_skipped"]) + "\n\n")
            out.write("**NOT tested:** actual ChatGPT/Codex Skill invocation, "
                      "complete user goal, novel-domain autonomy, "
                      "external child-business acceptance.\n")
    if not ok:
        raise SystemExit("CORE_GATE_UNVERIFIED: see ci-evidence-scope.json")


if __name__ == "__main__":
    main()
