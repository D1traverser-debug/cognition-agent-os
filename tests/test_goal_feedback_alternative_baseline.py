"""Prospective baseline: outcome feedback is not yet alternative-route control.

Runs in the existing real SQLite host, never grants external write authority.
The test documents the current behavioral boundary, not an acceptance claim.
"""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize


class GoalFeedbackAlternativeBaseline(unittest.TestCase):
    def test_independent_failure_retries_same_method_not_registered_alternative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fixtures=root/"fixtures"
            workspace=root/"workspace"
            fixtures.mkdir()
            workspace.mkdir()
            dbpath=root/"ledger.sqlite"
            fixtures.joinpath("settings.json").write_text('{"keep":42}')
            fixtures.joinpath("before.csv").write_text("id,amount\\nA,1\\n")
            fixtures.joinpath("after.csv").write_text("id,amount\\nA,2\\n")
            claims={"schema_version":1,"source_id":"baseline",
                    "claims":[{"goal_key":"restore-goal","route":"structure",
                               "status":"active","source_ref":"baseline:1"}]}
            data=json.dumps(claims,sort_keys=True).encode()
            fixtures.joinpath("knowledge.json").write_bytes(data)
            source={"kind":"knowledge_intent","goal_key":"restore-goal",
                    "knowledge":{"path":"knowledge.json",
                                 "sha256":hashlib.sha256(data).hexdigest(),
                                 "source_id":"baseline"},
                    "options":[
                        {"route":"structure","intent":{
                            "kind":"goal_intent","objective":"ensure_structure",
                            "resources":[{"role":"input","path":"settings.json"}],
                            "requirements":[{"field":"owner","equals":"ops"}]}},
                        {"route":"compare","intent":{
                            "kind":"goal_intent","objective":"compare_records",
                            "resources":[{"role":"reference","path":"before.csv"},
                                         {"role":"observed","path":"after.csv"}]}}
                    ]}
            with closing(connect(dbpath)) as db:
                initialize(db)
                top=create_task(db,source)
            initial=run_tick(dbpath,workspace,fixtures,
                             max_jobs=3,auto_stage_goals=True)
            self.assertEqual(initial["tasks"][0]["route"],"structure",initial)
            with closing(connect(dbpath)) as db:
                descendants=db.execute(
                    "SELECT task_id,source_spec,state FROM tasks WHERE task_id != ?",
                    (top,)).fetchall()
                leaf=next(dict(x) for x in descendants
                          if json.loads(x["source_spec"]).get("kind")=="goal_case")
            artifact=workspace/"artifacts"/(leaf["task_id"]+".json")
            self.assertTrue(artifact.is_file(),initial)
            artifact.write_bytes(artifact.read_bytes()+b" tampered")
            observed=run_tick(dbpath,workspace,fixtures,max_jobs=1)
            self.assertEqual(len(observed["local_evidence_retries"]),1,observed)
            self.assertFalse(observed["semantic_outcome_verified"])
            with closing(connect(dbpath)) as db:
                specs=[json.loads(row[0]) for row in
                       db.execute("SELECT source_spec FROM tasks")]
            # The alternative exists as an authorized option but is not
            # autonomously selected after independently detected failure.
            self.assertFalse(any(s.get("kind")=="record_reconciliation"
                                 for s in specs),specs)
            self.assertFalse(any(s.get("kind")=="goal_intent" and
                                 s.get("objective")=="compare_records"
                                 for s in specs),specs)


if __name__=="__main__":
    unittest.main()
