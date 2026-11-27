"""Cross-surface Skill entrypoint budget, inventory and package-closure tests."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/skill_package_policy.json"
VERIFIER_PATH = ROOT / "scripts/verify_skill_package.py"

spec = importlib.util.spec_from_file_location("verify_skill_package", VERIFIER_PATH)
verifier = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(verifier)


class SkillPackageContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_all_active_entrypoints_are_inventoried_and_within_operational_budget(self):
        report = verifier.audit_skill_package(ROOT, self.policy)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(
            {item["path"] for item in report["entrypoints"]},
            {item["path"] for item in self.policy["entrypoints"]},
        )
        self.assertEqual(len(report["entrypoints"]), 2)
        self.assertTrue(all(
            item["utf8_bytes"] <= self.policy["operational_entrypoint_budget_bytes"]
            for item in report["entrypoints"]
        ), report["entrypoints"])

    def test_shared_budget_preserves_platform_headroom(self):
        self.assertEqual(self.policy["platform_entrypoint_limit_bytes"], 12000)
        self.assertEqual(self.policy["operational_entrypoint_budget_bytes"], 10500)
        self.assertEqual(self.policy["preferred_entrypoint_budget_bytes"], 9000)
        self.assertEqual(
            self.policy["platform_entrypoint_limit_bytes"]
            - self.policy["operational_entrypoint_budget_bytes"],
            1500,
        )

    def test_child_policy_must_scan_repository_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config/skill_package_policy.json"
            config.parent.mkdir(parents=True)
            narrowed = dict(self.policy)
            narrowed["scan_roots"] = [".agents/skills"]
            config.write_text(json.dumps(narrowed), encoding="utf-8")
            with self.assertRaises(verifier.SkillPackageError):
                verifier.load_policy(root, "config/skill_package_policy.json")

    def test_utf8_bytes_not_character_count_control_the_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills/demo/SKILL.md"
            skill.parent.mkdir(parents=True)
            content = "---\nname: demo\ndescription: test\n---\n" + ("中" * 80)
            skill.write_text(content, encoding="utf-8")
            policy = {
                "policy_version": "1.0.0",
                "contract": "CAOS_SKILL_PACKAGE_BUDGET",
                "platform_entrypoint_limit_bytes": 12000,
                "operational_entrypoint_budget_bytes": 100,
                "preferred_entrypoint_budget_bytes": 80,
                "reference_module_limit_bytes": 32768,
                "package_uncompressed_limit_bytes": 131072,
                "max_description_characters": 400,
                "scan_roots": ["skills"],
                "excluded_directory_names": ["archive"],
                "entrypoints": [{
                    "id": "demo", "path": "skills/demo/SKILL.md",
                    "references": [], "package_id": None,
                }],
                "packages": [],
            }
            self.assertLess(len(content), 12000)
            self.assertGreater(len(content.encode("utf-8")), 100)
            report = verifier.audit_skill_package(root, policy)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("UTF-8 bytes exceeds operational budget" in e
                                for e in report["errors"]), report["errors"])

    def test_crlf_checkout_uses_same_canonical_utf8_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills/demo/SKILL.md"
            skill.parent.mkdir(parents=True)
            lf = "---\nname: demo\ndescription: test\n---\nbody\n"
            skill.write_bytes(lf.replace("\n", "\r\n").encode("utf-8"))
            policy = {
                "policy_version": "1.0.0",
                "contract": "CAOS_SKILL_PACKAGE_BUDGET",
                "platform_entrypoint_limit_bytes": 12000,
                "operational_entrypoint_budget_bytes": 10500,
                "preferred_entrypoint_budget_bytes": 9000,
                "reference_module_limit_bytes": 32768,
                "package_uncompressed_limit_bytes": 131072,
                "max_description_characters": 400,
                "scan_roots": ["skills"],
                "excluded_directory_names": ["archive"],
                "entrypoints": [{
                    "id": "demo", "path": "skills/demo/SKILL.md",
                    "references": [], "package_id": None,
                }],
                "packages": [],
            }
            report = verifier.audit_skill_package(root, policy)
            self.assertEqual(report["status"], "PASS", report["errors"])
            self.assertEqual(report["entrypoints"][0]["utf8_bytes"],
                             len(lf.encode("utf-8")))

    def test_child_policy_cannot_relax_shared_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config/skill_package_policy.json"
            config.parent.mkdir(parents=True)
            relaxed = dict(self.policy)
            relaxed["operational_entrypoint_budget_bytes"] = 11999
            config.write_text(json.dumps(relaxed), encoding="utf-8")
            with self.assertRaises(verifier.SkillPackageError):
                verifier.load_policy(root, "config/skill_package_policy.json")

    def test_unregistered_active_skill_fails_but_archived_skill_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registered = root / ".agents/skills/known/SKILL.md"
            registered.parent.mkdir(parents=True)
            registered.write_text(
                "---\nname: known\ndescription: known\n---\nbody\n",
                encoding="utf-8",
            )
            extra = root / ".agents/skills/unregistered/SKILL.md"
            extra.parent.mkdir(parents=True)
            extra.write_text(
                "---\nname: extra\ndescription: extra\n---\nbody\n",
                encoding="utf-8",
            )
            archived = root / ".agents/skills/archive/old/SKILL.md"
            archived.parent.mkdir(parents=True)
            archived.write_text(
                "---\nname: old\ndescription: old\n---\nbody\n",
                encoding="utf-8",
            )
            policy = {
                "policy_version": "1.0.0",
                "contract": "CAOS_SKILL_PACKAGE_BUDGET",
                "platform_entrypoint_limit_bytes": 12000,
                "operational_entrypoint_budget_bytes": 10500,
                "preferred_entrypoint_budget_bytes": 9000,
                "reference_module_limit_bytes": 32768,
                "package_uncompressed_limit_bytes": 131072,
                "max_description_characters": 400,
                "scan_roots": ["."],
                "excluded_directory_names": ["archive"],
                "entrypoints": [{
                    "id": "known", "path": ".agents/skills/known/SKILL.md",
                    "references": [], "package_id": None,
                }],
                "packages": [],
            }
            report = verifier.audit_skill_package(root, policy)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("unregistered active SKILL.md" in e
                                for e in report["errors"]), report["errors"])
            self.assertFalse(any("archive/old" in e for e in report["errors"]))

    def test_missing_declared_reference_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills/demo/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: demo\ndescription: test\n---\nbody\n",
                encoding="utf-8",
            )
            policy = {
                "policy_version": "1.0.0",
                "contract": "CAOS_SKILL_PACKAGE_BUDGET",
                "platform_entrypoint_limit_bytes": 12000,
                "operational_entrypoint_budget_bytes": 10500,
                "preferred_entrypoint_budget_bytes": 9000,
                "reference_module_limit_bytes": 32768,
                "package_uncompressed_limit_bytes": 131072,
                "max_description_characters": 400,
                "scan_roots": ["skills"],
                "excluded_directory_names": ["archive"],
                "entrypoints": [{
                    "id": "demo", "path": "skills/demo/SKILL.md",
                    "references": ["skills/demo/references/missing.md"],
                    "package_id": None,
                }],
                "packages": [],
            }
            report = verifier.audit_skill_package(root, policy)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("declared reference does not exist" in e
                                for e in report["errors"]), report["errors"])

    def test_broken_unregistered_local_markdown_link_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills/demo/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: demo\ndescription: test\n---\n[missing](references/missing.md)\n",
                encoding="utf-8",
            )
            policy = {
                "policy_version": "1.0.0",
                "contract": "CAOS_SKILL_PACKAGE_BUDGET",
                "platform_entrypoint_limit_bytes": 12000,
                "operational_entrypoint_budget_bytes": 10500,
                "preferred_entrypoint_budget_bytes": 9000,
                "reference_module_limit_bytes": 32768,
                "package_uncompressed_limit_bytes": 131072,
                "max_description_characters": 400,
                "scan_roots": ["skills"],
                "excluded_directory_names": ["archive"],
                "entrypoints": [{
                    "id": "demo", "path": "skills/demo/SKILL.md",
                    "references": [], "package_id": None,
                }],
                "packages": [],
            }
            report = verifier.audit_skill_package(root, policy)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("broken local Markdown link" in e
                                for e in report["errors"]), report["errors"])

    def test_reference_modules_are_not_misclassified_as_skill_entrypoints(self):
        report = verifier.audit_skill_package(ROOT, self.policy)
        self.assertEqual(report["status"], "PASS", report["errors"])
        references = {item["path"]: item["utf8_bytes"] for item in report["references"]}
        self.assertGreater(
            references["integrations/chatgpt/cognition-agent-os-chatgpt/"
                       "skills/cognition-parent-chatgpt-intake/references/parent-protocol.md"],
            12000,
        )
        self.assertLessEqual(
            max(references.values()), self.policy["reference_module_limit_bytes"]
        )

    def test_progressive_disclosure_preserves_semantic_guardrails(self):
        skill = (ROOT / ".agents/skills/goal-grounded-semantic-review/SKILL.md").read_text(
            encoding="utf-8"
        )
        research = (ROOT / ".agents/skills/goal-grounded-semantic-review/references/"
                    "research-method-selection.md").read_text(encoding="utf-8")
        verification = (ROOT / ".agents/skills/goal-grounded-semantic-review/references/"
                        "recursive-verification.md").read_text(encoding="utf-8")
        for token in (
            "Multiple faults remain separate obligations until disproved",
            "Start at the original source",
            "Minimum decision and evidence contract",
            "research-method-selection.md",
            "recursive-verification.md",
            "UNVERIFIED_ORIGINAL_SOURCE",
        ):
            self.assertIn(token, skill)
        for token in (
            "source-discovery funnel",
            "Ask four expert questions",
            "Decompose and trace requirements",
            "Decide the correct root-cause intervention",
            "Agent-Learning-Hub",
            "Filesystem MCP",
            "Sequential Thinking",
            "Memory MCP",
            "independent falsification",
        ):
            self.assertIn(token.lower(), research.lower())
        for token in (
            "Evidence-driven recursive challenge",
            "Verify before claiming completion",
            "Output discipline",
            "Empirical Skill evaluation",
            "resource limit is not an epistemic stopping criterion",
            "NOT_TESTED",
        ):
            self.assertIn(token, verification)

    def test_live_chatgpt_package_retains_file_crud_governance_and_versions(self):
        root = ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt"
        skill = (root / "skills/cognition-parent-chatgpt-intake/SKILL.md").read_text(encoding="utf-8")
        protocol = (root / "skills/cognition-parent-chatgpt-intake/references/parent-protocol.md").read_text(encoding="utf-8")
        for token in ("## Files and knowledge CRUD", "CAOS_OPERATING_MANUAL.md", "NO_OP",
                      "independent provider readback", "parent-protocol.md"):
            self.assertIn(token, skill)
        for token in ("Source lifecycle at the real retrieval/write boundary",
                      "privacy deletion", "get_plugin_metadata", "expected_release_id"):
            self.assertIn(token, protocol)
        self.assertIn("SOURCE_LIFECYCLE_CONFLICT", skill)
        plugin = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], codex["name"])
        self.assertEqual(plugin["version"], codex["version"])
        self.assertLess(len(skill.encode("utf-8")), 9000)

    def test_package_build_detects_post_audit_source_drift(self):
        """A clean old report cannot certify changed Skill or reference bytes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills/demo/SKILL.md"
            reference = root / "skills/demo/references/method.md"
            reference.parent.mkdir(parents=True)
            original_skill = (
                "---\nname: demo\ndescription: test\n---\n"
                "[method](references/method.md)\n"
            )
            skill.write_text(original_skill, encoding="utf-8")
            reference.write_text("version-one\n", encoding="utf-8")
            policy = {
                "policy_version": "1.0.0",
                "contract": "CAOS_SKILL_PACKAGE_BUDGET",
                "platform_entrypoint_limit_bytes": 12000,
                "operational_entrypoint_budget_bytes": 10500,
                "preferred_entrypoint_budget_bytes": 9000,
                "reference_module_limit_bytes": 32768,
                "package_uncompressed_limit_bytes": 131072,
                "max_description_characters": 400,
                "scan_roots": ["."],
                "excluded_directory_names": ["archive"],
                "entrypoints": [{
                    "id": "demo", "path": "skills/demo/SKILL.md",
                    "references": ["skills/demo/references/method.md"],
                    "package_id": "demo",
                }],
                "packages": [{
                    "id": "demo", "root": ".",
                    "paths": ["skills/demo/SKILL.md",
                              "skills/demo/references/method.md"],
                }],
            }
            report = verifier.audit_skill_package(root, policy)
            self.assertEqual(report["status"], "PASS", report["errors"])
            output = root / "bundle.zip"

            # Same byte count, different meaning: size-only checks miss this.
            skill.write_text(original_skill.replace("name: demo", "name: deMo"),
                             encoding="utf-8")
            with self.assertRaises(verifier.SkillPackageError):
                verifier.build_package(root, policy, report, "demo", output)
            self.assertFalse(output.exists())

            skill.write_text(original_skill, encoding="utf-8")
            reference.write_text("version-two\n", encoding="utf-8")
            with self.assertRaises(verifier.SkillPackageError):
                verifier.build_package(root, policy, report, "demo", output)
            self.assertFalse(output.exists())

            reference.write_text("version-one\n", encoding="utf-8")
            skill.write_text(original_skill + "中" * 4000, encoding="utf-8")
            with self.assertRaises(verifier.SkillPackageError):
                verifier.build_package(root, policy, report, "demo", output)
            self.assertFalse(output.exists())

            skill.write_text(original_skill, encoding="utf-8")
            built = verifier.build_package(root, policy, report, "demo", output)
            self.assertEqual(built["readback"],
                             "PASS_EXACT_MEMBERSHIP_AND_BYTES")
            published = output.read_bytes()

            # Publishing must be transactional: an injected ZIP write failure
            # must leave the previous validated output intact.
            with patch.object(zipfile.ZipFile, "writestr",
                              side_effect=OSError("INJECTED_ZIP_WRITE_FAILURE")):
                with self.assertRaisesRegex(OSError, "INJECTED_ZIP_WRITE_FAILURE"):
                    verifier.build_package(root, policy, report, "demo", output)
            self.assertEqual(output.read_bytes(), published)
            self.assertEqual(list(root.glob(".bundle.zip.*.tmp")), [])

            # Never permit the package output path to overwrite its source.
            with self.assertRaises(verifier.SkillPackageError):
                verifier.build_package(root, policy, report, "demo", skill)
            self.assertEqual(skill.read_text(encoding="utf-8"), original_skill)

    def test_native_plugin_package_builds_and_reads_back_exact_declared_files(self):
        report = verifier.audit_skill_package(ROOT, self.policy)
        self.assertEqual(report["status"], "PASS", report["errors"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "overlay.zip"
            built = verifier.build_package(
                ROOT, self.policy, report, "chatgpt-native-overlay", output
            )
            self.assertEqual(built["readback"], "PASS_EXACT_MEMBERSHIP_AND_BYTES")
            package = self.policy["packages"][0]
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), package["paths"])
                for member in package["paths"]:
                    expected = (ROOT / package["root"] / member).read_bytes()
                    self.assertEqual(archive.read(member), expected)

    def test_reusable_action_invokes_the_single_repository_verifier(self):
        action = (ROOT / "integrations/github-actions/skill-package-budget/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("GITHUB_ACTION_PATH/../../../scripts/verify_skill_package.py", action)
        self.assertIn("policy-path", action)
        self.assertIn("package-id", action)


    def test_explicit_system_building_entry_does_not_misroute_to_caos_repo(self):
        skill_path = (
            ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt/skills/"
            "cognition-parent-chatgpt-intake/SKILL.md"
        )
        skill = skill_path.read_text(encoding="utf-8")
        description = next(
            line[len("description: "):]
            for line in skill.splitlines()
            if line.startswith("description: ")
        )
        self.assertIn("architect, build, improve, or evolve a reusable task system", description)
        self.assertIn("Do not trigger for generic conceptual questions", description)
        self.assertIn("ordinary one-off tasks", description)
        self.assertIn("do not route the work into modifying the cognition-agent-os repository", skill)
        manifest = json.loads((
            ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt/plugin.json"
        ).read_text(encoding="utf-8"))
        ui = manifest["extensions"]["com.openai"]["interface"]
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn("用户要求构建其他系统时，不得误改 cognition-agent-os 本身", ui["defaultPrompt"])
        self.assertNotIn("继续 cognition-agent-os", ui["defaultPrompt"])
        codex_manifest = json.loads((
            ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt/.codex-plugin/plugin.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(codex_manifest["version"], manifest["version"])
        self.assertEqual(codex_manifest["description"], manifest["description"])
        self.assertEqual(codex_manifest["interface"]["defaultPrompt"], ui["defaultPrompt"])
        self.assertEqual(codex_manifest["interface"]["longDescription"], ui["longDescription"])

if __name__ == "__main__":
    unittest.main()
