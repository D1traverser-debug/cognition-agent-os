"""Cold chat/session recovery from the same real open_goal task ledger.

An original owner goal MUST remain discoverable without a second manual
continuity-registration step. All positive claims are independent local
readbacks; the command never creates a task or grants permission.
"""
from contextlib import closing
import subprocess
import sys
import json
import os
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.continuity import resume_goal
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority


class OpenGoalColdResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.db = self.home / "state.sqlite"
        self.workspace = self.home / "workspace"
        self.workspace.mkdir()
        self.fixtures = self.home / "fixtures"
        self.fixtures.mkdir()
        (self.fixtures / "settings.json").write_text(
            '{"timeout":7}\n', encoding="utf-8")
        (self.fixtures / "baseline.csv").write_text(
            "id,amount\nA,4\n", encoding="utf-8")
        (self.fixtures / "actual.csv").write_text(
            "id,amount\nA,6\n", encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)

    def seed(self, goal):
        with closing(connect(self.db)) as db:
            return create_task(db, {"kind": "open_goal", "goal": goal})

    def recover(self):
        return resume_goal(
            self.db, workspace=self.workspace, fixtures=self.fixtures)

    def test_original_goal_survives_without_second_continuity_registration(self):
        raw = "Please ensure a sandbox draft of settings.json has owner equal to ops."
        tid = self.seed(raw)
        first = self.recover()
        self.assertEqual(first["status"], "READY_TO_TICK", first)
        self.assertEqual(first["root_task_id"], tid)
        self.assertEqual(first["original_goal"], raw)
        self.assertEqual(first["next_task_id"], tid)
        self.assertFalse(first["business_outcome_verified"])
        self.assertEqual(self.recover(), first)

    def test_actual_host_effect_and_independent_verdict_survive_restart(self):
        raw = ("Please ensure a sandbox draft of settings.json has owner equal "
               "to ops, preserving the existing timeout.")
        tid = self.seed(raw)
        result = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=2,
            auto_stage_goals=True)
        self.assertEqual(result["goal_progress"]["goals"][0]
                         ["local_owner_result"]["status"],
                         "LOCAL_OWNER_RESULT_VERIFIED")
        resumed = self.recover()
        self.assertEqual(resumed["status"], "LOCAL_OWNER_RESULT_VERIFIED", resumed)
        self.assertEqual(resumed["root_task_id"], tid)
        self.assertEqual(resumed["original_goal"], raw)
        self.assertNotIn("next_task_id", resumed)
        self.assertFalse(resumed["business_outcome_verified"])
        self.assertEqual(self.recover(), resumed)

    def test_actual_source_change_cancels_derived_success(self):
        self.seed("Compare baseline.csv with actual.csv and report differences.")
        run_tick(self.db, self.workspace, self.fixtures, max_jobs=2)
        self.assertEqual(self.recover()["status"], "LOCAL_OWNER_RESULT_VERIFIED")
        (self.fixtures / "actual.csv").write_text(
            "id,amount\nA,100\n", encoding="utf-8")
        state = self.recover()
        self.assertNotEqual(state["status"], "LOCAL_OWNER_RESULT_VERIFIED", state)
        self.assertNotIn("next_task_id", state)
        self.assertFalse(state["local_owner_outcome_verified"])

    def test_revocation_blocks_recovery_without_losing_original_goal(self):
        self.seed("Compare baseline.csv with actual.csv and report differences.")
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        found = self.recover()
        self.assertEqual(found["status"], "AUTHORITY_REVOKED", found)
        # Revoking a write GRANT cannot erase the read-only original goal.
        self.assertEqual(found["original_goal"],
                         "Compare baseline.csv with actual.csv and report differences.")
        self.assertRegex(found["original_contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(found["authority_current"])
        self.assertNotIn("next_task_id", found)
        self.assertFalse(found["business_outcome_verified"])

    def test_two_open_owner_roots_are_ambiguous_not_latest_wins(self):
        self.seed("Compare baseline.csv with actual.csv and report differences.")
        self.seed("Please ensure a sandbox draft of settings.json has owner equal to ops.")
        state = self.recover()
        self.assertEqual(state["status"], "AMBIGUOUS_OPEN_OWNER_GOALS", state)
        self.assertNotIn("next_task_id", state)

    def test_cli_goal_resume_is_a_real_cross_process_entry(self):
        goal = "Compare baseline.csv with actual.csv and report differences."
        root = self.seed(goal)
        process = subprocess.run(
            [sys.executable, "-m", "cognition_agent_os.cli",
             "--db", str(self.db),
             "--workspace", str(self.workspace),
             "--fixtures", str(self.fixtures), "goal-resume"],
            text=True, capture_output=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        state = json.loads(process.stdout)
        self.assertEqual(state["root_task_id"], root)
        self.assertEqual(state["original_goal"], goal)

    def test_chinese_multi_clause_goal_survives_revocation_across_process(self):
        """The actual CLI must recover complete Chinese clauses, no hidden execution."""
        goal = (
            "先把GPT会话、技能和工具链做到可信；"
            "不要先联调视频或小说子系统；"
            "遇到新领域要独立研究、质疑并核验真实效果；"
            "跨会话不能丢失原始验收条件。"
        )
        root = self.seed(goal)
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        process = subprocess.run(
            [sys.executable, "-m", "cognition_agent_os.cli",
             "--db", str(self.db), "--workspace", str(self.workspace),
             "--fixtures", str(self.fixtures), "goal-resume"],
            text=True, capture_output=True, check=False,
            # Force a legacy Windows-like output encoding on every CI platform.
            # The JSON transport must remain ASCII-safe while decoded Chinese
            # original_goal still matches the input exactly.
            env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(process.returncode, 4, process.stderr)
        state = json.loads(process.stdout)
        self.assertEqual(state["status"], "AUTHORITY_REVOKED")
        self.assertEqual(state["original_goal"], goal)
        self.assertEqual(state["root_task_id"], root)
        self.assertFalse(state["authority_current"])
        self.assertNotIn("next_task_id", state)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT write_allowed FROM authority WHERE singleton=1").fetchone()[0], 0)

    def test_no_open_goal_does_not_invent_implicit_owner_authority(self):
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "fixture", "old": "a", "new": "b"})
        self.assertEqual(self.recover()["status"], "NO_DURABLE_GOAL")

    def test_large_unrelated_queue_cannot_hide_actual_owner_goal(self):
        # Cold recovery must scan *owner roots*, not the first 257 arbitrary
        # fixture tasks. Otherwise a busy Host loses the owner's identity.
        with closing(connect(self.db)) as db:
            for number in range(300):
                create_task(db, {
                    "kind":"fixture","old":f"old-{number}",
                    "new":f"new-{number}"}, commit=False)
            db.commit()
        original = "Compare baseline.csv with actual.csv and report differences."
        root = self.seed(original)
        recovered = self.recover()
        self.assertEqual(recovered["root_task_id"], root, recovered)
        self.assertEqual(recovered["original_goal"], original)


    def test_parallel_owner_obligations_are_recoverable_from_cold_ledger(self):
        """One durable owner root must resume BOTH admitted obligations."""
        (self.fixtures / "cause.md").write_text(
            "The UART reset held the timeout counter for several cycles.\n")
        goal = ("Investigate the UART timeout using local engineering evidence "
                "and ensure a sandbox draft of settings.json has owner equal to ops.")
        root = self.seed(goal)
        started = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1,
            planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(started["tasks"][0]["status"], "DECOMPOSED", started)
        with closing(connect(self.db)) as db:
            children = [dict(x) for x in db.execute(
                "SELECT task_id,source_spec FROM tasks WHERE parent_task=?", (root,))]
        self.assertEqual(len(children), 2)
        resumed = self.recover()
        self.assertEqual(resumed["status"], "READY_TO_TICK", resumed)
        self.assertEqual(resumed["original_goal"], goal)
        self.assertEqual(resumed["root_task_id"], root)
        self.assertEqual(set(resumed["child_task_ids"]),
                         {x["task_id"] for x in children})
        self.assertEqual(set(resumed["runnable_task_ids"]),
                         {x["task_id"] for x in children})
        self.assertEqual(len(resumed["original_obligation_progress"]), 2)
        self.assertFalse(resumed["local_owner_outcome_verified"])
        self.assertFalse(resumed["business_outcome_verified"])
        self.assertEqual(self.recover(), resumed)

    def test_ordered_owner_cold_resume_never_dispatches_gated_successor(self):
        """Research predecessor is runnable; its original follower stays gated."""
        (self.fixtures / "cause.md").write_text(
            "The UART reset held the timeout counter for several cycles.\n")
        goal = ("Investigate the UART timeout using local engineering evidence "
                "and then ensure a sandbox draft of settings.json has owner equal to ops.")
        root = self.seed(goal)
        started = run_tick(
            self.db, self.workspace, self.fixtures, max_jobs=1,
            planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(started["tasks"][0]["status"], "DECOMPOSED", started)
        with closing(connect(self.db)) as db:
            rows = [dict(x) for x in db.execute(
                "SELECT task_id,source_spec FROM tasks WHERE parent_task=?", (root,))]
        ids = {json.loads(x["source_spec"])["kind"]:x["task_id"] for x in rows}
        resumed = self.recover()
        self.assertEqual(resumed["status"], "READY_TO_TICK", resumed)
        self.assertEqual(resumed["next_task_id"], ids["investigate_goal"])
        self.assertEqual(resumed["runnable_task_ids"], [ids["investigate_goal"]])
        self.assertNotIn(ids["goal_case"], resumed["runnable_task_ids"])
        self.assertEqual(resumed["sequence_rule"],
                         "AFTER_INDEPENDENT_RESEARCH_EVIDENCE")

    def test_compound_cold_resume_rejects_changed_source_and_revocation(self):
        """Do not turn a stale candidate receipt into an executable pointer."""
        (self.fixtures / "cause.md").write_text("Recorded local UART cause.\n")
        goal = ("Investigate the UART timeout using local engineering evidence "
                "and then ensure a sandbox draft of settings.json has owner equal to ops.")
        self.seed(goal)
        started = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1,
                           planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(started["tasks"][0]["status"], "DECOMPOSED", started)
        (self.fixtures / "cause.md").write_text("Source changed after admission.\n")
        stale = self.recover()
        self.assertEqual(stale["status"], "ORIGINAL_GOAL_LINEAGE_UNVERIFIABLE", stale)
        self.assertNotIn("next_task_id", stale)
        self.assertNotIn("runnable_task_ids", stale)
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        revoked = self.recover()
        self.assertEqual(revoked["status"], "AUTHORITY_REVOKED", revoked)
        self.assertEqual(revoked["original_goal"], goal)
        self.assertNotIn("next_task_id", revoked)


    def test_ordered_cold_resume_release_and_forged_evidence_does_not_promote(self):
        """Recover actual verified successor only while predecessor proof survives."""
        from unittest.mock import patch
        from cognition_agent_os.dependency_gate import advance_pending_local_dependencies
        (self.fixtures / "cause.md").write_text(
            "The UART reset held the timeout counter for several cycles.\n")
        goal = ("Investigate the UART timeout using local engineering evidence "
                "and then ensure a sandbox draft of settings.json has owner equal to ops.")
        root = self.seed(goal)
        start = run_tick(self.db, self.workspace, self.fixtures, max_jobs=1,
                         planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(start["tasks"][0]["status"], "DECOMPOSED", start)
        with closing(connect(self.db)) as db:
            rows = [dict(x) for x in db.execute(
                "SELECT task_id,source_spec FROM tasks WHERE parent_task=?", (root,))]
        ids = {json.loads(x["source_spec"])["kind"]: x["task_id"] for x in rows}

        def model(method, endpoint, payload, timeout):
            if method == "GET":
                return {"models": [{"name": "installed:test"}]}
            properties = payload["format"]["properties"]
            if "sources" in properties:
                answer = {"sources": ["cause.md"]}
            elif "findings" in properties:
                answer = {"findings": [{
                    "source": "cause.md",
                    "quote": "The UART reset held the timeout counter for several cycles.",
                    "interpretation": "Reset is a potential counter pause cause.",
                }], "uncertainty": "Local fixture evidence is not a hardware outcome."}
            else:
                raise AssertionError("Unexpected model output schema")
            return {"done": True, "response": json.dumps(answer)}

        with patch("cognition_agent_os.local_model._request", side_effect=model):
            research = run_tick(
                self.db, self.workspace, self.fixtures, max_jobs=1,
                planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(research["tasks"][0]["task_id"], ids["investigate_goal"])
        self.assertEqual(research["tasks"][0]["status"], "NEEDS_REVIEW")
        before_release = self.recover()
        self.assertEqual(before_release["status"],
                         "AWAITING_DEPENDENCY_EVIDENCE", before_release)
        self.assertNotIn("next_task_id", before_release)

        release = advance_pending_local_dependencies(
            self.db, self.workspace, self.fixtures)
        self.assertTrue(any(x["status"] == "DEPENDENCY_RELEASED_LOCAL_ONLY"
                            for x in release), release)
        legitimate = self.recover()
        self.assertEqual(legitimate["status"], "READY_TO_TICK", legitimate)
        self.assertEqual(legitimate["next_task_id"], ids["goal_case"])
        self.assertEqual(legitimate["runnable_task_ids"], [ids["goal_case"]])

        # A stored release bit cannot resurrect an invalid research receipt.
        research_artifact = (self.workspace / "artifacts" /
                             (ids["investigate_goal"] + ".json"))
        research_artifact.write_bytes(research_artifact.read_bytes() + b" tampered")
        compromised = self.recover()
        self.assertEqual(compromised["status"],
                         "AWAITING_DEPENDENCY_EVIDENCE", compromised)
        self.assertNotIn("next_task_id", compromised)
        self.assertEqual(compromised["waiting_dependency_tasks"][0]["reason"],
                         "PREDECESSOR_EVIDENCE_CHANGED")
        self.assertFalse(compromised["local_owner_outcome_verified"])

    def test_missing_db_is_never_implicitly_initialized(self):
        missing = self.home / "missing.sqlite"
        self.assertEqual(
            resume_goal(missing, workspace=self.workspace, fixtures=self.fixtures)
            ["status"], "LEDGER_NOT_INITIALIZED")
        self.assertFalse(missing.exists())
