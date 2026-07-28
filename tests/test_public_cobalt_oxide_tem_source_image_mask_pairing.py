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

from mca.tem_source_image_mask_pairing import (
    PAIRING_STATUS,
    PUBLIC_CASE_ID,
    PUBLIC_DOI,
    PUBLIC_IMAGE_ARCHIVE_SHA256,
    PUBLIC_MASK_ARCHIVE_SHA256,
    PUBLIC_PREFIXES,
    ArchiveSpec,
    PairSpec,
    SourceImageMaskPairingConfig,
    inspect_hdf5_pair,
    load_config,
    run_pairing_audit,
    validate_public_config,
)


def _hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_h5(
    path: Path,
    dataset_name: str,
    values: np.ndarray,
    *,
    add_attribute: bool = False,
) -> None:
    with h5py.File(path, "w") as handle:
        if add_attribute:
            handle.attrs["unexpected"] = "metadata"
        handle.create_dataset(dataset_name, data=values.astype(np.float64))


def _write_archive(
    path: Path,
    member: str,
    source: Path,
    *,
    extra_member: tuple[str, bytes, int | None] | None = None,
) -> ArchiveSpec:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, arcname=member)
        if extra_member is not None:
            name, data, unix_mode = extra_member
            info = zipfile.ZipInfo(name)
            if unix_mode is not None:
                info.create_system = 3
                info.external_attr = unix_mode << 16
            archive.writestr(info, data)
    return ArchiveSpec(
        name=path.name,
        url="https://example.invalid/archive.zip",
        md5=_hash(path, "md5"),
        sha256=_hash(path, "sha256"),
        expected_members=(member,),
    )


def _fixture_config(
    root: Path,
    image_values: np.ndarray,
    mask_values: np.ndarray,
    *,
    image_attribute: bool = False,
    mask_attribute: bool = False,
    image_extra: tuple[str, bytes, int | None] | None = None,
) -> tuple[Path, Path, SourceImageMaskPairingConfig]:
    image_h5 = root / "image.h5"
    mask_h5 = root / "mask.h5"
    _write_h5(image_h5, "images", image_values, add_attribute=image_attribute)
    _write_h5(mask_h5, "labels", mask_values, add_attribute=mask_attribute)
    image_member = "Fixture_TEM_images.h5"
    mask_member = "Fixture_segmented_images.h5"
    image_archive_path = root / "TEM_images.zip"
    mask_archive_path = root / "Segmented_images.zip"
    image_spec = _write_archive(
        image_archive_path, image_member, image_h5, extra_member=image_extra
    )
    mask_spec = _write_archive(mask_archive_path, mask_member, mask_h5)
    config = SourceImageMaskPairingConfig(
        case_id="fixture_source_image_mask_pairing",
        record_id=1,
        doi="10.0000/fixture",
        dataset_version="fixture",
        license="fixture-only",
        source_description="fixture source-asserted correspondence",
        paper_doi="10.0000/fixture-paper",
        paper_reported_four_k_pixel_size_pm=86.0,
        calibration_binding_status="not_bound",
        image_archive=image_spec,
        mask_archive=mask_spec,
        pairs=(
            PairSpec(
                pair_id="fixture",
                image_member=image_member,
                mask_member=mask_member,
            ),
        ),
        image_dataset_name="images",
        mask_dataset_name="labels",
        expected_shape=tuple(int(value) for value in image_values.shape),
        image_dtype="float64",
        mask_dtype="float64",
        image_mean_abs_tolerance=1e-10,
        image_std_abs_tolerance=1e-12,
        attributes_expected=False,
    )
    config.validate()
    return image_archive_path, mask_archive_path, config


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_tracked_public_config_is_exactly_pinned() -> None:
    config = load_config(
        "case_studies/public_cobalt_oxide_tem_source_image_mask_pairing/case_config.json"
    )
    validate_public_config(config)
    assert config.case_id == PUBLIC_CASE_ID
    assert config.doi == PUBLIC_DOI
    assert config.image_archive.sha256 == PUBLIC_IMAGE_ARCHIVE_SHA256
    assert config.mask_archive.sha256 == PUBLIC_MASK_ARCHIVE_SHA256
    assert len(config.pairs) == len(PUBLIC_PREFIXES) == 10


