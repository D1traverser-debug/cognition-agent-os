"""The engineering aggregator must preserve failures rather than print PASS."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("delivery_receipt", Path(__file__).resolve().parents[1] / "scripts/verify_delivery.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class DeliveryReceipt(unittest.TestCase):
    def test_nonzero_exit_and_raw_evidence_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = delivery.run_check("failure", [sys.executable, "-c", "print('independent failure'); raise SystemExit(7)"], Path(tmp), os.environ.copy())
            self.assertEqual((row["status"], row["exit_code"]), ("FAIL", 7))
            self.assertIn("independent failure", Path(row["log"]).read_text())
            self.assertEqual(len(row["log_sha256"]), 64)

    def test_timeout_is_not_a_successful_or_missing_check(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(delivery.subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 600)):
            row = delivery.run_check("timeout", ["probe"], Path(tmp), os.environ.copy())
            self.assertEqual((row["status"], row["exit_code"]), ("FAIL", 124))

    def test_missing_interpreter_fails_without_fabricating_test_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = delivery.run_check("missing", [str(Path(tmp) / "absent-python")], Path(tmp), os.environ.copy())
            self.assertEqual((row["status"], row["exit_code"]), ("FAIL", 127))
