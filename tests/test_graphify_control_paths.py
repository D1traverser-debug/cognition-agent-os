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
                              "confidence":"EXTRACTED","source_file":"src/cognition_agent_os/test.py","source_location":"L1"} for a,b in checker.REQUIRED_PATHS]}
        self.graph["nodes"]=[{"id":i} for i in sorted({n["id"] for n in self.graph["nodes"]})]

    def result(self):
        self.path.write_text(json.dumps(self.graph),encoding="utf-8")
        with patch.object(checker.subprocess,"check_output",return_value=self.sha+"\n"):
            return checker.check(self.path,Path(self.tmp.name))

    def test_valid_extracted_control_edges_pass(self):
        self.assertEqual(self.result()["status"],"PASS")

    def test_missing_shared_kernel_grant_gate_cannot_pass_old_path_checks(self):
        target=("src_cognition_agent_os_control_kernel_drive_active_controller",
                "src_cognition_agent_os_ledger_current_guard")
        self.assertIn(target,checker.REQUIRED_PATHS)
        self.graph["links"]=[
            e for e in self.graph["links"]
            if (e["source"],e["target"])!=target]
        result=self.result()
        self.assertEqual(result["status"],"FAIL")
        self.assertIn("MISSING_EXTRACTED_CONTROL_EDGE:"+
                      target[0]+"->"+target[1],result["errors"])

    def test_missing_new_host_feedback_path_is_detected(self):
        target=("src_cognition_agent_os_host_run_tick",
                "src_cognition_agent_os_outcome_feedback_advance_evidence_goals")
        self.assertIn(target,checker.REQUIRED_PATHS)
        self.graph["links"]=[
            e for e in self.graph["links"]
            if (e["source"],e["target"])!=target]
        self.assertEqual(self.result()["status"],"FAIL")

    def test_inferred_edge_cannot_substitute_extracted_call(self):
        self.graph["links"][0]["confidence"]="INFERRED"
        self.assertTrue(any(x.startswith("MISSING_EXTRACTED_CONTROL_EDGE")
                            for x in self.result()["errors"]))

    def test_import_edge_cannot_substitute_call(self):
        self.graph["links"][0]["relation"]="imports"
        self.assertEqual(self.result()["status"],"FAIL")

    def test_extracted_edge_without_exact_source_location_is_rejected(self):
        del self.graph["links"][0]["source_location"]
        self.assertTrue(any(x.startswith("MISSING_SOURCE_LOCATION:")
                            for x in self.result()["errors"]))

    def test_control_edge_receipts_are_commit_bound_and_source_located(self):
        result=self.result()
        self.assertEqual(result["status"],"PASS",result)
        self.assertEqual(result["commit"],self.sha)
        self.assertEqual(len(result["control_edges"]),len(checker.REQUIRED_PATHS))
        self.assertTrue(all(e["confidence"]=="EXTRACTED"
                            for e in result["control_edges"]))

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
