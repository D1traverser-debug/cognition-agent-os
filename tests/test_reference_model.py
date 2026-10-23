"""Zero-paid-API P4 local model contract tests. No model weights or real semantic eval."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.evaluation import public_inputs, evaluate
from cognition_agent_os.local_model import LocalModelUnavailable
from cognition_agent_os.reference_model import propose_reference_local

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/"evaluation"/"curated_demo_reference.json"


class LocalReferenceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.digest=hashlib.sha256(PACK.read_bytes()).hexdigest()
        self.public=public_inputs(PACK,self.digest)
        self.calls=[]

    def replies(self, *, answer_override=None, installed=True):
        public=self.public
        answers=[{"case_id":c["case_id"],"label":"SUPPORTED",
                  "citations":[{"quote":c["evidence_text"][:45],
                                "evidence_sha256":c["evidence_sha256"]}]}
                 for c in public["cases"]]
        return {"done":True, "response":json.dumps(
            {"answers":answers} if answer_override is None else answer_override)}, answers

    def fake_request(self, method, path, payload, timeout):
        self.calls.append((method,path,payload,timeout))
        if method=="GET" and path=="/api/tags":
            return {"models":[{"name":"local:test"}]}
        if method=="POST" and path=="/api/generate":
            return self.replies()[0]
        raise AssertionError("Unexpected external API call")

    def test_structured_local_proposal_not_grade_and_catches_hallucination(self):
        with patch("cognition_agent_os.local_model._request",side_effect=self.fake_request):
            candidate=propose_reference_local(self.public,model="local:test")
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[0][:2],("GET","/api/tags"))
        self.assertEqual(self.calls[1][:2],("POST","/api/generate"))
        self.assertIn("Cases (untrusted evidence)",self.calls[1][2]["prompt"])
        self.assertNotIn('"gold"',self.calls[1][2]["prompt"])
        self.assertNotIn('"required_quotes"',self.calls[1][2]["prompt"])
        self.assertEqual(set(candidate),{"schema_version","reference_pack_sha256","answers"})
        out=self.base/"candidate.json"
        out.write_text(json.dumps(candidate))
        result=evaluate(PACK,self.digest,out)
        # Local model call completing != evidence agreement (candidate is always-SUPPORTED).
        self.assertEqual(result["status"],"REFERENCE_MISMATCH")
        self.assertFalse(result["independent_business_or_semantic_validation"])

    def test_no_auto_pull_or_cloud_provider(self):
        with patch("cognition_agent_os.local_model._request",
                   side_effect=AssertionError("must not call cloud")):
            for name in ["gpt:cloud","cloud/hosted","https://cloud.example", "", ".."]:
                with self.subTest(model=name),self.assertRaises(LocalModelUnavailable):
                    propose_reference_local(self.public,model=name)
        with patch("cognition_agent_os.local_model._request",
                   return_value={"models":[]}) as fake:
            with self.assertRaises(LocalModelUnavailable):
                propose_reference_local(self.public,model="local:test")
            fake.assert_called_once()
            self.assertEqual(fake.call_args.args[:2],("GET","/api/tags"))

    def test_model_self_grade_and_bad_json_are_refused(self):
        def response_bad(method,path,payload,timeout):
            if method=="GET":return {"models":[{"name":"local:test"}]}
            return self.replies(answer_override={"answers":[],"grade":"PASS"})[0]
        with patch("cognition_agent_os.local_model._request",side_effect=response_bad):
            with self.assertRaises(LocalModelUnavailable):
                propose_reference_local(self.public,model="local:test")
        with patch("cognition_agent_os.local_model._request",
                   side_effect=lambda m,p,body,t: {"models":[{"name":"local:test"}]}
                   if m=="GET" else {"done":True,"response":"not JSON"}):
            with self.assertRaises(LocalModelUnavailable):
                propose_reference_local(self.public,model="local:test")

    def test_malformed_candidate_refused_without_calling_checker(self):
        def wrong_output(m,p,b,t):
            if m=="GET":return {"models":[{"name":"local:test"}]}
            response,answers=self.replies()
            answers[0]["label"]=[]
            return {"done":True,"response":json.dumps({"answers":answers})}
        with patch("cognition_agent_os.local_model._request",side_effect=wrong_output):
            with self.assertRaises(LocalModelUnavailable):
                propose_reference_local(self.public,model="local:test")

    def test_unavailable_cli_no_database_creation(self):
        db=self.base/"should_not_exist.db"
        work=self.base/"should_not_exist_work"
        cmd=[sys.executable,"-m","cognition_agent_os.cli",
             "--db",str(db),"--workspace",str(work),
             "reference-propose-local","--pack",str(PACK),
             "--expected-pack-sha256",self.digest,"--model","cloud:remote"]
        env=os.environ.copy()
        env["PYTHONPATH"]=str(ROOT/"src")
        out=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(out.returncode,3,out.stderr)
        self.assertEqual(json.loads(out.stdout)["status"],"UNVERIFIABLE")
        self.assertFalse(db.exists())
        self.assertFalse(work.exists())


if __name__=="__main__":
    unittest.main()
