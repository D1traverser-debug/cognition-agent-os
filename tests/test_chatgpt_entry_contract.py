"""Static guardrails for the multi-repository ChatGPT entry contract.

These tests check source configuration only. They do NOT simulate native
skill selection, ChatGPT account settings, repository authorization, or effects.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt/skills/cognition-parent-chatgpt-intake/SKILL.md"
PROBES = SKILL.parent / "references/scope-probes.md"
REPO_INSTRUCTIONS = ROOT / "AGENTS.md"


class ChatGPTCurrentEntryBoundary(unittest.TestCase):
    def test_single_parent_and_historical_bootstrap_boundary(self):
        content = SKILL.read_text(encoding="utf-8")
        self.assertIn("The ONE active cognitive parent", content)
        self.assertIn("D1traverser-debug/cognition-agent-os", content)
        self.assertIn("universal-agent-os@main", content)
        self.assertIn("never the present parent bootstrap", content)
        self.assertIn("domain-specific live compatibility documents", content)
        self.assertIn("not proof", content.lower())

    def test_dynamic_multirepo_routing_without_pinned_pr(self):
        content = SKILL.read_text(encoding="utf-8")
        self.assertIn("A bare `继承`", content)
        self.assertIn("`继承视频`", content)
        self.assertIn("show a compact evidence-backed choice", content)
        self.assertIn("connected GitHub repository list/search", content)
        self.assertIn("ordinary engineering/code repository", content)
        self.assertIn("current relevant unclosed integration candidate", content)
        self.assertIn("same", content.lower())
        self.assertNotRegex(content, r"(?i)(?:PR\s*#|pull/)(?:\d+)")
        self.assertIn("separate current grants", content)

    def test_legacy_migration_not_accidentally_deleted(self):
        content = REPO_INSTRUCTIONS.read_text(encoding="utf-8")
        self.assertIn("Existing child repositories still name UAOS", content)
        self.assertIn("explicit cutover approval", content)
        self.assertIn("not a new permanent superior", content)

    def test_route_falsifiers_remain_in_scope_probes(self):
        content = PROBES.read_text(encoding="utf-8")
        for title in ("M. Legacy-entry collision:", "N. Bare new-chat inherit:",
                      "O. Direct child resume:", "P. Newly discovered project:"):
            self.assertIn(title, content)
        self.assertIn("Native first-call observability", content)


if __name__ == "__main__":
    unittest.main()
