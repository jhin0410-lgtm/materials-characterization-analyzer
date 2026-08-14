from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_zenodo_tem_candidate_metadata import (
    TemCandidateMetadataAuditError,
    build_snapshot,
    normalize_record,
    validate_config,
    verify_record,
)


def _boundary() -> dict[str, bool]:
    return {
        "metadata_api_request_authorized": True,
        "source_file_download_authorized": False,
        "remote_archive_inventory_authorized": False,
        "pixel_array_access_authorized": False,
        "model_weight_download_authorized": False,
        "model_execution_authorized": False,
        "analyzer_inference_authorized": False,
        "parameter_tuning_authorized": False,
        "model_retraining_authorized": False,
        "external_validation_claim_authorized": False,
        "engineering_decision_claim_authorized": False,
    }


def _rules() -> dict[str, bool]:
    return {
        "record_raw_tem_wording_does_not_prove_detector_native_or_lossless_representation": True,
        "filenames_or_folders_do_not_establish_immutable_acquisition_identity": True,
        "example_annotations_do_not_establish_complete_independent_ground_truth": True,
        "co_located_model_weights_do_not_establish_training_or_label_independence": True,
        "cross_material_tem_cannot_establish_cobalt_oxide_external_performance": True,
        "metadata_only_audit_cannot_establish_hdf5_schema_or_temporal_lineage": True,
        "declared_file_checksum_does_not_authorize_download_or_reuse": True,
    }


def _carbon_config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": "carbon",
        "audit_date": "2026-08-14",
        "candidate_profile": "cross_material_tem_segmentation",
        "source": {
            "repository": "Zenodo",
            "record_id": 21222653,
            "doi": "10.5281/zenodo.21222653",
            "record_url": "https://zenodo.org/records/21222653",
            "api_url": "https://zenodo.org/api/records/21222653",
            "expected_status": "published",
            "expected_resource_type": "dataset",
            "expected_title": "Carbon TEM",
            "landing_page_version_claim": "v1",
            "expected_files": [
                {"key": "Whole dataset.zip", "md5": "1" * 32}
            ],
            "expected_description_terms": [
                "raw TEM micrographs of all 15 samples",
                "segmented and annotated TEM micrographs",
            ],
        },
        "scientific_boundary": _boundary(),
        "decision_rules": _rules(),
    }


def _in2o3_config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": "in2o3",
        "audit_date": "2026-08-14",
        "candidate_profile": "in_situ_tem_temporal",
        "source": {
            "repository": "Zenodo",
            "record_id": 15052661,
            "doi": "10.5281/zenodo.15052661",
            "record_url": "https://zenodo.org/records/15052661",
            "api_url": "https://zenodo.org/api/records/15052661",
            "expected_status": "published",
            "expected_resource_type": "dataset",
            "expected_title": "In2O3 TEM",
            "landing_page_version_claim": None,
            "expected_files": [
                {"key": "model_10k.pth", "md5": "2" * 32},
                {"key": "set280624.h5", "md5": "3" * 32},
                {"key": "raw.xlsx", "md5": "4" * 32},
            ],
            "expected_description_terms": [],
        },
        "scientific_boundary": _boundary(),
        "decision_rules": _rules(),
    }


def _record(config: dict[str, object], *, license_id: str | None) -> dict[str, object]:
    source = config["source"]
    assert isinstance(source, dict)
    metadata: dict[str, object] = {
        "doi": source["doi"],
        "title": source["expected_title"],
        "resource_type": {"id": "dataset"},
        "description": (
            "This source contains raw TEM micrographs of all 15 samples and examples of "
            "segmented and annotated TEM micrographs."
        ),
        "publication_date": "2026-07-08",
    }
    if source["landing_page_version_claim"] is not None:
        metadata["version"] = source["landing_page_version_claim"]
    if license_id is not None:
        metadata["license"] = {"id": license_id}
    files = []
    for index, expected in enumerate(source["expected_files"], start=1):
        files.append(
            {
                "id": str(index),
                "key": expected["key"],
                "size": 1000 * index,
                "checksum": f"md5:{expected['md5']}",
                "links": {
                    "content": f"https://zenodo.org/api/records/{source['record_id']}/files/{index}/content"
                },
            }
        )
    return {
        "id": source["record_id"],
        "doi": source["doi"],
        "status": "published",
        "created": "2026-07-08T00:00:00+00:00",
        "updated": "2026-07-08T00:00:00+00:00",
        "metadata": metadata,
        "files": files,
    }


