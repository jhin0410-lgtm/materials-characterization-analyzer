"""Audit public hand-labeled HRTEM training patches and split readiness.

The audit validates source files, image/label pairing, patch representation, and
leakage risk in the source notebook's patch-level cross-validation. It does not
train a model or turn patch-level validation into an independent performance
claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import tempfile
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import h5py
import numpy as np

from . import __version__

PUBLIC_CASE_ID = "public_cobalt_oxide_tem_training_data_audit"
PUBLIC_DOI = "10.5281/zenodo.14927582"
PUBLIC_VERSION = "v1"
PUBLIC_LICENSE = "CC-BY-4.0"
PUBLIC_IMAGE_NAME = "training_images.h5"
PUBLIC_IMAGE_MD5 = "caac404a7ea2c65b2403aee5728a70eb"
PUBLIC_IMAGE_SHA256 = "e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926"
PUBLIC_LABEL_NAME = "training_labels.h5"
PUBLIC_LABEL_MD5 = "087a4df4cd67fa97cdf790c40bdc828b"
PUBLIC_LABEL_SHA256 = "28db52db53209a8a068f722990264a136ab187a192340ef3770e81d9c0de7c40"
READINESS_STATUS = "not_ready_for_independent_model_performance_claims"
PARENT_GROUPING_STATUS = "diagnostic_inference_not_embedded_metadata"

LIMITATIONS = (
    "The Zenodo record describes hand-labeled training data, but the HDF5 files do not embed parent-image identifiers, acquisition metadata, patch coordinates, or pixel calibration.",
    "Four contiguous groups of 64 patches are strongly consistent with four 8 x 8 tiled parent images, but this grouping is diagnostic reconstruction rather than authoritative source metadata.",
    "The linked source notebook applies shuffled eight-fold KFold directly to 256 patch indices; all four reconstructed candidate parents occur in both training and validation in every fold.",
    "Patch-level validation from that split is not independent parent-image validation and must not be presented as unbiased generalization performance.",
    "The image patches are already standardized to approximately zero mean and unit standard deviation, so original detector intensity is unavailable in the selected files.",
    "The dataset-level 67 to 86 pm description is not bound to individual patches and is not used for physical conversion.",
    "No model training, model inference, segmentation accuracy, physical-size conversion, synthesis-condition inference, causal claim, optimization, or engineering-release decision is performed.",
)


@dataclass(frozen=True)
class FileSpec:
    """One exact public HDF5 file."""

    name: str
    url: str
    md5: str
    sha256: str


@dataclass(frozen=True)
class NotebookSplitContract:
    """Pinned split and tiling behavior extracted from source notebooks."""

    repository: str
    commit: str
    training_notebook: str
    training_notebook_blob_sha: str
    tiling_notebook: str
    tiling_notebook_blob_sha: str
    patch_count: int
    n_splits: int
    shuffle: bool
    random_state: int
    parent_group_id_used: bool
    parent_grid_rows: int
    parent_grid_columns: int


@dataclass(frozen=True)
class TrainingDataAuditConfig:
    """Strict contract for the public training-data audit."""

    case_id: str
    record_id: int
    doi: str
    dataset_version: str
    license: str
    source_description: str
    image_file: FileSpec
    label_file: FileSpec
    image_dataset_name: str
    label_dataset_name: str
    image_shape: tuple[int, int, int]
    label_shape: tuple[int, int, int, int]
    image_dtype: str
    label_dtype: str
    attributes_expected: bool
    image_mean_abs_tolerance: float
    image_std_abs_tolerance: float
    candidate_parent_group_count: int
    patches_per_candidate_parent: int
    max_image_seam_ratio: float
    max_label_seam_ratio: float
    notebook: NotebookSplitContract
    literature_pixel_size_range_pm: tuple[float, float]
    calibration_binding_status: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "TrainingDataAuditConfig":
        _reject_unknown(
            payload,
            {
                "case_id",
                "source",
                "image_file",
                "label_file",
                "hdf5_contract",
                "candidate_parent_grouping",
                "notebook_contract",
                "literature_context",
            },
            "config",
        )
        source = _mapping(payload, "source")
        hdf5_contract = _mapping(payload, "hdf5_contract")
        grouping = _mapping(payload, "candidate_parent_grouping")
        notebook = _mapping(payload, "notebook_contract")
        literature = _mapping(payload, "literature_context")
        _reject_unknown(
            source,
            {"record_id", "doi", "dataset_version", "license", "source_description"},
            "source",
        )
        _reject_unknown(
            hdf5_contract,
            {
                "image_dataset_name",
                "label_dataset_name",
                "image_shape",
                "label_shape",
                "image_dtype",
                "label_dtype",
                "attributes_expected",
                "image_mean_abs_tolerance",
                "image_std_abs_tolerance",
            },
            "hdf5_contract",
        )
        _reject_unknown(
            grouping,
            {
                "candidate_parent_group_count",
                "patches_per_candidate_parent",
                "max_image_seam_ratio",
                "max_label_seam_ratio",
            },
            "candidate_parent_grouping",
        )
        _reject_unknown(
            notebook,
            {
                "repository",
                "commit",
                "training_notebook",
                "training_notebook_blob_sha",
                "tiling_notebook",
                "tiling_notebook_blob_sha",
                "patch_count",
                "n_splits",
                "shuffle",
                "random_state",
                "parent_group_id_used",
                "parent_grid_rows",
                "parent_grid_columns",
            },
            "notebook_contract",
        )
        _reject_unknown(
            literature,
            {"pixel_size_range_pm", "calibration_binding_status"},
            "literature_context",
        )
        image_shape = hdf5_contract.get("image_shape")
        label_shape = hdf5_contract.get("label_shape")
        pixel_range = literature.get("pixel_size_range_pm")
        if not isinstance(image_shape, list) or not isinstance(label_shape, list):
            raise ValueError("image_shape and label_shape must be lists.")
        if not isinstance(pixel_range, list) or len(pixel_range) != 2:
            raise ValueError("pixel_size_range_pm must contain two values.")
        config = cls(
            case_id=_required_text(payload, "case_id"),
            record_id=int(source["record_id"]),
            doi=_required_text(source, "doi"),
            dataset_version=_required_text(source, "dataset_version"),
            license=_required_text(source, "license"),
            source_description=_required_text(source, "source_description"),
            image_file=_file_spec(_mapping(payload, "image_file"), "image_file"),
            label_file=_file_spec(_mapping(payload, "label_file"), "label_file"),
            image_dataset_name=_required_text(hdf5_contract, "image_dataset_name"),
            label_dataset_name=_required_text(hdf5_contract, "label_dataset_name"),
            image_shape=tuple(int(value) for value in image_shape),
            label_shape=tuple(int(value) for value in label_shape),
            image_dtype=_required_text(hdf5_contract, "image_dtype"),
            label_dtype=_required_text(hdf5_contract, "label_dtype"),
            attributes_expected=_required_bool(hdf5_contract, "attributes_expected"),
            image_mean_abs_tolerance=float(hdf5_contract["image_mean_abs_tolerance"]),
            image_std_abs_tolerance=float(hdf5_contract["image_std_abs_tolerance"]),
            candidate_parent_group_count=int(grouping["candidate_parent_group_count"]),
            patches_per_candidate_parent=int(grouping["patches_per_candidate_parent"]),
            max_image_seam_ratio=float(grouping["max_image_seam_ratio"]),
            max_label_seam_ratio=float(grouping["max_label_seam_ratio"]),
            notebook=NotebookSplitContract(
                repository=_required_text(notebook, "repository"),
                commit=_digest(notebook, "commit", 40),
                training_notebook=_required_text(notebook, "training_notebook"),
                training_notebook_blob_sha=_digest(notebook, "training_notebook_blob_sha", 40),
                tiling_notebook=_required_text(notebook, "tiling_notebook"),
                tiling_notebook_blob_sha=_digest(notebook, "tiling_notebook_blob_sha", 40),
                patch_count=int(notebook["patch_count"]),
                n_splits=int(notebook["n_splits"]),
                shuffle=_required_bool(notebook, "shuffle"),
                random_state=int(notebook["random_state"]),
                parent_group_id_used=_required_bool(notebook, "parent_group_id_used"),
                parent_grid_rows=int(notebook["parent_grid_rows"]),
                parent_grid_columns=int(notebook["parent_grid_columns"]),
            ),
            literature_pixel_size_range_pm=(float(pixel_range[0]), float(pixel_range[1])),
            calibration_binding_status=_required_text(literature, "calibration_binding_status"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.case_id):
            raise ValueError("case_id must use lowercase letters, digits, and underscores.")
        if len(self.image_shape) != 3 or len(self.label_shape) != 4:
            raise ValueError("image_shape must be 3D and label_shape must be 4D.")
        if self.image_shape[0] != self.label_shape[0]:
            raise ValueError("image and label patch counts must match.")
        if self.image_shape[1:] != self.label_shape[1:3]:
            raise ValueError("image and label spatial shapes must match.")
        if self.label_shape[-1] != 2:
            raise ValueError("the supported public label contract has two channels.")
        if self.attributes_expected:
            raise ValueError("the supported public HDF5 contract has no attributes.")
        if self.image_mean_abs_tolerance <= 0 or self.image_std_abs_tolerance <= 0:
            raise ValueError("image standardization tolerances must be positive.")
        if self.candidate_parent_group_count * self.patches_per_candidate_parent != self.image_shape[0]:
            raise ValueError("candidate parent grouping must cover every patch exactly once.")
        grid_size = self.notebook.parent_grid_rows * self.notebook.parent_grid_columns
        if grid_size != self.patches_per_candidate_parent:
            raise ValueError("candidate parent grid must equal patches_per_candidate_parent.")
        if self.notebook.patch_count != self.image_shape[0]:
            raise ValueError("notebook patch_count must match the HDF5 patch count.")
        if self.notebook.n_splits <= 1 or self.notebook.patch_count % self.notebook.n_splits != 0:
            raise ValueError("the pinned notebook split requires equal nontrivial folds.")
        if self.notebook.parent_group_id_used:
            raise ValueError("the pinned source notebook does not use parent group IDs.")
        if self.max_image_seam_ratio <= 0 or self.max_label_seam_ratio <= 0:
            raise ValueError("seam-ratio thresholds must be positive.")


def load_config(path: str | Path) -> TrainingDataAuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("case config must contain a JSON object.")
    return TrainingDataAuditConfig.from_mapping(payload)


def validate_public_config(config: TrainingDataAuditConfig) -> None:
    expected = {
        "case_id": PUBLIC_CASE_ID,
        "record_id": 14927582,
        "doi": PUBLIC_DOI,
        "dataset_version": PUBLIC_VERSION,
        "license": PUBLIC_LICENSE,
        "image_dataset_name": "images",
        "label_dataset_name": "labels",
        "image_shape": (256, 512, 512),
        "label_shape": (256, 512, 512, 2),
        "image_dtype": "float64",
        "label_dtype": "float64",
        "attributes_expected": False,
        "image_mean_abs_tolerance": 1e-10,
        "image_std_abs_tolerance": 1e-12,
        "candidate_parent_group_count": 4,
        "patches_per_candidate_parent": 64,
        "max_image_seam_ratio": 0.75,
        "max_label_seam_ratio": 0.1,
        "literature_pixel_size_range_pm": (67.0, 86.0),
        "calibration_binding_status": "dataset_context_not_bound_to_individual_training_patches",
    }
    for field, value in expected.items():
        actual = getattr(config, field)
        if actual != value:
            raise ValueError(f"public config mismatch for {field}: {actual!r} != {value!r}")
    _validate_file_spec(
        config.image_file,
        name=PUBLIC_IMAGE_NAME,
        url="https://zenodo.org/records/14927582/files/training_images.h5?download=1",
        md5=PUBLIC_IMAGE_MD5,
        sha256=PUBLIC_IMAGE_SHA256,
    )
    _validate_file_spec(
        config.label_file,
        name=PUBLIC_LABEL_NAME,
        url="https://zenodo.org/records/14927582/files/training_labels.h5?download=1",
        md5=PUBLIC_LABEL_MD5,
        sha256=PUBLIC_LABEL_SHA256,
    )
    expected_notebook = NotebookSplitContract(
        repository="ScottLabUCB/NN_training",
        commit="9f92235102a805abc76e3d60065d677ee2068c90",
        training_notebook="model training for HRTEM_v2.ipynb",
        training_notebook_blob_sha="59a4f43a0aed1a30bcebda0597368c2425f38218",
        tiling_notebook="model training for HRTEM.ipynb",
        tiling_notebook_blob_sha="a21bf95fb41f63efb0c33b1563bc43a073afed58",
        patch_count=256,
        n_splits=8,
        shuffle=True,
        random_state=42,
        parent_group_id_used=False,
        parent_grid_rows=8,
        parent_grid_columns=8,
    )
    if config.notebook != expected_notebook:
        raise ValueError("public notebook split contract does not match the pinned source evidence.")


def run_training_data_audit(
    config: TrainingDataAuditConfig,
    output_dir: str | Path,
    *,
    image_path: str | Path | None = None,
    label_path: str | Path | None = None,
) -> dict[str, Any]:
    output = _prepare_empty_output(output_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="mca-tem-training-") as temp_name:
            temp = Path(temp_name)
            image_file, image_mode = _acquire(config.image_file, image_path, temp)
            label_file, label_mode = _acquire(config.label_file, label_path, temp)
            image_hashes = _verify_file(image_file, config.image_file)
            label_hashes = _verify_file(label_file, config.label_file)
            result = inspect_training_pair(image_file, label_file, config=config)

        patch_path = output / "tem_training_patch_inventory.csv"
        seam_path = output / "tem_training_candidate_parent_seams.csv"
        split_path = output / "tem_training_notebook_split_overlap.csv"
        summary_path = output / "training_data_readiness_summary.json"
        report_path = output / "training_data_readiness_report.md"
        manifest_path = output / "training_data_readiness_artifact_manifest.json"
        _write_csv(patch_path, result["patch_rows"], PATCH_COLUMNS)
        _write_csv(seam_path, result["seam_rows"], SEAM_COLUMNS)
        _write_csv(split_path, result["split_rows"], SPLIT_COLUMNS)

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
                "training_images": {
                    "name": config.image_file.name,
                    "md5": image_hashes["md5"],
                    "sha256": image_hashes["sha256"],
                    "acquisition_mode": image_mode,
                },
                "training_labels": {
                    "name": config.label_file.name,
                    "md5": label_hashes["md5"],
                    "sha256": label_hashes["sha256"],
                    "acquisition_mode": label_mode,
                },
            },
            "hdf5_contract": result["hdf5_contract"],
            "value_contract": result["value_contract"],
            "image_representation": result["image_representation"],
            "candidate_parent_grouping": result["candidate_parent_grouping"],
            "notebook_split_audit": result["notebook_split_audit"],
            "literature_context": {
                "pixel_size_range_pm": list(config.literature_pixel_size_range_pm),
                "calibration_binding_status": config.calibration_binding_status,
                "used_for_physical_conversion": False,
            },
            "result_counts": {
                "patch_pair_count": len(result["patch_rows"]),
                "candidate_parent_group_count": config.candidate_parent_group_count,
                "notebook_fold_count": len(result["split_rows"]),
            },
            "processing": {
                "source_values_modified_by_repository": False,
                "additional_standardization_performed": False,
                "augmentation_performed": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_accuracy_computed": False,
                "pixel_calibration_applied": False,
                "physical_size_computed": False,
                "synthesis_condition_inferred": False,
            },
            "scientific_closeout": {
                "status": "Diagnostic",
                "result": READINESS_STATUS,
                "strongest_evidence": (
                    "The checksum-bound public files contain 256 finite standardized image patches and 256 paired complementary one-hot labels. Four contiguous 64-patch blocks show strong 8 x 8 edge continuity, while every fold of the pinned shuffled patch-level KFold places all four reconstructed candidate parents in both training and validation."
                ),
                "primary_limitation": (
                    "Authoritative parent-image IDs and an untouched independent validation or test partition are absent from the public training HDF5 contract."
                ),
                "evidence_that_would_change_conclusion": (
                    "A source-provided immutable patch-to-parent mapping plus a predeclared parent-disjoint external validation set with independent labels and calibration metadata where physical measurements are intended."
                ),
                "suitable_for": [
                    "training-pair integrity validation",
                    "label representation validation",
                    "diagnostic parent-group reconstruction",
                    "split-leakage risk auditing",
                    "model development with explicit non-independent-validation limitations",
                ],
                "not_suitable_for": [
                    "independent segmentation performance claims",
                    "unbiased parent-image generalization estimates",
                    "nanometre-scale physical conversion",
                    "synthesis-condition comparison",
                    "causal inference",
                    "optimization or engineering release",
                ],
            },
            "limitations": list(LIMITATIONS),
        }
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary), encoding="utf-8")
        manifest = _build_manifest(
            output,
            [patch_path, seam_path, split_path, summary_path, report_path],
            case_id=config.case_id,
            image_sha256=image_hashes["sha256"],
            label_sha256=label_hashes["sha256"],
        )
        _write_json(manifest_path, manifest)
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def inspect_training_pair(
    image_path: str | Path,
    label_path: str | Path,
    *,
    config: TrainingDataAuditConfig,
) -> dict[str, Any]:
    patch_rows: list[dict[str, Any]] = []
    image_hashes: list[str] = []
    label_hashes: list[str] = []
    label_counts: Counter[str] = Counter()
    image_min = math.inf
    image_max = -math.inf

    with h5py.File(image_path, "r") as image_h5, h5py.File(label_path, "r") as label_h5:
        images = _validate_hdf5(
            image_h5,
            dataset_name=config.image_dataset_name,
            expected_shape=config.image_shape,
            expected_dtype=config.image_dtype,
            file_label=config.image_file.name,
        )
        labels = _validate_hdf5(
            label_h5,
            dataset_name=config.label_dataset_name,
            expected_shape=config.label_shape,
            expected_dtype=config.label_dtype,
            file_label=config.label_file.name,
        )
        for index in range(config.image_shape[0]):
            image = np.asarray(images[index])
            label = np.asarray(labels[index])
            if not np.isfinite(image).all():
                raise ValueError(f"non-finite image value in patch {index}.")
            if not np.isfinite(label).all():
                raise ValueError(f"non-finite label value in patch {index}.")
            valid_binary = np.logical_or(label == 0.0, label == 1.0)
            if not bool(valid_binary.all()):
                bad = np.unique(label[~valid_binary])[:10].tolist()
                raise ValueError(f"non-binary label value in patch {index}: {bad}")
            if not bool(np.all(label[..., 0] + label[..., 1] == 1.0)):
                raise ValueError(f"label channels are not complementary one-hot in patch {index}.")
            image_mean = float(image.mean())
            image_std = float(image.std())
            if abs(image_mean) > config.image_mean_abs_tolerance:
                raise ValueError(f"image mean drift in patch {index}: {image_mean}")
            if abs(image_std - 1.0) > config.image_std_abs_tolerance:
                raise ValueError(f"image standard deviation drift in patch {index}: {image_std}")
            image_hash = _array_hash(image)
            label_hash = _array_hash(label)
            image_hashes.append(image_hash)
            label_hashes.append(label_hash)
            image_min = min(image_min, float(image.min()))
            image_max = max(image_max, float(image.max()))
            values, counts = np.unique(label, return_counts=True)
            for value, count in zip(values.tolist(), counts.tolist()):
                label_counts[str(float(value))] += int(count)
            parent = index // config.patches_per_candidate_parent
            tile_index = index % config.patches_per_candidate_parent
            patch_rows.append(
                {
                    "patch_index": index,
                    "candidate_parent_group": parent,
                    "candidate_tile_row": tile_index // config.notebook.parent_grid_columns,
                    "candidate_tile_column": tile_index % config.notebook.parent_grid_columns,
                    "image_sha256": image_hash,
                    "label_sha256": label_hash,
                    "image_mean": image_mean,
                    "image_std": image_std,
                    "label_channel_0_fraction": float(label[..., 0].mean()),
                    "label_channel_1_fraction": float(label[..., 1].mean()),
                    "parent_identity_status": PARENT_GROUPING_STATUS,
                }
            )

        seam_result = _audit_candidate_parent_seams(images, labels, config=config)

    image_duplicates = Counter(image_hashes)
    label_duplicates = Counter(label_hashes)
    split_rows = _audit_notebook_split(config)
    overlap_counts = [int(row["overlap_group_count"]) for row in split_rows]
    return {
        "patch_rows": patch_rows,
        "seam_rows": seam_result["seam_rows"],
        "split_rows": split_rows,
        "hdf5_contract": {
            "image_dataset_name": config.image_dataset_name,
            "label_dataset_name": config.label_dataset_name,
            "image_shape": list(config.image_shape),
            "label_shape": list(config.label_shape),
            "image_dtype": config.image_dtype,
            "label_dtype": config.label_dtype,
            "attributes_present": False,
            "image_chunks": None,
            "label_chunks": None,
            "image_compression": None,
            "label_compression": None,
            "parent_ids_present": False,
            "patch_coordinates_present": False,
            "pixel_calibration_present": False,
        },
        "value_contract": {
            "all_images_finite": True,
            "all_labels_finite": True,
            "labels_binary": True,
            "label_channels_complementary_one_hot": True,
            "label_value_counts": dict(sorted(label_counts.items())),
            "exact_duplicate_image_patch_count": sum(
                count - 1 for count in image_duplicates.values() if count > 1
            ),
            "exact_duplicate_label_patch_count": sum(
                count - 1 for count in label_duplicates.values() if count > 1
            ),
        },
        "image_representation": {
            "classification": "source_standardized_float64_patch_array",
            "all_patch_means_near_zero": True,
            "all_patch_standard_deviations_near_one": True,
            "maximum_abs_patch_mean": max(abs(float(row["image_mean"])) for row in patch_rows),
            "maximum_abs_patch_std_deviation_from_one": max(
                abs(float(row["image_std"]) - 1.0) for row in patch_rows
            ),
            "minimum": image_min,
            "maximum": image_max,
            "original_detector_intensity_available": False,
        },
        "candidate_parent_grouping": {
            "status": PARENT_GROUPING_STATUS,
            "candidate_group_count": config.candidate_parent_group_count,
            "patches_per_candidate_group": config.patches_per_candidate_parent,
            "candidate_grid": [
                config.notebook.parent_grid_rows,
                config.notebook.parent_grid_columns,
            ],
            "basis": (
                "contiguous blocks of 64 follow the pinned source notebook's 4k-to-512 8 x 8 tiling order and show substantially lower edge discontinuity than random patch pairing"
            ),
            "observed_image_seam_mean_abs_difference": seam_result["observed_image_mean"],
            "random_image_seam_mean_abs_difference": seam_result["random_image_mean"],
            "observed_to_random_image_seam_ratio": seam_result["image_ratio"],
            "observed_label_seam_mean_abs_difference": seam_result["observed_label_mean"],
            "random_label_seam_mean_abs_difference": seam_result["random_label_mean"],
            "observed_to_random_label_seam_ratio": seam_result["label_ratio"],
            "edge_continuity_supports_candidate_grouping": True,
            "authoritative_parent_ids_available": False,
        },
        "notebook_split_audit": {
            "repository": config.notebook.repository,
            "commit": config.notebook.commit,
            "training_notebook": config.notebook.training_notebook,
            "training_notebook_blob_sha": config.notebook.training_notebook_blob_sha,
            "tiling_notebook": config.notebook.tiling_notebook,
            "tiling_notebook_blob_sha": config.notebook.tiling_notebook_blob_sha,
            "split_method": (
                f"KFold(n_splits={config.notebook.n_splits}, shuffle=True, random_state={config.notebook.random_state}) on {config.notebook.patch_count} patch indices"
            ),
            "split_unit": "patch_index",
            "parent_group_id_used": config.notebook.parent_group_id_used,
            "candidate_parent_group_overlap_in_every_fold": all(
                count == config.candidate_parent_group_count for count in overlap_counts
            ),
            "minimum_overlap_group_count": min(overlap_counts),
            "maximum_overlap_group_count": max(overlap_counts),
            "independent_parent_image_validation": False,
            "performance_claim_ready": False,
        },
    }


def _audit_candidate_parent_seams(
    images: h5py.Dataset,
    labels: h5py.Dataset,
    *,
    config: TrainingDataAuditConfig,
) -> dict[str, Any]:
    seam_rows: list[dict[str, Any]] = []
    observed_image: list[float] = []
    observed_label: list[float] = []
    rows = config.notebook.parent_grid_rows
    columns = config.notebook.parent_grid_columns
    for group in range(config.candidate_parent_group_count):
        start = group * config.patches_per_candidate_parent
        image_differences: list[float] = []
        label_differences: list[float] = []
        for row in range(rows):
            for column in range(columns):
                index = start + row * columns + column
                if column < columns - 1:
                    right = index + 1
                    image_differences.append(
                        _mean_abs_difference(images[index, :, -1], images[right, :, 0])
                    )
                    label_differences.append(
                        _mean_abs_difference(labels[index, :, -1, :], labels[right, :, 0, :])
                    )
                if row < rows - 1:
                    down = index + columns
                    image_differences.append(
                        _mean_abs_difference(images[index, -1, :], images[down, 0, :])
                    )
                    label_differences.append(
                        _mean_abs_difference(labels[index, -1, :, :], labels[down, 0, :, :])
                    )
        image_mean = float(np.mean(image_differences))
        label_mean = float(np.mean(label_differences))
        observed_image.append(image_mean)
        observed_label.append(label_mean)
        seam_rows.append(
            {
                "candidate_parent_group": group,
                "patch_start_index": start,
                "patch_end_index": start + config.patches_per_candidate_parent - 1,
                "observed_image_seam_mean_abs_difference": image_mean,
                "observed_label_seam_mean_abs_difference": label_mean,
                "parent_identity_status": PARENT_GROUPING_STATUS,
            }
        )

    random_order = np.random.default_rng(config.notebook.random_state).permutation(
        config.image_shape[0]
    )
    random_image: list[float] = []
    random_label: list[float] = []
    comparison_count = (
        config.candidate_parent_group_count * rows * (columns - 1)
    )
    for position in range(comparison_count):
        a = int(random_order[position])
        b = int(random_order[(position + 1) % len(random_order)])
        random_image.append(_mean_abs_difference(images[a, :, -1], images[b, :, 0]))
        random_label.append(_mean_abs_difference(labels[a, :, -1, :], labels[b, :, 0, :]))
    observed_image_mean = float(np.mean(observed_image))
    observed_label_mean = float(np.mean(observed_label))
    random_image_mean = float(np.mean(random_image))
    random_label_mean = float(np.mean(random_label))
    image_ratio = _safe_ratio(observed_image_mean, random_image_mean, 'image')
    label_ratio = _safe_ratio(observed_label_mean, random_label_mean, 'label')
    if image_ratio > config.max_image_seam_ratio:
        raise ValueError(f"candidate parent image seam ratio too high: {image_ratio}")
    if label_ratio > config.max_label_seam_ratio:
        raise ValueError(f"candidate parent label seam ratio too high: {label_ratio}")
    return {
        "seam_rows": seam_rows,
        "observed_image_mean": observed_image_mean,
        "random_image_mean": random_image_mean,
        "image_ratio": image_ratio,
        "observed_label_mean": observed_label_mean,
        "random_label_mean": random_label_mean,
        "label_ratio": label_ratio,
    }


def _audit_notebook_split(config: TrainingDataAuditConfig) -> list[dict[str, Any]]:
    indices = np.arange(config.notebook.patch_count)
    if config.notebook.shuffle:
        rng = np.random.RandomState(config.notebook.random_state)
        indices = indices.copy()
        rng.shuffle(indices)
    fold_sizes = np.full(
        config.notebook.n_splits,
        config.notebook.patch_count // config.notebook.n_splits,
        dtype=int,
    )
    fold_sizes[: config.notebook.patch_count % config.notebook.n_splits] += 1
    candidate_groups = np.arange(config.notebook.patch_count) // config.patches_per_candidate_parent
    rows: list[dict[str, Any]] = []
    current = 0
    all_indices = np.arange(config.notebook.patch_count)
    for fold, fold_size in enumerate(fold_sizes.tolist(), start=1):
        start, stop = current, current + fold_size
        validation = indices[start:stop]
        validation_set = set(validation.tolist())
        training = np.array(
            [index for index in all_indices.tolist() if index not in validation_set],
            dtype=int,
        )
        train_groups = sorted(set(candidate_groups[training].tolist()))
        validation_groups = sorted(set(candidate_groups[validation].tolist()))
        overlap = sorted(set(train_groups) & set(validation_groups))
        rows.append(
            {
                "fold": fold,
                "train_patch_count": len(training),
                "validation_patch_count": len(validation),
                "train_candidate_parent_groups": json.dumps(train_groups),
                "validation_candidate_parent_groups": json.dumps(validation_groups),
                "overlapping_candidate_parent_groups": json.dumps(overlap),
                "overlap_group_count": len(overlap),
                "independent_parent_image_validation": False,
            }
        )
        current = stop
    return rows


def _validate_hdf5(
    handle: h5py.File,
    *,
    dataset_name: str,
    expected_shape: tuple[int, ...],
    expected_dtype: str,
    file_label: str,
) -> h5py.Dataset:
    if list(handle.keys()) != [dataset_name]:
        raise ValueError(
            f"{file_label} must contain only dataset {dataset_name!r}; found {list(handle.keys())!r}."
        )
    if len(handle.attrs) != 0:
        raise ValueError(f"{file_label} root attributes changed from the pinned contract.")
    dataset = handle[dataset_name]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"{file_label} {dataset_name!r} is not an HDF5 dataset.")
    if tuple(dataset.shape) != expected_shape:
        raise ValueError(f"{file_label} shape {tuple(dataset.shape)} != {expected_shape}.")
    if str(dataset.dtype) != expected_dtype:
        raise ValueError(f"{file_label} dtype {dataset.dtype} != {expected_dtype}.")
    if len(dataset.attrs) != 0:
        raise ValueError(f"{file_label} dataset attributes changed from the pinned contract.")
    if dataset.chunks is not None or dataset.compression is not None:
        raise ValueError(f"{file_label} storage layout changed from contiguous uncompressed data.")
    return dataset



def _safe_ratio(numerator: float, denominator: float, label: str) -> float:
    if denominator == 0.0:
        if numerator == 0.0:
            return 0.0
        raise ValueError(f"random {label} seam reference is zero while observed seams are nonzero.")
    return numerator / denominator

def _mean_abs_difference(a: Any, b: Any) -> float:
    first = np.asarray(a, dtype=np.float64)
    second = np.asarray(b, dtype=np.float64)
    return float(np.mean(np.abs(first - second)))


def _array_hash(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes(order="C")).hexdigest()


def _file_spec(payload: Mapping[str, Any], context: str) -> FileSpec:
    _reject_unknown(payload, {"name", "url", "md5", "sha256"}, context)
    return FileSpec(
        name=_required_text(payload, "name"),
        url=_required_text(payload, "url"),
        md5=_digest(payload, "md5", 32),
        sha256=_digest(payload, "sha256", 64),
    )


def _validate_file_spec(
    spec: FileSpec,
    *,
    name: str,
    url: str,
    md5: str,
    sha256: str,
) -> None:
    expected = {"name": name, "url": url, "md5": md5, "sha256": sha256}
    for field, value in expected.items():
        actual = getattr(spec, field)
        if actual != value:
            raise ValueError(f"public file mismatch for {field}: {actual!r} != {value!r}")


def _acquire(spec: FileSpec, supplied_path: str | Path | None, temp: Path) -> tuple[Path, str]:
    if supplied_path is not None:
        supplied = Path(supplied_path)
        if not supplied.is_file():
            raise FileNotFoundError(f"source file does not exist: {supplied}")
        if supplied.is_symlink():
            raise ValueError(f"source file path must not be a symlink: {supplied}")
        return supplied, "user_supplied_local_copy_verified_against_pinned_hashes"
    destination = temp / spec.name
    request = urllib.request.Request(
        spec.url, headers={"User-Agent": "materials-characterization-analyzer"}
    )
    with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target, length=1024 * 1024)
    return destination, "downloaded_from_pinned_public_url"


def _verify_file(path: Path, spec: FileSpec) -> dict[str, str]:
    md5 = _hash_file(path, "md5")
    sha256 = _hash_file(path, "sha256")
    if md5 != spec.md5:
        raise ValueError(f"{spec.name} MD5 mismatch: {md5} != {spec.md5}")
    if sha256 != spec.sha256:
        raise ValueError(f"{spec.name} SHA-256 mismatch: {sha256} != {spec.sha256}")
    return {"md5": md5, "sha256": sha256}


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if not output.is_dir():
            raise ValueError(f"output path is not a directory: {output}")
        if any(output.iterdir()):
            raise FileExistsError(f"output directory must be absent or empty: {output}")
    else:
        output.mkdir(parents=True)
    return output


def _build_report(summary: Mapping[str, Any]) -> str:
    grouping = summary["candidate_parent_grouping"]
    split = summary["notebook_split_audit"]
    closeout = summary["scientific_closeout"]
    return "\n".join(
        [
            "# Public Cobalt Oxide TEM Training-Data Readiness Audit",
            "",
            f"- Dataset DOI: `{summary['source']['doi']}`",
            f"- Paired patches: `{summary['result_counts']['patch_pair_count']}`",
            f"- Candidate parent groups: `{summary['result_counts']['candidate_parent_group_count']}`",
            f"- Candidate image seam ratio: `{grouping['observed_to_random_image_seam_ratio']}`",
            f"- Candidate label seam ratio: `{grouping['observed_to_random_label_seam_ratio']}`",
            f"- Candidate parents overlapping every notebook fold: `{split['candidate_parent_group_overlap_in_every_fold']}`",
            f"- Independent parent-image validation: `{split['independent_parent_image_validation']}`",
            "- Model training performed: `false`",
            "- Segmentation accuracy computed: `false`",
            "- Pixel calibration applied: `false`",
            "",
            "## Scientific closeout",
            "",
            f"**Evidence level: {closeout['status']}**",
            "",
            f"Result: `{closeout['result']}`",
            "",
            closeout["strongest_evidence"],
            "",
            f"Primary limitation: {closeout['primary_limitation']}",
            "",
            "The files support training-data integrity checks and diagnostic model development, but the published patch-level KFold must not be represented as independent generalization evidence.",
            "",
        ]
    )


def _build_manifest(
    output: Path,
    files: Iterable[Path],
    *,
    case_id: str,
    image_sha256: str,
    label_sha256: str,
) -> dict[str, Any]:
    records = []
    for path in sorted(files, key=lambda item: item.name):
        records.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path, "sha256"),
            }
        )
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "training_images_sha256": image_sha256,
        "training_labels_sha256": label_sha256,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _mapping(payload: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()


def _required_bool(payload: Mapping[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean.")
    return value


def _digest(payload: Mapping[str, Any], field: str, length: int) -> str:
    value = _required_text(payload, field).lower()
    if len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a {length}-character hexadecimal digest.")
    return value


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {context} field(s): {', '.join(unknown)}")


PATCH_COLUMNS = (
    "patch_index",
    "candidate_parent_group",
    "candidate_tile_row",
    "candidate_tile_column",
    "image_sha256",
    "label_sha256",
    "image_mean",
    "image_std",
    "label_channel_0_fraction",
    "label_channel_1_fraction",
    "parent_identity_status",
)

SEAM_COLUMNS = (
    "candidate_parent_group",
    "patch_start_index",
    "patch_end_index",
    "observed_image_seam_mean_abs_difference",
    "observed_label_seam_mean_abs_difference",
    "parent_identity_status",
)

SPLIT_COLUMNS = (
    "fold",
    "train_patch_count",
    "validation_patch_count",
    "train_candidate_parent_groups",
    "validation_candidate_parent_groups",
    "overlapping_candidate_parent_groups",
    "overlap_group_count",
    "independent_parent_image_validation",
)
