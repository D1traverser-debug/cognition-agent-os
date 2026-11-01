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
        def worker(*args, **kwargs):
            event = queue.pop(0) if queue else {"status": "IDLE"}
            called.append(("worker", event.get("task_id")))
            return event
        def review(*args, **kwargs):
            called.append(("review", kwargs.get("max_reviews")))
            reviews.append({"verified": True})
            return [{"verified": True}]
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
