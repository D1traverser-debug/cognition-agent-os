"""Independent process tests for real Codex lifecycle rehydration (no hook simulation of effects)."""
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import alter_authority, connect, create_task, initialize
from cognition_agent_os.native_decision import register_native_goal

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts" / "codex_session_context.py"


class CodexSessionContext(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.db = self.tmp / "state.sqlite"
        self.ws = self.tmp / "workspace"
        self.fixtures = self.tmp / "fixtures"
        self.ws.mkdir()
        self.fixtures.mkdir()
        (self.fixtures / "settings.json").write_text(
            '{"timeout":7}\n', encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)

    def _run(self, *, cwd=None, with_database=True, vars=None):
        environ = dict(os.environ)
        for name in ("DB", "WORKSPACE", "FIXTURES"):
            environ.pop("COGNITION_AGENT_OS_" + name, None)
            environ.pop("COGNITION_OS_" + name, None)
        if with_database:
            environ.update({
                "COGNITION_AGENT_OS_DB": str(self.db),
                "COGNITION_AGENT_OS_WORKSPACE": str(self.ws),
                "COGNITION_AGENT_OS_FIXTURES": str(self.fixtures),
            })
        environ.update(vars or {})
        p = subprocess.run(
            [sys.executable, str(HOOK)],
            cwd=ROOT, input=json.dumps({"cwd": str(cwd or ROOT), "source": "startup"}),
            text=True, capture_output=True, env=environ, timeout=8)
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(
            result["hookSpecificOutput"]["hookEventName"], "SessionStart")
        msg = result["hookSpecificOutput"]["additionalContext"]
        self.last_context_chars = len(msg)
        self.assertTrue(msg.startswith("Read-only project state observation"), msg)
        return json.loads(msg.partition(": ")[-1])

    def test_codex_and_private_stdio_resolve_same_windows_host_by_default(self):
        """Independent entrypoint path contract, with no new SQLite or grants."""
        import importlib.util
        from unittest.mock import patch

        def load(name, filename):
            spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        codex = load("codex_path_contract_probe", "codex_session_context.py")
        private = load("chatgpt_path_contract_probe", "chatgpt_private_stdio.py")
        raw_checkout = self.tmp / "separate-checkout"
        # The fake ROOT is a fixture; a real hook's ROOT is also canonical
        # because it originates from Path(__file__).resolve().
        checkout = raw_checkout.resolve()
        runtime = checkout / "runtime"
        runtime.mkdir(parents=True)
        db = runtime / "state.sqlite"
        db.write_bytes(self.db.read_bytes())
        workspace = runtime / "workspace"
        fixtures = checkout / "fixtures"
        workspace.mkdir()
        fixtures.mkdir()
        # Existing Windows Host registrations default to checkout-root
        # fixtures. A stale runtime/fixtures must not win on another entry.
        alternate_fixtures = runtime / "fixtures"
        alternate_fixtures.mkdir()
        registration = (ROOT / "scripts" / "register_windows_host.ps1").read_text(
            encoding="utf-8")
        self.assertIn(
            "if (-not $FixturesPath) { $FixturesPath=Join-Path $root 'fixtures' }",
            registration)
        with patch.object(codex, "ROOT", checkout), patch.object(private, "_REPO", checkout):
            with patch.dict(os.environ, {}, clear=True):
                found, source = codex._existing_database()
                self.assertEqual(source, "DISCOVERED_EXISTING_LEDGER")
                self.assertTrue(found.samefile(db))
                self.assertTrue(all(actual.samefile(expected) for actual, expected in
                                    zip(private._paths(), (db, workspace, fixtures))))
                self.assertTrue(codex._optional_existing_directory(
                    "COGNITION_AGENT_OS_WORKSPACE", "runtime/workspace").samefile(workspace))
                self.assertTrue(codex._optional_existing_directory(
                    "COGNITION_AGENT_OS_FIXTURES", "fixtures").samefile(fixtures))

            # A configured alternate fixtures directory remains explicitly
            # supported; the default must not silently override it.
            with patch.dict(os.environ, {
                    "COGNITION_AGENT_OS_DB": str(db),
                    "COGNITION_AGENT_OS_FIXTURES": str(alternate_fixtures),
            }, clear=True):
                self.assertTrue(private._paths()[2].samefile(alternate_fixtures))
                self.assertTrue(codex._optional_existing_directory(
                    "COGNITION_AGENT_OS_FIXTURES", "fixtures").samefile(
                        alternate_fixtures))

            # Both supported env schemes must identify the identical resource,
            # including relative paths interpreted against the repo checkout.
            with patch.dict(os.environ, {
                    "COGNITION_AGENT_OS_DB": "runtime/state.sqlite",
                    # May retain the Windows RUNNER~1 spelling while ROOT
                    # above expands it to runneradmin: same inode, two names.
                    "COGNITION_OS_DB": str(raw_checkout / "runtime" / "state.sqlite"),
                    "COGNITION_OS_WORKSPACE": str(workspace),
                    "COGNITION_OS_FIXTURES": str(fixtures),
            }, clear=True):
                self.assertTrue(codex._existing_database()[0].samefile(db))
                self.assertTrue(all(actual.samefile(expected) for actual, expected in
                                    zip(private._paths(), (db, workspace, fixtures))))

            # Cold recovery must select runtime/ dirs even when the
            # initialized DB is configured through a Windows short-path alias.
            # The continuation oracle sees the actual resource paths, not
            # only the ledger ID or a source-observation summary.
            from unittest.mock import patch as mock_patch
            with patch.dict(os.environ, {
                    "COGNITION_OS_DB": str(raw_checkout / "runtime" / "state.sqlite")
            }, clear=True):
                with mock_patch("cognition_agent_os.continuity.resume_goal",
                                return_value={"status": "UNVERIFIED_TEST_GOAL"}) as resume:
                    codex.build_context({"cwd": str(checkout)})
                    kwargs = resume.call_args.kwargs
                    self.assertTrue(kwargs["workspace"].samefile(workspace))
                    self.assertTrue(kwargs["fixtures"].samefile(fixtures))

            # An older checkout-root ledger still selects its older
            # checkout-root resources, not the new runtime directories.
            legacy_db = checkout / "ledger.sqlite"
            legacy_db.write_bytes(self.db.read_bytes())
            root_ws, root_fx = checkout / "workspace", checkout / "fixtures"
            root_ws.mkdir()
            self.assertTrue(root_fx.samefile(fixtures))
            with patch.dict(os.environ, {
                    "COGNITION_OS_DB": str(raw_checkout / "ledger.sqlite")
            }, clear=True):
                with mock_patch("cognition_agent_os.continuity.resume_goal",
                                return_value={"status": "UNVERIFIED_TEST_GOAL"}) as resume:
                    codex.build_context({"cwd": str(checkout)})
                    kwargs = resume.call_args.kwargs
                    self.assertTrue(kwargs["workspace"].samefile(root_ws))
                    self.assertTrue(kwargs["fixtures"].samefile(root_fx))

            # Legacy-only and canonical-only configurations remain valid.
            for key in ("COGNITION_OS_DB", "COGNITION_AGENT_OS_DB"):
                with patch.dict(os.environ, {key: str(db)}, clear=True):
                    self.assertTrue(codex._existing_database()[0].samefile(db))
                    self.assertTrue(private._paths()[0].samefile(db))

            # Workspace/fixture aliases also must not silently diverge.
            other_dir = checkout / "other-workspace"
            other_dir.mkdir()
            # The fixture now holds two legitimate ledgers (new and legacy).
            # Explicitly select the runtime one so this case tests *workspace*
            # alias conflict rather than the earlier multi-ledger refusal.
            with patch.dict(os.environ, {
                    "COGNITION_AGENT_OS_DB": str(db),
                    "COGNITION_AGENT_OS_WORKSPACE": str(workspace),
                    "COGNITION_OS_WORKSPACE": str(other_dir),
            }, clear=True):
                with self.assertRaisesRegex(ValueError, "CONFLICTING_RUNTIME_RESOURCE_ENV"):
                    codex._optional_existing_directory(
                        "COGNITION_AGENT_OS_WORKSPACE", "runtime/workspace")
                denied = codex.build_context({"cwd": str(checkout)})
                self.assertEqual(denied["status"], "CONFLICTING_RUNTIME_RESOURCE_ENV")
                self.assertFalse(denied["original_goal_verified"])
                self.assertFalse(denied["scheduling_or_effects_performed"])
                with self.assertRaisesRegex(ValueError, "CONFLICTING_RUNTIME_RESOURCE_ENV"):
                    private._paths()

            # A silently different ledger is more dangerous than no ledger.
            other = checkout / "other.sqlite"
            other.write_bytes(self.db.read_bytes())
            with patch.dict(os.environ, {
                    "COGNITION_AGENT_OS_DB": str(db),
                    "COGNITION_OS_DB": str(other),
            }, clear=True):
                self.assertEqual(codex._existing_database(),
                                 (None, "CONFLICTING_LEDGER_ENV"))
                with self.assertRaisesRegex(ValueError, "CONFLICTING_RUNTIME_RESOURCE_ENV"):
                    private._paths()

            # No arbitrary default selection if old and new files coexist.
            (checkout / "state.sqlite").write_bytes(self.db.read_bytes())
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(codex._existing_database(),
                                 (None, "AMBIGUOUS_LOCAL_LEDGERS"))
                self.assertTrue(private._paths()[0].samefile(db))

    def test_large_no_ledger_index_does_not_claim_a_missing_sqlite_goal(self):
        """Source-map overflow must preserve a truthful no-ledger recovery."""
        import importlib.util
        import io
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location(
            "oversized_no_ledger_hook", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        guide = dict(module._project_recovery_when_no_ledger())
        guide["extra_untrusted_detail"] = "x" * 10000
        stdin = io.StringIO(json.dumps({"cwd": str(ROOT), "source": "startup"}))
        stdout = io.StringIO()
        with (patch.object(module, "_existing_database",
                           return_value=(None, "NO_LOCAL_LEDGER_CONFIGURED")),
              patch.object(module, "_project_recovery_when_no_ledger",
                           return_value=guide),
              patch.object(sys, "stdin", stdin),
              patch.object(sys, "stdout", stdout)):
            self.assertEqual(module.main(), 0)
        packet = json.loads(stdout.getvalue())
        receipt = packet["hookSpecificOutput"]["additionalContext"]
        self.assertGreater(len(receipt), 6000)
        data = json.loads(receipt.partition(": ")[-1])
        self.assertEqual(data["status"], "NO_LOCAL_LEDGER_CONFIGURED")
        self.assertEqual(data["ledger_discovery"], "NO_LOCAL_LEDGER_CONFIGURED")
        self.assertFalse(data["original_goal_verified"])
        self.assertNotIn("original_goal", data)
        self.assertEqual(data["repository_recovery"]["extra_untrusted_detail"],
                         "x" * 10000)
        self.assertNotEqual(data["status"], "FULL_LEDGER_READBACK_REQUIRED")
        self.assertEqual(
            data["repository_recovery"]["live_default_branch_head_and_ci"],
            "MUST_REFETCH")

    def test_approximate_token_budget_does_not_drop_bounded_source_map(self):
        """A >2k-character source map is not a >2k-token Codex violation."""
        import importlib.util
        import io
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location("bounded_source_hook", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        guide = dict(module._project_recovery_when_no_ledger())
        guide["bounded_source_details"] = "source:" * 430
        stdin = io.StringIO(json.dumps({"cwd": str(ROOT), "source": "startup"}))
        stdout = io.StringIO()
        with (patch.object(module, "_existing_database",
                           return_value=(None, "NO_LOCAL_LEDGER_CONFIGURED")),
              patch.object(module, "_project_recovery_when_no_ledger",
                           return_value=guide),
              patch.object(sys, "stdin", stdin),
              patch.object(sys, "stdout", stdout)):
            self.assertEqual(module.main(), 0)
        receipt = json.loads(stdout.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertGreater(len(receipt), 2000)
        recovered = json.loads(receipt.partition(": ")[-1])
        self.assertEqual(recovered["status"], "NO_LOCAL_LEDGER_CONFIGURED")
        self.assertEqual(recovered["repository_recovery"]["bounded_source_details"],
                         guide["bounded_source_details"])
        self.assertFalse(recovered["original_goal_verified"])

    def test_no_ledger_long_source_is_not_silently_discarded(self):
        """No extra index: let Codex native spill, keeping original repo guidance."""
        import importlib.util
        import io
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location("source_spill_hook", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        extra = "重要约束:不得合并、不许写子系统; " * 500
        guide = dict(module._project_recovery_when_no_ledger())
        guide["additional_constraints"] = extra
        stdin = io.StringIO(json.dumps({"cwd": str(ROOT), "source": "startup"}))
        stdout = io.StringIO()
        with (patch.object(module, "_existing_database",
                           return_value=(None, "NO_LOCAL_LEDGER_CONFIGURED")),
              patch.object(module, "_project_recovery_when_no_ledger",
                           return_value=guide),
              patch.object(sys, "stdin", stdin),
              patch.object(sys, "stdout", stdout)):
            self.assertEqual(module.main(), 0)
        full = json.loads(stdout.getvalue())["hookSpecificOutput"]["additionalContext"]
        result = json.loads(full.partition(": ")[-1])
        self.assertEqual(result["repository_recovery"]["additional_constraints"], extra)
        self.assertEqual(result["repository_recovery"]["live_default_branch_head_and_ci"],
                         "MUST_REFETCH")
        self.assertFalse(result["original_goal_verified"])

    def test_missing_source_never_invents_owner_goal(self):
        result = self._run(with_database=False)
        self.assertEqual(result["status"], "NO_LOCAL_LEDGER_CONFIGURED")
        self.assertFalse(result["original_goal_verified"])
        self.assertNotIn("original_goal", result)
        # Real process invocation without local SQLite must recover the
        # EXISTING repository product direction, NOT invent owner history,
        # claim GitHub-verified HEAD, or create a new authority.
        project = result["repository_recovery"]
        self.assertEqual(project["status"], "PROJECT_GUIDANCE_FOUND")
        self.assertEqual(project["source_path"],
                         "docs/PRODUCT-READINESS-GATE.md")
        self.assertEqual(project["source_role"],
                         "REPO_PROPOSAL_NOT_OWNER_OR_GRANT")
        self.assertIn("opt-in interactive cognition workflow",
                      project["near_term_priority"])
        self.assertEqual(project["original_user_utterances"],
                         "MUST_RECOVER_SEPARATELY")
        self.assertEqual(project["continuation_index"], "SESSION_HANDOFF.md")
        self.assertEqual(project["continuation_policy"],
                         "PROGRESSIVE_LIVE_SOURCE_DISCLOSURE")
        self.assertEqual(project["complete_work_log_location"],
                         "LIVE_GIT_PROVENANCE_ON_DEMAND")
        self.assertIn("bootstrap index", project["proposed_action"])
        self.assertIn("task-relevant source", project["proposed_action"])
        self.assertIn("specific conflict", project["proposed_action"])
        self.assertEqual(project["live_default_branch_head_and_ci"],
                         "MUST_REFETCH")
        self.assertEqual(project["live_active_pr_metadata"], "CHECK_IF_PRESENT")
        self.assertNotIn("live_pr_head_and_ci", project)
        self.assertIn("live default branch HEAD", project["proposed_action"])
        self.assertIn("active PR only if present", project["proposed_action"])
        self.assertEqual(project["product_readiness_claim"], "NOT_VERIFIED")
        # An active architectural pivot must reach the actual cold-entry
        # process rather than live only in a document the agent may never read.
        architecture = project["architecture_pivot"]
        self.assertEqual(architecture["status"],
                         "REPO_PROPOSAL_NOT_OWNER_OR_GRANT")
        self.assertEqual(architecture["source_path"],
                         "docs/01-ARCHITECTURE-DECISIONS.md")
        self.assertIn("ChatGPT/Codex",
                      architecture["proposed_first_action"])
        self.assertIn("挑战", architecture["proposed_first_action"])
        self.assertGreater(self.last_context_chars, 100,
                           "Native client owns the token overflow; hook must remain valid")
        topology = project["live_python_topology"]
        self.assertEqual(topology["kind"],
                         "CURRENT_CHECKOUT_AST_NOT_RUNTIME_PROOF")
        self.assertEqual(topology["source_map"], "scripts/architecture_probe.py")
        self.assertGreaterEqual(topology["parsed_modules"], 50)
        self.assertEqual(topology["parse_errors"], [])
        self.assertEqual(topology["paths"]["decision"],
                         "src/cognition_agent_os/native_decision.py")
        self.assertEqual(topology["paths"]["effect"],
                         "src/cognition_agent_os/runner.py")
        self.assertEqual(topology["paths"]["recovery"],
                         "src/cognition_agent_os/continuity.py")
        self.assertEqual(topology["paths"]["client_adapter"],
                         "src/cognition_agent_os/native_mcp_bridge.py")
        self.assertEqual(topology["paths"]["independent_local_result"],
                         "src/cognition_agent_os/owner_postcondition.py")
        self.assertFalse(result["business_outcome_verified"])
        self.assertFalse(result["scheduling_or_effects_performed"])

    def test_missing_current_architecture_or_modules_does_not_fabricate_map(self):
        """Cold recovery source truth is rechecked, never guessed from old prose."""
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location(
            "codex_test_recovery", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "ROOT", self.tmp):
            self.assertEqual(
                module._current_architecture_pivot()["status"],
                "ARCHITECTURE_PIVOT_UNVERIFIABLE")
            self.assertEqual(
                module._live_python_topology()["kind"],
                "CURRENT_SOURCE_TOPOLOGY_UNVERIFIABLE")
            docs = self.tmp / "docs"
            docs.mkdir()
            original = docs / "01-ARCHITECTURE-DECISIONS.md"
            original.write_text(
                "### 优先级反转（约束后续工程行为）\n"
                "1. ChatGPT/Codex first inspect ALL current original source "
                "evidence; compare two legitimate methods; independently "
                "read back authorized effects before promoting outcomes.\n",
                encoding="utf-8")
            first = module._current_architecture_pivot()
            self.assertEqual(
                first["status"], "REPO_PROPOSAL_NOT_OWNER_OR_GRANT")
            self.assertIn("ALL current original source", first["proposed_first_action"])
            # Editing the actual source must update the next cold recovery,
            # without a cached latest-decision summary.
            original.write_text(
                "### 优先级反转（约束后续工程行为）\n"
                "1. ChatGPT/Codex now challenge a changed evidence provider "
                "and re-evaluate actual task results before granting "
                "semantic success to any previous attempt.\n",
                encoding="utf-8")
            second = module._current_architecture_pivot()
            self.assertIn("changed evidence provider",
                          second["proposed_first_action"])
            self.assertNotIn("ALL current original source",
                             second["proposed_first_action"])

    def test_windows_cp1252_hook_wire_round_trips_architecture_unicode(self):
        """A Windows client can decode the original UTF-8 owner/ADR content
        even when console stdout uses a restrictive legacy codepage.
        """
        result = self._run(
            with_database=False,
            vars={"PYTHONIOENCODING": "cp1252:strict"})
        pivot = result["repository_recovery"]["architecture_pivot"]
        self.assertEqual(
            pivot["status"], "REPO_PROPOSAL_NOT_OWNER_OR_GRANT")
        self.assertIn("ChatGPT/Codex", pivot["proposed_first_action"])
        self.assertIn("认知", pivot["proposed_first_action"])

    def test_sqlite_original_owner_goal_is_not_replaced_by_repo_guidance(self):
        owner = "Compare reference.csv with observed.csv, preserve source."
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "open_goal", "goal": owner})
        result = self._run()
        self.assertNotIn("original_goal", result)
        self.assertTrue(result["original_goal_verified"])
        self.assertTrue(result["original_goal_available_via_readback"])
        self.assertTrue(result["original_goal_omitted_from_hook"])
        self.assertNotIn("repository_recovery", result)

    def test_large_valid_owner_goal_remains_in_ledger_not_hook_spill(self):
        # Native-goal admission permits 8,192 original characters. The hook
        # carries checked identity; only explicit same-ledger readback reveals
        # original private text (never arbitrary substring truncation).
        goal = ("Check evidence and permissions without skipping any original "
                "clauses. " + "compare sources and verify results; " * 220)
        self.assertTrue(7500 < len(goal) <= 8192)
        root = register_native_goal(self.db, goal)
        first = self._run()
        second = self._run()
        self.assertEqual(first, second)
        self.assertEqual(first["root_task_id"], root)
        self.assertEqual(first["source_of_truth"], "ORIGINAL_SQLITE_TASK")
        self.assertRegex(first["original_contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["ledger_discovery"], "CONFIGURED_LEDGER")
        self.assertNotIn("original_goal", first)
        self.assertTrue(first["original_goal_verified"])
        self.assertTrue(first["original_goal_available_via_readback"])
        self.assertFalse(first["business_outcome_verified"])
        self.assertFalse(first["scheduling_or_effects_performed"])
        with closing(connect(self.db)) as db:
            original = db.execute(
                "SELECT source_spec FROM tasks WHERE task_id=?", (root,)
            ).fetchone()[0]
        self.assertEqual(json.loads(original)["goal"], goal)

    def test_large_goal_revocation_survives_bounded_hook_context(self):
        goal = ("Keep complete owner intent and compare current evidence. "
                + "compare sources and verify results; " * 220)
        root = register_native_goal(self.db, goal)
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        state = self._run()
        self.assertEqual(state["root_task_id"], root)
        self.assertEqual(state["status"], "AUTHORITY_REVOKED")
        self.assertNotIn("original_goal", state)
        self.assertTrue(state["original_goal_verified"])
        self.assertTrue(state["original_goal_available_via_readback"])
        self.assertIs(state["authority_current"], False)
        self.assertNotIn("next_task_id", state)
        self.assertFalse(state["business_outcome_verified"])

    def test_multiple_original_owner_goals_survive_cold_start_ambiguity(self):
        """A hook must not drop distinct user goals or select a recent winner."""
        first_goal = "Reconcile source A without writing external systems."
        second_goal = "Investigate source B and preserve contradictory evidence."
        with closing(connect(self.db)) as db:
            first_root = create_task(db, {"kind": "open_goal", "goal": first_goal})
            second_root = create_task(db, {"kind": "open_goal", "goal": second_goal})
        result = self._run()
        self.assertEqual(result["status"], "AMBIGUOUS_OPEN_OWNER_GOALS")
        self.assertEqual(set(result["root_task_ids"]), {first_root, second_root})
        self.assertEqual(result["ambiguous_goal_count"], 2)
        self.assertNotIn("original_goals", result)
        self.assertNotIn(first_goal, json.dumps(result))
        self.assertNotIn(second_goal, json.dumps(result))
        self.assertFalse(result["original_goal_verified"])
        self.assertNotIn("next_task_id", result)
        self.assertFalse(result["business_outcome_verified"])
        locator = result["ambiguous_goal_readback"]
        self.assertEqual(locator["source_role"], "READ_ONLY_EXISTING_SQLITE_GOALS")
        env = dict(os.environ)
        env.update({"COGNITION_AGENT_OS_DB": str(self.db),
                    "COGNITION_AGENT_OS_WORKSPACE": str(self.ws),
                    "COGNITION_AGENT_OS_FIXTURES": str(self.fixtures)})
        def reread(args):
            proc = subprocess.run([sys.executable, str(HOOK), *args],
                                  cwd=ROOT, env=env, capture_output=True,
                                  text=True, timeout=8)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        actual = reread(locator["arguments"])
        self.assertEqual(actual["status"], "AMBIGUOUS_READBACK_IDENTITY_MATCHED")
        self.assertEqual(
            {entry["original_goal"] for entry in actual["readback"]["original_goals"]},
            {first_goal, second_goal})
        self.assertFalse(actual["scheduling_or_effects_performed"])
        invalid = reread(["--readback-ambiguous", "0" * 64])
        self.assertEqual(invalid["status"], "AMBIGUOUS_READBACK_IDENTITY_UNVERIFIED")
        self.assertNotIn("readback", invalid)

    def test_direct_original_readback_rejects_drift_and_is_read_only(self):
        """Codex can dereference its SAME SQLite root without any hook cache."""
        goal = "Preserve the full owner goal, including the last prohibition. " * 117
        root = register_native_goal(self.db, goal)
        hook = self._run()
        locator = hook["original_goal_readback"]
        self.assertNotIn("original_goal", hook)
        self.assertNotIn(goal, json.dumps(hook))
        self.assertNotIn("original_goal", hook.get("native_decision_state", {}))
        self.assertEqual(locator["source_role"], "READ_ONLY_EXISTING_SQLITE_GOAL")
        self.assertEqual(locator["arguments"][1:], [
            root, hook["original_contract_sha256"]])
        env = dict(os.environ)
        env.update({"COGNITION_AGENT_OS_DB": str(self.db),
                    "COGNITION_AGENT_OS_WORKSPACE": str(self.ws),
                    "COGNITION_AGENT_OS_FIXTURES": str(self.fixtures)})
        def readback(arguments):
            proc = subprocess.run(
                [sys.executable, str(HOOK), *arguments], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=8)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        with closing(connect(self.db)) as db:
            before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        actual = readback(locator["arguments"])
        self.assertEqual(actual["status"], "ORIGINAL_READBACK_IDENTITY_MATCHED")
        self.assertEqual(actual["readback"]["root_task_id"], root)
        self.assertEqual(actual["readback"]["original_goal"], goal)
        self.assertFalse(actual["scheduling_or_effects_performed"])
        self.assertEqual(readback(["--readback-original", root, "0" * 64])["status"],
                         "ORIGINAL_READBACK_IDENTITY_UNVERIFIED")
        self.assertEqual(readback(["--readback-original", "bad", "0" * 64])["status"],
                         "INVALID_ORIGINAL_READBACK_IDENTITY")
        with closing(connect(self.db)) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)
            alter_authority(db, revoke=True)
        revoked = readback(locator["arguments"])
        self.assertEqual(revoked["status"], "ORIGINAL_READBACK_IDENTITY_MATCHED")
        self.assertEqual(revoked["readback"]["status"], "AUTHORITY_REVOKED")
        self.assertIs(revoked["readback"]["authority_current"], False)
        self.assertNotIn("next_task_id", revoked["readback"])
        self.assertFalse(revoked["scheduling_or_effects_performed"])

    def test_cold_restart_resumes_exact_original_goal_without_new_ledger(self):
        goal = "Compare actual.csv with baseline.csv and report differences."
        with closing(connect(self.db)) as db:
            root = create_task(db, {"kind":"open_goal", "goal":goal})
            pre = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        first = self._run()
        second = self._run()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "READY_TO_TICK")
        self.assertEqual(first["root_task_id"], root)
        self.assertNotIn("original_goal", first)
        self.assertTrue(first["original_goal_verified"])
        self.assertTrue(first["original_goal_available_via_readback"])
        self.assertFalse(first["business_outcome_verified"])
        self.assertEqual(first["next_task_id"], root)
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events").fetchone()[0], pre)

    def test_revocation_cannot_be_laundered_into_session_permission(self):
        with closing(connect(self.db)) as db:
            create_task(db, {"kind":"open_goal",
                             "goal":"Compare actual.csv with baseline.csv and report differences."})
            alter_authority(db, revoke=True)
        state = self._run()
        self.assertEqual(state["status"], "AUTHORITY_REVOKED")
        self.assertNotIn("next_task_id", state)
        self.assertFalse(state["business_outcome_verified"])

    def test_real_source_and_output_replay_after_effect(self):
        goal = ("Please ensure a sandbox draft of settings.json has owner "
                "equal to ops, preserving the existing timeout.")
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "open_goal", "goal": goal})
        run_tick(self.db, self.ws, self.fixtures,
                 max_jobs=2, auto_stage_goals=True)
        verified = self._run()
        self.assertEqual(verified["status"], "LOCAL_OWNER_RESULT_VERIFIED", verified)
        self.assertTrue(verified["local_owner_outcome_verified"])
        self.assertFalse(verified["business_outcome_verified"])
        # Current output must be read again; a historical success is not authority.
        files = list((self.ws / "sandbox").glob("*.candidate"))
        self.assertEqual(len(files), 1)
        files[0].write_text('{"timeout":7,"owner":"tampered"}\n', encoding="utf-8")
        invalid = self._run()
        self.assertFalse(invalid["local_owner_outcome_verified"])
        self.assertNotEqual(invalid["status"], "LOCAL_OWNER_RESULT_VERIFIED")
        self.assertNotIn("next_task_id", invalid)

    def test_wrong_checkout_never_receives_private_owner_context(self):
        with closing(connect(self.db)) as db:
            create_task(db, {"kind": "open_goal",
                             "goal": "Compare actual.csv with baseline.csv and report differences."})
        state = self._run(cwd=self.tmp)
        self.assertEqual(state["status"], "HOOK_OUTSIDE_REPOSITORY")
        self.assertNotIn("original_goal", state)

    def test_actual_installed_hook_command_from_nested_directory(self):
        """Codex can be started inside src/, not only in repository root.

        Run the configured command with real shell parsing. Testing the Python
        entrypoint directly misses a broken relative hook command path.
        """
        goal = "Compare actual.csv with baseline.csv and report differences."
        with closing(connect(self.db)) as db:
            root = create_task(db, {"kind": "open_goal", "goal": goal})
        config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        handler = config["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertLessEqual(handler["additionalContextLimit"], 2500)
        env = dict(os.environ)
        env.update({
            "COGNITION_AGENT_OS_DB": str(self.db),
            "COGNITION_AGENT_OS_WORKSPACE": str(self.ws),
            "COGNITION_AGENT_OS_FIXTURES": str(self.fixtures),
        })
        nested = ROOT / "src"
        payload = json.dumps({
            "cwd": str(nested), "source": "resume",
            "hook_event_name": "SessionStart",
        })
        if os.name == "nt":
            # Replicate Codex Command::raw_arg: cmd.exe /C "<hook command>".
            # PowerShell masked POSIX $(...) substitution in commandWindows.
            command = 'cmd.exe /C "' + handler["commandWindows"] + '"'
        else:
            command = ["/bin/sh", "-c", handler["command"]]
        call = subprocess.run(
            command, cwd=nested, input=payload, text=True,
            capture_output=True, env=env, timeout=8)
        self.assertEqual(call.returncode, 0, call.stderr)
        wire = json.loads(call.stdout)
        self.assertEqual(wire["hookSpecificOutput"]["hookEventName"],
                         "SessionStart", wire)
        context = json.loads(
            wire["hookSpecificOutput"]["additionalContext"].partition(": ")[-1])
        self.assertEqual(context["root_task_id"], root, context)
        self.assertNotIn("original_goal", context)
        self.assertTrue(context["original_goal_available_via_readback"])
        self.assertEqual(context["status"], "READY_TO_TICK")
        self.assertFalse(context["scheduling_or_effects_performed"])

    def test_actual_pretool_hook_command_from_nested_directory(self):
        """Verify the SAME shell transport for the second configured Windows hook.

        The risk is systemic: an apparently tested Python guard can be dead
        when the Codex commandWindows wrapper is parsed by cmd.exe.
        """
        config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        handler = config["hooks"]["PreToolUse"][0]["hooks"][0]
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__GitHub__update_pull_request",
            "tool_input": {
                "repository_full_name": "D1traverser-debug/cognition-agent-os",
                "pr_number": 50,
                "body": "[run-real-native-schema]",
            },
        }
        if os.name == "nt":
            command = 'cmd.exe /C "' + handler["commandWindows"] + '"'
        else:
            command = ["/bin/sh", "-c", handler["command"]]
        result = subprocess.run(
            command, cwd=ROOT / "src", input=json.dumps(event), text=True,
            capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        decision = receipt["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("REUSE_PRIOR_NATIVE_EVIDENCE",
                      decision["permissionDecisionReason"])

    def test_windows_launcher_is_auditable_and_shell_neutral(self):
        """The Windows command is executable under cmd and inherited PowerShell.

        EncodedCommand avoids Codex's nested-quote corruption; decode the
        *exact* configured launcher here so an opaque change cannot broaden
        the script's actions or silently skip the real repo-root lookup.
        """
        import base64
        config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        for event, filename, options in (
            ("SessionStart", "codex_session_context.py", ""),
            ("PreToolUse", "verify_ci_evidence_scope.py", " --codex-pretool"),
        ):
            with self.subTest(event=event):
                handler = config["hooks"][event][0]["hooks"][0]
                command = handler["commandWindows"]
                prefix = "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
                self.assertTrue(command.startswith(prefix), command)
                wire = command[len(prefix):]
                decoded = base64.b64decode(wire, validate=True).decode("utf-16le")
                expected = (
                    "$root = (& git rev-parse --show-toplevel).Trim(); "
                    "if ($LASTEXITCODE -ne 0) { exit 1 }; "
                    f"& python (Join-Path $root 'scripts/{filename}'){options}; "
                    "exit $LASTEXITCODE"
                )
                self.assertEqual(decoded, expected)

    @unittest.skipUnless(os.name == "nt", "Windows inherited PowerShell only")
    def test_windows_inherited_powershell_hook_entrypoints(self):
        """Prove both configured commands against the other actual Codex shell."""
        with closing(connect(self.db)) as db:
            root = create_task(db, {
                "kind": "open_goal",
                "goal": "Compare actual.csv with baseline.csv and report differences.",
            })
        config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        environ = dict(os.environ)
        environ.update({
            "COGNITION_AGENT_OS_DB": str(self.db),
            "COGNITION_AGENT_OS_WORKSPACE": str(self.ws),
            "COGNITION_AGENT_OS_FIXTURES": str(self.fixtures),
        })
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__GitHub__update_pull_request",
            "tool_input": {
                "repository_full_name": "D1traverser-debug/cognition-agent-os",
                "pr_number": 50,
                "body": "[run-real-native-schema]",
            },
        }
        for kind, payload in (
            ("SessionStart", {"cwd": str(ROOT / "src"), "source": "resume"}),
            ("PreToolUse", event),
        ):
            with self.subTest(kind=kind):
                handler = config["hooks"][kind][0]["hooks"][0]
                # Codex can inherit PowerShell's -Command as its shell.
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive",
                     "-Command", handler["commandWindows"]],
                    cwd=ROOT / "src", input=json.dumps(payload), text=True,
                    capture_output=True, env=environ, timeout=12,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                wire = json.loads(result.stdout)
                outcome = wire["hookSpecificOutput"]
                if kind == "SessionStart":
                    self.assertEqual(outcome["hookEventName"], "SessionStart")
                    context = json.loads(outcome["additionalContext"].partition(": ")[-1])
                    self.assertEqual(context["root_task_id"], root)
                    self.assertTrue(context["original_goal_verified"])
                    self.assertFalse(context["business_outcome_verified"])
                else:
                    self.assertEqual(outcome["hookEventName"], "PreToolUse")
                    self.assertEqual(outcome["permissionDecision"], "deny")

    def test_hook_lifecycle_registration_and_entry_path(self):
        config = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        events = config["hooks"]["SessionStart"]
        self.assertEqual(len(events), 1)
        self.assertIn("compact", events[0]["matcher"])
        self.assertIn("resume", events[0]["matcher"])
        self.assertEqual(len(events[0]["hooks"]), 1)
        self.assertIn("codex_session_context.py", events[0]["hooks"][0]["command"])
