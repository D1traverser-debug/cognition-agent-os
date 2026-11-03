"""Real SQLite lease expiry fences every sibling direct-task transition.

These are source/admission state checks, not proof of arbitrary external effects.
The model-selected open-goal proposal is mocked solely to stop before any
model transport; its actual SQLite task, grant and transaction are real.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import (
    claim_one, connect, create_task, initialize, live_claim_owner,
)
from cognition_agent_os.intent_runtime import run_intent
from cognition_agent_os.knowledge_routing import run_knowledge_intent
from cognition_agent_os.research_gap import classify_research_gap, enqueue_research_gap
from cognition_agent_os.open_goal import run_open_goal


class CrossEntrypointLeaseFenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.fx = self.root / "fx"
        self.fx.mkdir()
        (self.fx / "settings.json").write_text('{"keep":42}', encoding="utf-8")
        self.db_path = self.root / "ledger.sqlite"
        with closing(connect(self.db_path)) as db:
            initialize(db)

    def claim(self, spec):
        db = connect(self.db_path)
        tid = create_task(db, spec)
        claimed = claim_one(db)
        self.assertEqual(claimed["task_id"], tid)
        return db, claimed

    def expire(self, db, task, expiry=0):
        db.execute("UPDATE tasks SET lease_until=? WHERE task_id=?",
                   (expiry, task["task_id"]))
        db.commit()

    def assert_no_child_or_transition(self, db, task):
        row = db.execute("SELECT state, claim_token FROM tasks WHERE task_id=?",
                         (task["task_id"],)).fetchone()
        self.assertEqual(row["state"], "RUNNING")
        self.assertEqual(row["claim_token"], task["claim_token"])
        self.assertEqual(db.execute(
            "SELECT count(*) FROM tasks WHERE parent_task=?",
            (task["task_id"],)).fetchone()[0], 0)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM events WHERE task_id=? AND kind NOT IN "
            "('ENQUEUED','CLAIMED')", (task["task_id"],)).fetchone()[0], 0)

    def intent(self):
        return {"kind": "goal_intent", "objective": "ensure_structure",
                "resources": [{"role": "input", "path": "settings.json"}],
                "requirements": [{"field": "owner", "equals": "ops"}]}

    def knowledge(self, *, matched=True, research=False):
        claim = {"goal_key": "target" if matched else "unrelated",
                 "route": "build", "status": "active", "source_ref": "test:provenance"}
        doc = {"schema_version": 1, "source_id": "independent-source",
               "claims": [claim]}
        raw = json.dumps(doc, sort_keys=True).encode()
        (self.fx / "source.json").write_bytes(raw)
        spec = {"kind": "knowledge_intent", "goal_key": "target",
                "knowledge": {"path": "source.json",
                              "source_id": "independent-source",
                              "sha256": hashlib.sha256(raw).hexdigest()},
                "options": [
                    {"route": "build", "intent": self.intent()},
                    {"route": "compare", "intent": {
                        "kind": "goal_intent", "objective": "compare_records",
                        "resources": [{"role": "reference", "path": "old.csv"},
                                      {"role": "observed", "path": "new.csv"}]}}
                ]}
        if research:
            spec["research_on_gap"] = True
        return spec

    def test_direct_intent_cannot_decompose_expired_lease(self):
        db, task = self.claim(self.intent())
        with closing(db):
            self.expire(db, task)
            result = run_intent(db, task)
            self.assertEqual(result["status"], "STALE_WORKER")
            self.assert_no_child_or_transition(db, task)

    def test_knowledge_route_cannot_enqueue_expired_lease(self):
        db, task = self.claim(self.knowledge())
        with closing(db):
            self.expire(db, task)
            result = run_knowledge_intent(db, task, self.fx)
            self.assertEqual(result["status"], "STALE_WORKER")
            self.assert_no_child_or_transition(db, task)

    def test_research_gap_cannot_enqueue_expired_lease(self):
        spec = self.knowledge(matched=False, research=True)
        gap = classify_research_gap(spec, self.fx)
        self.assertIsNotNone(gap)
        db, task = self.claim(spec)
        with closing(db):
            self.expire(db, task)
            result = enqueue_research_gap(db, task, self.fx, spec, gap)
            self.assertEqual(result["status"], "STALE_WORKER")
            self.assert_no_child_or_transition(db, task)

    def test_open_goal_cannot_decompose_expired_lease(self):
        spec = {"kind": "open_goal", "goal":
                "Ensure settings.json has owner equal to ops without removing keep."}
        db, task = self.claim(spec)
        with closing(db):
            self.expire(db, task)
            with patch("cognition_agent_os.open_goal._select_independent_conjunction",
                       return_value=None), patch(
                "cognition_agent_os.open_goal._select_method",
                return_value={"candidate": "untrusted", "plan": {}}):
                result = run_open_goal(db, task, self.fx,
                                       planner_mode="deterministic",
                                       local_model_name=None)
            self.assertEqual(result["status"], "STALE_WORKER")
            self.assert_no_child_or_transition(db, task)

    def test_missing_or_malformed_claim_token_never_grants_ownership(self):
        """Matching NULL/empty tokens cannot masquerade as a live worker."""
        db, task = self.claim(self.intent())
        with closing(db):
            for bad in (None, "", "not-a-uuid"):
                with self.subTest(token=bad):
                    db.execute(
                        "UPDATE tasks SET claim_token=? WHERE task_id=?",
                        (bad, task["task_id"]))
                    db.commit()
                    alleged = {**task, "claim_token": bad}
                    row = db.execute(
                        "SELECT state,claim_token,lease_until FROM tasks WHERE task_id=?",
                        (task["task_id"],)).fetchone()
                    self.assertFalse(live_claim_owner(row, alleged))
                    result = run_intent(db, alleged)
                    self.assertEqual(result["status"], "STALE_WORKER")
                    self.assert_no_child_or_transition(db, alleged)

    def test_nonfinite_lease_is_never_an_unbounded_grant(self):
        db, task = self.claim(self.intent())
        with closing(db):
            self.expire(db, task, float("inf"))
            row = db.execute("SELECT state,claim_token,lease_until FROM tasks "
                             "WHERE task_id=?", (task["task_id"],)).fetchone()
            self.assertFalse(live_claim_owner(row, task))
            result = run_intent(db, task)
            self.assertEqual(result["status"], "STALE_WORKER")
            self.assert_no_child_or_transition(db, task)


if __name__ == "__main__":
    unittest.main()
