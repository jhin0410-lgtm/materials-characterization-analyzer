from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_saed_remote_inventory as audit


def test_repository_config_is_bounded_to_saed_zip_only() -> None:
    path = Path("case_studies/zenodo_srtio3_saed_remote_inventory/case_config.json")
    config = audit._validate_config(json.loads(path.read_text(encoding="utf-8")))
    assert config["target_archive"]["key"] == "SAED.zip"
    assert config["target_archive"]["expected_bytes"] == 25850906
    assert config["scientific_boundary"]["central_directory_inventory_authorized"] is True
    assert config["scientific_boundary"]["full_archive_download_authorized"] is False
    assert config["scientific_boundary"]["archive_member_payload_download_authorized"] is False
    assert config["scientific_boundary"]["four_d_stem_download_authorized"] is False


def test_resolve_target_requires_pinned_license_and_exact_archive() -> None:
    config = audit._validate_config(
        json.loads(
            Path("case_studies/zenodo_srtio3_saed_remote_inventory/case_config.json").read_text(
                encoding="utf-8"
            )
        )
    )
    snapshot = json.loads(
        Path("case_studies/zenodo_srtio3_saed_metadata_audit/verified_metadata_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    target = audit._resolve_target(config, snapshot)
    assert target["key"] == "SAED.zip"
    assert target["bytes"] == 25850906
    assert target["md5"] == "0c830a9b276a491e91037872891cb440"

    changed = json.loads(json.dumps(snapshot))
    changed["source"]["license_id"] = None
    with pytest.raises(audit.SrTiO3SaedRemoteInventoryError, match="reuse terms"):
        audit._resolve_target(config, changed)


def test_summary_preserves_representation_as_filename_diagnostic_only() -> None:
    records = [
        {
            "member_path": "SAED/35K/pattern_01.tif",
            "is_directory": False,
            "unsafe_path": False,
        },
        {
            "member_path": "SAED/69K/pattern_02.npy",
            "is_directory": False,
            "unsafe_path": False,
        },
        {
            "member_path": "SAED/README.txt",
            "is_directory": False,
            "unsafe_path": False,
        },
        {
            "member_path": "SAED/",
            "is_directory": True,
            "unsafe_path": False,
        },
    ]
    summary = audit._summarize(records, "a" * 64)
    assert summary["file_member_count"] == 3
    assert summary["extension_counts"] == {".npy": 1, ".tif": 1, ".txt": 1}
    assert summary["unsafe_path_count"] == 0


def test_config_rejects_any_four_d_stem_authorization(tmp_path: Path) -> None:
    payload = json.loads(
        Path("case_studies/zenodo_srtio3_saed_remote_inventory/case_config.json").read_text(
            encoding="utf-8"
        )
    )
    payload["scientific_boundary"]["four_d_stem_download_authorized"] = True
    with pytest.raises(audit.SrTiO3SaedRemoteInventoryError, match="stronger archive/analyzer"):
        audit._validate_config(payload)
