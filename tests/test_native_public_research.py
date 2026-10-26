"""Authorized public method discovery must work for the native parent route.

The external GitHub transport is replaced with a fixed response; this tests
the real grant/task/Worker/audit boundary, not live provider availability.
"""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.native_decision import (
    register_native_goal, inspect_native_goal, admit_native_decision)
from cognition_agent_os.public_tool_discovery import audit_public_discovery
from cognition_agent_os.host import run_tick


class NativeAuthorizedPublicResearch(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        self.db = base/"ledger.sqlite"
        self.fx = base/"sources"
        self.ws = base/"workspace"
        self.fx.mkdir()
        self.ws.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)

    def proposal(self, root):
        observed = inspect_native_goal(self.db,self.ws,self.fx,root)
        return {
            "selected_intent": {
                "kind":"goal_intent", "objective":"discover_public_tools",
                "resources":[], "terms":["testbench","coverage"]},
            "alternative_intent":None,
            "decision_reason":(
                "Existing registered data tools do not evaluate software choices."),
            "alternative_reason":(
                "Local data-only checks cannot discover current public tool leads."),
            "expected_evidence":(
                "Independently audited public repository metadata; no install."),
            "observation_sha256":observed["observation_sha256"],
            "decision_basis": {
                "source_refs":[],
                "previous_result_task_id":None,
                "challenge":"A highly starred repository may not fit the actual goal.",
                "falsifier":"Official provider metadata contradicts the returned lead.",
                "uncertainty":"Metadata is not a security review or business result.",
            },
        }

    def test_native_owner_authorized_discovery_runs_real_worker(self):
        root = register_native_goal(
            self.db, "Investigate public testbench coverage tools for an "
                     "unfamiliar engineering task without installing them.",
            allow_public_discovery=True)
        choice = admit_native_decision(
            self.db,self.ws,self.fx,root,self.proposal(root))
        response = {"incomplete_results":False, "items":[{
            "full_name":"sample-org/sample-project",
            "html_url":"https://github.com/sample-org/sample-project",
            "private":False,"stargazers_count":7,"archived":False,
            "license":{"spdx_id":"MIT"},"description":"Example evidence only",
        }]}
        with patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   return_value=(response, "a"*64)) as provider:
            result = run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(provider.call_count,1)
        self.assertEqual(provider.call_args.args[0], ["testbench","coverage"])
        self.assertEqual(result["tasks"][0]["task_id"],choice["child_task_id"])
        self.assertEqual(result["tasks"][0]["status"],"NEEDS_REVIEW",result)
        audit=audit_public_discovery(
            self.db,self.ws,choice["child_task_id"])
        self.assertEqual(audit["status"],"PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED",
                         audit)
        state=inspect_native_goal(self.db,self.ws,self.fx,root)
        self.assertEqual(state["decisions"][0]["mechanical_verdict"],
                         "PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED",state)
        self.assertFalse(state["owner_outcome_verified"])

    def test_native_public_discovery_never_self_authorizes(self):
        root=register_native_goal(
            self.db,"Investigate public testbench coverage tools.")
        with self.assertRaisesRegex(PermissionError,
                                    "PUBLIC_DISCOVERY_NOT_AUTHORIZED"):
            admit_native_decision(
                self.db,self.ws,self.fx,root,self.proposal(root))
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE parent_task=?",
                (root,)).fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
