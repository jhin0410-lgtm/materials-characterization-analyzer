from __future__ import annotations

import importlib.util
import json
import stat
import zipfile
from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_repod_cofeni_tem_saed.py"
CONFIG = (
    ROOT
    / "case_studies"
    / "repod_cofeni_tem_saed_source_audit"
    / "case_config.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("repod_cofeni_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_config_is_pinned_and_fail_closed() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert payload["source"]["persistent_id"] == "doi:10.18150/SIOWH6"
    assert payload["source"]["version_number"] == 1
    assert payload["source"]["version_minor_number"] == 0
    assert payload["source"]["expected_record_file_count"] == 12
    targets = {row["name"]: row for row in payload["source"]["target_files"]}
    assert targets["TEM_SAED.zip"]["md5"] == "fbc9ab9944a398a0c4a3271e809f04ef"
    assert targets["HRTEM_SAED.zip"]["md5"] == "470b9996ea17f31b7fbe915e84d2d8d7"
    assert targets["HAADF_STEM.tif"]["md5"] == "4b8c137fd605995d9660223f4c971ff1"
    boundary = payload["scientific_boundary"]
    assert boundary["source_files_may_be_uploaded_as_artifacts"] is False
    assert boundary["model_inference_authorized"] is False
    assert boundary["annotation_authorized"] is False
    assert boundary["parameter_tuning_authorized"] is False
    assert boundary["external_validation_claim_authorized"] is False


def test_safe_zip_inventory_preserves_representation_boundaries(tmp_path: Path) -> None:
    module = _load_module()
    image_path = tmp_path / "pattern.tif"
    Image.new("L", (8, 6), color=17).save(image_path, format="TIFF")
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(image_path, "sample_01/SAED_pattern.tif")
        archive.writestr("sample_01/readme.txt", "metadata incomplete")

    rows = module.inspect_zip(archive_path, "source.zip")
    by_name = {row["member_path"]: row for row in rows}
    pattern = by_name["sample_01/SAED_pattern.tif"]
    assert pattern["representation_class"] == "lossless_or_lossless-capable_raster_export"
    assert "saed_or_diffraction_name_cue" in pattern["role_cues"]
    assert pattern["image_decodable"] is True
    assert pattern["image_format"] == "TIFF"
    assert pattern["width"] == 8
    assert pattern["height"] == 6


def test_zip_rejects_parent_traversal(tmp_path: Path) -> None:
    module = _load_module()
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.tif", b"not-an-image")
    with pytest.raises(module.RepodCoFeNiAuditError, match="unsafe archive member"):
        module.inspect_zip(archive_path, "unsafe.zip")


def test_zip_rejects_symlink(tmp_path: Path) -> None:
    module = _load_module()
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link.tif")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target.tif")
    with pytest.raises(module.RepodCoFeNiAuditError, match="symlink archive member"):
        module.inspect_zip(archive_path, "symlink.zip")


def test_summary_never_promotes_public_archives() -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    inventory = [{"name": f"file-{index}"} for index in range(12)]
    downloaded = [
        {"name": "TEM_SAED.zip"},
        {"name": "HRTEM_SAED.zip"},
        {"name": "HAADF_STEM.tif"},
    ]
    members = [
        {
            "member_path": "TEM_01.tif",
            "role_cues": ["tem_name_cue"],
            "representation_class": "lossless_or_lossless-capable_raster_export",
        },
        {
            "member_path": "SAED_01.tif",
            "role_cues": ["saed_or_diffraction_name_cue"],
            "representation_class": "lossless_or_lossless-capable_raster_export",
        },
    ]
    summary = module.build_summary(config, inventory, downloaded, members)
    assert summary["source_audit_closeout"]["status"] == "Supported"
    assert summary["analyzer_scientific_evidence_level"] == "Inconclusive"
    assert summary["external_validation_ready"] is False
    assert summary["engineering_decision_ready"] is False
    assert summary["model_inference_performed"] is False
    assert summary["primary_parameters_changed"] is False


def test_run_removes_transient_before_evidence_scan(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    targets = config["source"]["target_files"]

    files = []
    for index in range(12):
        name = f"other-{index}.txt"
        content_type = "text/plain"
        md5 = f"{index:032x}"
        if index < len(targets):
            target = targets[index]
            name = target["name"]
            content_type = target["content_type"]
            md5 = target["md5"]
        files.append(
            {
                "restricted": False,
                "licenseName": config["source"]["file_license_name"],
                "dataFile": {
                    "id": index + 1,
                    "filename": name,
                    "filesize": 1,
                    "contentType": content_type,
                    "checksum": {"type": "MD5", "value": md5},
                },
            }
        )
    payload = {
        "status": "OK",
        "data": {
            "latestVersion": {
                "versionNumber": 1,
                "versionMinorNumber": 0,
                "versionState": "RELEASED",
                "files": files,
            }
        },
    }
    monkeypatch.setattr(module, "_fetch_json", lambda _url: payload)

    def fake_download(url, destination, *, expected_bytes, expected_md5):
        del url, expected_bytes
        if destination.suffix == ".zip":
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("sample/SAED_pattern.txt", "diagnostic")
        else:
            Image.new("L", (4, 4), color=1).save(destination, format="TIFF")
        return {
            "bytes": destination.stat().st_size,
            "md5": expected_md5,
            "sha256": "0" * 64,
        }

    monkeypatch.setattr(module, "_stream_download", fake_download)
    output = tmp_path / "evidence"
    summary = module.run(CONFIG, output)
    assert summary["external_validation_ready"] is False
    assert not (output / "_transient").exists()
    assert (output / "repod_cofeni_tem_saed_source_audit_summary.json").is_file()
    leaked = [
        path
        for path in output.rglob("*")
        if path.is_file() and path.suffix.casefold() in module.FORBIDDEN_SOURCE_SUFFIXES
    ]
    assert leaked == []
