"""Mutation checks for the one local-effect source-shape admission gate.

These checks are not a semantic or security theorem. They establish that a
new unreviewed write call or removal of an effect-time guard breaks CI,
before a model-generated implementation can be accepted on test count alone.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.verify_effect_boundaries import inspect


SOURCE = Path(__file__).resolve().parents[1] / "src" / "cognition_agent_os"


class EffectBoundaryContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pkg = self.root / "src" / "cognition_agent_os"
        self.pkg.mkdir(parents=True)
        for src in SOURCE.glob("*.py"):
            shutil.copyfile(src, self.pkg / src.name)

    def mutate(self, module: str, before: str, after: str) -> None:
        dest = self.pkg / (module + ".py")
        original = dest.read_text(encoding="utf-8")
        self.assertEqual(original.count(before), 1, module)
        dest.write_text(original.replace(before, after), encoding="utf-8")

    def test_real_tree_matches_current_explicit_effect_contract(self):
        self.assertEqual(inspect(self.root), [])

    def test_new_unreviewed_effect_entry_fails_closed(self):
        dest = self.pkg / "sandbox_effect.py"
        dest.write_text(dest.read_text(encoding="utf-8") +
                        "\ndef hidden_effect():\n"
                        "    return stage_immutable(None, (), 'x', b'x')\n",
                        encoding="utf-8")
        self.assertTrue(any(x.startswith("UNREGISTERED_STAGE_EFFECT")
                            for x in inspect(self.root)))

    def test_import_alias_does_not_hide_new_writer(self):
        dest = self.pkg / "sandbox_effect.py"
        dest.write_text(dest.read_text(encoding="utf-8") +
                        "\nfrom .isolated_filesystem import stage_immutable as bypass\n"
                        "def hidden_effect_alias():\n"
                        "    return bypass(None, (), 'x', b'x')\n",
                        encoding="utf-8")
        self.assertTrue(any(x.startswith("UNREGISTERED_STAGE_EFFECT")
                            for x in inspect(self.root)))

    def test_missing_same_transaction_guard_fails_closed(self):
        self.mutate("pipeline_oracle",
                    "allowed,reason=current_guard(db,dict(row),needs_write=True)",
                    "allowed,reason=True,None")
        self.assertIn("REVIEW_GUARD_MISSING:pipeline_oracle:review_pipeline",
                      inspect(self.root))

    def test_new_unreviewed_artifact_entry_fails_closed(self):
        dest = self.pkg / "goal_loop.py"
        dest.write_text(dest.read_text(encoding="utf-8") +
                        "\ndef hidden_artifact_effect():\n"
                        "    return store_once(None, 'a'*32, b'x')\n",
                        encoding="utf-8")
        self.assertTrue(any(x.startswith("UNREGISTERED_ARTIFACT_EFFECT")
                            for x in inspect(self.root)))

    def test_new_direct_file_write_cannot_hide_outside_shared_stage(self):
        dest = self.pkg / "goal_loop.py"
        dest.write_text(dest.read_text(encoding="utf-8") +
                        "\ndef hidden_direct_write():\n"
                        "    from pathlib import Path\n"
                        "    return Path('untracked').write_bytes(b'x')\n",
                        encoding="utf-8")
        self.assertTrue(any(x.startswith("UNREGISTERED_DIRECT_FILE_EFFECT")
                            for x in inspect(self.root)))

    def test_missing_registered_review_module_fails_closed(self):
        (self.pkg / "repair_oracle.py").unlink()
        faults = inspect(self.root)
        self.assertIn("REVIEW_GUARD_MISSING:repair_oracle:review_patch", faults)
        self.assertIn("STAGE_EFFECT_COUNT:repair_oracle:_stage_patch:0", faults)


if __name__ == "__main__":
    unittest.main()
