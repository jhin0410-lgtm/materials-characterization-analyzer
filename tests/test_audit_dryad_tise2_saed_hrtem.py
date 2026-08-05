from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts import audit_dryad_tise2_saed_hrtem as audit


def test_config_loads_and_preserves_fail_closed_boundary(tmp_path: Path) -> None:
    payload = {
        "case_id": "x",
        "audit_date": "2026-08-06",
        "source": {
            "repository": "Dryad",
            "doi": "10.5061/dryad.6djh9w1hw",
            "record_url": "https://datadryad.org/x",
            "primary_file_id": 4808550,
            "primary_filename": "Data_TiSe2.zip",
            "readme_file_id": 4808551,
            "readme_filename": "README.md",
            "expected_license": "CC0-1.0",
            "expected_title": "Revisiting",
            "source_quality_flags": [],
        },
        "limits": {
            "minimum_archive_bytes": 1,
            "maximum_archive_bytes": 2,
            "maximum_member_count": 3,
            "maximum_total_uncompressed_bytes": 4,
            "maximum_single_member_bytes": 5,
            "maximum_compression_ratio": 6,
            "maximum_text_member_bytes": 7,
            "maximum_tiff_samples": 8,
            "maximum_tiff_sample_bytes": 9,
        },
        "scientific_boundary": {
            "source_archive_download_authorized": True,
            "archive_member_inventory_authorized": True,
            "bounded_text_read_authorized": True,
            "bounded_tiff_header_inspection_authorized": True,
            "source_archive_retention_authorized": False,
            "source_files_may_be_uploaded_as_artifacts": False,
            "archive_members_may_be_uploaded_as_artifacts": False,
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
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert audit.load_config(path)["source"]["primary_file_id"] == 4808550
    payload["scientific_boundary"]["model_inference_authorized"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(audit.AuditError, match="fail-closed"):
        audit.load_config(path)


@pytest.mark.parametrize("name", ["../escape.tif", "/absolute.tif", "C:/drive.tif", "x\\y.tif"])
def test_unsafe_zip_member_paths_fail(name: str) -> None:
    with pytest.raises(audit.AuditError):
        audit.safe_member_path(name)


def test_explicit_figure_roles_are_not_inferred_from_pixels() -> None:
    assert audit.fixed_folder_role("Fig2_Data")[0] == "experimental"
    assert audit.fixed_folder_role("Fig3_Data")[0] == "simulated"
    assert audit.fixed_folder_role("Fig4_Data")[0] == "simulated"
    assert audit.fixed_folder_role("S1_Data") is None


def test_text_classification_keeps_mixed_evidence_mixed() -> None:
    role, hits = audit.classify_text(
        "Experimental electron diffraction pattern compared with a simulated DFT result."
    )
    assert role == "mixed"
    assert "experimental" in hits
    assert "simulated" in hits
    assert "dft" in hits


def test_upstream_digest_is_checked_when_present() -> None:
    observed = {
        "md5": hashlib.md5(b"abc").hexdigest(),
        "sha256": hashlib.sha256(b"abc").hexdigest(),
    }
    status = audit.verify_upstream_digest(observed, {"md5": observed["md5"]})
    assert status["checked_algorithms"] == ["md5"]
    with pytest.raises(audit.AuditError, match="md5 mismatch"):
        audit.verify_upstream_digest(observed, {"md5": "0" * 32})


def test_small_zip_inventory_separates_explicit_roles(tmp_path: Path) -> None:
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Fig2_Data/ReadMe.txt", "Experimental electron diffraction pattern")
        zf.writestr("Fig2_Data/pattern_data.tif", b"not-a-real-tiff")
        zf.writestr("Fig3_Data/ReadMe.txt", "Simulated diffraction pattern")
        zf.writestr("Fig3_Data/sim_data.bmp", b"BM")
        zf.writestr("S1_Data/ReadMe.txt", "Experimental pattern and simulated comparison")
    config = {
        "limits": {
            "maximum_member_count": 100,
            "maximum_total_uncompressed_bytes": 1000000,
            "maximum_single_member_bytes": 100000,
            "maximum_compression_ratio": 100,
            "maximum_text_member_bytes": 10000,
            "maximum_tiff_samples": 3,
            "maximum_tiff_sample_bytes": 100000,
        }
    }
    result = audit.audit_zip(archive, config, tmp_path / "work")
    roles = {row["folder"]: row["role"] for row in result["folder_roles"]}
    assert roles["Fig2_Data"] == "experimental"
    assert roles["Fig3_Data"] == "simulated"
    assert roles["S1_Data"] == "mixed_or_ambiguous"
    assert result["representation_counts"]["native_microscopy_container"] == 0
