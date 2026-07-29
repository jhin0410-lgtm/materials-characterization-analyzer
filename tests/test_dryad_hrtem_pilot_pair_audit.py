from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import h5py
import numpy as np
import pytest

from mca.tem_external_validation_pilot_audit import run_pilot_pair_audit
from mca.tem_external_validation_pilot_contract import (
    load_config,
    normalize_dryad_file_metadata,
    validate_public_config,
)

CONFIG = Path("case_studies/dryad_hrtem_pilot_pair_audit/case_config.json")


def _standardized(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = rng.normal(size=(512, 512))
    return (values - values.mean()) / values.std()


def _hashes(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return md5, sha256


def _api(path: Path, file_id: int, name: str) -> Path:
    md5, _ = _hashes(path)
    target = path.with_suffix(path.suffix + ".api.json")
    target.write_text(
        json.dumps(
            {
                "id": file_id,
                "path": name,
                "size": path.stat().st_size,
                "digest": f"md5:{md5}",
                "_links": {
                    "stash:download": {
                        "href": f"https://datadryad.org/downloads/file_stream/{file_id}"
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return target


def _fixture(tmp_path: Path, *, exact_overlap: bool = False, bad_label: bool = False):
    config = load_config(CONFIG)
    validate_public_config(config)
    images_path = tmp_path / config.image_file.name
    labels_path = tmp_path / config.label_file.name
    metadata_path = tmp_path / config.processed_metadata_file.name
    training_path = tmp_path / config.training.name

    dryad = np.stack([_standardized(1), _standardized(2), _standardized(3)])
    labels = np.zeros((3, 512, 512), dtype=np.uint8)
    labels[0, 100:200, 100:200] = 1
    labels[1, 50:300, 200:350] = 1
    labels[2, 10:500, 10:500] = 1
    if bad_label:
        labels[1, 0, 0] = 2
    training = np.stack(
        [
            dryad[0] if exact_overlap else _standardized(10),
            _standardized(11),
            _standardized(12),
            _standardized(13),
        ]
    )
    with h5py.File(images_path, "w") as handle:
        handle.create_dataset("images", data=dryad)
    with h5py.File(labels_path, "w") as handle:
        handle.create_dataset("labels", data=labels)
    with h5py.File(training_path, "w") as handle:
        handle.create_dataset("images", data=training)
    metadata_path.write_text(
        "image_file,label_file,material,raw_session\n"
        f"{config.image_file.name},{config.label_file.name},Au,synthetic-session\n",
        encoding="utf-8",
    )
    training_md5, training_sha = _hashes(training_path)
    training_reference = replace(
        config.training,
        md5=training_md5,
        sha256=training_sha,
        shape=(4, 512, 512),
        candidate_parent_patch_count=2,
        candidate_parent_count=2,
    )
    config = replace(config, training=training_reference)
    return {
        "config": config,
        "images": images_path,
        "labels": labels_path,
        "metadata": metadata_path,
        "training": training_path,
        "images_api": _api(images_path, config.image_file.file_id, config.image_file.name),
        "labels_api": _api(labels_path, config.label_file.file_id, config.label_file.name),
        "metadata_api": _api(
            metadata_path,
            config.processed_metadata_file.file_id,
            config.processed_metadata_file.name,
        ),
    }


def _run(tmp_path: Path, fixture: dict):
    return run_pilot_pair_audit(
        fixture["config"],
        tmp_path / "out",
        image_path=fixture["images"],
        label_path=fixture["labels"],
        processed_metadata_path=fixture["metadata"],
        training_path=fixture["training"],
        image_api_metadata_path=fixture["images_api"],
        label_api_metadata_path=fixture["labels_api"],
        processed_metadata_api_path=fixture["metadata_api"],
    )


def test_public_contract_is_pinned() -> None:
    validate_public_config(load_config(CONFIG))


def test_valid_pair_without_overlap_is_ready_for_protocol_freeze(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    summary = _run(tmp_path, fixture)
    assert summary["hdf5_pair_audit"]["patch_count"] == 3
    assert summary["hdf5_pair_audit"]["observed_label_values"] == [0, 1]
    assert summary["source"]["processed_metadata_binding"]["status"] == (
        "exact_unique_row_binding"
    )
    assert summary["content_overlap_audit"]["exact_content_match_patch_count"] == 0
    assert summary["content_overlap_audit"]["review_required_patch_count"] == 0
    assert summary["readiness"]["content_overlap_gate_passed"]
    assert summary["readiness"]["next_status"] == (
        "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"
    )
    assert not summary["readiness"]["in_domain_cobalt_oxide_external_validation"]
    assert not summary["processing"]["model_inference_performed"]
    assert (tmp_path / "out" / "pilot_pair_audit_artifact_manifest.json").is_file()


def test_exact_training_overlap_is_blocked(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exact_overlap=True)
    summary = _run(tmp_path, fixture)
    assert summary["content_overlap_audit"]["exact_content_match_patch_count"] == 1
    assert not summary["readiness"]["content_overlap_gate_passed"]
    assert summary["readiness"]["next_status"] == (
        "blocked_by_possible_cross_dataset_content_overlap"
    )


def test_nonbinary_label_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, bad_label=True)
    with pytest.raises(ValueError, match="unexpected label values"):
        _run(tmp_path, fixture)


def test_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["images_api"].read_text(encoding="utf-8"))
    payload["digest"] = "md5:" + "0" * 32
    fixture["images_api"].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="MD5 mismatch"):
        _run(tmp_path, fixture)


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _run(tmp_path, fixture)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _run(tmp_path, fixture)


def test_dryad_metadata_requires_checksum() -> None:
    config = load_config(CONFIG)
    with pytest.raises(ValueError, match="does not expose a checksum"):
        normalize_dryad_file_metadata(
            {
                "id": config.image_file.file_id,
                "path": config.image_file.name,
                "size": 123,
            },
            config.image_file,
            "https://datadryad.org/downloads/file_stream/2451485",
        )
