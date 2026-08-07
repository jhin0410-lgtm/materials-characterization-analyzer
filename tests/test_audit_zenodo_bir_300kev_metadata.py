from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_zenodo_bir_300kev_metadata import (
    Bir300MetadataAuditError,
    build_snapshot,
    normalize_record,
    validate_config,
    verify_record,
)


def _config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": "zenodo_bir_300kev_saed_metadata_audit",
        "audit_date": "2026-08-07",
        "source": {
            "repository": "Zenodo",
            "record_id": 10995139,
            "doi": "10.5281/zenodo.10995139",
            "record_url": "https://zenodo.org/records/10995139",
            "api_url": "https://zenodo.org/api/records/10995139",
            "expected_status": "published",
            "expected_resource_type": "dataset",
            "expected_title": "BIR 300",
            "expected_version": "v1",
            "expected_files": [
                {"key": f"file_{index}.zip", "md5": f"{index:032x}"}
                for index in range(1, 7)
            ],
            "expected_description_terms": [
                ".tvips",
                "electron diffraction",
                "static_diffraction",
            ],
        },
        "scientific_boundary": {
            "metadata_api_request_authorized": True,
            "source_archive_download_authorized": False,
            "source_file_retention_authorized": False,
            "archive_inventory_authorized": False,
            "pixel_array_access_authorized": False,
            "analyzer_inference_authorized": False,
            "parameter_tuning_authorized": False,
            "model_retraining_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_claim_authorized": False,
            "engineering_decision_claim_authorized": False,
        },
        "decision_rules": {
            "missing_dataset_license_is_blocking_for_reuse": True,
            "article_license_cannot_substitute_for_dataset_license": True,
            "archive_identity_does_not_establish_tvips_member_identity": True,
            "filename_conditions_do_not_establish_acquisition_lineage": True,
            "static_diffraction_wording_does_not_establish_pattern_center_or_reciprocal_calibration": True,
            "cross_material_data_cannot_establish_cobalt_oxide_in_domain_performance": True,
        },
    }


def _record(*, license_id: str | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "doi": "10.5281/zenodo.10995139",
        "title": "BIR 300",
        "version": "v1",
        "resource_type": {"id": "dataset"},
        "description": (
            "electron diffraction data in .tvips files named with "
            "Compound_static_diffraction conditions"
        ),
        "publication_date": "2024-04-18",
    }
    if license_id is not None:
        metadata["license"] = {"id": license_id}
    return {
        "id": 10995139,
        "doi": "10.5281/zenodo.10995139",
        "status": "published",
        "created": "2024-04-19T00:00:00+00:00",
        "updated": "2024-04-19T00:00:00+00:00",
        "metadata": metadata,
        "files": [
            {
                "id": str(index),
                "key": f"file_{index}.zip",
                "size": 1000 + index,
                "checksum": f"md5:{index:032x}",
                "links": {"content": f"https://zenodo.org/api/records/10995139/files/{index}/content"},
            }
            for index in range(1, 7)
        ],
    }


def test_metadata_only_contract_keeps_all_stronger_operations_disabled() -> None:
    config = validate_config(_config())
    boundary = config["scientific_boundary"]
    assert boundary["metadata_api_request_authorized"] is True
    assert all(
        boundary[key] is False
        for key in boundary
        if key != "metadata_api_request_authorized"
    )


def test_missing_dataset_license_blocks_reuse_without_using_article_license() -> None:
    config = validate_config(_config())
    record = normalize_record(_record())
    verification = verify_record(config, record)
    snapshot = build_snapshot(config, record, verification, config_sha256="a" * 64)

    assert snapshot["source"]["license_id"] is None
    assert snapshot["readiness"]["reuse_status"] == "dataset_license_missing_reuse_blocked"
    assert snapshot["readiness"]["archive_audit_authorized"] is False
    assert snapshot["evidence_assessment"]["dataset_reuse_terms"] == "Inconclusive"
    assert snapshot["source_archive_downloaded"] is False
    assert snapshot["analyzer_inference_performed"] is False


def test_declared_dataset_license_is_recorded_but_does_not_authorize_archive_audit() -> None:
    config = validate_config(_config())
    record = normalize_record(_record(license_id="cc-by-4.0"))
    verification = verify_record(config, record)
    snapshot = build_snapshot(config, record, verification, config_sha256="b" * 64)

    assert snapshot["source"]["license_id"] == "cc-by-4.0"
    assert snapshot["evidence_assessment"]["dataset_reuse_terms"] == "Supported"
    assert snapshot["readiness"]["archive_audit_authorized"] is False
    assert snapshot["readiness"]["external_validation_ready"] is False


def test_archive_inventory_or_md5_drift_fails_closed() -> None:
    config = validate_config(_config())
    payload = _record()
    payload["files"][0]["checksum"] = "md5:" + "f" * 32  # type: ignore[index]
    record = normalize_record(payload)

    with pytest.raises(Bir300MetadataAuditError, match="checksum changed"):
        verify_record(config, record)


def test_untrusted_content_host_fails_closed() -> None:
    config = validate_config(_config())
    payload = _record()
    payload["files"][0]["links"]["content"] = "https://example.com/file.zip"  # type: ignore[index]
    record = normalize_record(payload)

    with pytest.raises(Bir300MetadataAuditError, match="trusted Zenodo host"):
        verify_record(config, record)


def test_repository_config_parses_with_exact_six_file_contract() -> None:
    path = Path("case_studies/zenodo_bir_300kev_saed_metadata_audit/case_config.json")
    config = validate_config(json.loads(path.read_text(encoding="utf-8")))
    expected = config["source"]["expected_files"]
    assert len(expected) == 6
    assert {entry["key"] for entry in expected} == {
        "AVAAGA_300kV_100K.zip",
        "AVAAGA_300kV_293K.zip",
        "coPorphryin_300kV_100K.zip",
        "coPorphryin_300kV_293K.zip",
        "znHis_300kV_100K.zip",
        "znHis_300kV_293K.zip",
    }
