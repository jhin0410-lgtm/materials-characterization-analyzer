from __future__ import annotations

import json
from pathlib import Path


SNAPSHOT = Path(
    "case_studies/zenodo_in2o3_insitu_tem_model_lineage/verified_model_lineage.json"
)


def _snapshot() -> dict[str, object]:
    value = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_hdf5_size_matches_two_10k_float32_512_square_arrays_plus_small_container_overhead() -> None:
    snapshot = _snapshot()
    check = snapshot["size_consistency_check"]
    expected_payload = (
        check["synthetic_images"]
        * check["height"]
        * check["width"]
        * check["bytes_per_float32"]
        * check["float32_datasets"]
    )
    assert expected_payload == 20_971_520_000
    assert check["theoretical_array_payload_bytes"] == expected_payload
    assert check["observed_hdf5_bytes"] == 20_971_522_048
    assert check["observed_hdf5_bytes"] - expected_payload == check["difference_bytes"] == 2048


def test_hdf5_is_not_retained_as_raw_temporal_candidate() -> None:
    snapshot = _snapshot()
    assessment = snapshot["evidence_assessment"]
    assert assessment["hdf5_role_as_synthetic_model_development_dataset"] == "Supported"
    assert assessment["hdf5_role_as_raw_experimental_temporal_trajectory"] == "Unsupported"
    assert assessment["raw_temporal_trajectory_stress_test_using_this_zenodo_hdf5"] == "Unsupported"
    assert assessment["synthetic_training_pipeline_reproduction_use"] == "Diagnostic"
    assert assessment["external_validation_use"] == "Unsupported"


def test_exact_generator_provenance_is_not_overclaimed() -> None:
    snapshot = _snapshot()
    facts = snapshot["verified_method_facts"]
    assert facts["synthetic_generator_shape_contract"]["generator_output_filename_in_public_script"] == (
        "dataset_3/testtest.h5"
    )
    assert snapshot["source_dataset"]["hdf5"]["key"] == "set280624.h5"
    assert snapshot["evidence_assessment"]["exact_generator_run_to_zenodo_hdf5_byte_provenance"] == (
        "Inconclusive"
    )


def test_model_and_hdf5_are_development_coupled() -> None:
    snapshot = _snapshot()
    assessment = snapshot["evidence_assessment"]
    assert assessment["model_weights_independent_of_hdf5_training_corpus"] == "Unsupported"
    assert assessment["model_development_independent_of_experimental_difference_image_distribution"] == (
        "Unsupported"
    )
    facts = snapshot["verified_method_facts"]
    assert facts["paper_training_count"] == {
        "status": "Supported",
        "synthetic_images": 10000,
        "training_images": 8000,
        "validation_images": 2000,
    }


def test_public_code_snapshot_is_pinned_but_not_claimed_as_exact_execution_environment() -> None:
    snapshot = _snapshot()
    code = snapshot["code_source"]
    assert code["snapshot_commit"] == "372ad5bbb3eff82bb8c3bb58060d2f6649f069de"
    assert code["files"]["train.py"] == "56b3e0741bfd02afcda0834ccacb8283e9f5ea0f"
    assert code["files"]["synthetic_diff_map.py"] == "8134ff402b5ff81587d04bff4bb93bdaad7fc06f"
    assert "no release tag or checksum" in code["historical_identity_boundary"]
