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
        fixtures = runtime / "fixtures"
        workspace.mkdir()
        fixtures.mkdir()
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
                    "COGNITION_AGENT_OS_FIXTURES", "runtime/fixtures").samefile(fixtures))

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

            # Legacy-only and canonical-only configurations remain valid.
            for key in ("COGNITION_OS_DB", "COGNITION_AGENT_OS_DB"):
                with patch.dict(os.environ, {key: str(db)}, clear=True):
                    self.assertTrue(codex._existing_database()[0].samefile(db))
                    self.assertTrue(private._paths()[0].samefile(db))

            # Workspace/fixture aliases also must not silently diverge.
            other_dir = checkout / "other-workspace"
            other_dir.mkdir()
            with patch.dict(os.environ, {
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
                         "LIVE_GIT_COMMIT_HISTORY_AND_DIFF")
        self.assertIn("bootstrap index", project["proposed_action"])
        self.assertIn("commit history/diff", project["proposed_action"])
        self.assertEqual(project["live_pr_head_and_ci"], "MUST_REFETCH")
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
        self.assertLessEqual(self.last_context_chars, 2000,
                             "Codex hook advertised additionalContextLimit=2000")
        topology = project["live_python_topology"]
        self.assertEqual(topology["kind"],
                         "CURRENT_CHECKOUT_AST_NOT_RUNTIME_PROOF")
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
        self.assertEqual(result["original_goal"], owner)
        self.assertTrue(result["original_goal_verified"])
        self.assertNotIn("repository_recovery", result)

    def test_large_valid_owner_goal_preserves_sqlite_locator_not_partial_text(self):
        # Native-goal admission permits 8,192 original characters. The
        # read-only SessionStart hook must not erase its identity simply
        # because that legitimate original exceeds the model-context budget.
        goal = ("Check evidence and permissions without skipping any original "
                "clauses. " + "compare sources and verify results; " * 220)
        self.assertTrue(7500 < len(goal) <= 8192)
        root = register_native_goal(self.db, goal)
        first = self._run()
        second = self._run()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "FULL_LEDGER_READBACK_REQUIRED")
        self.assertEqual(first["root_task_id"], root)
        self.assertEqual(first["source_of_truth"], "ORIGINAL_SQLITE_TASK")
        self.assertRegex(first["original_contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["ledger_discovery"], "CONFIGURED_LEDGER")
        self.assertTrue(first["original_goal_persisted_in_ledger"])
        self.assertTrue(first["original_goal_omitted_from_hook"])
        self.assertFalse(first["original_goal_verified"])
        self.assertNotIn("original_goal", first)
        self.assertNotIn("next_task_id", first)
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
        self.assertEqual(state["status"], "FULL_LEDGER_READBACK_REQUIRED")
        self.assertEqual(state["observed_runtime_status"], "AUTHORITY_REVOKED")
        self.assertFalse(state["original_goal_verified"])
        self.assertNotIn("next_task_id", state)
        self.assertFalse(state["business_outcome_verified"])

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
        self.assertEqual(first["original_goal"], goal)
        self.assertTrue(first["original_goal_verified"])
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
        self.assertEqual(context["original_goal"], goal)
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
