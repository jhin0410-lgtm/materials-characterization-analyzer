from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_wtacrv_tem_saed as audit


def _config() -> dict:
    return {
        "case_id": "x",
        "audit_date": "2026-08-06",
        "source": {
            "repository": "Zenodo",
            "record_id": 10512463,
            "doi": "10.5281/zenodo.10512463",
            "record_url": "https://zenodo.org/records/10512463",
            "api_url": "https://zenodo.org/api/records/10512463",
            "expected_status": "published",
            "expected_resource_type": "dataset",
            "expected_title_substring": "low-activation W-Ta-Cr-V refractory high entropy alloy",
            "allowed_license_ids": ["odbl-1.0"],
            "target_file": {
                "key": "D_Kalita_NME.zip",
                "md5": "2d3db56126bb936844c9d817b0a01f4c",
            },
            "required_description_terms": [
                "raw TEM images",
                "selected area diffraction",
                "EDS elemental maps",
                "as-deposited",
                "He-irradiated",
            ],
            "source_quality_flags": [],
        },
        "limits": {
            "minimum_archive_bytes": 10,
            "maximum_archive_bytes": 1000,
            "maximum_member_count": 100,
            "maximum_total_uncompressed_bytes": 10000,
            "maximum_single_member_bytes": 5000,
            "maximum_member_compression_ratio": 100,
            "maximum_selected_member_count": 5,
            "maximum_selected_uncompressed_bytes": 1000,
        },
        "scientific_boundary": {
            "source_archive_download_authorized": True,
            "archive_member_inventory_authorized": True,
            "bounded_selected_member_header_inspection_authorized": True,
            "source_archive_retention_authorized": False,
            "source_files_may_be_uploaded_as_artifacts": False,
            "archive_members_may_be_uploaded_as_artifacts": False,
            "pixel_array_export_authorized": False,
            "image_preprocessing_authorized": False,
            "model_inference_authorized": False,
            "annotation_authorized": False,
            "parameter_tuning_authorized": False,
            "model_retraining_authorized": False,
            "external_validation_claim_authorized": False,
            "phase_indexing_claim_authorized": False,
            "engineering_decision_claim_authorized": False,
        },
    }


def _record(*, license_id: str = "odbl-1.0") -> dict:
    return {
        "id": 10512463,
        "doi": "10.5281/zenodo.10512463",
        "status": "published",
        "metadata": {
            "title": "The microstructure and He+ ion irradiation behavior of novel low-activation W-Ta-Cr-V refractory high entropy alloy for nuclear applications",
            "resource_type": {"id": "dataset"},
            "license": {"id": license_id},
            "description": (
                "TEM folder contains raw TEM images in as-deposited and He-irradiated "
                "conditions, selected area diffraction patterns and EDS elemental maps."
            ),
        },
        "files": [
            {
                "id": "f1",
                "key": "D_Kalita_NME.zip",
                "size": 100,
                "checksum": "md5:2d3db56126bb936844c9d817b0a01f4c",
                "links": {"content": "https://zenodo.org/api/records/10512463/files/D_Kalita_NME.zip/content"},
            }
        ],
    }


def test_config_preserves_fail_closed_boundary(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    payload = _config()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert audit.load_config(path)["source"]["record_id"] == 10512463
    payload["scientific_boundary"]["model_inference_authorized"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(audit.WTaCrVAuditError, match="fail-closed"):
        audit.load_config(path)


def test_record_and_archive_contract_is_verified() -> None:
    record, target = audit.verify_record(_config(), _record())
    assert record["id"] == 10512463
    assert target["key"] == "D_Kalita_NME.zip"
    assert target["bytes"] == 100


def test_unexpected_license_fails_closed() -> None:
    with pytest.raises(audit.WTaCrVAuditError, match="licence mismatch"):
        audit.verify_record(_config(), _record(license_id="cc-by-4.0"))


def test_microscopy_cues_preserve_condition_and_modality() -> None:
    cues = set(
        audit.microscopy_cues(
            "D_Kalita_NME/TEM/He-irradiated/SAED/area_01_diffraction.tif"
        )
    )
    assert {"tem_folder", "saed_name_cue", "irradiated_condition_cue"} <= cues
    cues = set(audit.microscopy_cues("D_Kalita_NME/TEM/as-deposited/EDS/map.emsa"))
    assert {"tem_folder", "eds_name_cue", "as_deposited_condition_cue"} <= cues


def test_selection_prioritizes_saed_and_stays_bounded() -> None:
    rows = [
        {
            "member_path": "TEM/as-deposited/image.tif",
            "uncompressed_bytes": 200,
            "suffix": ".tif",
            "representation_class": "lossless_or_lossless_capable_raster_export",
            "wtacrv_role_cues": ["tem_folder", "as_deposited_condition_cue"],
        },
        {
            "member_path": "TEM/He-irradiated/SAED/diff.tif",
            "uncompressed_bytes": 300,
            "suffix": ".tif",
            "representation_class": "lossless_or_lossless_capable_raster_export",
            "wtacrv_role_cues": ["tem_folder", "saed_name_cue", "irradiated_condition_cue"],
        },
        {
            "member_path": "SEM/image.tif",
            "uncompressed_bytes": 10,
            "suffix": ".tif",
            "representation_class": "lossless_or_lossless_capable_raster_export",
            "wtacrv_role_cues": ["sem_folder"],
        },
    ]
    limits = {"maximum_selected_member_count": 1, "maximum_selected_uncompressed_bytes": 1000}
    selected = audit.select_header_members(rows, limits)
    assert [row["member_path"] for row in selected] == ["TEM/He-irradiated/SAED/diff.tif"]


def test_selection_without_tem_member_fails() -> None:
    with pytest.raises(audit.WTaCrVAuditError, match="no bounded TEM-folder"):
        audit.select_header_members(
            [{
                "member_path": "SEM/image.tif",
                "uncompressed_bytes": 10,
                "suffix": ".tif",
                "representation_class": "lossless_or_lossless_capable_raster_export",
                "wtacrv_role_cues": ["sem_folder"],
            }],
            {"maximum_selected_member_count": 5, "maximum_selected_uncompressed_bytes": 1000},
        )
