"""Independent regression: a controller cannot re-admit an orphaned attempt.

A one-sided loss of the attempt index must not leave its PENDING child live
and permit a second ordinal-zero admission. This models accidental corruption
within the local SQLite trust boundary, not a privileged attacker forging
both the database and the source receipts.
"""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cognition_agent_os.bounded_goal_control import (
    advance_local_goals, register_local_goal,
)
from cognition_agent_os.conformance import inspect_conformance
from cognition_agent_os.ledger import connect, initialize


class ControlAttemptLineageIntegrity(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.dbpath = root / "ledger.sqlite"
        self.fixtures = root / "fixtures"
        self.fixtures.mkdir()
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        (self.fixtures / "first.json").write_text(
            '{"id":"A","owner":"wrong"}', encoding="utf-8")
        (self.fixtures / "second.csv").write_text(
            "id\nA\n", encoding="utf-8")
        with closing(connect(self.dbpath)) as db:
            initialize(db)
        self.root_id = register_local_goal(
            self.dbpath, self.fixtures, goal_id="owner-record",
            target={"id": "A", "owner": "ops"},
            alternatives=[
                {"kind": "goal_case", "goal_type": "json_keys",
                 "input": "first.json", "desired": {"owner": "ops"}},
                {"kind": "goal_case", "goal_type": "csv_columns",
                 "input": "second.csv", "desired": {"owner": "ops"}},
            ],
        )
        first = advance_local_goals(
            self.dbpath, self.workspace, self.fixtures, limit=1)
        self.assertEqual(first[0]["status"], "ADMITTED_LOCAL_ATTEMPT")
        self.child_id = first[0]["child_task_id"]

    def corrupt_attempt_index(self):
        with closing(connect(self.dbpath)) as db:
            db.execute(
                "DELETE FROM bounded_goal_attempts WHERE root_task_id=?",
                (self.root_id,))
            db.commit()

    def test_intact_active_control_remains_admitted(self):
        result = inspect_conformance(
            self.dbpath, self.workspace, self.fixtures,
            enforce=False, max_cases=64)
        finding = next(
            x for x in result["findings"] if x["task_id"] == self.root_id)
        self.assertEqual(finding["disposition"], "PASS", finding)

    def test_orphaned_child_is_detected_and_quarantined_by_host_gate(self):
        self.corrupt_attempt_index()
        result = inspect_conformance(
            self.dbpath, self.workspace, self.fixtures,
            enforce=True, max_cases=64)
        finding = next(
            x for x in result["findings"] if x["task_id"] == self.root_id)
        self.assertEqual(
            finding["disposition"], "CONFIRMED_INCONSISTENCY", finding)
        self.assertIn(
            self.root_id, [r["task_id"] for r in result["quarantined"]])
        with closing(connect(self.dbpath)) as db:
            root_state = db.execute(
                "SELECT state FROM tasks WHERE task_id=?",
                (self.root_id,)).fetchone()[0]
            child_state = db.execute(
                "SELECT state FROM tasks WHERE task_id=?",
                (self.child_id,)).fetchone()[0]
        self.assertEqual(root_state, "UNKNOWN")
        self.assertIn(child_state, ("BLOCKED", "UNKNOWN"))

    def test_orphaned_child_never_gets_duplicate_ordinal_zero(self):
        self.corrupt_attempt_index()
        advanced = advance_local_goals(
            self.dbpath, self.workspace, self.fixtures, limit=1)
        self.assertFalse(any(
            x.get("status") == "ADMITTED_LOCAL_ATTEMPT" for x in advanced),
            advanced)
        with closing(connect(self.dbpath)) as db:
            children = [
                r[0] for r in db.execute(
                    "SELECT task_id FROM tasks WHERE parent_task=?",
                    (self.root_id,)).fetchall()]
            root_state = db.execute(
                "SELECT state FROM tasks WHERE task_id=?",
                (self.root_id,)).fetchone()[0]
        self.assertEqual(children, [self.child_id])
        self.assertEqual(root_state, "CONTROL_UNVERIFIABLE")

    def test_orphaned_admission_receipt_is_detected(self):
        self.corrupt_attempt_index()
        with closing(connect(self.dbpath)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM events WHERE task_id=? "
                "AND kind='BOUNDED_CONTROLLER_ADMITTED'",
                (self.root_id,)).fetchone()[0], 1)
        report = inspect_conformance(
            self.dbpath, self.workspace, self.fixtures,
            enforce=False, max_cases=64)
        root = next(
            x for x in report["findings"] if x["task_id"] == self.root_id)
        self.assertNotEqual(root["disposition"], "PASS", root)
