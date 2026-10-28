"""Cross-domain checks for the non-authoritative goal-fidelity Host observer."""
import hashlib
import json
import unittest
from cognition_agent_os.goal_fidelity import check_goal_fidelity


def root(state="DECOMPOSED", kind="open_goal"):
    spec=json.dumps({"kind":kind,"goal":"Build an owner-meaningful result."},sort_keys=True)
    return {"source_spec":spec,"state":state}


def child(kind,state="NEEDS_REVIEW"):
    return {"source_spec":json.dumps({"kind":kind,"scope":"LOCAL_EVIDENCE_ONLY"},
                                     sort_keys=True),"state":state}


class GoalFidelityTests(unittest.TestCase):
    def test_local_research_does_not_pretend_owner_outcome(self):
        r=root()
        checked=check_goal_fidelity(r,[child("investigate_goal")])
        self.assertEqual(checked["fidelity_state"],
                         "EVIDENCE_RESEARCH_ONLY_NOT_OWNER_RESULT")
        self.assertEqual(checked["next_goal_action"],
                         "COMPARE_SUPPORTED_METHODS_WITH_ORIGINAL_GOAL")
        self.assertFalse(checked["owner_outcome_verified"])
        self.assertEqual(checked["root_contract_digest"],
                         hashlib.sha256(r["source_spec"].encode()).hexdigest())

    def test_legitimate_active_work_is_not_wrongly_stopped(self):
        checked=check_goal_fidelity(root("DECOMPOSED"),
                                    [child("goal_case","PENDING")])
        self.assertEqual(checked["fidelity_state"],"LEGAL_WORK_PENDING")
        self.assertEqual(checked["next_goal_action"],"CONTINUE_ADMITTED_WORK")

    def test_duplicates_flagged_but_dont_change_authority(self):
        r=root()
        c=child("goal_case","VERIFIED")
        checked=check_goal_fidelity(r,[c,c.copy()])
        self.assertEqual(checked["fidelity_state"],
                         "REPEATED_CANDIDATE_UNVERIFIED")
        self.assertEqual(checked["repeated_source_spec_count"],1)
        self.assertFalse(checked["owner_outcome_verified"])

    def test_owner_unknown_without_child_needs_new_plan(self):
        checked=check_goal_fidelity(root("UNKNOWN"),[])
        self.assertEqual(checked["fidelity_state"],
                         "OWNER_GOAL_BLOCKED_WITHOUT_RESULT")
        self.assertEqual(checked["next_goal_action"],
                         "RESEARCH_OR_REPLAN_WITH_CURRENT_GRANT")

    def test_successful_mechanical_component_does_not_promote_goal(self):
        checked=check_goal_fidelity(root(),[child("goal_case","VERIFIED")])
        self.assertEqual(checked["fidelity_state"],
                         "LOCAL_WORK_NOT_OWNER_RESULT")
        self.assertFalse(checked["owner_outcome_verified"])

    def test_malformed_original_owner_goal_never_becomes_verified(self):
        checked=check_goal_fidelity({"source_spec":"not-json","state":"VERIFIED"},[])
        self.assertEqual(checked["fidelity_state"],"GOAL_IDENTITY_UNVERIFIABLE")
        self.assertFalse(checked["owner_outcome_verified"])


if __name__=="__main__":
    unittest.main()
