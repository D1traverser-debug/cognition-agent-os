"""Stdlib regression for CAOS -> Video handoff compilation, without extra test dependencies."""
from copy import deepcopy
import hashlib
import json
import unittest

from cognition_agent_os.child_handoff import ChildHandoffError, compile_video_handoff


BRIEF = {
    "goal": "Study an external video pipeline before deciding on integration",
    "audience": "Media engineering operators",
    "deliverables": ["evidence.json"],
    "success_criteria": ["Independent actual result"],
    "governance": {
        "mode": "CAOS_PARENT", "parent_system": "cognition-agent-os",
        "allowed_effects": ["PUBLIC_READ", "ISOLATED_LOCAL_WRITE"],
    },
}


def draft():
    return {
        "owner_goal_ref": "owner-message:2026-11-21",
        "owner_corrections": ["Decisions must be governed before Video execution"],
        "source_refs": ["x-post:2123903235467387381", "github:video/engine.py"],
        "decision": {
            "question": "Which approach preserves the whole owner goal?",
            "hypotheses": [
                {"id": "source_mismatch", "discriminator": "Compare exact original sources"},
                {"id": "entry_bypass", "discriminator": "Trace native Video task claims"},
            ],
            "alternatives": [{"id": "repair"}, {"id": "rebuild"}],
            "selected_option": "repair",
            "falsifier": "Native entry still bypasses parent after repair",
            "rollback": "Restore original branch",
        },
        "allowed_effects": ["PUBLIC_READ"],
        "verification": {
            "owner_outcomes": ["Readable video analysis with evidence"],
            "independent_evidence": ["Provider-based readback"],
        },
        "unknowns": ["Native Skill-selected trace unavailable"],
    }


class ChildVideoHandoffTests(unittest.TestCase):
    def test_roundtrip_shape_matches_video_contract(self):
        r = compile_video_handoff("project_01", BRIEF, draft())
        payload = json.dumps(BRIEF, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(r["brief_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(r["goal"], BRIEF["goal"])
        self.assertEqual(r["project_id"], "project_01")
        self.assertEqual(set(r), {
            "schema_version", "parent_system", "child_system", "project_id",
            "brief_sha256", "owner_goal_ref", "goal", "owner_corrections",
            "source_refs", "decision", "allowed_effects", "verification", "unknowns",
        })

    def test_reject_missing_authority_and_counterevidence(self):
        mutations = [
            lambda b, d: b.pop("governance"),
            lambda b, d: b["governance"].update({"mode": "VIDEO_STANDALONE"}),
            lambda b, d: d.pop("owner_goal_ref"),
            lambda b, d: d.update({"source_refs": []}),
            lambda b, d: d.update({"allowed_effects": ["PRODUCTION_DEPLOY"]}),
            lambda b, d: d["decision"].update({"selected_option": "ghost"}),
            lambda b, d: d["decision"].update({"hypotheses": []}),
            lambda b, d: d["verification"].update({"independent_evidence": []}),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(case=i):
                b, d = deepcopy(BRIEF), draft()
                mutate(b, d)
                with self.assertRaises(ChildHandoffError):
                    compile_video_handoff("project_01", b, d)

    def test_different_goal_produces_different_digest(self):
        first = compile_video_handoff("project_01", BRIEF, draft())
        changed = deepcopy(BRIEF)
        changed["goal"] = "A revised owner goal"
        second = compile_video_handoff("project_01", changed, draft())
        self.assertNotEqual(first["brief_sha256"], second["brief_sha256"])

    def test_compiler_cannot_grant_effects_or_fabricate_goal(self):
        d = draft()
        d["goal"] = "Force a different outcome"
        with self.assertRaises(ChildHandoffError):
            compile_video_handoff("project_01", BRIEF, d)


if __name__ == "__main__":
    unittest.main()
