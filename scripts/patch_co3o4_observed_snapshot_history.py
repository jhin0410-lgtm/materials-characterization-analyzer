from __future__ import annotations

import json
from pathlib import Path

ROOT = Path('.')
AUDIT_CONFIG = ROOT / 'case_studies' / 'co3o4_public_tem_candidate_audit' / 'case_config.json'
AUDIT_README = ROOT / 'case_studies' / 'co3o4_public_tem_candidate_audit' / 'README.md'
REGISTRY_CONFIG = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'case_config.json'
REGISTRY_README = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'README.md'

latest_snapshot = {
    'observed_date': '2026-08-03',
    'workflow_run_id': 30789059140,
    'artifact_id': 8846350084,
    'name': 'Data.rar',
    'bytes': 16250421,
    'sha256': 'e3afceb4e3b6cebabb16c19129d1959ec2620ac8b86d4e1bcc4cbccb413e4984',
    'observed_file_id': '251dd224-6e9e-4c25-810b-cc7c24702685',
    'file_id_role': 'download_routing_only',
    'member_count': 760,
    'decodable_images': [
        'Data/SEM/1_001.png',
        'Data/SEM/4_019.png',
        'Data/SEM/B_010.png',
    ],
    'tem_hrtem_stem_member_count': 0,
    'microscopy_detector_file_count': 0,
}

config = json.loads(AUDIT_CONFIG.read_text(encoding='utf-8'))
mendeley = config['sources']['mendeley_palygorskite_co3o4']
if not any(
    item['sha256'] == latest_snapshot['sha256']
    for item in mendeley['known_snapshots']
):
    mendeley['known_snapshots'].append(latest_snapshot)
AUDIT_CONFIG.write_text(
    json.dumps(config, indent=2, ensure_ascii=False) + '\n',
    encoding='utf-8',
)

registry = json.loads(REGISTRY_CONFIG.read_text(encoding='utf-8'))
candidate = next(
    item for item in registry['candidates']
    if item['candidate_id'] == 'mendeley_kkk76z8g8z_current_public_archive'
)
candidate['source_evidence'] = [
    'A checksum-bound version-1 snapshot of Data.rar was verified at 16250421 bytes with SHA-256 e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9; the API file UUID is download-routing metadata only.',
    'A later checksum-bound audit of the same DOI/version verified the same byte count but SHA-256 e3afceb4e3b6cebabb16c19129d1959ec2620ac8b86d4e1bcc4cbccb413e4984 and routing UUID 251dd224-6e9e-4c25-810b-cc7c24702685. The changed file UUID and SHA-256 demonstrate unstable public source identity, so stable immutable archive identity is unavailable.',
    'The first directly extracted snapshot contained 760 file members and only three 1536 x 1103 16-bit SEM PNG images: Data/SEM/2.png, Data/SEM/3.png, and Data/SEM/4.png.',
    'The later directly extracted snapshot also contained 760 file members and only three 1536 x 1103 16-bit SEM PNG images: Data/SEM/1_001.png, Data/SEM/4_019.png, and Data/SEM/B_010.png.',
    'Neither inspected snapshot contained a TEM, HRTEM, STEM, DM3, DM4, EMD, SER, TIFF, or TIF source file.',
]
REGISTRY_CONFIG.write_text(
    json.dumps(registry, indent=2, ensure_ascii=False) + '\n',
    encoding='utf-8',
)

audit_readme = AUDIT_README.read_text(encoding='utf-8')
marker = 'The records should be reconsidered only if a new immutable release deposits checksum-bound detector or demonstrably lossless TEM/HRTEM files with sample/acquisition lineage and target-model non-use evidence.\n'
addition = (
    'The 2026-08-03 audit history contains two directly verified version-1 archive snapshots with the same byte count but different SHA-256 values and different SEM member paths. Both snapshots remained wrong-modality controls with zero TEM/HRTEM/STEM or microscopy-detector files.\n\n'
    + marker
)
if 'two directly verified version-1 archive snapshots' not in audit_readme:
    if marker not in audit_readme:
        raise SystemExit('audit README closeout anchor not found')
    audit_readme = audit_readme.replace(marker, addition, 1)
AUDIT_README.write_text(audit_readme, encoding='utf-8')

registry_readme = REGISTRY_README.read_text(encoding='utf-8')
old = '- Mendeley Data `10.17632/kkk76z8g8z.1`: the checksum-bound current archive contains 760 members and only three SEM PNG images; no deposited TEM/HRTEM files.\n'
new = '- Mendeley Data `10.17632/kkk76z8g8z.1`: two directly verified version-1 snapshots had different SHA-256 values and different SEM member paths; both contained 760 members, only three SEM PNG images, and no deposited TEM/HRTEM/STEM files.\n'
if old in registry_readme:
    registry_readme = registry_readme.replace(old, new, 1)
REGISTRY_README.write_text(registry_readme, encoding='utf-8')
