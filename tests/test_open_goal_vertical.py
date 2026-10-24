"""Whole-host, real ledger verification for open-language goal -> local method.

The local model transport is stubbed only in these unit tests; the planner,
registered child, immutable artifacts, SQL independent oracles and grants are
real Python production code. Real model quality requires separate held-out CI.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, initialize, create_task, alter_authority
from cognition_agent_os.open_goal import audit_open_goal
from cognition_agent_os.goal_audit import audit_goal
from cognition_agent_os.reconciliation_oracle import audit_stored_report


class OpenGoalVerticalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fx = self.root / "fx"
        self.fx.mkdir()
        self.ws = self.root / "ws"
        self.ws.mkdir()
        self.db = self.root / "authority.sqlite"
        with closing(connect(self.db)) as db:
            initialize(db)
        (self.fx / "settings.json").write_text('{"timeout": 7}\n', encoding="utf-8")
        (self.fx / "baseline.csv").write_text(
            "id,amount\nA,4\nB,5\n", encoding="utf-8")
        (self.fx / "actual.csv").write_text(
            "id,amount\nA,6\nB,5\n", encoding="utf-8")
        self.goal = ("Please ensure settings.json has owner equal to ops, "
                     "without changing the existing timeout.")
        self.received = []

    def enqueue(self, goal=None):
        with closing(connect(self.db)) as db:
            return create_task(db, {"kind": "open_goal",
                                    "goal": self.goal if goal is None else goal})

    def row(self, tid):
        with closing(connect(self.db)) as db:
            return dict(db.execute("SELECT * FROM tasks WHERE task_id=?",
                                   (tid,)).fetchone())

    def children(self, tid):
        with closing(connect(self.db)) as db:
            return [x[0] for x in db.execute(
                "SELECT task_id FROM tasks WHERE parent_task=?", (tid,)).fetchall()]

    def suggestion(self, *, intent=None, quote="owner equal to ops"):
        candidate = {
            "method": "ensure_structure",
            "input": "settings.json",
            "reference": "__none__", "observed": "__none__",
            "field": "owner", "equals": "ops",
            "rationale": "A bounded local non-destructive candidate",
            "rejected_alternative": "Compare records is not applicable",
            "uncertainty": "Meaning and business effect need independent review",
        }
        if intent is not None and intent.get("objective") == "compare_records":
            candidate.update({
                "method": "compare_records", "input": "__none__",
                "reference": "baseline.csv", "observed": "actual.csv",
                "field": "__none__", "equals": "__none__",
            })
        return candidate

    def transport(self, candidate, *, mutate=None):
        def responder(method, endpoint, payload, timeout):
            self.received.append((method, endpoint, payload))
            if method == "GET" and endpoint == "/api/tags":
                return {"models": [{"name": "installed:test"}]}
            if mutate:
                mutate()
            if "method" in payload.get("format", {}).get("properties", {}):
                result = {k: candidate[k] for k in
                          ("method", "rationale", "rejected_alternative", "uncertainty")}
            elif candidate["method"] == "ensure_structure":
                result = {k: candidate[k] for k in ("input", "field", "equals")}
            else:
                result = {k: candidate[k] for k in ("reference", "observed")}
            if "remote_write_allowed" in candidate:
                result["remote_write_allowed"] = candidate["remote_write_allowed"]
            return {"done": True, "response": json.dumps(result)}
        return responder

    def tick(self, candidate, *, mutate=None, max_jobs=2):
        with patch("cognition_agent_os.local_model._request",
                   side_effect=self.transport(candidate, mutate=mutate)):
            return run_tick(self.db, self.ws, self.fx, max_jobs=max_jobs,
                            planner_mode="ollama-local",
                            local_model="installed:test")

    def test_unknown_owner_goal_enters_real_host_and_finishes_typed_local_proposal(self):
        parent = self.enqueue()
        before = (self.fx / "settings.json").read_bytes()
        observed = self.tick(self.suggestion())
        self.assertEqual([x["status"] for x in observed["tasks"]],
                         ["DECOMPOSED", "NEEDS_REVIEW"], observed)
        child = observed["tasks"][0]["child_task_id"]
        self.assertEqual(self.row(child)["parent_task"], parent)
        self.assertEqual(self.row(parent)["state"], "DECOMPOSED")
        self.assertEqual(self.row(child)["state"], "NEEDS_REVIEW")
        self.assertEqual(audit_open_goal(self.db, self.fx, parent)["status"],
                         "METHOD_CANDIDATE_MECHANICALLY_GROUNDED")
        self.assertEqual(audit_goal(self.db, self.ws, self.fx, child)["status"],
                         "CANDIDATE_MECHANICALLY_VALID")
        self.assertEqual((self.fx / "settings.json").read_bytes(), before)
        self.assertFalse(observed["tasks"][0]["business_outcome_verified"])
        self.assertEqual(len(self.children(parent)), 1)

    def test_model_selects_different_registered_method_for_csv_goal(self):
        goal = "Please compare baseline.csv and actual.csv to identify record discrepancies."
        parent = self.enqueue(goal)
        method = {
            "kind": "goal_intent", "objective": "compare_records",
            "resources": [{"role": "reference", "path": "baseline.csv"},
                          {"role": "observed", "path": "actual.csv"}],
        }
        observed = self.tick(self.suggestion(intent=method,
                                             quote="identify record discrepancies"))
        self.assertEqual([x["status"] for x in observed["tasks"]],
                         ["DECOMPOSED", "NEEDS_REVIEW"], observed)
        child = observed["tasks"][0]["child_task_id"]
        self.assertEqual(self.row(child)["state"], "NEEDS_REVIEW")
        self.assertEqual(audit_stored_report(self.db, self.ws, self.fx, child)["status"],
                         "REPORT_MECHANICALLY_VERIFIED")
        self.assertEqual(audit_open_goal(self.db, self.fx, parent)["status"],
                         "METHOD_CANDIDATE_MECHANICALLY_GROUNDED")

    def test_invalid_model_tool_or_write_grant_cannot_mint_child(self):
        parent = self.enqueue()
        illegal = self.suggestion()
        illegal["remote_write_allowed"] = True
        out = self.tick(illegal, max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"], "UNKNOWN", out)
        self.assertFalse(self.children(parent))
        self.assertFalse((self.ws / "artifacts").exists())

    def test_nonexistent_model_selected_source_cannot_mint_child(self):
        parent = self.enqueue()
        invalid = self.suggestion()
        invalid["input"] = "newly-made-by-model.json"
        out = self.tick(invalid, max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"], "UNKNOWN", out)
        self.assertFalse(self.children(parent))

    def test_model_abstention_does_not_fabricate_work(self):
        parent = self.enqueue()
        out = self.tick(self.suggestion() | {"method": "abstain"},
                        max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"], "UNKNOWN", out)
        self.assertFalse(self.children(parent))

    def test_source_changes_while_model_decides_no_child_or_action(self):
        parent = self.enqueue()
        changed = False
        def mutate():
            nonlocal changed
            if not changed:
                (self.fx / "settings.json").write_text('{"timeout": 8}\n')
                changed = True
        out = self.tick(self.suggestion(), mutate=mutate, max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"], "UNKNOWN", out)
        self.assertEqual(self.row(parent)["error_code"], "OPEN_GOAL_SOURCE_CHANGED")
        self.assertFalse(self.children(parent))

    def test_grant_revoked_while_model_decides_cannot_spawn_child(self):
        parent = self.enqueue()
        changed = False
        def mutate():
            nonlocal changed
            if not changed:
                with closing(connect(self.db)) as db:
                    alter_authority(db, revoke=True)
                changed = True
        out = self.tick(self.suggestion(), mutate=mutate, max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"], "BLOCKED", out)
        self.assertFalse(self.children(parent))
        self.assertFalse((self.ws / "artifacts").exists())

    def test_child_source_drift_between_host_ticks_is_fenced(self):
        parent = self.enqueue()
        out = self.tick(self.suggestion(), max_jobs=1)
        self.assertEqual(out["tasks"][0]["status"], "DECOMPOSED", out)
        child = out["tasks"][0]["child_task_id"]
        (self.fx / "settings.json").write_text('{"timeout": 9}\n')
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("no new model needed for child")):
            result = run_tick(self.db, self.ws, self.fx, max_jobs=1,
                              planner_mode="ollama-local",
                              local_model="installed:test")
        self.assertEqual(result["tasks"][0]["status"], "UNKNOWN")
        self.assertEqual(self.row(child)["error_code"], "KNOWLEDGE_SOURCE_CHANGED")
        self.assertFalse((self.ws / "artifacts" / (child + ".json")).exists())
        self.assertEqual(audit_open_goal(self.db, self.fx, parent)["status"],
                         "SOURCE_CHANGED_SINCE_PROPOSAL")

    def test_purely_deterministic_host_mode_does_not_pretend_to_interpret_goal(self):
        parent = self.enqueue()
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("local inference not enabled")):
            result = run_tick(self.db, self.ws, self.fx, max_jobs=1)
        self.assertEqual(result["tasks"][0]["status"], "UNKNOWN")
        self.assertFalse(self.children(parent))


if __name__ == "__main__":
    unittest.main()
