"""P31 offline preregistration tests; does not import the external package."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_p31_full_dateutil import (
    PUBLIC,HIDDEN,PUBLIC_SPECS,HIDDEN_SPECS,PROBE,GOAL,WHEEL_SHAS,
    _independent_dates,_cases,manifest,verify_wheels,
)

class FullDateutilPreregistrationTests(unittest.TestCase):
    def test_original_reporter_case_has_independent_union_gold(self):
        self.assertEqual(_independent_dates(2024,4,"MO,1FR"),
                         ["2024-04-01","2024-04-05","2024-04-08",
                          "2024-04-15","2024-04-22","2024-04-29"])
        self.assertEqual(_independent_dates(2024,2,"TU,-1TH"),
                         ["2024-02-06","2024-02-13","2024-02-20",
                          "2024-02-27","2024-02-29"])

    def test_public_and_sealed_holdout_independently_frozen(self):
        self.assertEqual(len(PUBLIC),4)
        self.assertEqual(len(HIDDEN),8)
        self.assertEqual(len(set(PUBLIC_SPECS+HIDDEN_SPECS)),12)
        self.assertEqual(len(manifest()),64)
        self.assertEqual(PUBLIC,_cases(PUBLIC_SPECS))
        self.assertEqual(HIDDEN,_cases(HIDDEN_SPECS))
        self.assertTrue(all(set(case)=={"input","expected"} for case in PUBLIC+HIDDEN))
        self.assertTrue(all(len(case["expected"]["dates"])>=1 for case in PUBLIC+HIDDEN))
        self.assertNotIn("expected",PROBE)
        self.assertNotIn("HIDDEN",PROBE)
        self.assertIn("dateutil.rrule",PROBE)
        self.assertIn("BYDAY",GOAL)

    def test_pinned_wheel_hash_fail_closed(self):
        self.assertEqual(len(WHEEL_SHAS),2)
        self.assertTrue(all(len(h)==64 for h in WHEEL_SHAS.values()))
        with tempfile.TemporaryDirectory() as tmp:
            for name in WHEEL_SHAS:
                (Path(tmp)/name).write_bytes(b"not a published release wheel")
            with self.assertRaisesRegex(ValueError,"SHA256"):
                verify_wheels(Path(tmp))

if __name__=="__main__":
    unittest.main()
