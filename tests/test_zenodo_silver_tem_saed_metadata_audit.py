from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_zenodo_silver_tem_saed_metadata.py"
CONFIG = (
    ROOT
    / "case_studies"
    / "zenodo_silver_tem_saed_metadata_audit"
    / "case_config.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("zenodo_silver_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(*, checksum: str = "md5:c7bda9d495dd0fd657a8fe0332db4f9c"):
    return {
        "id": 18942976,
        "doi": "10.5281/zenodo.18942976",
        "status": "published",
        "created": "2026-05-21T00:00:00Z",
        "updated": "2026-05-21T00:00:00Z",
        "metadata": {
            "title": "Raw data for silver nanoparticles",
            "publication_date": "2026-03-10",
            "resource_type": {"id": "image"},
            "license": {"id": "cc-by-4.0"},
        },
        "files": [
            {
                "id": "1",
                "key": "CMI_Halo_biofilm.xlsx",
                "size": 99500,
                "checksum": "md5:0d2a27047f7f26895bc41e6adef305e5",
                "links": {"content": "https://example.invalid/file/1"},
            },
            {
                "id": "2",
                "key": "TEM_SAED.zip",
                "size": 1400000000,
                "checksum": checksum,
                "links": {"content": "https://example.invalid/file/2"},
            },
            {
                "id": "3",
                "key": "UV_Vis.xlsx",
                "size": 39800,
                "checksum": "md5:a59916a765420147a7c63d68b4f5bad7",
                "links": {"content": "https://example.invalid/file/3"},
            },
        ],
    }


def test_config_is_metadata_only_and_fail_closed() -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    source = config["source"]
    assert source["record_id"] == 18942976
    assert source["doi"] == "10.5281/zenodo.18942976"
    assert source["expected_resource_type"] == "image"
    assert source["expected_license_id"] == "cc-by-4.0"
    assert source["target_file"]["checksum"] == (
        "md5:c7bda9d495dd0fd657a8fe0332db4f9c"
    )
    plan = config["bounded_plan"]
    assert plan["source_archive_download_authorized"] is False
    assert plan["source_files_may_be_uploaded_as_artifacts"] is False
    assert plan["model_inference_authorized"] is False
    assert plan["parameter_tuning_authorized"] is False


def test_record_normalization_and_verification() -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    record = module.normalize_record(_payload())
    target, files = module.verify_record(config, record)
    assert record["resource_type_id"] == "image"
    assert len(files) == 3
    assert target["key"] == "TEM_SAED.zip"
    assert target["size"] == 1400000000
    assert target["checksum"] == "md5:c7bda9d495dd0fd657a8fe0332db4f9c"


def test_checksum_change_fails_closed() -> None:
    module = _load_module()
    config = module.load_config(CONFIG)
    record = module.normalize_record(_payload(checksum="md5:changed"))
    with pytest.raises(module.ZenodoMetadataAuditError, match="checksum mismatch"):
        module.verify_record(config, record)


def test_run_writes_metadata_only_plan(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "fetch_json", lambda _url: _payload())
    output = tmp_path / "audit"
    summary = module.run(CONFIG, output)
    assert summary["metadata_audit_closeout"]["status"] == "Supported"
    assert summary["source"]["resource_type_id"] == "image"
    assert summary["source_archive_downloaded"] is False
    assert summary["archive_member_inventory_complete"] is False
    assert summary["external_validation_ready"] is False
    assert summary["analyzer_scientific_evidence_level"] == "Inconclusive"

    plan = json.loads(
        (output / "bounded_archive_acquisition_plan.json").read_text(encoding="utf-8")
    )
    assert plan["target_archive"]["exact_bytes"] == 1400000000
    assert plan["authorization"]["source_archive_download_authorized"] is False
    assert plan["authorization"]["model_inference_authorized"] is False
    assert not any(path.suffix == ".zip" for path in output.rglob("*"))
