"""Focused similarity review for one unresolved TEM source-frame/parent pair.

This module quantifies content correspondence under the pinned aligned tiling and
per-tile standardization path. It does not establish authoritative parent identity,
train a model, evaluate segmentation accuracy, or create an external validation set.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import h5py
import numpy as np

from . import __version__

PUBLIC_CASE_ID = "public_cobalt_oxide_tem_parent_similarity_review"
PUBLIC_DOI = "10.5281/zenodo.14927582"
PUBLIC_DATASET_VERSION = "v1"
PUBLIC_LICENSE = "CC-BY-4.0"
PUBLIC_TRAINING_NAME = "training_images.h5"
PUBLIC_TRAINING_MD5 = "caac404a7ea2c65b2403aee5728a70eb"
PUBLIC_TRAINING_SHA256 = "e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926"
PUBLIC_ARCHIVE_NAME = "TEM_images.zip"
PUBLIC_ARCHIVE_MD5 = "d1e991346d07b8a112c4b6dbfd8367ba"
PUBLIC_ARCHIVE_SHA256 = "a9e4618f697205bf8560ab14bc5e313d4011b51aaa6dbf8a5c62ddc22bc558d8"
PUBLIC_SOURCE_MEMBER = "Co0_7_TEM_images.h5"
PUBLIC_SOURCE_ID = "co0_7"
PUBLIC_FRAME_INDEX = 0
PUBLIC_PARENT_INDEX = 3

STRONG_STATUS = "strong_content_correspondence_parent_identity_unresolved"
INSUFFICIENT_STATUS = "content_similarity_insufficient_for_parent_exclusion"
EXCLUSION_STATUS = "exclude_from_external_candidate_pool_as_conservative_leakage_control"
NO_EXCLUSION_STATUS = "retain_as_image_only_candidate_with_identity_uncertainty"
INDEPENDENT_LABEL_STATUS = "source_predicted_masks_not_independent_validation_labels"

LIMITATIONS = (
    "Candidate parent 3 is reconstructed from contiguous training-patch order rather than source-issued immutable parent metadata.",
    "High numerical similarity can support conservative leakage exclusion but cannot prove acquisition identity or recover missing provenance.",
    "The selected public source masks are model-predicted outputs, not independent expert ground truth.",
    "Only the pinned aligned orientation, tile grid, and per-tile standardization path are quantified; unknown resampling, filtering, or unpublished processing cannot be fully reconstructed.",
    "No model training, model inference, segmentation metric, pixel calibration, physical measurement, causal claim, optimization, or engineering-release decision is performed.",
)


@dataclass(frozen=True)
class FileSpec:
    name: str
    url: str
    md5: str
    sha256: str


@dataclass(frozen=True)
class ArchiveSpec:
    name: str
    url: str
    md5: str
    sha256: str
    expected_data_members: tuple[str, ...]


@dataclass(frozen=True)
class SimilarityReviewConfig:
    case_id: str
    record_id: int
    doi: str
    dataset_version: str
    license: str
    source_description: str
    training_file: FileSpec
    source_archive: ArchiveSpec
    source_id: str
    source_member: str
    frame_index: int
    candidate_parent_index: int
    training_dataset_name: str
    source_dataset_name: str
    training_shape: tuple[int, int, int]
    source_member_shape: tuple[int, int, int]
    dtype: str
    attributes_expected: bool
    parent_count: int
    grid_rows: int
    grid_columns: int
    tile_height: int
    tile_width: int
    image_mean_abs_tolerance: float
    image_std_abs_tolerance: float
    quantization_decimals: int
    block_size: int
    strong_global_ncc_threshold: float
    strong_median_tile_ncc_threshold: float
    strong_minimum_tile_ncc_threshold: float
    independent_label_status: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SimilarityReviewConfig":
        _reject_unknown(
            payload,
            {
                "case_id",
                "source",
                "training_file",
                "source_archive",
                "review_target",
                "hdf5_contract",
                "parent_reconstruction",
                "similarity_contract",
                "label_contract",
            },
            "config",
        )
        source = _mapping(payload, "source")
        target = _mapping(payload, "review_target")
        hdf5_contract = _mapping(payload, "hdf5_contract")
        parent = _mapping(payload, "parent_reconstruction")
        similarity = _mapping(payload, "similarity_contract")
        labels = _mapping(payload, "label_contract")
        _reject_unknown(source, {"record_id", "doi", "dataset_version", "license", "source_description"}, "source")
        _reject_unknown(target, {"source_id", "source_member", "frame_index", "candidate_parent_index"}, "review_target")
        _reject_unknown(
            hdf5_contract,
            {"training_dataset_name", "source_dataset_name", "training_shape", "source_member_shape", "dtype", "attributes_expected"},
            "hdf5_contract",
        )
        _reject_unknown(parent, {"parent_count", "grid_rows", "grid_columns", "tile_height", "tile_width"}, "parent_reconstruction")
        _reject_unknown(
            similarity,
            {
                "image_mean_abs_tolerance",
                "image_std_abs_tolerance",
                "quantization_decimals",
                "block_size",
                "strong_global_ncc_threshold",
                "strong_median_tile_ncc_threshold",
                "strong_minimum_tile_ncc_threshold",
            },
            "similarity_contract",
        )
        _reject_unknown(labels, {"independent_label_status"}, "label_contract")
        training_shape = _int_tuple(hdf5_contract, "training_shape", 3)
        source_shape = _int_tuple(hdf5_contract, "source_member_shape", 3)
        config = cls(
            case_id=_required_text(payload, "case_id"),
            record_id=int(source["record_id"]),
            doi=_required_text(source, "doi"),
            dataset_version=_required_text(source, "dataset_version"),
            license=_required_text(source, "license"),
            source_description=_required_text(source, "source_description"),
            training_file=_file_spec(_mapping(payload, "training_file"), "training_file"),
            source_archive=_archive_spec(_mapping(payload, "source_archive"), "source_archive"),
            source_id=_required_text(target, "source_id"),
            source_member=_required_text(target, "source_member"),
            frame_index=int(target["frame_index"]),
            candidate_parent_index=int(target["candidate_parent_index"]),
            training_dataset_name=_required_text(hdf5_contract, "training_dataset_name"),
            source_dataset_name=_required_text(hdf5_contract, "source_dataset_name"),
            training_shape=training_shape,
            source_member_shape=source_shape,
            dtype=_required_text(hdf5_contract, "dtype"),
            attributes_expected=_required_bool(hdf5_contract, "attributes_expected"),
            parent_count=int(parent["parent_count"]),
            grid_rows=int(parent["grid_rows"]),
            grid_columns=int(parent["grid_columns"]),
            tile_height=int(parent["tile_height"]),
            tile_width=int(parent["tile_width"]),
            image_mean_abs_tolerance=float(similarity["image_mean_abs_tolerance"]),
            image_std_abs_tolerance=float(similarity["image_std_abs_tolerance"]),
            quantization_decimals=int(similarity["quantization_decimals"]),
            block_size=int(similarity["block_size"]),
            strong_global_ncc_threshold=float(similarity["strong_global_ncc_threshold"]),
            strong_median_tile_ncc_threshold=float(similarity["strong_median_tile_ncc_threshold"]),
            strong_minimum_tile_ncc_threshold=float(similarity["strong_minimum_tile_ncc_threshold"]),
            independent_label_status=_required_text(labels, "independent_label_status"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.case_id):
            raise ValueError("case_id must use lowercase letters, digits, and underscores.")
        if self.attributes_expected:
            raise ValueError("this audit supports only the pinned no-attribute HDF5 contract.")
        if self.parent_count <= 0 or not 0 <= self.candidate_parent_index < self.parent_count:
            raise ValueError("candidate parent index is outside the configured parent count.")
        tiles_per_parent = self.grid_rows * self.grid_columns
        if tiles_per_parent <= 0 or self.parent_count * tiles_per_parent != self.training_shape[0]:
            raise ValueError("parent reconstruction must cover every training patch exactly once.")
        if self.source_member_shape[1:] != (
            self.grid_rows * self.tile_height,
            self.grid_columns * self.tile_width,
        ):
            raise ValueError("source frame shape does not equal configured tile grid.")
        if self.training_shape[1:] != (self.tile_height, self.tile_width):
            raise ValueError("training patch shape does not equal configured tile dimensions.")
        if not 0 <= self.frame_index < self.source_member_shape[0]:
            raise ValueError("frame_index is outside source_member_shape.")
        if self.quantization_decimals < 0 or self.quantization_decimals > 15:
            raise ValueError("quantization_decimals must be between 0 and 15.")
        if self.block_size <= 0 or self.tile_height % self.block_size or self.tile_width % self.block_size:
            raise ValueError("block_size must divide both tile dimensions.")
        thresholds = (
            self.strong_global_ncc_threshold,
            self.strong_median_tile_ncc_threshold,
            self.strong_minimum_tile_ncc_threshold,
        )
        if any(not -1.0 <= value <= 1.0 for value in thresholds):
            raise ValueError("NCC thresholds must be between -1 and 1.")
        if self.image_mean_abs_tolerance <= 0 or self.image_std_abs_tolerance <= 0:
            raise ValueError("standardization tolerances must be positive.")
        _validate_member_name(self.source_member)


def load_config(path: str | Path) -> SimilarityReviewConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("case config must contain a JSON object.")
    return SimilarityReviewConfig.from_mapping(payload)


def validate_public_config(config: SimilarityReviewConfig) -> None:
    expected = {
        "case_id": PUBLIC_CASE_ID,
        "record_id": 14927582,
        "doi": PUBLIC_DOI,
        "dataset_version": PUBLIC_DATASET_VERSION,
        "license": PUBLIC_LICENSE,
        "source_id": PUBLIC_SOURCE_ID,
        "source_member": PUBLIC_SOURCE_MEMBER,
        "frame_index": PUBLIC_FRAME_INDEX,
        "candidate_parent_index": PUBLIC_PARENT_INDEX,
        "training_dataset_name": "images",
        "source_dataset_name": "images",
        "training_shape": (256, 512, 512),
        "source_member_shape": (5, 4096, 4096),
        "dtype": "float64",
        "attributes_expected": False,
        "parent_count": 4,
        "grid_rows": 8,
        "grid_columns": 8,
        "tile_height": 512,
        "tile_width": 512,
        "image_mean_abs_tolerance": 1e-10,
        "image_std_abs_tolerance": 1e-12,
        "quantization_decimals": 9,
        "block_size": 16,
        "strong_global_ncc_threshold": 0.995,
        "strong_median_tile_ncc_threshold": 0.995,
        "strong_minimum_tile_ncc_threshold": 0.98,
        "independent_label_status": INDEPENDENT_LABEL_STATUS,
    }
    for field, value in expected.items():
        actual = getattr(config, field)
        if actual != value:
            raise ValueError(f"public config mismatch for {field}: {actual!r} != {value!r}")
    expected_training = FileSpec(
        PUBLIC_TRAINING_NAME,
        "https://zenodo.org/records/14927582/files/training_images.h5?download=1",
        PUBLIC_TRAINING_MD5,
        PUBLIC_TRAINING_SHA256,
    )
    if config.training_file != expected_training:
        raise ValueError("public training file contract changed.")
    if config.source_archive.name != PUBLIC_ARCHIVE_NAME:
        raise ValueError("public archive name changed.")
    if config.source_archive.url != "https://zenodo.org/records/14927582/files/TEM_images.zip?download=1":
        raise ValueError("public archive URL changed.")
    if config.source_archive.md5 != PUBLIC_ARCHIVE_MD5 or config.source_archive.sha256 != PUBLIC_ARCHIVE_SHA256:
        raise ValueError("public archive digest contract changed.")
    if PUBLIC_SOURCE_MEMBER not in config.source_archive.expected_data_members:
        raise ValueError("review source member is absent from expected_data_members.")


def run_similarity_review(
    config: SimilarityReviewConfig,
    output_dir: str | Path,
    *,
    training_path: str | Path | None = None,
    source_archive_path: str | Path | None = None,
) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="mca-tem-parent-similarity-") as temp_name:
            temp = Path(temp_name)
            training, training_mode = _acquire(config.training_file, training_path, temp / config.training_file.name)
            archive, archive_mode = _acquire(config.source_archive, source_archive_path, temp / config.source_archive.name)
            training_hashes = _verify_hashes(training, config.training_file)
            archive_hashes = _verify_hashes(archive, config.source_archive)
            archive_inventory = _validate_zip(archive, config.source_archive.expected_data_members)
            extracted = temp / config.source_member
            with zipfile.ZipFile(archive) as zipped:
                source_member_sha256 = _extract_member(zipped, config.source_member, extracted)
            result = inspect_similarity_pair(training, extracted, config=config)

        tile_path = output / "tem_parent_similarity_review_tiles.csv"
        summary_path = output / "parent_similarity_review_summary.json"
        report_path = output / "parent_similarity_review_report.md"
        manifest_path = output / "parent_similarity_review_artifact_manifest.json"
        _write_csv(tile_path, result["tile_rows"], TILE_COLUMNS)
        aggregate = result["aggregate"]
        strong = bool(aggregate["strong_content_correspondence"])
        relationship_status = STRONG_STATUS if strong else INSUFFICIENT_STATUS
        exclusion_status = EXCLUSION_STATUS if strong else NO_EXCLUSION_STATUS
        summary = {
            "schema_version": "1.0",
            "case_id": config.case_id,
            "software_version": __version__,
            "source": {
                "repository": "Zenodo",
                "record_id": config.record_id,
                "doi": config.doi,
                "dataset_version": config.dataset_version,
                "license": config.license,
                "source_description": config.source_description,
                "training_images": {"name": config.training_file.name, **training_hashes, "acquisition_mode": training_mode},
                "source_image_archive": {"name": config.source_archive.name, **archive_hashes, "acquisition_mode": archive_mode},
                "source_member": config.source_member,
                "source_member_sha256": source_member_sha256,
            },
            "review_target": {
                "source_id": config.source_id,
                "source_frame_id": f"{config.source_id}:frame-{config.frame_index}",
                "frame_index": config.frame_index,
                "candidate_parent_index": config.candidate_parent_index,
                "candidate_parent_identity_status": "diagnostic_reconstruction_not_authoritative_mapping",
            },
            "comparison_contract": {
                "aligned_grid": [config.grid_rows, config.grid_columns],
                "tile_shape": [config.tile_height, config.tile_width],
                "per_tile_standardization": True,
                "quantization_decimals": config.quantization_decimals,
                "block_size": config.block_size,
                "strong_global_ncc_threshold": config.strong_global_ncc_threshold,
                "strong_median_tile_ncc_threshold": config.strong_median_tile_ncc_threshold,
                "strong_minimum_tile_ncc_threshold": config.strong_minimum_tile_ncc_threshold,
            },
            "archive_inventory": {**archive_inventory, "review_member_crc_verified_during_stream_extraction": True},
            "aggregate_similarity": aggregate,
            "relationship_assessment": {
                "status": relationship_status,
                "authoritative_parent_identity_confirmed": False,
                "conservative_external_candidate_pool_action": exclusion_status,
                "rationale": (
                    "Strong correspondence supports conservative leakage exclusion, but missing source-issued mapping prevents parent identity confirmation."
                    if strong
                    else "The predeclared numerical thresholds were not met; identity remains unresolved and the frame remains image-only."
                ),
            },
            "external_validation_readiness": {
                "independent_label_status": config.independent_label_status,
                "source_masks_are_independent_ground_truth": False,
                "independent_external_validation_candidate": False,
                "reason": "independent expert labels and authoritative parent-disjoint provenance are absent",
            },
            "processing": {
                "tile_restandardization_for_identity_comparison_only": True,
                "source_values_written_to_outputs": False,
                "denoising_performed": False,
                "geometric_registration_performed": False,
                "augmentation_performed": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_accuracy_computed": False,
                "source_predicted_masks_used_as_ground_truth": False,
                "pixel_calibration_applied": False,
                "physical_size_computed": False,
            },
            "scientific_closeout": {
                "status": "Diagnostic",
                "result": relationship_status,
                "strongest_evidence": (
                    f"All {len(result['tile_rows'])} aligned tiles were compared at pixel and block-signature levels after the pinned per-tile standardization path."
                ),
                "primary_limitation": "The candidate parent grouping is reconstructed and no immutable acquisition mapping is embedded in the public files.",
                "evidence_that_would_change_conclusion": "A source-issued immutable mapping from training patches to acquisition/frame identity and independently labeled parent-disjoint images.",
                "suitable_for": [
                    "conservative data-leakage exclusion",
                    "content-similarity diagnostics",
                    "external-candidate inventory triage",
                ],
                "not_suitable_for": [
                    "authoritative parent identity",
                    "independent segmentation performance claims",
                    "physical measurements or engineering release",
                ],
            },
            "limitations": list(LIMITATIONS),
        }
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary), encoding="utf-8")
        manifest = _build_manifest(output, [tile_path, summary_path, report_path], config.case_id, training_hashes["sha256"], archive_hashes["sha256"])
        _write_json(manifest_path, manifest)
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def inspect_similarity_pair(
    training_path: str | Path,
    source_member_path: str | Path,
    *,
    config: SimilarityReviewConfig,
) -> dict[str, Any]:
    tile_rows: list[dict[str, Any]] = []
    pixel_products = 0.0
    pixel_difference_sq = 0.0
    pixel_abs_difference = 0.0
    pixel_count = 0
    source_block_parts: list[np.ndarray] = []
    training_block_parts: list[np.ndarray] = []
    exact_count = 0
    tiles_per_parent = config.grid_rows * config.grid_columns
    parent_start = config.candidate_parent_index * tiles_per_parent

    with h5py.File(training_path, "r") as training_h5, h5py.File(source_member_path, "r") as source_h5:
        training = _validate_hdf5(training_h5, config.training_dataset_name, config.training_shape, config.dtype, Path(training_path).name)
        source = _validate_hdf5(source_h5, config.source_dataset_name, config.source_member_shape, config.dtype, config.source_member)
        frame = np.asarray(source[config.frame_index], dtype=np.float64)
        _validate_finite(frame, "source frame")
        _validate_standardized(frame, config, "source frame")
        for row in range(config.grid_rows):
            for column in range(config.grid_columns):
                tile_index = row * config.grid_columns + column
                patch_index = parent_start + tile_index
                training_tile = np.asarray(training[patch_index], dtype=np.float64)
                _validate_finite(training_tile, f"training patch {patch_index}")
                _validate_standardized(training_tile, config, f"training patch {patch_index}")
                source_tile = frame[
                    row * config.tile_height : (row + 1) * config.tile_height,
                    column * config.tile_width : (column + 1) * config.tile_width,
                ]
                source_tile = _standardize(source_tile)
                difference = source_tile - training_tile
                ncc = _ncc(source_tile, training_tile)
                rmse = float(np.sqrt(np.mean(difference * difference)))
                mae = float(np.mean(np.abs(difference)))
                max_abs = float(np.max(np.abs(difference)))
                source_block = _block_signature(source_tile, config.block_size)
                training_block = _block_signature(training_tile, config.block_size)
                block_ncc = _ncc(source_block, training_block)
                block_rmse = float(np.sqrt(np.mean((source_block - training_block) ** 2)))
                exact = _array_hash(source_tile, config.quantization_decimals) == _array_hash(training_tile, config.quantization_decimals)
                exact_count += int(exact)
                pixel_products += float(np.sum(source_tile * training_tile, dtype=np.float64))
                pixel_difference_sq += float(np.sum(difference * difference, dtype=np.float64))
                pixel_abs_difference += float(np.sum(np.abs(difference), dtype=np.float64))
                pixel_count += int(source_tile.size)
                source_block_parts.append(source_block)
                training_block_parts.append(training_block)
                tile_rows.append(
                    {
                        "source_id": config.source_id,
                        "frame_index": config.frame_index,
                        "source_frame_id": f"{config.source_id}:frame-{config.frame_index}",
                        "candidate_parent_index": config.candidate_parent_index,
                        "tile_index": tile_index,
                        "tile_row": row,
                        "tile_column": column,
                        "training_patch_index": patch_index,
                        "exact_quantized_hash_match": exact,
                        "pixel_ncc": ncc,
                        "pixel_rmse": rmse,
                        "pixel_mae": mae,
                        "pixel_max_abs_difference": max_abs,
                        "block_signature_ncc": block_ncc,
                        "block_signature_rmse": block_rmse,
                    }
                )

    pixel_ncc_values = np.asarray([float(item["pixel_ncc"]) for item in tile_rows])
    pixel_rmse_values = np.asarray([float(item["pixel_rmse"]) for item in tile_rows])
    source_blocks = np.concatenate(source_block_parts)
    training_blocks = np.concatenate(training_block_parts)
    global_pixel_ncc = pixel_products / pixel_count
    global_pixel_rmse = math.sqrt(pixel_difference_sq / pixel_count)
    global_pixel_mae = pixel_abs_difference / pixel_count
    global_block_ncc = _ncc(source_blocks, training_blocks)
    global_block_rmse = float(np.sqrt(np.mean((source_blocks - training_blocks) ** 2)))
    median_ncc = float(np.median(pixel_ncc_values))
    minimum_ncc = float(np.min(pixel_ncc_values))
    strong = (
        global_pixel_ncc >= config.strong_global_ncc_threshold
        and median_ncc >= config.strong_median_tile_ncc_threshold
        and minimum_ncc >= config.strong_minimum_tile_ncc_threshold
    )
    aggregate = {
        "tile_count": len(tile_rows),
        "exact_quantized_tile_hash_match_count": exact_count,
        "exact_quantized_tile_hash_match_fraction": exact_count / len(tile_rows),
        "global_pixel_ncc": float(global_pixel_ncc),
        "global_pixel_rmse": float(global_pixel_rmse),
        "global_pixel_mae": float(global_pixel_mae),
        "global_block_signature_ncc": float(global_block_ncc),
        "global_block_signature_rmse": float(global_block_rmse),
        "minimum_tile_pixel_ncc": minimum_ncc,
        "median_tile_pixel_ncc": median_ncc,
        "mean_tile_pixel_ncc": float(np.mean(pixel_ncc_values)),
        "maximum_tile_pixel_ncc": float(np.max(pixel_ncc_values)),
        "tile_count_ncc_at_least_0_98": int(np.sum(pixel_ncc_values >= 0.98)),
        "tile_count_ncc_at_least_0_99": int(np.sum(pixel_ncc_values >= 0.99)),
        "tile_count_ncc_at_least_0_995": int(np.sum(pixel_ncc_values >= 0.995)),
        "tile_count_ncc_at_least_0_999": int(np.sum(pixel_ncc_values >= 0.999)),
        "median_tile_pixel_rmse": float(np.median(pixel_rmse_values)),
        "maximum_tile_pixel_rmse": float(np.max(pixel_rmse_values)),
        "strong_content_correspondence": bool(strong),
    }
    return {"tile_rows": tile_rows, "aggregate": aggregate}


def _validate_hdf5(handle: h5py.File, dataset_name: str, expected_shape: tuple[int, int, int], expected_dtype: str, label: str) -> h5py.Dataset:
    if list(handle.keys()) != [dataset_name]:
        raise ValueError(f"{label} must contain only dataset {dataset_name!r}.")
    if len(handle.attrs) != 0:
        raise ValueError(f"{label} root attributes changed from the pinned contract.")
    dataset = handle[dataset_name]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"{label} dataset is not HDF5 data.")
    if tuple(dataset.shape) != expected_shape:
        raise ValueError(f"{label} shape {tuple(dataset.shape)} != {expected_shape}.")
    if str(dataset.dtype) != expected_dtype:
        raise ValueError(f"{label} dtype {dataset.dtype} != {expected_dtype}.")
    if len(dataset.attrs) != 0:
        raise ValueError(f"{label} dataset attributes changed from the pinned contract.")
    return dataset


def _standardize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    mean = float(values.mean())
    std = float(values.std())
    if not math.isfinite(std) or std <= 0:
        raise ValueError("cannot standardize constant or non-finite values.")
    return (values - mean) / std


def _validate_standardized(values: np.ndarray, config: SimilarityReviewConfig, label: str) -> None:
    mean = float(values.mean())
    std = float(values.std())
    if abs(mean) > config.image_mean_abs_tolerance:
        raise ValueError(f"standardized mean drift in {label}: {mean}")
    if abs(std - 1.0) > config.image_std_abs_tolerance:
        raise ValueError(f"standardized standard deviation drift in {label}: {std}")


def _validate_finite(values: np.ndarray, label: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"non-finite value in {label}.")


def _array_hash(values: np.ndarray, decimals: int) -> str:
    rounded = np.round(np.asarray(values, dtype=np.float64), decimals=decimals)
    return hashlib.sha256(np.ascontiguousarray(rounded).tobytes()).hexdigest()


def _block_signature(values: np.ndarray, block: int) -> np.ndarray:
    height, width = values.shape
    return values.reshape(height // block, block, width // block, block).mean(axis=(1, 3)).ravel()


def _ncc(left: np.ndarray, right: np.ndarray) -> float:
    left_flat = np.asarray(left, dtype=np.float64).ravel()
    right_flat = np.asarray(right, dtype=np.float64).ravel()
    left_centered = left_flat - left_flat.mean()
    right_centered = right_flat - right_flat.mean()
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    if denominator == 0:
        return 1.0 if np.array_equal(left_flat, right_flat) else 0.0
    return max(-1.0, min(1.0, float(np.dot(left_centered, right_centered) / denominator)))


def _acquire(spec: FileSpec | ArchiveSpec, supplied: str | Path | None, target: Path) -> tuple[Path, str]:
    if supplied is not None:
        path = Path(supplied)
        if path.is_symlink():
            raise ValueError(f"local input must not be a symlink: {path}")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path, "local_exact_file"
    request = urllib.request.Request(spec.url, headers={"User-Agent": "materials-characterization-analyzer"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)
    return target, "runtime_download"


def _verify_hashes(path: Path, spec: FileSpec | ArchiveSpec) -> dict[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    result = {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}
    if result["md5"] != spec.md5:
        raise ValueError(f"MD5 mismatch for {spec.name}.")
    if result["sha256"] != spec.sha256:
        raise ValueError(f"SHA-256 mismatch for {spec.name}.")
    return result


def _validate_zip(path: Path, expected_members: tuple[str, ...]) -> dict[str, Any]:
    expected = set(expected_members)
    data_members: set[str] = set()
    metadata_members: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            _validate_zip_info(info)
            if info.is_dir():
                continue
            normalized = info.filename.replace("\\", "/")
            pure = PurePosixPath(normalized)
            if normalized.startswith("__MACOSX/") or pure.name.startswith("._"):
                metadata_members.append(normalized)
            else:
                data_members.add(normalized)
    if data_members != expected:
        raise ValueError(
            "ZIP data-member inventory changed: "
            f"missing={sorted(expected-data_members)}, unexpected={sorted(data_members-expected)}"
        )
    return {
        "data_member_count": len(data_members),
        "data_members": sorted(data_members),
        "metadata_member_count": len(metadata_members),
        "metadata_members": sorted(metadata_members),
        "safe_paths_verified": True,
        "symlinks_absent": True,
        "encrypted_entries_absent": True,
    }


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    normalized = info.filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError(f"unsafe ZIP member path: {info.filename}")
    if info.flag_bits & 0x1:
        raise ValueError(f"encrypted ZIP member is unsupported: {info.filename}")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"ZIP member must not be a symlink: {info.filename}")


def _extract_member(archive: zipfile.ZipFile, member: str, target: Path) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as source, target.open("wb") as output:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty.")
    else:
        output.mkdir(parents=True)
    return output


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_manifest(output: Path, artifacts: list[Path], case_id: str, training_sha256: str, archive_sha256: str) -> dict[str, Any]:
    records = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in artifacts
    ]
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "software_version": __version__,
        "source_sha256": {"training_images": training_sha256, "source_image_archive": archive_sha256},
        "artifact_count": len(records),
        "artifacts": records,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    aggregate = summary["aggregate_similarity"]
    assessment = summary["relationship_assessment"]
    lines = [
        "# Public Cobalt Oxide TEM Parent Similarity Review",
        "",
        "**Evidence level:** Diagnostic",
        "",
        f"**Result:** `{assessment['status']}`",
        "",
        "## Target",
        "",
        f"- Source frame: `{summary['review_target']['source_frame_id']}`",
        f"- Candidate parent: {summary['review_target']['candidate_parent_index']}",
        "",
        "## Similarity",
        "",
        f"- Global pixel NCC: {aggregate['global_pixel_ncc']}",
        f"- Median tile pixel NCC: {aggregate['median_tile_pixel_ncc']}",
        f"- Minimum tile pixel NCC: {aggregate['minimum_tile_pixel_ncc']}",
        f"- Exact quantized tile hashes: {aggregate['exact_quantized_tile_hash_match_count']} / {aggregate['tile_count']}",
        f"- Tiles with NCC >= 0.995: {aggregate['tile_count_ncc_at_least_0_995']} / {aggregate['tile_count']}",
        "",
        "## Conservative action",
        "",
        f"`{assessment['conservative_external_candidate_pool_action']}`",
        "",
        "This action is a leakage-control recommendation, not authoritative parent identity.",
        "",
        "## External validation boundary",
        "",
        "The frame is not an independent external validation sample because independent expert labels and authoritative parent-disjoint provenance are absent.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def _file_spec(payload: Mapping[str, Any], context: str) -> FileSpec:
    _reject_unknown(payload, {"name", "url", "md5", "sha256"}, context)
    return FileSpec(
        name=_required_text(payload, "name"),
        url=_required_text(payload, "url"),
        md5=_digest(payload, "md5", 32),
        sha256=_digest(payload, "sha256", 64),
    )


def _archive_spec(payload: Mapping[str, Any], context: str) -> ArchiveSpec:
    _reject_unknown(payload, {"name", "url", "md5", "sha256", "expected_data_members"}, context)
    members = payload.get("expected_data_members")
    if not isinstance(members, list) or not members or not all(isinstance(item, str) and item for item in members):
        raise ValueError("expected_data_members must be a non-empty string list.")
    if len(set(members)) != len(members):
        raise ValueError("expected_data_members must be unique.")
    for member in members:
        _validate_member_name(member)
    return ArchiveSpec(
        name=_required_text(payload, "name"),
        url=_required_text(payload, "url"),
        md5=_digest(payload, "md5", 32),
        sha256=_digest(payload, "sha256", 64),
        expected_data_members=tuple(members),
    )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object.")
    return value


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text.")
    return value


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value


def _digest(payload: Mapping[str, Any], key: str, length: int) -> str:
    value = _required_text(payload, key).lower()
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{key} must be a {length}-character lowercase hexadecimal digest.")
    return value


def _int_tuple(payload: Mapping[str, Any], key: str, length: int) -> tuple[int, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{key} must be a list of {length} integers.")
    result = tuple(int(item) for item in value)
    if any(item <= 0 for item in result):
        raise ValueError(f"{key} values must be positive.")
    return result


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {context} keys: {unknown}")


def _validate_member_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError(f"unsafe ZIP member path: {name}")


TILE_COLUMNS = (
    "source_id",
    "frame_index",
    "source_frame_id",
    "candidate_parent_index",
    "tile_index",
    "tile_row",
    "tile_column",
    "training_patch_index",
    "exact_quantized_hash_match",
    "pixel_ncc",
    "pixel_rmse",
    "pixel_mae",
    "pixel_max_abs_difference",
    "block_signature_ncc",
    "block_signature_rmse",
)
