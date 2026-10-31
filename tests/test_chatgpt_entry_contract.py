"""Source/package contracts only.

These tests never claim native Skill selection, actual ChatGPT loading, method
comparison, correct cross-chat recovery or owner-level effect. Those require
captured first-party client runs and independent outcome traces.
"""
import io
import json
from pathlib import Path
import re
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "integrations/chatgpt/cognition-agent-os-chatgpt"
SKILL = BASE / "skills/cognition-parent-chatgpt-intake/SKILL.md"
PROBES = SKILL.parent / "references/scope-probes.md"
PROTOCOL = SKILL.parent / "references/parent-protocol.md"
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


def complete_policy():
    return SKILL.read_text(encoding='utf-8') + '\n' + PROTOCOL.read_text(encoding='utf-8')


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

    def test_unnamed_in_scope_continuation_is_discoverable_at_metadata_boundary(self):
        """Only tests metadata/spec coverage; not native client selection."""
        body = SKILL.read_text(encoding="utf-8")
        meta = metadata(body)
        desc = meta["description"]
        self.assertLess(len(desc), 400)
        for topic in ("主支分支", "知识库", "跨对话继承", "长上下文",
                      "记忆架构", "loop/graph/skills/harness/RSI",
                      "轮询质疑", "增删改查", "合并清理"):
            self.assertIn(topic, desc)
        self.assertIn("without its name", desc)
        self.assertIn("never for unrelated", desc)
        self.assertIn("Unlabeled but still in-scope follow-ups", body)
        self.assertIn("do not guess the named repo", body)
        self.assertIn("X. Named-project-free architecture continuation", 
                      PROBES.read_text(encoding="utf-8"))
        self.assertIn("NOT_TESTED", PROBES.read_text(encoding="utf-8"))

    def test_ordinary_chat_is_the_required_parent_entry_surface(self):
        """Regression for wrong Project-only architecture; static candidate only."""
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("Ordinary new chats are the required entry surface", skill)
        self.assertIn("OUTSIDE ChatGPT Projects", skill)
        self.assertIn("Project instructions are not an account-wide trigger", skill)
        self.assertIn("account Custom Instructions", skill)
        self.assertIn("allow_implicit_invocation: true", skill)
        self.assertIn("No tool here is authorized/capable", skill)
        self.assertIn("Root-before-leaves dependency gate", skill)
        self.assertLess(skill.index("Root-before-leaves dependency gate"),
                        skill.index("## Work on the problem, not the instructions"))
        self.assertIn("ordinary new ChatGPT chat", PROBES.read_text(encoding="utf-8"))

    def test_first_mile_parent_dependency_is_recursive_before_any_effect(self):
        """Static entry contract, NOT a ChatGPT native selection trace.

        Prevent the earlier regression where a correct recursive body was
        contradicted by a one-way six-step headline and then overlooked.
        """
        skill = SKILL.read_text(encoding="utf-8")
        intro = skill.split("**Root-before-leaves dependency gate", 1)[1].split(
            "\n", 1)[0]
        self.assertIn("NOT a linear pipeline", intro)
        self.assertIn("RECURSIVELY", intro)
        self.assertIn("RECHALLENGE", intro)
        self.assertIn("BEFORE action", intro)
        self.assertIn("BACK into investigation", intro)
        self.assertNotIn("selected goal -> original private requirement/", intro)
        self.assertIn("Neither a checklist nor green CI", intro)

    def test_material_decisions_have_owner_visible_receipts(self):
        """Traceable comparison is required; native output cannot be asserted here."""
        skill = SKILL.read_text(encoding="utf-8")
        for term in ("Owner-visible decision and execution evidence",
                     "competing root-cause hypotheses", "counterevidence",
                     "falsifier/rollback", "NOT_TESTED/UNKNOWN",
                     "private chain-of-thought"):
            self.assertIn(term, skill)
        # Verify the comparison obligation, not one frozen slogan that
        # rejects legitimate additions such as retire/remove.
        study = skill.split("3. **Study deeply / traverse original projects:**", 1)[1].split("\n4. ", 1)[0]
        for method in ("reuse", "adapt", "replace", "remove", "build"):
            self.assertRegex(study, rf"\b{method}\b")
        self.assertIn("For EVERY cognition-system decision", skill)
        # Source-contract regression only: any one-way stage representation
        # must fail source checks, but a runtime Client trace is still needed.
        self.assertLess(skill.index("recursive root cause"),
                        skill.index("Study deeply / traverse original projects"))
        self.assertLess(skill.index("Study deeply / traverse original projects"),
                        skill.index("Rechallenge BEFORE decision"))
        self.assertIn("LOOP BACK into root-cause investigation", skill)
        self.assertIn("architecture, real implementation and call paths", skill)
        self.assertIn("tests/negative cases", skill)
        self.assertIn("issues and compatibility limits", skill)
        self.assertIn("challenge the preferred solution and the completeness of the research again", skill)
        self.assertIn("Failed or contradictory evidence can invalidate upstream causal assumptions", skill)

        self.assertIn("AB. Ordinary-chat entry versus Project-only false baseline",
                      PROBES.read_text(encoding="utf-8"))

    def test_progressive_disclosure_preserves_semantic_guardrails(self):
        core = SKILL.read_text(encoding="utf-8")
        protocol = PROTOCOL.read_text(encoding="utf-8")
        self.assertLess(len(core.encode("utf-8")), 9000)
        self.assertGreater(len(protocol), 16000)
        self.assertIn("references/parent-protocol.md", core)
        self.assertIn("The concise `../SKILL.md` is the interactive execution entrance", protocol)
        for token in ("SOURCE_LIFECYCLE_CONFLICT", "Source lifecycle at the real retrieval/write boundary",
                      "working memory", "episodic memory", "semantic memory", "procedural memory",
                      "invalidation", "competing causes"):
            self.assertIn(token, complete_policy())

    def test_decision_also_challenges_own_prompt_method_and_test(self):
        core = SKILL.read_text(encoding="utf-8")
        for token in ("Decision self-critique", "goal, prompt/entry, source",
                      "SKILL_DEFECT", "EXECUTION_LAPSE", "ENTRY_NOT_SELECTED",
                      "Bounded critique", "without new evidence", "independent readback"):
            self.assertIn(token, core)
        self.assertLess(core.index("Rechallenge BEFORE decision"), core.index("Execute / independent check / recursive reopen"))
        self.assertIn("Do not rewrite an existing valid rule", core)

    def test_owner_woken_interactive_phase_not_gated_on_permanent_host(self):
        """Source policy only; cannot prove a fresh ChatGPT launch."""
        gate = (ROOT / "docs/PRODUCT-READINESS-GATE.md").read_text(encoding="utf-8")
        handoff = (ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        skill = SKILL.read_text(encoding="utf-8")
        adr = (ROOT / "docs/01-ARCHITECTURE-DECISIONS.md").read_text(encoding="utf-8")
        probes = PROBES.read_text(encoding="utf-8")
        for body in (gate, handoff, skill, adr):
            self.assertIn("2026-10-29", body)
            self.assertTrue(("Host" in body or "SQLite" in body))
        self.assertIn("INTERACTIVE PHASE acceptance", gate)
        self.assertIn("each owner message can resume work", skill)
        self.assertIn("U. Owner-woken continuation", probes)
        self.assertIn("V. Oversized multi-session objective", probes)
        self.assertIn("NOT_TESTED", probes)

    def test_recurring_source_confusion_reenters_evidence_and_memory_decisions(self):
        """Contract-only probe; NOT native ChatGPT invocation evidence."""
        skill = complete_policy()
        probes = PROBES.read_text(encoding="utf-8")
        # A named parent-goal decision cannot treat dated handoffs or a
        # repository-only inventory as proof that private owner memory is
        # recovered or that all different surfaces were semantically read.
        for required in (
                "private Library", "stale index", "source coverage",
                "working memory", "episodic memory", "semantic memory",
                "procedural memory", "invalidation", "competing causes"):
            self.assertIn(required, skill)
        # A real negative control is still necessary to verify behavior.
        self.assertIn("T. Stale-index first-mile retrieval", probes)
        self.assertIn("NOT_TESTED", probes)

    def test_historical_source_supersession_is_not_naive_deletion(self):
        """Static candidate policy; new-chat behavior still needs live traces."""
        skill = complete_policy()
        codex = AGENTS.read_text(encoding="utf-8")
        adr = (ROOT / "docs/01-ARCHITECTURE-DECISIONS.md").read_text(encoding="utf-8")
        probes = PROBES.read_text(encoding="utf-8")
        for token in ("SOURCE_LIFECYCLE_CONFLICT", "supersedes its claim",
                      "independently reread", "privacy deletion"):
            self.assertIn(token, codex)
        for token in ("Source lifecycle at the real retrieval/write boundary",
                      "UNKNOWN", "dated history", "semantic search"):
            self.assertIn(token, skill)
        self.assertIn("失效不是删除", adr)
        self.assertIn("HISTORICAL_PR26_BUILD_STATE_20261023.json", adr)
        self.assertIn("W. Historical snapshot lifecycle", probes)
        self.assertIn("current state UNKNOWN", probes)
        self.assertIn("NOT_TESTED", probes)

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

    def test_bootstrap_is_a_locator_not_a_bulk_history_download(self):
        """Static structural checks; not a claim that ChatGPT obeys them."""
        handoff = (ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        recovery = handoff.split("## Recovery order and responsibility map", 1)[1].split(
            "## Work cycle after recovery", 1)[0]
        steps = re.findall(r"(?m)^(\d+)\.\s+\*\*([^*\n]+):\*\*", recovery)
        self.assertEqual([int(n) for n, _ in steps], list(range(1, 11)))
        self.assertLess(len(handoff.encode("utf-8")), 8192)
        self.assertNotIn("ALL open Draft PRs", recovery)
        self.assertIn("Agent-Learning-Hub", recovery)
        self.assertIn("architecture_probe.py --repo .", recovery)
        self.assertIn("LIVE_GIT_PROVENANCE_ON_DEMAND",
                      (ROOT / "scripts/codex_session_context.py").read_text(encoding="utf-8"))
        self.assertIn("default-branch HEAD and active-PR topology",
                      (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("live default-branch HEAD", AGENTS.read_text(encoding="utf-8"))
        self.assertIn("First recover unfinished work", SKILL.read_text(encoding="utf-8"))

    def test_recovery_roadmap_steps_are_monotonic_without_missing_entries(self):
        """Route order remains deterministic when new preflight phases are added."""
        handoff = (ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        recovery = handoff.split("## Recovery order and responsibility map", 1)[1].split(
            "## Work cycle after recovery", 1)[0]
        skill = SKILL.read_text(encoding="utf-8")
        workflow = skill.split("## Work on the problem, not the instructions", 1)[1].split(
            "**Continuation/stop check", 1)[0]
        for body in (recovery, workflow):
            ordinals = re.findall(r"(?m)^(\d+)\. \*\*", body)
            self.assertGreaterEqual(len(ordinals), 6)
            self.assertEqual(ordinals, [str(i) for i in range(1, len(ordinals) + 1)])

    def test_each_surface_is_a_distinct_loading_boundary(self):
        chatgpt = SKILL.read_text(encoding="utf-8").lower()
        codex = AGENTS.read_text(encoding="utf-8").lower()
        self.assertIn("installed account", chatgpt)
        self.assertIn("codex", codex)
        self.assertIn("host", chatgpt)
        self.assertIn("sqlite", codex)
        self.assertIn(".agents/skills/goal-grounded-semantic-review/skill.md",
                      codex)

    def test_cognition_entrypoints_share_one_live_architecture_source(self):
        """A file reference is a proposed route, NOT observed client obedience."""
        adr_path = "docs/01-ARCHITECTURE-DECISIONS.md"
        adr = (ROOT / adr_path).read_text(encoding="utf-8")
        self.assertIn("### 优先级反转", adr)
        self.assertIn("ChatGPT/Codex", adr)
        for entrypoint in (
                AGENTS, SKILL, ROOT / "SESSION_HANDOFF.md"):
            source = entrypoint.read_text(encoding="utf-8")
            self.assertIn(adr_path, source)
            self.assertIn("docs/PRODUCT-READINESS-GATE.md", source)
            self.assertNotRegex(source, r"\b[0-9a-f]{40}\b")
        hook = (ROOT / "scripts/codex_session_context.py").read_text(
            encoding="utf-8")
        self.assertIn(adr_path, hook)
        self.assertIn("from architecture_probe import inspect", hook)
        self.assertIn("REPO_PROPOSAL_NOT_OWNER_OR_GRANT", hook)

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

    def test_native_plugin_candidate_matches_installed_package_contract(self):
        root = json.loads((BASE / "plugin.json").read_text(encoding="utf-8"))
        native = json.loads((BASE / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(root["name"], native["name"])
        self.assertEqual(root["version"], native["version"])
        self.assertEqual(native["skills"].rstrip("/"), "./skills")
        self.assertEqual(native["repository"], root["repository"])

        # Test the real five-entry source package, not just a manifest word.
        # Preserve the installed plugin's native metadata during upgrade.
        entries = (
            ".codex-plugin/plugin.json",
            "plugin.json",
            "agents/openai.yaml",
            "skills/cognition-parent-chatgpt-intake/SKILL.md",
            "skills/cognition-parent-chatgpt-intake/references/scope-probes.md",
            "skills/cognition-parent-chatgpt-intake/references/parent-protocol.md",
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in entries:
                self.assertTrue((BASE / path).is_file())
                archive.write(BASE / path, arcname=path)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as package:
            self.assertEqual(set(package.namelist()), set(entries))
            for path in entries:
                self.assertEqual(package.read(path), (BASE / path).read_bytes())
            self.assertEqual(
                json.loads(package.read(".codex-plugin/plugin.json"))["version"],
                json.loads(package.read("plugin.json"))["version"])

    def test_all_three_discovery_surfaces_use_one_cognition_entry(self):
        """Different manifest defaults used to silently diverge across clients."""
        main = json.loads((BASE / "plugin.json").read_text(encoding="utf-8"))
        native = json.loads((BASE / ".codex-plugin/plugin.json").read_text(
            encoding="utf-8"))
        yaml = (BASE / "agents/openai.yaml").read_text(encoding="utf-8")
        yaml_prompt = next(
            line.partition(": ")[2] for line in yaml.splitlines()
            if line.startswith("  default_prompt: "))
        prompts = (
            main["extensions"]["com.openai"]["interface"]["defaultPrompt"],
            native["interface"]["defaultPrompt"], yaml_prompt)
        self.assertEqual(len(set(prompts)), 1, prompts)
        for concept in ("完整用户目标", "质疑", "研究", "比较", "执行",
                        "独立验收", "失败纠偏"):
            self.assertIn(concept, prompts[0])
        self.assertEqual(main["version"], native["version"])
        # Candidate package must be distinguishable from account-installed
        # 0.1.4; this check does not pretend that the account was changed.
        self.assertGreater(
            tuple(map(int, main["version"].split("."))), (0, 1, 4))

    def test_integrated_main_receives_real_core_ci_without_manual_dispatch(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8")
        # main was formerly invisible to push CI after integration.
        # Require the actual event mapping, not just an incidental mention.
        trigger = workflow.split("\npermissions:", 1)[0]
        self.assertRegex(
            trigger,
            r"(?ms)^  push:\n    branches:\n(?:(?:      - [^\n]+)\n)*?      - main\n")
        self.assertIn("  pull_request:\n", trigger)
        # Push must run core conformance, not optional model experiments.
        self.assertIn("  offline_regression:\n", workflow)
        self.assertIn("  windows_offline_regression:\n", workflow)

    def test_plugin_bundle_tracks_source_version_not_frozen_prose(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8")
        self.assertIn("chatgpt_plugin_release_bundle:", workflow)
        self.assertIn("chatgpt_plugin_release_bundle:", workflow)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", workflow)
        self.assertNotIn("contains(github.event.pull_request.body, '[bundle-chatgpt-plugin]')", workflow)
        self.assertIn("manifest['version']", workflow)
        self.assertNotIn("manifest['version'] == '0.1.3'", workflow)
        self.assertIn("No installation or owner account mutation occurs in CI",
                      workflow)
        self.assertIn("'.codex-plugin/plugin.json'", workflow)
        self.assertIn("manifest['version'] == native['version']", workflow)
        self.assertIn("'skills/cognition-parent-chatgpt-intake/SKILL.md'",
                      workflow)


if __name__ == "__main__":
    unittest.main()
