"""Precommitted real-Host A/B for the cognitive-feedback extraction.

Compare the exact pre-extraction Git commit and the candidate HEAD on identical
isolated owner goals, permissions and input fixtures. Never call model APIs,
write production state, or claim unknown-goal cognition from local programs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

BASELINE_SHA = "89614f0d1ba0214f4717fb24c6a554158fbac54c"
SCENARIOS = ("exact_csv", "exact_json", "revoked_before_execution",
             "source_drift_after_first")
REPETITIONS = 2

# This program is executed in two isolated, separately imported repository
# revisions. It uses the actual Host, task ledger, Worker and owner oracle;
# no replacement planner / Worker / verdict is injected.
_WORKER = r'''
import hashlib, json, sys, tempfile
from contextlib import closing
from pathlib import Path
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.owner_postcondition import inspect_owner_local_outcome

case=sys.argv[1]
with tempfile.TemporaryDirectory(prefix="native-feedback-real-host-") as td:
    root=Path(td)
    db=root/"ledger.sqlite"
    work=root/"work";work.mkdir()
    fixtures=root/"fixtures";fixtures.mkdir()
    data={
        "baseline.csv":"id,amount\nA,7\n",
        "actual.csv":"id,amount\nA,5\n",
        "settings.json":'{"timeout":12}\n',
    }
    for name,value in data.items():
        (fixtures/name).write_text(value, encoding="utf-8")
    original={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in fixtures.iterdir()}
    with closing(connect(db)) as conn:
        initialize(conn)
    goal=("Compare baseline.csv with actual.csv and report differences."
          if case!="exact_json" else
          "Please ensure an isolated draft of settings.json has owner equal to ops.")
    root_id=register_native_goal(db, goal)
    if case=="revoked_before_execution":
        with closing(connect(db)) as conn:
            alter_authority(conn, revoke=True)
    ticks=[run_tick(
        db, work, fixtures, max_jobs=1, auto_native_cognition=True,
        auto_stage_goals=(case=="exact_json"))]
    if case=="source_drift_after_first":
        # The originally correct owner result must be invalidated by a real
        # fixture revision; no implied semantic success or duplicate effect.
        (fixtures/"actual.csv").write_text(
            "id,amount\\nA,999\\nB,5\\n", encoding="utf-8")
    ticks.append(run_tick(
        db, work, fixtures, max_jobs=1, auto_native_cognition=True,
        auto_stage_goals=(case=="exact_json")))
    outcome=inspect_owner_local_outcome(db, work, fixtures, root_id)
    with closing(connect(db)) as conn:
        children=conn.execute(
            "SELECT state,source_spec FROM tasks WHERE parent_task=?",
            (root_id,)).fetchall()
    snapshot={
        "case":case,
        "local_owner_outcome_verified":outcome["local_owner_outcome_verified"],
        "business_outcome_verified":outcome["business_outcome_verified"],
        "outcome_scope":outcome.get("outcome_scope"),
        "child_count":len(children),
        "tick_processed":[tick["processed"] for tick in ticks],
        "native_statuses":[[choice["status"] for choice in
                            tick["native_cognition"]] for tick in ticks],
        "source_unchanged":original=={
            p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in fixtures.iterdir()},
        "semantic_outcome_verified":any(
            tick["semantic_outcome_verified"] for tick in ticks),
    }
    print(json.dumps(snapshot,sort_keys=True,separators=(",",":")))
'''


def _run(command: list[str], cwd: Path, *, env: dict | None = None) -> str:
    return subprocess.check_output(
        command, cwd=cwd, env=env, text=True, stderr=subprocess.PIPE,
        timeout=90).strip()


def _worktree(repo: Path, target: Path, sha: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(target), sha],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _replay(root: Path, scenario: str) -> tuple[dict, float]:
    start=time.monotonic()
    env=os.environ.copy()
    env["PYTHONPATH"]=str(root/"src")
    data=json.loads(_run([sys.executable, "-c", _WORKER, scenario],root,env=env))
    return data, time.monotonic()-start


def _oracle(value: dict, scenario: str) -> bool:
    # Negative cases do not become "pass" by agreeing on a broken effect.
    if (value["source_unchanged"] !=
            (scenario != "source_drift_after_first")
        or value["business_outcome_verified"]):
        return False
    if value["semantic_outcome_verified"]:
        return False
    if scenario=="revoked_before_execution":
        return (not value["local_owner_outcome_verified"] and
                value["child_count"]==0 and value["tick_processed"]==[0,0])
    if scenario=="source_drift_after_first":
        return (not value["local_owner_outcome_verified"] and
                value["child_count"]==1 and value["tick_processed"]==[1,0])
    return (value["local_owner_outcome_verified"] and
            value["child_count"]==1 and value["tick_processed"]==[1,0])


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",type=Path,default=Path("."))
    parser.add_argument("--output",type=Path,default=Path("native_feedback_seam_ab.json"))
    args=parser.parse_args()
    repo=args.repo.resolve()
    candidate=_run(["git","rev-parse","HEAD"],repo)
    if (not re.fullmatch("[0-9a-f]{40}",candidate)
        or candidate==BASELINE_SHA):
        raise SystemExit("INVALID_OR_IDENTICAL_AB_CANDIDATE")
    _run(["git","cat-file","-e",BASELINE_SHA+"^{commit}"],repo)
    report={
        "baseline_sha":BASELINE_SHA,"candidate_sha":candidate,
        "scope":"ISOLATED_REGISTERED_OWNER_LOCAL_TASKS_ONLY",
        "source":"ACTUAL_HOST_LEDGER_WORKER_OWNER_ORACLE",
        "model_calls":0,"repetitions":REPETITIONS,
        "semantic_ability_proven":False,"real_chatgpt_activation_proven":False,
        "cases":[],"mismatches":[]
    }
    with tempfile.TemporaryDirectory(prefix="native-feedback-ab-") as td:
        baseline=Path(td)/"baseline"
        variant=Path(td)/"candidate"
        _worktree(repo,baseline,BASELINE_SHA)
        try:
            _worktree(repo,variant,candidate)
            try:
                for case in SCENARIOS:
                    observations=[]
                    for _ in range(REPETITIONS):
                        old,told=_replay(baseline,case)
                        new,tnew=_replay(variant,case)
                        observations.append((old,new,told,tnew))
                    equivalent=all(a==b for a,b,_,_ in observations)
                    stable=(all(a==observations[0][0] for a,_,_,_ in observations)
                            and all(b==observations[0][1] for _,b,_,_ in observations))
                    baseline_oracle=all(_oracle(a,case) for a,_,_,_ in observations)
                    candidate_oracle=all(_oracle(b,case) for _,b,_,_ in observations)
                    good=equivalent and stable and baseline_oracle and candidate_oracle
                    if not good:
                        report["mismatches"].append(case)
                    report["cases"].append({
                        "scenario":case,"equivalent":equivalent,
                        "repeat_stable":stable,
                        "baseline_oracle":baseline_oracle,
                        "candidate_oracle":candidate_oracle,
                        "baseline_observation":observations[0][0],
                        "candidate_observation":observations[0][1],
                        "baseline_seconds":[round(told,4) for _,_,told,_ in observations],
                        "candidate_seconds":[round(tnew,4) for _,_,_,tnew in observations],
                    })
            finally:
                subprocess.run(["git","-C",str(repo),"worktree","remove",
                                "--force",str(variant)],check=False,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        finally:
            subprocess.run(["git","-C",str(repo),"worktree","remove",
                            "--force",str(baseline)],check=False,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    report["result"]="PASS" if not report["mismatches"] else "FAIL"
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                           encoding="utf-8")
    print(json.dumps({"result":report["result"],
                      "baseline_sha":BASELINE_SHA,"candidate_sha":candidate,
                      "scenarios":len(report["cases"]),
                      "mismatches":report["mismatches"]},sort_keys=True))
    if report["mismatches"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
