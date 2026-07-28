from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from mca.tem_mask_import import (
    PUBLIC_ARCHIVE_MD5,
    PUBLIC_ARCHIVE_SHA256,
    PUBLIC_CASE_ID,
    PUBLIC_DATASET_DOI,
    PUBLIC_EXPECTED_MEMBERS,
    QUALITY_FLAG,
    TemMaskCaseConfig,
    load_config,
    run_case,
    summarize_binary_mask,
    validate_public_case_config,
)


def _hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_h5(path: Path, values: np.ndarray, *, root_attribute: bool = False) -> None:
    with h5py.File(path, "w") as handle:
        if root_attribute:
            handle.attrs["unexpected"] = "value"
        handle.create_dataset("labels", data=values.astype(np.float64))


def _write_fixture_archive(
    root: Path,
    values: np.ndarray,
    *,
    member: str = "Fixture_segmented_images.h5",
    root_attribute: bool = False,
    extra_member: tuple[str, bytes, int | None] | None = None,
) -> tuple[Path, TemMaskCaseConfig]:
    h5_path = root / "source.h5"
    _write_h5(h5_path, values, root_attribute=root_attribute)
    archive = root / "Segmented_images.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(h5_path, arcname=member)
        if extra_member is not None:
            name, data, unix_mode = extra_member
            info = zipfile.ZipInfo(name)
            if unix_mode is not None:
                info.create_system = 3
                info.external_attr = unix_mode << 16
            zf.writestr(info, data)
    payload = {
        "case_id": "fixture_tem_masks",
        "source": {
            "record_id": 1,
            "doi": "10.0000/fixture",
            "dataset_version": "fixture",
            "license": "fixture-only",
            "archive_name": archive.name,
            "archive_url": "https://example.invalid/fixture.zip",
            "archive_md5": _hash(archive, "md5"),
            "archive_sha256": _hash(archive, "sha256"),
            "expected_members": [member],
        },
        "hdf5_contract": {
            "dataset_name": "labels",
            "expected_shape": list(values.shape),
            "expected_dtype": "float64",
            "allowed_values": [0.0, 1.0],
        },
        "analysis": {"connectivity": 8},
    }
    return archive, TemMaskCaseConfig.from_mapping(payload)


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_tracked_public_config_is_exactly_pinned() -> None:
    config = load_config("case_studies/public_cobalt_oxide_tem_masks/case_config.json")
    validate_public_case_config(config)
    assert config.case_id == PUBLIC_CASE_ID
    assert config.doi == PUBLIC_DATASET_DOI
    assert config.archive_md5 == PUBLIC_ARCHIVE_MD5
    assert config.archive_sha256 == PUBLIC_ARCHIVE_SHA256
    assert config.expected_members == PUBLIC_EXPECTED_MEMBERS
    assert config.expected_shape == (5, 4096, 4096)


def test_eight_connected_pixel_descriptors_do_not_create_physical_sizes() -> None:
    mask = np.zeros((5, 6), dtype=np.uint8)
    mask[0, 0] = 1
    mask[2, 2] = 1
    mask[3, 3] = 1
    summary, components = summarize_binary_mask(
        mask,
        sample_id="fixture",
        measurement_id="fixture_mask_00",
        archive_member="Fixture_segmented_images.h5",
        frame_index=0,
    )
    assert summary["foreground_pixel_count"] == 3
    assert summary["connected_component_count"] == 2
    assert summary["border_touching_component_count"] == 1
    assert summary["interior_component_count"] == 1
    assert summary["component_area_pixels_total"] == 3
    assert sorted(row["area_pixels"] for row in components) == [1, 2]
    assert summary["pixel_calibration_applied"] is False


