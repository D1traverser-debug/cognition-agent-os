"""P32 preregistration: full original APScheduler wheel, two genuine code sites."""
import base64
import csv
import hashlib
import io
import json
import unittest
import zipfile

from scripts.verify_p32_full_apscheduler import (
    PUBLIC,HIDDEN,SOURCE_PATHS,SOURCE_GIT_BLOBS,PACKAGES,PROBE,GOAL,
    _manifest,_scope,_compact,_repack,git_blob_sha,
)

class FullAPSchedulerTwoFileTests(unittest.TestCase):
    def test_contract_frozen_and_both_modules_distinct(self):
        self.assertEqual(len(PUBLIC),4)
        self.assertEqual(len(HIDDEN),4)
        self.assertEqual([x["input"]["case"] for x in PUBLIC],
                         ["memory_single","memory_duplicate",
                          "scheduler_tracked","scheduler_removed"])
        self.assertEqual(set(SOURCE_PATHS),{
            "apscheduler/datastores/memory.py",
            "apscheduler/_schedulers/async_.py"})
        self.assertEqual(len(SOURCE_GIT_BLOBS),2)
        self.assertEqual(len(PACKAGES),8)
        self.assertEqual(len(_manifest()),64)
        self.assertNotIn("expected",PROBE)
        self.assertNotIn("HIDDEN",PROBE)
        self.assertIn("BOTH",GOAL)

    def test_two_original_method_bodies_required_not_other_mutations(self):
        originals={
            SOURCE_PATHS[0]:b"class MemoryDataStore:\n    async def release_job(self):\n        return 1\n    def other(self):\n        return 9\n",
            SOURCE_PATHS[1]:b"class AsyncScheduler:\n    async def _run_job(self):\n        return 1\n    def other(self):\n        return 9\n",
        }
        changes={p:source.replace(b"return 1",b"return 2")
                 for p,source in originals.items()}
        self.assertTrue(_scope(originals,changes))
        self.assertFalse(_scope(originals,{SOURCE_PATHS[0]:changes[SOURCE_PATHS[0]],
                                           SOURCE_PATHS[1]:originals[SOURCE_PATHS[1]]}))
        altered=dict(changes)
        altered[SOURCE_PATHS[0]]=changes[SOURCE_PATHS[0]].replace(b"return 9",b"return 8")
        self.assertFalse(_scope(originals,altered))
        edits={"edits":[
            {"path":p,"find":"return 1","replace":"return 2"} for p in SOURCE_PATHS]}
        self.assertEqual(_compact(json.dumps(edits),originals),changes)
        with self.assertRaisesRegex(ValueError,"Both original modules"):
            _compact(json.dumps({"edits":[edits["edits"][0],edits["edits"][0]]}),originals)

    def test_two_module_wheel_record_and_other_members_untouched(self):
        first,second=SOURCE_PATHS
        record="apscheduler-4.0.0a6.dist-info/RECORD"
        old={first:b"class One:\n    pass\n",second:b"class Two:\n    pass\n"}
        new={first:b"class One:\n    safe=True\n",second:b"class Two:\n    safe=True\n"}
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,"w") as wheel:
            for path,content in old.items():
                wheel.writestr(path,content)
            wheel.writestr("apscheduler/abc.py",b"original source")
            rows=[[path,"",""] for path in old]
            rows.extend([["apscheduler/abc.py","",""],[record,"",""]])
            csvio=io.StringIO(newline="")
            csv.writer(csvio,lineterminator="\n").writerows(rows)
            wheel.writestr(record,csvio.getvalue())
        resulting=_repack(memory.getvalue(),new)
        with zipfile.ZipFile(io.BytesIO(resulting)) as repacked:
            for path in SOURCE_PATHS:self.assertEqual(repacked.read(path),new[path])
            self.assertEqual(repacked.read("apscheduler/abc.py"),b"original source")
            record_rows=list(csv.reader(io.StringIO(repacked.read(record).decode())))
            for path in SOURCE_PATHS:
                row=[r for r in record_rows if r[0]==path][0]
                want=base64.urlsafe_b64encode(hashlib.sha256(new[path]).digest()).decode().rstrip("=")
                self.assertEqual(row[1],"sha256="+want)
                self.assertEqual(row[2],str(len(new[path])))

    def test_original_git_blob_validation_is_content_sensitive(self):
        self.assertEqual(len(git_blob_sha(b"hello")),40)
        self.assertNotEqual(git_blob_sha(b"hello"),git_blob_sha(b"hello!"))

if __name__=="__main__":
    unittest.main()
