"""Evidence-gated ordered local actions through the original Host and SQLite."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority
from cognition_agent_os.goal_audit import audit_goal
from cognition_agent_os.dependency_gate import register_local_dependency


class OrderedEvidenceGateTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.db=self.root/"state.db"
        self.workspace=self.root/"workspace"
        self.fixtures=self.root/"sources"
        self.fixtures.mkdir()
        (self.fixtures/"config.json").write_text('{"existing":"keep"}\n')
        with closing(connect(self.db)) as db:
            initialize(db)

    def tasks(self):
        with closing(connect(self.db)) as db:
            first=create_task(db,{"kind":"goal_case","goal_type":"json_keys",
                "input":"config.json","desired":{"diagnostic":"ready"}})
            second=create_task(db,{"kind":"goal_case","goal_type":"json_keys",
                "input":"config.json","desired":{"next_step":"draft"}})
        return first,second

    def get(self, task_id):
        with closing(connect(self.db)) as db:
            return db.execute("SELECT * FROM tasks WHERE task_id=?",
                              (task_id,)).fetchone()

    def test_predecessor_evidence_gates_later_candidate_across_host_ticks(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        start=run_tick(self.db,self.workspace,self.fixtures,max_jobs=2)
        self.assertEqual([x["status"] for x in start["tasks"]],["NEEDS_REVIEW"])
        self.assertEqual(self.get(second)["state"],"PENDING")
        self.assertEqual(audit_goal(self.db,self.workspace,self.fixtures,first)["status"],
                         "CANDIDATE_MECHANICALLY_VALID")
        next_run=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(next_run["tasks"][0]["task_id"],second)
        self.assertEqual(next_run["tasks"][0]["status"],"NEEDS_REVIEW")
        self.assertEqual(audit_goal(self.db,self.workspace,self.fixtures,second)["status"],
                         "CANDIDATE_MECHANICALLY_VALID")
        self.assertEqual(json.loads((self.fixtures/"config.json").read_text()),
                         {"existing":"keep"})

    def test_released_successor_retracted_when_predecessor_invalidated(self):
        """A formerly admitted sibling result cannot outlive source revocation."""
        from cognition_agent_os.conformance import inspect_conformance
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(self.get(first)["state"],"NEEDS_REVIEW")
        self.assertEqual(self.get(second)["state"],"NEEDS_REVIEW")
        before=inspect_conformance(self.db,self.workspace,self.fixtures)
        states={x["task_id"]:x for x in before["findings"]}
        self.assertEqual(states[first]["disposition"],"PASS",before)
        self.assertEqual(states[second]["disposition"],"PASS",before)
        with closing(connect(self.db)) as db:
            db.execute("UPDATE tasks SET state='UNKNOWN',error_code='SOURCE_WITHDRAWN' "
                       "WHERE task_id=?",(first,))
            db.commit()
        found=inspect_conformance(self.db,self.workspace,self.fixtures)
        findings={x["task_id"]:x for x in found["findings"]}
        self.assertEqual(findings[second]["disposition"],
                         "CONFIRMED_INCONSISTENCY",found)
        self.assertEqual(findings[second]["proof"],
                         "DEPENDENCY_PREDECESSOR_INVALIDATED")
        inspect_conformance(self.db,self.workspace,self.fixtures,enforce=True)
        self.assertEqual(self.get(second)["state"],"UNKNOWN")
        self.assertEqual(self.get(second)["error_code"],
                         "CONFORMANCE_DEPENDENCY_PREDECESSOR_INVALIDATED")

    def test_unavailable_predecessor_source_does_not_forge_contradiction(self):
        """An outage is UNKNOWN, not automatically a confirmed false result."""
        from cognition_agent_os.conformance import inspect_conformance
        (self.fixtures/"other.json").write_text("{}")
        with closing(connect(self.db)) as db:
            first=create_task(db,{"kind":"goal_case","goal_type":"json_keys",
                "input":"config.json","desired":{"diagnostic":"ready"}})
            second=create_task(db,{"kind":"goal_case","goal_type":"json_keys",
                "input":"other.json","desired":{"next_step":"draft"}})
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        (self.fixtures/"config.json").unlink()
        checked=inspect_conformance(self.db,self.workspace,self.fixtures)
        findings={x["task_id"]:x for x in checked["findings"]}
        self.assertEqual(findings[second]["proof"],
                         "DEPENDENCY_PREDECESSOR_EVIDENCE_UNVERIFIABLE",checked)
        self.assertEqual(findings[second]["disposition"],"INSUFFICIENT_EVIDENCE")
        self.assertNotEqual(findings[second]["disposition"],"PASS")
        self.assertEqual(self.get(second)["state"],"NEEDS_REVIEW")

    def test_bad_source_blocks_not_executes_successor(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        (self.fixtures/"config.json").write_text('{"existing":"changed"}\n')
        after=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertFalse(any(x.get("task_id")==second for x in after["tasks"]))
        self.assertEqual(self.get(second)["state"],"NEEDS_REPLAN")
        self.assertEqual(self.get(second)["error_code"],
                         "PREDECESSOR_EVIDENCE_UNVERIFIABLE")
        self.assertTrue(any(x["status"]=="DEPENDENCY_REPLAN_REQUIRED"
                            for x in after["dependency_observations"]))

    def test_unknown_predecessor_does_not_leave_successor_waiting_forever(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        with closing(connect(self.db)) as db:
            db.execute("UPDATE tasks SET state='UNKNOWN',error_code='NO_SAFE_GOAL_PLAN' "
                       "WHERE task_id=?",(first,))
            db.commit()
        observed=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(self.get(second)["state"],"NEEDS_REPLAN")
        self.assertTrue(any(
            x.get("reason")=="PREDECESSOR_NOT_VERIFIED"
            for x in observed["dependency_observations"]))

    def test_forged_release_cannot_bypass_independent_worker_readback(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        with closing(connect(self.db)) as db:
            db.execute("UPDATE task_dependencies SET released_at=1 "
                       "WHERE task_id=?",(second,))
            db.execute("UPDATE tasks SET state='UNKNOWN',error_code='PROBE' "
                       "WHERE task_id=?",(first,))
            db.commit()
        final=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(final["tasks"][0]["task_id"],second)
        self.assertEqual(final["tasks"][0]["status"],"UNKNOWN")
        self.assertEqual(self.get(second)["error_code"],
                         "PREDECESSOR_EVIDENCE_CHANGED")
        self.assertFalse((self.workspace/"artifacts"/(second+".json")).exists())

    def test_revocation_never_releases_dependency(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(self.get(second)["state"],"PENDING")

    def test_source_race_after_gate_release_is_rechecked_by_worker(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        from cognition_agent_os.dependency_gate import advance_pending_local_dependencies
        def invalidate_after_audit(*args,**kwargs):
            observed=advance_pending_local_dependencies(*args,**kwargs)
            self.assertTrue(any(x["status"]=="DEPENDENCY_RELEASED_LOCAL_ONLY"
                                for x in observed))
            (self.fixtures/"config.json").write_text('{"existing":"changed"}\n')
            return observed
        with patch("cognition_agent_os.dependency_gate.advance_pending_local_dependencies",
                   side_effect=invalidate_after_audit):
            result=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(result["tasks"][0]["task_id"],second)
        self.assertEqual(result["tasks"][0]["status"],"UNKNOWN")
        self.assertEqual(self.get(second)["error_code"],
                         "PREDECESSOR_EVIDENCE_CHANGED")
        self.assertFalse((self.workspace/"artifacts"/(second+".json")).exists())

    def test_legacy_authoritative_db_without_dependency_table_still_runs(self):
        # Existing installed ledgers did not have this table. This cannot
        # silently create a second database or break the original worker.
        with closing(connect(self.db)) as db:
            db.execute("DROP TABLE task_dependencies")
            db.commit()
        first,second=self.tasks()
        result=run_tick(self.db,self.workspace,self.fixtures,max_jobs=2)
        self.assertEqual([x["status"] for x in result["tasks"]],
                         ["NEEDS_REVIEW","NEEDS_REVIEW"],result)
        self.assertEqual(self.get(first)["state"],"NEEDS_REVIEW")
        self.assertEqual(self.get(second)["state"],"NEEDS_REVIEW")

    def test_revoke_after_release_before_worker_blocks_effect(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        from cognition_agent_os.dependency_gate import advance_pending_local_dependencies
        def revoke_after_audit(*args,**kwargs):
            observed=advance_pending_local_dependencies(*args,**kwargs)
            self.assertTrue(any(
                x["status"]=="DEPENDENCY_RELEASED_LOCAL_ONLY" for x in observed))
            with closing(connect(self.db)) as db:
                alter_authority(db,revoke=True)
            return observed
        with patch("cognition_agent_os.dependency_gate.advance_pending_local_dependencies",
                   side_effect=revoke_after_audit):
            result=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(result["tasks"][0]["task_id"],second)
        self.assertEqual(result["tasks"][0]["status"],"BLOCKED")
        self.assertFalse((self.workspace/"artifacts"/(second+".json")).exists())

    def test_duplicate_and_reverse_dependency_refused(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        with self.assertRaises(ValueError):
            register_local_dependency(self.db,first,second)
        with self.assertRaises(ValueError):
            register_local_dependency(self.db,second,first)


if __name__=="__main__":
    unittest.main()
