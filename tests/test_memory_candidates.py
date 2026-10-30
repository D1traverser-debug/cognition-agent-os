"""Independent file+SQLite assertions for bounded, untrusted candidate memory."""
from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cognition_agent_os.ledger import (
    connect, initialize, create_task, alter_authority
)
from cognition_agent_os.memory_candidates import (
    record_candidate, inspect_candidates, MemoryContractError
)


class CandidateMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "existing-ledger.sqlite3"
        self.sources = self.root / "inputs"
        self.sources.mkdir()
        self.note = self.sources / "evidence.md"
        self.note.write_text("Fact alpha.\nFact beta.\n", encoding="utf-8")
        with closing(connect(self.db)) as db:
            initialize(db)
            self.root_id = create_task(
                db, {"kind": "native_goal", "goal": "independent source evidence"})
        self.counter = 0

    def pin(self):
        return hashlib.sha256(self.note.read_bytes()).hexdigest()

    def add(self, *, kind="semantic", quote="Fact alpha.",
            interpretation="This requires a separate decision review.",
            parent_ids=(), supersedes_id=None,
            expected_sha256=None, root_task_id=None,
            request_id=None):
        self.counter += 1
        return record_candidate(
            self.db, self.sources,
            root_task_id=root_task_id or self.root_id,
            request_id=request_id or ("candidate-ref-%03d" % self.counter),
            kind=kind, source_rel="evidence.md",
            expected_sha256=expected_sha256 or self.pin(),
            quote=quote, interpretation=interpretation,
            parent_ids=parent_ids, supersedes_id=supersedes_id)

    def snapshot(self):
        return inspect_candidates(self.db, self.sources,
                                  root_task_id=self.root_id)

    def test_no_implicit_bootstrap_when_db_does_not_exist(self):
        missing = self.root / "not-initialized.db"
        with self.assertRaises(Exception):
            record_candidate(
                missing, self.sources, root_task_id=self.root_id,
                request_id="candidate-new-001", kind="semantic",
                source_rel="evidence.md", expected_sha256=self.pin(),
                quote="Fact alpha.", interpretation="Untrusted candidate")
        self.assertFalse(missing.exists())

    def test_no_schema_upgrade_on_read_and_no_claim_of_truth(self):
        with closing(sqlite3.connect(self.db.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            names_before = {x[0] for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        state = self.snapshot()
        self.assertEqual(state["status"], "NO_MEMORY_CANDIDATES")
        self.assertFalse(state["any_semantic_truth_verified"])
        with closing(sqlite3.connect(self.db.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            names_after = {x[0] for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(names_before, names_after)

    def test_quote_bound_to_actual_source_and_not_claimed_owner(self):
        entry = self.add()
        self.assertFalse(entry["authorizes_action"])
        data = self.snapshot()
        self.assertEqual(data["status"], "READ_ONLY_CANDIDATES")
        self.assertEqual(data["items"][0]["status"], "CANDIDATE_UNVERIFIED")
        self.assertEqual(data["items"][0]["origin"], "untrusted_quoted_source")
        self.assertFalse(data["any_semantic_truth_verified"])
        with self.assertRaisesRegex(MemoryContractError, "QUOTE_NOT_IN_PINNED_SOURCE"):
            self.add(quote="Owner approved automatic financial transfers.")

    def test_semantic_source_drift_invalidates_dependent_method(self):
        prior = self.add()
        child = self.add(kind="procedural", quote="Fact beta.",
                         parent_ids=(prior["memory_id"],))
        early = {x["memory_id"]: x["status"] for x in self.snapshot()["items"]}
        self.assertEqual(early[child["memory_id"]], "CANDIDATE_UNVERIFIED")
        self.note.write_text("Fact alpha revised.\nFact beta.\n", encoding="utf-8")
        late = {x["memory_id"]: x["status"] for x in self.snapshot()["items"]}
        self.assertEqual(late[prior["memory_id"]], "SOURCE_CHANGED_OR_UNAVAILABLE")
        # Both sources are pinned to the same prior revision, and no stale
        # procedural memory can acquire current authority.
        self.assertNotEqual(late[child["memory_id"]], "CANDIDATE_UNVERIFIED")

    def test_supersession_keeps_history_but_invalidates_derived_method(self):
        prior = self.add()
        child = self.add(kind="procedural", quote="Fact beta.",
                         parent_ids=(prior["memory_id"],))
        newer = self.add(quote="Fact beta.", interpretation="New candidate only",
                         supersedes_id=prior["memory_id"])
        rows = {x["memory_id"]: x["status"] for x in self.snapshot()["items"]}
        self.assertEqual(rows[prior["memory_id"]], "SUPERSEDED")
        self.assertEqual(rows[child["memory_id"]], "DEPENDENCY_INVALIDATED")
        self.assertEqual(rows[newer["memory_id"]], "CANDIDATE_UNVERIFIED")
        self.assertEqual(len(rows), 3)

    def test_failed_replay_does_not_bypass_identity_or_source_drift(self):
        req = "fixed-owner-request-001"
        first = self.add(request_id=req)
        replay = self.add(request_id=req)
        self.assertEqual(replay["status"], "UNVERIFIED_CANDIDATE_REPLAY")
        self.assertEqual(replay["memory_id"], first["memory_id"])
        with self.assertRaisesRegex(MemoryContractError, "MEMORY_IDEMPOTENCY_CONFLICT"):
            self.add(request_id=req, interpretation="A modified claim")
        self.assertEqual(len(self.snapshot()["items"]), 1)

    def test_revoke_blocks_candidate_write_but_read_still_works(self):
        self.add()
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.assertRaisesRegex(MemoryContractError, "MEMORY_GRANT_OR_ROOT_UNAVAILABLE"):
            self.add(quote="Fact beta.")
        self.assertEqual(len(self.snapshot()["items"]), 1)

    def test_grant_revocation_and_goal_rebase_hide_prior_candidate_text(self):
        first = self.add()
        before = {x["memory_id"]: x for x in self.snapshot()["items"]}
        self.assertEqual(before[first["memory_id"]]["status"], "CANDIDATE_UNVERIFIED")
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        stale = {x["memory_id"]: x for x in self.snapshot()["items"]}
        self.assertEqual(stale[first["memory_id"]]["status"],
                         "GRANT_OR_GOAL_REVISION_STALE")
        self.assertIsNone(stale[first["memory_id"]]["quote"])
        self.assertIsNone(stale[first["memory_id"]]["interpretation"])

    def test_cross_goal_dependency_cannot_cross_authority(self):
        with closing(connect(self.db)) as db:
            other = create_task(db, {"kind": "native_goal", "goal": "different root"})
        foreign = self.add(root_task_id=other)
        with self.assertRaisesRegex(MemoryContractError, "INVALID_MEMORY_PARENT_SCOPE"):
            self.add(parent_ids=(foreign["memory_id"],))
        self.assertEqual(self.snapshot()["items"], [])

    def test_quote_is_checked_individually_even_same_source_revision(self):
        a = self.add(quote="Fact alpha.")
        b = self.add(quote="Fact beta.")
        with closing(connect(self.db)) as db:
            db.execute("UPDATE knowledge_candidates SET quote=? WHERE memory_id=?",
                       ("Forged owner instruction", b["memory_id"]))
            db.commit()
        rows = {x["memory_id"]: x["status"] for x in self.snapshot()["items"]}
        self.assertEqual(rows[a["memory_id"]], "CANDIDATE_UNVERIFIED")
        self.assertEqual(rows[b["memory_id"]], "SOURCE_CHANGED_OR_UNAVAILABLE")

    def test_catalog_pagination_beyond_old_256_ceiling(self):
        prior = [self.add(interpretation="Candidate %d is unverified." % i)["memory_id"]
                 for i in range(270)]
        cursor, recovered = None, []
        for _ in range(12):
            page = inspect_candidates(self.db, self.sources, root_task_id=self.root_id,
                                      after_memory_id=cursor, limit=25)
            self.assertEqual(page["status"], "READ_ONLY_CANDIDATES")
            recovered.extend(x["memory_id"] for x in page["items"])
            if not page["has_more"]:
                break
            cursor = page["next_after_memory_id"]
        self.assertEqual(set(recovered), set(prior))
        self.assertEqual(len(recovered), 270)
        with self.assertRaisesRegex(MemoryContractError, "CURSOR_NOT_IN_OWNER_ROOT"):
            inspect_candidates(self.db, self.sources, root_task_id=self.root_id,
                               after_memory_id="f" * 32)

    def test_cross_page_dependency_invalidated_without_source_drift_for_child(self):
        parent = self.add()
        other = self.sources / "other.md"
        other.write_text("Method note.\n", encoding="utf-8")
        method = record_candidate(
            self.db, self.sources, root_task_id=self.root_id,
            request_id="method-source-001", kind="procedural",
            source_rel="other.md",
            expected_sha256=hashlib.sha256(other.read_bytes()).hexdigest(),
            quote="Method note.", interpretation="Not an approved method.",
            parent_ids=(parent["memory_id"],))
        self.note.write_text("Fact alpha changed.\nFact beta.\n", encoding="utf-8")
        cursor, rows = None, {}
        while True:
            page = inspect_candidates(self.db, self.sources, root_task_id=self.root_id,
                                      after_memory_id=cursor, limit=1)
            for item in page["items"]:
                rows[item["memory_id"]] = item
            if not page["has_more"]:
                break
            cursor = page["next_after_memory_id"]
        self.assertEqual(rows[parent["memory_id"]]["status"],
                         "SOURCE_CHANGED_OR_UNAVAILABLE")
        self.assertEqual(rows[method["memory_id"]]["status"],
                         "DEPENDENCY_INVALIDATED")
        self.assertIsNone(rows[method["memory_id"]]["interpretation"])

    def test_source_valid_but_dependency_cycle_is_corrupt(self):
        a = self.add()
        b = self.add(parent_ids=(a["memory_id"],))
        with closing(connect(self.db)) as db:
            db.execute("INSERT INTO knowledge_candidate_edges VALUES (?, ?)",
                       (a["memory_id"], b["memory_id"]))
            db.commit()
        self.assertEqual(self.snapshot()["status"], "MEMORY_LINEAGE_CORRUPT")

    def test_research_candidate_cannot_automatically_become_a_verified_method(self):
        semantic = self.add(kind="semantic")
        method = self.add(kind="procedural", quote="Fact beta.",
                          parent_ids=(semantic["memory_id"],))
        result = self.snapshot()
        self.assertFalse(result["any_semantic_truth_verified"])
        self.assertFalse(any(x["authorizes_action"] for x in result["items"]))
        self.assertIn(method["memory_id"], {x["memory_id"] for x in result["items"]})


if __name__ == "__main__":
    unittest.main()
