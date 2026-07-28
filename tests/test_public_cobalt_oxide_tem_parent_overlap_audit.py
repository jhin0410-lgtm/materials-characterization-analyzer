from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from mca.tem_parent_overlap_audit import (
    CLOSEOUT_RESULT,
    LABEL_STATUS,
    OVERLAP_EQUIVALENT,
    OVERLAP_NOT_DETECTED,
    ArchiveSpec,
    FileSpec,
    ParentOverlapAuditConfig,
    SourceMemberSpec,
    load_config,
    run_parent_overlap_audit,
    validate_public_config,
)


def _hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _standardize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return (values - values.mean()) / values.std()


def _parent(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(8, 8))
    y, x = np.mgrid[:8, :8]
    return base + 0.13 * x + 0.07 * y + 0.02 * x * y


def _training_patches(parents: list[np.ndarray]) -> np.ndarray:
    patches = []
    for parent in parents:
        for row in range(2):
            for column in range(2):
                tile = parent[row * 4 : (row + 1) * 4, column * 4 : (column + 1) * 4]
                patches.append(_standardize(tile))
    return np.asarray(patches, dtype=np.float64)


def _fixture(root: Path, *, nonfinite: bool = False) -> tuple[Path, Path, ParentOverlapAuditConfig]:
    parent0 = _parent(1)
    parent1 = _parent(2)
    unrelated = _parent(3)
    training = _training_patches([parent0, parent1])
    training_path = root / "training_images.h5"
    with h5py.File(training_path, "w") as handle:
        handle.create_dataset("images", data=training)

    frames = np.stack([_standardize(parent0), _standardize(parent1), _standardize(unrelated)])
    if nonfinite:
        frames[2, 0, 0] = np.nan
    member_name = "fixture_TEM_images.h5"
    member_path = root / member_name
    with h5py.File(member_path, "w") as handle:
        handle.create_dataset("images", data=frames.astype(np.float64))
    archive_path = root / "TEM_images.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(member_path, arcname=member_name)

    config = ParentOverlapAuditConfig(
        case_id="fixture_parent_overlap_audit",
        record_id=1,
        doi="10.0000/fixture",
        dataset_version="fixture",
        license="fixture-only",
        source_description="fixture source frames",
        training_file=FileSpec(
            name=training_path.name,
            url="https://example.invalid/training_images.h5",
            md5=_hash(training_path, "md5"),
            sha256=_hash(training_path, "sha256"),
        ),
        source_archive=ArchiveSpec(
            name=archive_path.name,
            url="https://example.invalid/TEM_images.zip",
            md5=_hash(archive_path, "md5"),
            sha256=_hash(archive_path, "sha256"),
            expected_members=(member_name,),
        ),
        source_members=(SourceMemberSpec(source_id="fixture", image_member=member_name),),
        training_dataset_name="images",
        source_dataset_name="images",
        training_shape=(8, 4, 4),
        source_member_shape=(3, 8, 8),
        dtype="float64",
        attributes_expected=False,
        parent_count=2,
        grid_rows=2,
        grid_columns=2,
        tile_height=4,
        tile_width=4,
        image_mean_abs_tolerance=1e-10,
        image_std_abs_tolerance=1e-12,
        quantization_decimals=9,
        signature_block_size=2,
        review_ncc_threshold=0.995,
        independent_label_status=LABEL_STATUS,
        notebook_repository="fixture/repository",
        notebook_commit="0" * 40,
        tiling_notebook="tiling.ipynb",
        tiling_notebook_blob_sha="1" * 40,
        normalization_notebook="normalization.ipynb",
        normalization_notebook_blob_sha="2" * 40,
    )
    config.validate()
    return training_path, archive_path, config


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_tracked_public_config_is_exactly_pinned() -> None:
    config = load_config(
        "case_studies/public_cobalt_oxide_tem_parent_overlap_audit/case_config.json"
    )
    validate_public_config(config)
    assert config.training_shape == (256, 512, 512)
    assert config.source_member_shape == (5, 4096, 4096)
    assert config.parent_count == 4
    assert config.independent_label_status == LABEL_STATUS


