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
        name = s.get('archived_basename', '')
        require(isinstance(name, str) and bool(name) and name not in ('.','..')
                and '/' not in name and '\\' not in name,
                f'{key}: archive ref must be a basename')
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


# Immutable Git blob ID of the original long, multiply-"CURRENT" handoff.
# The archive is evidence, not an alternate source of live project commands.
_ARCHIVE_HANDOFF = 'archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md'
_ARCHIVE_GIT_BLOB_SHA1 = '6bc6ad3041876916c16886767ce2ff24bfd88b75'
# Safety ceiling for the bootstrap index, NOT a target size and NOT storage.
# Full work provenance belongs in Git/runtime sources and is fetched on demand.
_MAX_ACTIVE_HANDOFF_BYTES = 8192

# Only durable current product specifications belong in docs/. Dated milestone,
# benchmark, audit and experiment reports live under archive/ and are retrieved
# explicitly when historical evidence is material. This prevents broad agent
# search from silently promoting old plans into current context.
_ACTIVE_DOCS = {
    'docs/00-PRODUCT-CONOPS.md',
    'docs/01-ARCHITECTURE-DECISIONS.md',
    'docs/02-AUTHORITY-AND-INTERFACES.md',
    'docs/04-SECURITY-OPERATIONS.md',
    'docs/06-ZERO-API-CREDIT-POLICY.md',
    'docs/PRODUCT-READINESS-GATE.md',
}

def verify_active_context_surface(root):
    docs = root / 'docs'
    actual = {
        p.relative_to(root).as_posix()
        for p in docs.iterdir()
        if p.is_file() and not p.is_symlink()
    }
    require(actual == _ACTIVE_DOCS,
            'active docs drifted; historical/experimental material must be '
            'archived, not added to default agent context')
    require(not (root / 'README-P1.md').exists(),
            'obsolete P1 readme returned to active repository root')
    require(not (root / 'audits').exists(),
            'dated audit snapshots must remain under archive/')
    for relative in (
        'scripts/codex_session_context.py',
        'AGENTS.md',
        'integrations/chatgpt/cognition-agent-os-chatgpt/skills/'
        'cognition-parent-chatgpt-intake/SKILL.md',
    ):
        text = (root / relative).read_text(encoding='utf-8')
        require('archive/docs/' not in text and 'archive/audits/' not in text,
                relative + ': default agent entrypoint must not load archived '
                'evidence without an explicit historical task')
    return {
        'status': 'ACTIVE_CONTEXT_SURFACE_VALID',
        'active_docs': sorted(actual),
        'historical_default_loaded': False,
    }

def verify_live_handoff(root):
    """Check only identity, active/archive isolation and stale-context hygiene.

    NOT a proof that retrieved prose is semantically correct, current GitHub
    state is live, or any owner objective has been achieved.
    """
    active_path = root / 'SESSION_HANDOFF.md'
    archive_path = root / _ARCHIVE_HANDOFF
    readme_path = root / 'README.md'
    for path in (active_path, archive_path, readme_path):
        require(path.is_file() and not path.is_symlink(),
                'missing, linked or unsuitable context source: ' + path.name)
    raw = active_path.read_bytes()
    require(0 < len(raw) <= _MAX_ACTIVE_HANDOFF_BYTES,
            'bootstrap handoff exceeded safety ceiling; retrieve full history '
            'from live sources instead of compressing it into this file')
    try:
        live = raw.decode('utf-8')
        readme = readme_path.read_text(encoding='utf-8')
    except UnicodeError as exc:
        raise RegistryError('context text must be UTF-8') from exc
    # Static checks must never bless a historical PR number as the LIVE head.
    # A dated navigation snapshot is permitted; only host/GitHub ref reads
    # can establish the actual current code and authorization.
    headings = [line for line in live.splitlines()
                if re.match(r'^#+\s+CURRENT\b', line)]
    require(not headings, 'dated handoff must not assert CURRENT authority')
    first = live.splitlines()[0] if live.splitlines() else ''
    require(re.fullmatch(
        r'# cognition-agent-os — dated continuation pointer \(\d{4}-\d{2}-\d{2}\)',
        first) is not None, 'handoff must be a date-scoped non-authoritative pointer')
    require('live GitHub' in live and 'exact HEADs' in live
            and 'ALL open Draft PRs' in live,
            'handoff lacks explicit live-authority resolution requirement')
    require('BOOTSTRAP INDEX ONLY' in live
            and 'not a complete work log' in live
            and 'progressive disclosure' in live,
            'handoff must remain a bootstrap index, not a project database')
    require('commit history' in live and 'Files changed' in live
            and 'Do NOT duplicate' in live,
            'handoff must defer complete work history to live Git provenance')
    require('current *development* integration tip' not in readme
            and 'live GitHub' in readme,
            'README must not freeze an obsolete live PR as active')
    require('NOT_READY' in live and 'NOT_READY' in readme,
            'cannot silently promote incomplete product via handoff')
    require('archive/SESSION_HANDOFF_20261024_PRE_COMPACTION.md' in live,
            'historical evidence is not explicitly discoverable')
    require('**START HERE, NOT THE HISTORICAL' not in live,
            'superseded START HERE leaked into live context')
    historical = archive_path.read_bytes()
    # Git SHA-1 object ID contains the original exact byte length and bytes.
    blob = b'blob ' + str(len(historical)).encode('ascii') + b'\x00' + historical
    require(hashlib.sha1(blob).hexdigest() == _ARCHIVE_GIT_BLOB_SHA1,
            'archived original text was lost or silently changed')
    require(historical != raw and len(historical) > _MAX_ACTIVE_HANDOFF_BYTES,
            'history was rewritten as the current brief')
    return {'status': 'DATED_HANDOFF_VALID',
            'active_bytes': len(raw),
            'archive_integrity': 'EXACT_GIT_BLOB',
            'current_ref_verified': False,
            'historical_instruction_authority': False,
            'semantic_claims_verified': False}

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--archive-dir', type=Path, default=None)
    opts = p.parse_args(argv)
    try:
        root = opts.root
        reg = json.loads((root / 'evaluation/assurance_registry_v1.json').read_text(encoding='utf-8'))
        result = check(reg,
                       (root / 'docs/00-PRODUCT-CONOPS.md').read_text(encoding='utf-8'),
                       (root / 'docs/PRODUCT-READINESS-GATE.md').read_text(encoding='utf-8'))
        result['active_handoff'] = verify_live_handoff(root)
        result['active_context_surface'] = verify_active_context_surface(root)
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
