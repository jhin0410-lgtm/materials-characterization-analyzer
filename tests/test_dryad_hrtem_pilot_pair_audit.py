from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import h5py
import numpy as np
import pytest

from mca.tem_external_validation_pilot_audit import run_pilot_pair_audit
from mca.tem_external_validation_pilot_io import resolve_dryad_file
from mca.tem_external_validation_pilot_contract import (
    Hdf5Contract,
    OverlapContract,
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
    payload = path.read_bytes()
    md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    return md5, sha256


def _api(
    path: Path,
    file_id: int,
    name: str,
    *,
    algorithm: str = "md5",
) -> Path:
    md5, sha256 = _hashes(path)
    digest = {"md5": md5, "sha256": sha256}[algorithm]
    target = path.with_suffix(path.suffix + ".api.json")
    target.write_text(
        json.dumps(
            {
                "id": file_id,
                "path": name,
                "size": path.stat().st_size,
                "digest": f"{algorithm}:{digest}",
                "source_version_id": 247105,
                "dataset_doi": "10.7941/D1SP93",
                "_links": {
                    "stash:download": {
                        "href": (
                            "https://datadryad.org/downloads/file_stream/"
                            f"{file_id}"
                        )
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return target


def _fixture(
    tmp_path: Path,
    *,
    exact_overlap: bool = False,
    bad_label: bool = False,
    source_algorithm: str = "md5",
) -> dict[str, object]:
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
    config = replace(
        config,
        training=replace(
            config.training,
            md5=training_md5,
            sha256=training_sha,
            shape=(4, 512, 512),
            candidate_parent_patch_count=2,
            candidate_parent_count=2,
        ),
    )
    return {
        "config": config,
        "images": images_path,
        "labels": labels_path,
        "metadata": metadata_path,
        "training": training_path,
        "images_api": _api(
            images_path,
            config.image_file.file_id,
            config.image_file.name,
            algorithm=source_algorithm,
        ),
        "labels_api": _api(
            labels_path,
            config.label_file.file_id,
            config.label_file.name,
            algorithm=source_algorithm,
        ),
        "metadata_api": _api(
            metadata_path,
            config.processed_metadata_file.file_id,
            config.processed_metadata_file.name,
            algorithm=source_algorithm,
        ),
    }


def _run(tmp_path: Path, fixture: dict[str, object]):
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


def _assert_overlap_partition(summary: dict) -> None:
    overlap = summary["content_overlap_audit"]
    assert (
        overlap["exact_content_match_patch_count"]
        + overlap["review_required_patch_count"]
        + overlap["no_detected_overlap_patch_count"]
        == overlap["dryad_patch_count"]
    )


def test_public_contract_is_pinned() -> None:
    validate_public_config(load_config(CONFIG))


@pytest.mark.parametrize("source_algorithm", ["md5", "sha256"])
def test_valid_pair_without_overlap_is_ready_for_protocol_freeze(
    tmp_path: Path,
    source_algorithm: str,
) -> None:
    fixture = _fixture(tmp_path, source_algorithm=source_algorithm)
    summary = _run(tmp_path, fixture)
    assert summary["hdf5_pair_audit"]["patch_count"] == 3
    assert summary["hdf5_pair_audit"]["observed_label_values"] == [0, 1]
    assert summary["source"]["files"]["images"]["digest_algorithm"] == (
        source_algorithm
    )
    assert summary["source"]["files"]["images"]["source_digest_verified"]
    assert summary["source"]["processed_metadata_binding"]["status"] == (
        "exact_unique_row_binding"
    )
    assert summary["content_overlap_audit"]["exact_content_match_patch_count"] == 0
    assert summary["content_overlap_audit"]["review_required_patch_count"] == 0
    assert summary["content_overlap_audit"]["no_detected_overlap_patch_count"] == 3
    _assert_overlap_partition(summary)
    assert summary["readiness"]["content_overlap_gate_passed"]
    assert summary["readiness"]["next_status"] == (
        "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"
    )
    assert not summary["readiness"]["in_domain_cobalt_oxide_external_validation"]
    assert not summary["processing"]["model_inference_performed"]
    assert (tmp_path / "out" / "pilot_pair_audit_artifact_manifest.json").is_file()


def test_exact_training_overlap_is_blocked_and_exclusively_counted(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exact_overlap=True, source_algorithm="sha256")
    summary = _run(tmp_path, fixture)
    assert summary["content_overlap_audit"]["exact_content_match_patch_count"] == 1
    assert summary["content_overlap_audit"]["review_required_patch_count"] == 0
    assert summary["content_overlap_audit"]["no_detected_overlap_patch_count"] == 2
    _assert_overlap_partition(summary)
    assert not summary["readiness"]["content_overlap_gate_passed"]
    assert summary["readiness"]["next_status"] == (
        "blocked_by_possible_cross_dataset_content_overlap"
    )


def test_nonbinary_label_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, bad_label=True)
    with pytest.raises(ValueError, match="unexpected label values"):
        _run(tmp_path, fixture)


def test_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, source_algorithm="sha256")
    api_path = fixture["images_api"]
    payload = json.loads(api_path.read_text(encoding="utf-8"))
    payload["digest"] = "sha256:" + "0" * 64
    api_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sha256 mismatch"):
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


def test_unsupported_digest_algorithm_fails_closed() -> None:
    config = load_config(CONFIG)
    with pytest.raises(ValueError, match="unsupported Dryad digest algorithm"):
        normalize_dryad_file_metadata(
            {
                "id": config.image_file.file_id,
                "path": config.image_file.name,
                "size": 123,
                "digest": "sha1:" + "0" * 40,
            },
            config.image_file,
            "https://datadryad.org/downloads/file_stream/2451485",
        )



def test_public_contract_rejects_scientific_contract_drift() -> None:
    base = load_config(CONFIG)
    with pytest.raises(ValueError, match="public config mismatch for hdf5"):
        validate_public_config(
            replace(
                base,
                hdf5=Hdf5Contract(
                    image_dataset_name=base.hdf5.image_dataset_name,
                    label_dataset_name=base.hdf5.label_dataset_name,
                    patch_height=base.hdf5.patch_height,
                    patch_width=base.hdf5.patch_width,
                    image_mean_abs_tolerance=base.hdf5.image_mean_abs_tolerance,
                    image_std_abs_tolerance=base.hdf5.image_std_abs_tolerance,
                    allowed_label_values=(0, 1, 2),
                ),
            )
        )
    with pytest.raises(ValueError, match="public config mismatch for overlap"):
        validate_public_config(
            replace(
                base,
                overlap=OverlapContract(
                    quantization_decimals=base.overlap.quantization_decimals,
                    signature_block_size=base.overlap.signature_block_size,
                    review_ncc_threshold=0.90,
                    exact_match_rule=base.overlap.exact_match_rule,
                ),
            )
        )
    with pytest.raises(ValueError, match="public config mismatch for training"):
        validate_public_config(
            replace(base, training=replace(base.training, sha256="0" * 64))
        )
    with pytest.raises(ValueError, match="public config mismatch for notebook_commit"):
        validate_public_config(replace(base, notebook_commit="0" * 40))


def test_non_authoritative_processed_metadata_binding_blocks_protocol_freeze(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    config = fixture["config"]
    fixture["metadata"].write_text(
        "dataset,material\n"
        f"{config.image_file.name.removesuffix('_Images.h5')},Au\n",
        encoding="utf-8",
    )
    fixture["metadata_api"] = _api(
        fixture["metadata"],
        config.processed_metadata_file.file_id,
        config.processed_metadata_file.name,
    )
    summary = _run(tmp_path, fixture)
    assert summary["source"]["processed_metadata_binding"]["status"] == (
        "unique_prefix_candidate_not_authoritative"
    )
    assert not summary["readiness"]["data_audit_complete"]
    assert not summary["readiness"]["processed_metadata_binding_authoritative"]
    assert summary["readiness"]["next_status"] == (
        "blocked_unresolved_processed_metadata_binding"
    )


def test_automatic_resolution_follows_pinned_version_and_sends_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(CONFIG)
    payload_path = tmp_path / config.processed_metadata_file.name
    payload_path.write_text("x\n", encoding="utf-8")
    digest = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    api_url = config.api_file_endpoint_template.format(
        file_id=config.processed_metadata_file.file_id
    )
    version_url = f"https://datadryad.org/api/v2/versions/{config.source_version_id}"
    files_url = version_url + "/files"
    individual = {
        "id": config.processed_metadata_file.file_id,
        "path": config.processed_metadata_file.name,
        "size": payload_path.stat().st_size,
        "_links": {
            "stash:version": {"href": version_url},
            "stash:download": {"href": api_url + "/download"},
        },
    }
    version = {
        "doi": config.doi,
        "_links": {"stash:files": {"href": files_url}},
    }
    files = {
        "files": [
            {
                "id": config.processed_metadata_file.file_id,
                "path": config.processed_metadata_file.name,
                "size": payload_path.stat().st_size,
                "digest": f"sha256:{digest}",
            }
        ]
    }
    responses = {api_url: individual, version_url: version, files_url: files}
    monkeypatch.setattr(
        "mca.tem_external_validation_pilot_io.fetch_json",
        lambda url, attempts=5, headers=None: responses[url],
    )
    captured: dict[str, str] = {}

    def fake_download(url, destination, attempts=5, headers=None):
        captured.update(dict(headers or {}))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload_path.read_bytes())

    monkeypatch.setattr(
        "mca.tem_external_validation_pilot_io.download", fake_download
    )
    monkeypatch.setenv("DRYAD_API_TOKEN", "test-token")
    metadata, resolved = resolve_dryad_file(
        config,
        config.processed_metadata_file,
        local_path=None,
        api_metadata_path=None,
        temp=tmp_path / "download",
        source_version_cache={},
    )
    assert resolved.is_file()
    assert metadata["source_version_id"] == 247105
    assert metadata["dataset_doi"] == config.doi
    assert metadata["source_digest_verified"]
    assert captured["Authorization"] == "Bearer test-token"


def test_automatic_download_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(CONFIG)
    api_url = config.api_file_endpoint_template.format(file_id=config.image_file.file_id)
    version_url = f"https://datadryad.org/api/v2/versions/{config.source_version_id}"
    files_url = version_url + "/files"
    responses = {
        api_url: {
            "id": config.image_file.file_id,
            "path": config.image_file.name,
            "size": 1,
            "_links": {
                "stash:version": {"href": version_url},
                "stash:download": {"href": api_url + "/download"},
            },
        },
        version_url: {"doi": config.doi, "_links": {"stash:files": {"href": files_url}}},
        files_url: {
            "files": [
                {
                    "id": config.image_file.file_id,
                    "path": config.image_file.name,
                    "size": 1,
                    "digest": "sha256:" + hashlib.sha256(b"x").hexdigest(),
                }
            ]
        },
    }
    monkeypatch.setattr(
        "mca.tem_external_validation_pilot_io.fetch_json",
        lambda url, attempts=5, headers=None: responses[url],
    )
    monkeypatch.delenv("DRYAD_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DRYAD_API_TOKEN is required"):
        resolve_dryad_file(
            config,
            config.image_file,
            local_path=None,
            api_metadata_path=None,
            temp=tmp_path / "download",
            source_version_cache={},
        )