def test_fixture_audit_is_deterministic_and_preserves_pairing_boundary(
    tmp_path: Path,
) -> None:
    image_values = np.arange(2 * 8 * 9, dtype=np.float64).reshape(2, 8, 9)
    image_values = np.stack(
        [(frame - frame.mean()) / frame.std() for frame in image_values]
    )
    mask_values = np.zeros((2, 8, 9), dtype=np.float64)
    mask_values[0, 1:4, 2:6] = 1
    mask_values[1, 0:2, 0:2] = 1
    image_archive, mask_archive, config = _fixture_config(
        tmp_path, image_values, mask_values
    )

    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = run_pairing_audit(
        config,
        first,
        image_archive_path=image_archive,
        mask_archive_path=mask_archive,
    )
    run_pairing_audit(
        config,
        second,
        image_archive_path=image_archive,
        mask_archive_path=mask_archive,
    )

    assert _file_hashes(first) == _file_hashes(second)
    assert summary["result_counts"] == {
        "file_pair_count": 1,
        "frame_pair_count": 2,
    }
    assert summary["pairing"]["status"] == PAIRING_STATUS
    assert summary["pairing"]["independent_pairing_verification"] is False
    assert summary["literature_context"]["used_for_physical_conversion"] is False
    assert all(value is False for value in summary["processing"].values())
    assert summary["scientific_closeout"]["status"] == "Diagnostic"

    files = pd.read_csv(first / "tem_source_image_mask_file_pairs.csv")
    frames = pd.read_csv(first / "tem_source_image_mask_frame_pairs.csv")
    assert len(files) == 1
    assert len(frames) == 2
    assert files.loc[0, "same_shape"]
    assert files.loc[0, "same_frame_count"]
    assert frames["image_frame_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert frames["mask_frame_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert not frames["pixel_calibration_applied"].any()
    assert frames["mask_foreground_fraction"].tolist() == pytest.approx(
        [12 / 72, 4 / 72]
    )

    artifact_manifest = json.loads(
        (first / "source_image_mask_pairing_artifact_manifest.json").read_text()
    )
    assert artifact_manifest["case_id"] == config.case_id
    assert artifact_manifest["artifact_count"] == 4
    for artifact in artifact_manifest["artifacts"]:
        path = first / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_nonstandardized_source_image_fails_closed(tmp_path: Path) -> None:
    image = np.zeros((1, 5, 6), dtype=np.float64)
    mask = np.zeros_like(image)
    image_archive, mask_archive, config = _fixture_config(tmp_path, image, mask)
    with pytest.raises(ValueError, match="source image frame standard deviation drift"):
        run_pairing_audit(
            config,
            tmp_path / "nonstandard-output",
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )


def test_shape_nonbinary_and_attributes_fail_closed(tmp_path: Path) -> None:
    image = np.zeros((2, 5, 6), dtype=np.float64)
    mask = np.zeros((2, 5, 6), dtype=np.float64)
    root = tmp_path / "nonbinary"
    root.mkdir()
    mask[0, 1, 1] = 0.5
    image_archive, mask_archive, config = _fixture_config(root, image, mask)
    with pytest.raises(ValueError, match="non-binary mask value"):
        run_pairing_audit(
            config,
            tmp_path / "nonbinary-output",
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )

    root = tmp_path / "attribute"
    root.mkdir()
    image_archive, mask_archive, config = _fixture_config(
        root,
        image,
        np.zeros_like(image),
        image_attribute=True,
    )
    with pytest.raises(ValueError, match="root attributes changed"):
        run_pairing_audit(
            config,
            tmp_path / "attribute-output",
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )

    image_path = tmp_path / "shape-image.h5"
    mask_path = tmp_path / "shape-mask.h5"
    _write_h5(image_path, "images", image)
    _write_h5(mask_path, "labels", np.zeros((1, 5, 6)))
    with pytest.raises(ValueError, match="shape"):
        inspect_hdf5_pair(
            image_path,
            mask_path,
            config=config,
            pair=config.pairs[0],
            image_member_sha256="0" * 64,
            mask_member_sha256="1" * 64,
        )


def test_unsafe_archive_and_nonempty_output_are_rejected(tmp_path: Path) -> None:
    image = np.zeros((1, 4, 4), dtype=np.float64)
    mask = np.zeros_like(image)
    traversal_root = tmp_path / "traversal"
    traversal_root.mkdir()
    image_archive, mask_archive, config = _fixture_config(
        traversal_root,
        image,
        mask,
        image_extra=("../escape.txt", b"no", None),
    )
    with pytest.raises(ValueError, match="unsafe archive path"):
        run_pairing_audit(
            config,
            tmp_path / "traversal-output",
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    image_archive, mask_archive, config = _fixture_config(
        symlink_root,
        image,
        mask,
        image_extra=("link", b"target", stat.S_IFLNK | 0o777),
    )
    with pytest.raises(ValueError, match="symlink rejected"):
        run_pairing_audit(
            config,
            tmp_path / "symlink-output",
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )

    clean_root = tmp_path / "clean"
    clean_root.mkdir()
    image_archive, mask_archive, config = _fixture_config(clean_root, image, mask)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_pairing_audit(
            config,
            output,
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_hash_drift_and_unknown_config_fields_are_rejected(tmp_path: Path) -> None:
    image = np.zeros((1, 4, 4), dtype=np.float64)
    mask = np.zeros_like(image)
    image_archive, mask_archive, config = _fixture_config(tmp_path, image, mask)
    bad_image = ArchiveSpec(
        name=config.image_archive.name,
        url=config.image_archive.url,
        md5=config.image_archive.md5,
        sha256="0" * 64,
        expected_members=config.image_archive.expected_members,
    )
    bad_config = SourceImageMaskPairingConfig(
        **{**config.__dict__, "image_archive": bad_image}
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_pairing_audit(
            bad_config,
            tmp_path / "hash-output",
            image_archive_path=image_archive,
            mask_archive_path=mask_archive,
        )

    payload = json.loads(
        Path(
            "case_studies/public_cobalt_oxide_tem_source_image_mask_pairing/case_config.json"
        ).read_text()
    )
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown config"):
        SourceImageMaskPairingConfig.from_mapping(payload)


def test_pairing_audit_contains_no_model_or_physical_conversion() -> None:
    text = Path("src/mca/tem_source_image_mask_pairing.py").read_text(encoding="utf-8")
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
    assert '"model_inference_performed": False' in text
    assert '"physical_size_computed": False' in text
