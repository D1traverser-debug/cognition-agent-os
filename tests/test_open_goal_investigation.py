"""P1 open-source research probe: true host path, not a fabricated task label.

The local model replies are controlled test doubles, not proof of model reasoning.
The worker must choose documents from a *discovered* manifest and attach exact
source quotations. Independent conformance reads back the original bytes.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import alter_authority, connect, create_task, initialize
from cognition_agent_os import local_model


class OpenGoalInvestigationTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.workspace = self.root / "workspace"
        self.dbpath = self.root / "state.sqlite"
        with closing(connect(self.dbpath)) as db:
            initialize(db)
        self.a = "An untrusted plan cannot grant itself permission."
        self.b = "An independent reviewer checks readback against the requested outcome."
        (self.sources / "authority.md").write_text(self.a, encoding="utf-8")
        (self.sources / "verification.md").write_text(self.b, encoding="utf-8")
        self.before = {p.name: p.read_bytes() for p in self.sources.iterdir()}

    def seed(self, question="How should an unknown plan be evaluated?"):
        with closing(connect(self.dbpath)) as db:
            return create_task(db, {
                "kind": "investigate_goal",
                "question": question,
                "scope": "LOCAL_EVIDENCE_ONLY",
            })

    def model(self, *, selection=None, findings=None, callback=None):
        selected = selection if selection is not None else [
            "authority.md", "verification.md"]
        facts = findings if findings is not None else [
            {"source": "authority.md", "quote": self.a,
             "interpretation": "Permission needs a separate authority."},
            {"source": "verification.md", "quote": self.b,
             "interpretation": "Readback must have an independent evaluator."},
        ]
        requests = []

        def fake(method, path, payload, timeout):
            requests.append((method, path, payload))
            if method == "GET":
                return {"models": [{"name": "local:test"}]}
            if len([q for q in requests if q[0] == "POST"]) == 1:
                return {"done": True, "response": json.dumps({"sources": selected})}
            if callback is not None:
                callback()
            return {"done": True, "response": json.dumps({
                "findings": facts,
                "uncertainty": "Unverified interpretation; no actual business effect.",
            })}

        return fake, requests

    def test_unknown_question_discovers_documents_and_runs_same_host(self):
        tid = self.seed()
        fake, calls = self.model()
        with patch.object(local_model, "_request", side_effect=fake):
            result = run_tick(self.dbpath, self.workspace, self.sources,
                              max_jobs=1, planner_mode="ollama-local",
                              local_model="local:test")
        self.assertEqual(result["tasks"][0]["status"], "NEEDS_REVIEW", result)
        artifact = json.loads((self.workspace / "artifacts" / (tid + ".json")).read_text())
        self.assertEqual({x["source"] for x in artifact["findings"]},
                         {"authority.md", "verification.md"})
        self.assertEqual(len(artifact["source_sha256"]), 2)
        self.assertFalse(artifact["business_outcome_verified"])
        self.assertEqual(artifact["status"], "MODEL_RESEARCH_NOT_APPROVED")
        self.assertEqual(len([x for x in calls if x[0] == "POST"]), 2)
        self.assertEqual({p.name: p.read_bytes() for p in self.sources.iterdir()}, self.before)
        # Conformance must not falsely quarantine an unapproved grounded candidate.
        self.assertEqual(result["conformance"]["quarantined"], [], result)

    def test_different_domain_same_controller_no_domain_branch(self):
        self.a = "The regulator requires traceable assumptions in the scenario."
        self.b = "The field study found that outcomes may differ from predictions."
        (self.sources / "authority.md").write_text(self.a, encoding="utf-8")
        (self.sources / "verification.md").write_text(self.b, encoding="utf-8")
        tid = self.seed("What evidence informs a regulation field-study conflict?")
        fake, _ = self.model()
        with patch.object(local_model, "_request", side_effect=fake):
            tick = run_tick(self.dbpath, self.workspace, self.sources,
                            max_jobs=1, planner_mode="ollama-local",
                            local_model="local:test")
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW", tick)
        self.assertTrue((self.workspace / "artifacts" / (tid + ".json")).is_file())

    def test_fake_quote_is_rejected_no_artifact_or_success(self):
        tid = self.seed()
        bad = [{"source": "authority.md", "quote": "False independent approval.",
                "interpretation": "Pass"}]
        fake, _ = self.model(findings=bad)
        with patch.object(local_model, "_request", side_effect=fake):
            result = run_tick(self.dbpath, self.workspace, self.sources,
                              max_jobs=1, planner_mode="ollama-local",
                              local_model="local:test")
        self.assertEqual(result["tasks"][0]["status"], "UNKNOWN", result)
        self.assertFalse((self.workspace / "artifacts" / (tid + ".json")).exists())

    def test_unlisted_source_rejected_before_read(self):
        tid = self.seed()
        fake, _ = self.model(selection=["authority.md", "../private.txt"])
        with patch.object(local_model, "_request", side_effect=fake):
            result = run_tick(self.dbpath, self.workspace, self.sources,
                              max_jobs=1, planner_mode="ollama-local",
                              local_model="local:test")
        self.assertEqual(result["tasks"][0]["status"], "UNKNOWN", result)
        self.assertFalse((self.workspace / "artifacts" / (tid + ".json")).exists())

    def test_revocation_during_model_reasoning_prevents_commit(self):
        tid = self.seed()
        def revoke():
            with closing(connect(self.dbpath)) as db:
                alter_authority(db, revoke=True)
        fake, _ = self.model(callback=revoke)
        with patch.object(local_model, "_request", side_effect=fake):
            tick = run_tick(self.dbpath, self.workspace, self.sources,
                            max_jobs=1, planner_mode="ollama-local",
                            local_model="local:test")
        self.assertEqual(tick["tasks"][0]["status"], "BLOCKED", tick)
        self.assertFalse((self.workspace / "artifacts" / (tid + ".json")).exists())
        with closing(sqlite3.connect(self.dbpath)) as db:
            self.assertEqual(db.execute(
                "SELECT write_allowed FROM authority WHERE singleton=1").fetchone()[0], 0)

    def test_source_drift_during_model_reasoning_prevents_candidate(self):
        tid = self.seed()
        def drift():
            (self.sources / "authority.md").write_text(self.a + " tampered", encoding="utf-8")
        fake, _ = self.model(callback=drift)
        with patch.object(local_model, "_request", side_effect=fake):
            tick = run_tick(self.dbpath, self.workspace, self.sources,
                            max_jobs=1, planner_mode="ollama-local",
                            local_model="local:test")
        self.assertEqual(tick["tasks"][0]["status"], "UNKNOWN", tick)
        self.assertFalse((self.workspace / "artifacts" / (tid + ".json")).exists())

    def test_no_model_mode_fails_closed(self):
        tid = self.seed()
        tick = run_tick(self.dbpath, self.workspace, self.sources,
                        max_jobs=1, planner_mode="deterministic")
        self.assertEqual(tick["tasks"][0]["status"], "UNKNOWN", tick)
        self.assertFalse((self.workspace / "artifacts" / (tid + ".json")).exists())


if __name__ == "__main__":
    unittest.main()
