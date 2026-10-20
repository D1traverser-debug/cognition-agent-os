"""Independent readback for real Windows Task Scheduler host invocations.

No process spawn in audit mode, no fake host_tick rows and no cloud calls.
The paired PowerShell test actually registers a task and lets Windows
Task Scheduler execute the production CLI in separate OS processes.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.runner import verify_artifact


def seed(root: Path) -> dict:
    root.mkdir(parents=True,exist_ok=True)
    db_path=root/"state.sqlite"
    if db_path.exists():
        raise ValueError("Scheduler probe never overwrites existing ledger")
    fixtures=root/"fixtures"
    fixtures.mkdir()
    (fixtures/"old.txt").write_bytes(b"scheduled-old\n")
    (fixtures/"new.txt").write_bytes(b"scheduled-new\n")
    db=connect(db_path)
    try:
        initialize(db)
        initial=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"},
                            due_at=time.time()-1)
        delayed=create_task(db,{"kind":"fixture","old":"old.txt","new":"new.txt"},
                            due_at=time.time()+70)
    finally:
        db.close()
    return {"status":"SEEDED_BY_TEST_PROCESS",
            "db":str(db_path),"fixtures":str(fixtures),
            "workspace":str(root/"workspace"),
            "task_ids":[initial,delayed],
            "requires_actual_scheduler_process":True}


def audit(root: Path) -> dict:
    path=root/"state.sqlite"
    fail={"status":"NOT_YET_VERIFIED","external_business_success":False,
          "owner_machine_unattended_proved":False}
    if not path.is_file() or path.is_symlink():
        return {**fail,"reason":"PRESEEDED_AUTHORITY_MISSING"}
    try:
        uri=path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
            db.row_factory=sqlite3.Row
            tasks=[dict(r) for r in db.execute(
                "SELECT * FROM tasks ORDER BY created_at,task_id")]
            tick_table=db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='host_ticks'""").fetchone()
            if not tick_table:
                return {**fail,"reason":"NO_OS_INVOKED_HOST_TICK"}
            row=db.execute("""SELECT ticks,processed_total,last_finished_at
                           FROM host_ticks WHERE singleton=1""").fetchone()
            if row is None:
                return {**fail,"reason":"NO_COMPLETED_TICKS"}
            if row["ticks"]<2 or row["processed_total"]!=2:
                return {**fail,"reason":"SECOND_SCHEDULED_TICK_NOT_OBSERVED",
                        "ticks":row["ticks"],"processed_total":row["processed_total"]}
            owner=db.execute("""SELECT grant_rev,goal_rev,write_allowed
                FROM authority WHERE singleton=1""").fetchone()
            if not owner or owner["grant_rev"]!=1 or owner["goal_rev"]!=1 or not owner["write_allowed"]:
                return {**fail,"reason":"AUTHORITY_IDENTITY_CHANGED"}
            if len(tasks)!=2 or any(r["state"]!="NEEDS_REVIEW" for r in tasks):
                return {**fail,"reason":"EXPECTED_EVIDENCE_TASKS_NOT_FINISHED",
                        "states":[r["state"] for r in tasks]}
            for task in tasks:
                if not verify_artifact(root/"workspace",task):
                    return {**fail,"reason":"PINNED_ARTIFACT_READBACK_FAILED",
                            "task_id":task["task_id"]}
            fixtures=root/"fixtures"
            if ((fixtures/"old.txt").read_bytes()!=b"scheduled-old\n" or
                (fixtures/"new.txt").read_bytes()!=b"scheduled-new\n"):
                return {**fail,"reason":"SOURCE_FILES_CHANGED"}
            return {"status":"HOSTED_WINDOWS_SCHEDULER_WITNESSED",
                "ticks":row["ticks"],"processed_total":row["processed_total"],
                "completed_tasks":len(tasks),
                "original_sources_preserved":True,
                "artifact_sha_readbacks_passed":True,
                "user_windows_host_tested":False,
                "unattended_prelogin_run_proved":False,
                "production_release_authorized":False}
    except (sqlite3.Error,OSError,ValueError) as exc:
        return {**fail,"reason":"READBACK_UNAVAILABLE",
                "diagnostic":type(exc).__name__}


def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=["seed","audit"])
    p.add_argument("--root",type=Path,required=True)
    args=p.parse_args()
    report=seed(args.root) if args.mode=="seed" else audit(args.root)
    print(json.dumps(report,sort_keys=True))
    return 0 if report["status"] in ("SEEDED_BY_TEST_PROCESS",
                                    "HOSTED_WINDOWS_SCHEDULER_WITNESSED") else 4


if __name__=="__main__":
    raise SystemExit(main())
