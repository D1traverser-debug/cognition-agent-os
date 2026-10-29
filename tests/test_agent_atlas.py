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

    def test_nested_research_graph_reaches_all_linked_sources(self):
        observed = mod.validate(self.data, cards=self.cards)
        self.assertEqual(observed["nested_total"], len(self.data["nested_records"]))
        self.assertGreater(observed["nested_total"], 0)
        self.assertEqual(observed["all_total"],
                         observed["total"] + observed["nested_total"])
        for record in self.data["records"]:
            for lead in record["nested_leads"]:
                self.assertIn(lead, {r["url"] for r in self.data["nested_records"]})

    def test_studied_github_repo_cannot_borrow_other_repo_evidence(self):
        """A valid SHA in the wrong repository must NOT certify reading."""
        evidence = copy.deepcopy(self.data)
        entry = next(x for x in evidence["records"]
                     if x["url"] == "https://github.com/shareAI-lab/learn-claude-code")
        self.assertEqual(entry["status"], "SOURCE_AND_TEST_READ")
        self.assertIn("s08_context_compact/code.py",
                      [x["path"] for x in entry["evidence"]])
        entry["evidence"] = [
            {**item, "repo": "unrelated/misleading"} for item in entry["evidence"]]
        with self.assertRaisesRegex(mod.AtlasError, "STUDY_EVIDENCE_SOURCE_MISMATCH"):
            mod.validate(evidence, cards=self.cards)
        self.assertIn("## Method card L", self.cards)
        self.assertIn("client tests remain **NOT_TESTED**", self.cards)
        self.assertFalse(mod.validate(self.data, cards=self.cards)
                         ["native_skill_trigger_or_user_outcome_tested"])

    def test_context_doctor_primary_source_depth_and_discovery_boundary(self):
        """Study-status integrity, never a claimed live client launch."""
        doctor = next(x for x in self.data["nested_records"]
                      if x["url"].endswith("/context-doctor/SKILL.md"))
        self.assertEqual(doctor["status"], "SOURCE_AND_METHOD_READ")
        self.assertEqual(doctor["evidence"][0]["blob_sha"],
                         "30980fffcf03ecbf9277f8ad1c2009894fc78943")
        audit = next(x for x in self.data["nested_records"]
                     if x["url"].endswith("/context-doctor/references/auditing-memory.md"))
        self.assertIn(audit["url"], doctor["nested_leads"])
        self.assertIn("link alone", self.cards)
        self.assertIn("new-chat behavior is **not verified**", self.cards)
        self.assertFalse(mod.validate(self.data, cards=self.cards)
                         ["native_skill_trigger_or_user_outcome_tested"])

    def test_nested_link_without_status_record_is_rejected(self):
        fake = copy.deepcopy(self.data)
        fake["records"][0]["nested_leads"].append("https://example.org/deeper")
        with self.assertRaisesRegex(mod.AtlasError, "NESTED_LEAD_MISSING_OR_UNLINKED_RECORD"):
            mod.validate(fake, cards=self.cards)

    def test_unlinked_nested_record_and_duplicate_url_are_rejected(self):
        fake = copy.deepcopy(self.data)
        fake["nested_records"][0]["url"] = "https://example.org/unlinked"
        with self.assertRaisesRegex(mod.AtlasError, "NESTED_LEAD_MISSING_OR_UNLINKED_RECORD"):
            mod.validate(fake, cards=self.cards)
        fake = copy.deepcopy(self.data)
        fake["nested_records"].append(copy.deepcopy(fake["nested_records"][0]))
        with self.assertRaisesRegex(mod.AtlasError, "INVALID_RECORD_OR_DUPLICATE"):
            mod.validate(fake, cards=self.cards)

    def test_new_recursive_depth_is_admitted_with_status_and_evidence(self):
        fake = copy.deepcopy(self.data)
        parent = fake["nested_records"][0]
        parent["nested_leads"].append("https://example.org/third-level")
        fake["nested_records"].append({
            "url": "https://example.org/third-level",
            "label": "Independent third-level target",
            "status": "DISCOVERED_NOT_DEEPLY_AUDITED",
            "evidence": [], "nested_leads": []
        })
        observed = mod.validate(fake, cards=self.cards)
        self.assertEqual(observed["nested_total"], len(self.data["nested_records"]) + 1)
        self.assertEqual(observed["nested_frontier"],
                         mod.validate(self.data, cards=self.cards)["nested_frontier"] + 1)

    def test_nested_research_cannot_claim_test_evidence_from_docs_only(self):
        fake = copy.deepcopy(self.data)
        target = next(x for x in fake["nested_records"]
                      if x["status"] == "DISCOVERED_NOT_DEEPLY_AUDITED")
        target["status"] = "SOURCE_AND_TEST_READ"
        target["evidence"] = [{
            "repo": "sample/other", "path": "README.md",
            "blob_sha": "c" * 40, "kind": "docs"
        }]
        with self.assertRaisesRegex(mod.AtlasError, "STUDY_STATUS_UNSUPPORTED_BY_EVIDENCE"):
            mod.validate(fake, cards=self.cards)

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
