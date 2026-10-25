"""Static protection of the cognition-agent-os first-mile source boundary.

This is NOT a native ChatGPT invocation test. It prevents accidental
re-introduction of historical UAOS as the new product's live bootstrap.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt/skills/cognition-parent-chatgpt-intake/SKILL.md"
PROBES = SKILL.parent / "references/scope-probes.md"
REPO_INSTRUCTIONS = ROOT / "AGENTS.md"


class ChatGPTCurrentEntryBoundary(unittest.TestCase):
    def test_current_parent_not_bootstrapped_from_historical_uaos(self):
        content = SKILL.read_text(encoding="utf-8")
        self.assertIn("Canonical entry: cognition-agent-os, not historical UAOS", content)
        self.assertIn("D1traverser-debug/cognition-agent-os", content)
        self.assertIn("Do **not** bootstrap from", content)
        self.assertIn("universal-agent-os@main", content)
        self.assertIn("configuration conflict", content)
        self.assertIn("not proof of native ChatGPT pre-tool interception", content)
        self.assertIn("NOT_VERIFIED", content)

    def test_legacy_migration_not_accidentally_deleted(self):
        content = REPO_INSTRUCTIONS.read_text(encoding="utf-8")
        self.assertIn("Existing child repositories still name UAOS", content)
        self.assertIn("explicit cutover approval", content)
        self.assertIn("not a new permanent superior", content)

    def test_live_conflict_counterexample_remains_in_scope_probes(self):
        content = PROBES.read_text(encoding="utf-8")
        self.assertIn("M. Legacy-entry collision:", content)
        self.assertIn("do not take old UAOS status as live task authority", content)
        self.assertIn("Native first-call observability", content)


if __name__ == "__main__":
    unittest.main()
