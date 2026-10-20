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

    def seed(self,source,visible,holdout,*,function="condition"):
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
        tid=create_task(db,spec)
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

    def example_compare(self,*,reject=False):
        source="def condition(x, threshold):\n    return x > threshold\n"
        visible=[
            {"args":[5,5],"expected":True},
            {"args":[6,5],"expected":True},
            {"args":[4,5],"expected":False}]
        holdout=[{"args":[7,7],"expected":True if not reject else False},
                 {"args":[0,8],"expected":False},
                 {"args":[12,8],"expected":True}]
        return self.seed(source,visible,holdout)

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
        self.assertEqual(review_patch(self.db,self.ws,self.fx,tid)["status"],"NOT_ADMITTED")
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
        visible=[{"args":[1,2],"expected":False},
                 {"args":[3,2],"expected":True},
                 {"args":[4,2],"expected":True}]
        hidden=[{"args":[2,2],"expected":True},
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
