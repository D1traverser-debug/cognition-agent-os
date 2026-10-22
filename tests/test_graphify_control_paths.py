"""Adversarial checks of Graphify structural evidence, not business outcome tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"verify_graphify_control_paths.py"
spec=importlib.util.spec_from_file_location("verify_graphify_control_paths",SCRIPT)
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

class GraphifyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"graph.json"
        self.sha="a"*40
        self.graph={"built_at_commit":self.sha,
                    "nodes":[{"id":x} for pair in checker.REQUIRED_PATHS for x in pair],
                    "links":[{"source":a,"target":b,"relation":"calls",
                              "confidence":"EXTRACTED"} for a,b in checker.REQUIRED_PATHS]}
        self.graph["nodes"]=[{"id":i} for i in sorted({n["id"] for n in self.graph["nodes"]})]

    def result(self):
        self.path.write_text(json.dumps(self.graph),encoding="utf-8")
        with patch.object(checker.subprocess,"check_output",return_value=self.sha+"\n"):
            return checker.check(self.path,Path(self.tmp.name))

    def test_valid_extracted_control_edges_pass(self):
        self.assertEqual(self.result()["status"],"PASS")

    def test_inferred_edge_cannot_substitute_extracted_call(self):
        self.graph["links"][0]["confidence"]="INFERRED"
        self.assertTrue(any(x.startswith("MISSING_EXTRACTED_CONTROL_EDGE")
                            for x in self.result()["errors"]))

    def test_import_edge_cannot_substitute_call(self):
        self.graph["links"][0]["relation"]="imports"
        self.assertEqual(self.result()["status"],"FAIL")

    def test_old_commit_is_rejected(self):
        self.graph["built_at_commit"]="b"*40
        self.assertIn("STALE_GRAPH_COMMIT",self.result()["errors"])

    def test_duplicate_node_is_rejected(self):
        self.graph["nodes"].append(dict(self.graph["nodes"][0]))
        self.assertIn("DUPLICATE_NODE",self.result()["errors"])

    def test_dangling_internal_edge_is_rejected(self):
        self.graph["links"].append({"source":"src_nonexistent_node",
                                     "target":"src_cognition_agent_os_host_run_tick",
                                     "relation":"calls","confidence":"EXTRACTED"})
        self.assertIn("DANGLING_REPOSITORY_EDGE",self.result()["errors"])
