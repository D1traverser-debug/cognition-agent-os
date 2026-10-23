"""Compare the PR24 and PR25 architectures on EXACTLY the same scenarios.

No LLM/API calls, live writes, fake approvals, or separate task engines.
Measure behavioral equivalence AND failures, not unit-test count.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

BASELINE_SHA = "54c6de63caa47ced87f1e0cc534dec175e39dcf6"
SCENARIOS = (
    "legacy_switch", "feedback_structure_switch", "feedback_record_switch",
    "revocation", "source_drift", "two_goals", "admission_crash",
)
# Precommitted terminal-state oracle: a simultaneous regression in both
# versions must not pass merely because their traces agree.
EXPECTED_FINAL = {
    "legacy_switch": (("CONTROL_CANDIDATE_MATCHED", 2),),
    "feedback_structure_switch": (("FEEDBACK_EVIDENCE_READY", 2),),
    "feedback_record_switch": (("FEEDBACK_EVIDENCE_READY", 2),),
    "revocation": (("FEEDBACK_STOPPED", 1),),
    "source_drift": (("FEEDBACK_UNVERIFIABLE", 1),),
    "two_goals": (("FEEDBACK_EVIDENCE_READY", 2),
                  ("FEEDBACK_EVIDENCE_READY", 2)),
    "admission_crash": (("UNKNOWN", 1),),
}

_WORKER = r'''
import json, os, sqlite3, sys, tempfile
from pathlib import Path
from contextlib import closing
from cognition_agent_os.ledger import connect, initialize, alter_authority
from cognition_agent_os.host import run_tick
from cognition_agent_os.bounded_goal_control import register_local_goal
from cognition_agent_os.outcome_feedback import register_evidence_goal

scenario=sys.argv[1]
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    db=root/"ledger.sqlite"
    workspace=root/"work";workspace.mkdir()
    fx=root/"fixtures";fx.mkdir()
    with closing(connect(db)) as conn:
        initialize(conn)
    (fx/"bad.json").write_text('{"id":"A","owner":"wrong"}')
    (fx/"good.csv").write_text("id\nA\n")
    (fx/"amb_ref.csv").write_text("code,zone\nA,1\nB,2\n")
    (fx/"amb_obs.csv").write_text("code,zone\nA,1\nB,2\n")
    (fx/"ref.csv").write_text("id,amount\nA,4\nB,5\n")
    (fx/"obs.csv").write_text("id,amount\nA,6\nB,5\n")
    structure=[
        {"kind":"goal_case","goal_type":"json_keys",
         "input":"bad.json","desired":{"owner":"ops"}},
        {"kind":"goal_case","goal_type":"csv_columns",
         "input":"good.csv","desired":{"owner":"ops"}}]
    reconciliation=[
        {"kind":"record_reconciliation","reference":"amb_ref.csv",
         "observed":"amb_obs.csv","objective":"identify_discrepancies"},
        {"kind":"record_reconciliation","reference":"ref.csv",
         "observed":"obs.csv","objective":"identify_discrepancies"}]
    if scenario=="legacy_switch":
        root_id=register_local_goal(db,fx,goal_id="stable-owner",
            target={"id":"A","owner":"ops"},alternatives=structure)
    elif scenario=="two_goals":
        root_id=register_evidence_goal(db,fx,goal_id="one",
            objective="Local evidence",alternatives=structure)
        other=register_evidence_goal(db,fx,goal_id="two",
            objective="Independent source differences",alternatives=reconciliation)
    else:
        kind=reconciliation if scenario=="feedback_record_switch" else structure
        root_id=register_evidence_goal(db,fx,goal_id="case",
            objective="Bounded independent outcome evidence",alternatives=kind)
    roots=[root_id]+([other] if scenario=="two_goals" else [])
    def snapshot():
        with closing(connect(db)) as conn:
            all_states=[]
            for rid in roots:
                parent=conn.execute(
                    "SELECT state,error_code FROM tasks WHERE task_id=?",
                    (rid,)).fetchone()
                children=conn.execute(
                    "SELECT state,error_code,source_spec FROM tasks "
                    "WHERE parent_task=? ORDER BY created_at,task_id",
                    (rid,)).fetchall()
                receipt=conn.execute(
                    "SELECT kind FROM events WHERE task_id=? AND "
                    "kind IN ('BOUNDED_CONTROLLER_ADMITTED','FEEDBACK_ADMITTED') "
                    "ORDER BY event_id",(rid,)).fetchall()
                all_states.append({
                    "root_state":parent["state"],
                    "root_error":parent["error_code"],
                    "children":[
                        {"state":c["state"],"error":c["error_code"],
                         "kind":json.loads(c["source_spec"])["kind"]}
                        for c in children],
                    "admissions":len(receipt),
                })
            return all_states
    traces=[snapshot()]
    for i in range(4):
        if scenario=="revocation" and i==1:
            with closing(connect(db)) as conn:
                alter_authority(conn,revoke=True)
        if scenario=="source_drift" and i==1:
            (fx/"bad.json").write_text('{"id":"A","owner":"tampered"}')
        if scenario=="admission_crash" and i==1:
            # A persisted child survives while its attempt index is lost.
            # Conformance must refuse to admit a replacement child.
            with closing(connect(db)) as conn:
                conn.execute(
                    "DELETE FROM evidence_feedback_attempts WHERE root_task_id=?",
                    (root_id,))
                conn.commit()
        run_tick(db,workspace,fx,max_jobs=4,auto_local_goal_control=True)
        traces.append(snapshot())
    print(json.dumps({"scenario":scenario,"traces":traces},
        sort_keys=True,separators=(",",":")))
'''


def _run(command: list[str], cwd: Path, *, env=None) -> str:
    return subprocess.check_output(
        command, cwd=cwd, env=env, text=True, stderr=subprocess.PIPE,
        timeout=90
    ).strip()


def _worktree(repo: Path, target: Path, sha: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach",
         str(target), sha], check=True, capture_output=True, text=True)


def _replay(root: Path, case: str) -> tuple[dict, float]:
    start=time.monotonic()
    env=os.environ.copy()
    env["PYTHONPATH"]=str(root/"src")
    output=_run([sys.executable, "-c", _WORKER, case], root, env=env)
    result=json.loads(output)
    return result,time.monotonic()-start


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",type=Path,default=Path("."))
    parser.add_argument("--baseline",default=BASELINE_SHA)
    parser.add_argument("--repetitions",type=int,default=3)
    parser.add_argument("--output",type=Path,default=Path("architecture_ab.json"))
    args=parser.parse_args()
    if args.baseline != BASELINE_SHA or not 2 <= args.repetitions <= 5:
        raise SystemExit("BASELINE_OR_REPETITION_CONTRACT_INVALID")
    repo=args.repo.resolve()
    expected=_run(["git","rev-parse","HEAD"],repo)
    _run(["git","cat-file","-e",args.baseline+"^{commit}"],repo)
    with tempfile.TemporaryDirectory(prefix="control-architecture-ab-") as td:
        workspace=Path(td)
        base=workspace/"base"
        candidate=workspace/"candidate"
        _worktree(repo,base,args.baseline)
        _worktree(repo,candidate,expected)
        records=[]
        mismatch=[]
        try:
            for case in SCENARIOS:
                originals=[]
                variants=[]
                durations={"baseline":[],"candidate":[]}
                for _ in range(args.repetitions):
                    old,told=_replay(base,case)
                    new,tnew=_replay(candidate,case)
                    originals.append(old)
                    variants.append(new)
                    durations["baseline"].append(told)
                    durations["candidate"].append(tnew)
                repeat_stable=(len({
                    json.dumps(x,sort_keys=True) for x in originals})==1 and
                    len({json.dumps(x,sort_keys=True) for x in variants})==1)
                equivalent=all(a==b for a,b in zip(originals,variants))
                expected=list(EXPECTED_FINAL[case])
                baseline_final=[
                    (r["root_state"],len(r["children"]))
                    for r in originals[0]["traces"][-1]]
                candidate_final=[
                    (r["root_state"],len(r["children"]))
                    for r in variants[0]["traces"][-1]]
                oracle_pass=(baseline_final==expected and
                             candidate_final==expected)
                if not equivalent or not repeat_stable or not oracle_pass:
                    mismatch.append(case)
                records.append({
                    "scenario":case,
                    "equivalent":equivalent,
                    "repeat_stable":repeat_stable,
                    "oracle_pass":oracle_pass,
                    "expected_terminal":expected,
                    "baseline_terminal":baseline_final,
                    "candidate_terminal":candidate_final,
                    "baseline_median_seconds":round(
                        statistics.median(durations["baseline"]),4),
                    "candidate_median_seconds":round(
                        statistics.median(durations["candidate"]),4),
                    "baseline_trace":originals[0],
                    "candidate_trace":variants[0],
                })
        finally:
            for folder in (candidate,base):
                subprocess.run(["git","-C",str(repo),"worktree","remove",
                                "--force",str(folder)],
                               capture_output=True,check=False)
    # No unearned "autonomous business success" claim from mechanical replay.
    report={
        "comparison":"PR24_vs_PR25_SAME_SCENARIOS",
        "baseline_sha":args.baseline,
        "candidate_commit":expected,
        "scope":"ISOLATED_LOCAL_TASK_CONTROL_ONLY",
        "repetitions":args.repetitions,
        "scenarios":list(SCENARIOS),
        "result":"PASS" if not mismatch else "FAIL",
        "mismatches":mismatch,
        "cases":records,
        "business_outcome_verified":False,
        "real_host_unattended_verified":False,
        "architecture_global_optimum_proven":False,
    }
    args.output.write_text(
        json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
        encoding="utf-8")
    print(json.dumps({
        "result":report["result"],"baseline":args.baseline,
        "candidate":expected,"repetitions":args.repetitions,
        "cases":len(records),"mismatches":mismatch,
    },sort_keys=True))
    if mismatch:
        raise SystemExit(1)


if __name__=="__main__":
    main()
