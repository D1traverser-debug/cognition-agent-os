"""Offline negative controls for source-study honesty and upstream URL drift.

No model, GitHub/Library private data, external network, native invocation or
third-party business effect is created by these tests.
"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_agent_atlas", ROOT / "scripts/verify_agent_atlas.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class ResearchAtlasGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(mod.REGISTER.read_text(encoding="utf-8"))
        cls.cards = mod.CARDS.read_text(encoding="utf-8")

    def test_canonical_record_preserves_unstudied_and_studied_difference(self):
        observed = mod.validate(self.data, cards=self.cards)
        self.assertEqual(observed["total"], 96)
        unstudied = sum(r["status"] == "DISCOVERED_NOT_DEEPLY_AUDITED"
                         for r in self.data["records"])
        self.assertEqual(observed["source_only"], unstudied)
        self.assertEqual(observed["source_read"], len(self.data["records"]) - unstudied)
        self.assertFalse(observed["native_skill_trigger_or_user_outcome_tested"])
        self.assertFalse(observed["actual_upstream_links_checked"])

    def test_current_link_set_snapshot_with_explicit_readme_is_consistent(self):
        # Synthetic URL corpus tests comparison mechanism, not actual live Hub.
        snapshot = "\n".join(
            f"[{r['label']}]({r['url']})" for r in self.data["records"])
        self.assertTrue(mod.validate(
            self.data, cards=self.cards, source_readme=snapshot
        )["actual_upstream_links_checked"])
        with self.assertRaisesRegex(mod.AtlasError, "UPSTREAM_README_LINK_DRIFT"):
            mod.validate(self.data, cards=self.cards,
                         source_readme=snapshot + "\n[new](https://example.org/new)")
        without_one = "\n".join(snapshot.splitlines()[1:])
        with self.assertRaisesRegex(mod.AtlasError, "UPSTREAM_README_LINK_DRIFT"):
            mod.validate(self.data, cards=self.cards, source_readme=without_one)

    def test_cannot_promote_unread_link_to_studied_without_source(self):
        fake = copy.deepcopy(self.data)
        unread = next(x for x in fake["records"] if x["status"] ==
                      "DISCOVERED_NOT_DEEPLY_AUDITED")
        unread["status"] = "SOURCE_AND_CODE_READ"
        with self.assertRaises(mod.AtlasError):
            mod.validate(fake, cards=self.cards)

    def test_research_status_can_grow_without_rewriting_validation_code(self):
        fake = copy.deepcopy(self.data)
        item = next(r for r in fake["records"]
                    if r["status"] == "DISCOVERED_NOT_DEEPLY_AUDITED")
        item["status"] = "SOURCE_AND_CODE_READ"
        item["evidence"] = [{
            "repo": "example/repo", "path": "src/implementation.py",
            "blob_sha": "a" * 40, "kind": "implementation"
        }]
        before = mod.validate(self.data, cards=self.cards)
        after = mod.validate(fake, cards=self.cards)
        self.assertEqual(after["source_read"], before["source_read"] + 1)
        self.assertEqual(after["source_only"], before["source_only"] - 1)

    def test_study_status_requires_corresponding_source_kind(self):
        fake = copy.deepcopy(self.data)
        item = next(r for r in fake["records"] if
                    r["status"] == "DISCOVERED_NOT_DEEPLY_AUDITED")
        item["status"] = "SOURCE_AND_TEST_READ"
        item["evidence"] = [{
            "repo": "example/repo", "path": "README.md",
            "blob_sha": "a" * 40, "kind": "docs"
        }]
        with self.assertRaisesRegex(mod.AtlasError, "STUDY_STATUS_UNSUPPORTED_BY_EVIDENCE"):
            mod.validate(fake, cards=self.cards)

    def test_stale_evidence_and_duplicates_fail_closed(self):
        fake = copy.deepcopy(self.data)
        read = next(x for x in fake["records"] if x["evidence"])
        read["evidence"][0]["blob_sha"] = "unknown"
        with self.assertRaisesRegex(mod.AtlasError, "UNATTESTED_STUDY_EVIDENCE"):
            mod.validate(fake, cards=self.cards)
        fake = copy.deepcopy(self.data)
        fake["records"][0]["url"] = fake["records"][1]["url"]
        with self.assertRaisesRegex(mod.AtlasError, "INVALID_RECORD_OR_DUPLICATE"):
            mod.validate(fake, cards=self.cards)

    def test_method_note_must_admit_incomplete_coverage(self):
        with self.assertRaisesRegex(mod.AtlasError, "MISSING_EXPLICIT_UNSTUDIED_BOUNDARY"):
            mod.validate(self.data, cards="All 96 resources deeply mastered.")

if __name__ == "__main__":
    unittest.main()
