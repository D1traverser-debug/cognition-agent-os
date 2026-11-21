"""Real cross-repository Video Studio boundary test (no mocks, no network).

Run with PYTHONPATH=caos/src:video using the pinned Video Studio source.
Tests structural CAOS->Video admission, not native ChatGPT Skill selection.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.child_handoff import compile_video_handoff, ChildHandoffError
from video_studio.engine import StudioEngine, GateError, ContractError


def brief(governed=True):
    b = {
        "goal": "Evaluate a video-clip technique from verified external source.",
        "audience": "Media operators",
        "deliverables": ["decision.json"],
        "success_criteria": ["Verified answer and reusable decision with limits"],
    }
    if governed:
        b["governance"] = {
            "mode": "CAOS_PARENT", "parent_system": "cognition-agent-os",
            "allowed_effects": ["PUBLIC_READ", "ISOLATED_LOCAL_WRITE"],
        }
    return b


def reviewed_draft():
    return {
        "owner_goal_ref": "synthetic-ci-owner:1",
        "owner_corrections": ["Use CAOS parent decision governance"],
        "source_refs": ["synthetic-ci:evidence", "synthetic-ci:counterexample"],
        "decision": {
            "question": "How should this media technique be integrated?",
            "hypotheses": [
                {"id": "entry_failure", "discriminator": "Check claim admission"},
                {"id": "source_failure", "discriminator": "Compare original source"},
            ],
            "alternatives": [{"id": "reuse"}, {"id": "rebuild"}],
            "selected_option": "reuse",
            "falsifier": "Owner-outcome test contradicts selected route",
            "rollback": "Restore original version",
        },
        "allowed_effects": ["PUBLIC_READ"],
        "verification": {
            "owner_outcomes": ["Real business acceptance"],
            "independent_evidence": ["Unrelated reviewer actual bytes"],
        },
        "unknowns": ["Native ChatGPT selection not tested"],
    }


def task():
    return {
        "task_id": "research", "kind": "research", "executor": "agent",
        "depends_on": [], "inputs": [], "outputs": ["decision"],
        "acceptance": {"requirement": "Independent evidence"},
    }


class ParentChildIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = StudioEngine(Path(self.temp.name))

    def test_caos_compiler_to_native_video_claim(self):
        b = brief()
        self.engine.create_project("p1", "p1", b)
        self.engine.add_tasks("p1", [task()])
        with self.assertRaises(GateError):
            self.engine.claim_next("p1", "worker")

        receipt = compile_video_handoff("p1", b, reviewed_draft())
        status = self.engine.admit_parent_handoff("p1", receipt)
        self.assertTrue(status["admitted"])
        packet = self.engine.claim_next("p1", "worker")
        self.assertEqual(packet["task"]["task_id"], "research")
        self.assertEqual(packet["claim"]["worker_id"], "worker")

    def test_stale_goal_and_downgrade_are_refused(self):
        b = brief()
        self.engine.create_project("p1", "p1", b)
        self.engine.add_tasks("p1", [task()])
        old = compile_video_handoff("p1", b, reviewed_draft())
        self.engine.admit_parent_handoff("p1", old)

        edited = deepcopy(b)
        edited["goal"] = "Owner-revised question about media evidence"
        self.engine.revise_brief("p1", edited, reason="Owner correction", affected_task_ids=[])
        self.assertEqual(self.engine.parent_handoff_status("p1")["reason"], "PARENT_HANDOFF_STALE")
        with self.assertRaises(GateError):
            self.engine.claim_next("p1", "worker")
        with self.assertRaises(ContractError):
            self.engine.admit_parent_handoff("p1", old)
        with self.assertRaises(GateError):
            self.engine.revise_brief("p1", brief(governed=False), reason="Silent opt-out")

        new = compile_video_handoff("p1", edited, reviewed_draft())
        self.engine.admit_parent_handoff("p1", new)
        self.assertIsNotNone(self.engine.claim_next("p1", "worker"))

    def test_out_of_scope_effects_and_wrong_project_rejected(self):
        b = brief()
        self.engine.create_project("p1", "p1", b)
        d = reviewed_draft()
        d["allowed_effects"] = ["PRODUCTION_RELEASE"]
        with self.assertRaises(ChildHandoffError):
            compile_video_handoff("p1", b, d)
        valid = compile_video_handoff("another_project", b, reviewed_draft())
        with self.assertRaises(ContractError):
            self.engine.admit_parent_handoff("p1", valid)

    def test_unrelated_direct_video_still_works(self):
        b = brief(governed=False)
        self.engine.create_project("standalone", "standalone", b)
        self.engine.add_tasks("standalone", [task()])
        self.assertEqual(self.engine.claim_next("standalone", "worker")["task"]["task_id"], "research")


if __name__ == "__main__":
    unittest.main(verbosity=2)
