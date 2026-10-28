"""Targeted existing-worker claims may not consume unrelated pending work."""
from contextlib import closing
from pathlib import Path
import tempfile
import time
import unittest

from cognition_agent_os.ledger import connect, create_task, initialize, claim_one


class TargetedWorkerClaim(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "state.sqlite"
        with closing(connect(self.db)) as db:
            initialize(db)

    def create(self, *, due_at=None):
        with closing(connect(self.db)) as db:
            return create_task(db, {"kind": "unknown_local_fixture"},
                               due_at=due_at)

    def test_targeted_claim_never_claims_earlier_unrelated_task(self):
        unrelated = self.create()
        target = self.create()
        with closing(connect(self.db)) as db:
            claimed = claim_one(db, only_task_id=target)
            self.assertEqual(claimed["task_id"], target)
            self.assertEqual(db.execute(
                "SELECT state FROM tasks WHERE task_id=?",
                (unrelated,)).fetchone()["state"], "PENDING")
            self.assertIsNone(claim_one(db, only_task_id=target))
            next_claim = claim_one(db)
            self.assertEqual(next_claim["task_id"], unrelated)

    def test_targeted_claim_cannot_be_redirected_when_missing_or_not_due(self):
        unrelated = self.create()
        future = self.create(due_at=time.time() + 86400)
        with closing(connect(self.db)) as db:
            self.assertIsNone(claim_one(db, only_task_id=future))
            self.assertIsNone(claim_one(db, only_task_id="f" * 32))
            self.assertEqual(db.execute(
                "SELECT state FROM tasks WHERE task_id=?", (unrelated,)
            ).fetchone()["state"], "PENDING")
            selected = claim_one(db, only_task_id=unrelated)
            self.assertEqual(selected["task_id"], unrelated)


if __name__ == "__main__":
    unittest.main()
