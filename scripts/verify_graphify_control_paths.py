"""Validate official Graphify output before trusting structural evidence.

Graph reachability is supporting evidence, never an authorization oracle.
"""
import argparse
import ast
import json
import subprocess
from pathlib import Path

REQUIRED_PATHS = (
    ("src_cognition_agent_os_cli_main", "src_cognition_agent_os_host_run_tick"),
    ("src_cognition_agent_os_host_run_tick", "src_cognition_agent_os_runner_run_once"),
    ("src_cognition_agent_os_runner_run_once", "src_cognition_agent_os_ledger_claim_one"),
    # Post-refactor: runner performs admission, a static adapter dispatches
    # capability-specific work. Prove BOTH real call edges independently.
    ("src_cognition_agent_os_runner_run_once", "src_cognition_agent_os_capability_dispatch_dispatch_capability"),
    # Graphify currently extracts runner->dispatch but not a Python function
    # reached through a static registry. Verify that hop with Python AST below.

    # The currently implemented bounded-control path, not merely an old P0-P3 skeleton.
    ("src_cognition_agent_os_host_run_tick", "src_cognition_agent_os_bounded_goal_control_advance_local_goals"),
    ("src_cognition_agent_os_bounded_goal_control_advance_local_goals", "src_cognition_agent_os_bounded_control_audit_verify_registered_control"),
    ("src_cognition_agent_os_bounded_goal_control_observe", "src_cognition_agent_os_goal_audit_audit_goal"),
    ("src_cognition_agent_os_bounded_control_audit_audit_controlled_candidate", "src_cognition_agent_os_bounded_outcome_oracle_assess_local_record"),
    ("src_cognition_agent_os_conformance_inspect_conformance", "src_cognition_agent_os_conformance_check_one"),
    ("src_cognition_agent_os_conformance_check_one", "src_cognition_agent_os_bounded_control_audit_audit_controlled_candidate"),
    # PR25: three must-have call paths for the actual SINGLE control kernel,
    # proved present as EXTRACTED/line-located in Graphify's PR merge-tree.
    ("src_cognition_agent_os_bounded_goal_control_advance_local_goals", "src_cognition_agent_os_control_kernel_drive_active_controller"),
    ("src_cognition_agent_os_outcome_feedback_advance_evidence_goals", "src_cognition_agent_os_control_kernel_drive_active_controller"),
    ("src_cognition_agent_os_control_kernel_drive_active_controller", "src_cognition_agent_os_ledger_current_guard"),
    ("src_cognition_agent_os_host_run_tick", "src_cognition_agent_os_outcome_feedback_advance_evidence_goals"),
    ("src_cognition_agent_os_conformance_check_one", "src_cognition_agent_os_outcome_feedback_verify_feedback_root"),
    # All post-planning local effects must use one authorization gate.
    # These are real official EXTRACTED call edges, not the checker inventing
    # reachability or an LLM asserting that a class has been repaired.
    ("src_cognition_agent_os_sandbox_effect_stage_one", "src_cognition_agent_os_ledger_current_guard"),
    ("src_cognition_agent_os_pipeline_oracle_review_pipeline", "src_cognition_agent_os_ledger_current_guard"),
    ("src_cognition_agent_os_repair_oracle_review_patch", "src_cognition_agent_os_ledger_current_guard"),
    ("src_cognition_agent_os_repo_repair_review_repo", "src_cognition_agent_os_ledger_current_guard"),
    ("src_cognition_agent_os_repo_refinement_freeze_revision", "src_cognition_agent_os_ledger_current_guard"),
    ("src_cognition_agent_os_repo_refinement_record_attempt", "src_cognition_agent_os_ledger_current_guard"),
)

def check(graph_path: Path, repo: Path) -> dict:
    g=json.loads(graph_path.read_text(encoding="utf-8"))
    nodes={n["id"] for n in g["nodes"]}
    edges={(e["source"],e["target"]) for e in g["links"]
           if e.get("relation")=="calls" and e.get("confidence")=="EXTRACTED"}
    sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    errors=[]
    if g.get("built_at_commit")!=sha:
        errors.append("STALE_GRAPH_COMMIT")
    if len(nodes)!=len(g["nodes"]):
        errors.append("DUPLICATE_NODE")
    if any(e["source"] not in nodes or e["target"] not in nodes
           for e in g["links"] if e["source"].startswith("src_") and e["target"].startswith("src_")):
        errors.append("DANGLING_REPOSITORY_EDGE")
    evidence=[]
    for src,dst in REQUIRED_PATHS:
        matches=[e for e in g["links"] if
                 e.get("source")==src and e.get("target")==dst
                 and e.get("relation")=="calls"
                 and e.get("confidence")=="EXTRACTED"]
        if not matches:
            errors.append("MISSING_EXTRACTED_CONTROL_EDGE:"+src+"->"+dst)
            continue
        citations=[e for e in matches if isinstance(e.get("source_file"),str)
                   and e["source_file"].startswith("src/")
                   and isinstance(e.get("source_location"),str)
                   and e["source_location"].startswith("L")
                   and e["source_location"][1:].isdigit()]
        if not citations:
            errors.append("MISSING_SOURCE_LOCATION:"+src+"->"+dst)
            continue
        evidence.append({"caller":src,"callee":dst,"confidence":"EXTRACTED",
                         "source_file":citations[0]["source_file"],
                         "source_location":citations[0]["source_location"]})
    # The intentionally static registry is indirect. Python AST, not a
    # guessed Graphify edge, must independently witness both the exact
    # goal_intent binding and its direct call to the legacy target function.
    try:
        module = ast.parse((repo / "src/cognition_agent_os/capability_dispatch.py")
                           .read_text(encoding="utf-8"))
        reg = next(n.value for n in module.body
                   if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "_HANDLERS"
                           for t in n.targets))
        mapping = {k.value: v.id for k, v in zip(reg.keys, reg.values)
                   if isinstance(k, ast.Constant) and isinstance(k.value, str)
                   and isinstance(v, ast.Name)}
        handler_name = mapping.get("goal_intent")
        handler = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                       and n.name == handler_name)
        imported = any(
            isinstance(n, ast.ImportFrom)
            and n.module == "intent_runtime"
            and any(alias.name == "run_intent" for alias in n.names)
            for n in ast.walk(handler))
        invoked = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "run_intent" for n in ast.walk(handler))
        if not (imported and invoked):
            errors.append("CAPABILITY_REGISTRY_INTENT_EXECUTION_UNPROVEN")
    except (OSError, ValueError, StopIteration, SyntaxError, TypeError, AttributeError):
        errors.append("CAPABILITY_REGISTRY_INTENT_EXECUTION_UNPROVEN")
    return {"status":"PASS" if not errors else "FAIL",
            "commit":sha,"nodes":len(nodes),"edges":len(g["links"]),
            "inferred_edges":sum(e.get("confidence")=="INFERRED" for e in g["links"]),
            "control_edges":evidence,
            "errors":errors,"semantic_outcome_verified":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("graph",type=Path)
    p.add_argument("--repo",type=Path,default=Path("."))
    p.add_argument("--output",type=Path,help="Write SHA-bound extracted control edges as reusable CI evidence")
    a=p.parse_args()
    result=check(a.graph,a.repo)
    if a.output:
        a.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+chr(10),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
    if result["status"]!="PASS":raise SystemExit(1)

if __name__=="__main__":main()
