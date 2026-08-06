from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_mendeley_lunar_tem_saed as audit


def _source() -> dict:
    return {
        "dataset_id": "fcwyz3kv3k",
        "version": 1,
        "doi": "10.17632/fcwyz3kv3k.1",
        "landing_url": "https://data.mendeley.com/datasets/fcwyz3kv3k/1",
        "expected_title_substring": "Chang’E-5 samples reveal high water content",
        "expected_description_terms": [
            "TEM",
            "bright-field",
            "High-resolution",
            "selected area electron diffraction",
        ],
        "expected_license_terms": ["CC BY 4.0"],
        "material_scope": "lunar minerals",
        "source_quality_flags": [],
    }


def _config() -> dict:
    return {
        "case_id": "x",
        "audit_date": "2026-08-06",
        "sources": [_source()],
        "limits": {
            "maximum_file_records_per_dataset": 100,
            "maximum_folder_records_per_dataset": 100,
            "maximum_header_samples_per_dataset": 4,
            "maximum_header_bytes_per_file": 1024,
            "maximum_total_header_bytes_per_dataset": 4096,
        },
        "scientific_boundary": {
            "public_metadata_fetch_authorized": True,
            "public_file_inventory_authorized": True,
            "bounded_file_header_probe_authorized": True,
            "source_file_retention_authorized": False,
            "source_files_may_be_uploaded_as_artifacts": False,
            "pixel_array_export_authorized": False,
            "image_preprocessing_authorized": False,
            "model_inference_authorized": False,
            "annotation_authorized": False,
            "parameter_tuning_authorized": False,
            "model_retraining_authorized": False,
            "phase_indexing_claim_authorized": False,
            "external_validation_claim_authorized": False,
            "engineering_decision_claim_authorized": False,
        },
    }


def test_config_preserves_fail_closed_boundary(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    payload = _config()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert audit.load_config(path)["sources"][0]["dataset_id"] == "fcwyz3kv3k"
    payload["scientific_boundary"]["model_inference_authorized"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(audit.MendeleyAuditError, match="fail-closed"):
        audit.load_config(path)


def test_folder_paths_follow_parent_chain() -> None:
    folders = [
        {"id": "root", "name": "TEM", "parent_id": ""},
        {"id": "child", "name": "SAED", "parent_id": "root"},
    ]
    assert audit.build_folder_paths(folders) == {
        "root": "TEM",
        "child": "TEM/SAED",
    }


def test_folder_cycle_fails_closed() -> None:
    with pytest.raises(audit.MendeleyAuditError, match="cycle"):
        audit.build_folder_paths(
            [
                {"id": "a", "name": "A", "parent_id": "b"},
                {"id": "b", "name": "B", "parent_id": "a"},
            ]
        )


@pytest.mark.parametrize(
    ("filename", "content_type", "expected"),
    [
        ("pattern.dm4", "application/octet-stream", "native_microscopy_container"),
        ("image.tif", "image/tiff", "raster_image"),
        ("figure.jpg", "image/jpeg", "rendered_or_lossy_raster"),
        ("metadata.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "table_or_document"),
    ],
)
def test_representation_classification(
    filename: str, content_type: str, expected: str
) -> None:
    assert audit.representation_from_name(filename, content_type) == expected


def test_header_magic_is_version_aware() -> None:
    dm3 = b"\x00\x00\x00\x03" + b"x" * 4 + b"\x00\x00\x00\x01" + b"z" * 32
    dm4 = (
        b"\x00\x00\x00\x04"
        + (12345).to_bytes(8, "big")
        + b"\x00\x00\x00\x01"
        + b"z" * 32
    )
    dm3_result = audit.classify_header("pattern.dm3", dm3)
    dm4_result = audit.classify_header("pattern.dm4", dm4)
    assert dm3_result["magic_class"] == "digital_micrograph_dm3"
    assert dm3_result["digital_micrograph_byte_order_marker"] == 1
    assert dm4_result["magic_class"] == "digital_micrograph_dm4"
    assert dm4_result["digital_micrograph_declared_payload_bytes_big_endian"] == 12345
    assert dm4_result["digital_micrograph_byte_order_marker"] == 1
    assert audit.classify_header("image.tif", b"II*\x00fixture")["magic_class"] == "tiff"
    assert audit.classify_header("image.bmp", b"BMfixture")["magic_class"] == "bmp"


def test_normalized_files_preserve_ids_hashes_paths_and_roles() -> None:
    records = [
        {
            "id": "file-1",
            "filename": "area_diffraction.dm4",
            "folder_id": "folder-1",
            "content_details": {
                "size": 100,
                "sha256_hash": "a" * 64,
                "content_type": "application/octet-stream",
                "download_url": "https://api.data.mendeley.com/file-download",
            },
        }
    ]
    rows = audit.normalize_files(records, {"folder-1": "TEM/SAED"})
    assert len(rows) == 1
    row = rows[0]
    assert row["file_id"] == "file-1"
    assert row["path"] == "TEM/SAED/area_diffraction.dm4"
    assert row["bytes"] == 100
    assert row["sha256"] == "a" * 64
    assert row["representation_class"] == "native_microscopy_container"
    assert {"tem_cue", "saed_cue"} <= set(row["role_cues"])


def test_header_selection_prioritizes_saed_then_native() -> None:
    rows = [
        {
            "path": "TEM/image.tif",
            "filename": "image.tif",
            "bytes": 10,
            "representation_class": "raster_image",
            "role_cues": ["tem_cue"],
        },
        {
            "path": "TEM/SAED/pattern.tif",
            "filename": "pattern.tif",
            "bytes": 20,
            "representation_class": "raster_image",
            "role_cues": ["tem_cue", "saed_cue"],
        },
        {
            "path": "TEM/image.dm4",
            "filename": "image.dm4",
            "bytes": 30,
            "representation_class": "native_microscopy_container",
            "role_cues": ["tem_cue"],
        },
    ]
    selected = audit.select_header_candidates(
        rows, {"maximum_header_samples_per_dataset": 2}
    )
    assert [row["path"] for row in selected] == [
        "TEM/SAED/pattern.tif",
        "TEM/image.dm4",
    ]


def test_external_api_and_download_hosts_fail_closed() -> None:
    with pytest.raises(audit.MendeleyAuditError, match="untrusted Mendeley API"):
        audit._trusted_api_url("https://example.org/datasets/x")
    with pytest.raises(audit.MendeleyAuditError, match="untrusted Mendeley download"):
        audit._trusted_download_url("https://example.org/file")