def test_fixture_detects_two_exact_parents_but_zero_external_validation_candidates(
    tmp_path: Path,
) -> None:
    training_path, archive_path, config = _fixture(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = run_parent_overlap_audit(
        config,
        first,
        training_path=training_path,
        source_archive_path=archive_path,
    )
    run_parent_overlap_audit(
        config,
        second,
        training_path=training_path,
        source_archive_path=archive_path,
    )
    assert _file_hashes(first) == _file_hashes(second)
    assert summary["scientific_closeout"]["status"] == "Diagnostic"
    assert summary["scientific_closeout"]["result"] == CLOSEOUT_RESULT
    assert summary["result_counts"] == {
        "training_candidate_parent_count": 2,
        "source_member_count": 1,
        "source_frame_count": 3,
        "pairwise_comparison_count": 6,
        "content_equivalent_overlap_frame_count": 2,
        "review_required_frame_count": 0,
        "no_content_equivalent_overlap_detected_frame_count": 1,
        "independent_external_validation_candidate_count": 0,
    }
    assert not summary["external_validation_readiness"][
        "source_masks_are_independent_ground_truth"
    ]

    frames = pd.read_csv(first / "tem_parent_overlap_frame_inventory.csv")
    comparisons = pd.read_csv(first / "tem_parent_overlap_pairwise_comparisons.csv")
    assert len(frames) == 3
    assert len(comparisons) == 6
    assert frames.loc[0, "overlap_status"] == OVERLAP_EQUIVALENT
    assert frames.loc[1, "overlap_status"] == OVERLAP_EQUIVALENT
    assert frames.loc[2, "overlap_status"] == OVERLAP_NOT_DETECTED
    assert frames.loc[0, "best_training_candidate_parent"] == 0
    assert frames.loc[1, "best_training_candidate_parent"] == 1
    assert frames.loc[:1, "best_exact_tile_match_count"].eq(4).all()
    assert not frames["independent_external_validation_candidate"].any()

    manifest = json.loads(
        (first / "parent_overlap_audit_artifact_manifest.json").read_text()
    )
    assert manifest["artifact_count"] == 4
    for record in manifest["artifacts"]:
        path = first / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_nonfinite_hash_output_and_unknown_config_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "nonfinite"
    root.mkdir()
    training_path, archive_path, config = _fixture(root, nonfinite=True)
    with pytest.raises(ValueError, match="non-finite value"):
        run_parent_overlap_audit(
            config,
            root / "output",
            training_path=training_path,
            source_archive_path=archive_path,
        )

    root = tmp_path / "hash"
    root.mkdir()
    training_path, archive_path, config = _fixture(root)
    bad_config = ParentOverlapAuditConfig(
        **{
            **config.__dict__,
            "training_file": FileSpec(
                name=config.training_file.name,
                url=config.training_file.url,
                md5=config.training_file.md5,
                sha256="0" * 64,
            ),
        }
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_parent_overlap_audit(
            bad_config,
            root / "bad-output",
            training_path=training_path,
            source_archive_path=archive_path,
        )

    output = root / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_parent_overlap_audit(
            config,
            output,
            training_path=training_path,
            source_archive_path=archive_path,
        )

    payload = json.loads(
        Path(
            "case_studies/public_cobalt_oxide_tem_parent_overlap_audit/case_config.json"
        ).read_text()
    )
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown config"):
        ParentOverlapAuditConfig.from_mapping(payload)


def test_unsafe_zip_member_is_rejected(tmp_path: Path) -> None:
    training_path, archive_path, config = _fixture(tmp_path)
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../fixture_TEM_images.h5", b"not hdf5")
    unsafe_spec = ArchiveSpec(
        name=unsafe.name,
        url=config.source_archive.url,
        md5=_hash(unsafe, "md5"),
        sha256=_hash(unsafe, "sha256"),
        expected_members=("../fixture_TEM_images.h5",),
    )
    unsafe_config = ParentOverlapAuditConfig(
        **{
            **config.__dict__,
            "source_archive": unsafe_spec,
            "source_members": (
                SourceMemberSpec(
                    source_id="fixture", image_member="../fixture_TEM_images.h5"
                ),
            ),
        }
    )
    with pytest.raises(ValueError, match="unsafe ZIP member path"):
        unsafe_config.validate()


def test_overlap_audit_contains_no_model_training_or_physical_conversion() -> None:
    text = Path("src/mca/tem_parent_overlap_audit.py").read_text(encoding="utf-8")
    forbidden = (
        "from sklearn",
        "import torch",
        "import tensorflow",
        ".fit(",
        ".predict(",
        "nm_per_pixel",
        "particle_diameter_nm",
    )
    for token in forbidden:
        assert token not in text
    assert '"model_training_performed": False' in text
    assert '"segmentation_accuracy_computed": False' in text
    assert '"source_predicted_masks_used_as_ground_truth": False' in text
