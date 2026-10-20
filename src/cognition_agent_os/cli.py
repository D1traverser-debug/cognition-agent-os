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
from .reconciliation import validate_reconciliation
from .reconciliation_oracle import audit_stored_report
from .intent_planner import compile_intent
from .intent_runtime import audit_intent_plan
from .semantic_contract import load_pinned_relationship
from .conformance import inspect_conformance
from .repair_search import validate_repair_spec
from .repair_oracle import audit_patch,review_patch
from .outcome_attestation import verify_signed_outcome,prepare_unsigned_outcome
from .signed_feedback import record_signed_feedback,bind_owner_review_trust


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
    reconcile = sub.add_parser("seed-reconciliation",
                              help="Identify discrepancies between two small CSV sources")
    reconcile.add_argument("--reference",required=True)
    reconcile.add_argument("--observed",required=True)
    reconcile.add_argument("--relationship-contract",default=None)
    reconcile.add_argument("--expected-contract-sha256",default=None)
    report = sub.add_parser("reconciliation-audit",
                            help="Read-only independent SQL check of a proposed diff report")
    report.add_argument("--task-id",required=True)
    intent = sub.add_parser("seed-intent",help="Register constrained typed outcome for capability planning")
    intent.add_argument("--spec",type=Path,required=True)
    plan_audit = sub.add_parser("intent-audit",help="Read-only check of durable goal decomposition")
    plan_audit.add_argument("--task-id",required=True)
    goal = sub.add_parser("seed-goal", help="Explicit bounded JSON/CSV conformance goal")
    goal.add_argument("--spec", type=Path, required=True)
    intake_repair = sub.add_parser("seed-code-repair",
                         help="Bounded pure-function repair with externally pinned sealed holdout")
    intake_repair.add_argument("--source",required=True)
    intake_repair.add_argument("--function",required=True)
    intake_repair.add_argument("--visible",required=True)
    intake_repair.add_argument("--holdout",required=True)
    intake_repair.add_argument("--holdout-sha256",required=True)
    repair_audit = sub.add_parser("repair-audit",
                       help="Read-only independent check; holdout remains hidden from proposer")
    repair_audit.add_argument("--task-id",required=True)
    repair_audit.add_argument("--include-holdout",action="store_true")
    repair_review = sub.add_parser("repair-review",
                       help="Stage a pure repair candidate only after independent holdout acceptance")
    repair_review.add_argument("--task-id",required=True)
    unsigned=sub.add_parser("attestation-subject",
        help="Export unsigned exact-scope candidate for independent reviewer")
    unsigned.add_argument("--task-id",required=True)
    unsigned.add_argument("--principal",required=True)
    bind = sub.add_parser("attestation-bind-trust",
        help="Explicit write-once owner review policy enrollment; host never calls this")
    bind.add_argument("--allowed-signers",required=True,type=Path)
    bind.add_argument("--expected-allowed-sha256",required=True)
    bind.add_argument("--principal",required=True)
    imported = sub.add_parser("attestation-record",
        help="Explicitly import an externally signed accept/reject into existing ledger; never deploy")
    imported.add_argument("--statement",required=True,type=Path)
    imported.add_argument("--signature",required=True,type=Path)
    imported.add_argument("--allowed-signers",required=True,type=Path)
    imported.add_argument("--expected-allowed-sha256",required=True)
    imported.add_argument("--principal",required=True)
    signed = sub.add_parser("attestation-audit",
        help="Read-only independently signed outcome statement; no production promotion")
    signed.add_argument("--statement",required=True,type=Path)
    signed.add_argument("--signature",required=True,type=Path)
    signed.add_argument("--allowed-signers",required=True,type=Path)
    signed.add_argument("--expected-allowed-sha256",required=True)
    signed.add_argument("--principal",required=True)
    governance = sub.add_parser("conformance-audit",
        help="Inspect claims vs current evidence; --enforce quarantines confirmed contradictions")
    governance.add_argument("--max-cases",type=int,default=64)
    governance.add_argument("--enforce",action="store_true")
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
    if args.command == "attestation-subject":
        result=prepare_unsigned_outcome(
            args.db,args.workspace,args.fixtures,args.task_id,
            reviewer_principal=args.principal)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"]=="UNSIGNED_REVIEW_SUBJECT" else 4
    if args.command == "attestation-bind-trust":
        result=bind_owner_review_trust(
            args.db,args.workspace,args.fixtures,args.allowed_signers,
            args.expected_allowed_sha256,expected_principal=args.principal)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"] in ("OWNER_TRUST_BOUND",
                                        "OWNER_TRUST_ALREADY_BOUND") else 4
    if args.command == "attestation-record":
        result=record_signed_feedback(
            args.db,args.workspace,args.fixtures,args.statement,args.signature,
            args.allowed_signers,args.expected_allowed_sha256,
            expected_principal=args.principal)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"] in ("SIGNED_FEEDBACK_RECORDED",
                                        "SIGNED_FEEDBACK_ALREADY_RECORDED") else 4
    if args.command == "attestation-audit":
        result=verify_signed_outcome(
            args.db,args.workspace,args.fixtures,args.statement,args.signature,
            args.allowed_signers,args.expected_allowed_sha256,
            expected_principal=args.principal)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"]=="SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED" else 4
    if args.command == "repair-audit":
        result=audit_patch(args.db,args.workspace,args.fixtures,args.task_id,
             reveal_holdout=args.include_holdout,
             require_staged=False)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"] in ("VISIBLE_PATCH_MECHANICALLY_VALID",
                                        "HOLDOUT_ACCEPTED") else 4
    if args.command == "repair-review":
        result=review_patch(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"]=="REPAIR_LAB_VERIFIED" else 4
    if args.command == "conformance-audit":
        result=inspect_conformance(args.db,args.workspace,args.fixtures,
                                   enforce=args.enforce,max_cases=args.max_cases)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"] in ("MECHANICAL_EVIDENCE_OBSERVED",
                                        "NO_RUNTIME_EVIDENCE","PARTIAL_EVIDENCE") else 4
    if args.command == "intent-audit":
        result=audit_intent_plan(args.db,args.task_id)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"]=="PLAN_MECHANICALLY_VALID" else 4
    if args.command == "reconciliation-audit":
        result=audit_stored_report(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0 if result["status"]=="REPORT_MECHANICALLY_VERIFIED" else 4
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
        elif args.command == "seed-code-repair":
            spec=validate_repair_spec({
                "kind":"pure_code_repair","source":args.source,
                "function":args.function,"visible":args.visible,
                "holdout":args.holdout,
                "holdout_sha256":args.holdout_sha256})
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner["write_allowed"]:
                raise PermissionError("Repair task rejected after write revoke")
            result={"task_id":create_task(db,spec),"state":"PENDING",
                    "holdout_digest_pinned":True,
                    "scope":"local_pure_ast_only"}
        elif args.command == "seed-intent":
            if args.spec.is_symlink() or not args.spec.is_file() or args.spec.stat().st_size>16384:
                raise ValueError("Intent file not a small regular file")
            spec=json.loads(args.spec.read_text(encoding="utf-8"))
            plan=compile_intent(spec)
            if "relationship_contract" in plan["child_source_spec"]:
                # Prevent staging a claimed semantic approval without the
                # reviewed manifest bytes actually matching at intake.
                load_pinned_relationship(plan["child_source_spec"],args.fixtures)
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner["write_allowed"]:
                raise PermissionError("New intent refused after write revocation")
            result={"task_id":create_task(db,spec),"state":"PENDING",
                    "planned_capability":plan["capability"],"plan_sha256":plan["plan_sha256"]}
        elif args.command == "seed-reconciliation":
            if (args.relationship_contract is None)!=(args.expected_contract_sha256 is None):
                raise ValueError("Both relationship manifest and independently pinned SHA256 required")
            raw_spec={"kind":"record_reconciliation",
                      "reference":args.reference,"observed":args.observed,
                      "objective":"identify_discrepancies"}
            if args.relationship_contract is not None:
                raw_spec["relationship_contract"]={
                    "path":args.relationship_contract,
                    "expected_sha256":args.expected_contract_sha256}
            spec=validate_reconciliation(raw_spec)
            # Intake validates the actual externally-pinned manifest but does
            # not infer or bless any reviewer identity from file contents.
            load_pinned_relationship(spec,args.fixtures)
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner["write_allowed"]:
                raise PermissionError("New reconciliation task rejected after revocation")
            result={"task_id":create_task(db,spec),"state":"PENDING",
                    "objective":spec["objective"]}
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
