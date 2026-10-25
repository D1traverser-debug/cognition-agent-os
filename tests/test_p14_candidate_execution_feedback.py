"""P14: candidate defects must remain useful PUBLIC evidence, never fake Docker outage."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cognition_agent_os.container_lab import (
    CandidateExecutionFailed,ContainerUnavailable,_docker_run,run_suite
)
from cognition_agent_os.repo_refinement import _public_feedback


class CandidateExecutionFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.base={"main.py":b"print('{}')\n",
                   "module.py":b"def get(): return 1\n"}
        self.cases=[
            {"input":{"value":1},"expected":{"value":2}},
            {"input":{"value":2},"expected":{"value":3}}
        ]

    def test_crash_becomes_public_failure_not_missing_docker(self):
        failures=[
            CandidateExecutionFailed("CANDIDATE_NONZERO"),
            {"value":3}
        ]
        with patch("cognition_agent_os.container_lab._docker_run",
                   side_effect=failures) as invoked:
            report=run_suite(self.base,{},"main.py",self.cases)
        self.assertEqual(invoked.call_count,2)
        self.assertEqual((report["passes"],report["total"]),(1,2))
        self.assertEqual(report["observed"][0]["execution_error"],
                         "CANDIDATE_NONZERO")
        feedback=_public_feedback({"main.py":b"broken"} ,self.cases,report)
        self.assertEqual(feedback["failed_public_cases"][0]["input"],{"value":1})
        self.assertEqual(feedback["failed_public_cases"][0]["expected"],{"value":2})
        self.assertEqual(feedback["failed_public_cases"][0]["execution_error"],
                         "CANDIDATE_NONZERO")
        self.assertNotIn("hidden",str(feedback).lower())

    def test_public_wrong_output_contains_bounded_actual_value(self):
        with patch("cognition_agent_os.container_lab._docker_run",
                   side_effect=[{"value":99},{"value":3}]):
            result=run_suite(self.base,{},"main.py",self.cases,
                             include_observed=True)
        self.assertEqual(result["passes"],1)
        self.assertEqual(result["observed"][0]["observed_value"],{"value":99})
        feedback=_public_feedback({"module.py":b"bad source"},self.cases,result)
        row=feedback["failed_public_cases"][0]
        self.assertEqual(row["observed_value"],{"value":99})
        self.assertEqual(row["expected"],{"value":2})
        self.assertNotIn("observed_value",result["observed"][1])

    def test_hidden_oracle_default_returns_only_hash_even_on_wrong_output(self):
        # All independent hidden reviewers call run_suite without the flag.
        with patch("cognition_agent_os.container_lab._docker_run",
                   return_value={"value":99}):
            hidden=run_suite(self.base,{},"main.py",self.cases)
        self.assertEqual(hidden["passes"],0)
        self.assertTrue(all("observed_value" not in obs
                            for obs in hidden["observed"]))
        self.assertTrue(all("output_sha256" in obs
                            for obs in hidden["observed"]))

    def test_huge_public_wrong_output_is_hashed_not_echoed(self):
        with patch("cognition_agent_os.container_lab._docker_run",
                   return_value={"value":"A"*600}):
            results=run_suite(self.base,{},"main.py",self.cases,
                              include_observed=True)
        self.assertTrue(all("observed_value" not in obs
                            for obs in results["observed"]))
        feedback=_public_feedback({"module.py":b"bad source"},self.cases,results)
        self.assertTrue(all("observed_value" not in row
                            for row in feedback["failed_public_cases"]))

    def test_real_docker_service_failure_cannot_become_public_failure(self):
        with patch("cognition_agent_os.container_lab._docker_run",
                   side_effect=ContainerUnavailable("DOCKER_CLI_NOT_INSTALLED")):
            with self.assertRaisesRegex(ContainerUnavailable,
                                         "DOCKER_CLI_NOT_INSTALLED"):
                run_suite(self.base,{},"main.py",self.cases)

    def test_candidate_process_nonzero_distinguished_from_docker_cli_error(self):
        with patch("cognition_agent_os.container_lab.shutil.which",
                   return_value="/fake/docker"),patch(
                   "cognition_agent_os.container_lab.subprocess.run",
                   return_value=SimpleNamespace(returncode=1,stdout=b"",stderr=b"")):
            with self.assertRaisesRegex(CandidateExecutionFailed,
                                         "CANDIDATE_NONZERO"):
                _docker_run(Path("/tmp/fake-app"),"main.py",{"test":True})
        with patch("cognition_agent_os.container_lab.shutil.which",
                   return_value="/fake/docker"),patch(
                   "cognition_agent_os.container_lab.subprocess.run",
                   return_value=SimpleNamespace(returncode=125,stdout=b"",stderr=b"")):
            with self.assertRaisesRegex(ContainerUnavailable,
                                         "DOCKER_PROCESS_UNAVAILABLE"):
                _docker_run(Path("/tmp/fake-app"),"main.py",{"test":True})

    def test_no_output_is_not_infrastructure_error(self):
        with patch("cognition_agent_os.container_lab.shutil.which",
                   return_value="/fake/docker"),patch(
                   "cognition_agent_os.container_lab.subprocess.run",
                   return_value=SimpleNamespace(returncode=0,stdout=b"",stderr=b"")):
            with self.assertRaisesRegex(CandidateExecutionFailed,
                                         "CANDIDATE_EMPTY_OR_OVERSIZE_OUTPUT"):
                _docker_run(Path("/tmp/fake-app"),"main.py",{})

    def test_candidate_failure_codes_are_allowlisted(self):
        with self.assertRaises(ValueError):
            CandidateExecutionFailed("attacker supplied string; rm -rf /")


if __name__=="__main__":
    unittest.main()
