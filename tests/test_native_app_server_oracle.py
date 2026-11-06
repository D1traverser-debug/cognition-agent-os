"""Negative neighbors for the independent native-seam oracle; no model run."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from measure_native_app_server import judge


class NativeSeamOracleTests(unittest.TestCase):
    def test_success_requires_actual_tool_result_usage_and_preserved_state(self):
        case = dict(marker="random-marker", original="original", final_original="original",
                    reply="random-marker READ_ONLY", usage=73,
                    result={"status": "CLIENT_TURN_COMPLETED"},
                    before_workspace={}, after_workspace={}, before_tasks=["root"], after_tasks=["root"],
                    items=[{"type": "mcpToolCall", "server": "caos",
                            "tool": "cognition_session_inspect", "status": "completed",
                            "result": {"original": "random-marker"}}])
        good = judge(**case)
        self.assertEqual(good["status"], "PASS")
        self.assertFalse(good["product_ready"])
        for change in ({"items": []}, {"usage": 0}, {"reply": "invented READ_ONLY"},
                       {"reply": "random-marker"}, {"final_original": "changed"},
                       {"after_workspace": {"output": "hash"}}, {"after_tasks": ["root", "child"]},
                       {"result": {"status": "CLIENT_TURN_FAILED"}}):
            with self.subTest(change=change):
                self.assertEqual(judge(**(case | change))["status"], "FAIL")
        for mutation in ({"status": "failed"}, {"server": "other"}, {"result": {}},
                         {"error": {"message": "rejected"}}):
            changed = copy.deepcopy(case)
            changed["items"][0].update(mutation)
            self.assertEqual(judge(**changed)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
