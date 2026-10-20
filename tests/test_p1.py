"""Real subprocess + SQLite + isolated filesystem. NOT a cloud/LLM acceptance suite."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from cognition_agent_os.ledger import connect, create_task, initialize, alter_authority, claim_one
from cognition_agent_os.runner import run_once, verify_artifact
from cognition_agent_os.source import git_blob_sha, safe_fixture

ROOT = Path(__file__).resolve().parents[1]


class P1Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.fx = self.home / "fixtures"
        self.fx.mkdir()
        (self.fx / "same.txt").write_text("same data\n")
        (self.fx / "old.txt").write_text("source v1\n")
        (self.fx / "new.txt").write_text("source v2\n")
        self.dbpath = self.home / "state.sqlite"
        self.out = self.home / "out"
        db = connect(self.dbpath)
        initialize(db)
        db.close()

    def seed(self, *, old="old.txt", new="new.txt", interval=0):
        db = connect(self.dbpath)
        try:
            return create_task(db, {"kind": "fixture", "old": old, "new": new}, interval_seconds=interval)
        finally:
            db.close()

    def records(self):
        db = connect(self.dbpath)
        try:
            return ([dict(r) for r in db.execute("SELECT * FROM tasks ORDER BY created_at")],
                    [dict(r) for r in db.execute("SELECT * FROM events ORDER BY event_id")])
        finally:
            db.close()

    def execute_once(self, *, fail_at=None):
        return run_once(self.dbpath, self.out, self.fx, fail_at=fail_at)

    def child(self, command="worker-once", fail_at=None):
        argv = [sys.executable, "-m", "cognition_agent_os.cli", "--db", str(self.dbpath),
                "--workspace", str(self.out), "--fixtures", str(self.fx), command]
        if fail_at:
            argv += ["--fail-at", fail_at]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)

    def test_no_change_is_verified_without_fake_report(self):
        self.seed(old="same.txt",new="same.txt")
        r=self.execute_once()
        self.assertEqual((r["status"],r["decision"]),("VERIFIED","NO_CHANGE"))
        self.assertFalse((self.out / "artifacts").exists())

    def test_change_requires_review_and_integrity(self):
        tid = self.seed()
        r=self.execute_once()
        self.assertEqual(r["status"],"NEEDS_REVIEW")
        self.assertEqual(r["semantic_review"],"NOT_PERFORMED")
        db=connect(self.dbpath)
        task=dict(db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone())
        db.close()
        self.assertTrue(verify_artifact(self.out,task))
        doc=json.loads((self.out/"artifacts"/(tid+".json")).read_text())
        self.assertEqual(doc["source"]["old_blob"],git_blob_sha(b"source v1\n"))
        self.assertEqual(doc["proposal"]["decision"],"CHANGE_REQUIRES_REVIEW")

    def test_source_error_unknown(self):
        self.seed(new="missing.txt")
        r=self.execute_once()
        self.assertEqual(r["status"],"UNKNOWN")
        self.assertFalse((self.out/"artifacts").exists())

    def test_revoke_blocks_write_but_no_change_read_continues(self):
        self.seed()
        self.seed(old="same.txt",new="same.txt")
        db=connect(self.dbpath)
        alter_authority(db,revoke=True)
        db.close()
        out1=self.execute_once();out2=self.execute_once()
        self.assertEqual(out1["status"],"BLOCKED")
        self.assertEqual(out2["status"],"VERIFIED")
        self.assertFalse((self.out/"artifacts").exists())

    def test_goal_revision_prevents_old_task(self):
        self.seed()
        db=connect(self.dbpath)
        alter_authority(db,goal_change=True)
        db.close()
        self.assertEqual(self.execute_once()["status"],"BLOCKED")

    def test_duplicate_worker_single_claim(self):
        tid=self.seed()
        results=[]
        barrier=threading.Barrier(2)
        def worker():
            db=connect(self.dbpath)
            barrier.wait()
            row=claim_one(db)
            results.append(row["task_id"] if row else None)
            db.close()
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(results.count(tid),1)
        self.assertEqual(results.count(None),1)

    def test_claim_crash_then_recover_other_process(self):
        tid=self.seed()
        p=self.child(fail_at="after_claim")
        self.assertEqual(p.returncode,78,p.stderr)
        db=connect(self.dbpath)
        db.execute("UPDATE tasks SET lease_until=0 WHERE task_id=?",(tid,)); db.commit();db.close()
        p=self.child()
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"],"NEEDS_REVIEW")

    def test_crash_after_artifact_before_commit_reconciles(self):
        tid=self.seed()
        p=self.child(fail_at="after_artifact_before_commit")
        self.assertEqual(p.returncode,79,p.stderr)
        payload=(self.out/"artifacts"/(tid+".json")).read_bytes()
        db=connect(self.dbpath)
        self.assertEqual(db.execute("SELECT state FROM tasks WHERE task_id=?",(tid,)).fetchone()["state"],"RUNNING")
        db.execute("UPDATE tasks SET lease_until=0 WHERE task_id=?",(tid,));db.commit();db.close()
        p=self.child()
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"],"NEEDS_REVIEW")
        self.assertEqual(payload,(self.out/"artifacts"/(tid+".json")).read_bytes())
        self.assertEqual(len(list((self.out/"artifacts").glob("*"))),1)

    def test_tamper_before_retry_is_unknown(self):
        tid=self.seed()
        p=self.child(fail_at="after_artifact_before_commit")
        self.assertEqual(p.returncode,79)
        (self.out/"artifacts"/(tid+".json")).write_text("malicious")
        db=connect(self.dbpath);db.execute("UPDATE tasks SET lease_until=0 WHERE task_id=?",(tid,));db.commit();db.close()
        self.assertEqual(self.execute_once()["status"],"UNKNOWN")
        self.assertEqual(self.records()[0][0]["error_code"],"ARTIFACT_CONFLICT")

    def test_recurrence_is_pending_not_host_wakeup(self):
        self.seed(old="same.txt",new="same.txt",interval=3600)
        r=self.execute_once()
        self.assertEqual(r["status"],"VERIFIED")
        tasks,events=self.records()
        self.assertEqual(len(tasks),2)
        self.assertEqual(tasks[1]["state"],"PENDING")
        self.assertGreater(tasks[1]["due_at"],time.time())
        self.assertEqual(self.execute_once()["status"],"IDLE")

    def test_deny_fixture_escape_and_symlink(self):
        outside=self.home/"secret.txt";outside.write_text("private")
        with self.assertRaises(ValueError):safe_fixture(self.fx,"../secret.txt")
        (self.fx/"link.txt").symlink_to(outside)
        with self.assertRaises(ValueError):safe_fixture(self.fx,"link.txt")

    def test_fake_remote_details_invalid(self):
        from cognition_agent_os.source import github_public_snapshot
        with self.assertRaises(ValueError):github_public_snapshot("https://evil.test/xx","file.txt","f"*40)
        with self.assertRaises(ValueError):github_public_snapshot("owner/repo","../env","f"*40)
        with self.assertRaises(ValueError):github_public_snapshot("owner/repo","file.txt","main")


    def test_revoke_mid_source_fetch_blocks_precommit_write(self):
        from unittest.mock import patch
        import cognition_agent_os.runner as runner
        self.seed()
        read_real = runner.get_pair
        calls = [0]
        def fetch_then_revoke(spec, root):
            old, new, evidence = read_real(spec, root)
            calls[0] += 1
            if calls[0] == 2:
                db = connect(self.dbpath)
                alter_authority(db, revoke=True)
                db.close()
            return old, new, evidence
        with patch.object(runner, "get_pair", side_effect=fetch_then_revoke):
            result = self.execute_once()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "WRITE_GRANT_REVOKED")
        self.assertFalse((self.out / "artifacts").exists())

    def test_tampered_completed_artifact_fails_independent_readback(self):
        tid = self.seed()
        self.assertEqual(self.execute_once()["status"],"NEEDS_REVIEW")
        db = connect(self.dbpath)
        task = dict(db.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone())
        db.close()
        artifact = self.out / "artifacts" / (tid+".json")
        artifact.write_bytes(artifact.read_bytes()+b"tamper")
        self.assertFalse(verify_artifact(self.out, task))

    def test_github_content_sha_independently_checked(self):
        from unittest.mock import patch
        from cognition_agent_os.source import github_public_snapshot, SourceUnavailable
        import base64
        from io import BytesIO
        data=b"# checked bytes\n"
        payload=json.dumps({"type":"file","encoding":"base64",
            "content":base64.b64encode(data).decode(),"sha":git_blob_sha(data)}).encode()
        with patch("cognition_agent_os.source.urlopen") as fn:
            response=fn.return_value.__enter__.return_value
            response.read.return_value=payload
            self.assertEqual(github_public_snapshot("owner/repo", "doc.md", "f"*40),data)
        tampered=json.dumps({"type":"file","encoding":"base64",
            "content":base64.b64encode(data).decode(),"sha":"0"*40}).encode()
        with patch("cognition_agent_os.source.urlopen") as fn:
            fn.return_value.__enter__.return_value.read.return_value=tampered
            with self.assertRaises(SourceUnavailable):
                github_public_snapshot("owner/repo", "doc.md", "f"*40)

    def test_two_real_subprocesses_do_not_duplicate_local_artifact(self):
        tid=self.seed()
        argv=[sys.executable,"-m","cognition_agent_os.cli","--db",str(self.dbpath),
              "--workspace",str(self.out),"--fixtures",str(self.fx),"worker-once"]
        env=os.environ.copy();env["PYTHONPATH"]=str(ROOT/"src")
        workers=[subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,text=True) for _ in range(2)]
        results=[]
        for w in workers:
            stdout,stderr=w.communicate(timeout=15)
            self.assertEqual(w.returncode,0,stderr)
            results.append(json.loads(stdout))
        self.assertEqual(sorted(x["status"] for x in results),["IDLE","NEEDS_REVIEW"])
        self.assertEqual(len(list((self.out/"artifacts").glob("*.json"))),1)

    def test_git_blob_matches_known_sha(self):
        self.assertEqual(git_blob_sha(b"hello\n"),"ce013625030ba8dba906f756967f9e9ca394464a")


if __name__ == "__main__":
    unittest.main()