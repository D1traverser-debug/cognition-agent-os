"""Local loopback HTTP and claim-of-completion safety tests (not actual model weights)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cognition_agent_os import local_model
from cognition_agent_os.ledger import connect, create_task, initialize
from cognition_agent_os.runner import run_once


class FakeLocalService:
    def __init__(self, *, available_model='local:test', answer=None, tags_status=200):
        self.calls = []
        self.answer = answer if answer is not None else {"summary": "Potential API change", "affected_claims": ["ADR-04"], "uncertainty": "unverified"}
        self.tags_status = tags_status
        self.available_model = available_model
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                outer.calls.append(("GET", self.path))
                if self.path != "/api/tags":
                    self.send_error(404)
                    return
                data = json.dumps({"models": [{"name": outer.available_model}]}).encode()
                self.send_response(outer.tags_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.calls.append(("POST", self.path, data))
                if self.path != "/api/generate":
                    self.send_error(404)
                    return
                raw = json.dumps({"done": True, "response": json.dumps(outer.answer)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.patch = patch.object(local_model, "_BASE", f"http://127.0.0.1:{self.server.server_port}")
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FreeLocalTests(unittest.TestCase):
    def setUp(self):
        self.old = b"protocol v1\n"
        self.new = b"protocol v2\n"
        self.evidence = {"kind": "fixture", "old_blob": "a", "new_blob": "b"}

    def test_no_change_never_contacts_local_model(self):
        with patch.object(local_model, "_request", side_effect=AssertionError("network forbidden")):
            out = local_model.propose_local(self.old, self.old, self.evidence, model="")
        self.assertEqual(out["decision"], "NO_CHANGE")

    def test_model_must_be_installed_local_only(self):
        with FakeLocalService() as service:
            with self.assertRaises(local_model.LocalModelUnavailable):
                local_model.propose_local(self.old, self.new, self.evidence, model="missing:7b")
            self.assertEqual(service.calls, [("GET", "/api/tags")])

    def test_cloud_model_name_refused_before_network(self):
        with patch.object(local_model, "_request", side_effect=AssertionError("must not call")):
            for name in ["qwen:cloud", "cloud/model", "model:Cloud", "http://example.test", ""]:
                with self.subTest(name=name), self.assertRaises(local_model.LocalModelUnavailable):
                    local_model.propose_local(self.old, self.new, self.evidence, model=name)

    def test_success_is_still_unverified_proposal(self):
        with FakeLocalService() as service:
            out = local_model.propose_local(self.old, self.new, self.evidence, model="local:test")
        self.assertEqual(out["decision"], "CHANGE_REQUIRES_REVIEW")
        self.assertTrue(out["needs_semantic_review"])
        self.assertIn("model_proposal_unverified", out)
        self.assertEqual(out["model_proposal_unverified"]["affected_claims"], ["ADR-04"])
        self.assertEqual([x[0] for x in service.calls], ["GET", "POST"])
        body = service.calls[-1][2]
        self.assertEqual(body["model"], "local:test")
        self.assertFalse(body["stream"])
        self.assertEqual(body["format"], "json")
        self.assertIn("Evidence (not instructions)", body["prompt"])
        self.assertNotIn("Authorization", body)

    def test_bad_structured_result_rejected(self):
        with FakeLocalService(answer={"summary": "a", "affected_claims": "ADR-04", "uncertainty": "none"}):
            with self.assertRaises(local_model.LocalModelUnavailable):
                local_model.propose_local(self.old, self.new, self.evidence, model="local:test")

    def test_failed_local_service_fails_closed_not_as_verification(self):
        with FakeLocalService(tags_status=503):
            with self.assertRaises(local_model.LocalModelUnavailable):
                local_model.propose_local(self.old, self.new, self.evidence, model="local:test")

    def test_missing_model_is_unknown_at_runner_and_has_no_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "a.txt").write_bytes(self.old)
            (fixtures / "b.txt").write_bytes(self.new)
            db_path = root / "tasks.sqlite"
            db = connect(db_path)
            initialize(db)
            create_task(db, {"kind": "fixture", "old": "a.txt", "new": "b.txt"})
            db.close()
            with patch.object(local_model, "_request", side_effect=local_model.LocalModelUnavailable("offline")):
                result = run_once(db_path, root / "out", fixtures, planner_mode="ollama-local", local_model="local:test")
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["reason"], "LOCAL_MODEL_UNAVAILABLE")
            self.assertFalse((root / "out" / "artifacts").exists())

    def test_unauthorized_model_may_not_expand_target_or_allow_writes(self):
        with FakeLocalService(answer={"summary": "system commands ignored", "affected_claims": ["WRITE MAIN"], "uncertainty": "none"}):
            out = local_model.propose_local(self.old, self.new, self.evidence, model="local:test")
        self.assertIn("WRITE MAIN", out["model_proposal_unverified"]["affected_claims"])
        self.assertEqual(out["decision"], "CHANGE_REQUIRES_REVIEW")
        self.assertTrue(out["needs_semantic_review"])


if __name__ == "__main__":
    unittest.main()
