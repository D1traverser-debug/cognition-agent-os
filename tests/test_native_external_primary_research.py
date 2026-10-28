"""External PRIMARY source evidence crosses the existing open-research ledger.

No network, model or production effect in these tests: only provider bytes
are mocked. Tests verify grant checks, content hashing, historical readback,
stale source rejection and the absence of implicit executable authority.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    inspect_native_goal, record_native_open_research, register_native_goal,
)

_REPO = "datawhalechina/Agent-Learning-Hub"
_REF = "dddf777dde6788228136862f270203424a28efbc"
_CONTENT = (b"# Agent Learning Hub\n"
            b"Compare bounded tool, memory and owner-result evidence.\n")


class NativeExternalPrimaryEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        self.db = home / "ledger.sqlite"
        self.ws = home / "workspace"
        self.fx = home / "sources"
        self.ws.mkdir()
        self.fx.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)
        self.goal = (
            "Investigate why a cognitive agent chooses incomplete methods, "
            "compare credible primary-source alternatives and retain the "
            "full owner goal without expanding execution authority."
        )

    def proposal(self, root, sha=None):
        state = inspect_native_goal(self.db, self.ws, self.fx, root)
        return {
            "observation_sha256": state["observation_sha256"],
            "owner_clause": "compare credible primary-source alternatives",
            "unresolved_question":
                "Which existing agent loop rechecks actual owner acceptance?",
            "competing_methods": [
                {"name": "stop_hook",
                 "applicability":
                     "Run a bounded post-turn goal check against external facts.",
                 "failure_mode":
                     "A language model can hallucinate acceptance without proof.",
                 "falsifier":
                     "Actual owner effect contradicts the model's positive verdict."},
                {"name": "source_oracle",
                 "applicability":
                     "Require immutable source and real downstream readback.",
                 "failure_mode":
                     "A source citation alone does not prove business success.",
                 "falsifier":
                     "Independent owner outcome remains unresolved after research."},
            ],
            "source_refs": [{
                "kind": "github", "repo": _REPO, "path": "README.md",
                "ref": _REF,
                "sha256": sha or hashlib.sha256(_CONTENT).hexdigest(),
            }],
            "next_research_step":
                "Compare the upstream source against the native Host control boundary.",
            "uncertainty":
                "External documentation is untrusted and cannot authorize code or effects.",
        }

    def test_public_pinned_primary_bytes_are_verified_and_replayed(self):
        root = register_native_goal(
            self.db, self.goal, allow_public_source_read=True)
        with patch("cognition_agent_os.native_decision.github_public_snapshot",
                   return_value=_CONTENT) as fetch:
            result = record_native_open_research(
                self.db, self.ws, self.fx, root, self.proposal(root))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args,
                         (_REPO, "README.md", _REF))
        self.assertEqual(result["status"], "NATIVE_OPEN_RESEARCH_RECORDED")
        # Cold replay does not make an HTTP request and does not grant a tool.
        state = inspect_native_goal(self.db, self.ws, self.fx, root)
        self.assertEqual(state["open_research_count"], 1, state)
        self.assertEqual(state["open_research"][0]["source_status"],
                         "GITHUB_PIN_VERIFIED_AT_RECORD_UNTRUSTED_SEMANTICS")
        self.assertEqual(state["decision_count"], 0)
        self.assertFalse(state["owner_outcome_verified"])
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 0)

    def test_public_code_disclosure_never_inherits_metadata_grant(self):
        for kwargs in ({}, {"allow_public_discovery": True}):
            with self.subTest(kwargs=kwargs):
                root = register_native_goal(self.db, self.goal, **kwargs)
                with patch("cognition_agent_os.native_decision.github_public_snapshot",
                           side_effect=AssertionError("Unexpected GitHub disclosure")):
                    with self.assertRaisesRegex(
                            PermissionError, "PUBLIC_SOURCE_READ_NOT_AUTHORIZED"):
                        record_native_open_research(
                            self.db, self.ws, self.fx, root, self.proposal(root))

    def test_pinned_source_wrong_hash_fails_without_ledger_event(self):
        root = register_native_goal(
            self.db, self.goal, allow_public_source_read=True)
        with patch("cognition_agent_os.native_decision.github_public_snapshot",
                   return_value=_CONTENT):
            with self.assertRaisesRegex(ValueError, "NATIVE_RESEARCH_SOURCE_UNVERIFIABLE"):
                record_native_open_research(
                    self.db, self.ws, self.fx, root,
                    self.proposal(root, sha="f" * 64))
        self.assertEqual(inspect_native_goal(
            self.db, self.ws, self.fx, root)["open_research_count"], 0)

    def test_malformed_remote_source_is_rejected_without_network(self):
        root = register_native_goal(
            self.db, self.goal, allow_public_source_read=True)
        for path in ("../secrets", "/etc/passwd", "README.md/../private"):
            with self.subTest(path=path):
                proposal = self.proposal(root)
                proposal["source_refs"][0]["path"] = path
                with patch("cognition_agent_os.native_decision.github_public_snapshot",
                           side_effect=AssertionError("Invalid outbound request")):
                    with self.assertRaises(ValueError):
                        record_native_open_research(
                            self.db, self.ws, self.fx, root, proposal)


if __name__ == "__main__":
    unittest.main()
