from __future__ import annotations

import json
from pathlib import Path

ROOT = Path('.')
CONFIG = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'case_config.json'
README = ROOT / 'case_studies' / 'tem_external_validation_candidate_registry' / 'README.md'
TESTS = ROOT / 'tests' / 'test_tem_external_validation_candidate_registry.py'

payload = json.loads(CONFIG.read_text(encoding='utf-8'))
payload['search_snapshot']['search_date'] = '2026-08-03'
for term in (
    'Co3O4 NiO TEM raw data replication package',
    'palygorskite Co3O4 TEM public archive',
):
    if term not in payload['search_snapshot']['search_terms']:
        payload['search_snapshot']['search_terms'].append(term)

new_candidates = [
    {
        'candidate_id': 'zenodo_14160831_co3o4_nio_replication_package',
        'repository': 'Zenodo',
        'doi': '10.5281/zenodo.14160831',
        'record_url': 'https://zenodo.org/records/14160831',
        'title': 'On the epitaxial growth in ALD Co3O4- and NiO-based bilayers',
        'materials': ['Co3O4', 'NiO', 'Co3O4/NiO bilayers'],
        'modalities': ['tabular replication package'],
        'file_inventory_status': 'exact',
        'file_checksums_available': True,
        'raw_or_lossless_tem_images_available': False,
        'reported_tem_file_count': 0,
        'independent_segmentation_labels_available': False,
        'label_origin': 'no public TEM image files or segmentation labels',
        'labeler_count': None,
        'blinded_labeling_verified': False,
        'adjudicated_consensus_available': False,
        'immutable_sample_ids_available': False,
        'immutable_acquisition_ids_available': False,
        'verified_not_used_for_target_training_or_model_selection': False,
        'target_creator_name_overlap': False,
        'target_material_relation': 'heterojunction_contains_cobalt_oxide',
        'imaging_domain_relation': 'wrong_modality',
        'reuse_license': 'CC-BY-4.0',
        'reuse_license_verified': True,
        'target_training_source': False,
        'source_evidence': [
            'The official Zenodo record is CC-BY-4.0 and exposes exactly one file, replication_package.xlsx, at 383655 bytes with repository MD5 862e64d9ebeba6fb34da16e89d5c19c4.',
            'The associated study reports cross-sectional TEM/STEM, but the public record contains no TEM, HRTEM, STEM, DM3, DM4, EMD, SER, TIFF, or other detector-image file.',
            'Literature evidence that microscopy was performed does not establish that reusable microscopy source arrays were deposited.'
        ],
        'next_validation_step': 'Exclude the current public record from TEM segmentation validation. Reconsider only if the authors or curator publish checksum-bound detector or lossless TEM files with immutable sample/acquisition lineage.',
    },
    {
        'candidate_id': 'mendeley_kkk76z8g8z_current_public_archive',
        'repository': 'Mendeley Data',
        'doi': '10.17632/kkk76z8g8z.1',
        'record_url': 'https://data.mendeley.com/datasets/kkk76z8g8z/1',
        'title': 'Data for: Palygorskite@Co3O4 nanocomposites as efficient peroxidase mimics for colorimetric detection of H2O2 and ascorbic acid',
        'materials': ['palygorskite', 'Co3O4', 'palygorskite@Co3O4'],
        'modalities': ['SEM', 'XRD', 'FTIR', 'UV-Vis', 'fluorescence spectroscopy'],
        'file_inventory_status': 'exact',
        'file_checksums_available': True,
        'raw_or_lossless_tem_images_available': False,
        'reported_tem_file_count': 0,
        'independent_segmentation_labels_available': False,
        'label_origin': 'no public TEM image files or segmentation labels',
        'labeler_count': None,
        'blinded_labeling_verified': False,
        'adjudicated_consensus_available': False,
        'immutable_sample_ids_available': False,
        'immutable_acquisition_ids_available': False,
        'verified_not_used_for_target_training_or_model_selection': False,
        'target_creator_name_overlap': False,
        'target_material_relation': 'exact_cobalt_oxide',
        'imaging_domain_relation': 'wrong_modality',
        'reuse_license': 'CC-BY-4.0',
        'reuse_license_verified': True,
        'target_training_source': False,
        'source_evidence': [
            'The current version-1 Mendeley public API resolves Data.rar as file UUID 251b0061-cc22-48b4-bc3d-8bba56f8a030, 16250421 bytes, SHA-256 e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9.',
            'Checksum-bound extraction contains 760 file members. The only image-decodable files are Data/SEM/2.png, Data/SEM/3.png, and Data/SEM/4.png; all are 1536 x 1103 16-bit PNG images.',
            'No archive member path or decodable image provides TEM or HRTEM source data despite the associated article describing TEM observations.'
        ],
        'next_validation_step': 'Exclude the current public archive from TEM segmentation validation. Reopen only if a versioned repository release explicitly deposits checksum-bound TEM/HRTEM files with immutable sample/acquisition lineage.',
    },
]
existing = {item['candidate_id'] for item in payload['candidates']}
for candidate in new_candidates:
    if candidate['candidate_id'] not in existing:
        payload['candidates'].append(candidate)
