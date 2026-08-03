from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_zenodo_8132804_co3o4_mn3o4.py"
CONFIG = (
    ROOT
    / "case_studies"
    / "zenodo_8132804_co3o4_mn3o4_audit"
    / "case_config.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_zenodo_8132804", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _record(config: dict) -> dict:
    source = config["source"]
    return {
        "id": int(source["record_id"]),
        "doi": source["doi"],
        "conceptdoi": source["concept_doi"],
        "metadata": {
            "title": source["title"],
            "version": source["version"],
            "license": {"id": "cc-by-4.0"},
        },
        "files": [
            {
                "key": source["archive_name"],
                "size": source["archive_bytes"],
                "checksum": f"md5:{source['archive_md5']}",
                "links": {"self": "https://example.invalid/archive/content"},
            }
        ],
    }


def test_case_config_is_fail_closed_and_valid() -> None:
    module = _load_module()
    config = _config()
    module.validate_config(config)
    assert config["bounded_transfer"]["full_archive_download_permitted"] is False
    assert config["expected_disposition"]["external_validation_ready"] is False
    assert config["expected_disposition"]["model_inference_permitted"] is False
    assert len(config["members"]) == 2


def test_config_rejects_full_archive_download_permission() -> None:
    module = _load_module()
    config = _config()
    config["bounded_transfer"]["full_archive_download_permitted"] = True
    with pytest.raises(module.AuditContractError, match="full archive download"):
        module.validate_config(config)


def test_config_rejects_understated_transfer_budget() -> None:
    module = _load_module()
    config = _config()
    config["bounded_transfer"]["maximum_compressed_member_bytes"] = 1
    with pytest.raises(module.AuditContractError, match="exceed transfer budget"):
        module.validate_config(config)


def test_archive_identity_is_checksum_and_licence_bound() -> None:
    module = _load_module()
    config = _config()
    record = _record(config)
    url = module._archive_content_url(record, config["source"])
    assert url == "https://example.invalid/archive/content"

    changed = copy.deepcopy(record)
    changed["files"][0]["checksum"] = "md5:" + "0" * 32
    with pytest.raises(RuntimeError, match="MD5 mismatch"):
        module._archive_content_url(changed, config["source"])


def test_hdf5_inspection_records_shapes_types_and_small_values(tmp_path: Path) -> None:
    module = _load_module()
    source = tmp_path / "fixture.h5"
    with h5py.File(source, "w") as handle:
        group = handle.create_group("haadf")
        group.create_dataset("tiltSeries", data=np.zeros((4, 5, 3), dtype=np.float32))
        group.create_dataset(
            "tiltAngles", data=np.array([-10.0, 0.0, 10.0], dtype=np.float32)
        )
    observed = module.inspect_hdf5(source)
    datasets = {item["path"]: item for item in observed["datasets"]}
    assert datasets["haadf/tiltSeries"]["shape"] == [4, 5, 3]
    assert datasets["haadf/tiltSeries"]["dtype"] == "float32"
    assert datasets["haadf/tiltAngles"]["values"]["preview"] == [-10.0, 0.0, 10.0]


def test_report_preserves_scientific_prohibitions() -> None:
    module = _load_module()
    text = module._report(
        {"status": "raw_stem_tomography_verified_but_not_tem_segmentation_validation_ready"}
    )
    assert "HAADF-STEM and EELS tomography" in text
    assert "not target TEM/HRTEM segmentation" in text
    assert "No annotation, model inference, retraining" in text
    assert "excluded_wrong_microscopy_modality" in text


def test_manifest_binds_artifact_bytes(tmp_path: Path) -> None:
    module = _load_module()
    artifact = tmp_path / "summary.json"
    artifact.write_text('{"ready": false}\n', encoding="utf-8")
    manifest = module._manifest(tmp_path, [artifact])
    assert manifest["artifact_count"] == 1
    record = manifest["artifacts"][0]
    assert record["bytes"] == artifact.stat().st_size
    assert record["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_source_contract_declares_single_mixed_material_stem_experiment() -> None:
    config = _config()
    context = config["published_context"]
    assert context["material"] == "Co3O4-Mn3O4 core-shell nanocrystal"
    assert context["microscopy"] == ["HAADF-STEM tomography", "EELS tmography"]
    assert context["source_assigned_experiment_id"] == "Exp_1"
    assert context["reported_independent_sample_count"] == 1
    assert context["reported_independent_acquisition_count"] == 1
