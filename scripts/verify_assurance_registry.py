"""Fail-closed static inventory checks. NEVER a business/IV&V verdict."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

REQ_IDS = {f'R{i:02d}' for i in range(1, 25)}
OT_IDS = {f'OT{i:02d}' for i in range(1, 15)}
GATE_IDS = {f'G{i}' for i in range(1, 7)}
VALID_METHODS = {'ANALYSIS', 'INSPECTION', 'TEST', 'DEMONSTRATION'}
VALID_LIMITATIONS = {'AUTOMATED_PARTIAL', 'EXTERNAL_ORACLE_REQUIRED',
                     'HUMAN_JUDGMENT_REQUIRED', 'REAL_HOST_REQUIRED'}
VALID_RELATIONS = {'UNREVIEWED', 'PARTIAL_NOT_ACCEPTED',
                   'MISSING_EXPLICIT_SCENARIO'}
SHA256 = re.compile(r'^[0-9a-f]{64}$')

class RegistryError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise RegistryError(message)

def unique_ids(items, name, expected):
    require(isinstance(items, list), f'{name}: not a list')
    ids = [x.get('id') for x in items if isinstance(x, dict)]
    require(len(ids) == len(items) and len(set(ids)) == len(ids),
            f'{name}: duplicate/invalid IDs')
    require(set(ids) == expected, f'{name}: missing/extra IDs')

def check(registry, conops_text, readiness_text):
    """Validate draft inventory, not complete user requirements or product."""
    require(registry.get('schema_version') == 1, 'schema version')
    require(registry.get('classification') == 'DRAFT_INVENTORY_NOT_RELEASE_EVIDENCE',
            'not a draft inventory')
    require(registry.get('release_ready') is False, 'false release claim')
    require(registry.get('stakeholder_requirements_complete') is False,
            'cannot declare owner requirements complete')
    sources = registry.get('source_registry', {})
    for key in ('legacy_conops', 'legacy_extension'):
        s = sources.get(key, {})
        require(SHA256.fullmatch(str(s.get('sha256', ''))), f'{key}: no source SHA')
        require(s.get('source_bytes_checked_in_ci') is False,
                f'{key}: CI does not have private source bytes')
    unique_ids(registry.get('requirements'), 'historical candidates', REQ_IDS)
    for item in registry['requirements']:
        rid = item['id']
        require(item.get('origin') in sources, f'{rid}: no source identity')
        require(SHA256.fullmatch(str(item.get('draft_text_sha256', ''))),
                f'{rid}: no archived text hash')
        require(item.get('stakeholder_approved') is False, f'{rid}: fake owner approval')
        require(item.get('verification_status') == 'NOT_VERIFIED',
                f'{rid}: unsubstantiated verification')
        require(item.get('validation_status') == 'NOT_VALIDATED',
                f'{rid}: unsubstantiated validation')
        v = item.get('verification_design', {})
        require(v.get('method') in VALID_METHODS, f'{rid}: missing verification method')
        require(isinstance(v.get('proposed_oracle'), str)
                and bool(v['proposed_oracle'].strip()), f'{rid}: missing proposed oracle')
        require(v.get('limit') in VALID_LIMITATIONS,
                f'{rid}: automation/independence limits unspecified')
        require(item.get('verification_evidence') == []
                and item.get('validation_evidence') == [],
                f'{rid}: evidence must be adjudicated outside draft inventory')
    unique_ids(registry.get('legacy_scenarios'), 'historical OT', OT_IDS)
    unique_ids(registry.get('current_scenarios'), 'current OT', OT_IDS)
    current = {}
    for line in conops_text.splitlines():
        if re.match(r'^\| OT\d\d \|', line):
            cells = [x.strip() for x in line.strip().strip('|').split('|')]
            require(len(cells) >= 2 and cells[0] not in current,
                    'duplicate/malformed current OT')
            current[cells[0]] = cells[1]
    require(set(current) == OT_IDS, 'current OT labels no longer match inventory')
    for row in registry['current_scenarios']:
        require(row['description'] == current[row['id']],
                f"{row['id']}: current OT text drift")
    for row in registry['legacy_scenarios']:
        key = row['id']
        require(SHA256.fullmatch(str(row.get('archived_title_sha256', ''))),
                f'{key}: original description hash absent')
        require(row.get('relation') in VALID_RELATIONS,
                f'{key}: semantic migration classification missing')
        refs = row.get('current_refs')
        require(isinstance(refs, list) and len(refs) == len(set(refs))
                and set(refs) <= OT_IDS, f'{key}: malformed references')
        require(row.get('semantic_review_status') == 'UNREVIEWED',
                f'{key}: cannot self-certify semantic migration')
        if row['relation'] == 'MISSING_EXPLICIT_SCENARIO':
            require(refs == [], f'{key}: false same-number mapping')
    for key in ('OT06', 'OT07'):
        row = next(x for x in registry['legacy_scenarios'] if x['id'] == key)
        require(row['relation'] == 'MISSING_EXPLICIT_SCENARIO'
                and row['current_refs'] == [], f'{key}: old meaning not shown to survive')
    unique_ids(registry.get('product_gates'), 'readiness gates', GATE_IDS)
    for gate in registry['product_gates']:
        require(gate.get('status') == 'NOT_ACCEPTED'
                and gate.get('independent_evidence') == [],
                f"{gate['id']}: unsupported product acceptance")
        require(isinstance(gate.get('validation_design'), str)
                and bool(gate['validation_design'].strip()),
                f"{gate['id']}: missing product validation method")
    require('**Current disposition: NOT_READY' in readiness_text,
            'cannot promote product by silently editing prose')
    return {'status': 'STATIC_INVENTORY_VALID',
            'historical_candidates': 24, 'legacy_scenarios': 14,
            'product_gates': 6, 'release_ready': False,
            'independent_verification': 'NOT_PERFORMED'}

def verify_archived_sources(registry, directory):
    """Opt-in local auditor: requires original private archive bytes."""
    identities = {'legacy_conops': ('candidate_requirements', 'operational_threads'),
                  'legacy_extension': ('new_candidate_requirements', 'new_threads')}
    confirmed = []
    for origin, (req_key, ot_key) in identities.items():
        source = registry['source_registry'][origin]
        data = (directory / source['archived_basename']).read_bytes()
        require(hashlib.sha256(data).hexdigest() == source['sha256'],
                f'{origin}: original source digest mismatch')
        obj = json.loads(data)
        originals = {x['id']: (x['draft_requirement'] if origin == 'legacy_conops'
                               else x['text']) for x in obj[req_key]}
        claimed = {x['id']: x for x in registry['requirements']
                   if x['origin'] == origin}
        require(set(originals) == set(claimed), f'{origin}: missing original requirements')
        for key, value in originals.items():
            require(hashlib.sha256(value.encode()).hexdigest()
                    == claimed[key]['draft_text_sha256'],
                    f'{key}: original requirement text mismatch')
        old_titles = {x['id']: x.get('title', x.get('name')) for x in obj[ot_key]}
        legacy = {x['id']: x for x in registry['legacy_scenarios']
                  if x['id'] in old_titles}
        require(set(old_titles) == set(legacy), f'{origin}: historical scenarios missing')
        for key, title in old_titles.items():
            require(hashlib.sha256(title.encode()).hexdigest()
                    == legacy[key]['archived_title_sha256'],
                    f'{key}: original scenario title mismatch')
        confirmed.append({'origin': origin, 'sha256': source['sha256'],
                          'requirements': len(originals), 'scenarios': len(old_titles)})
    return confirmed

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--archive-dir', type=Path, default=None)
    opts = p.parse_args(argv)
    try:
        root = opts.root
        reg = json.loads((root / 'evaluation/assurance_registry_v1.json').read_text())
        result = check(reg,
                       (root / 'docs/00-PRODUCT-CONOPS.md').read_text(),
                       (root / 'docs/PRODUCT-READINESS-GATE.md').read_text())
        result['original_source_content_verified'] = (
            verify_archived_sources(reg, opts.archive_dir)
            if opts.archive_dir else 'NOT_CHECKED_CI_HAS_NO_PRIVATE_ARCHIVES')
    except (RegistryError, ValueError, KeyError, TypeError, OSError) as e:
        print(json.dumps({'status': 'STATIC_INVENTORY_INVALID',
                          'reason': str(e)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == '__main__':
    sys.exit(main())
