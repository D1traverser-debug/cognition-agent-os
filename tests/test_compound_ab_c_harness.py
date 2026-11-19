"""Offline policy tests for the optional A/B/C MCP architecture screen."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_compound_ab_c as harness


class CompoundAbcHarnessTests(unittest.TestCase):
    def test_sdk_allowlist_exposes_only_scoped_native_tools(self):
        self.assertEqual(set(harness.SDK_TOOL_ALLOWLIST), {
            "native_goal_inspect",
            "native_procedure_evidence",
            "native_capabilities",
            "native_source_read",
            "native_decision_admit",
        })
        self.assertEqual(harness.HARNESS_EXECUTION_TOOL, "native_local_tick")
        self.assertNotIn(harness.HARNESS_EXECUTION_TOOL, harness.SDK_TOOL_ALLOWLIST)
        for forbidden in (
            "native_goal_create",
            "native_local_tick",
            "native_owner_outcome",
            "native_local_model_plan",
            "native_memory_candidate_record",
            "native_public_primary_source_read",
            "cognition_shell",
        ):
            self.assertNotIn(forbidden, harness.SDK_TOOL_ALLOWLIST)

    def test_agents_sdk_provider_is_loopback_only(self):
        self.assertEqual(
            harness.local_openai_base_url("127.0.0.1:11434"),
            "http://127.0.0.1:11434/v1")
        self.assertEqual(
            harness.local_openai_base_url("http://localhost:11434/"),
            "http://localhost:11434/v1")
        for remote in (
            "https://api.openai.com/v1",
            "http://192.0.2.10:11434",
            "http://127.0.0.1:11434/proxy",
        ):
            with self.subTest(remote=remote), self.assertRaisesRegex(
                    ValueError, "LOOPBACK_HTTP"):
                harness.local_openai_base_url(remote)

    def test_independent_contract_pins_exact_goal_and_all_source_bytes(self):
        source_hashes = {
            "baseline.csv": hashlib.sha256(b"baseline").hexdigest(),
            "actual.csv": hashlib.sha256(b"actual").hexdigest(),
            "settings.json": hashlib.sha256(b"settings").hexdigest(),
        }
        contract = harness.build_contract(harness.OWNER_GOAL, source_hashes)
        self.assertEqual(
            contract["owner_goal_sha256"],
            hashlib.sha256(harness.OWNER_GOAL.encode("utf-8")).hexdigest())
        self.assertEqual(contract["source_sha256"], source_hashes)
        self.assertEqual(contract["allowed_effect"], "LOCAL_CANDIDATES_ONLY")
        with self.assertRaisesRegex(ValueError, "SOURCE_MANIFEST_MISMATCH"):
            harness.build_contract(harness.OWNER_GOAL, {
                "baseline.csv": source_hashes["baseline.csv"]})


if __name__ == "__main__":
    unittest.main()
