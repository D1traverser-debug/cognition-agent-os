"""Explicit commands; only an external host can schedule host-tick."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .ledger import alter_authority, connect, create_task, initialize
from .host import HostNotConfigured, run_tick
from .runner import run_once
from .watch import create_watch
from .evaluation import EvaluationError, public_inputs, evaluate
from .reference_model import propose_reference_local
from .local_model import LocalModelUnavailable
from .goal_loop import validate_goal
from .goal_audit import audit_goal
from .sandbox_effect import stage_one


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cognition-os", description="Bounded P0/P1 evidence workflow; scheduling is external")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--fixtures", type=Path, default=Path("fixtures"))
    sub = p.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-fixture")
    seed.add_argument("--old", required=True)
    seed.add_argument("--new", required=True)
    seed.add_argument("--interval-seconds", type=int, default=0)
    gh = sub.add_parser("seed-github")
    gh.add_argument("--repo", required=True)
    gh.add_argument("--path", required=True)
    gh.add_argument("--old-ref", required=True)
    gh.add_argument("--new-ref", required=True)
    gh.add_argument("--interval-seconds", type=int, default=0)
    watch = sub.add_parser("seed-watch-github", help="Opt-in public branch watch; baseline first, no fake change")
    watch.add_argument("--repo", required=True)
    watch.add_argument("--path", required=True)
    watch.add_argument("--branch", default="main")
    watch.add_argument("--interval-seconds", type=int, default=1800)
    goal = sub.add_parser("seed-goal", help="Explicit bounded JSON/CSV conformance goal")
    goal.add_argument("--spec", type=Path, required=True)
    audit = sub.add_parser("goal-audit", help="Read-only, second-checker audit of a P5 goal artifact")
    audit.add_argument("--task-id", required=True)
    sandbox = sub.add_parser("goal-stage-sandbox",
                         help="Apply audited P5 proposal to isolated sandbox only, then read back")
    sandbox.add_argument("--task-id", required=True)
    run = sub.add_parser("worker-once")
    run.add_argument("--planner-mode", choices=["deterministic", "ollama-local"], default="deterministic")
    run.add_argument("--local-model", default=None)
    run.add_argument("--fail-at", choices=["after_claim", "after_artifact_before_commit"])
    host = sub.add_parser("host-tick", help="Run due jobs once; for OS-scheduled invocation")
    host.add_argument("--max-jobs", type=int, default=16)
    host.add_argument("--auto-stage-goals", action="store_true",
                      help="Explicitly opt in to local sandbox-only follow-up")
    host.add_argument("--planner-mode", choices=["deterministic", "ollama-local"], default="deterministic")
    host.add_argument("--local-model", default=None)
    export = sub.add_parser("reference-export", help="Export model-visible cases without reference gold")
    export.add_argument("--pack", type=Path, required=True)
    export.add_argument("--expected-pack-sha256", required=True)
    proposer = sub.add_parser("reference-propose-local", help="Opt-in local installed model candidate; no gold or self-grading")
    proposer.add_argument("--pack", type=Path, required=True)
    proposer.add_argument("--expected-pack-sha256", required=True)
    proposer.add_argument("--model", required=True)
    review = sub.add_parser("reference-evaluate", help="Read-only two-family evidence/reference gate")
    review.add_argument("--pack", type=Path, required=True)
    review.add_argument("--expected-pack-sha256", required=True)
    review.add_argument("--candidate", type=Path, required=True)
    sub.add_parser("revoke-write")
    sub.add_parser("bump-goal")
    sub.add_parser("status")
    args = p.parse_args(argv)
    if args.command == "goal-stage-sandbox":
        result=stage_one(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"]=="SANDBOX_VERIFIED" else 4
    if args.command == "goal-audit":
        result=audit_goal(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["mechanical_audit"] else 4
    if args.command == "worker-once":
        result = run_once(args.db, args.workspace, args.fixtures, fail_at=args.fail_at,
                          planner_mode=args.planner_mode, local_model=args.local_model)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "host-tick":
        try:
            result = run_tick(args.db, args.workspace, args.fixtures, max_jobs=args.max_jobs,
                              planner_mode=args.planner_mode, local_model=args.local_model,
                              auto_stage_goals=args.auto_stage_goals)
        except HostNotConfigured as exc:
            print(json.dumps({"status":"HOST_NOT_CONFIGURED", "error":str(exc)}))
            return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command in ("reference-export", "reference-evaluate", "reference-propose-local"):
        try:
            if args.command == "reference-export":
                result = public_inputs(args.pack, args.expected_pack_sha256)
            elif args.command == "reference-propose-local":
                result = propose_reference_local(
                    public_inputs(args.pack, args.expected_pack_sha256), model=args.model)
            else:
                result = evaluate(args.pack, args.expected_pack_sha256, args.candidate)
        except (EvaluationError, LocalModelUnavailable, OSError) as exc:
            print(json.dumps({"status":"UNVERIFIABLE", "reason":str(exc)}, sort_keys=True))
            return 3
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if args.command != "reference-evaluate" or result["status"] == "REFERENCE_MATCH" else 4
    db = connect(args.db)
    try:
        initialize(db)
        if args.command in ("seed-fixture", "seed-github"):
            spec = {"kind": "fixture", "old": args.old, "new": args.new} if args.command == "seed-fixture" else {
                "kind": "github", "repo": args.repo, "path": args.path, "old_ref": args.old_ref, "new_ref": args.new_ref}
            task_id = create_task(db, spec, interval_seconds=args.interval_seconds)
            result = {"task_id": task_id, "state": "PENDING"}
        elif args.command == "seed-goal":
            if args.spec.is_symlink() or args.spec.stat().st_size > 16384:
                raise ValueError("Goal spec file must be bounded and regular")
            spec = validate_goal(json.loads(args.spec.read_text(encoding="utf-8")))
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner["write_allowed"]:
                raise PermissionError("Cannot enqueue new goal after write grant revocation")
            result={"task_id":create_task(db,spec),"state":"PENDING","goal_type":spec["goal_type"]}
        elif args.command == "seed-watch-github":
            result = {"watch_id":create_watch(db, args.repo, args.path, args.branch,
                        interval_seconds=args.interval_seconds), "state":"PENDING_BASELINE"}
        elif args.command == "revoke-write":
            alter_authority(db, revoke=True)
            result = {"grant": "REVOKED"}
        elif args.command == "bump-goal":
            alter_authority(db, goal_change=True)
            result = {"goal": "REVISED"}
        else:
            result = {"authority": dict(db.execute("SELECT * FROM authority").fetchone()),
                      "tasks": [dict(r) for r in db.execute("SELECT * FROM tasks ORDER BY created_at")],
                      "events": [dict(r) for r in db.execute("SELECT * FROM events ORDER BY event_id")]}
            if args.command == "status":
                try:
                    r = db.execute("SELECT * FROM host_ticks WHERE singleton=1").fetchone()
                except sqlite3.OperationalError:  # Before the first host invocation this table is absent.
                    r = None
                result["host_observation"] = dict(r) if r else None
                try:
                    result["watches"] = [dict(w) for w in db.execute("SELECT * FROM watch_sources ORDER BY created_at")]
                    result["watch_observations"] = [dict(o) for o in db.execute("SELECT * FROM watch_observations ORDER BY observation_id")]
                except sqlite3.OperationalError:
                    result["watches"] = []
                    result["watch_observations"] = []
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
