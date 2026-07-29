from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from mca.tem_parent_similarity_review import (
    EXCLUSION_STATUS,
    STRONG_STATUS,
    ArchiveSpec,
    FileSpec,
    SimilarityReviewConfig,
    inspect_similarity_pair,
    load_config,
    run_similarity_review,
    validate_public_config,
)


def _hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _standardize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return (values - values.mean()) / values.std()


def _build_fixture(root: Path, *, unrelated: bool = False, nonfinite: bool = False):
    rng = np.random.default_rng(42)
    raw = rng.normal(size=(8, 8)) + np.linspace(0, 1, 8)[None, :]
    parents = [rng.normal(size=(8, 8)) for _ in range(2)]
    parents[1] = raw
    patches = []
    for parent in parents:
        for row in range(2):
            for col in range(2):
                patches.append(_standardize(parent[row*4:(row+1)*4, col*4:(col+1)*4]))
    training_path = root / "training_images.h5"
    with h5py.File(training_path, "w") as handle:
        handle.create_dataset("images", data=np.asarray(patches, dtype=np.float64))

    source_raw = rng.normal(size=(8, 8)) if unrelated else raw + 0.01 * rng.normal(size=(8, 8))
    frame = _standardize(source_raw)
    if nonfinite:
        frame[0, 0] = np.nan
    source_member = root / "fixture_TEM_images.h5"
    with h5py.File(source_member, "w") as handle:
        handle.create_dataset("images", data=np.asarray([frame], dtype=np.float64))
    archive_path = root / "TEM_images.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("__MACOSX/._fixture_TEM_images.h5", b"metadata")
        archive.write(source_member, arcname=source_member.name)

    config = SimilarityReviewConfig(
        case_id="fixture_parent_similarity_review",
        record_id=1,
        doi="10.0000/fixture",
        dataset_version="fixture",
        license="fixture-only",
        source_description="fixture",
        training_file=FileSpec(training_path.name, "https://example.invalid/training", _hash(training_path, "md5"), _hash(training_path, "sha256")),
        source_archive=ArchiveSpec(archive_path.name, "https://example.invalid/archive", _hash(archive_path, "md5"), _hash(archive_path, "sha256"), (source_member.name,)),
        source_id="fixture",
        source_member=source_member.name,
        frame_index=0,
        candidate_parent_index=1,
        training_dataset_name="images",
        source_dataset_name="images",
        training_shape=(8, 4, 4),
        source_member_shape=(1, 8, 8),
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
        block_size=2,
        strong_global_ncc_threshold=0.99,
        strong_median_tile_ncc_threshold=0.99,
        strong_minimum_tile_ncc_threshold=0.95,
        independent_label_status="not_independent",
    )
    config.validate()
    return training_path, archive_path, source_member, config


def test_public_config_is_pinned() -> None:
    config = load_config("case_studies/public_cobalt_oxide_tem_parent_similarity_review/case_config.json")
    validate_public_config(config)
    assert config.frame_index == 0
    assert config.candidate_parent_index == 3


def test_noisy_same_parent_is_strong_but_not_authoritative(tmp_path: Path) -> None:
    training_path, archive_path, _, config = _build_fixture(tmp_path)
    summary = run_similarity_review(
        config,
        tmp_path / "output",
        training_path=training_path,
        source_archive_path=archive_path,
    )
    assert summary["relationship_assessment"]["status"] == STRONG_STATUS
    assert summary["relationship_assessment"]["conservative_external_candidate_pool_action"] == EXCLUSION_STATUS
    assert not summary["relationship_assessment"]["authoritative_parent_identity_confirmed"]
    assert not summary["external_validation_readiness"]["independent_external_validation_candidate"]
    aggregate = summary["aggregate_similarity"]
    assert aggregate["exact_quantized_tile_hash_match_count"] == 0
    assert aggregate["strong_content_correspondence"]
    assert aggregate["minimum_tile_pixel_ncc"] >= config.strong_minimum_tile_ncc_threshold
    tiles = pd.read_csv(tmp_path / "output" / "tem_parent_similarity_review_tiles.csv")
    assert len(tiles) == 4
    assert tiles["training_patch_index"].tolist() == [4, 5, 6, 7]
    assert not tiles["exact_quantized_hash_match"].any()
    manifest = json.loads((tmp_path / "output" / "parent_similarity_review_artifact_manifest.json").read_text())
    assert manifest["artifact_count"] == 3


def test_unrelated_pair_does_not_trigger_exclusion(tmp_path: Path) -> None:
    training_path, _, source_member, config = _build_fixture(tmp_path, unrelated=True)
    result = inspect_similarity_pair(training_path, source_member, config=config)
    assert not result["aggregate"]["strong_content_correspondence"]


def test_nonfinite_hash_and_output_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "nonfinite"
    root.mkdir()
    training_path, archive_path, _, config = _build_fixture(root, nonfinite=True)
    with pytest.raises(ValueError, match="non-finite"):
        run_similarity_review(config, root / "output", training_path=training_path, source_archive_path=archive_path)

    root = tmp_path / "hash"
    root.mkdir()
    training_path, archive_path, _, config = _build_fixture(root)
    bad = SimilarityReviewConfig(**{**config.__dict__, "training_file": FileSpec(config.training_file.name, config.training_file.url, config.training_file.md5, "0" * 64)})
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_similarity_review(bad, root / "bad", training_path=training_path, source_archive_path=archive_path)

    existing = root / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("keep")
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_similarity_review(config, existing, training_path=training_path, source_archive_path=archive_path)


def test_module_contains_no_model_or_physical_measurement() -> None:
    text = Path("src/mca/tem_parent_similarity_review.py").read_text(encoding="utf-8")
    for token in ("import torch", "import tensorflow", ".fit(", ".predict(", "nm_per_pixel", "particle_diameter_nm"):
        assert token not in text
    assert '"model_training_performed": False' in text
    assert '"segmentation_accuracy_computed": False' in text
