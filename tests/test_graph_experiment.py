"""Independent graph-failure hypothesis experiments on live temp ledgers.

No production repairs or privilege re-enablement; the observed structural
hypothesis selects a bounded containment strategy, not business semantics.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect,create_task,initialize
from cognition_agent_os.graph_experiment import investigate_dependency_graph
from cognition_agent_os.conformance import inspect_conformance,capability_disabled


class GraphExperimentTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.db_path=self.root/"state.sqlite"
        self.ws=self.root/"work";self.ws.mkdir()
        self.fx=self.root/"fixtures";self.fx.mkdir()
        self.fx.joinpath("config.json").write_text("{}")
        db=connect(self.db_path);initialize(db);db.close()

    def _root(self,db):
        root=create_task(db,{"kind":"goal_intent","objective":"ensure_structure",
                             "resources":[{"role":"input","path":"config.json"}],
                             "requirements":[{"field":"owner","equals":"ops"}]})
        db.execute("UPDATE tasks SET state='DECOMPOSED' WHERE task_id=?",(root,))
        return root

    def _spec(self):
        return {"kind":"goal_case","goal_type":"json_keys",
                "input":"config.json","desired":{"owner":"ops"}}

    def test_independent_graph_oracles_support_multiple_acyclic_shapes(self):
        for n,shape in ((263,"fanout"),(264,"chain"),(275,"branching")):
            with self.subTest(n=n,shape=shape):
                db=connect(self.db_path)
                root=self._root(db)
                ids=[root]
                for i in range(n):
                    parent=(root if shape=="fanout" else
                            ids[-1] if shape=="chain" else
                            ids[(i//3)])
                    ids.append(create_task(db,self._spec(),parent=parent,commit=False))
                db.commit()
                p=investigate_dependency_graph(db,root)
                self.assertEqual(p["status"],"ACYCLIC_GRAPH_PROVEN")
                self.assertEqual(p["action"],"COMPLETE_LOCAL_QUARANTINE")
                self.assertEqual(p["nodes"],n+1)
                self.assertEqual(set(p["descendants"]),set(ids[1:]))
                self.assertEqual(len(p["snapshot_sha256"]),64)
                self.assertTrue(p["hypotheses"][1]["falsified"])
                db.close()
                r=inspect_conformance(self.db_path,self.ws,self.fx,enforce=True,max_cases=16)
                self.assertTrue(any(e["task_id"]==root and e["descendants"]==n
                                    for e in r["quarantined"]))
                self.assertFalse(capability_disabled(self.db_path))

    def test_cycle_distinguished_from_valid_fanout(self):
        db=connect(self.db_path)
        root=self._root(db)
        first=create_task(db,self._spec(),parent=root)
        second=create_task(db,self._spec(),parent=first)
        db.execute("UPDATE tasks SET parent_task=? WHERE task_id=?",(second,root))
        db.commit()
        result=investigate_dependency_graph(db,root)
        self.assertEqual(result["status"],"CYCLE_CONFIRMED")
        self.assertEqual(result["action"],"GLOBAL_FAIL_CLOSED")
        self.assertTrue(result["hypotheses"][0]["falsified"])
        db.close()
        # Graph under 256 nodes is still untrustworthy; normal BFS sees repeat
        # even at small size, triggers independent causal experiment.
        r=inspect_conformance(self.db_path,self.ws,self.fx,enforce=True,max_cases=16)
        self.assertEqual(r["emergency_stops"],[root])
        self.assertTrue(capability_disabled(self.db_path))

    def test_oracle_disagreement_preserves_hard_stop(self):
        db=connect(self.db_path)
        root=self._root(db)
        for i in range(258):
            create_task(db,self._spec(),parent=root,commit=False)
        db.commit()
        from cognition_agent_os import graph_experiment as g
        with patch.object(g,"_sql_closure",return_value=({"an_unrelated_id"},"COMPLETE")):
            result=investigate_dependency_graph(db,root)
            self.assertEqual(result["status"],"ORACLE_DISAGREEMENT")
            self.assertEqual(result["action"],"GLOBAL_FAIL_CLOSED")
            report=inspect_conformance(self.db_path,self.ws,self.fx,
                                      enforce=True,max_cases=1)
        self.assertEqual(report["emergency_stops"],[root])
        self.assertTrue(capability_disabled(self.db_path))
        db.close()

    def test_more_than_hard_experiment_budget_blocks_release(self):
        from cognition_agent_os.graph_experiment import MAX_GRAPH_EXPERIMENT_NODES
        db=connect(self.db_path)
        root=self._root(db)
        for i in range(MAX_GRAPH_EXPERIMENT_NODES+2):
            create_task(db,self._spec(),parent=root,commit=False)
        db.commit()
        result=investigate_dependency_graph(db,root)
        self.assertEqual(result["status"],"UNVERIFIABLE")
        self.assertEqual(result["action"],"GLOBAL_FAIL_CLOSED")
        db.close()
        report=inspect_conformance(self.db_path,self.ws,self.fx,
                                   enforce=True,max_cases=1)
        self.assertEqual(report["emergency_stops"],[root])
        self.assertTrue(capability_disabled(self.db_path))


if __name__=="__main__":
    unittest.main()
