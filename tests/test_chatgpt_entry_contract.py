"""Source/package contracts only.

These tests never claim native Skill selection, actual ChatGPT loading, method
comparison, correct cross-chat recovery or owner-level effect. Those require
captured first-party client runs and independent outcome traces.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt"
SKILL = BASE / "skills/cognition-parent-chatgpt-intake/SKILL.md"
PROBES = SKILL.parent / "references/scope-probes.md"
CODEX_SKILL = ROOT / ".agents/skills/goal-grounded-semantic-review/SKILL.md"
AGENTS = ROOT / "AGENTS.md"


def metadata(source):
    assert source.startswith("---\n")
    parts = source.split("---", 2)
    return {
        line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in parts[1].splitlines()
        if ":" in line
    }


class ChatGPTSourceBoundaries(unittest.TestCase):
    def test_plugin_version_is_semantic_and_candidate_is_not_installed_truth(self):
        manifest = json.loads((BASE / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "cognition-agent-os-chatgpt")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn("Does not itself connect a custom Host API",
                      manifest["description"])
        self.assertIn("not", SKILL.read_text(encoding="utf-8").lower())

    def test_triggers_are_scoped_and_body_is_on_demand(self):
        content = SKILL.read_text(encoding="utf-8")
        desc = metadata(content)["description"]
        self.assertIn("cognition-agent-os", desc)
        self.assertIn("继承", desc)
        self.assertIn("unrelated", desc.lower())
        self.assertLess(len(desc), 400)
        self.assertIn("references/scope-probes.md", content)
        self.assertTrue(PROBES.is_file())
        self.assertNotRegex(content, r"(?i)(?:PR\s*#|pull/)(?:\d+)")
        # Metadata is discoverable; this test does not run ChatGPT.
        self.assertIn("not", content.lower())

    def test_current_parent_and_child_permission_boundary(self):
        chatgpt = SKILL.read_text(encoding="utf-8")
        codex = AGENTS.read_text(encoding="utf-8")
        for content in (chatgpt, codex):
            self.assertIn("cognition-agent-os", content)
            self.assertIn("universal-agent-os", content)
            self.assertRegex(content.lower(), r"child.{0,300}(?:grant|permission|native)")
            self.assertNotIn("UAOS is the active parent", content)
        self.assertIn("SESSION_HANDOFF.md", chatgpt)
        self.assertIn("SESSION_HANDOFF.md", codex)
        self.assertTrue(CODEX_SKILL.is_file())

    def test_each_surface_is_a_distinct_loading_boundary(self):
        chatgpt = SKILL.read_text(encoding="utf-8").lower()
        codex = AGENTS.read_text(encoding="utf-8").lower()
        self.assertIn("installed account", chatgpt)
        self.assertIn("codex", codex)
        self.assertIn("host", chatgpt)
        self.assertIn("sqlite", codex)
        self.assertIn(".agents/skills/goal-grounded-semantic-review/skill.md",
                      codex)

    def test_evaluation_cases_not_default_loaded(self):
        probes = PROBES.read_text(encoding="utf-8")
        for title in ("M. Legacy-entry collision:", "N. Bare new-chat inherit:",
                      "O. Direct child resume:", "P. Newly discovered project:",
                      "Q. Interrupted work / mid-task user question / connection loss:",
                      "R. In-scope skill selection versus ordinary-chat non-trigger:",
                      "S. Nonexpert original-owner task input/output:"):
            self.assertIn(title, probes)
        self.assertIn("false-positive trigger", probes)
        self.assertIn("false-negative trigger", probes)
        self.assertIn("real ChatGPT conversation", probes)
        self.assertIn("Load", SKILL.read_text(encoding="utf-8"))

    def test_plugin_bundle_tracks_source_version_not_frozen_prose(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8")
        self.assertIn("chatgpt_plugin_release_bundle:", workflow)
        self.assertIn("[bundle-chatgpt-plugin]", workflow)
        self.assertIn("manifest['version']", workflow)
        self.assertNotIn("manifest['version'] == '0.1.3'", workflow)
        self.assertIn("No installation or owner account mutation occurs in CI",
                      workflow)
        self.assertIn("'skills/cognition-parent-chatgpt-intake/SKILL.md'",
                      workflow)


if __name__ == "__main__":
    unittest.main()
