from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from mca.tem_training_data_audit import (
    PUBLIC_CASE_ID,
    PUBLIC_DOI,
    PUBLIC_IMAGE_SHA256,
    PUBLIC_LABEL_SHA256,
    READINESS_STATUS,
    FileSpec,
    NotebookSplitContract,
    TrainingDataAuditConfig,
    inspect_training_pair,
    load_config,
    run_training_data_audit,
    validate_public_config,
)


def _hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_hdf5(
    path: Path,
    dataset_name: str,
    values: np.ndarray,
    *,
    add_attribute: bool = False,
    chunks: bool | None = None,
) -> None:
    with h5py.File(path, "w") as handle:
        if add_attribute:
            handle.attrs["unexpected"] = "metadata"
        kwargs = {} if chunks is None else {"chunks": chunks}
        handle.create_dataset(dataset_name, data=values, **kwargs)


def _standardized_patches(count: int, height: int, width: int) -> np.ndarray:
    base = np.arange(count * height * width, dtype=np.float64).reshape(count, height, width)
    return np.stack([(patch - patch.mean()) / patch.std() for patch in base])


def _fixture(
    root: Path,
    *,
    image_values: np.ndarray | None = None,
    label_values: np.ndarray | None = None,
    image_attribute: bool = False,
    label_attribute: bool = False,
    image_chunks: bool | None = None,
) -> tuple[Path, Path, TrainingDataAuditConfig]:
    images = (
        _standardized_patches(8, 8, 8)
        if image_values is None
        else np.asarray(image_values)
    )
    if label_values is None:
        foreground = np.zeros((8, 8, 8), dtype=np.float64)
        foreground[:, 2:6, 2:6] = 1.0
        labels = np.stack([1.0 - foreground, foreground], axis=-1)
    else:
        labels = np.asarray(label_values)
    image_path = root / "training_images.h5"
    label_path = root / "training_labels.h5"
    _write_hdf5(
        image_path,
        "images",
        images.astype(np.float64),
        add_attribute=image_attribute,
        chunks=image_chunks,
    )
    _write_hdf5(
        label_path,
        "labels",
        labels.astype(np.float64),
        add_attribute=label_attribute,
    )
    image_spec = FileSpec(
        name=image_path.name,
        url="https://example.invalid/training_images.h5",
        md5=_hash(image_path, "md5"),
        sha256=_hash(image_path, "sha256"),
    )
    label_spec = FileSpec(
        name=label_path.name,
        url="https://example.invalid/training_labels.h5",
        md5=_hash(label_path, "md5"),
        sha256=_hash(label_path, "sha256"),
    )
    notebook = NotebookSplitContract(
        repository="fixture/repository",
        commit="0" * 40,
        training_notebook="training.ipynb",
        training_notebook_blob_sha="1" * 40,
        tiling_notebook="tiling.ipynb",
        tiling_notebook_blob_sha="2" * 40,
        patch_count=8,
        n_splits=2,
        shuffle=True,
        random_state=42,
        parent_group_id_used=False,
        parent_grid_rows=2,
        parent_grid_columns=2,
    )
    config = TrainingDataAuditConfig(
        case_id="fixture_tem_training_data_audit",
        record_id=1,
        doi="10.0000/fixture",
        dataset_version="fixture",
        license="fixture-only",
        source_description="fixture training pairs",
        image_file=image_spec,
        label_file=label_spec,
        image_dataset_name="images",
        label_dataset_name="labels",
        image_shape=tuple(int(value) for value in images.shape),
        label_shape=tuple(int(value) for value in labels.shape),
        image_dtype="float64",
        label_dtype="float64",
        attributes_expected=False,
        image_mean_abs_tolerance=1e-10,
        image_std_abs_tolerance=1e-12,
        candidate_parent_group_count=2,
        patches_per_candidate_parent=4,
        max_image_seam_ratio=10.0,
        max_label_seam_ratio=10.0,
        notebook=notebook,
        literature_pixel_size_range_pm=(67.0, 86.0),
        calibration_binding_status="not_bound",
    )
    config.validate()
    return image_path, label_path, config


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_tracked_public_config_is_exactly_pinned() -> None:
    config = load_config(
        "case_studies/public_cobalt_oxide_tem_training_data_audit/case_config.json"
    )
    validate_public_config(config)
    assert config.case_id == PUBLIC_CASE_ID
    assert config.doi == PUBLIC_DOI
    assert config.image_file.sha256 == PUBLIC_IMAGE_SHA256
    assert config.label_file.sha256 == PUBLIC_LABEL_SHA256
    assert config.image_shape == (256, 512, 512)
    assert config.label_shape == (256, 512, 512, 2)
    assert config.notebook.parent_group_id_used is False


