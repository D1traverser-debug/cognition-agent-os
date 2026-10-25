"""OT06: a new process can recover the durable owner goal, not a handoff heading.

The experiment is read-only after explicit registration. A green mechanical
task state is NOT owner-level acceptance, and a new remote HEAD invalidates
the pinned development checkpoint until it is revalidated.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize, create_task, alter_authority
from cognition_agent_os.continuity import register_goal, resume_goal, checkpoint_goal


class GoalContinuityColdResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state.sqlite"
        with closing(connect(self.db_path)) as db:
            initialize(db)
            self.first_task = create_task(
                db, {"kind": "fixture", "old": "before", "new": "after"})

    def contract(self, *, name="cognition-os", next_task_id=None, source=None):
        return {
            "goal_id": name,
            "objective": "Build a goal-directed autonomous controller",
            "acceptance": "A held-out user outcome must be independently verified",
            "constraints": ["No unauthorized external write", "No paid model API"],
            "next_task_id": self.first_task if next_task_id is None else next_task_id,
            "source": source,
        }

    def test_original_goal_survives_new_python_interpreter(self):
        register_goal(self.db_path, self.contract())
        # An unrelated and outdated file does not outrank the SQLite authority.
        (self.root / "SESSION_HANDOFF.md").write_text(
            "# CURRENT P1 - wrong repository - wrong goal", encoding="utf-8")
        code = (
            "import json,sys;from pathlib import Path;"
            "from cognition_agent_os.continuity import resume_goal;"
            "print(json.dumps(resume_goal(Path(sys.argv[1]))))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(self.db_path)], capture_output=True,
            text=True, check=True)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "READY_TO_TICK", result)
        self.assertEqual(result["goal_id"], "cognition-os")
        self.assertEqual(result["next_task_id"], self.first_task)
        self.assertEqual(result["acceptance"], self.contract()["acceptance"])
        self.assertFalse(result["business_outcome_verified"])

    def test_no_registered_goal_is_not_inferred_from_recent_tasks(self):
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "NO_DURABLE_GOAL", result)
        self.assertNotIn("next_task_id", result)

    def test_two_active_goals_do_not_invent_priority(self):
        register_goal(self.db_path, self.contract())
        register_goal(self.db_path, self.contract(name="other-goal"))
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "AMBIGUOUS_ACTIVE_GOALS", result)
        self.assertEqual(result["goal_ids"], ["cognition-os", "other-goal"])
        self.assertNotIn("next_task_id", result)

    def test_revocation_blocks_recovered_next_action(self):
        register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            alter_authority(db, revoke=True)
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "AUTHORITY_REVOKED", result)
        self.assertNotIn("next_task_id", result)
        # Explicit continuation must preserve goal meaning, acceptance, and
        # boundaries after a REVOKE, while never resuming side effects.
        self.assertEqual(result["objective"], self.contract()["objective"])
        self.assertEqual(result["acceptance"], self.contract()["acceptance"])
        self.assertEqual(result["constraints"], self.contract()["constraints"])
        self.assertFalse(result["authority_current"])
        self.assertRegex(result["contract_sha256"], r"^[0-9a-f]{64}$")

    def test_registered_goal_does_not_hide_distinct_current_open_goal(self):
        """Mixed continuity forms cannot silently choose one owner goal."""
        self.assertEqual(register_goal(self.db_path, self.contract())["status"],
                         "REGISTERED")
        different = "Investigate a separate original supplier quality goal."
        with closing(connect(self.db_path)) as db:
            second = create_task(db, {"kind": "open_goal", "goal": different})
            before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "AMBIGUOUS_DURABLE_GOALS", result)
        self.assertNotIn("next_task_id", result)
        self.assertEqual(result["registered_goal"]["objective"],
                         self.contract()["objective"])
        self.assertEqual(result["other_original_goals"], [
            {"root_task_id": second, "original_goal": different}])
        with closing(connect(self.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events")
                             .fetchone()[0], before)

    def test_registered_pointer_into_same_open_goal_is_not_a_second_goal(self):
        """A registered pointer and its original root are one identity."""
        with closing(connect(self.db_path)) as db:
            owner = create_task(db, {
                "kind": "open_goal",
                "goal": "Compare independent fixture evidence carefully."})
        register_goal(self.db_path, self.contract(next_task_id=owner))
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "READY_TO_TICK", result)
        self.assertEqual(result["next_task_id"], owner)

    def test_registered_descendant_resolves_same_open_goal_ancestor(self):
        """An exact registered child and its original root remain one goal."""
        with closing(connect(self.db_path)) as db:
            root = create_task(db, {
                "kind": "open_goal",
                "goal": "Compare original evidence under one persistent goal."})
            db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",
                       (root,))
            child = create_task(db, {
                "kind": "fixture", "old": "before", "new": "after"},
                parent=root)
        register_goal(self.db_path, self.contract(next_task_id=child))
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "READY_TO_TICK", result)
        self.assertEqual(result["next_task_id"], child)

    def test_mixed_goal_ambiguity_preserves_readable_roots_after_revoke(self):
        """Revocation prevents action, not goal restoration or visibility."""
        register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            second = create_task(db, {
                "kind": "open_goal",
                "goal": "Preserve another original goal after write revoke."})
            alter_authority(db, revoke=True)
        state = resume_goal(self.db_path)
        self.assertEqual(state["status"], "AMBIGUOUS_DURABLE_GOALS", state)
        self.assertFalse(state["authority_current"])
        self.assertEqual(state["other_original_goals"][0]["root_task_id"], second)
        self.assertEqual(state["registered_goal"]["constraints"],
                         self.contract()["constraints"])
        self.assertNotIn("next_task_id", state)

    def test_new_goal_revision_requires_explicit_reconciliation(self):
        register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            alter_authority(db, goal_change=True)
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "STALE_GOAL_REVISION", result)
        self.assertNotIn("next_task_id", result)

    def test_remote_head_change_requires_revalidation_not_auto_advance(self):
        source = {"repo": "example/public-repo", "branch": "main",
                  "head_sha": "a"*40}
        register_goal(self.db_path, self.contract(source=source))
        result = resume_goal(
            self.db_path, resolve_head=lambda _repo, _branch: "b"*40)
        self.assertEqual(result["status"], "SOURCE_REVALIDATION_REQUIRED", result)
        self.assertEqual(result["observed_head_sha"], "b"*40)
        self.assertNotIn("next_task_id", result)

    def test_network_outage_does_not_claim_freshness(self):
        source = {"repo": "example/public-repo", "branch": "main",
                  "head_sha": "a"*40}
        register_goal(self.db_path, self.contract(source=source))
        def fail(_repo, _branch):
            raise OSError("unreachable")
        result = resume_goal(self.db_path, resolve_head=fail)
        self.assertEqual(result["status"], "SOURCE_UNAVAILABLE", result)
        self.assertNotIn("next_task_id", result)

    def test_pinned_remote_head_can_resume(self):
        source = {"repo": "example/public-repo", "branch": "main",
                  "head_sha": "a"*40}
        register_goal(self.db_path, self.contract(source=source))
        result = resume_goal(
            self.db_path, resolve_head=lambda _repo, _branch: "a"*40)
        self.assertEqual(result["status"], "READY_TO_TICK", result)

    def test_single_field_contract_corruption_is_not_accepted(self):
        register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            db.execute(
                "UPDATE goal_continuity SET contract=? WHERE goal_id=?",
                ('{"objective":"forged goal"}', "cognition-os"))
            db.commit()
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "INTEGRITY_CONFLICT", result)
        self.assertNotIn("next_task_id", result)

    def test_task_needs_review_not_business_success(self):
        register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            db.execute(
                "UPDATE tasks SET state='VERIFIED' WHERE task_id=?",
                (self.first_task,))
            db.commit()
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "NEEDS_OWNER_OUTCOME_REVIEW", result)
        self.assertFalse(result["business_outcome_verified"])

    def test_duplicate_registration_requires_explicit_checkpoint(self):
        register_goal(self.db_path, self.contract())
        with self.assertRaises(ValueError):
            register_goal(self.db_path, self.contract())

    def test_checkpoint_cas_preserves_existing_identity_and_recovers_new_task(self):
        first = register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            second_task = create_task(
                db, {"kind": "fixture", "old": "new-a", "new": "new-b"})
        second = checkpoint_goal(
            self.db_path, "cognition-os",
            expected_digest=first["contract_sha256"],
            next_task_id=second_task)
        self.assertNotEqual(first["contract_sha256"], second["contract_sha256"])
        with self.assertRaises(ValueError):
            checkpoint_goal(
                self.db_path, "cognition-os",
                expected_digest=first["contract_sha256"],
                next_task_id=self.first_task)
        result = resume_goal(self.db_path)
        self.assertEqual(result["next_task_id"], second_task)
        self.assertEqual(result["status"], "READY_TO_TICK")


    def test_task_future_due_is_not_falsely_runnable(self):
        import time
        with closing(connect(self.db_path)) as db:
            future = create_task(
                db, {"kind":"fixture", "old":"future-a", "new":"future-b"},
                due_at=time.time() + 3600)
        register_goal(self.db_path, self.contract(next_task_id=future))
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "NOT_DUE", result)
        self.assertNotIn("next_task_id", result)

    def test_explicit_remote_reattest_must_match_independent_live_head(self):
        source = {"repo":"example/public-repo", "branch":"main",
                  "head_sha":"a"*40}
        first = register_goal(self.db_path, self.contract(source=source))
        with closing(connect(self.db_path)) as db:
            second_task = create_task(
                db, {"kind":"fixture", "old":"head-a", "new":"head-b"})
        with self.assertRaises(ValueError):
            checkpoint_goal(
                self.db_path, "cognition-os",
                expected_digest=first["contract_sha256"],
                next_task_id=second_task, observed_head_sha="b"*40,
                resolve_head=lambda *_: "c"*40)
        with self.assertRaises(ValueError):
            checkpoint_goal(
                self.db_path, "cognition-os",
                expected_digest=first["contract_sha256"],
                next_task_id=second_task,
                resolve_head=lambda *_: "b"*40)
        second = checkpoint_goal(
            self.db_path, "cognition-os",
            expected_digest=first["contract_sha256"],
            next_task_id=second_task, observed_head_sha="b"*40,
            resolve_head=lambda *_: "b"*40)
        self.assertEqual(second["status"], "CHECKPOINT_COMMITTED")
        result = resume_goal(
            self.db_path, resolve_head=lambda *_: "b"*40)
        self.assertEqual(result["status"], "READY_TO_TICK", result)
        self.assertEqual(result["next_task_id"], second_task)
        self.assertFalse(result["business_outcome_verified"])

    def test_cli_resume_reads_same_canonical_db(self):
        contract_path = self.root / "goal.json"
        contract_path.write_text(
            json.dumps(self.contract()), encoding="utf-8")
        common = [
            sys.executable, "-m", "cognition_agent_os.cli",
            "--db", str(self.db_path),
            "--workspace", str(self.root / "workspace"),
            "--fixtures", str(self.root),
        ]
        created = subprocess.run(
            common + ["seed-continuity", "--spec", str(contract_path)],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(created.stdout)["status"], "REGISTERED")
        recovered = subprocess.run(
            common + ["goal-resume"],
            capture_output=True, text=True, check=True)
        state = json.loads(recovered.stdout)
        self.assertEqual(state["status"], "READY_TO_TICK", state)
        self.assertEqual(state["next_task_id"], self.first_task)

    def test_checkpoint_after_revocation_is_not_allowed(self):
        first = register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            other = create_task(
                db, {"kind":"fixture", "old":"other", "new":"new"})
            alter_authority(db, revoke=True)
        with self.assertRaises(PermissionError):
            checkpoint_goal(
                self.db_path, "cognition-os",
                expected_digest=first["contract_sha256"],
                next_task_id=other)
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "AUTHORITY_REVOKED")


    def test_remote_resolver_runs_outside_sqlite_write_lock(self):
        # The public network can be slow or unavailable. Checking source HEAD
        # must not serialize independent granted jobs behind network latency.
        source = {"repo":"example/public-repo", "branch":"main",
                  "head_sha":"a"*40}
        first = register_goal(self.db_path, self.contract(source=source))
        with closing(connect(self.db_path)) as db:
            second_task = create_task(
                db, {"kind":"fixture", "old":"out", "new":"of-band"})
        def checked_live_head(_repo, _branch):
            with closing(sqlite3.connect(str(self.db_path), timeout=0.05)) as other:
                other.execute("PRAGMA busy_timeout=50")
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
            return "b"*40
        committed = checkpoint_goal(
            self.db_path, "cognition-os",
            expected_digest=first["contract_sha256"],
            next_task_id=second_task, observed_head_sha="b"*40,
            resolve_head=checked_live_head)
        self.assertEqual(committed["status"], "CHECKPOINT_COMMITTED")


    def test_recovered_task_implementation_must_equal_pinned_registration(self):
        register_goal(self.db_path, self.contract())
        with closing(connect(self.db_path)) as db:
            db.execute(
                "UPDATE tasks SET source_spec=? WHERE task_id=?",
                (json.dumps({"kind":"github","repo":"injected/other",
                             "path":"README.md","old_ref":"a"*40,
                             "new_ref":"b"*40}), self.first_task))
            db.commit()
        result = resume_goal(self.db_path)
        self.assertEqual(result["status"], "TASK_LINEAGE_UNVERIFIABLE", result)
        self.assertNotIn("next_task_id", result)


    def test_nested_feature_branch_recovers_via_strict_git_ref_adapter(self):
        source = {"repo": "example/public-repo",
                  "branch": "experiment/feature-branch",
                  "head_sha": "a"*40}
        register_goal(self.db_path, self.contract(source=source))
        with patch(
            "cognition_agent_os.continuity.github_public_branch_head_nested",
            return_value="a"*40
        ) as resolver:
            result = resume_goal(self.db_path)
        resolver.assert_called_once_with(
            "example/public-repo", "experiment/feature-branch")
        self.assertEqual(result["status"], "READY_TO_TICK", result)

    def test_nested_ref_client_checks_exact_identity_and_safe_url(self):
        from cognition_agent_os.source import (
            github_public_branch_head_nested, SourceUnavailable)
        with patch("cognition_agent_os.source.urlopen") as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = (
                json.dumps({"ref":"refs/heads/experiment/feature-branch",
                            "object":{"type":"commit","sha":"a"*40}}).encode()
            )
            sha = github_public_branch_head_nested(
                "example/public-repo", "experiment/feature-branch")
            self.assertEqual(sha, "a"*40)
            self.assertIn(
                "/git/ref/heads/experiment/feature-branch",
                fetch.call_args.args[0].full_url)
        for unsafe in ("../admin", "experiment//feature",
                       "experiment/..", "/feature", "name.lock/x"):
            with self.subTest(branch=unsafe):
                with self.assertRaises(ValueError):
                    github_public_branch_head_nested(
                        "example/public-repo", unsafe)
        with patch("cognition_agent_os.source.urlopen") as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = (
                json.dumps({"ref":"refs/heads/other",
                            "object":{"type":"commit","sha":"a"*40}}).encode()
            )
            with self.assertRaises(SourceUnavailable):
                github_public_branch_head_nested(
                    "example/public-repo", "experiment/feature-branch")


if __name__ == "__main__":
    unittest.main()
