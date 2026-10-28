"""P31 offline preregistration tests; does not import the external package."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_p31_full_dateutil import (
    PUBLIC,HIDDEN,PUBLIC_SPECS,HIDDEN_SPECS,PROBE,GOAL,WHEEL_SHAS,
    _independent_dates,_cases,manifest,verify_wheels,
    _scope_ok,_expand_one_compact,_repack_only_rrule,
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

    def test_compact_method_scope_accepts_repair_but_refuses_other_changes(self):
        original="class rrule:\n    def _iter(self):\n        return False\n    def other(self):\n        return 1\n"
        revised=original.replace("return False","return True")
        self.assertTrue(_scope_ok(original,revised))
        self.assertFalse(_scope_ok(original,original))
        self.assertFalse(_scope_ok(original,original.replace("return 1","return 2")))
        import json
        change={"edits":[{"find":"return False","replace":"return True"}]}
        self.assertEqual(_expand_one_compact(json.dumps(change),original),revised)
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_METHOD_CHANGE"):
            _expand_one_compact(json.dumps(
                {"edits":[{"find":"return 1","replace":"return 2"}]}),original)

    def test_repack_changes_only_module_and_consistent_wheel_record(self):
        import io
        import csv
        import zipfile
        import hashlib
        import base64
        target="dateutil/rrule.py"
        record="dateutil_test-0.1.dist-info/RECORD"
        old=b"class rrule:\n    pass\n"
        new=b"class rrule:\n    def _iter(self): return True\n"
        old_sha=base64.urlsafe_b64encode(hashlib.sha256(old).digest()).decode().rstrip("=")
        original=io.BytesIO()
        with zipfile.ZipFile(original,"w") as z:
            z.writestr(target,old)
            z.writestr("dateutil/_common.py",b"original other module")
            z.writestr(record,
                       f"{target},sha256={old_sha},{len(old)}\n"
                       f"dateutil/_common.py,,\n{record},,\n")
        revised=_repack_only_rrule(original.getvalue(),new)
        with zipfile.ZipFile(io.BytesIO(revised)) as z:
            self.assertEqual(z.read(target),new)
            self.assertEqual(z.read("dateutil/_common.py"),b"original other module")
            rows=list(csv.reader(io.StringIO(z.read(record).decode())))
            item=[r for r in rows if r[0]==target][0]
            self.assertEqual(item[2],str(len(new)))
            actual_digest=base64.urlsafe_b64encode(
                hashlib.sha256(new).digest()).decode().rstrip("=")
            self.assertEqual(item[1],"sha256="+actual_digest)

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