def test_metadata_only_boundary_keeps_every_stronger_operation_disabled() -> None:
    config = validate_config(_carbon_config())
    boundary = config["scientific_boundary"]
    assert boundary["metadata_api_request_authorized"] is True
    assert all(
        boundary[key] is False
        for key in boundary
        if key != "metadata_api_request_authorized"
    )


def test_copyright_is_not_treated_as_reuse_authorization() -> None:
    config = validate_config(_carbon_config())
    record = normalize_record(_record(_carbon_config(), license_id="copyright"))
    verification = verify_record(config, record)
    snapshot = build_snapshot(config, record, verification, config_sha256="a" * 64)

    assert snapshot["readiness"]["reuse_status"] == "copyright_only_reuse_not_established"
    assert snapshot["evidence_assessment"]["dataset_reuse_terms"] == "Inconclusive"
    assert snapshot["readiness"]["source_download_authorized"] is False
    assert snapshot["evidence_assessment"]["cobalt_oxide_material_domain_match"] == "Unsupported"
    assert snapshot["evidence_assessment"]["record_declared_raw_tem_for_15_samples"] == "Diagnostic"


def test_declared_open_license_still_requires_manual_reuse_review() -> None:
    config = validate_config(_carbon_config())
    record = normalize_record(_record(_carbon_config(), license_id="cc-by-4.0"))
    verification = verify_record(config, record)
    snapshot = build_snapshot(config, record, verification, config_sha256="b" * 64)

    assert snapshot["readiness"]["reuse_status"] == (
        "dataset_license_declared_manual_reuse_review_required"
    )
    assert snapshot["readiness"]["source_download_authorized"] is False
    assert snapshot["readiness"]["external_validation_ready"] is False


def test_in2o3_metadata_does_not_infer_hdf5_or_model_independence() -> None:
    config = validate_config(_in2o3_config())
    record = normalize_record(_record(_in2o3_config(), license_id=None))
    verification = verify_record(config, record)
    snapshot = build_snapshot(config, record, verification, config_sha256="c" * 64)

    assessment = snapshot["evidence_assessment"]
    assert assessment["hdf5_schema"] == "Inconclusive"
    assert assessment["trajectory_time_and_order_semantics"] == "Inconclusive"
    assert assessment["model_development_coupling"] == "Inconclusive"
    assert assessment["label_or_target_leakage_boundary"] == "Inconclusive"
    assert snapshot["source_file_downloaded"] is False
    assert snapshot["model_weights_downloaded"] is False
    assert snapshot["model_execution_performed"] is False


def test_file_checksum_drift_fails_closed() -> None:
    config = validate_config(_in2o3_config())
    payload = _record(_in2o3_config(), license_id=None)
    payload["files"][0]["checksum"] = "md5:" + "f" * 32  # type: ignore[index]
    record = normalize_record(payload)

    with pytest.raises(TemCandidateMetadataAuditError, match="checksum changed"):
        verify_record(config, record)


def test_untrusted_content_host_fails_closed() -> None:
    config = validate_config(_carbon_config())
    payload = _record(_carbon_config(), license_id=None)
    payload["files"][0]["links"]["content"] = "https://example.com/file.zip"  # type: ignore[index]
    record = normalize_record(payload)

    with pytest.raises(TemCandidateMetadataAuditError, match="trusted Zenodo host"):
        verify_record(config, record)


def test_repository_candidate_configs_parse_and_keep_downloads_disabled() -> None:
    paths = [
        Path("case_studies/zenodo_carbon_nitride_tem_metadata_audit/case_config.json"),
        Path("case_studies/zenodo_in2o3_insitu_tem_metadata_audit/case_config.json"),
    ]
    for path in paths:
        config = validate_config(json.loads(path.read_text(encoding="utf-8")))
        assert config["scientific_boundary"]["source_file_download_authorized"] is False
        assert config["scientific_boundary"]["pixel_array_access_authorized"] is False
        assert config["scientific_boundary"]["model_execution_authorized"] is False
