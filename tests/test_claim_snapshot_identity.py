"""M-031 independent claim-definition integrity at execution boundaries.

Real SQLite + real Worker dispatch, with an external transaction changing the
record during proposal generation. No model or nonlocal provider is needed.
"""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from cognition_agent_os.ledger import (
    connect, initialize, create_task, claim_one, renew_claim,
    finalize_observed, live_claim_owner,
)
from cognition_agent_os import runner
from cognition_agent_os.runner import run_once
from cognition_agent_os.intent_runtime import run_intent


class ClaimSnapshotIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'ledger.sqlite'
        self.fixture = self.root / 'fixtures'
        self.fixture.mkdir()
        self.workspace = self.root / 'workspace'
        (self.fixture / 'a').write_bytes(b'identical\n')
        (self.fixture / 'b').write_bytes(b'identical\n')
        with closing(connect(self.path)) as db:
            initialize(db)

    def new_claim(self, spec=None):
        spec = {'kind':'fixture', 'old':'a','new':'b'} if spec is None else spec
        db = connect(self.path)
        tid = create_task(db, spec)
        claim = claim_one(db, only_task_id=tid)
        self.assertIsNotNone(claim)
        return db, claim

    def assert_no_terminal_events(self, db, tid):
        self.assertEqual(db.execute('SELECT COUNT(*) FROM events WHERE task_id=? '
                                    'AND kind=?', (tid, 'FINALIZED')).fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT state FROM tasks WHERE task_id=?',
                                    (tid,)).fetchone()[0], 'RUNNING')

    def test_real_worker_cannot_verify_an_edited_source_definition(self):
        with closing(connect(self.path)) as db:
            tid = create_task(db, {'kind':'fixture','old':'a','new':'b'})
        original_propose = runner.propose
        def change_spec_after_proposal_inputs(old, new, evidence):
            # Mutates the exact claimed row after genuine source comparison,
            # before finalizing. Current source is different and unavailable.
            with closing(connect(self.path)) as other:
                other.execute('UPDATE tasks SET source_spec=?,state_version=state_version+1 '
                              'WHERE task_id=?',
                              (json.dumps({'kind':'fixture','old':'a','new':'missing.txt'}), tid))
                other.commit()
            return original_propose(old,new,evidence)
        with patch.object(runner,'propose',side_effect=change_spec_after_proposal_inputs):
            observed = run_once(self.path, self.workspace, self.fixture,
                                only_task_id=tid)
        self.assertEqual(observed['status'], 'STALE_WORKER')
        with closing(connect(self.path)) as db:
            self.assert_no_terminal_events(db, tid)
            self.assertIsNone(db.execute('SELECT artifact_hash FROM tasks WHERE task_id=?',
                                         (tid,)).fetchone()[0])
        self.assertFalse((self.workspace/'artifacts'/(tid+'.json')).exists())

    def test_source_spec_or_schedule_mutation_blocks_verdict_and_artifact(self):
        for name,value in [('source_spec','{"kind":"fixture","old":"tampered"}'),
                           ('due_at',0), ('interval_seconds',1800)]:
            with self.subTest(column=name):
                with closing(connect(self.path)) as db:
                    tid = create_task(db, {'kind':'fixture','old':'a','new':'b'})
                    claimed = claim_one(db, only_task_id=tid)
                    db.execute('UPDATE tasks SET '+name+'=? WHERE task_id=?',(value,tid))
                    db.commit()
                    effects=[]
                    result = finalize_observed(db,claimed,'VERIFIED',decision='NO_CHANGE',
                            artifact_writer=lambda:effects.append('incorrect') or 'sha')
                    self.assertEqual(result['status'],'STALE_WORKER')
                    self.assertEqual(effects,[])
                    self.assert_no_terminal_events(db,tid)

    def test_renewal_refuses_changed_definition_but_preserves_valid_renewal(self):
        for name,value in [('source_spec','{"kind":"different"}'),('due_at',0),
                           ('interval_seconds',1800)]:
            with self.subTest(column=name):
                with closing(connect(self.path)) as db:
                    tid=create_task(db,{'kind':'fixture','old':'a','new':'b'})
                    claimed=claim_one(db, only_task_id=tid)
                    db.execute('UPDATE tasks SET '+name+'=? WHERE task_id=?',(value,tid))
                    db.commit()
                    self.assertFalse(renew_claim(db, claimed))
                    self.assert_no_terminal_events(db,tid)
        with closing(connect(self.path)) as db:
            tid=create_task(db,{'kind':'fixture','old':'a','new':'b'})
            claimed=claim_one(db,only_task_id=tid)
            self.assertTrue(renew_claim(db,claimed,lease_seconds=90))
            # A worker renewing its own lease increments state_version, but
            # cannot be falsely treated as another goal definition.
            now=db.execute('SELECT * FROM tasks WHERE task_id=?',(tid,)).fetchone()
            self.assertGreater(now['state_version'],claimed['state_version'])
            self.assertTrue(live_claim_owner(now,claimed))
            self.assertEqual(finalize_observed(db,claimed,'VERIFIED',
                decision='NO_CHANGE')['status'], 'VERIFIED')

    def test_direct_decomposition_is_also_fenced_by_task_definition(self):
        spec={'kind':'goal_intent','objective':'ensure_structure',
              'resources':[{'role':'input','path':'a'}],
              'requirements':[{'field':'owner','equals':'ops'}]}
        with closing(connect(self.path)) as db:
            tid=create_task(db,spec)
            claimed=claim_one(db,only_task_id=tid)
            db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",
                       (json.dumps({'kind':'fixture','old':'a','new':'b'}),tid))
            db.commit()
            result=run_intent(db,claimed)
            self.assertEqual(result['status'],'STALE_WORKER')
            self.assert_no_terminal_events(db,tid)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks WHERE parent_task=?',
                         (tid,)).fetchone()[0],0)

if __name__ == '__main__':
    unittest.main()
