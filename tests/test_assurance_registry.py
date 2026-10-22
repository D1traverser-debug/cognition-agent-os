"""Meta-V&V: intentionally corrupt the acceptance inventory and require rejection."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_assurance_registry import check, RegistryError

class AssuranceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / 'evaluation/assurance_registry_v1.json').read_text())
        cls.conops = (ROOT / 'docs/00-PRODUCT-CONOPS.md').read_text()
        cls.readiness = (ROOT / 'docs/PRODUCT-READINESS-GATE.md').read_text()

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

if __name__ == '__main__':
    unittest.main()
