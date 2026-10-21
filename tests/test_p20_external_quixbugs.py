"""P20 static and offline external-source trust tests.

No network, Docker, model downloads, hidden-answer injection, or
fabricated real inference is performed by this unittest module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_p20_external_quixbugs as p20
from cognition_agent_os.container_lab import validate_task_spec,cases_from_bytes


class ExternalQuixbugsContractTests(unittest.TestCase):
    def test_exact_upstream_repo_and_immutable_blob_pins(self):
        self.assertEqual(p20.UPSTREAM_OWNER,"jkoppel")
        self.assertEqual(p20.UPSTREAM_REPOSITORY,"QuixBugs")
        self.assertEqual(len(p20.UPSTREAM_COMMIT),40)
        self.assertEqual(len(p20.CASES),2)
        self.assertEqual({x["name"] for x in p20.CASES},{
            "external_gcd","external_max_sublist_sum"})
        for task in p20.CASES:
            self.assertEqual(task["expected_rows"],6)
            self.assertEqual(len(task["public_rows"]),2)
            for kind in ("source","tests"):
                blob=task[kind+"_blob"]
                self.assertRegex(blob,r"^[a-f0-9]{40}$")
                self.assertIn(p20.UPSTREAM_COMMIT,
                              p20.source_url(task[kind+"_path"]))
                self.assertNotIn("/master/",p20.source_url(task[kind+"_path"]))
            self.assertNotIn("correct_python_programs",str(task))
        self.assertEqual(p20.git_blob_sha1(b""),
            hashlib.sha1(b"blob 0\\0").hexdigest())

    def test_reject_unregistered_correct_source_and_wrong_blob(self):
        with self.assertRaises(ValueError):
            p20.source_url("correct_python_programs/gcd.py")
        with patch.object(p20,"urlopen") as network:
            with self.assertRaises(ValueError):
                p20.fetch_pinned("python_programs/gcd.py","bad")
            network.assert_not_called()
        valid=p20.CASES[0]["source_blob"]
        with patch.object(p20,"urlopen") as network:
            response=network.return_value.__enter__.return_value
            response.read.return_value=b"altered source!"
            with self.assertRaises(ValueError):
                p20.fetch_pinned("python_programs/gcd.py",valid)
            self.assertEqual(response.read.call_args.args,(25001,))

    def test_upstream_jsonl_case_adaptation_uses_only_pinned_gold(self):
        original=b"def gcd(a,b):\\n    return 0\\n"
        upstream=b'[[17,0],17]\\n[[20,100],20]\\n[[3,12],3]\\n'
        task={**p20.CASES[0],
              "source_blob":p20.git_blob_sha1(original),
              "tests_blob":p20.git_blob_sha1(upstream),
              "expected_rows":3,"public_rows":(0,1)}
        adapted=p20.make_case(task,original,upstream)
        self.assertTrue(adapted["source"].startswith(original.decode()))
        self.assertIn("def calculate(data):",adapted["source"])
        self.assertIn("return {'value': gcd(*data['args'])}",
                      adapted["source"])
        self.assertEqual(len(adapted["public"]),2)
        self.assertEqual(len(adapted["hidden"]),1)
        self.assertEqual(adapted["public"][1]["expected"],{"value":20})
        self.assertEqual(adapted["hidden"][0]["input"],{"args":[3,12]})
        self.assertNotIn(str(adapted["hidden"][0]["input"]),
                         str(adapted["public"]))
        with self.assertRaises(ValueError):
            p20.make_case({**task,"source_blob":"0"*40},original,upstream)
        with self.assertRaises(ValueError):
            p20.parse_upstream_test_rows(b'[[1],1]\\n',3)
        with self.assertRaises(ValueError):
            p20.parse_upstream_test_rows(b'[[1],1]\\nmalformed\\n',2)

    def test_source_acceptance_is_original_ledger_spec_not_new_authority(self):
        task=p20.CASES[0]
        gold=json.dumps([{"input":{"args":[3,12]},
                          "expected":{"value":3}}]).encode()
        spec={"kind":"repo_container_repair",
              "files":["main.py","calculator.py"],"entrypoint":"main.py",
              "candidate":"seed.json","visible":"visible.json",
              "holdout":"sealed.json",
              "holdout_sha256":hashlib.sha256(gold).hexdigest(),
              "goal_statement":task["goal_statement"]}
        self.assertEqual(validate_task_spec(spec),spec)
        self.assertEqual(len(cases_from_bytes(gold)),1)
        with self.assertRaises(ValueError):
            validate_task_spec({**spec,"external_code_execution":True})

    def test_standalone_requires_explicit_opt_in_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            env={"P14_LOCAL_MODEL":"qwen2.5-coder:0.5b"}
            import os
            env={**os.environ,**env}
            env.pop("PYTHONPATH",None)
            x=subprocess.run(
                [sys.executable,str(Path(__file__).resolve().parents[1]/
                                    "scripts"/"verify_p20_external_quixbugs.py")],
                env=env,cwd=directory,capture_output=True,text=True,timeout=12)
        self.assertNotEqual(x.returncode,0)
        self.assertIn("explicit one-time local 7B opt-in",x.stderr)
        self.assertNotIn("ModuleNotFoundError",x.stderr)


if __name__=="__main__":
    unittest.main()
