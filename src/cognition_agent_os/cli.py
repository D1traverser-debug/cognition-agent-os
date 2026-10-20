"""Explicit, non-daemon CLI. A user/host must invoke each iteration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ledger import alter_authority, connect, create_task, initialize
from .runner import run_once


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cognition-os", description="Bounded P0/P1 evidence workflow, not autonomous host")
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
    run = sub.add_parser("worker-once")
    run.add_argument("--planner-mode", choices=["deterministic", "ollama-local"], default="deterministic")
    run.add_argument("--local-model", default=None)
    run.add_argument("--fail-at", choices=["after_claim", "after_artifact_before_commit"])
    sub.add_parser("revoke-write")
    sub.add_parser("bump-goal")
    sub.add_parser("status")
    args = p.parse_args(argv)
    if args.command == "worker-once":
        result = run_once(args.db, args.workspace, args.fixtures, fail_at=args.fail_at,
                          planner_mode=args.planner_mode, local_model=args.local_model)
        print(json.dumps(result, sort_keys=True))
        return 0
    db = connect(args.db)
    try:
        initialize(db)
        if args.command in ("seed-fixture", "seed-github"):
            spec = {"kind": "fixture", "old": args.old, "new": args.new} if args.command == "seed-fixture" else {
                "kind": "github", "repo": args.repo, "path": args.path, "old_ref": args.old_ref, "new_ref": args.new_ref}
            task_id = create_task(db, spec, interval_seconds=args.interval_seconds)
            result = {"task_id": task_id, "state": "PENDING"}
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
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
