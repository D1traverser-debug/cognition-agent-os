"""P5 post-action independent-mechanics audit, including compromised proposer."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import connect, initialize, create_task, alter_authority
from cognition_agent_os.runner import run_once
from cognition_agent_os.goal_audit import audit_goal
from cognition_agent_os.goal_loop import validate_goal


class GoalAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.fx=self.home/"fx";self.fx.mkdir()
        self.out=self.home/"out"
        self.db=self.home/"state.sqlite"
        db=connect(self.db);initialize(db);db.close()

    def seed(self,kind,name,desired):
        db=connect(self.db)
        try:
            return create_task(db,validate_goal({"kind":"goal_case","goal_type":kind,
                                                 "input":name,"desired":desired}))
        finally: db.close()

    def audit(self,tid):
        return audit_goal(self.db,self.out,self.fx,tid)

    def test_valid_json_proposal_checked_against_source(self):
        (self.fx/"config.json").write_text('{"port":8080}')
        tid=self.seed("json_keys","config.json",{"port":8080,"owner":"ops"})
        self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"NEEDS_REVIEW")
        r=self.audit(tid)
        self.assertEqual(r["status"],"CANDIDATE_MECHANICALLY_VALID")
        self.assertTrue(r["mechanical_audit"])
        self.assertFalse(r["authorizes_source_mutation"])
        self.assertFalse(r["semantic_goal_achieved"])

    def test_valid_csv_proposal_checked_separately(self):
        (self.fx/"rows.csv").write_text("id,cycle\nA,1\n")
        tid=self.seed("csv_columns","rows.csv",{"pass":"UNKNOWN"})
        self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"NEEDS_REVIEW")
        self.assertEqual(self.audit(tid)["status"],"CANDIDATE_MECHANICALLY_VALID")

    def test_tampered_artifact_fails(self):
        (self.fx/"config.json").write_text("{}")
        tid=self.seed("json_keys","config.json",{"owner":"ops"})
        run_once(self.db,self.out,self.fx)
        path=self.out/"artifacts"/(tid+".json")
        path.write_bytes(path.read_bytes()+b"tamper")
        self.assertEqual(self.audit(tid)["status"],"ARTIFACT_HASH_MISMATCH")

    def test_post_proposal_source_change_rejected(self):
        src=self.fx/"config.json";src.write_text("{}")
        tid=self.seed("json_keys","config.json",{"owner":"ops"})
        run_once(self.db,self.out,self.fx)
        src.write_text('{"new":"external"}')
        self.assertEqual(self.audit(tid)["status"],"SOURCE_CHANGED_SINCE_PROPOSAL")

    def test_revocation_or_goal_change_blocks_audit_authority(self):
        (self.fx/"config.json").write_text("{}")
        tid=self.seed("json_keys","config.json",{"owner":"ops"})
        run_once(self.db,self.out,self.fx)
        db=connect(self.db);alter_authority(db,revoke=True);db.close()
        self.assertEqual(self.audit(tid)["status"],"STALE_AUTHORITY")

    def test_compromised_planner_cannot_fool_separate_checker(self):
        """Simulate all internal checks being wrong: separate audit must reject."""
        src=self.fx/"config.json";src.write_text('{"critical":"keep"}')
        tid=self.seed("json_keys","config.json",{"owner":"ops"})
        import cognition_agent_os.goal_loop as gl
        original=gl._candidates
        def dishonest(kind,parsed,desired):
            return [("NO_OP",None),("ADD_MISSING_JSON_KEYS",b'{"owner":"ops"}\n')]
        with patch.object(gl,"_candidates",side_effect=dishonest), \
             patch.object(gl,"_check_candidate",side_effect=lambda *args:args[2]!=b'{"critical":"keep"}'):
            r=run_once(self.db,self.out,self.fx)
        # Compromised code can create a plausible-looking non-destructive claim;
        # actual separate checker reads before+after and rejects the false claim.
        self.assertEqual(r["status"],"NEEDS_REVIEW")
        self.assertEqual(self.audit(tid)["status"],"CANDIDATE_CONSTRAINTS_FAILED")

    def test_bad_task_id_and_uninitialized_db_never_create_file(self):
        bad_db=self.home/"missing.sqlite"
        self.assertEqual(audit_goal(bad_db,self.out,self.fx,"a"*32)["status"],"TASK_NOT_FOUND")
        self.assertFalse(bad_db.exists())
        self.assertEqual(audit_goal(self.db,self.out,self.fx,"../../etc/passwd")["status"],"INVALID_TASK_ID")

    def test_no_op_task_has_no_mutating_proposal(self):
        (self.fx/"config.json").write_text('{"owner":"ops"}')
        tid=self.seed("json_keys","config.json",{"owner":"ops"})
        self.assertEqual(run_once(self.db,self.out,self.fx)["status"],"VERIFIED")
        self.assertEqual(self.audit(tid)["status"],"TASK_NOT_PENDING_REVIEW")


if __name__=="__main__":
    unittest.main()
