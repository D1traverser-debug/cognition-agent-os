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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
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
