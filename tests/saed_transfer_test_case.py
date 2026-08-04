from __future__ import annotations

import importlib.util
from pathlib import Path

DATA_PATH = Path(__file__).with_name("saed_transfer_test_data.py")
DATA_SPEC = importlib.util.spec_from_file_location("saed_transfer_test_data_for_case", DATA_PATH)
assert DATA_SPEC is not None and DATA_SPEC.loader is not None
data = importlib.util.module_from_spec(DATA_SPEC)
DATA_SPEC.loader.exec_module(data)

BUNDLE_PATH = Path(__file__).with_name("saed_transfer_test_bundle.py")
BUNDLE_SPEC = importlib.util.spec_from_file_location("saed_transfer_test_bundle", BUNDLE_PATH)
assert BUNDLE_SPEC is not None and BUNDLE_SPEC.loader is not None
bundle = importlib.util.module_from_spec(BUNDLE_SPEC)
BUNDLE_SPEC.loader.exec_module(bundle)

module = data.module
_sha = data._sha
_write_json = data._write_json
_source_tree = data._source_tree
_response_bundle = bundle._response_bundle

def _verification(
    tmp_path: Path,
    source_root: Path,
    response_root: Path,
    candidate: dict[str, object],
) -> Path:
    response_manifest = response_root / "saed_independent_source_response_manifest.json"
    collection = source_root / "source_manifest.json"
    payload = {
        "schema_version": "1.0",
        "case_id": module.CASE_ID,
        "response_case_id": module.SOURCE_REQUEST_CASE_ID,
        "response_artifact_manifest_sha256": _sha(response_manifest),
        "transfer_authorization": {
            "authorized": True,
            "authorized_by": "Principal Investigator",
            "authority_basis": "Dataset owner approval",
            "authorized_at": "2026-08-04",
            "scope": "declared_patterns_and_collection_manifest_only",
        },
        "collection_manifest": {
            "relative_path": "source_manifest.json",
            "sha256": _sha(collection),
            "bytes": collection.stat().st_size,
        },
        "dataset_verification": {
            "intake_source_type": candidate["source_type"],
            "source_type_mapping_basis": "Exact source declaration",
            "reuse_authorization_verified": True,
            "material_identity_source": "Source response and collection manifest",
            "creator_overlap_with_analyzer_development_source": False,
            "cross_dataset_lineage_independence_attested": True,
            "minimum_independent_samples": 2,
            "minimum_independent_acquisitions": 2,
        },
        "reference_verification": {
            "intake_reference_identifier": "COD:2102215",
            "reference_identifier_selection_basis": "Only declared reference",
        },
        "pattern_verifications": [
            {
                "pattern_id": "pattern-001",
                "material_id": "l_histidine_hydrochloride_monohydrate",
                "file_format": "TIFF",
                "camera_length_mm": 800.0,
                "preprocessing_operations": ["none"],
                "used_for_center_selection": False,
                "used_for_smoothing_selection": False,
                "used_for_prominence_selection": False,
                "used_for_radius_bound_selection": False,
                "used_for_candidate_count_selection": False,
                "excluded": False,
                "exclusion_reason": None,
            },
            {
                "pattern_id": "pattern-002",
                "material_id": "l_histidine_hydrochloride_monohydrate",
                "file_format": "MRC",
                "camera_length_mm": 800.0,
                "preprocessing_operations": ["none"],
                "used_for_center_selection": False,
                "used_for_smoothing_selection": False,
                "used_for_prominence_selection": False,
                "used_for_radius_bound_selection": False,
                "used_for_candidate_count_selection": False,
                "excluded": False,
                "exclusion_reason": None,
            },
        ],
    }
    path = tmp_path / "verification.json"
    _write_json(path, payload)
    return path


def _case(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    source, candidate = _source_tree(tmp_path)
    response = _response_bundle(tmp_path, candidate)
    verification = _verification(tmp_path, source, response, candidate)
    return source, response, verification, candidate



__all__ = ["module", "_sha", "_write_json", "_source_tree", "_response_bundle", "_verification", "_case"]
