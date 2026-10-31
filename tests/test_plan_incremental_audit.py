import copy
import tempfile
import subprocess
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from plan_incremental_audit import plan, AuditInputError, _git_tree

R = "D1traverser-debug/cognition-agent-os"
H = "a" * 40
J = "b" * 40
K = "c" * 40

def previous():
    return {"schema":"caos-blob-audit-baseline-v1", "repository":R,
            "ref":H,"git_tree_sha":H,
            "authority":"PUBLIC_SOURCE_READ_RECEIPT_NOT_EXECUTION_GRANT",
            "files":[{"path":"a.py","blob_sha":H,"receipt":"SOURCE_FETCHED_STRUCTURAL_REVIEW_ONLY"},
                     {"path":"old.md","blob_sha":K,"receipt":"SOURCE_FETCHED_STRUCTURAL_REVIEW_ONLY"}]}

def tree():
    return {"sha":J,"truncated":False,"tree":[{"path":"a.py","type":"blob","sha":H},
            {"path":"new.py","type":"blob","sha":K}]}

class DeltaAuditTests(unittest.TestCase):
    def test_reuse_new_and_retired_are_not_semantic_proofs(self):
        x = plan(previous(), tree(), repository=R)
        self.assertEqual(x["summary"],{"reuse_prior_structural_receipt_only":1,
                         "changed_requires_read":0,"new_requires_read":1,
                         "retired_requires_lifecycle_review":1})
        self.assertFalse(x["semantic_understanding_verified"])
        self.assertFalse(x["client_or_business_outcome_verified"])

    def test_changed_blob_reopens_only_that_path(self):
        data=tree();data["tree"][0]["sha"]=J
        x=plan(previous(),data,repository=R)
        self.assertEqual(x["changed_requires_read"],["a.py"])
        self.assertEqual(x["new_requires_read"],["new.py"])

    def test_truncated_tree_must_fail_closed(self):
        data=tree();data["truncated"]=True
        with self.assertRaisesRegex(AuditInputError,"TRUNCATED"):
            plan(previous(),data,repository=R)

    def test_forged_audit_promotion_is_not_reusable(self):
        b=previous();b["files"][0]["receipt"]="BUSINESS_VERIFIED"
        with self.assertRaisesRegex(AuditInputError,"RECEIPT"):
            plan(b,tree(),repository=R)

    def test_different_repo_and_duplicates_are_rejected(self):
        with self.assertRaisesRegex(AuditInputError,"REPOSITORY"):
            plan(previous(),tree(),repository="attacker/other")
        data=tree();data["tree"].append(copy.deepcopy(data["tree"][0]))
        with self.assertRaisesRegex(AuditInputError,"DUPLICATE"):
            plan(previous(),data,repository=R)

    def test_git_head_move_mid_audit_never_mixes_two_commits(self):
        # Counterexample: HEAD changes after the initial identity read.
        # A valid source receipt must bind the tree/listing to that SAME SHA.
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            commands=(
                ["git","init","-q",d],
                ["git","-C",d,"config","user.name","CI"],
                ["git","-C",d,"config","user.email","ci@example.invalid"],
            )
            for cmd in commands:
                subprocess.run(cmd,check=True,capture_output=True)
            Path(d,"before.py").write_text("v1\n",encoding="utf-8")
            subprocess.run(["git","-C",d,"add","."],check=True,capture_output=True)
            subprocess.run(["git","-C",d,"commit","-qm","old"],check=True,capture_output=True)
            old=subprocess.run(["git","-C",d,"rev-parse","HEAD"],capture_output=True,check=True).stdout.decode().strip()
            Path(d,"after.py").write_text("v2\n",encoding="utf-8")
            subprocess.run(["git","-C",d,"add","."],check=True,capture_output=True)
            subprocess.run(["git","-C",d,"commit","-qm","new"],check=True,capture_output=True)
            new=subprocess.run(["git","-C",d,"rev-parse","HEAD"],capture_output=True,check=True).stdout.decode().strip()
            subprocess.run(["git","-C",d,"reset","--hard",old],check=True,capture_output=True)
            real_run=subprocess.run
            moved=[]
            def moving_run(args, *pos, **kw):
                result=real_run(args,*pos,**kw)
                if args[-2:]==["rev-parse","HEAD"] and not moved:
                    real_run(["git","-C",d,"reset","--hard",new],
                             check=True,capture_output=True)
                    moved.append(True)
                return result
            with patch("plan_incremental_audit.subprocess.run",side_effect=moving_run):
                scanned=_git_tree(Path(d))
            self.assertTrue(moved)
            self.assertEqual(scanned["commit"],old)
            self.assertEqual({x["path"] for x in scanned["tree"]},{"before.py"})
            expected=real_run(["git","-C",d,"rev-parse",old+"^{tree}"],
                              capture_output=True,check=True).stdout.decode().strip()
            self.assertEqual(scanned["sha"],expected)

    def test_real_git_checkout_is_read_without_remote_network(self):
        with tempfile.TemporaryDirectory() as d:
            for cmd in (["git","init","-q",d],["git","-C",d,"config","user.name","CI"],
                        ["git","-C",d,"config","user.email","ci@example.invalid"]):
                subprocess.run(cmd,check=True,capture_output=True)
            Path(d,"a.py").write_text("print('yes')\n",encoding="utf-8")
            subprocess.run(["git","-C",d,"add","a.py"],check=True,capture_output=True)
            subprocess.run(["git","-C",d,"commit","-qm","one"],check=True,capture_output=True)
            t=_git_tree(Path(d))
            self.assertEqual(len(t["tree"]),1)
            self.assertEqual(t["tree"][0]["path"],"a.py")
            self.assertEqual(len(t["tree"][0]["sha"]),40)

if __name__=="__main__":
    unittest.main()
