"""Real bounded code repair experiments, independent sealed holdout and safety.

Every function is parsed to AST and interpreted, NEVER imported/executed.
All writes are in temporary workspace, never original source or production.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,create_task,initialize,alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.host import run_tick
from cognition_agent_os.conformance import inspect_conformance
from cognition_agent_os.repair_search import (
    RepairError,parse_function,propose_patch,validate_repair_spec
)
from cognition_agent_os.repair_oracle import (
    audit_patch,review_patch,_execute_independent,review_due_repairs
)

ROOT=Path(__file__).resolve().parents[1]


class PureRepairTests(unittest.TestCase):
    def setUp(self):
        holder=tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root=Path(holder.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.ws=self.root/"workspace";self.ws.mkdir()
        self.db=self.root/"state.sqlite"
        connection=connect(self.db);initialize(connection);connection.close()

    def seed(self,source,visible,holdout,*,function="condition",parent=None):
        source_name="function.py"
        self.fx.joinpath(source_name).write_text(source)
        self.fx.joinpath("visible.json").write_text(json.dumps(visible))
        hidden=json.dumps(holdout).encode()
        self.fx.joinpath("hidden.json").write_bytes(hidden)
        spec={"kind":"pure_code_repair","source":source_name,
              "function":function,"visible":"visible.json",
              "holdout":"hidden.json",
              "holdout_sha256":hashlib.sha256(hidden).hexdigest()}
        db=connect(self.db)
        tid=create_task(db,spec,parent=parent)
        db.close()
        return tid,spec

    def row(self,tid):
        db=connect(self.db)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:db.close()

    def receipt(self,tid,kind):
        db=connect(self.db)
        try:return [json.loads(r[0]) for r in db.execute(
            "SELECT details FROM events WHERE task_id=? AND kind=?",(tid,kind))]
        finally:db.close()

    def example_compare(self,*,reject=False,parent=None):
        source="def condition(x, threshold):\n    return x > threshold\n"
        visible=[
            {"args":[5,5],"expected":True},
            {"args":[6,5],"expected":True},
            {"args":[4,5],"expected":False}]
        holdout=[{"args":[7,7],"expected":True if not reject else False},
                 {"args":[0,8],"expected":False},
                 {"args":[12,8],"expected":True}]
        return self.seed(source,visible,holdout,parent=parent)

    def test_pure_repair_failure_after_goal_rotation_must_not_claim_unknown(self):
        from cognition_agent_os import repair_search
        tid,_=self.example_compare()
        def rotate(*args,**kwargs):
            db=connect(self.db)
            try:alter_authority(db,goal_change=True)
            finally:db.close()
            raise ValueError("Injected candidate proposal failure")
        with patch.object(repair_search,"propose_patch",side_effect=rotate):
            result=run_once(self.db,self.ws,self.fx)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["reason"],"STALE_GOAL")
        self.assertEqual(self.row(tid)["state"],"BLOCKED")

    def test_review_between_finalize_commit_and_result_read_cannot_be_misattributed(self):
        # A second trusted reviewer may legitimately promote an already
        # frozen proposal immediately after the original worker commits.
        # The worker's response must describe ITS OWN commit (NEEDS_REVIEW),
        # not claim the independent review's later REPAIR_LAB_VERIFIED.
        import cognition_agent_os.ledger as ledger
        tid,_=self.example_compare()
        original_finalize=ledger.finalize
        reviews=[]
        def finalize_then_independent_review(db,task,state,**kwargs):
            result=original_finalize(db,task,state,**kwargs)
            if result and task["task_id"]==tid and state=="NEEDS_REVIEW":
                # Separate SQLite connection and real independent gold review,
                # not an arbitrary forced task-state UPDATE.
                reviews.append(review_patch(self.db,self.ws,self.fx,tid))
            return result
        with patch.object(ledger,"finalize",side_effect=finalize_then_independent_review):
            report=run_once(self.db,self.ws,self.fx)
        self.assertEqual(len(reviews),1,reviews)
        self.assertEqual(reviews[0]["status"],"REPAIR_LAB_VERIFIED",reviews)
        self.assertEqual(self.row(tid)["state"],"REPAIR_LAB_VERIFIED")
        self.assertEqual(report["status"],"NEEDS_REVIEW",report)
        self.assertEqual(report["decision"],"BOUNDED_CODE_PATCH_PROPOSAL",report)
        self.assertEqual(report["mechanism"],"Gt->GtE",report)
        self.assertNotEqual(report["status"],self.row(tid)["state"])

    def test_comparison_patch_accepted_by_separate_holdout_oracle(self):
        tid,spec=self.example_compare()
        original=self.fx.joinpath("function.py").read_bytes()
        output=run_once(self.db,self.ws,self.fx)
        self.assertEqual(output["status"],"NEEDS_REVIEW",output)
        self.assertIn("Gt->GtE",output["mechanism"])
        artifact=json.loads((self.ws/"artifacts"/(tid+".json")).read_text())
        self.assertEqual(artifact["holdout_status"],"SEALED_NOT_READ_BY_PROPOSER")
        self.assertNotIn("holdout_passes",json.dumps(artifact))
        result=audit_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"VISIBLE_PATCH_MECHANICALLY_VALID")
        self.assertFalse(result["holdout_evaluated"])
        evaluated=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(evaluated["status"],"REPAIR_LAB_VERIFIED",evaluated)
        self.assertEqual(self.row(tid)["state"],"REPAIR_LAB_VERIFIED")
        actual=self.ws/"repair_lab"/(tid+".py")
        self.assertIn("x >= threshold",actual.read_text())
        self.assertEqual(self.fx.joinpath("function.py").read_bytes(),original)
        self.assertEqual(audit_patch(self.db,self.ws,self.fx,tid,
                         reveal_holdout=True,require_staged=True)["status"],"HOLDOUT_ACCEPTED")
        self.assertEqual(len(self.receipt(tid,"REPAIR_HOLDOUT_ACCEPTED")),1)
        self.assertEqual(review_patch(self.db,self.ws,self.fx,tid)["status"],"NOT_PENDING_REVIEW")
        self.assertFalse(evaluated["authorizes_source_mutation"])

    def test_arithmetic_correction_generalizes_to_unseen_inputs(self):
        visible=[{"args":[8,3],"expected":5},
                 {"args":[12,2],"expected":10},
                 {"args":[0,0],"expected":0}]
        hidden=[{"args":[9,4],"expected":5},
                {"args":[100,30],"expected":70},
                {"args":[-3,2],"expected":-5}]
        tid,_=self.seed("def condition(count, used):\n    return count + used\n",visible,hidden)
        first=run_once(self.db,self.ws,self.fx)
        self.assertEqual(first["status"],"NEEDS_REVIEW")
        self.assertEqual(first["mechanism"],"Add->Sub")
        self.assertEqual(review_patch(self.db,self.ws,self.fx,tid)["status"],"REPAIR_LAB_VERIFIED")
        self.assertEqual(inspect_conformance(self.db,self.ws,self.fx)["mechanically_valid"],1)

    def test_heldout_counterexample_refutes_unique_visible_patch(self):
        source="def condition(x, y):\n    return x < y\n"
        # Public probes single out '>' but cannot rule out a hidden upper
        # bound in the real requested behavior. Held-out 100 refutes it.
        visible=[{"args":[1,2],"expected":False},
                 {"args":[2,2],"expected":False},
                 {"args":[3,2],"expected":True},
                 {"args":[4,2],"expected":True}]
        hidden=[{"args":[100,2],"expected":False},
                {"args":[5,2],"expected":True},
                {"args":[-2,2],"expected":False}]
        tid,_=self.seed(source,visible,hidden)
        first=run_once(self.db,self.ws,self.fx)
        self.assertEqual(first["status"],"NEEDS_REVIEW")
        self.assertEqual(first["mechanism"],"Lt->Gt")
        self.assertEqual(audit_patch(self.db,self.ws,self.fx,tid)["status"],
                         "VISIBLE_PATCH_MECHANICALLY_VALID")
        result=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"HOLDOUT_REFUTED")
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")
        self.assertEqual(len(self.receipt(tid,"REPAIR_HOLDOUT_REJECTED")),1)
        self.assertEqual(self.receipt(tid,"REPAIR_HOLDOUT_ACCEPTED"),[])
        self.assertFalse((self.ws/"repair_lab").exists())

    def test_durable_negative_feedback_blocks_identical_refuted_method(self):
        source="def condition(x, y):\n    return x < y\n"
        visible=[{"args":[1,2],"expected":False},
                 {"args":[2,2],"expected":False},
                 {"args":[3,2],"expected":True},
                 {"args":[4,2],"expected":True}]
        holdout=[{"args":[100,2],"expected":False},
                 {"args":[5,2],"expected":True},
                 {"args":[-2,2],"expected":False}]
        original,spec=self.seed(source,visible,holdout)
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(review_patch(self.db,self.ws,self.fx,original)["status"],
                         "HOLDOUT_REFUTED")
        db=connect(self.db)
        repeated=create_task(db,spec)
        db.close()
        result=run_once(self.db,self.ws,self.fx)
        self.assertEqual(result["status"],"UNKNOWN")
        self.assertEqual(result["reason"],"IDENTICAL_REPAIR_PREVIOUSLY_REFUTED")
        self.assertFalse((self.ws/"artifacts"/(repeated+".json")).exists())
        # The same failed operator must not be falsely promoted or retested
        # against the exact same hidden oracle with identical public evidence.
        self.assertEqual(len(self.receipt(original,"REPAIR_HOLDOUT_REJECTED")),1)
        self.assertEqual(self.receipt(repeated,"REPAIR_HOLDOUT_ACCEPTED"),[])
        # New public evidence / explicit test revision must be evaluated afresh.
        self.fx.joinpath("visible.json").write_text(json.dumps(
            visible+[{"args":[7,2],"expected":True}]))
        db=connect(self.db)
        changed=create_task(db,spec)
        db.close()
        retry=run_once(self.db,self.ws,self.fx)
        self.assertEqual(retry["task_id"],changed)
        self.assertEqual(retry["status"],"NEEDS_REVIEW")

    def test_ambiguous_visible_alternatives_abstain_before_holdout(self):
        visible=[{"args":[5,5],"expected":True},
                 {"args":[5,5],"expected":True}]
        hidden=[{"args":[6,5],"expected":True},
                {"args":[4,5],"expected":False}]
        tid,_=self.seed("def condition(x,y):\n    return x>y\n",visible,hidden)
        outcome=run_once(self.db,self.ws,self.fx)
        self.assertEqual(outcome["status"],"UNKNOWN")
        self.assertEqual(outcome["reason"],"NO_UNAMBIGUOUS_VISIBLE_REPAIR")
        self.assertFalse((self.ws/"artifacts").exists())

    def test_no_original_failure_causes_no_guess(self):
        visible=[{"args":[6,5],"expected":True},{"args":[4,5],"expected":False}]
        tid,_=self.seed("def condition(x,y):\n    return x>y\n",visible,visible)
        result=run_once(self.db,self.ws,self.fx)
        self.assertEqual(result["reason"],"FAILURE_NOT_REPRODUCED")
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")

    def test_dangerous_arbitrary_code_refused_without_execution(self):
        attempts=[
            "import os\ndef condition(x):\n    return os.system('echo BAD')\n",
            "def condition(x):\n    return __import__('os').system('false')\n",
            "def condition(x):\n    while True: pass\n",
            "def condition(x):\n    return [z for z in range(x)]\n",
            "def condition(x):\n    return x**1000000\n",
            "def condition(x):\n    return x.attr\n",
            "@decorator\ndef condition(x):\n    return x>1\n"
        ]
        for source in attempts:
            with self.subTest(source=source),self.assertRaises(RepairError):
                parse_function(source.encode(),"condition")

    def test_holdout_changed_after_proposal_never_stages(self):
        tid,_=self.example_compare()
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        self.fx.joinpath("hidden.json").write_text("[]")
        result=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"HOLDOUT_UNVERIFIABLE")
        self.assertEqual(self.row(tid)["state"],"NEEDS_REVIEW")
        self.assertFalse((self.ws/"repair_lab").exists())

    def test_stale_authority_refuses_heldout_promotion(self):
        tid,_=self.example_compare()
        run_once(self.db,self.ws,self.fx)
        db=connect(self.db);alter_authority(db,revoke=True);db.close()
        self.assertEqual(review_patch(self.db,self.ws,self.fx,tid)["status"],"AUTHORITY_BLOCKED")
        self.assertFalse((self.ws/"repair_lab").exists())

    def test_blocked_ancestor_cannot_authorize_independent_repair_stage(self):
        """Independent holdout passing cannot revive a blocked root lineage."""
        db=connect(self.db)
        try:
            root=create_task(db, {"kind":"goal_intent","objective":"compare_records"},
                             due_at=9999999999)
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",(root,))
            db.commit()
        finally:
            db.close()
        tid,_=self.example_compare(parent=root)
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        db=connect(self.db)
        try:
            db.execute("UPDATE tasks SET state='BLOCKED' WHERE task_id=?",(root,))
            db.commit()
        finally:
            db.close()
        observed=review_patch(self.db,self.ws,self.fx,tid)
        self.assertNotEqual(observed["status"],"REPAIR_LAB_VERIFIED",observed)
        self.assertFalse((self.ws/"repair_lab"/(tid+".py")).exists())

    def test_tampered_immutable_proposal_refuses(self):
        tid,_=self.example_compare()
        run_once(self.db,self.ws,self.fx)
        p=self.ws/"artifacts"/(tid+".json")
        p.write_text(p.read_text()+"tamper")
        self.assertEqual(review_patch(self.db,self.ws,self.fx,tid)["status"],"NOT_ADMITTED")
        self.assertFalse((self.ws/"repair_lab").exists())

    def test_tampered_lab_patch_is_detected_after_former_success(self):
        tid,_=self.example_compare()
        run_once(self.db,self.ws,self.fx)
        review_patch(self.db,self.ws,self.fx,tid)
        staged=self.ws/"repair_lab"/(tid+".py")
        staged.write_text("def condition(x): return 1\n")
        r=inspect_conformance(self.db,self.ws,self.fx,enforce=True)
        self.assertEqual(r["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")
        self.assertEqual(staged.read_text(),"def condition(x): return 1\n")

    def test_host_opt_in_automatically_checks_holdout(self):
        tid,_=self.example_compare()
        tick=run_tick(self.db,self.ws,self.fx,auto_stage_goals=True)
        self.assertEqual(tick["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(tick["repair_lab_reviews"][0]["status"],"REPAIR_LAB_VERIFIED")
        self.assertEqual(self.row(tid)["state"],"REPAIR_LAB_VERIFIED")
        self.assertEqual(tick["conformance"]["mechanically_valid"],1)

    def test_host_default_does_not_consume_holdout(self):
        tid,_=self.example_compare()
        tick=run_tick(self.db,self.ws,self.fx)
        self.assertEqual(tick["repair_lab_reviews"],[])
        self.assertEqual(self.row(tid)["state"],"NEEDS_REVIEW")

    def test_planner_never_reads_sealed_holdout(self):
        tid,spec=self.example_compare()
        from cognition_agent_os import repair_search as proposer
        real=proposer.safe_fixture
        observed=[]
        def deny_hidden(root,name):
            observed.append(name)
            if name==spec["holdout"]:raise AssertionError("Leaked holdout to proposer")
            return real(root,name)
        with patch.object(proposer,"safe_fixture",side_effect=deny_hidden):
            result=run_once(self.db,self.ws,self.fx)
        self.assertEqual(result["status"],"NEEDS_REVIEW")
        self.assertEqual(set(observed),{spec["source"],spec["visible"]})

    def test_child_process_crash_after_lab_effect_recovers_immutable_file(self):
        tid,_=self.example_compare()
        run_once(self.db,self.ws,self.fx)
        code=("from pathlib import Path;from cognition_agent_os.repair_oracle import review_patch;"
              "review_patch(Path(%r),Path(%r),Path(%r),%r,fault_after_effect=True)" %
              (str(self.db),str(self.ws),str(self.fx),tid))
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        killed=subprocess.run([sys.executable,"-c",code],
                              env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(killed.returncode,82,killed.stderr)
        out=self.ws/"repair_lab"/(tid+".py")
        previous=out.read_bytes()
        self.assertEqual(self.row(tid)["state"],"NEEDS_REVIEW")
        resumed=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(resumed["status"],"REPAIR_LAB_VERIFIED")
        self.assertEqual(out.read_bytes(),previous)
        self.assertEqual(len(self.receipt(tid,"REPAIR_HOLDOUT_ACCEPTED")),1)

    def test_artifact_changed_after_final_holdout_audit_is_not_staged(self):
        tid,_=self.example_compare()
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        artifact=self.ws/"artifacts"/(tid+".json")
        original=artifact.read_bytes()
        from cognition_agent_os import repair_oracle as oracle
        real_audit=oracle.audit_patch
        calls=0
        def mutate_after_final_audit(*args,**kwargs):
            nonlocal calls
            result=real_audit(*args,**kwargs)
            calls+=1
            if calls==2:
                self.assertEqual(result["status"],"HOLDOUT_ACCEPTED")
                artifact.write_bytes(original+b"\n")
            return result
        with patch.object(oracle,"audit_patch",side_effect=mutate_after_final_audit):
            result=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"NOT_ADMITTED",result)
        self.assertEqual(result["reason"],"ARTIFACT_CHANGED_AFTER_AUDIT")
        self.assertFalse((self.ws/"repair_lab"/(tid+".py")).exists())
        self.assertEqual(self.row(tid)["state"],"NEEDS_REVIEW")

    def test_post_effect_holdout_substitution_refuses_false_success(self):
        tid,_=self.example_compare()
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        from cognition_agent_os import repair_oracle as oracle
        effect=oracle._stage_patch
        def stage_then_swap_hidden(workspace,task_id,candidate):
            actual=effect(workspace,task_id,candidate)
            # Reproduces a separate process replacing hidden gold AFTER the
            # initial approval, but BEFORE the SQLite acceptance receipt.
            self.fx.joinpath("hidden.json").write_bytes(b"[]")
            return actual
        with patch.object(oracle,"_stage_patch",side_effect=stage_then_swap_hidden):
            result=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"POST_EFFECT_REJECTED",result)
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")
        self.assertEqual(self.row(tid)["error_code"],"REPAIR_POST_EFFECT_EVIDENCE_CHANGED")
        self.assertTrue((self.ws/"repair_lab"/(tid+".py")).exists())
        self.assertEqual(self.receipt(tid,"REPAIR_HOLDOUT_ACCEPTED"),[])
        self.assertEqual(len(self.receipt(tid,"REPAIR_POST_EFFECT_REJECTED")),1)

    def test_post_effect_original_source_change_refuses_success(self):
        tid,_=self.example_compare()
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        from cognition_agent_os import repair_oracle as oracle
        effect=oracle._stage_patch
        def stage_then_swap_source(workspace,task_id,candidate):
            actual=effect(workspace,task_id,candidate)
            self.fx.joinpath("function.py").write_text(
                "def condition(x, threshold):\\n    return x == threshold\\n")
            return actual
        with patch.object(oracle,"_stage_patch",side_effect=stage_then_swap_source):
            result=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"POST_EFFECT_REJECTED",result)
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")
        self.assertEqual(self.receipt(tid,"REPAIR_HOLDOUT_ACCEPTED"),[])
        self.assertEqual(len(self.receipt(tid,"REPAIR_POST_EFFECT_REJECTED")),1)

    def test_post_effect_lab_bytes_tamper_refuses_acceptance(self):
        tid,_=self.example_compare()
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        from cognition_agent_os import repair_oracle as oracle
        effect=oracle._stage_patch
        def stage_then_tamper(workspace,task_id,candidate):
            digest=effect(workspace,task_id,candidate)
            (workspace/"repair_lab"/(task_id+".py")).write_bytes(b"not a patch")
            return digest
        with patch.object(oracle,"_stage_patch",side_effect=stage_then_tamper):
            result=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(result["status"],"POST_EFFECT_REJECTED",result)
        self.assertEqual(self.receipt(tid,"REPAIR_HOLDOUT_ACCEPTED"),[])
        record=self.receipt(tid,"REPAIR_POST_EFFECT_REJECTED")[0]
        self.assertFalse(record["staged_bytes_consistent"])
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")

    def test_lab_receipt_or_file_tamper_disables_further_repair_effects(self):
        from cognition_agent_os.conformance import capability_disabled,REPAIR_LAB_CAPABILITY
        tid,_=self.example_compare()
        run_once(self.db,self.ws,self.fx)
        self.assertEqual(review_patch(self.db,self.ws,self.fx,tid)["status"],
                         "REPAIR_LAB_VERIFIED")
        (self.ws/"repair_lab"/(tid+".py")).write_text("def condition(x): return -100\n")
        event=inspect_conformance(self.db,self.ws,self.fx,enforce=True)
        self.assertEqual(event["status"],"CONFORMANCE_VIOLATIONS")
        self.assertTrue(capability_disabled(self.db,REPAIR_LAB_CAPABILITY))
        second,_=self.example_compare()
        self.assertEqual(run_once(self.db,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(review_patch(self.db,self.ws,self.fx,second)["status"],
                         "CAPABILITY_DISABLED")
        self.assertFalse((self.ws/"repair_lab"/(second+".py")).exists())
        self.assertFalse(event["production_mutation_authorized"])

    def test_unavailable_holdout_has_finite_retry_budget(self):
        tid,_=self.example_compare()
        run_once(self.db,self.ws,self.fx)
        self.fx.joinpath("hidden.json").write_bytes(b"tampered")
        for i in (1,2):
            output=review_patch(self.db,self.ws,self.fx,tid)
            self.assertEqual(output["status"],"HOLDOUT_UNVERIFIABLE")
            self.assertEqual(output["attempts"],i)
        third=review_patch(self.db,self.ws,self.fx,tid)
        self.assertEqual(third["status"],"HOLDOUT_RETRY_EXHAUSTED")
        self.assertEqual(self.row(tid)["state"],"UNKNOWN")
        self.assertEqual(len(self.receipt(tid,"REPAIR_HOLDOUT_UNAVAILABLE")),3)
        self.assertEqual(review_due_repairs(self.db,self.ws,self.fx),[])
        self.assertFalse((self.ws/"repair_lab").exists())

    def test_cli_seed_worker_and_holdout_review(self):
        tid,spec=self.example_compare()
        # Intake through CLI must reuse ledger authority, not a private DB.
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        shared=[sys.executable,"-m","cognition_agent_os.cli",
                "--db",str(self.db),"--workspace",str(self.ws),"--fixtures",str(self.fx)]
        def call(args):
            return subprocess.run(shared+args,env=env,capture_output=True,text=True,timeout=15)
        # First task still exists; create a new task via the actual CLI.
        args=["seed-code-repair","--source",spec["source"],"--function",spec["function"],
              "--visible",spec["visible"],"--holdout",spec["holdout"],
              "--holdout-sha256",spec["holdout_sha256"]]
        seeded=call(args)
        self.assertEqual(seeded.returncode,0,seeded.stderr)
        cid=json.loads(seeded.stdout)["task_id"]
        worker=call(["worker-once"])
        self.assertEqual(worker.returncode,0,worker.stderr)
        chosen=json.loads(worker.stdout)["task_id"]
        self.assertEqual(chosen,tid)
        r=call(["worker-once"])
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)["task_id"],cid)
        preliminary=call(["repair-audit","--task-id",cid])
        self.assertEqual(preliminary.returncode,0,preliminary.stderr)
        self.assertFalse(json.loads(preliminary.stdout)["holdout_evaluated"])
        reviewed=call(["repair-review","--task-id",cid])
        self.assertEqual(reviewed.returncode,0,reviewed.stderr)
        self.assertEqual(json.loads(reviewed.stdout)["status"],"REPAIR_LAB_VERIFIED")


if __name__=="__main__":
    unittest.main()
