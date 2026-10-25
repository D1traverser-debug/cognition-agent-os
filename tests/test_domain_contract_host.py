"""Real Host/Worker/SQLite child contract intake, independent live-source re-read.

Network transport is replaced in these tests only. The runtime uses the
existing commit-pinned public-GitHub adapter; it never writes child repositories.
"""
from contextlib import closing
import json
import os
import subprocess
import sys
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
        "skill": {"entrypoint": "UAOS_SKILL.md"},
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
    docs = {path: json.dumps(doc, sort_keys=True).encode("utf-8")
            for path, doc in zip(FILES, (manifest, adapter, caps))}
    docs["UAOS_SKILL.md"] = f"# {domain_id} native entry\n".encode("utf-8")
    return docs


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
                    self.assertEqual(evidence["observation"]["advertised_capability_ids"],
                                     ["native_governed_workflow"])
                    self.assertEqual(evidence["observation"]["declared_skill_entrypoint"],
                                     "UAOS_SKILL.md")
                    self.assertIn("UAOS_SKILL.md",
                                  evidence["observation"]["source_sha256"])
                    self.assertTrue(evidence["observation"]
                                    ["advertisement_is_not_execution_grant"])
                    self.assertFalse(evidence["observation"]["child_business_state_modified"])

    def test_child_owned_business_checkpoints_from_video_and_novel_real_host(self):
        """Two different native state schemas use their OWN declared refs and IDs."""
        cases=(
            ("video", "video-growth-agent", "integrated_default_program",
             "projects/ai-self-media-commercialization/PROGRAM_STATE.json",
             {"program_id":"ai-self-media-commercialization","status":"ACTIVE",
              "current_focus":"ORIGINAL_DIGITAL_IP/H1_SCULPTURAL_MASSING_V2"}),
            ("novel", "novel-writing-agent", "study_state_ref",
             "research/masterworks/STUDY_STATE.json",
             {"status":"ACTIVE","active_work":{"work_id":"GUI_CHUI_DENG",
              "status":"ACTIVE__PAUSED_BY_USER_AT_SAFE_CHECKPOINT"}}),
        )
        for domain, name, key, path, state in cases:
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                dbpath=root/"ledger.sqlite"
                ws=root/"work";ws.mkdir()
                fx=root/"fixtures";fx.mkdir()
                repo="D1traverser-debug/"+name
                docs=make_native(domain,repo)
                manifest=json.loads(docs[FILES[0]])
                manifest["domain_authority"][key]=path
                docs[FILES[0]]=json.dumps(manifest).encode()
                docs[path]=json.dumps(state,ensure_ascii=False).encode()
                with closing(connect(dbpath)) as db:
                    initialize(db)
                    tid=create_task(db,{"kind":"domain_contract",
                        "domain_id":domain,"repo":repo,"ref":SHA,
                        "state_authority_key":key})
                with self.mock(docs):
                    tick=run_tick(dbpath,ws,fx,max_jobs=1)
                    review=audit_domain_contract(dbpath,ws,tid)
                self.assertEqual(tick["tasks"][0]["status"],"NEEDS_REVIEW",tick)
                self.assertEqual(review["status"],
                    "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED",review)
                observed=review["child_native_state_observation"]
                self.assertEqual(observed["child_declared_state_ref"],path)
                self.assertEqual(observed["status_from_child_source"],"ACTIVE")
                self.assertEqual(observed["authority_key"],key)
                self.assertTrue(observed["status_is_not_parent_business_acceptance"])
                self.assertFalse(review["child_business_result_verified"])
                self.assertFalse(review["parent_replacement_admitted"])
                self.assertFalse((fx/path).exists())
                self.assertEqual(len(list((ws/"artifacts").iterdir())),1)

    def test_child_state_change_after_parent_readback_fails_closed(self):
        repo="D1traverser-debug/video-growth-agent"
        tid, spec=self.seed(domain="video",repo=repo)
        with closing(connect(self.db)) as db:
            db.execute("UPDATE tasks SET source_spec=? WHERE task_id=?",(
                json.dumps({**spec,"state_authority_key":"project_index"}),tid))
            db.commit()
        docs=make_native("video",repo)
        manifest=json.loads(docs[FILES[0]])
        manifest["domain_authority"]["project_index"]="projects/PROJECT_INDEX.json"
        docs[FILES[0]]=json.dumps(manifest).encode()
        docs["projects/PROJECT_INDEX.json"]=b'{"status":"ACTIVE","projects":[]}'
        with self.mock(docs):
            self.assertEqual(self.tick()["tasks"][0]["status"],"NEEDS_REVIEW")
        docs2=dict(docs)
        docs2["projects/PROJECT_INDEX.json"]=b'{"status":"HOLD","projects":[]}'
        with self.mock(docs2):
            independent=audit_domain_contract(self.db,self.workspace,tid)
        self.assertEqual(independent["status"],"NOT_ADMITTED",independent)
        self.assertEqual(independent["reason"],"CHILD_CONTRACT_CHANGED",independent)

    def test_child_cannot_redirect_parent_to_undeclared_or_escaping_state(self):
        repo="D1traverser-debug/video-growth-agent"
        for bad in (None,"../secret.json","https://evil.example/state.json",
                    "projects/<task>/STATE.json"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); dbpath=root/"db.sqlite";ws=root/"work";ws.mkdir()
                fx=root/"fixtures";fx.mkdir()
                docs=make_native("video",repo)
                if bad is not None:
                    manifest=json.loads(docs[FILES[0]])
                    manifest["domain_authority"]["project_index"]=bad
                    docs[FILES[0]]=json.dumps(manifest).encode()
                with closing(connect(dbpath)) as db:
                    initialize(db)
                    create_task(db,{"kind":"domain_contract","domain_id":"video",
                       "repo":repo,"ref":SHA,"state_authority_key":"project_index"})
                with self.mock(docs):
                    result=run_tick(dbpath,ws,fx,max_jobs=1)["tasks"][0]
                self.assertEqual(result["status"],"UNKNOWN",result)
                self.assertFalse((ws/"artifacts").exists())

    def test_child_state_is_data_not_an_executable_grant(self):
        repo="D1traverser-debug/video-growth-agent"
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);dbpath=root/"db.sqlite";ws=root/"work";ws.mkdir()
            fx=root/"fixtures";fx.mkdir()
            docs=make_native("video",repo)
            manifest=json.loads(docs[FILES[0]])
            manifest["domain_authority"]["project_index"]="projects/PROJECT_INDEX.json"
            docs[FILES[0]]=json.dumps(manifest).encode()
            docs["projects/PROJECT_INDEX.json"]=json.dumps({
                "status":"READY","execute":"delete-production-assets",
                "parent_authorized":True}).encode()
            with closing(connect(dbpath)) as db:
                initialize(db)
                tid=create_task(db,{"kind":"domain_contract","domain_id":"video",
                    "repo":repo,"ref":SHA,"state_authority_key":"project_index"})
            with self.mock(docs):
                result=run_tick(dbpath,ws,fx,max_jobs=1)["tasks"][0]
                audit=audit_domain_contract(dbpath,ws,tid)
            self.assertEqual(result["status"],"NEEDS_REVIEW",result)
            self.assertFalse(audit["child_business_result_verified"])
            self.assertFalse(audit["parent_replacement_admitted"])
            self.assertNotIn("execute",str(audit["child_native_state_observation"]))

    def test_native_entrypoint_missing_is_not_admitted(self):
        tid, spec = self.seed()
        docs = make_native("video", spec["repo"])
        docs["UAOS_SKILL.md"] = b""
        with self.mock(docs):
            result = self.tick()["tasks"][0]
        self.assertEqual(result["status"], "UNKNOWN", result)
        self.assertFalse((self.workspace / "artifacts").exists())

    def test_native_entrypoint_path_must_not_escape_child_repository(self):
        tid, spec = self.seed()
        docs = make_native("video", spec["repo"])
        manifest = json.loads(docs[FILES[0]])
        manifest["skill"]["entrypoint"] = "../private.md"
        docs[FILES[0]] = json.dumps(manifest).encode()
        with self.mock(docs):
            result = self.tick()["tasks"][0]
        self.assertEqual(result["status"], "UNKNOWN", result)
        self.assertFalse((self.workspace / "artifacts").exists())

    def test_changed_skill_blocks_independent_readback(self):
        tid, spec = self.seed()
        docs = make_native("video", spec["repo"])
        with self.mock(docs):
            self.tick()
        altered = dict(docs)
        altered["UAOS_SKILL.md"] = b"# different entrypoint\\n"
        with self.mock(altered):
            verdict = audit_domain_contract(self.db, self.workspace, tid)
        self.assertEqual(verdict["reason"], "CHILD_CONTRACT_CHANGED", verdict)

    def test_duplicate_or_untyped_capability_not_a_valid_method_catalog(self):
        for invalid in ("duplicate", "untyped"):
            with self.subTest(invalid=invalid):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    db = root / "ledger.sqlite"
                    ws = root / "workspace"
                    ws.mkdir()
                    fx = root / "fixtures"
                    fx.mkdir()
                    with closing(connect(db)) as conn:
                        initialize(conn)
                        create_task(conn, {"kind": "domain_contract",
                            "domain_id": "video", "repo": "D1traverser-debug/video-growth-agent",
                            "ref": SHA})
                    docs = make_native("video", "D1traverser-debug/video-growth-agent")
                    caps = json.loads(docs[FILES[2]])
                    caps["capabilities"] = ([
                        {"capability_id": "native_governed_workflow"},
                        {"capability_id": "native_governed_workflow"}]
                        if invalid == "duplicate" else ["plain-string-not-interface"])
                    docs[FILES[2]] = json.dumps(caps).encode()
                    with self.mock(docs):
                        got = run_tick(db, ws, fx, max_jobs=1)["tasks"][0]
                    self.assertEqual(got["status"], "UNKNOWN", got)
                    self.assertFalse((ws / "artifacts").exists())

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

    def test_real_cli_seeds_same_worker_domain_readback_without_extra_grant(self):
        repo = "D1traverser-debug/video-growth-agent"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        cmd = [
            sys.executable, "-m", "cognition_agent_os.cli",
            "--db", str(self.db),
            "--workspace", str(self.workspace),
            "--fixtures", str(self.fixtures),
            "seed-domain-contract", "--repo", repo,
            "--ref", SHA, "--domain-id", "video",
        ]
        process = subprocess.run(
            cmd, text=True, capture_output=True, env=env, timeout=12)
        self.assertEqual(process.returncode, 0, process.stderr)
        intake = json.loads(process.stdout)
        self.assertEqual(intake["scope"],
                         "PUBLIC_CHILD_SOURCE_READ_LOCAL_REVIEW_ONLY")
        self.assertFalse(intake["parent_replacement_admitted"])
        tid = intake["task_id"]
        docs = make_native("video", repo)
        with self.mock(docs):
            tick = self.tick()
            reviewed = audit_domain_contract(self.db, self.workspace, tid)
        self.assertEqual(tick["tasks"][0]["status"], "NEEDS_REVIEW")
        self.assertEqual(reviewed["status"],
                         "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED")
        self.assertFalse(reviewed["child_business_result_verified"])
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tasks").fetchone()[0], 1)

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
