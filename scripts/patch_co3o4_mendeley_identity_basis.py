from __future__ import annotations

import json
from pathlib import Path

ROOT = Path('.')
AUDIT_SCRIPT = ROOT / 'scripts' / 'audit_co3o4_public_tem_candidates.py'
AUDIT_CONFIG = ROOT / 'case_studies' / 'co3o4_public_tem_candidate_audit' / 'case_config.json'
REGISTRY_CONFIG = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'case_config.json'
REGISTRY_README = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'README.md'
AUDIT_README = ROOT / 'case_studies' / 'co3o4_public_tem_candidate_audit' / 'README.md'
TESTS = ROOT / 'tests' / 'test_tem_external_validation_candidate_registry.py'

script = AUDIT_SCRIPT.read_text(encoding='utf-8')
script = script.replace(
    '    for key in ("file_id", "bytes", "sha256"):\n',
    '    for key in ("bytes", "sha256"):\n',
    1,
)
old_return = '''        {
            "dataset_id": dataset_id,
            "version": version,
            "doi": expected["doi"],
            "title": snapshot.get("name") or snapshot.get("title"),
            "license_verified": True,
            "files": observed_files,
        },
'''
new_return = '''        {
            "dataset_id": dataset_id,
            "version": version,
            "doi": expected["doi"],
            "title": snapshot.get("name") or snapshot.get("title"),
            "license_verified": True,
            "source_identity_basis": [
                "dataset_id",
                "version",
                "archive filename",
                "archive byte count",
                "archive SHA-256",
            ],
            "observed_download_file_id": archive["file_id"],
            "file_id_used_only_for_download_routing": True,
            "files": observed_files,
        },
'''
if old_return not in script:
    raise SystemExit('audit-script return anchor not found')
script = script.replace(old_return, new_return, 1)
AUDIT_SCRIPT.write_text(script, encoding='utf-8')

audit_config = json.loads(AUDIT_CONFIG.read_text(encoding='utf-8'))
audit_config['sources']['mendeley_palygorskite_co3o4']['archive'].pop('file_id', None)
audit_config['sources']['mendeley_palygorskite_co3o4']['archive'][
    'identity_basis'
] = ['name', 'bytes', 'sha256']
AUDIT_CONFIG.write_text(
    json.dumps(audit_config, indent=2, ensure_ascii=False) + '\n',
    encoding='utf-8',
)

registry = json.loads(REGISTRY_CONFIG.read_text(encoding='utf-8'))
candidate = next(
    item
    for item in registry['candidates']
    if item['candidate_id'] == 'mendeley_kkk76z8g8z_current_public_archive'
)
candidate['source_evidence'][0] = (
    'The current version-1 Mendeley public API resolves Data.rar at 16250421 bytes '
    'with SHA-256 e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9. '
    'The API file UUID is treated only as mutable download-routing metadata, not as source identity.'
)
REGISTRY_CONFIG.write_text(
    json.dumps(registry, indent=2, ensure_ascii=False) + '\n',
    encoding='utf-8',
)

for path in (REGISTRY_README, AUDIT_README):
    text = path.read_text(encoding='utf-8')
    marker = 'The audit distinguishes microscopy described in a publication from microscopy arrays actually deposited in the public data record.\n'
    addition = marker + '\nMendeley file UUIDs are treated as download-routing metadata. Reproducible source identity is bound to the versioned dataset, archive filename, byte count, SHA-256, and extracted representation.\n'
    if path == AUDIT_README and 'download-routing metadata' not in text:
        if marker not in text:
            raise SystemExit('audit README anchor not found')
        text = text.replace(marker, addition, 1)
    if path == REGISTRY_README and 'Mendeley file UUIDs are treated' not in text:
        conclusion = 'No assessed public candidate is ready for in-domain external validation.'
        text = text.replace(
            conclusion,
            'Mendeley file UUIDs are treated as mutable download-routing metadata; archive content identity is bound to filename, bytes, SHA-256, and extracted representation.\n\n' + conclusion,
            1,
        )
    path.write_text(text, encoding='utf-8')

tests = TESTS.read_text(encoding='utf-8')
tests = tests.replace(
    '    assert "251b0061-cc22-48b4-bc3d-8bba56f8a030" in mendeley["source_evidence"]\n',
    '    assert "download-routing metadata" in mendeley["source_evidence"]\n',
    1,
)
TESTS.write_text(tests, encoding='utf-8')
