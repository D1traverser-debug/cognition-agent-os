"""End-to-end owner-goal continuity and unsupported-method fallback tests.

These test an unrelated procurement/operations domain; the same existing
Host, current-grant ledger, original evidence Worker and readback are used.
"""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize
from cognition_agent_os.open_goal import audit_open_goal
from cognition_agent_os.investigation import audit_investigation


class IndependentGoalContinuationTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.db = self.root / "authority.sqlite"
        with closing(connect(self.db)) as conn:
            initialize(conn)
        (self.evidence / "issue_tracker.md").write_text(
            "The issue tracker supports a read-only API for searching defect "
            "reports and keeps provenance with every item.\n", encoding="utf-8")
        (self.evidence / "alternative.md").write_text(
            "The team inbox accepts forwarded defect reports but does not "
            "preserve a structured record of origin.\n", encoding="utf-8")

    def seed(self, goal):
        with closing(connect(self.db)) as conn:
            return create_task(conn, {"kind": "open_goal", "goal": goal})

    def children(self, root):
        with closing(connect(self.db)) as conn:
            return [dict(x) for x in conn.execute(
                "SELECT * FROM tasks WHERE parent_task=?", (root,))]

    @staticmethod
    def local_model(method, endpoint, payload, timeout):
        if method == "GET":
            return {"models": [{"name": "installed:test"}]}
        props = payload["format"]["properties"]
        if "method" in props:
            return {"done": True, "response": json.dumps({"method": "abstain"})}
        if "sources" in props:
            return {"done": True, "response": json.dumps(
                {"sources": ["issue_tracker.md", "alternative.md"]})}
        if "findings" in props:
            return {"done": True, "response": json.dumps({
                "findings": [
                    {"source": "issue_tracker.md",
                     "quote": "supports a read-only API for searching defect reports",
                     "interpretation": "May satisfy evidence acquisition."},
                    {"source": "alternative.md",
                     "quote": "does not preserve a structured record of origin",
                     "interpretation": "Weaker provenance than an issue tracker."}
                ],
                "uncertainty": "No external provider API has been tried or authorized."
            })}
        raise AssertionError("Unregistered model method")

    def test_unsupported_goal_autonomously_starts_readonly_tool_research(self):
        goal = "Find a viable way to manage supplier defects with reliable provenance."
        root = self.seed(goal)
        before = {p.name: p.read_bytes() for p in self.evidence.iterdir()}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.local_model):
            run = run_tick(self.db, self.workspace, self.evidence, max_jobs=2,
                           planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual([x["status"] for x in run["tasks"]],
                         ["DECOMPOSED", "NEEDS_REVIEW"], run)
        child = self.children(root)[0]
        self.assertEqual(json.loads(child["source_spec"]), {
            "kind": "investigate_goal", "question": goal,
            "scope": "LOCAL_EVIDENCE_ONLY"
        })
        self.assertEqual(audit_open_goal(self.db, self.evidence, root)["status"],
                         "METHOD_CANDIDATE_MECHANICALLY_GROUNDED")
        self.assertEqual(audit_investigation(
            self.db, self.workspace, self.evidence, child["task_id"])["status"],
            "SOURCE_GROUNDED_UNREVIEWED")
        result = json.loads(
            (self.workspace / "artifacts" / (child["task_id"] + ".json")).read_text())
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["authorizes_mutation"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.evidence.iterdir()})

    def test_owner_forbids_research_no_gap_child(self):
        root = self.seed(
            "Do not investigate vendor selection; produce no research report.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.local_model):
            run = run_tick(self.db, self.workspace, self.evidence, max_jobs=1,
                           planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(run["tasks"][0]["status"], "UNKNOWN")
        self.assertFalse(self.children(root))

    def test_external_operation_not_disguised_as_gap_research(self):
        root = self.seed(
            "Upload private supplier invoices and credentials to a production endpoint.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.local_model):
            run = run_tick(self.db, self.workspace, self.evidence, max_jobs=1,
                           planner_mode="ollama-local", local_model="installed:test")
        self.assertEqual(run["tasks"][0]["status"], "UNKNOWN")
        self.assertFalse(self.children(root))

    def test_no_installed_model_abstains_without_fabricating_evidence(self):
        root = self.seed("Find an approach to reliable supplier defect tracking.")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("No local model is allowed")):
            run = run_tick(self.db, self.workspace, self.evidence, max_jobs=1)
        self.assertEqual(run["tasks"][0]["status"], "UNKNOWN")
        self.assertFalse(self.children(root))

if __name__ == "__main__":
    unittest.main()
