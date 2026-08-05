from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_zenodo_ge_dm3_tem_saed import (
    ZenodoGeDm3AuditError,
    load_config,
    normalize_7z_inventory,
    normalize_record,
    parse_7z_slt,
    role_cues,
    select_dm3_members,
    verify_record,
    verify_required_members,
)


LIMITS = {
    "maximum_archive_bytes": 400_000_000,
    "maximum_member_count": 100,
    "maximum_total_uncompressed_bytes": 10_000_000,
    "maximum_single_member_bytes": 5_000_000,
    "maximum_member_compression_ratio": 500,
    "maximum_selected_member_count": 20,
    "maximum_selected_uncompressed_bytes": 10_000_000,
}


def _config() -> dict[str, object]:
    return {
        "case_id": "zenodo_ge_dm3_tem_saed_source_audit",
        "audit_date": "2026-08-05",
        "source": {
            "repository": "Zenodo",
            "record_id": 15082448,
            "doi": "10.5281/zenodo.15082448",
            "record_url": "https://zenodo.org/records/15082448",
            "api_url": "https://zenodo.org/api/records/15082448",
            "expected_status": "published",
            "expected_resource_type": "dataset",
            "expected_title": "Dataset for \"Highly strained Ge nanostructures and direct bandgap transition induced by femtosecond laser\"",
            "expected_license_id": "cc-by-4.0",
            "target_file": {
                "key": "10.5281zenodo.15082448.7z",
                "md5": "535f513e05d88a9b14a3bc6fde8ae3bd",
            },
            "required_member_basenames": [
                "d1 TEM 30k.dm3",
                "d1 diff.dm3",
            ],
            "source_quality_flags": ["record-level quality flag"],
        },
        "limits": LIMITS,
        "scientific_boundary": {
            "source_archive_download_authorized": True,
            "archive_member_inventory_authorized": True,
            "selected_dm3_metadata_inspection_authorized": True,
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


def _record() -> dict[str, object]:
    return {
        "id": 15082448,
        "doi": "10.5281/zenodo.15082448",
        "status": "published",
        "metadata": {
            "title": "Dataset for \"Highly strained Ge nanostructures and direct bandgap transition induced by femtosecond laser\"",
            "resource_type": {"id": "dataset"},
            "license": {"id": "cc-by-4.0"},
            "publication_date": "2025-03-25",
        },
        "files": [
            {
                "id": "file-id",
                "key": "10.5281zenodo.15082448.7z",
                "size": 270_500_000,
                "checksum": "md5:535f513e05d88a9b14a3bc6fde8ae3bd",
                "links": {
                    "content": "https://zenodo.org/api/records/15082448/files/archive/content"
                },
            }
        ],
    }


def _listing(*records: str) -> str:
    return "\n".join(
        [
            "7-Zip [64] 16.02",
            "Scanning the drive for archives:",
            "----------",
            *records,
        ]
    )


def _member(path: str, *, size: int = 1000, packed: int = 800, encrypted: str = "-") -> str:
    return "\n".join(
        [
            f"Path = {path}",
            f"Size = {size}",
            f"Packed Size = {packed}",
            "Modified = 2025-03-25 00:00:00",
            "Attributes = A",
            "CRC = ABCDEF12",
            f"Encrypted = {encrypted}",
            "Method = LZMA2:24",
            "Block = 0",
            "",
        ]
    )


def test_record_normalization_and_verification_preserve_cc_by_license() -> None:
    normalized = normalize_record(_record())
    assert normalized["license_id"] == "cc-by-4.0"
    assert normalized["resource_type_id"] == "dataset"
    target = verify_record(_config(), normalized)
    assert target["key"] == "10.5281zenodo.15082448.7z"
    assert target["bytes"] == 270_500_000


def test_record_verification_rejects_missing_license_or_checksum_drift() -> None:
    unlicensed = _record()
    del unlicensed["metadata"]["license"]  # type: ignore[index]
    with pytest.raises(ZenodoGeDm3AuditError, match="license_id"):
        verify_record(_config(), normalize_record(unlicensed))

    changed = _record()
    changed["files"][0]["checksum"] = "md5:00000000000000000000000000000000"  # type: ignore[index]
    with pytest.raises(ZenodoGeDm3AuditError, match="checksum changed"):
        verify_record(_config(), normalize_record(changed))


def test_parse_and_normalize_7z_inventory_identifies_native_pairs() -> None:
    text = _listing(
        _member("Figure 3/Lo/d1 TEM 30k.dm3"),
        _member("Figure 3/Lo/d1 diff.dm3"),
        _member("Figure 3/Hi/w1.dm3"),
        _member("Figure 2/EDS/b2 eds1.emsa"),
    )
    rows = normalize_7z_inventory(parse_7z_slt(text), LIMITS)
    assert len(rows) == 4
    by_path = {row["member_path"]: row for row in rows}
    assert by_path["Figure 3/Lo/d1 TEM 30k.dm3"]["representation_class"] == (
        "native_microscopy_container"
    )
    assert "tem_name_cue" in by_path["Figure 3/Lo/d1 TEM 30k.dm3"]["role_cues"]
    assert "static_saed_name_cue" in by_path["Figure 3/Lo/d1 diff.dm3"]["role_cues"]
    assert "hrtem_name_cue" in by_path["Figure 3/Hi/w1.dm3"]["role_cues"]
    assert "eds_name_cue" in by_path["Figure 2/EDS/b2 eds1.emsa"]["role_cues"]

    resolved = verify_required_members(rows, ["d1 TEM 30k.dm3", "d1 diff.dm3"])
    assert resolved == {
        "d1 TEM 30k.dm3": "Figure 3/Lo/d1 TEM 30k.dm3",
        "d1 diff.dm3": "Figure 3/Lo/d1 diff.dm3",
    }
    selected = select_dm3_members(rows, LIMITS)
    assert {row["member_path"] for row in selected} == {
        "Figure 3/Lo/d1 TEM 30k.dm3",
        "Figure 3/Lo/d1 diff.dm3",
        "Figure 3/Hi/w1.dm3",
    }


def test_7z_inventory_rejects_unsafe_duplicate_and_encrypted_members() -> None:
    with pytest.raises(ZenodoGeDm3AuditError, match="unsafe archive member path"):
        normalize_7z_inventory(
            parse_7z_slt(_listing(_member("../escape.dm3"))), LIMITS
        )

    duplicate = _listing(
        _member("Figure 3/Lo/d1 diff.dm3"),
        _member("figure 3/lo/D1 DIFF.DM3"),
    )
    with pytest.raises(ZenodoGeDm3AuditError, match="duplicate normalized"):
        normalize_7z_inventory(parse_7z_slt(duplicate), LIMITS)

    with pytest.raises(ZenodoGeDm3AuditError, match="encrypted archive member"):
        normalize_7z_inventory(
            parse_7z_slt(_listing(_member("secret.dm3", encrypted="+"))), LIMITS
        )


def test_required_member_must_resolve_exactly_once() -> None:
    rows = normalize_7z_inventory(
        parse_7z_slt(_listing(_member("Figure 3/Lo/d1 diff.dm3"))), LIMITS
    )
    with pytest.raises(ZenodoGeDm3AuditError, match="resolve exactly once"):
        verify_required_members(rows, ["missing.dm3"])


def test_diffraction_cues_are_filename_diagnostics_not_mode_authority() -> None:
    assert "static_saed_name_cue" not in role_cues("3D_ED/rotation_series_001.dm3")
    assert "static_saed_name_cue" in role_cues("4DSTEM/diffraction_frame.dm3")
    assert "static_saed_name_cue" in role_cues("Figure 3/Lo/w0 diff.dm3")
    # The record-level acquisition-mode contract, not this cue, determines whether a
    # member may be treated as static SAED.


def test_repository_config_is_pinned_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(
        root / "case_studies/zenodo_ge_dm3_tem_saed_source_audit/case_config.json"
    )
    assert config["source"]["record_id"] == 15082448
    assert config["source"]["expected_license_id"] == "cc-by-4.0"
    assert config["source"]["target_file"]["md5"] == (
        "535f513e05d88a9b14a3bc6fde8ae3bd"
    )
    assert len(config["source"]["required_member_basenames"]) == 8
    boundary = config["scientific_boundary"]
    assert boundary["source_archive_download_authorized"] is True
    assert boundary["source_archive_retention_authorized"] is False
    assert boundary["pixel_array_export_authorized"] is False
    assert boundary["model_inference_authorized"] is False
    assert boundary["parameter_tuning_authorized"] is False
    assert boundary["model_retraining_authorized"] is False
    assert boundary["phase_indexing_claim_authorized"] is False
