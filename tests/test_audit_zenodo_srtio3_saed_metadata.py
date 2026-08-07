from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_saed_metadata as audit


def _config(tmp_path: Path) -> Path:
    source = Path("case_studies/zenodo_srtio3_saed_metadata_audit/case_config.json")
    path = tmp_path / "config.json"
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def _record(*, license_id: str | None = "cc-by-4.0") -> dict:
    rights = [{"id": license_id}] if license_id else []
    files = {
        "4D_35K.npy": ("734883ae9e44af98226ac786efc31c94", 2_600_000_000),
        "4D_69K.npy": ("243111090578c7aa808ad4107713bb05", 2_600_000_000),
        "Kikuchi_COM.ipynb": ("56383d23c198347220ed751ddb3dbae5", 1_700_000),
        "SAED.zip": ("0c830a9b276a491e91037872891cb440", 25_900_000),
    }
    entries = {}
    for index, (key, (md5, size)) in enumerate(files.items()):
        entries[key] = {
            "id": f"id-{index}",
            "key": key,
            "size": size,
            "checksum": f"md5:{md5}",
            "links": {
                "content": f"https://zenodo.org/api/records/20300700/files/{key}/content"
            },
        }
    return {
        "id": 20300700,
        "status": "published",
        "created": "2026-06-11T00:00:00+00:00",
        "updated": "2026-06-11T00:00:00+00:00",
        "metadata": {
            "title": 'Datasets for "Nanoscale Polar Landscapes in Quantum Paraelectric SrTiO3"',
            "resource_type": {"id": "dataset"},
            "publication_date": "2026-05-20",
            "description": "4D-STEM datasets, SAED and analysis code for SrTiO3.",
            "rights": rights,
        },
        "files": {"entries": entries},
    }


def test_validate_record_supports_expected_inventory(tmp_path: Path) -> None:
    config = audit._validate_config(audit._load_json(_config(tmp_path)))
    verified = audit._validate_record(config, _record())
    assert verified["license_id"] == "cc-by-4.0"
    assert len(verified["inventory"]) == 4
    saed = next(item for item in verified["inventory"] if item["key"] == "SAED.zip")
    assert saed["md5"] == "0c830a9b276a491e91037872891cb440"


def test_missing_dataset_license_remains_explicit(tmp_path: Path, monkeypatch) -> None:
    config_path = _config(tmp_path)
    monkeypatch.setattr(audit, "_fetch_record", lambda _url: _record(license_id=None))
    result = audit.run_audit(config_path=config_path, output_path=tmp_path / "out.json")
    assert result["evidence_assessment"]["dataset_reuse_terms"] == "Inconclusive"
    assert result["readiness"]["reuse_status"] == "dataset_license_missing_reuse_blocked"
    assert result["readiness"]["saed_archive_inventory_authorized"] is False


def test_file_md5_drift_is_rejected(tmp_path: Path) -> None:
    config = audit._validate_config(audit._load_json(_config(tmp_path)))
    record = _record()
    record["files"]["entries"]["SAED.zip"]["checksum"] = "md5:" + "0" * 32
    with pytest.raises(audit.SrTiO3SaedMetadataAuditError, match="inventory/MD5 drifted"):
        audit._validate_record(config, record)


def test_metadata_stage_never_authorizes_pixels_or_inference(tmp_path: Path, monkeypatch) -> None:
    config_path = _config(tmp_path)
    monkeypatch.setattr(audit, "_fetch_record", lambda _url: _record())
    output = tmp_path / "snapshot.json"
    result = audit.run_audit(config_path=config_path, output_path=output)
    assert result["source_archive_downloaded"] is False
    assert result["source_bytes_retained"] is False
    assert result["analyzer_inference_performed"] is False
    assert result["readiness"]["four_d_stem_download_authorized"] is False
    assert result["readiness"]["pixel_array_access_authorized"] is False
    assert result["readiness"]["analyzer_execution_authorized"] is False
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["saed_archive"]["key"] == "SAED.zip"