def test_fixture_audit_is_deterministic_and_preserves_claim_boundary(
    tmp_path: Path,
) -> None:
    image_path, label_path, config = _fixture(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = run_training_data_audit(
        config,
        first,
        image_path=image_path,
        label_path=label_path,
    )
    run_training_data_audit(
        config,
        second,
        image_path=image_path,
        label_path=label_path,
    )
    assert _file_hashes(first) == _file_hashes(second)
    assert summary["result_counts"] == {
        "patch_pair_count": 8,
        "candidate_parent_group_count": 2,
        "notebook_fold_count": 2,
    }
    assert summary["scientific_closeout"]["status"] == "Diagnostic"
    assert summary["scientific_closeout"]["result"] == READINESS_STATUS
    assert summary["notebook_split_audit"]["candidate_parent_group_overlap_in_every_fold"]
    assert not summary["notebook_split_audit"]["independent_parent_image_validation"]
    assert summary["value_contract"]["labels_binary"]
    assert summary["value_contract"]["label_channels_complementary_one_hot"]
    assert all(value is False for value in summary["processing"].values())

    patches = pd.read_csv(first / "tem_training_patch_inventory.csv")
    seams = pd.read_csv(first / "tem_training_candidate_parent_seams.csv")
    splits = pd.read_csv(first / "tem_training_notebook_split_overlap.csv")
    assert len(patches) == 8
    assert len(seams) == 2
    assert len(splits) == 2
    assert patches["image_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert patches["label_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert patches["image_mean"].abs().max() <= 1e-10
    assert (patches["image_std"] - 1.0).abs().max() <= 1e-12
    assert splits["overlap_group_count"].eq(2).all()
    assert not splits["independent_parent_image_validation"].any()

    manifest = json.loads(
        (first / "training_data_readiness_artifact_manifest.json").read_text()
    )
    assert manifest["artifact_count"] == 5
    for record in manifest["artifacts"]:
        path = first / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_nonfinite_nonbinary_and_noncomplementary_values_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "nonfinite"
    root.mkdir()
    images = _standardized_patches(8, 8, 8)
    images[0, 0, 0] = np.nan
    image_path, label_path, config = _fixture(root, image_values=images)
    with pytest.raises(ValueError, match="non-finite image"):
        inspect_training_pair(image_path, label_path, config=config)

    root = tmp_path / "nonbinary"
    root.mkdir()
    foreground = np.zeros((8, 8, 8), dtype=np.float64)
    labels = np.stack([1.0 - foreground, foreground], axis=-1)
    labels[0, 0, 0, 1] = 0.5
    image_path, label_path, config = _fixture(root, label_values=labels)
    with pytest.raises(ValueError, match="non-binary label"):
        inspect_training_pair(image_path, label_path, config=config)

    root = tmp_path / "noncomplement"
    root.mkdir()
    labels = np.zeros((8, 8, 8, 2), dtype=np.float64)
    image_path, label_path, config = _fixture(root, label_values=labels)
    with pytest.raises(ValueError, match="not complementary one-hot"):
        inspect_training_pair(image_path, label_path, config=config)


def test_hdf5_shape_attribute_storage_and_standardization_drift_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "attribute"
    root.mkdir()
    image_path, label_path, config = _fixture(root, image_attribute=True)
    with pytest.raises(ValueError, match="root attributes changed"):
        inspect_training_pair(image_path, label_path, config=config)

    root = tmp_path / "chunks"
    root.mkdir()
    image_path, label_path, config = _fixture(root, image_chunks=True)
    with pytest.raises(ValueError, match="storage layout changed"):
        inspect_training_pair(image_path, label_path, config=config)

    root = tmp_path / "standardization"
    root.mkdir()
    images = np.zeros((8, 8, 8), dtype=np.float64)
    image_path, label_path, config = _fixture(root, image_values=images)
    with pytest.raises(ValueError, match="standard deviation drift"):
        inspect_training_pair(image_path, label_path, config=config)

    root = tmp_path / "shape"
    root.mkdir()
    image_path, label_path, config = _fixture(root)
    wrong_label = root / "wrong_labels.h5"
    with h5py.File(wrong_label, "w") as handle:
        handle.create_dataset("labels", data=np.zeros((7, 8, 8, 2)))
    with pytest.raises(ValueError, match="shape"):
        inspect_training_pair(image_path, wrong_label, config=config)


def test_hash_symlink_unknown_config_and_nonempty_output_are_rejected(
    tmp_path: Path,
) -> None:
    image_path, label_path, config = _fixture(tmp_path)
    bad_image = FileSpec(
        name=config.image_file.name,
        url=config.image_file.url,
        md5=config.image_file.md5,
        sha256="0" * 64,
    )
    bad_config = TrainingDataAuditConfig(
        **{**config.__dict__, "image_file": bad_image}
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_training_data_audit(
            bad_config,
            tmp_path / "hash-output",
            image_path=image_path,
            label_path=label_path,
        )

    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_training_data_audit(
            config,
            output,
            image_path=image_path,
            label_path=label_path,
        )
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"

    symlink = tmp_path / "image-link.h5"
    try:
        symlink.symlink_to(image_path)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(ValueError, match="must not be a symlink"):
        run_training_data_audit(
            config,
            tmp_path / "symlink-output",
            image_path=symlink,
            label_path=label_path,
        )

    payload = json.loads(
        Path(
            "case_studies/public_cobalt_oxide_tem_training_data_audit/case_config.json"
        ).read_text()
    )
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown config"):
        TrainingDataAuditConfig.from_mapping(payload)


def test_training_audit_contains_no_model_or_physical_conversion() -> None:
    text = Path("src/mca/tem_training_data_audit.py").read_text(encoding="utf-8")
    forbidden = (
        "from sklearn",
        "import torch",
        "import tensorflow",
        ".fit(",
        ".predict(",
        "nm_per_pixel",
        "particle_diameter_nm",
        "equivalent_diameter_nm",
    )
    for token in forbidden:
        assert token not in text
    assert '"model_training_performed": False' in text
    assert '"segmentation_accuracy_computed": False' in text
    assert '"physical_size_computed": False' in text
