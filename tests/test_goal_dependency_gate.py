"""Evidence-gated ordered local actions through the original Host and SQLite."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

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
        (self.fixtures/"config.json").write_text('{"existing":"keep"}\\n')
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

    def test_bad_source_blocks_not_executes_successor(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        (self.fixtures/"config.json").write_text('{"existing":"changed"}\\n')
        after=run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertFalse(any(x.get("task_id")==second for x in after["tasks"]))
        self.assertNotEqual(self.get(second)["state"],"NEEDS_REVIEW")

    def test_revocation_never_releases_dependency(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        with closing(connect(self.db)) as db:
            alter_authority(db,revoke=True)
        run_tick(self.db,self.workspace,self.fixtures,max_jobs=1)
        self.assertEqual(self.get(second)["state"],"PENDING")

    def test_duplicate_and_reverse_dependency_refused(self):
        first,second=self.tasks()
        register_local_dependency(self.db,first,second)
        with self.assertRaises(ValueError):
            register_local_dependency(self.db,first,second)
        with self.assertRaises(ValueError):
            register_local_dependency(self.db,second,first)


if __name__=="__main__":
    unittest.main()
