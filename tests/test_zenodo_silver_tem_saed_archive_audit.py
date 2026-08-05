from __future__ import annotations

import importlib.util
import json
import stat
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_zenodo_silver_tem_saed_archive.py"
CONFIG = (
    ROOT
    / "case_studies"
    / "zenodo_silver_tem_saed_archive_audit"
    / "case_config.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("zenodo_archive_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_payload() -> dict:
    return {
        "id": 18942976,
        "doi": "10.5281/zenodo.18942976",
        "status": "published",
        "metadata": {
            "publication_date": "2027-05-10",
            "resource_type": {"id": "image"},
            "license": {"id": "cc-by-4.0"},
        },
        "files": [
            {
                "id": "target",
                "key": "TEM_SAED.zip",
                "size": 1417789651,
                "checksum": "md5:c7bda9d495dd0fd657a8fe0332db4f9c",
                "links": {
                    "content": "https://zenodo.org/api/records/18942976/files/TEM_SAED.zip/content"
                },
            }
        ],
    }


def _write_safe_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample_01/TEM_01.tif", b"tem-bytes")
        archive.writestr("sample_01/SAED_01.tif", b"saed-bytes")
        archive.writestr("sample_01/metadata.txt", b"metadata incomplete")


def test_config_is_bounded_and_fail_closed() -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    target = config["source"]["target_file"]
    assert target["exact_bytes"] == 1417789651
    assert target["md5"] == "c7bda9d495dd0fd657a8fe0332db4f9c"
    limits = config["limits"]
    assert limits["maximum_archive_bytes"] == 1600000000
    assert limits["maximum_total_uncompressed_bytes"] == 20000000000
    boundary = config["scientific_boundary"]
    assert boundary["source_archive_download_authorized"] is True
    assert boundary["source_archive_retention_authorized"] is False
    assert boundary["source_files_may_be_uploaded_as_artifacts"] is False
    assert boundary["model_inference_authorized"] is False
    assert boundary["parameter_tuning_authorized"] is False
    assert boundary["external_validation_claim_authorized"] is False


def test_safe_archive_inventory_hashes_all_members(tmp_path: Path) -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    archive_path = tmp_path / "source.zip"
    _write_safe_archive(archive_path)

    result = module.inspect_archive(archive_path, config["limits"])
    assert result["member_count"] == 3
    assert result["member_hashing_complete"] is True
    assert result["crc_verification_complete"] is True
    by_path = {row["member_path"]: row for row in result["members"]}
    assert by_path["sample_01/TEM_01.tif"]["representation_class"] == (
        "lossless_or_lossless-capable_raster_export"
    )
    assert "tem_name_cue" in by_path["sample_01/TEM_01.tif"]["role_cues"]
    assert "saed_or_diffraction_name_cue" in by_path[
        "sample_01/SAED_01.tif"
    ]["role_cues"]
    assert all(len(row["sha256"]) == 64 for row in result["members"])


def test_archive_rejects_parent_traversal(tmp_path: Path) -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.tif", b"bad")
    with pytest.raises(module.ZenodoArchiveAuditError, match="unsafe archive member"):
        module.inspect_archive(archive_path, config["limits"])


def test_archive_rejects_symlink(tmp_path: Path) -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link.tif")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target.tif")
    with pytest.raises(module.ZenodoArchiveAuditError, match="symlink archive member"):
        module.inspect_archive(archive_path, config["limits"])


def test_summary_never_promotes_archive_integrity_to_scientific_validation(
    tmp_path: Path,
) -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    archive_path = tmp_path / "source.zip"
    _write_safe_archive(archive_path)
    inventory = module.inspect_archive(archive_path, config["limits"])
    record = module.normalize_record(_record_payload())
    summary = module.build_summary(
        config,
        record,
        {"bytes": 1417789651, "md5": config["source"]["target_file"]["md5"], "sha256": "0" * 64},
        inventory,
    )
    assert summary["source_audit_closeout"]["status"] == "Supported"
    assert summary["analyzer_scientific_evidence_level"] == "Inconclusive"
    assert summary["intake_decision"] == "accepted_for_bounded_diagnostic_only"
    assert summary["external_validation_ready"] is False
    assert summary["engineering_decision_ready"] is False
    assert summary["model_inference_performed"] is False
    assert summary["primary_parameters_changed"] is False


def test_run_removes_source_and_writes_metadata_only_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "fetch_json", lambda _url: _record_payload())

    def fake_download(url, destination, *, expected_bytes, expected_md5):
        del url
        _write_safe_archive(destination)
        return {
            "bytes": expected_bytes,
            "md5": expected_md5,
            "sha256": "1" * 64,
        }

    monkeypatch.setattr(module, "stream_download", fake_download)
    output = tmp_path / "evidence"
    summary = module.run(CONFIG, output)
    assert summary["archive"]["member_count"] == 3
    assert summary["source_archive_retained"] is False
    assert not (output / "_transient").exists()
    assert (output / "archive_member_inventory.json").is_file()
    assert not any(path.suffix == ".zip" for path in output.rglob("*"))

    stored = json.loads(
        (output / "zenodo_silver_tem_saed_archive_audit_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["external_validation_ready"] is False
    assert stored["model_inference_performed"] is False