def test_fixture_run_is_deterministic_provenance_complete_and_pixel_only(tmp_path: Path) -> None:
    values = np.zeros((2, 8, 9), dtype=np.float64)
    values[0, 1:3, 1:3] = 1
    values[1, 0, 0] = 1
    values[1, 4:7, 4:8] = 1
    archive, config = _write_fixture_archive(tmp_path, values)

    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = run_case(config, first, archive_path=archive)
    run_case(config, second, archive_path=archive)

    assert _file_hashes(first) == _file_hashes(second)
    assert summary["result_counts"]["source_file_count"] == 1
    assert summary["result_counts"]["mask_count"] == 2
    assert summary["result_counts"]["analysis_count"] == 2
    assert summary["scientific_closeout"]["status"] == "Diagnostic"
    assert all(value is False for value in summary["processing"].values())

    masks = pd.read_csv(first / "tem_source_mask_summary.csv")
    components = pd.read_csv(first / "tem_source_mask_components.csv")
    features = pd.read_csv(first / "tem_source_mask_features_long.csv")
    assert masks["foreground_pixel_count"].sum() == 17
    assert components["area_pixels"].sum() == 17
    assert set(features["unit"]).issubset({"fraction", "pixel", "pixel^2", "count"})
    assert not features["unit"].astype(str).str.contains("nm", case=False).any()
    assert set(features["quality_flag"]) == {QUALITY_FLAG}
    assert features["source_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert features["preprocessing_id"].str.fullmatch(r"[0-9a-f]{16}").all()

    manifest = json.loads((first / "case_analysis_manifest.json").read_text())
    assert manifest["analysis_count"] == 2
    for analysis in manifest["analyses"]:
        assert analysis["acquisition_metadata"]["mask_provenance"] == (
            "source_predicted_segmentation"
        )
        assert analysis["acquisition_metadata"]["pixel_calibration"] == (
            "not_embedded_in_selected_hdf5"
        )
        assert "source_prediction_not_independent_ground_truth" in analysis["warnings"]

    artifact_manifest = json.loads((first / "case_artifact_manifest.json").read_text())
    assert artifact_manifest["case_id"] == config.case_id
    assert artifact_manifest["source_archive_sha256"] == config.archive_sha256
    for artifact in artifact_manifest["artifacts"]:
        path = first / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_nonbinary_and_unexpected_hdf5_metadata_fail_closed(tmp_path: Path) -> None:
    values = np.zeros((1, 5, 5), dtype=np.float64)
    values[0, 2, 2] = 0.5
    archive, config = _write_fixture_archive(tmp_path, values)
    output = tmp_path / "bad-values"
    with pytest.raises(ValueError, match="non-binary mask value"):
        run_case(config, output, archive_path=archive)
    assert not output.exists()

    metadata_root = tmp_path / "metadata"
    metadata_root.mkdir()
    archive, config = _write_fixture_archive(
        metadata_root,
        np.zeros((1, 4, 4), dtype=np.float64),
        root_attribute=True,
    )
    with pytest.raises(ValueError, match="root attributes changed"):
        run_case(config, tmp_path / "bad-metadata", archive_path=archive)


def test_archive_traversal_symlink_and_member_drift_are_rejected(tmp_path: Path) -> None:
    values = np.zeros((1, 4, 4), dtype=np.float64)
    traversal_root = tmp_path / "traversal"
    traversal_root.mkdir()
    archive, config = _write_fixture_archive(
        traversal_root,
        values,
        extra_member=("../escape.txt", b"no", None),
    )
    with pytest.raises(ValueError, match="unsafe archive path"):
        run_case(config, tmp_path / "traversal-output", archive_path=archive)

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    archive, config = _write_fixture_archive(
        symlink_root,
        values,
        extra_member=("link", b"target", stat.S_IFLNK | 0o777),
    )
    with pytest.raises(ValueError, match="symlink rejected"):
        run_case(config, tmp_path / "symlink-output", archive_path=archive)

    drift_root = tmp_path / "drift"
    drift_root.mkdir()
    archive, config = _write_fixture_archive(
        drift_root,
        values,
        extra_member=("unexpected.txt", b"unexpected", None),
    )
    with pytest.raises(ValueError, match="archive members do not match"):
        run_case(config, tmp_path / "drift-output", archive_path=archive)


def test_hash_mismatch_and_nonempty_output_are_rejected(tmp_path: Path) -> None:
    archive, config = _write_fixture_archive(
        tmp_path,
        np.zeros((1, 4, 4), dtype=np.float64),
    )
    payload = config.__dict__.copy()
    payload["archive_sha256"] = "0" * 64
    bad_config = TemMaskCaseConfig(**payload)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_case(bad_config, tmp_path / "hash-output", archive_path=archive)

    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_case(config, output, archive_path=archive)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_public_importer_contains_no_training_prediction_or_physical_conversion() -> None:
    text = Path("src/mca/tem_mask_import.py").read_text(encoding="utf-8")
    forbidden = (
        "from sklearn",
        "import torch",
        "import tensorflow",
        ".fit(",
        ".predict(",
        "nm_per_pixel",
        "microns_per_pixel",
        "particle_diameter_nm",
    )
    for token in forbidden:
        assert token not in text
    assert '"model_training_performed": False' in text
    assert '"resegmentation_performed": False' in text
    assert '"segmentation_accuracy_computed": False' in text
