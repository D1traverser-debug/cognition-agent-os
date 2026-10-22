"""Validate official Graphify output before trusting structural evidence.

Graph reachability is supporting evidence, never an authorization oracle.
"""
import argparse
import json
import subprocess
from pathlib import Path

REQUIRED_PATHS = (
    ("src_cognition_agent_os_cli_main", "src_cognition_agent_os_host_run_tick"),
    ("src_cognition_agent_os_host_run_tick", "src_cognition_agent_os_runner_run_once"),
    ("src_cognition_agent_os_runner_run_once", "src_cognition_agent_os_ledger_claim_one"),
    ("src_cognition_agent_os_runner_run_once", "src_cognition_agent_os_intent_runtime_run_intent"),
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
    for src,dst in REQUIRED_PATHS:
        if (src,dst) not in edges:
            errors.append("MISSING_EXTRACTED_CONTROL_EDGE:"+src+"->"+dst)
    return {"status":"PASS" if not errors else "FAIL",
            "commit":sha,"nodes":len(nodes),"edges":len(g["links"]),
            "inferred_edges":sum(e.get("confidence")=="INFERRED" for e in g["links"]),
            "errors":errors,"semantic_outcome_verified":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("graph",type=Path)
    p.add_argument("--repo",type=Path,default=Path("."))
    a=p.parse_args()
    result=check(a.graph,a.repo)
    print(json.dumps(result,sort_keys=True))
    if result["status"]!="PASS":raise SystemExit(1)

if __name__=="__main__":main()
