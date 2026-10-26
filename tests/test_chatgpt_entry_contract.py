"""Static guardrails for the multi-repository ChatGPT entry contract.

These tests check source configuration only. They do NOT simulate native
skill selection, ChatGPT account settings, repository authorization, or effects.
"""
from pathlib import Path
import unittest
import json

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
        self.assertIn("Q. Interrupted work / mid-task user question / connection loss:", content)
        self.assertIn("real ChatGPT conversation", content)
        self.assertIn("Fail if user must repeat", content)

    def test_discovery_description_is_scoped_not_an_everyday_chat_hijack(self):
        """Source-only metadata contract; native implicit trigger is untested."""
        content = SKILL.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        self.assertEqual(len(parts), 3)
        header = parts[1]
        description = next((line.partition(":")[2].strip()
                            for line in header.splitlines()
                            if line.startswith("description:")), "")
        self.assertTrue(0 < len(description) <= 1024)
        self.assertIn("cognition-agent-os", description)
        self.assertIn("继承", description)
        self.assertIn("cross-domain", description)
        self.assertIn("Do not use for unrelated ordinary requests", description)
        self.assertIn("Do not assume", description)

    def test_nonexpert_owner_intake_has_outcome_first_evidence_contract(self):
        """The expert-research burden belongs to the agent, not the owner."""
        content = SKILL.read_text(encoding="utf-8")
        self.assertIn("## Outcome-first input/output contract", content)
        self.assertIn("No owner domain or AI expertise is presumed", content)
        self.assertIn("independent owner-level postcondition", content)
        self.assertIn("do not invent missing source facts", content)
        self.assertIn("ask the owner only for indispensable", content.lower())
        self.assertIn("No mandatory report format", content)

    def test_trigger_holdouts_include_positive_and_negative_controls(self):
        probes = PROBES.read_text(encoding="utf-8")
        self.assertIn("R. In-scope skill selection versus ordinary-chat non-trigger:", probes)
        self.assertIn("S. Nonexpert original-owner task input/output:", probes)
        self.assertIn("false-positive trigger", probes)
        self.assertIn("false-negative trigger", probes)
        self.assertIn("without an invoked skill", probes)

    def test_private_plugin_version_and_no_false_runtime_claim(self):
        root = ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt"
        manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.1.2")
        self.assertIn("Does not itself connect a custom Host API", manifest["description"])
        self.assertIn("not proof", SKILL.read_text(encoding="utf-8").lower())



if __name__ == "__main__":
    unittest.main()
