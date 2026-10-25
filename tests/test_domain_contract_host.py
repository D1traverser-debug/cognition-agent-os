"""Real Host/Worker/SQLite child contract intake, independent live-source re-read.

Network transport is replaced in these tests only. The runtime uses the
existing commit-pinned public-GitHub adapter; it never writes child repositories.
"""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.domain_contract import (
    FILES, audit_domain_contract, observe_native_domain)
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority


SHA = "a" * 40


def make_native(domain_id: str, repo: str, *, controller="D1traverser-debug/universal-agent-os@main"):
    manifest = {
        "domain_id": domain_id, "schema_version": "2.5",
        "controller": controller,
        "binding": {"adapter_ref": FILES[1], "capability_ref": FILES[2]},
        "domain_authority": {"native_task_state": "child-only", "owner": domain_id},
    }
    adapter = {
        "domain_id": domain_id, "schema_version": "2.2",
        "controller": controller, "business_state_authority": "child-only",
    }
    caps = {
        "domain_id": domain_id, "schema_version": "3.2",
        "repository": repo,
        "capabilities": [{"capability_id": "native_governed_workflow"}],
    }
    return {path: json.dumps(doc, sort_keys=True).encode("utf-8")
            for path, doc in zip(FILES, (manifest, adapter, caps))}


class DomainContractHostIntegration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "ledger.sqlite"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        with closing(connect(self.db)) as db:
            initialize(db)

    def seed(self, domain="video", repo=None):
        repo = repo or "D1traverser-debug/" + domain + "-agent"
        spec = {"kind": "domain_contract", "domain_id": domain,
                "repo": repo, "ref": SHA}
        with closing(connect(self.db)) as db:
            tid = create_task(db, spec)
        return tid, spec

    @staticmethod
    def mock(docs):
        def read(repo, path, ref):
            if path not in docs or ref != SHA:
                raise RuntimeError("fetch exceeded declared child scope")
            return docs[path]
        return patch("cognition_agent_os.domain_contract.github_public_snapshot",
                     side_effect=read)

    def tick(self):
        return run_tick(self.db, self.workspace, self.fixtures, max_jobs=1)

    def read_state(self, task_id):
        with closing(connect(self.db)) as db:
            return dict(db.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())

    def test_four_native_domains_and_a_future_unregistered_domain(self):
        domains = (
            ("video", "video-growth-agent"),
            ("financial_writing", "financial-writing-agent"),
            ("novel", "novel-writing-agent"),
            ("ashare", "a-share-event-driven-agent"),
            ("podcast", "future-podcast-agent"),
        )
        for domain, name in domains:
            with self.subTest(domain=domain):
                # Use separate ledger per domain, so no previous reviewed task
                # changes which pending task the real Worker claims.
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    dbpath = root / "ledger.sqlite"
                    ws = root / "workspace"
                    ws.mkdir()
                    fx = root / "fixtures"
                    fx.mkdir()
                    repo = "D1traverser-debug/" + name
                    docs = make_native(domain, repo)
                    with closing(connect(dbpath)) as db:
                        initialize(db)
                        tid = create_task(db, {
                            "kind": "domain_contract", "domain_id": domain,
                            "repo": repo, "ref": SHA})
                    with self.mock(docs):
                        tick = run_tick(dbpath, ws, fx, max_jobs=1)
                        audit = audit_domain_contract(dbpath, ws, tid)
                    self.assertEqual(tick["tasks"][0]["status"],
                                     "NEEDS_REVIEW", tick)
                    self.assertEqual(audit["status"],
                                     "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED", audit)
                    self.assertTrue(audit["legacy_parent_bound"])
                    self.assertFalse(audit["parent_replacement_admitted"])
                    self.assertFalse(audit["child_business_result_verified"])
                    evidence = json.loads(
                        (ws / "artifacts" / (tid + ".json")).read_text())
                    self.assertEqual(evidence["observation"]["domain_id"], domain)
                    self.assertEqual(evidence["observation"]["capability_count"], 1)
                    self.assertFalse(evidence["observation"]["child_business_state_modified"])

    def test_child_changes_after_worker_observation_fail_independent_readback(self):
        tid, spec = self.seed()
        original = make_native("video", spec["repo"])
        with self.mock(original):
            self.tick()
        changed = dict(original)
        newer = json.loads(changed[FILES[2]])
        newer["capabilities"].append({"capability_id": "new_domain_method"})
        changed[FILES[2]] = json.dumps(newer, sort_keys=True).encode()
        with self.mock(changed):
            audit = audit_domain_contract(self.db, self.workspace, tid)
        self.assertEqual(audit["status"], "NOT_ADMITTED", audit)
        self.assertEqual(audit["reason"], "CHILD_CONTRACT_CHANGED")

    def test_no_false_admission_after_local_receipt_tampered(self):
        tid, spec = self.seed()
        docs = make_native("video", spec["repo"])
        with self.mock(docs):
            self.tick()
            path = self.workspace / "artifacts" / (tid + ".json")
            path.write_text('{"forged":"ok"}\n', encoding="utf-8")
            audit = audit_domain_contract(self.db, self.workspace, tid)
        self.assertEqual(audit["reason"], "RECEIPT_TAMPERED", audit)

    def test_conflicting_native_controllers_fail_before_receipt(self):
        tid, spec = self.seed()
        docs = make_native("video", spec["repo"])
        adapter = json.loads(docs[FILES[1]])
        adapter["controller"] = "future-parent-not-currently-admitted"
        docs[FILES[1]] = json.dumps(adapter).encode()
        with self.mock(docs):
            processed = self.tick()["tasks"][0]
        self.assertEqual(processed["status"], "UNKNOWN", processed)
        self.assertFalse((self.workspace / "artifacts").exists())

    def test_mismatched_domain_and_repo_fail_no_import_no_child_write(self):
        tid, spec = self.seed()
        docs = make_native("ashare", spec["repo"])
        with self.mock(docs):
            processed = self.tick()["tasks"][0]
        self.assertEqual(processed["status"], "UNKNOWN", processed)
        self.assertNotIn("next_task_id", processed)
        self.assertFalse((self.workspace / "artifacts").exists())

    def test_revoke_blocks_local_artifact_and_independent_admission(self):
        tid, spec = self.seed()
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        docs = make_native("video", spec["repo"])
        with self.mock(docs):
            result = self.tick()
        self.assertEqual(result["tasks"][0]["status"], "BLOCKED", result)
        self.assertFalse((self.workspace / "artifacts").exists())
        self.assertEqual(audit_domain_contract(self.db, self.workspace, tid)
                         ["status"], "NOT_ADMITTED")

    def test_revoke_after_observation_cancels_independent_admission(self):
        tid, spec = self.seed()
        docs = make_native("video", spec["repo"])
        with self.mock(docs):
            self.tick()
        with closing(connect(self.db)) as db:
            alter_authority(db, revoke=True)
        with self.mock(docs):
            audit = audit_domain_contract(self.db, self.workspace, tid)
        self.assertEqual(audit["reason"], "AUTHORITY_CHANGED", audit)

    def test_only_exact_pinned_sha_and_repo_not_untrusted_url(self):
        tid, spec = self.seed()
        invalid = dict(spec, ref="main")
        with self.assertRaises(ValueError):
            observe_native_domain(invalid)
        invalid = dict(spec, repo="https://evil.invalid/steal")
        with self.assertRaises(ValueError):
            observe_native_domain(invalid)
        invalid = dict(spec, domain_id="VIDEO/../../")
        with self.assertRaises(ValueError):
            observe_native_domain(invalid)
