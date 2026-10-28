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

    def test_one_root_discovers_candidates_then_preserves_primary_research(self):
        """Provider metadata -> actual Worker -> pinned primary study -> cold audit.

        Search results and source bytes are mocked at the network boundary.
        The single original goal, ledger, admission, Worker, artifact hashes
        and later resumption are all real, and neither artifact is an effect
        authorization or a verified business result.
        """
        from cognition_agent_os.native_decision import admit_native_decision
        from cognition_agent_os.host import run_tick
        root = register_native_goal(
            self.db, self.goal, allow_public_discovery=True,
            allow_public_source_read=True)
        state = inspect_native_goal(self.db, self.ws, self.fx, root)
        proposal = {
            "selected_intent": {
                "kind": "goal_intent", "objective": "discover_public_tools",
                "resources": [], "terms": ["agent", "harness"]},
            "alternative_intent": None,
            "decision_reason":
                "A current public source lead must be checked against actual code.",
            "alternative_reason":
                "Local files do not contain current external package methods.",
            "expected_evidence":
                "A bounded provider response and independently pinned source.",
            "observation_sha256": state["observation_sha256"],
            "decision_basis": {
                "source_refs": [], "previous_result_task_id": None,
                "challenge":
                    "Repository popularity cannot establish professional fit.",
                "falsifier":
                    "Original source disagrees with advertised functionality.",
                "uncertainty":
                    "The user business outcome remains independently unresolved.",
            },
        }
        chosen = admit_native_decision(
            self.db, self.ws, self.fx, root, proposal)
        envelope = {"incomplete_results": False, "items": [{
            "full_name": _REPO, "html_url": "https://github.com/" + _REPO,
            "private": False, "stargazers_count": 42,
            "archived": False, "license": {"spdx_id": "MIT"},
            "description": "An Agent engineering learning map",
        }]}
        with patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   return_value=(envelope, "a" * 64)):
            tick = run_tick(self.db, self.ws, self.fx, max_jobs=1)
        self.assertEqual(tick["tasks"][0]["task_id"], chosen["child_task_id"])
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW", tick)
        report = self.ws / "artifacts" / (chosen["child_task_id"] + ".json")
        import json
        self.assertEqual(
            json.loads(report.read_text())["candidate_repositories"][0]
            ["research_status"], "UNVERIFIED_CANDIDATE")
        with patch("cognition_agent_os.native_decision.github_public_snapshot",
                   return_value=_CONTENT) as provider:
            result = record_native_open_research(
                self.db, self.ws, self.fx, root, self.proposal(root))
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(result["status"], "NATIVE_OPEN_RESEARCH_RECORDED")
        after = inspect_native_goal(self.db, self.ws, self.fx, root)
        self.assertEqual(after["decision_count"], 1, after)
        self.assertEqual(after["open_research_count"], 1, after)
        self.assertEqual(
            after["open_research"][0]["source_status"],
            "GITHUB_PIN_VERIFIED_AT_RECORD_UNTRUSTED_SEMANTICS")
        self.assertFalse(after["owner_outcome_verified"])
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0], 1)

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

    def test_revoked_grant_during_remote_read_cannot_commit_research(self):
        root = register_native_goal(
            self.db, self.goal, allow_public_source_read=True)
        def change_authority(repo, path, ref):
            with closing(connect(self.db)) as db:
                db.execute("UPDATE authority SET grant_rev=grant_rev+1 "
                           "WHERE singleton=1")
                db.commit()
            return _CONTENT
        with patch("cognition_agent_os.native_decision.github_public_snapshot",
                   side_effect=change_authority):
            with self.assertRaisesRegex(
                    ValueError, "NATIVE_DECISION_NOT_ADMISSIBLE"):
                record_native_open_research(
                    self.db, self.ws, self.fx, root, self.proposal(root))
        with closing(connect(self.db)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='NATIVE_OPEN_RESEARCH_RECORDED'",
                (root,)).fetchone()[0]
        self.assertEqual(count, 0)

    def test_request_id_cannot_upgrade_metadata_grant_on_retry(self):
        key = "native-source-scope-check-20261028"
        first = register_native_goal(
            self.db, self.goal, client_request_id=key,
            allow_public_discovery=True)
        self.assertEqual(register_native_goal(
            self.db, self.goal, client_request_id=key,
            allow_public_discovery=True), first)
        with self.assertRaisesRegex(ValueError, "NATIVE_GOAL_IDEMPOTENCY_CONFLICT"):
            register_native_goal(
                self.db, self.goal, client_request_id=key,
                allow_public_discovery=True, allow_public_source_read=True)

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
