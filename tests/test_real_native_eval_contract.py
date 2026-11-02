"""Offline checks for the separate REAL-MODEL native vs incumbent evaluation.

These tests only protect benchmark labels and setup. They DO NOT count as
model-performance evidence; that requires the opt-in real inference job.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest


def load_benchmark():
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_real_native_goal.py"
    spec = importlib.util.spec_from_file_location("real_native_eval_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeRealModelEvalContract(unittest.TestCase):
    def test_independent_hidden_labels_and_both_success_failure_owner_cases(self):
        benchmark = load_benchmark()
        cases = benchmark.CASES
        self.assertGreaterEqual(len(cases), 4)
        self.assertEqual(len({x["id"] for x in cases}), len(cases))
        self.assertTrue(any(x["must_complete_local_owner"] for x in cases))
        self.assertTrue(any(not x["must_complete_local_owner"] for x in cases))
        self.assertTrue(any(x["target"] is None for x in cases))
        for case in cases:
            self.assertTrue(case["goal"])
            self.assertTrue(case["files"])
            self.assertTrue(all(name.split(".")[-1] in
                                ("md", "txt", "csv", "json")
                                for name in case["files"]))
            self.assertNotIn("selected_intent", case)
            self.assertNotIn("decision_basis", case)

    def test_missing_independent_oracle_cannot_count_as_model_failure_or_pass(self):
        """Unknown semantic business outcomes are not an all-failed label."""
        bench = load_benchmark()
        rows = [
            {
                "case": "unknown_domain_without_owner_oracle",
                "withheld_expected_method": None,
                "withheld_local_owner_required": True,
                "independent_local_oracle_available": False,
                "baseline": {
                    "whole_local_owner_verified": False,
                    "source_preserved": True, "selected_objectives": [],
                    "model_calls": 0},
                "native": {
                    "whole_local_owner_verified": False,
                    "source_preserved": True, "selected_objectives": [],
                    "model_calls": 1, "progress": []},
            },
            {
                "case": "mechanically_verifiable_supported_goal",
                "withheld_expected_method": "compare_records",
                "withheld_local_owner_required": True,
                "independent_local_oracle_available": True,
                "baseline": {
                    "whole_local_owner_verified": True,
                    "source_preserved": True,
                    "selected_objectives": ["compare_records"]},
                "native": {
                    "whole_local_owner_verified": False,
                    "source_preserved": True, "selected_objectives": [],
                    "model_calls": 1},
            },
        ]
        scored = bench.score_trial_results(rows)
        self.assertEqual(scored["baseline"]["owner_goals_required"], 1)
        self.assertEqual(scored["baseline"]["owner_goals_completed"], 1)
        self.assertEqual(scored["native"]["owner_goals_required"], 1)
        self.assertEqual(scored["native"]["ungradable_requested_outcomes"], 1)
        self.assertEqual(scored["native"]["owner_goals_completed"], 0)
        self.assertEqual(scored["native"]["wrong_owner_success_claims"], 0)
        self.assertFalse(scored["native"]["independent_business_result_verified"])

    def test_unscorable_positive_cannot_inflate_negative_safe_refusal(self):
        bench = load_benchmark()
        row = {
            "case": "ungraded_composite_goal",
            "withheld_expected_method": None,
            "withheld_local_owner_required": True,
            "independent_local_oracle_available": False,
            "baseline": {"whole_local_owner_verified": False,
                         "source_preserved": True, "selected_objectives": []},
            "native": {"whole_local_owner_verified": False,
                       "source_preserved": True, "selected_objectives": [],
                       "model_calls": 1,
                       "progress": [{"model_plan_status":
                                     "NATIVE_LOCAL_MODEL_ABSTAINED"}]},
        }
        scored = bench.score_trial_results([row])
        self.assertEqual(scored["native"]["negative_cases"], 0)
        self.assertEqual(scored["native"]["explicit_safe_refusals"], 0)
        self.assertEqual(scored["native"]["ungradable_requested_outcomes"], 1)

    def test_real_host_does_not_fabricate_owner_success_without_an_oracle(self):
        """Actual fixture/Host/SQLite, no paid model, no simulated outcome."""
        bench = load_benchmark()
        case = {
            "id": "unfamiliar_semantic_row_count_goal",
            "goal": ("Count nonempty event rows in audit.csv, explain why two "
                     "rows were discarded, and produce an isolated evidence "
                     "report without changing the input."),
            "files": {
                "audit.csv": "id,state\\nA,good\\nB,invalid\\nC,good\\n",
                "notes.md": "B has an invalid timestamp; verify cause.\\n",
            },
            "target": None, "must_complete_local_owner": True,
            "independent_local_oracle_available": False,
        }
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            result = bench._baseline_trial(case, home)
        self.assertTrue(result["source_preserved"], result)
        self.assertFalse(result["whole_local_owner_verified"], result)
        self.assertFalse(result["external_business_result_verified"])
        row = {
            "case": case["id"],
            "withheld_expected_method": case["target"],
            "withheld_local_owner_required": True,
            "independent_local_oracle_available": False,
            "baseline": result,
            "native": {"whole_local_owner_verified": False,
                       "source_preserved": True, "selected_objectives": [],
                       "model_calls": 0},
        }
        scores = bench.score_trial_results([row])
        self.assertEqual(scores["baseline"]["ungradable_requested_outcomes"], 1)
        self.assertEqual(scores["baseline"]["owner_goals_required"], 0)
        self.assertEqual(scores["baseline"]["owner_goals_completed"], 0)
        self.assertEqual(scores["baseline"]["negative_cases"], 0)

    def test_ungradable_false_positive_is_flagged_not_promoted(self):
        bench = load_benchmark()
        row = {
            "case": "unsupported_claimed_success",
            "withheld_expected_method": None,
            "withheld_local_owner_required": True,
            "independent_local_oracle_available": False,
            "baseline": {"whole_local_owner_verified": False,
                         "source_preserved": True, "selected_objectives": []},
            "native": {"whole_local_owner_verified": True,
                       "source_preserved": True,
                       "selected_objectives": ["investigate_evidence"],
                       "model_calls": 1},
        }
        score = bench.score_trial_results([row])["native"]
        self.assertEqual(score["owner_goals_completed"], 0)
        self.assertEqual(score["owner_claims_without_independent_oracle"], 1)

    def test_real_host_oracle_coverage_probe_shows_unknowns_without_model(self):
        """Actual SQLite/Host/effect boundary across five predeclared goals."""
        from unittest.mock import patch
        bench = load_benchmark()
        with patch.object(
            bench.local_model, "_request",
            side_effect=AssertionError("MODEL_MUST_NOT_RUN")
        ) as model:
            report = bench.measure_offline_owner_oracle_scope()
        model.assert_not_called()
        self.assertEqual(report["status"],
                         "OFFLINE_OWNER_ORACLE_SCOPE_DIAGNOSTIC")
        self.assertEqual(report["total_probes"], 5)
        self.assertEqual(report["oracle_available_probes"], 2)
        self.assertEqual(report["ungradable_probes"], 3)
        self.assertTrue(report["source_isolated"], report)
        self.assertFalse(report["real_model_capability_tested"])
        self.assertFalse(report["whole_product_ready"])
        self.assertTrue(all(
            x["evidence_status"] == "OWNER_ORACLE_NOT_IMPLEMENTED"
            for x in report["cases"][2:]), report)
        self.assertTrue(all(
            x["whole_local_owner_verified"] is False
            for x in report["cases"][2:]), report)

    def test_real_benchmark_includes_actual_host_adaptive_entry(self):
        """The model-only planner is a diagnostic arm, not the real Host path."""
        bench = load_benchmark()
        self.assertTrue(callable(getattr(bench, "_adaptive_host_trial", None)))
        rows = []
        for case in bench.CASES:
            row = {
                "case": case["id"],
                "withheld_expected_method": case["target"],
                "withheld_local_owner_required": case["must_complete_local_owner"],
            }
            for path in ("baseline", "native", "adaptive_host"):
                row[path] = {
                    "whole_local_owner_verified": False,
                    "source_preserved": True,
                    "selected_objectives": [],
                    "model_calls": 0,
                }
            rows.append(row)
        scores = bench.score_trial_results(rows)
        self.assertEqual(set(scores), {"baseline", "native", "adaptive_host"})
        self.assertEqual(scores["adaptive_host"]["owner_goals_completed"], 0)

    def test_adaptive_host_real_entry_has_source_preservation_and_owner_readback(self):
        """Actual Host/Worker/isolated effect, never stubbed planner responses."""
        bench = load_benchmark()
        with tempfile.TemporaryDirectory() as td:
            for case in bench.CASES:
                location = Path(td) / case["id"]
                location.mkdir()
                result = bench._adaptive_host_trial(case, location)
                self.assertTrue(result["source_preserved"], result)
                self.assertEqual(result["model_calls"], 0)
                self.assertEqual(result["whole_local_owner_verified"],
                                 case["must_complete_local_owner"], result)
                if case["must_complete_local_owner"]:
                    self.assertIn(case["target"], result["selected_objectives"])
                    self.assertEqual(result["independent_owner_result"],
                                     "LOCAL_OWNER_RESULT_VERIFIED", result)
                else:
                    self.assertNotEqual(result["independent_owner_result"],
                                        "LOCAL_OWNER_RESULT_VERIFIED", result)

    def test_7b_transport_failure_is_distinct_from_model_abstention(self):
        """Genuine model error receipts never count as model cognition."""
        bench = load_benchmark()
        rows = [{
            "withheld_local_owner_required": True,
            "withheld_expected_method": "compare_records",
            "native": {
                "whole_local_owner_verified": False, "source_preserved": True,
                "method_alignment": False, "model_calls": 3,
                "model_trace_actual_not_mocked": [
                    {"transport_error_class": "LocalModelUnavailable",
                     "elapsed_seconds": 120.05},
                    {"transport_error_class": "LocalModelUnavailable",
                     "elapsed_seconds": 120.07},
                    {"done": True, "raw_response": '{"abstain":true}'},
                ],
                "progress": [
                    {"model_plan_status": "NATIVE_LOCAL_MODEL_UNAVAILABLE"},
                    {"model_plan_status": "NATIVE_LOCAL_MODEL_ABSTAINED"},
                ],
                "selected_objectives": [],
            },
            "baseline": {
                "whole_local_owner_verified": True, "source_preserved": True,
                "method_alignment": True, "model_calls": 0,
                "selected_objectives": ["compare_records"],
            },
        }]
        results = bench.score_trial_results(rows)
        self.assertEqual(results["native"]["owner_goals_completed"], 0)
        self.assertEqual(results["native"]["model_generation_calls"], 3)
        self.assertEqual(results["native"]["model_transport_failures"], 2)
        self.assertEqual(results["native"]["model_abstention_calls"], 1)
        self.assertEqual(results["native"]["model_completed_generations"], 1)
        self.assertEqual(results["baseline"]["owner_goals_completed"], 1)
        self.assertEqual(results["baseline"]["model_transport_failures"], 0)

    def test_unavailable_local_model_is_not_blindly_retried_in_same_trial(self):
        """No extra 120s cost on unchanged evidence after genuine transport loss."""
        from unittest.mock import patch
        bench = load_benchmark()
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            case = bench.CASES[0]
            with patch.object(bench, "advance_native_local_once",
                return_value={"status": "NATIVE_LOCAL_MODEL_UNAVAILABLE",
                              "reason": "local timeout",
                              "owner_outcome_verified": False}) as attempt:
                result = bench._native_trial(case, home)
            self.assertEqual(attempt.call_count, 1)
            self.assertEqual(result["independent_owner_result"],
                             "OWNER_POSTCONDITION_UNVERIFIED")
            self.assertEqual(
                [x["model_plan_status"] for x in result["progress"]],
                ["NATIVE_LOCAL_MODEL_UNAVAILABLE"])
            self.assertTrue(result["source_preserved"])
            self.assertFalse(result["whole_local_owner_verified"])

    def test_three_arm_scores_expose_real_model_invocation_cost(self):
        """A deterministic win must not be mislabeled as model cognition."""
        bench = load_benchmark()
        rows = []
        for case in bench.CASES:
            row = {"case": case["id"],
                   "withheld_expected_method": case["target"],
                   "withheld_local_owner_required": case["must_complete_local_owner"]}
            for arm in ("baseline", "native", "adaptive_host"):
                row[arm] = {"whole_local_owner_verified": False,
                            "source_preserved": True,
                            "selected_objectives": [],
                            "model_calls": 2 if arm == "native" else 0}
            rows.append(row)
        scored = bench.score_trial_results(rows)
        self.assertEqual(scored["baseline"]["model_generation_calls"], 0)
        self.assertEqual(scored["native"]["model_generation_calls"], 8)
        self.assertEqual(scored["adaptive_host"]["model_generation_calls"], 0)
        self.assertEqual(scored["adaptive_host"]["owner_goals_completed"], 0)

    def test_main_serializes_three_actual_arms_into_one_report(self):
        """Execute the evaluation ENTRY, not an internal scoring helper.

        Stubs are only wire tests; no model performance may be inferred.
        """
        import contextlib
        import io
        import json
        from unittest.mock import patch
        bench = load_benchmark()
        def fake(case, home):
            return {"case": case["id"], "path": "TEST_STUB_NOT_MODEL",
                    "whole_local_owner_verified": False,
                    "source_preserved": True, "selected_objectives": [],
                    "independent_owner_result": "OWNER_POSTCONDITION_UNVERIFIED",
                    "model_calls": 0, "method_alignment": False}
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "report.json"
            with patch.object(bench, "OUTPUT", output), \
                 patch.object(bench, "_native_trial", fake), \
                 patch.object(bench, "_baseline_trial", fake), \
                 patch.object(bench, "_adaptive_host_trial", fake), \
                 contextlib.redirect_stdout(io.StringIO()):
                bench.main()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(report["scores"]),
                             {"baseline", "native", "adaptive_host"})
            self.assertEqual(len(report["cases"]), len(bench.CASES))
            for row in report["cases"]:
                self.assertEqual(set(("baseline", "native", "adaptive_host"))
                                 - set(row), set(), row)
            self.assertFalse(report["whole_product_ready"])

    def test_no_action_on_negative_cases_never_counts_as_goal_completion(self):
        bench = load_benchmark()
        rows = []
        for case in bench.CASES:
            # Two negative cases are left untouched. An old agreement score
            # reported this as 2/4 correct even when zero owner goals were
            # delivered. Safety/non-action cannot buy completion credit.
            row = {
                "case": case["id"],
                "withheld_expected_method": case["target"],
                "withheld_local_owner_required":
                    case["must_complete_local_owner"],
                "baseline": {},
                "native": {},
            }
            for name in ("baseline", "native"):
                row[name] = {
                    "whole_local_owner_verified": False,
                    "selected_objectives": [],
                    "source_preserved": True,
                    "method_alignment": False,
                    "progress": [],
                    "model_calls": 0,
                }
            rows.append(row)
        scores = bench.score_trial_results(rows)
        for name in ("baseline", "native"):
            score = scores[name]
            self.assertEqual(score["owner_goals_completed"], 0)
            self.assertEqual(score["owner_goals_required"], 2)
            self.assertEqual(score["unsupported_or_unverified_positive"], 2)
            self.assertEqual(score["wrong_owner_success_claims"], 0)
            self.assertEqual(score["explicit_safe_refusals"], 0)
            self.assertNotIn("exact_owner_oracle_agreement", score)
            self.assertNotIn("success_rate", score)

    def test_explicit_refusal_requires_model_evidence_not_idle(self):
        bench = load_benchmark()
        case = bench.CASES[-1]
        row = {
            "case": case["id"],
            "withheld_expected_method": None,
            "withheld_local_owner_required": False,
            "baseline": {
                "whole_local_owner_verified": False,
                "selected_objectives": [],
                "source_preserved": True,
                "progress": [],
                "model_calls": 0,
            },
            "native": {
                "whole_local_owner_verified": False,
                "selected_objectives": [],
                "source_preserved": True,
                "progress": [
                    {"model_plan_status": "NATIVE_LOCAL_MODEL_ABSTAINED"}],
                "model_calls": 1,
            },
        }
        scores = bench.score_trial_results([row])
        self.assertEqual(scores["native"]["explicit_safe_refusals"], 1)
        self.assertEqual(scores["baseline"]["explicit_safe_refusals"], 0)
        self.assertEqual(scores["native"]["owner_goals_completed"], 0)

    def test_every_positive_eval_label_has_a_feasible_local_plan(self):
        """Don't interpret a known impossible safety-preserving task as LLM failure."""
        from cognition_agent_os.goal_loop import plan_goal
        bench = load_benchmark()
        labeled = [
            case for case in bench.CASES
            if case["must_complete_local_owner"]]
        self.assertEqual(len(labeled), 2)
        structure = next(
            c for c in labeled if c["target"] == "ensure_structure")
        from cognition_agent_os.owner_postcondition import _full_owner_scope_is_supported
        from cognition_agent_os.intent_planner import compile_intent
        selected = {
            "kind": "goal_intent", "objective": "ensure_structure",
            "resources": [{"role": "input", "path": "settings.json"}],
            "requirements": [{"field": "owner", "equals": "ops"}],
        }
        compiled = compile_intent(selected)
        self.assertTrue(_full_owner_scope_is_supported(
            structure["goal"], compiled))
        plan = plan_goal(
            compiled["child_source_spec"],
            structure["files"]["settings.json"].encode("utf-8"))
        self.assertIsNotNone(plan["selection"])
        self.assertEqual(plan["status"], "NEEDS_REVIEW")
        self.assertEqual(plan["selection"]["action"], "ADD_MISSING_JSON_KEYS")

    def test_native_evaluator_runs_actual_json_sandbox_stage_before_grading(self):
        """Benchmark the real Host effect, independently of model accuracy.

        The model choice is substituted ONLY in this harness unit test, never
        in the opt-in real-Ollama performance job. A correct selected method
        must have a fair opportunity to satisfy the same owner oracle as the
        deterministic incumbent.
        """
        import hashlib
        from unittest.mock import patch
        from cognition_agent_os.native_decision import (
            inspect_native_goal, admit_native_decision)
        bench = load_benchmark()
        case = next(c for c in bench.CASES
                    if c["target"] == "ensure_structure")
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            def choose_correct_method(db, work, fixtures, root, **kwargs):
                observed = inspect_native_goal(db, work, fixtures, root)
                refs = [{"path": f.name,
                         "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
                        for f in sorted(fixtures.iterdir())]
                proposal = {
                    "selected_intent": {
                        "kind": "goal_intent", "objective": "ensure_structure",
                        "resources": [{"role": "input", "path": "settings.json"}],
                        "requirements": [{"field": "owner", "equals": "ops"}]},
                    "alternative_intent": None,
                    "decision_reason":
                        "The original owner requests an isolated JSON draft.",
                    "alternative_reason":
                        "An unrelated CSV comparison cannot create that draft.",
                    "expected_evidence":
                        "A staged immutable candidate independently checked.",
                    "observation_sha256": observed["observation_sha256"],
                    "decision_basis": {
                        "source_refs": refs,
                        "previous_result_task_id": None,
                        "challenge": "An existing owner key could be contradictory.",
                        "falsifier": "Original fields are changed in the draft.",
                        "uncertainty":
                            "A local draft does not prove production deployment.",
                    },
                }
                return admit_native_decision(
                    db, work, fixtures, root, proposal)
            with patch.object(bench, "advance_native_local_once",
                              side_effect=choose_correct_method):
                result = bench._native_trial(case, home)
        self.assertTrue(result["whole_local_owner_verified"], result)
        self.assertTrue(result["source_preserved"], result)
        self.assertEqual(result["independent_owner_result"],
                         "LOCAL_OWNER_RESULT_VERIFIED")
        self.assertIn("SANDBOX_VERIFIED",
                      [item.get("status")
                       for step in result["progress"]
                       for item in step.get("sandbox_reviews", [])])
        self.assertEqual(result["model_calls"], 0)

    def test_sandbox_effect_count_cannot_be_counted_as_completed_owner_goal(self):
        bench = load_benchmark()
        case = next(c for c in bench.CASES
                    if c["target"] == "ensure_structure")
        row = {
            "case": case["id"],
            "withheld_expected_method": case["target"],
            "withheld_local_owner_required": True,
            "baseline": {
                "whole_local_owner_verified": False,
                "source_preserved": True,
                "sandbox_effects_verified": 1,
            },
            "native": {
                "whole_local_owner_verified": False,
                "source_preserved": True,
                "sandbox_effects_verified": 1,
            },
        }
        score = bench.score_trial_results([row])
        for lane in ("native", "baseline"):
            self.assertEqual(score[lane]["actual_sandbox_effects_verified"], 1)
            self.assertEqual(score[lane]["owner_goals_completed"], 0)
            self.assertEqual(score[lane]["unsupported_or_unverified_positive"], 1)

    def test_incumbent_receives_same_fixtures_without_mutating_sources(self):
        benchmark = load_benchmark()
        with tempfile.TemporaryDirectory() as td:
            result = benchmark._baseline_trial(
                benchmark.CASES[0], Path(td))
            self.assertTrue(result["source_preserved"], result)
            self.assertFalse(result["external_business_result_verified"])
            self.assertNotIn("model_trace_actual_not_mocked", result)


if __name__ == "__main__":
    unittest.main()
