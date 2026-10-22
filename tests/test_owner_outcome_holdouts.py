"""Synthetic black-box acceptance against live local host output.

Owner contract is set independently before running the worker; oracle never
imports agent planner/checker code or trusts its status claims.
"""
from __future__ import annotations
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"evaluation"))
from owner_outcome_oracle import assess_route_fitness,evaluate_outcome
from cognition_agent_os.ledger import connect,create_task,initialize
from cognition_agent_os.runner import run_once


class OwnerPinnedBlackboxHoldouts(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.fixtures=self.root/"fixtures"
        self.fixtures.mkdir()
        self.workspace=self.root/"workspace"
        self.workspace.mkdir()
        self.dbpath=self.root/"ledger.sqlite"
        with closing(connect(self.dbpath)) as db:
            initialize(db)

    def observe_live_candidate(self,filename,data,kind,desired):
        self.fixtures.joinpath(filename).write_bytes(data)
        with closing(connect(self.dbpath)) as db:
            tid=create_task(db,{"kind":"goal_case","goal_type":kind,
                                "input":filename,"desired":desired})
        result=run_once(self.dbpath,self.workspace,self.fixtures)
        self.assertEqual(result["status"],"NEEDS_REVIEW",result)
        # Give oracle only bytes, not task state, claim of success, or planner score.
        doc=json.loads((self.workspace/"artifacts"/(tid+".json")).read_text(encoding="utf-8"))
        return doc["candidate_text"].encode("utf-8")

    @staticmethod
    def owner_contract(key,kind,original,expected):
        return {"schema_version":1,"goal_id":key,"kind":kind,
                "expected":expected,"original_sha256":hashlib.sha256(original).hexdigest(),
                "allowed_effect":"LOCAL_CANDIDATE_ONLY"}

    def test_json_config_actual_host_candidate_independent_outcome(self):
        original=b'{"port":1234,"debug":false}'
        contract=self.owner_contract("config-owner","json_fields",original,{"owner":"ops"})
        candidate=self.observe_live_candidate("config.json",original,"json_keys",{"owner":"ops"})
        ok=evaluate_outcome(contract,original,candidate)
        self.assertEqual(ok["status"],"SYNTHETIC_POSTCONDITION_MET",ok)
        self.assertFalse(ok["business_outcome_verified"])
        self.assertFalse(ok["authorizes_mutation"])
        self.assertEqual(self.fixtures.joinpath("config.json").read_bytes(),original)
        changed=json.loads(candidate)
        changed["port"]=9999
        self.assertEqual(evaluate_outcome(contract,original,json.dumps(changed).encode())
                         ["status"],"NOT_ACCEPTED")
        changed=json.loads(candidate)
        changed["extra"]="unauthorized"
        self.assertEqual(evaluate_outcome(contract,original,json.dumps(changed).encode())
                         ["status"],"NOT_ACCEPTED")

    def test_csv_dv_coverage_actual_host_candidate_independent_outcome(self):
        original=b"case,cycles\nA,10\nB,20\n"
        contract=self.owner_contract("dv-coverage-columns","csv_columns",original,
                                     {"passed":"NOT_RUN"})
        candidate=self.observe_live_candidate("coverage.csv",original,"csv_columns",
                                              {"passed":"NOT_RUN"})
        ok=evaluate_outcome(contract,original,candidate)
        self.assertEqual(ok["status"],"SYNTHETIC_POSTCONDITION_MET",ok)
        self.assertFalse(ok["business_outcome_verified"])
        self.assertEqual(self.fixtures.joinpath("coverage.csv").read_bytes(),original)
        bad=candidate.replace(b"A,10,NOT_RUN",b"A,8,NOT_RUN")
        self.assertEqual(evaluate_outcome(contract,original,bad)["status"],"NOT_ACCEPTED")
        self.assertEqual(evaluate_outcome(contract,original,
                         b"case,cycles,passed\nA,10,NOT_RUN\n")["status"],"NOT_ACCEPTED")

    def test_contract_rejects_drift_invalid_types_and_forged_claims(self):
        original=b'{"x":1}'
        contract=self.owner_contract("bounded-json","json_fields",original,{"active":True})
        candidate=b'{"x":1,"active":true}'
        self.assertEqual(evaluate_outcome(contract,b'{"x":2}',candidate)["reason"],
                         "ORIGINAL_DRIFT")
        self.assertEqual(evaluate_outcome(contract,original,
                         b'{"x":1,"active":1}')["status"],"NOT_ACCEPTED")
        self.assertEqual(evaluate_outcome(contract,original,
                         b'{"x":1,"x":1,"active":true}')["status"],"NOT_ACCEPTED")
        self.assertEqual(evaluate_outcome(dict(contract,allowed_effect="PRODUCTION_WRITE"),
                         original,candidate)["status"],"NOT_ACCEPTED")
        self.assertFalse(evaluate_outcome(contract,original,candidate)
                         ["business_outcome_verified"])

    def test_two_route_labels_are_not_a_same_goal_proof(self):
        one={"kind":"goal_intent","objective":"ensure_structure",
             "resources":[{"role":"input","path":"settings.json"}],
             "requirements":[{"field":"owner","equals":"ops"}]}
        other={"kind":"goal_intent","objective":"compare_records",
               "resources":[{"role":"reference","path":"before.csv"},
                            {"role":"observed","path":"after.csv"}]}
        differing=assess_route_fitness([{"route":"structure","intent":one},
                                       {"route":"compare","intent":other}])
        self.assertEqual(differing["reason"],"DIFFERENT_OBJECTIVES")
        self.assertFalse(differing["safe_to_autoswitch"])
        duplicated=assess_route_fitness([{"route":"structure","intent":one},
                                        {"route":"compare","intent":dict(one)}])
        self.assertEqual(duplicated["reason"],"DUPLICATE_METHOD")
        self.assertFalse(duplicated["safe_to_autoswitch"])

    def test_local_contract_cannot_claim_real_world_result(self):
        original=b'{"port":1}'
        contract=self.owner_contract("real-business","json_fields",original,{"owner":"ops"})
        result=evaluate_outcome(contract,original,b'{"port":1,"owner":"ops"}')
        self.assertEqual(result["evidence_class"],"SYNTHETIC_LOCAL_TARGET")
        self.assertFalse(result["business_outcome_verified"])


if __name__=="__main__":
    unittest.main()
