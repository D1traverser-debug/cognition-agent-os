"""Architecture seam contract: independent scripted traces, same Host authority.

Scripted dependencies test ordering and refusal, not model cognition or
business-outcome success. Real Host/SQLite/Worker tests run in full CI too.
"""
import unittest
from pathlib import Path

from cognition_agent_os.native_tick_flow import drain_native_feedback


class FeedbackSeamTests(unittest.TestCase):
    def run_case(self, events, choices, *, enabled=True, stage=False,
                 admitted=True, max_jobs=4):
        queue = list(events)
        called = []
        decisions = []
        reviews = []
        most_recent_task_id = None
        def worker(*args, **kwargs):
            nonlocal most_recent_task_id
            event = queue.pop(0) if queue else {"status": "IDLE"}
            most_recent_task_id = event.get("task_id")
            called.append(("worker", most_recent_task_id))
            return event
        def review(*args, **kwargs):
            called.append(("review", kwargs.get("max_reviews")))
            receipt = {"task_id": most_recent_task_id,
                       "status": "SANDBOX_VERIFIED"}
            reviews.append(receipt)
            return [receipt]
        def policy(*args, **kwargs):
            called.append(("policy", args[3]))
            decisions.append(args[3])
            return {"status": "NATIVE_LOCAL_MODEL_ABSTAINED"}
        out = drain_native_feedback(
            Path("ledger"), Path("work"), Path("fixtures"),
            max_jobs=max_jobs, planner_mode="deterministic", local_model=None,
            auto_native_cognition=enabled, auto_stage_goals=stage,
            preflight={"admitted": admitted} if stage else None,
            native_choices=choices, run_one=worker, review_due=review,
            advance_cognition=policy)
        return out, called, decisions, reviews

    def test_only_admitted_effect_in_this_tick_can_trigger_followup(self):
        decisions = [{"status": "NATIVE_METHOD_ENQUEUED",
                      "child_task_id": "c1", "root_task_id": "root"}]
        out, calls, selected, _ = self.run_case(
            [{"status": "PROCESSED", "task_id": "other"},
             {"status": "PROCESSED", "task_id": "c1"}], decisions)
        self.assertEqual(selected, ["root"])
        self.assertEqual(calls, [
            ("worker", "other"), ("worker", "c1"),
            ("policy", "root"), ("worker", None)])
        self.assertEqual(len(out[0]), 2)
        self.assertEqual(len(decisions), 2)

    def test_planned_peer_not_finished_prevents_new_decision(self):
        decisions = [
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "c1", "root_task_id": "root"},
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "c2", "root_task_id": "root"}]
        _, _, selected, _ = self.run_case(
            [{"status": "PROCESSED", "task_id": "c1"}], decisions)
        self.assertEqual(selected, [])

    def test_unrelated_pending_root_does_not_block_completed_root(self):
        # Two separately admitted owner roots have no causal dependency.
        # Root B's queued child must not suppress Root A's legal follow-up.
        decisions = [
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "a1", "root_task_id": "root-a"},
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "b1", "root_task_id": "root-b"},
        ]
        _, calls, selected, _ = self.run_case(
            [{"status": "PROCESSED", "task_id": "a1"}], decisions)
        self.assertEqual(selected, ["root-a"])
        self.assertEqual(calls[:2], [
            ("worker", "a1"), ("policy", "root-a")])

    def test_same_root_unfinished_peer_still_blocks_followup(self):
        decisions = [
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "a1", "root_task_id": "root-a"},
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "a2", "root_task_id": "root-a"},
            {"status": "NATIVE_METHOD_ENQUEUED",
             "child_task_id": "b1", "root_task_id": "root-b"},
        ]
        _, _, selected, _ = self.run_case(
            [{"status": "PROCESSED", "task_id": "a1"}], decisions)
        self.assertEqual(selected, [])

    def test_opt_out_prevents_model_and_review_writes(self):
        decisions = [{"status": "NATIVE_METHOD_ENQUEUED",
                      "child_task_id": "c1", "root_task_id": "root"}]
        out, called, selected, reviews = self.run_case(
            [{"status": "PROCESSED", "task_id": "c1"}], decisions,
            enabled=False, stage=True)
        self.assertEqual(selected, [])
        self.assertEqual(reviews, [])
        self.assertEqual(out[1], [])
        self.assertEqual(called, [("worker", "c1"), ("worker", None)])

    def test_unstaged_json_must_not_trigger_model_replanning(self):
        choices = [{"status": "NATIVE_METHOD_ENQUEUED",
                    "child_task_id": "json1", "root_task_id": "owner-json",
                    "selected_objective": "ensure_structure"}]
        observed, events, selected, reviews = self.run_case(
            [{"status": "NEEDS_REVIEW", "task_id": "json1"}],
            choices, enabled=True, stage=False, max_jobs=2)
        self.assertEqual(selected, [], "No new model plan without sandbox grant")
        self.assertEqual(reviews, [])
        self.assertEqual(choices[-1]["status"],
                         "NATIVE_SANDBOX_EFFECT_AWAITING_OPT_IN")
        self.assertEqual(observed[0][0]["task_id"], "json1")
        self.assertNotIn(("policy", "owner-json"), events)

    def test_staged_json_preserves_followup_independent_readback(self):
        choices = [{"status": "NATIVE_METHOD_ENQUEUED",
                    "child_task_id": "json1", "root_task_id": "owner-json",
                    "selected_objective": "ensure_structure"}]
        _, events, selected, reviews = self.run_case(
            [{"status": "NEEDS_REVIEW", "task_id": "json1"}],
            choices, enabled=True, stage=True, admitted=True, max_jobs=2)
        self.assertEqual(selected, ["owner-json"])
        self.assertEqual(len(reviews), 1)
        self.assertIn(("policy", "owner-json"), events)

    def test_real_review_budget_shared_and_fail_closed(self):
        decisions = [{"status": "NATIVE_METHOD_ENQUEUED",
                      "child_task_id": "c1", "root_task_id": "root"}]
        out, called, selected, reviews = self.run_case(
            [{"status": "PROCESSED", "task_id": "c1"},
             {"status": "PROCESSED", "task_id": "c2"}], decisions,
            stage=True, admitted=True, max_jobs=2)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(len(out[1]), 2)
        self.assertEqual(out[2], 0)
        self.assertEqual(selected, ["root"])
        self.assertEqual(called, [
            ("worker", "c1"), ("review", 1), ("policy", "root"),
            ("worker", "c2"), ("review", 1)])

    def test_refused_preflight_never_invokes_review(self):
        out, called, _, reviews = self.run_case(
            [{"status": "PROCESSED", "task_id": "unrelated"}], [],
            stage=True, admitted=False, max_jobs=1)
        self.assertEqual(reviews, [])
        self.assertEqual(out[2], 1)
        self.assertEqual(called, [("worker", "unrelated")])

    def test_granted_stage_without_verified_receipt_does_not_replan(self):
        choices = [{"status": "NATIVE_METHOD_ENQUEUED",
                    "child_task_id": "json1", "root_task_id": "root",
                    "selected_objective": "ensure_structure"}]
        queue = iter([{"status": "NEEDS_REVIEW", "task_id": "json1"},
                      {"status": "IDLE"}])
        policy_calls = []
        output = drain_native_feedback(
            Path("ledger"), Path("work"), Path("fixtures"), max_jobs=2,
            planner_mode="deterministic", local_model=None,
            auto_native_cognition=True, auto_stage_goals=True,
            preflight={"admitted": True}, native_choices=choices,
            run_one=lambda *a, **k: next(queue),
            review_due=lambda *a, **k: [],
            advance_cognition=lambda *a, **k: policy_calls.append("model"))
        self.assertEqual(policy_calls, [])
        self.assertEqual(output[0][0]["task_id"], "json1")
        self.assertEqual(choices[-1]["status"],
                         "NATIVE_SANDBOX_EFFECT_AWAITING_VERIFICATION")

    def test_unrelated_stage_receipt_cannot_complete_json(self):
        choices = [{"status": "NATIVE_METHOD_ENQUEUED",
                    "child_task_id": "json1", "root_task_id": "root",
                    "selected_objective": "ensure_structure"}]
        queue = iter([{"status": "NEEDS_REVIEW", "task_id": "json1"},
                      {"status": "IDLE"}])
        policy_calls = []
        drain_native_feedback(
            Path("ledger"), Path("work"), Path("fixtures"), max_jobs=2,
            planner_mode="deterministic", local_model=None,
            auto_native_cognition=True, auto_stage_goals=True,
            preflight={"admitted": True}, native_choices=choices,
            run_one=lambda *a, **k: next(queue),
            review_due=lambda *a, **k: [
                {"task_id": "other", "status": "SANDBOX_VERIFIED"}],
            advance_cognition=lambda *a, **k: policy_calls.append("model"))
        self.assertEqual(policy_calls, [])
        self.assertEqual(choices[-1]["status"],
                         "NATIVE_SANDBOX_EFFECT_AWAITING_VERIFICATION")

    def test_budget_and_choice_validation(self):
        with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_FEEDBACK_BUDGET"):
            drain_native_feedback(
                Path("db"), Path("work"), Path("source"),
                max_jobs=0, planner_mode="deterministic", local_model=None,
                auto_native_cognition=False, auto_stage_goals=False,
                preflight=None, native_choices=[], run_one=lambda *a, **k: {},
                review_due=lambda *a, **k: [])
        with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_FEEDBACK_CHOICES"):
            drain_native_feedback(
                Path("db"), Path("work"), Path("source"),
                max_jobs=1, planner_mode="deterministic", local_model=None,
                auto_native_cognition=False, auto_stage_goals=False,
                preflight=None, native_choices=None, run_one=lambda *a, **k: {},
                review_due=lambda *a, **k: [])


if __name__ == "__main__":
    unittest.main()
