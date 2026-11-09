import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("native_summary", Path(__file__).resolve().parents[1]
                                            / "scripts/summarize_native_evidence.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class NativeEvidenceSummaryTests(unittest.TestCase):
    def test_reported_pass_is_not_verification_and_contradictions_remain_visible(self):
        for checks in ({}, {"real_write": False}, {"real_write": "true"}):
            row = summary.summarize({"status": "PASS", "checks": checks, "native_items": []},
                                    locator="receipt", digest="abc")
            self.assertEqual(row["interpretation"], "CONTRADICTORY_PASS")
            self.assertEqual(row["independent_verification"], "NOT_PERFORMED")
        row = summary.summarize({"status": "PASS", "checks": {"read": True}, "native_items": []},
                                locator="receipt", digest="abc")
        self.assertEqual(row["interpretation"], "REPORT_ONLY")

    def test_private_trace_excluded_and_cumulative_usage_not_summed(self):
        data = {"status": "FAIL", "checks": {"write": False}, "reply": "PRIVATE_REPLY",
                "native_token_usage": [2, 7, 15], "native_items": [
                    {"type": "reasoning", "text": "PRIVATE_REASONING"},
                    {"type": "mcpToolCall", "tool": "cognition_node_record", "status": "failed",
                     "arguments": {"text": "PRIVATE_GOAL"},
                     "result": {"text": "COGNITION_STALE_REVISION PRIVATE_PATH"}}]}
        row = summary.summarize(data, locator="receipt", digest="abc")
        self.assertNotIn("PRIVATE", json.dumps(row))
        self.assertEqual(row["native_total_tokens"], 15)
        self.assertEqual(row["error_codes"], {"COGNITION_STALE_REVISION": 1})

    def test_zip_members_keep_identity_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "both.zip"
            data = {"status": "FAIL", "native_items": []}
            with zipfile.ZipFile(path, "w") as archive:
                for prefix in ("linux", "windows"):
                    archive.writestr(prefix + "/native-execution-boundary.json", json.dumps(data))
            rows = list(summary.read_receipts(path))
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]["evidence"], rows[1]["evidence"])
            self.assertEqual(list(Path(tmp).iterdir()), [path])
            self.assertEqual(rows[0]["artifact_sha256"], rows[1]["artifact_sha256"])

    def test_unknown_json_not_accepted_as_evidence(self):
        with self.assertRaisesRegex(ValueError, "UNRECOGNIZED_NATIVE_RECEIPT"):
            summary.summarize({"status": "PASS"}, locator="receipt", digest="abc")
