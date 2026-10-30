"""P10 self-observation: actual evidence and system-wide lineage enforcement.

All operations use small temporary local SQLite databases and sources.
No network, paid model call or production resource is touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.runner import run_once
from cognition_agent_os.host import run_tick
from cognition_agent_os.sandbox_effect import stage_one
from cognition_agent_os.conformance import inspect_conformance

ROOT=Path(__file__).resolve().parents[1]


class ConformanceTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.ws=self.root/"workspace";self.ws.mkdir()
        self.dbpath=self.root/"state.sqlite"
        db=connect(self.dbpath);initialize(db);db.close()

    def seed(self,name="config.json",desired=None):
        spec={"kind":"goal_case","goal_type":"json_keys","input":name,
              "desired":desired or {"owner":"ops"}}
        db=connect(self.dbpath)
        try:return create_task(db,spec)
        finally: db.close()

    def seed_intent(self):
        intent={"kind":"goal_intent","objective":"ensure_structure",
                "resources":[{"role":"input","path":"config.json"}],
                "requirements":[{"field":"owner","equals":"ops"}]}
        db=connect(self.dbpath)
        try:return create_task(db,intent)
        finally:db.close()

    def task(self,tid):
        db=connect(self.dbpath)
        try:return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        finally:db.close()

    def events(self,tid,kind):
        db=connect(self.dbpath)
        try:return [dict(r) for r in db.execute(
            "SELECT * FROM events WHERE task_id=? AND kind=?",(tid,kind))]
        finally:db.close()

    def check(self,*,enforce=False,max_cases=64):
        return inspect_conformance(self.dbpath,self.ws,self.fx,
                                   enforce=enforce,max_cases=max_cases)

    def create_staged(self):
        self.fx.joinpath("config.json").write_text('{"existing":"keep"}')
        tid=self.seed()
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(stage_one(self.dbpath,self.ws,self.fx,tid)["status"],"SANDBOX_VERIFIED")
        return tid

    def test_empty_initialized_runtime_cannot_claim_operational_success(self):
        r=self.check()
        self.assertEqual(r["status"],"NO_RUNTIME_EVIDENCE")
        self.assertEqual(r["eligible"],0)
        self.assertEqual(r["release_gate"],
                         "BLOCKED_AWAITING_INDEPENDENT_OUTCOME_AND_HOST_PROOF")
        self.assertEqual(r["unattended_windows_host_evidence"],"NOT_OBSERVED")
        self.assertFalse(r["production_mutation_authorized"])

    def test_read_only_probe_never_initializes_absent_db(self):
        missing=self.root/"missing.sqlite"
        r=inspect_conformance(missing,self.ws,self.fx)
        self.assertEqual(r["status"],"NOT_CONFIGURED")
        self.assertFalse(missing.exists())

    def test_valid_proposal_rechecked_from_actual_artifact(self):
        self.fx.joinpath("config.json").write_text("{}")
        tid=self.seed()
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        r=self.check()
        self.assertEqual(r["status"],"MECHANICAL_EVIDENCE_OBSERVED")
        self.assertEqual(r["checked"],1)
        self.assertEqual(r["findings"][0]["disposition"],"PASS")
        self.assertEqual(self.task(tid)["state"],"NEEDS_REVIEW")

    def test_bona_fide_sandbox_readback_is_not_business_success(self):
        tid=self.create_staged()
        r=self.check()
        self.assertEqual(r["mechanically_valid"],1)
        self.assertEqual(r["status"],"MECHANICAL_EVIDENCE_OBSERVED")
        self.assertFalse(r["production_mutation_authorized"])
        self.assertEqual(self.task(tid)["state"],"SANDBOX_VERIFIED")

    def test_enforcement_does_not_quarantine_source_repaired_after_preview(self):
        # The DB row and PRAGMA data_version stay unchanged while a separate
        # writer repairs the actual file after the first evidence scan.
        from cognition_agent_os import conformance
        task_id = self.create_staged()
        staged = self.ws / "sandbox" / (task_id + ".candidate")
        original = staged.read_bytes()
        staged.write_bytes(b"tampered")
        real_prepare = conformance._prepare_conformance_readback

        def repair_after_preview(*args, **kwargs):
            candidate = real_prepare(*args, **kwargs)
            self.assertEqual(candidate[5][task_id]["disposition"],
                             "CONFIRMED_INCONSISTENCY")
            staged.write_bytes(original)
            return candidate

        with patch.object(conformance, "_prepare_conformance_readback",
                          side_effect=repair_after_preview):
            result = self.check(enforce=True)
        self.assertEqual(result["quarantined"], [], result)
        self.assertEqual(self.task(task_id)["state"], "SANDBOX_VERIFIED")
        self.assertEqual(self.events(task_id, "CONFORMANCE_VIOLATION"), [])

    def test_enforcement_detects_source_corruption_after_clean_preview(self):
        from cognition_agent_os import conformance
        task_id = self.create_staged()
        staged = self.ws / "sandbox" / (task_id + ".candidate")
        real_prepare = conformance._prepare_conformance_readback

        def corrupt_after_preview(*args, **kwargs):
            candidate = real_prepare(*args, **kwargs)
            self.assertEqual(candidate[5][task_id]["disposition"], "PASS")
            staged.write_bytes(b"tampered")
            return candidate

        with patch.object(conformance, "_prepare_conformance_readback",
                          side_effect=corrupt_after_preview):
            result = self.check(enforce=True)
        # Even if no destructive action is appropriate during the race,
        # the stale clean result must not be asserted as fresh conformance.
        self.assertNotEqual(result["status"], "MECHANICAL_EVIDENCE_OBSERVED")
        self.assertEqual(result["mechanically_valid"], 0)
        self.assertEqual(self.task(task_id)["state"], "SANDBOX_VERIFIED")

    def test_forged_staged_success_without_effect_quarantined(self):
        self.fx.joinpath("config.json").write_text("{}")
        tid=self.seed()
        db=connect(self.dbpath)
        db.execute("UPDATE tasks SET state='SANDBOX_VERIFIED' WHERE task_id=?",(tid,))
        db.commit();db.close()
        r=self.check(enforce=True)
        self.assertEqual(r["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(r["quarantined"][0]["task_id"],tid)
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        self.assertEqual(len(self.events(tid,"CONFORMANCE_VIOLATION")),1)
        self.assertEqual(self.check(enforce=True)["quarantined"],[])

    def test_corrupted_staged_file_triggers_default_host_governance(self):
        tid=self.create_staged()
        path=self.ws/"sandbox"/(tid+".candidate")
        path.write_text("UNTRUSTED")
        tick=run_tick(self.dbpath,self.ws,self.fx)
        r=tick["conformance"]
        self.assertEqual(r["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(len(r["quarantined"]),1)
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        self.assertEqual(path.read_text(),"UNTRUSTED")

    def test_falsified_effect_receipt_revokes_false_success(self):
        tid=self.create_staged()
        db=connect(self.dbpath)
        db.execute("UPDATE events SET details=? WHERE task_id=? AND kind=?",
                   ('{"effect_sha256":"0","scope":"isolated_workspace_only"}',
                    tid,"SANDBOX_EFFECT_VERIFIED"))
        db.commit();db.close()
        r=self.check(enforce=True)
        self.assertEqual(r["findings"][0]["proof"],"FALSE_EFFECT_RECEIPT")
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")

    def test_confirmed_receipt_forgery_trips_system_wide_capability_guard(self):
        from cognition_agent_os.conformance import capability_disabled
        from cognition_agent_os.sandbox_effect import advance_due_reviews
        first=self.create_staged()
        db=connect(self.dbpath)
        db.execute("UPDATE events SET details=? WHERE task_id=? AND kind=?",
                   ('{"effect_sha256":"forged","scope":"isolated_workspace_only"}',
                    first,"SANDBOX_EFFECT_VERIFIED"))
        db.commit();db.close()
        self.assertFalse(capability_disabled(self.dbpath))
        r=self.check(enforce=True)
        self.assertEqual(r["status"],"CONFORMANCE_VIOLATIONS")
        self.assertTrue(r["capability_circuit_open"])
        self.assertTrue(capability_disabled(self.dbpath))
        self.assertEqual(self.task(first)["state"],"UNKNOWN")
        self.assertEqual(len(self.events(first,"CONFORMANCE_CAPABILITY_DISABLED")),1)

        self.fx.joinpath("other.json").write_text("{}")
        second=self.seed(name="other.json")
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(stage_one(self.dbpath,self.ws,self.fx,second)["status"],
                         "CAPABILITY_DISABLED")
        self.assertEqual(self.task(second)["state"],"NEEDS_REVIEW")
        self.assertFalse((self.ws/"sandbox"/(second+".candidate")).exists())
        self.assertEqual(advance_due_reviews(self.dbpath,self.ws,self.fx),[])
        self.assertEqual(self.check(enforce=True)["quarantined"],[])
        self.assertTrue(capability_disabled(self.dbpath))

    def test_single_insufficient_legacy_proof_does_not_trip_global_circuit(self):
        from cognition_agent_os.conformance import capability_disabled
        db=connect(self.dbpath)
        tid=create_task(db,{"kind":"fixture","old":"a","new":"b"})
        db.execute("UPDATE tasks SET state='VERIFIED',decision='NO_CHANGE' WHERE task_id=?",
                   (tid,))
        db.commit();db.close()
        result=self.check(enforce=True)
        self.assertEqual(result["status"],"EVIDENCE_INSUFFICIENT")
        self.assertFalse(result["capability_circuit_open"])
        self.assertFalse(capability_disabled(self.dbpath))

    def test_corrupted_pending_report_is_quarantined_before_stage(self):
        self.fx.joinpath("config.json").write_text("{}")
        tid=self.seed()
        run_once(self.dbpath,self.ws,self.fx)
        artifact=self.ws/"artifacts"/(tid+".json")
        artifact.write_bytes(artifact.read_bytes()+b"corrupt")
        r=self.check(enforce=True)
        self.assertEqual(r["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        self.assertFalse((self.ws/"sandbox").exists())

    def test_corrupted_intent_parent_blocks_entire_descendant_chain(self):
        self.fx.joinpath("config.json").write_text("{}")
        parent=self.seed_intent()
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"DECOMPOSED")
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        db=connect(self.dbpath)
        child=db.execute("SELECT task_id FROM tasks WHERE parent_task=?",(parent,)).fetchone()[0]
        db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                   ('{"kind":"fixture","old":"x","new":"y"}',child))
        db.commit();db.close()
        r=self.check(enforce=True)
        self.assertTrue(any(f["proof"]=="CHILD_TASK_IDENTITY_MISMATCH"
                            for f in r["findings"]))
        self.assertEqual(self.task(parent)["state"],"UNKNOWN")
        self.assertEqual(self.task(child)["state"],"UNKNOWN")
        self.assertEqual(self.task(child)["error_code"],"UPSTREAM_CONFORMANCE_VIOLATION")
        self.assertEqual(len(self.events(child,"CONFORMANCE_DEPENDENCY_BLOCKED")),1)

    def test_valid_parent_intent_graph_passes_without_approval(self):
        self.fx.joinpath("config.json").write_text("{}")
        parent=self.seed_intent()
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"DECOMPOSED")
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"NEEDS_REVIEW")
        r=self.check()
        self.assertEqual(r["mechanically_valid"],2)
        self.assertEqual(r["status"],"MECHANICAL_EVIDENCE_OBSERVED")
        self.assertEqual(self.task(parent)["state"],"DECOMPOSED")

    def test_goal_noop_can_be_reobserved(self):
        self.fx.joinpath("config.json").write_text('{"owner":"ops"}')
        tid=self.seed()
        self.assertEqual(run_once(self.dbpath,self.ws,self.fx)["status"],"VERIFIED")
        self.assertEqual(self.check()["mechanically_valid"],1)
        self.fx.joinpath("config.json").write_text('{"owner":"changed"}')
        r=self.check(enforce=True)
        self.assertEqual(r["status"],"CONFORMANCE_VIOLATIONS")
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")

    def test_inconclusive_historical_success_does_not_mean_corruption(self):
        db=connect(self.dbpath)
        tid=create_task(db,{"kind":"fixture","old":"a","new":"b"})
        db.execute("UPDATE tasks SET state='VERIFIED',decision='NO_CHANGE' WHERE task_id=?",
                   (tid,))
        db.commit();db.close()
        r=self.check(enforce=True)
        self.assertEqual(r["status"],"EVIDENCE_INSUFFICIENT")
        self.assertEqual(r["findings"][0]["disposition"],"INSUFFICIENT_EVIDENCE")
        self.assertEqual(self.task(tid)["state"],"VERIFIED")
        self.assertEqual(self.events(tid,"CONFORMANCE_VIOLATION"),[])

    def test_full_scan_bounded_progress_finds_late_corruption(self):
        self.fx.joinpath("config.json").write_text('{"owner":"ops"}')
        ids=[]
        for i in range(31):
            tid=self.seed()
            ids.append(tid)
        db=connect(self.dbpath)
        db.execute("""UPDATE tasks SET state='VERIFIED',
                    decision='GOAL_ALREADY_SATISFIED' WHERE state='PENDING'""")
        suspect=max(ids)
        db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                   (json.dumps({"kind":"goal_case","goal_type":"json_keys",
                                "input":"missing.json","desired":{"owner":"ops"}}),suspect))
        db.commit();db.close()
        seen=set()
        for _ in range(8):
            audit=self.check(enforce=True,max_cases=5)
            seen.update(item["task_id"] for item in audit["findings"])
            self.assertFalse(audit["production_mutation_authorized"])
        self.assertEqual(len(seen),31)
        # Missing source is INSUFFICIENT_EVIDENCE, not a forged claim;
        # scan must still cycle across all tasks even with small batch.
        self.assertEqual(self.task(suspect)["state"],"VERIFIED")
        self.assertEqual(self.check(enforce=True,max_cases=5)["checked"],5)

    def test_cli_read_only_then_enforce_uses_original_authority(self):
        tid=self.create_staged()
        (self.ws/"sandbox"/(tid+".candidate")).write_bytes(b"tamper")
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        command=[sys.executable,"-m","cognition_agent_os.cli","--db",str(self.dbpath),
                 "--workspace",str(self.ws),"--fixtures",str(self.fx),"conformance-audit"]
        read=subprocess.run(command,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(read.returncode,4,read.stderr)
        self.assertEqual(self.task(tid)["state"],"SANDBOX_VERIFIED")
        enforce=subprocess.run(command+["--enforce"],env=env,
                               capture_output=True,text=True,timeout=10)
        self.assertEqual(enforce.returncode,4,enforce.stderr)
        self.assertEqual(self.task(tid)["state"],"UNKNOWN")
        self.assertEqual(len(self.events(tid,"CONFORMANCE_VIOLATION")),1)


if __name__=="__main__":
    unittest.main()
