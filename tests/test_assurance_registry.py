"""Meta-V&V: intentionally corrupt the acceptance inventory and require rejection."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_assurance_registry import (check, RegistryError, verify_archived_sources,
                                       verify_live_handoff, verify_active_context_surface)

class AssuranceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / 'evaluation/assurance_registry_v1.json').read_text(encoding='utf-8'))
        cls.conops = (ROOT / 'docs/00-PRODUCT-CONOPS.md').read_text(encoding='utf-8')
        cls.readiness = (ROOT / 'docs/PRODUCT-READINESS-GATE.md').read_text(encoding='utf-8')

    def rejected(self, edit):
        reg = copy.deepcopy(self.registry)
        edit(reg)
        with self.assertRaises(RegistryError):
            check(reg, self.conops, self.readiness)

    def test_well_formed_still_not_release_or_independent_vv(self):
        result = check(self.registry, self.conops, self.readiness)
        self.assertEqual(result['status'], 'STATIC_INVENTORY_VALID')
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['independent_verification'], 'NOT_PERFORMED')

    def test_missing_and_duplicate_requirements_killed(self):
        self.rejected(lambda x: x['requirements'].pop())
        self.rejected(lambda x: x['requirements'].__setitem__(
            1, copy.deepcopy(x['requirements'][0])))

    def test_fake_stakeholder_approval_and_self_verification_killed(self):
        self.rejected(lambda x: x['requirements'][0].__setitem__('stakeholder_approved', True))
        self.rejected(lambda x: x['requirements'][0].__setitem__('verification_status', 'VERIFIED'))
        self.rejected(lambda x: x['requirements'][0].__setitem__('validation_evidence', ['self-grade']))

    def test_unfounded_product_promotion_killed(self):
        self.rejected(lambda x: x['product_gates'][0].__setitem__('status', 'ACCEPTED'))
        self.rejected(lambda x: x.__setitem__('release_ready', True))

    def test_missing_oracle_and_automation_limits_killed(self):
        self.rejected(lambda x: x['requirements'][0]['verification_design'].pop('method'))
        self.rejected(lambda x: x['requirements'][0]['verification_design'].pop('proposed_oracle'))
        self.rejected(lambda x: x['requirements'][0]['verification_design'].__setitem__('limit', 'AUTOMATED_FULL'))

    def test_legacy_ot06_cold_resume_is_not_worker_restart(self):
        def mutant(x):
            x['legacy_scenarios'][5]['relation'] = 'PARTIAL_NOT_ACCEPTED'
            x['legacy_scenarios'][5]['current_refs'] = ['OT06']
        self.rejected(mutant)

    def test_legacy_ot07_injection_is_not_revocation(self):
        def mutant(x):
            x['legacy_scenarios'][6]['relation'] = 'PARTIAL_NOT_ACCEPTED'
            x['legacy_scenarios'][6]['current_refs'] = ['OT07']
        self.rejected(mutant)

    def test_current_scenario_drift_detected(self):
        self.rejected(lambda x: x['current_scenarios'].pop())
        with self.assertRaises(RegistryError):
            check(self.registry, self.conops.replace(
                '到期且用户未再发消息', '失去上下文自动理解原始用户需求'), self.readiness)

    def test_product_readiness_text_cannot_silently_flip(self):
        with self.assertRaises(RegistryError):
            check(self.registry, self.conops, self.readiness.replace(
                '**Current disposition: NOT_READY', '**Current disposition: READY'))

    def test_ci_cannot_claim_private_original_source_was_verified(self):
        self.rejected(lambda x: x['source_registry']['legacy_conops'].__setitem__(
            'source_bytes_checked_in_ci', True))

    def test_archive_path_traversal_rejected(self):
        self.rejected(lambda x: x['source_registry']['legacy_conops'].__setitem__(
            'archived_basename', '../untrusted.json'))

    def test_active_handoff_is_small_dated_navigation_not_live_authority(self):
        report = verify_live_handoff(ROOT)
        self.assertEqual(report['status'], 'DATED_HANDOFF_VALID')
        self.assertFalse(report['current_ref_verified'])
        self.assertEqual(report['archive_integrity'], 'EXACT_GIT_BLOB')
        self.assertLess(report['active_bytes'], 8192)

    def test_primary_context_is_selective_not_fixed_directory_whitelist(self):
        report = verify_active_context_surface(ROOT)
        self.assertEqual(report['status'], 'ACTIVE_CONTEXT_SURFACE_VALID')
        self.assertFalse(report['default_agent_loading_observed'])
        self.assertEqual(len(report['primary_docs']), 6)
        self.assertGreater(report['other_docs_available_on_demand'], 0)
        self.assertGreater(report['relative_links_checked'], 0)
        self.assertFalse((ROOT / 'README-P1.md').exists())
        self.assertFalse((ROOT / 'audits').exists())
        self.assertTrue((ROOT / 'docs/03-FIRST-VERTICAL-SLICE.md').is_file())
        self.assertTrue((ROOT / 'docs/ENGINEERING-COGNITION-TOOLCHAIN.md').is_file())
        self.assertTrue((ROOT / 'archive/audits/2026-10-25/whole-source-part-01.json').is_file())

    def test_moved_document_link_break_is_detected_without_excluding_new_docs(self):
        with tempfile.TemporaryDirectory() as d:
            from shutil import copytree, copy2
            dst = Path(d)
            copytree(ROOT / 'docs', dst / 'docs')
            (dst / 'archive').mkdir()
            for name in ('README.md', 'AGENTS.md'):
                copy2(ROOT / name, dst / name)
            report = verify_active_context_surface(dst)
            self.assertGreater(report['other_docs_available_on_demand'], 0)
            # A replacement link to a missing file must fail; this is exactly
            # the regression hidden by a prior mass doc archive.
            source = dst / 'docs/00-PRODUCT-CONOPS.md'
            source.write_text(source.read_text(encoding='utf-8').replace(
                '(03-FIRST-VERTICAL-SLICE.md)',
                '(does-not-exist.md)'), encoding='utf-8')
            with self.assertRaisesRegex(RegistryError, 'broken relative Markdown link'):
                verify_active_context_surface(dst)

    def test_archive_is_not_an_active_instruction_source(self):
        live = (ROOT / 'SESSION_HANDOFF.md').read_text(encoding='utf-8')
        self.assertEqual(len([
            line for line in live.splitlines()
            if line.startswith('# CURRENT')
        ]), 0)
        self.assertNotIn('## HISTORICAL CHECKPOINT ARCHIVE', live)
        self.assertNotIn('**START HERE, NOT THE HISTORICAL', live)

    def test_unconditional_history_preload_is_rejected(self):
        """Cold resume must not regress to a large mandatory PR crawl."""
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            (dst / 'README.md').write_text(
                (ROOT / 'README.md').read_text(encoding='utf-8'),
                encoding='utf-8')
            live = (ROOT / 'SESSION_HANDOFF.md').read_text(encoding='utf-8')
            live = live.replace(
                'PR **metadata**',
                'ALL open Draft PRs')
            (dst / 'SESSION_HANDOFF.md').write_text(live, encoding='utf-8')
            (dst / 'archive').mkdir()
            (dst / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').write_bytes(
                (ROOT / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').read_bytes())
            with self.assertRaisesRegex(
                    RegistryError, 'task-scoped live-authority'):
                verify_live_handoff(dst)

    def test_cold_handoff_without_default_branch_resolution_fails(self):
        """Merged integration must not force discovery of a nonexistent Draft."""
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            (dst / 'README.md').write_text(
                (ROOT / 'README.md').read_text(encoding='utf-8'),
                encoding='utf-8')
            live = (ROOT / 'SESSION_HANDOFF.md').read_text(encoding='utf-8')
            self.assertIn('GitHub default branch', live)
            live = live.replace('GitHub default branch', 'GitHub old open PR')
            (dst / 'SESSION_HANDOFF.md').write_text(live, encoding='utf-8')
            (dst / 'archive').mkdir()
            source = ROOT / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md'
            (dst / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').write_bytes(
                source.read_bytes())
            with self.assertRaisesRegex(RegistryError, 'task-scoped live-authority'):
                verify_live_handoff(dst)

    def test_stale_handoff_substitution_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            (dst / 'README.md').write_text((ROOT / 'README.md').read_text(encoding='utf-8'), encoding='utf-8')
            (dst / 'SESSION_HANDOFF.md').write_text(
                (ROOT / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').read_text(encoding='utf-8'),
                encoding='utf-8')
            (dst / 'archive').mkdir()
            (dst / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').write_bytes(
                (ROOT / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').read_bytes())
            with self.assertRaises(RegistryError):
                verify_live_handoff(dst)

    def test_archive_tamper_and_false_current_head_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            (dst / 'README.md').write_text((ROOT / 'README.md').read_text(encoding='utf-8'), encoding='utf-8')
            (dst / 'SESSION_HANDOFF.md').write_text(
                (ROOT / 'SESSION_HANDOFF.md').read_text(encoding='utf-8'), encoding='utf-8')
            (dst / 'archive').mkdir()
            archive = dst / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md'
            archive.write_bytes(b'spoofed historical context')
            with self.assertRaises(RegistryError):
                verify_live_handoff(dst)
            archive.write_bytes(
                (ROOT / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').read_bytes())
            live = (dst / 'SESSION_HANDOFF.md')
            live.write_text(live.read_text(encoding='utf-8') +
                            '\\n# CURRENT misleading checkpoint\\n'.replace('\\n','\n'), encoding='utf-8')
            with self.assertRaises(RegistryError):
                verify_live_handoff(dst)


    def test_readme_cannot_restore_a_frozen_current_pr(self):
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d)
            (dst / 'README.md').write_text(
                'Current integration tip: PR #26\n' +
                (ROOT / 'README.md').read_text(encoding='utf-8'),
                encoding='utf-8')
            (dst / 'SESSION_HANDOFF.md').write_text(
                (ROOT / 'SESSION_HANDOFF.md').read_text(encoding='utf-8'),
                encoding='utf-8')
            (dst / 'archive').mkdir()
            (dst / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').write_bytes(
                (ROOT / 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md').read_bytes())
            with self.assertRaises(RegistryError):
                verify_live_handoff(dst)

    def test_changed_original_archive_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.registry['source_registry']['legacy_conops']
            Path(tmp, source['archived_basename']).write_bytes(b'altered source')
            with self.assertRaises(RegistryError):
                verify_archived_sources(self.registry, Path(tmp))

if __name__ == '__main__':
    unittest.main()
