"""End-to-end opt-in public tool discovery, unrelated to seeded JSON/CSV tasks."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect,initialize,create_task,alter_authority
from cognition_agent_os.open_goal import audit_open_goal
from cognition_agent_os.public_tool_discovery import (
    audit_public_discovery, safe_public_terms, _project_results,
    PublicDiscoveryInvalid, PublicDiscoveryTransport,
)

def public_search_result():
    return {
        "incomplete_results":False,
        "items":[
            {"full_name":"example/tool-framework",
             "html_url":"https://github.com/example/tool-framework",
             "private":False,"stargazers_count":172,"archived":False,
             "description":"Example metadata; no claimed runtime support",
             "license":{"spdx_id":"MIT"}},
            {"full_name":"sample/alternative-framework",
             "html_url":"https://github.com/sample/alternative-framework",
             "private":False,"stargazers_count":80,"archived":True,
             "description":"Archived example","license":None},
        ],
    }


class PublicToolDiscoveryVertical(unittest.TestCase):
    def setUp(self):
        d=TemporaryDirectory();self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.db=self.root/"authority.sqlite"
        self.ws=self.root/"workspace";self.ws.mkdir()
        self.fx=self.root/"local_sources";self.fx.mkdir()
        with closing(connect(self.db)) as db:initialize(db)
        self.goal="Find open source agent workflow orchestration framework"

    def seed(self,enabled):
        spec={"kind":"open_goal","goal":self.goal}
        if enabled:spec["allow_public_discovery"]=True
        with closing(connect(self.db)) as db:
            return create_task(db,spec)

    def children(self,root):
        with closing(connect(self.db)) as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM tasks WHERE parent_task=?",(root,))]

    def test_owner_approved_search_is_real_registered_host_work(self):
        root=self.seed(True)
        envelope=public_search_result()
        raw=json.dumps(envelope).encode()
        observed={}
        def mock_search(terms):
            observed["terms"]=terms
            return envelope,hashlib.sha256(raw).hexdigest()
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("Public owner terms need no model")), \
             patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   side_effect=mock_search):
            out=run_tick(self.db,self.ws,self.fx,max_jobs=2)
        self.assertEqual([x["status"] for x in out["tasks"]],
                         ["DECOMPOSED","NEEDS_REVIEW"],out)
        self.assertEqual(observed["terms"],["agent","workflow","orchestration"])
        children=self.children(root);self.assertEqual(len(children),1)
        child=children[0]
        self.assertEqual(json.loads(child["source_spec"]),{
            "kind":"public_tool_discovery","scope":"GITHUB_PUBLIC_METADATA_ONLY",
            "terms":["agent","workflow","orchestration"]})
        audit=audit_public_discovery(self.db,self.ws,child["task_id"])
        self.assertEqual(audit["status"],"PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED",audit)
        self.assertEqual(audit["count"],2)
        self.assertEqual(audit_open_goal(self.db,self.fx,root)["status"],
                         "METHOD_CANDIDATE_MECHANICALLY_GROUNDED")
        artifact=json.loads((self.ws/"artifacts"/(child["task_id"]+".json")).read_text())
        self.assertIs(artifact["new_tool_execution_authorized"],False)
        self.assertIs(artifact["business_outcome_verified"],False)
        self.assertIs(artifact["provider_security_verified"],False)
        self.assertEqual(out["goal_progress"]["goals"][0]["owner_outcome_verified"],False)

    def test_absent_explicit_public_grant_does_not_call_network(self):
        parent=self.seed(False)
        with patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   side_effect=AssertionError("NO NETWORK WITHOUT OWNER GRANT")), \
             patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("missing sources")):
            out=run_tick(self.db,self.ws,self.fx,max_jobs=2)
        self.assertEqual(out["tasks"][0]["status"],"UNKNOWN",out)
        self.assertFalse(self.children(parent))

    def test_revoke_before_network_fences_child(self):
        root=self.seed(True)
        with patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   side_effect=AssertionError("network only in child tick")):
            first=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(first["tasks"][0]["status"],"DECOMPOSED",first)
        with closing(connect(self.db)) as db:alter_authority(db,revoke=True)
        with patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   side_effect=AssertionError("cannot send revoked request")):
            second=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(second["tasks"][0]["status"],"BLOCKED",second)

    def test_forged_public_search_task_without_owner_has_no_network(self):
        with closing(connect(self.db)) as db:
            task=create_task(db,{
                "kind":"public_tool_discovery","scope":"GITHUB_PUBLIC_METADATA_ONLY",
                "terms":["agent","workflow"]})
        with patch("cognition_agent_os.public_tool_discovery._search_public_github",
                   side_effect=AssertionError("unowned search")):
            result=run_tick(self.db,self.ws,self.fx,max_jobs=1)
        self.assertEqual(result["tasks"][0]["status"],"UNKNOWN",result)

    def test_malicious_provider_url_rejected_as_candidate(self):
        x=public_search_result()
        x["items"][0]["html_url"]="https://evil.example.com/leak"
        with self.assertRaises(PublicDiscoveryInvalid):
            _project_results(x)

    def test_incomplete_search_is_unknown_not_false_no_results(self):
        x=public_search_result();x["incomplete_results"]=True
        with self.assertRaises(PublicDiscoveryInvalid):
            _project_results(x)

    def test_public_query_terms_are_strictly_bounded(self):
        self.assertEqual(safe_public_terms(self.goal),
                         ["agent","workflow","orchestration"])
        with self.assertRaises(PublicDiscoveryInvalid):
            safe_public_terms("Find a tool")

if __name__=="__main__":
    unittest.main()
