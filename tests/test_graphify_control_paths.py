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
            # Graph is synthetic, but the registry contract under test is
            # the actual checkout, not a nonexistent module in temp data.
            return checker.check(self.path,Path(__file__).resolve().parents[1])

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
        extracted = [e for e in result["control_edges"]
                     if e["confidence"] == "EXTRACTED"]
        delegation = [e for e in result["control_edges"]
                      if e["confidence"] == "SOURCE_AST_EXPLICIT_DEPENDENCY_WIRING"]
        self.assertEqual(len(extracted), len(checker.REQUIRED_PATHS))
        self.assertEqual(len(delegation), 1)
        self.assertEqual(delegation[0]["callee"],
                         "src_cognition_agent_os_runner_run_once")

    def test_rewired_native_worker_dependency_is_not_mistaken_for_real_runner(self):
        repo=Path(__file__).resolve().parents[1]
        dest=Path(self.tmp.name)/"src"/"cognition_agent_os"
        dest.mkdir(parents=True, exist_ok=True)
        for filename in ("capability_dispatch.py", "native_mcp_bridge.py",
                         "native_local_planner.py", "host.py", "native_tick_flow.py"):
            content=(repo/"src"/"cognition_agent_os"/filename).read_text(
                encoding="utf-8")
            if filename=="host.py":
                self.assertIn("run_one=run_once", content)
                content=content.replace("run_one=run_once",
                                        "run_one=unauthorized_runner")
            (dest/filename).write_text(content, encoding="utf-8")
        self.path.write_text(json.dumps(self.graph), encoding="utf-8")
        with patch.object(checker.subprocess, "check_output",
                          return_value=self.sha+"\\n"):
            result=checker.check(self.path, Path(self.tmp.name))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("NATIVE_FEEDBACK_WORKER_DELEGATION_UNPROVEN",
                      result["errors"])

    def test_registry_cannot_silently_change_goal_intent_destination(self):
        live = (Path(__file__).resolve().parents[1] /
                "src/cognition_agent_os/capability_dispatch.py").read_text(encoding="utf-8")
        altered = live.replace('"goal_intent": _intent', '"goal_intent": _goal_case')
        self.assertNotEqual(altered, live)
        folder = Path(self.tmp.name)/"src"/"cognition_agent_os"
        folder.mkdir(parents=True)
        (folder/"capability_dispatch.py").write_text(altered, encoding="utf-8")
        self.path.write_text(json.dumps(self.graph), encoding="utf-8")
        with patch.object(checker.subprocess,"check_output",return_value=self.sha+"\\n"):
            result = checker.check(self.path,Path(self.tmp.name))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertIn("CAPABILITY_REGISTRY_INTENT_EXECUTION_UNPROVEN",
                      result["errors"])

    def test_current_mcp_research_path_cannot_be_cut_without_graph_notice(self):
        """A stale legacy graph must not pass when the ACTIVE MCP branch breaks."""
        repo=Path(__file__).resolve().parents[1]
        dest=Path(self.tmp.name)/"src"/"cognition_agent_os"
        dest.mkdir(parents=True,exist_ok=True)
        for filename in ("capability_dispatch.py","native_mcp_bridge.py",
                         "native_local_planner.py","host.py"):
            original=(repo/"src"/"cognition_agent_os"/filename).read_text(
                encoding="utf-8")
            if filename=="native_mcp_bridge.py":
                self.assertIn("return record_native_open_research(",original)
                original=original.replace(
                    "return record_native_open_research(",
                    "return unverified_research_checkpoint(")
            (dest/filename).write_text(original,encoding="utf-8")
        self.path.write_text(json.dumps(self.graph),encoding="utf-8")
        with patch.object(checker.subprocess,"check_output",
                          return_value=self.sha+"\n"):
            result=checker.check(self.path,Path(self.tmp.name))
        self.assertEqual(result["status"],"FAIL",result)
        self.assertIn("NATIVE_MCP_RESEARCH_LINEAGE_UNPROVEN",
                      result["errors"])

    def test_native_host_planner_path_cannot_be_cut_without_graph_notice(self):
        """Also guard actual Host→planner route, not obsolete legacy only."""
        repo=Path(__file__).resolve().parents[1]
        dest=Path(self.tmp.name)/"src"/"cognition_agent_os"
        dest.mkdir(parents=True,exist_ok=True)
        for filename in ("capability_dispatch.py","native_mcp_bridge.py",
                         "native_local_planner.py","host.py"):
            original=(repo/"src"/"cognition_agent_os"/filename).read_text(
                encoding="utf-8")
            if filename=="host.py":
                self.assertIn("native_choices = advance_native_local_goals(",original)
                original=original.replace(
                    "native_choices = advance_native_local_goals(",
                    "native_choices = unverified_planner_route(")
            (dest/filename).write_text(original,encoding="utf-8")
        self.path.write_text(json.dumps(self.graph),encoding="utf-8")
        with patch.object(checker.subprocess,"check_output",
                          return_value=self.sha+"\n"):
            result=checker.check(self.path,Path(self.tmp.name))
        self.assertEqual(result["status"],"FAIL",result)
        self.assertIn("HOST_NATIVE_PLANNER_LINEAGE_UNPROVEN",
                      result["errors"])

    def test_native_mcp_same_named_function_from_wrong_module_is_rejected(self):
        """Same spelling + call line does NOT prove its implementation identity."""
        repo=Path(__file__).resolve().parents[1]
        dest=Path(self.tmp.name)/"src"/"cognition_agent_os"
        dest.mkdir(parents=True,exist_ok=True)
        for filename in ("capability_dispatch.py","native_mcp_bridge.py",
                         "native_local_planner.py","host.py"):
            original=(repo/"src"/"cognition_agent_os"/filename).read_text(
                encoding="utf-8")
            if filename=="native_mcp_bridge.py":
                wrong="from .native_decision import ("
                self.assertIn(wrong,original)
                original=original.replace(
                    wrong,"from .shadow_untrusted_decision import (")
            (dest/filename).write_text(original,encoding="utf-8")
        self.path.write_text(json.dumps(self.graph),encoding="utf-8")
        with patch.object(checker.subprocess,"check_output",
                          return_value=self.sha+"\n"):
            result=checker.check(self.path,Path(self.tmp.name))
        self.assertEqual(result["status"],"FAIL",result)
        self.assertIn("NATIVE_MCP_RESEARCH_LINEAGE_UNPROVEN",
                      result["errors"])
        self.assertIn("NATIVE_MCP_ADMISSION_LINEAGE_UNPROVEN",
                      result["errors"])

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
