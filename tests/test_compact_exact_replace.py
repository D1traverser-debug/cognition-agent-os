"""P22b: compact source edits keep original audit, Docker, and gold boundaries."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os.container_lab import candidate_changes,validate_task_spec
from cognition_agent_os.repo_repair import (
    _expand_exact_replace_response,_candidate_from_model,
    CompletedCompactModelValidationRejected
)

BASE={
    "main.py":b"import json\nprint('not executed during expansion')\n",
    "rules.py":(
        b"def startswith(s, prefix):\n"
        b"    return s.endswith(prefix)\n"
        b"\n"
        b"def endswith(s, suffix):\n"
        b"    return s.startswith(suffix)\n"
    )
}
FILES=["main.py","rules.py"]

def patch_doc(edits):
    return json.dumps({"edits":edits}).encode()

class CompactExactReplaceContractTests(unittest.TestCase):
    def test_nonoverlapping_unique_original_source_edits_preserve_elsewhere(self):
        raw=patch_doc([
            {"path":"rules.py","find":"return s.endswith(prefix)",
             "replace":"return s.startswith(prefix)"},
            {"path":"rules.py","find":"return s.startswith(suffix)",
             "replace":"return s.endswith(suffix)"},
        ])
        full=_expand_exact_replace_response(raw,BASE,FILES)
        expanded=candidate_changes(full,FILES)
        self.assertEqual(list(expanded),["rules.py"])
        self.assertIn(b"def startswith",expanded["rules.py"])
        self.assertIn(b"    return s.startswith(prefix)",expanded["rules.py"])
        self.assertIn(b"    return s.endswith(suffix)",expanded["rules.py"])
        self.assertEqual(BASE["main.py"],b"import json\nprint('not executed during expansion')\n")
        self.assertEqual(expanded["rules.py"].count(b"def "),2)
        self.assertNotIn(b"hidden",full.lower())

    def test_ambiguous_nonexistent_overlapping_and_nochange_rejected(self):
        duplicated={"rules.py":b"return value\nreturn value\n",
                    "main.py":BASE["main.py"]}
        bad=[
            (BASE,[{"path":"rules.py","find":"missing","replace":"yes"}]),
            (duplicated,[{"path":"rules.py","find":"return value","replace":"yes"}]),
            (BASE,[{"path":"rules.py","find":"return s.endswith(prefix)",
                    "replace":"return s.endswith(prefix)"}]),
            (BASE,[{"path":"evil.py","find":"x","replace":"y"}]),
            (BASE,[{"path":"rules.py","find":"","replace":"y"}]),
            (BASE,[{"path":"rules.py","find":"def startswith(s, prefix):\n"
                      "    return s.endswith(prefix)","replace":"x"},
                   {"path":"rules.py","find":"return s.endswith(prefix)",
                    "replace":"y"}]),
        ]
        for base,edits in bad:
            with self.subTest(edits=edits),self.assertRaises(ValueError):
                _expand_exact_replace_response(patch_doc(edits),base,FILES)

    def test_rejects_untrusted_json_structure_or_malicious_growth(self):
        base=BASE
        values=[
            b"[]",b"{}",b'{"edits":[]}',
            b'{"changes":[]}',b'{"edits":[{}]}',
            patch_doc([{"path":"rules.py","find":"a","replace":"x"*3300}]),
            patch_doc([{"path":"rules.py","find":"\u0000","replace":"x"}]),
            patch_doc([{"path":"rules.py","find":"return s.endswith(prefix)",
                        "replace":"x"}]*7),
            b"x"*9000,
        ]
        for value in values:
            with self.subTest(size=len(value)),self.assertRaises((ValueError,TypeError)):
                _expand_exact_replace_response(value,base,FILES)

    def test_schema_admission_is_bounded_and_optional_for_existing_tasks(self):
        spec={"kind":"repo_container_repair",
              "files":FILES,"entrypoint":"main.py",
              "candidate":"seed.json","visible":"public.json",
              "holdout":"hidden.json","holdout_sha256":"a"*64,
              "goal_statement":"Preserve prefix and suffix semantics"}
        self.assertEqual(validate_task_spec(spec),spec)
        compact={**spec,"candidate_format":"exact_replace"}
        self.assertEqual(validate_task_spec(compact),compact)
        for bad in ("","unified_diff","patch_any_path",None,[],123):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_task_spec({**spec,"candidate_format":bad})

    def test_genuine_model_response_must_supply_patch_not_reference_solution(self):
        spec={"files":FILES,"candidate_format":"exact_replace",
              "goal_statement":"Use proper startswith and endswith."}
        response=patch_doc([{"path":"rules.py",
                  "find":"return s.endswith(prefix)",
                  "replace":"return s.startswith(prefix)"}]).decode()
        requests=[]
        def fake_request(method,path,payload,timeout):
            requests.append((method,path,payload,timeout))
            if method=="GET":
                return {"models":[{"name":"qwen2.5-coder:7b"}]}
            return {"done":True,"response":response}
        public=json.dumps([{"input":{"text":"hello"},"expected":{"match":True}}]).encode()
        with patch("cognition_agent_os.local_model._request",
                   side_effect=fake_request):
            raw=_candidate_from_model(spec,BASE,public,"qwen2.5-coder:7b")
        expanded=candidate_changes(raw,FILES)
        self.assertIn(b"return s.startswith(prefix)",expanded["rules.py"])
        self.assertEqual(len(requests),2)
        self.assertEqual(requests[1][0:2],("POST","/api/generate"))
        self.assertEqual(requests[1][2]["options"]["num_predict"],1800)
        self.assertEqual(requests[1][2]["format"]["required"],["edits"])
        prompt=json.loads(requests[1][2]["prompt"])
        self.assertEqual(prompt["output_contract"]["required"],["edits"])
        self.assertNotIn("hidden",json.dumps(prompt).lower())
        self.assertEqual(requests[1][3],180)


    def test_real_completed_model_response_rejected_as_nochange_is_counted(self):
        spec={"files":FILES,"candidate_format":"exact_replace",
              "goal_statement":"Preserve prefix semantics"}
        unmodified_patch=patch_doc([{"path":"rules.py",
            "find":"return s.endswith(prefix)",
            "replace":"return s.endswith(prefix)"}]).decode()
        def fake_request(method,path,payload,timeout):
            if method=="GET":
                return {"models":[{"name":"qwen2.5-coder:7b"}]}
            return {"done":True,"response":unmodified_patch}
        with patch("cognition_agent_os.local_model._request",
                   side_effect=fake_request):
            with self.assertRaises(CompletedCompactModelValidationRejected) as cm:
                _candidate_from_model(spec,BASE,b"[]","qwen2.5-coder:7b")
            self.assertEqual(str(cm.exception),
                             "Candidate makes no actual source change")

    def test_completed_invalid_compact_candidate_cannot_claim_zero_model_calls(self):
        from scripts.verify_actual_local_model import source_cases
        from cognition_agent_os.runner import run_once
        case={"name":"compact_completed_generation_telemetry",
              "source":"def calculate(data):\n    return {'answer':0}\n",
              "public":[{"input":{},"expected":{"answer":1}}],
              "hidden":[{"input":{},"expected":{"answer":1}}],
              "candidate_format":"exact_replace"}
        with tempfile.TemporaryDirectory(prefix="compact-inference-telemetry-") as tmp:
            root=Path(tmp)
            fx,ws,db,tid=source_cases(root,case,goal_statement="Fix output")
            with patch("cognition_agent_os.repo_repair._candidate_from_model",
                       side_effect=CompletedCompactModelValidationRejected(
                           "Candidate makes no actual source change")):
                out=run_once(db,ws,fx,planner_mode="ollama-local",
                             local_model="qwen2.5-coder:7b")
            self.assertEqual(out["status"],"UNKNOWN")
            self.assertEqual(out["reason"],"REPOSITORY_PROPOSAL_UNAVAILABLE")
            self.assertEqual(out["validation_failure"],
                             "Candidate makes no actual source change")
            self.assertTrue(out["model_called"])
            self.assertEqual(out["completed_model_generations"],1)
            self.assertFalse(out["nochange_retry_attempted"])
            self.assertFalse((ws/"artifacts"/(tid+".json")).exists())

if __name__=="__main__":
    unittest.main()
