"""Safe, bounded feedback for native MCP decision-schema rejection."""
from __future__ import annotations

import unittest

from cognition_agent_os.native_mcp_bridge import _TOOL_REJECTIONS


class NativeMcpDecisionRejectionFeedbackTests(unittest.TestCase):
    def test_mcp_cas_and_comparison_feedback_is_actionable_without_bypass(self):
        cases = {
            "MISSING_DECISION_COMPARISON": (
                "alternative_reason",
                "even when alternative_intent is null",
                "non-empty strings",
                "must never be null",
            ),
            "INVALID_OBSERVATION_FINGERPRINT": (
                "bridge-bound observation",
                "64-character lowercase SHA-256",
                "native_goal_inspect",
                "do not add an observation_sha256 field",
            ),
            "NATIVE_DECISION_REQUIRES_FRESH_INSPECTION": (
                "native_goal_inspect",
                "native_procedure_evidence",
                "restarted process",
            ),
            "NATIVE_PROCEDURE_EVIDENCE_NOT_READ": (
                "native_procedure_evidence",
                "bridge binds",
            ),
            "NATIVE_STALE_OBSERVATION": (
                "snapshot changed",
                "re-read",
                "reconsider",
            ),
        }
        for code, required in cases.items():
            message = _TOOL_REJECTIONS[code]
            for fragment in required:
                with self.subTest(code=code, fragment=fragment):
                    self.assertIn(fragment.lower(), message.lower())
            for forbidden in (
                "bypass", "disable validation", "force admission", "grant write",
            ):
                with self.subTest(code=code, forbidden=forbidden):
                    self.assertNotIn(forbidden, message.lower())

    def test_ungrounded_decision_rejection_explains_exact_schema_without_bypass(self):
        message = _TOOL_REJECTIONS["UNSUPPORTED_UNGROUNDED_DECISION"]
        for required in (
            "Do not tick",
            "selected_intent",
            "alternative_intent",
            "decision_reason",
            "alternative_reason",
            "expected_evidence",
            "decision_basis",
            "Only alternative_intent may be null",
            "Do NOT include observation_sha256",
            "previous_result_task_id",
            "decision_review_version",
            "decision_reviews",
            "LIST of objects",
            "exactly path and sha256",
            "For a first decision, omit both review fields",
            "Do not add authority",
            "re-read",
        ):
            with self.subTest(required=required):
                self.assertIn(required, message)
        for forbidden in (
            "bypass",
            "disable validation",
            "force admission",
            "grant write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, message.lower())


if __name__ == "__main__":
    unittest.main()
