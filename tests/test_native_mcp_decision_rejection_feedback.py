"""Safe, bounded feedback for native MCP decision-schema rejection."""
from __future__ import annotations

import unittest

from cognition_agent_os.native_mcp_bridge import _TOOL_REJECTIONS


class NativeMcpDecisionRejectionFeedbackTests(unittest.TestCase):
    def test_ungrounded_decision_rejection_explains_exact_schema_without_bypass(self):
        message = _TOOL_REJECTIONS["UNSUPPORTED_UNGROUNDED_DECISION"]
        for required in (
            "Do not tick",
            "selected_intent",
            "alternative_intent",
            "decision_reason",
            "alternative_reason",
            "expected_evidence",
            "observation_sha256",
            "decision_basis",
            "decision_review_version",
            "decision_reviews",
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
