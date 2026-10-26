"""Explicit commands; only an external host can schedule host-tick."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .ledger import alter_authority, connect, create_task, initialize
from .continuity import register_goal, resume_goal, checkpoint_goal
from .outcome_feedback import register_evidence_goal
from .host import HostNotConfigured, _admit_existing_ledger, run_tick
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
from .investigation import validate_investigation, audit_investigation
from .open_goal import validate_open_goal, audit_open_goal
from .domain_contract import validate_domain_task, audit_domain_contract
from .intent_runtime import audit_intent_plan
from .semantic_contract import load_pinned_relationship
from .conformance import inspect_conformance
from .repair_search import validate_repair_spec
from .repair_oracle import audit_patch,review_patch
from .pipeline_repair import validate_pipeline
from .pipeline_oracle import audit_pipeline,review_pipeline
from .container_lab import validate_task_spec
from .repo_repair import audit_repo,review_repo
from .repo_refinement import refine_repo_public
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
    native_seed = sub.add_parser("seed-native-goal",
        help="Register complete owner text for model-neutral current-tool decisions")
    native_seed.add_argument("--goal", required=True)
    native_seed.add_argument("--allow-public-tool-discovery", action="store_true")
    native_read = sub.add_parser("native-goal-readback",
        help="Read original native goal, live evidence and next-decision digest")
    native_read.add_argument("--root-task-id", required=True)
    native_admit = sub.add_parser("native-decision-admit",
        help="Admit one compared typed native-tool proposal under existing grant")
    native_admit.add_argument("--root-task-id", required=True)
    native_admit.add_argument("--spec", required=True, type=Path)
    open_input = sub.add_parser("seed-open-goal",
        help="Enqueue owner natural-language goal; local installed model selects registered LOCAL proposal method")
    open_input.add_argument("--goal", required=True)
    open_input.add_argument("--allow-public-tool-discovery", action="store_true",
        help="Explicitly allow disclosure of up to three goal-derived search terms to GitHub public repository search")
    domain_seed = sub.add_parser("seed-domain-contract",
        help="Inspect a public child-native adapter at a pinned SHA, read-only")
    domain_seed.add_argument("--repo", required=True)
    domain_seed.add_argument("--ref", required=True)
    domain_seed.add_argument("--domain-id", required=True)
    domain_seed.add_argument("--state-authority-key",
        help="Optional exact JSON checkpoint key declared by the child Manifest")
    domain_audit = sub.add_parser("domain-contract-audit",
        help="Independently re-read pinned child-native source and review receipt")
    domain_audit.add_argument("--task-id", required=True)
    open_audit = sub.add_parser("open-goal-audit",
        help="Read-only independent check of source-pinned open-goal child provenance")
    open_audit.add_argument("--task-id", required=True)
    intent = sub.add_parser("seed-intent",help="Register constrained typed outcome for capability planning")
    intent.add_argument("--spec",type=Path,required=True)
    investigate = sub.add_parser("seed-investigation",
        help="Opt-in an open question for locally selected, quoted source evidence")
    investigate.add_argument("--question",required=True)
    investigate_audit = sub.add_parser("investigation-audit",
        help="Read-only independent quotation and source-hash replay")
    investigate_audit.add_argument("--task-id",required=True)
    plan_audit = sub.add_parser("intent-audit",help="Read-only check of durable goal decomposition")
    plan_audit.add_argument("--task-id",required=True)
    bounded = sub.add_parser("seed-bounded-local-goal",
        help="Explicitly register two pinned local methods; no production mutation")
    bounded.add_argument("--spec",type=Path,required=True)
    feedback=sub.add_parser("seed-evidence-feedback",
        help="Register two pinned LOCAL capabilities for independent feedback; no external effect")
    feedback.add_argument("--spec",type=Path,required=True)
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
    seed_pipeline=sub.add_parser("seed-pipeline-repair",
       help="Queue bounded two-file coupled repair spec under current authority")
    seed_pipeline.add_argument("--spec",type=Path,required=True)
    pipeline_check=sub.add_parser("pipeline-audit",
       help="Independent read-only verifier, hidden only after candidate frozen")
    pipeline_check.add_argument("--task-id",required=True)
    pipeline_check.add_argument("--include-holdout",action="store_true")
    pipeline_review=sub.add_parser("pipeline-review",
       help="Isolated coupled code effect under authority + independent holdout")
    pipeline_review.add_argument("--task-id",required=True)
    repo_seed=sub.add_parser("seed-repo-repair",
        help="Queue whole-file repo candidate; Docker execution is separate and opt-in")
    repo_seed.add_argument("--spec",type=Path,required=True)
    repo_audit=sub.add_parser("repo-audit",
        help="Read-only digest/authority check without Docker or gold execution")
    repo_audit.add_argument("--task-id",required=True)
    repo_review=sub.add_parser("repo-review",
        help="Run entire candidate only in a preinstalled no-network Docker container")
    repo_review.add_argument("--task-id",required=True)
    refine=sub.add_parser("repo-refine-local",
        help="Explicit local-model + offline Docker public feedback loop; creates new reviewable child")
    refine.add_argument("--task-id",required=True)
    refine.add_argument("--model",required=True)
    refine.add_argument("--max-attempts",type=int,choices=(1,2,3),default=2)
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
    host.add_argument("--auto-review-repos", action="store_true",
                      help="Separately opt in to untrusted whole-file Python execution IN Docker; also requires --auto-stage-goals")
    host.add_argument("--auto-local-goal-control", action="store_true",
                      help="Opt in to bounded LOCAL candidate follow-ups, never external effects")
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
    sub.add_parser("status", help="Read existing ledger state; never initialize a new database")
    sub.add_parser("init", help="Explicitly create local prototype SQLite ledger (not a production authorization)")
    continuity_seed = sub.add_parser("seed-continuity",
        help="Explicitly anchor owner objective to an existing task; never grants authority")
    continuity_seed.add_argument("--spec", type=Path, required=True)
    sub.add_parser("goal-resume",
        help="Read-only cold-resume from SQLite goal and task authority; no task execution")
    continuity_advance = sub.add_parser("goal-checkpoint",
        help="Compare-and-set active goal's next existing task; no new grant")
    continuity_advance.add_argument("--goal-id", required=True)
    continuity_advance.add_argument("--expected-digest", required=True)
    continuity_advance.add_argument("--next-task-id", required=True)
    continuity_advance.add_argument("--observed-head-sha", default=None,
        help="Explicit GitHub HEAD reattestation; runtime independently re-reads it")
    args = p.parse_args(argv)
    if args.command == "init":
        if args.db.exists() or args.db.is_symlink():
            try:
                _admit_existing_ledger(args.db)
            except HostNotConfigured as exc:
                print(json.dumps({"status":"INITIALIZATION_REFUSED",
                    "reason":str(exc)[:160]},sort_keys=True))
                return 4
            print(json.dumps({"status":"ALREADY_INITIALIZED",
                "authority_unchanged":True,
                "production_effect_authorized":False},sort_keys=True))
            return 0
        try:
            if args.db.parent.is_symlink():
                raise OSError("Database parent must not be a symlink")
            db = connect(args.db)
            try:
                initialize(db)
                owner = dict(db.execute("SELECT * FROM authority WHERE singleton=1").fetchone())
            finally:
                db.close()
        except (OSError,sqlite3.Error) as exc:
            print(json.dumps({"status":"INITIALIZATION_REFUSED",
                "reason":str(exc)[:160]},sort_keys=True))
            return 4
        print(json.dumps({"status":"LOCAL_LEDGER_INITIALIZED",
            "goal_rev":owner["goal_rev"],"grant_rev":owner["grant_rev"],
            "local_write_allowed":bool(owner["write_allowed"]),
            "production_effect_authorized":False,
            "business_outcome_verified":False},sort_keys=True))
        return 0
    if args.command in ("seed-native-goal", "native-goal-readback",
                        "native-decision-admit"):
        from .native_decision import (
            register_native_goal, inspect_native_goal, admit_native_decision)
        try:
            if args.command == "seed-native-goal":
                tid=register_native_goal(
                    args.db, args.goal,
                    allow_public_discovery=args.allow_public_tool_discovery)
                result={"root_task_id":tid,"status":"NATIVE_GOAL_REGISTERED",
                        "owner_outcome_verified":False}
            elif args.command == "native-goal-readback":
                result=inspect_native_goal(
                    args.db,args.workspace,args.fixtures,args.root_task_id)
            else:
                if (args.spec.is_symlink() or not args.spec.is_file()
                    or args.spec.stat().st_size>16384):
                    raise ValueError("INVALID_NATIVE_DECISION_FILE")
                candidate=json.loads(args.spec.read_text(encoding="utf-8"))
                result=admit_native_decision(
                    args.db,args.workspace,args.fixtures,args.root_task_id,candidate)
        except (ValueError,TypeError,KeyError,PermissionError,
                OSError,sqlite3.Error) as exc:
            print(json.dumps({"status":"NATIVE_DECISION_REFUSED",
                "reason":str(exc)[:120],"owner_outcome_verified":False},
                sort_keys=True))
            return 4
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] not in (
            "NATIVE_GOAL_UNVERIFIABLE","NATIVE_SOURCE_CHANGED",
            "NATIVE_EVIDENCE_UNVERIFIABLE","NATIVE_GRANT_REVOKED"
        ) else 4
    if args.command == "goal-resume":
        result = resume_goal(
            args.db, workspace=args.workspace, fixtures=args.fixtures)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result["status"] in (
            "READY_TO_TICK", "READY_TO_RECOVER",
            "AWAITING_WORKER", "NEEDS_INDEPENDENT_REVIEW",
            "NEEDS_OWNER_OUTCOME_REVIEW",
            "LOCAL_OWNER_RESULT_VERIFIED",
            "READY_FOR_NATIVE_DECISION") else 4
    if args.command in ("seed-continuity", "goal-checkpoint"):
        try:
            if args.command == "seed-continuity":
                if (args.spec.is_symlink() or not args.spec.is_file()
                    or args.spec.stat().st_size > 8192):
                    raise ValueError("UNSAFE_CONTINUITY_INPUT")
                payload = json.loads(args.spec.read_text(encoding="utf-8"))
                result = register_goal(args.db, payload)
            else:
                result = checkpoint_goal(
                    args.db, args.goal_id,
                    expected_digest=args.expected_digest,
                    next_task_id=args.next_task_id,
                    observed_head_sha=args.observed_head_sha)
        except (ValueError, TypeError, KeyError, PermissionError,
                sqlite3.Error, OSError) as exc:
            print(json.dumps({"status":"CONTINUITY_NOT_ADMITTED",
                "reason":str(exc)[:120]}, sort_keys=True))
            return 4
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    if args.command == "attestation-subject":
        result=prepare_unsigned_outcome(
            args.db,args.workspace,args.fixtures,args.task_id,
            reviewer_principal=args.principal)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="UNSIGNED_REVIEW_SUBJECT" else 4
    if args.command == "attestation-bind-trust":
        result=bind_owner_review_trust(
            args.db,args.workspace,args.fixtures,args.allowed_signers,
            args.expected_allowed_sha256,expected_principal=args.principal)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] in ("OWNER_TRUST_BOUND",
                                        "OWNER_TRUST_ALREADY_BOUND") else 4
    if args.command == "attestation-record":
        result=record_signed_feedback(
            args.db,args.workspace,args.fixtures,args.statement,args.signature,
            args.allowed_signers,args.expected_allowed_sha256,
            expected_principal=args.principal)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] in ("SIGNED_FEEDBACK_RECORDED",
                                        "SIGNED_FEEDBACK_ALREADY_RECORDED") else 4
    if args.command == "attestation-audit":
        result=verify_signed_outcome(
            args.db,args.workspace,args.fixtures,args.statement,args.signature,
            args.allowed_signers,args.expected_allowed_sha256,
            expected_principal=args.principal)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="SIGNATURE_AND_MECHANICAL_SCOPE_VERIFIED" else 4
    if args.command == "repo-refine-local":
        result=refine_repo_public(
            args.db,args.workspace,args.fixtures,args.task_id,
            model=args.model,max_attempts=args.max_attempts)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="REVISED_PUBLIC_CANDIDATE_FROZEN" else 4
    if args.command == "repo-audit":
        result=audit_repo(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="REPO_BYTES_MECHANICALLY_VALID" else 4
    if args.command == "repo-review":
        result=review_repo(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="REPAIR_LAB_VERIFIED" else 4
    if args.command == "pipeline-audit":
        result=audit_pipeline(args.db,args.workspace,args.fixtures,
                  args.task_id,hidden=args.include_holdout)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] in ("VISIBLE_PIPELINE_VERIFIED",
                                        "HOLDOUT_ACCEPTED") else 4
    if args.command == "pipeline-review":
        result=review_pipeline(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="REPAIR_LAB_VERIFIED" else 4
    if args.command == "repair-audit":
        result=audit_patch(args.db,args.workspace,args.fixtures,args.task_id,
             reveal_holdout=args.include_holdout,
             require_staged=False)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] in ("VISIBLE_PATCH_MECHANICALLY_VALID",
                                        "HOLDOUT_ACCEPTED") else 4
    if args.command == "repair-review":
        result=review_patch(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="REPAIR_LAB_VERIFIED" else 4
    if args.command == "conformance-audit":
        result=inspect_conformance(args.db,args.workspace,args.fixtures,
                                   enforce=args.enforce,max_cases=args.max_cases)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] in ("MECHANICAL_EVIDENCE_OBSERVED",
                                        "NO_RUNTIME_EVIDENCE","PARTIAL_EVIDENCE") else 4
    if args.command == "domain-contract-audit":
        result = audit_domain_contract(args.db, args.workspace, args.task_id)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result["status"] == "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED" else 4
    if args.command == "open-goal-audit":
        result=audit_open_goal(args.db,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="METHOD_CANDIDATE_MECHANICALLY_GROUNDED" else 4
    if args.command == "investigation-audit":
        result = audit_investigation(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"] == "SOURCE_GROUNDED_UNREVIEWED" else 4
    if args.command == "intent-audit":
        result=audit_intent_plan(args.db,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="PLAN_MECHANICALLY_VALID" else 4
    if args.command == "reconciliation-audit":
        result=audit_stored_report(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="REPORT_MECHANICALLY_VERIFIED" else 4
    if args.command == "goal-stage-sandbox":
        result=stage_one(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result["status"]=="SANDBOX_VERIFIED" else 4
    if args.command == "goal-audit":
        result=audit_goal(args.db,args.workspace,args.fixtures,args.task_id)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
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
                              auto_stage_goals=args.auto_stage_goals,
                              auto_review_repos=args.auto_review_repos,
                              auto_local_goal_control=args.auto_local_goal_control)
        except HostNotConfigured as exc:
            print(json.dumps({"status":"HOST_NOT_CONFIGURED", "error":str(exc)}))
            return 2
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
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
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if args.command != "reference-evaluate" or result["status"] == "REFERENCE_MATCH" else 4
    if args.command == "seed-evidence-feedback":
        if not args.db.is_file() or args.db.is_symlink():
            print(json.dumps({"status":"HOST_NOT_CONFIGURED"},sort_keys=True))
            return 2
        try:
            if (args.spec.is_symlink() or not args.spec.is_file()
                or args.spec.stat().st_size>16384):
                raise ValueError("UNSAFE_FEEDBACK_SPEC")
            proposal=json.loads(args.spec.read_text(encoding="utf-8"))
            if (not isinstance(proposal,dict)
                or set(proposal) not in (
                    {"goal_id","objective","alternatives"},
                    {"goal_id","objective","alternatives","acceptance"},
                    {"goal_id","objective","alternatives","acceptance","execution_scope"})):
                raise ValueError("INVALID_FEEDBACK_SEED")
            tid=register_evidence_goal(args.db,args.fixtures,
                goal_id=proposal["goal_id"],
                objective=proposal["objective"],
                alternatives=proposal["alternatives"],
                acceptance=proposal.get("acceptance"),
                execution_scope=proposal.get("execution_scope","LOCAL_EVIDENCE_ONLY"))
        except (ValueError,TypeError,KeyError,OSError,sqlite3.Error,
                PermissionError) as exc:
            print(json.dumps({"status":"FEEDBACK_NOT_ADMITTED",
                "reason":str(exc)[:120]},sort_keys=True))
            return 4
        print(json.dumps({"task_id":tid,"state":"FEEDBACK_ACTIVE",
            "business_outcome_verified":False,
            "allowed_effect":("LOCAL_SANDBOX_ONLY" if
                proposal.get("execution_scope")=="LOCAL_SANDBOX_POSTCONDITION"
                else "LOCAL_EVIDENCE_ONLY")},sort_keys=True))
        return 0
    if args.command == "seed-bounded-local-goal":
        # This command NEVER creates a fresh grant or ledger automatically.
        if not args.db.is_file() or args.db.is_symlink():
            print(json.dumps({"status":"HOST_NOT_CONFIGURED"},sort_keys=True))
            return 2
        if (args.spec.is_symlink() or not args.spec.is_file()
            or args.spec.stat().st_size>16384):
            print(json.dumps({"status":"INVALID_LOCAL_GOAL_FILE"},sort_keys=True))
            return 3
        try:
            from .bounded_goal_control import register_local_goal
            payload=json.loads(args.spec.read_text(encoding="utf-8"))
            if not isinstance(payload,dict) or set(payload)!={"goal_id","target","alternatives"}:
                raise ValueError("INVALID_SEED_FIELDS")
            tid=register_local_goal(args.db,args.fixtures,
                goal_id=payload["goal_id"],target=payload["target"],
                alternatives=payload["alternatives"])
        except (ValueError,TypeError,KeyError,sqlite3.Error,OSError) as exc:
            print(json.dumps({"status":"LOCAL_GOAL_NOT_ADMITTED",
                              "reason":str(exc)[:120]},sort_keys=True))
            return 4
        print(json.dumps({"task_id":tid,"state":"CONTROL_ACTIVE",
                          "business_outcome_verified":False,
                          "scope":"LOCAL_CANDIDATE_ONLY"},sort_keys=True))
        return 0
    # Existing commands must never create a grant just by probing or
    # referencing a new --db path. Only the explicit init command does so.
    try:
        _admit_existing_ledger(args.db)
    except HostNotConfigured as exc:
        print(json.dumps({"status":"HOST_NOT_CONFIGURED",
            "reason":str(exc)[:160]},sort_keys=True))
        return 4
    db = connect(args.db)
    try:
        if args.command in ("seed-fixture", "seed-github"):
            spec = {"kind": "fixture", "old": args.old, "new": args.new} if args.command == "seed-fixture" else {
                "kind": "github", "repo": args.repo, "path": args.path, "old_ref": args.old_ref, "new_ref": args.new_ref}
            task_id = create_task(db, spec, interval_seconds=args.interval_seconds)
            result = {"task_id": task_id, "state": "PENDING"}
        elif args.command == "seed-repo-repair":
            if (args.spec.is_symlink() or not args.spec.is_file()
                or args.spec.stat().st_size>4096):
                raise ValueError("Unsafe repository task specification")
            spec=validate_task_spec(json.loads(args.spec.read_text(encoding="utf-8")))
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner or not owner["write_allowed"]:
                raise PermissionError("Repo experiment requires existing authority")
            result={"task_id":create_task(db,spec),"state":"PENDING",
                    "scope":"local_Docker_only_no_production_mutation"}
        elif args.command == "seed-pipeline-repair":
            if (args.spec.is_symlink() or not args.spec.is_file()
                or args.spec.stat().st_size>4096):
                raise ValueError("Unsafe coupled-pipeline input")
            spec=validate_pipeline(json.loads(args.spec.read_text(encoding="utf-8")))
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner or not owner["write_allowed"]:
                raise PermissionError("Pipeline repair disabled by authority")
            result={"task_id":create_task(db,spec),"state":"PENDING",
                    "scope":"isolated_two_file_ast_only"}
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
        elif args.command == "seed-domain-contract":
            spec = validate_domain_task({
                "kind":"domain_contract", "repo":args.repo,
                "ref":args.ref, "domain_id":args.domain_id,
                **({"state_authority_key":args.state_authority_key}
                   if args.state_authority_key else {})})
            owner = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner or not owner["write_allowed"]:
                raise PermissionError("No existing authority for local review artifact")
            result = {"task_id":create_task(db,spec),"state":"PENDING",
                      "scope":"PUBLIC_CHILD_SOURCE_READ_LOCAL_REVIEW_ONLY",
                      "parent_replacement_admitted":False,
                      "business_outcome_verified":False}
        elif args.command == "seed-open-goal":
            spec={"kind":"open_goal","goal":args.goal}
            if args.allow_public_tool_discovery:
                spec["allow_public_discovery"]=True
            spec=validate_open_goal(spec)
            owner=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner or not owner["write_allowed"]:
                raise PermissionError("Cannot admit open goal after grant revocation")
            result={"task_id":create_task(db,spec),"state":"PENDING",
                    "scope":("OWNER_EXPLICIT_PUBLIC_METADATA_RESEARCH"
                             if args.allow_public_tool_discovery
                             else "OWNER_LOCAL_SOURCES_PROPOSAL_ONLY"),
                    "public_search_authorized":args.allow_public_tool_discovery,
                    "requires_installed_local_model":True,
                    "business_outcome_verified":False}
        elif args.command == "seed-investigation":
            spec = validate_investigation({"kind": "investigate_goal",
                "question": args.question, "scope": "LOCAL_EVIDENCE_ONLY"})
            owner = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if not owner["write_allowed"]:
                raise PermissionError("Investigation rejected after write revoke")
            result = {"task_id": create_task(db, spec), "state": "PENDING",
                      "scope": "LOCAL_EVIDENCE_ONLY",
                      "semantic_outcome_verified": False}
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
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