CONFIG.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

readme = README.read_text(encoding='utf-8')
readme = readme.replace('refreshed on 2026-08-02', 'refreshed on 2026-08-03')
anchor = '- Zenodo `10.5281/zenodo.7941248`: Co3O4 SEM/XPS/HAXPES; wrong modality.\n'
addition = (
    anchor
    + '- Zenodo `10.5281/zenodo.14160831`: Co3O4/NiO TEM/STEM is reported in the publication, but the public record contains only `replication_package.xlsx`; wrong public modality.\n'
    + '- Mendeley Data `10.17632/kkk76z8g8z.1`: the checksum-bound current archive contains 760 members and only three SEM PNG images; no deposited TEM/HRTEM files.\n'
)
if 'zenodo.14160831' not in readme:
    if anchor not in readme:
        raise SystemExit('README source-list anchor not found')
    readme = readme.replace(anchor, addition, 1)
README.write_text(readme, encoding='utf-8')

tests = TESTS.read_text(encoding='utf-8')
tests = tests.replace(
    '    RESULT,\n    CandidateContractError,',
    '    RESULT,\n    WRONG_MODALITY,\n    CandidateContractError,',
    1,
)
tests = tests.replace('"candidate_count": 7,', '"candidate_count": 9,', 1)
tests = tests.replace('"excluded_control_count": 3,', '"excluded_control_count": 5,', 1)
tests = tests.replace('assert printed["candidate_count"] == 7', 'assert printed["candidate_count"] == 9', 1)
marker = '\n\ndef test_phaset3m_processed_exact_material_is_diagnostic_only(\n'
new_test = '''\n\ndef test_new_co3o4_public_records_are_wrong_modality_exclusions(\n    tmp_path: Path,\n) -> None:\n    output = tmp_path / "out"\n    run_candidate_registry(load_registry_config(CONFIG), output)\n    with (output / "tem_external_validation_candidate_inventory.csv").open(\n        encoding="utf-8", newline=""\n    ) as handle:\n        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}\n\n    zenodo = rows["zenodo_14160831_co3o4_nio_replication_package"]\n    assert zenodo["candidate_status"] == WRONG_MODALITY\n    assert zenodo["reported_tem_file_count"] == "0"\n    assert zenodo["raw_or_lossless_tem_images_available"] == "False"\n    assert "replication_package.xlsx" in zenodo["source_evidence"]\n    assert "862e64d9ebeba6fb34da16e89d5c19c4" in zenodo["source_evidence"]\n\n    mendeley = rows["mendeley_kkk76z8g8z_current_public_archive"]\n    assert mendeley["candidate_status"] == WRONG_MODALITY\n    assert mendeley["reported_tem_file_count"] == "0"\n    assert mendeley["raw_or_lossless_tem_images_available"] == "False"\n    assert "251b0061-cc22-48b4-bc3d-8bba56f8a030" in mendeley["source_evidence"]\n    assert "e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9" in mendeley["source_evidence"]\n    assert "760 file members" in mendeley["source_evidence"]\n    assert "Data/SEM/2.png" in mendeley["source_evidence"]\n\n'''
if 'test_new_co3o4_public_records_are_wrong_modality_exclusions' not in tests:
    if marker not in tests:
        raise SystemExit('test insertion anchor not found')
    tests = tests.replace(marker, new_test + marker, 1)
TESTS.write_text(tests, encoding='utf-8')
