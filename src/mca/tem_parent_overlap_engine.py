"""Comparison engine for the TEM parent-overlap audit."""
from __future__ import annotations

import hashlib
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from . import __version__
from .tem_parent_overlap_contract import (
    OVERLAP_EQUIVALENT, OVERLAP_REVIEW, OVERLAP_NOT_DETECTED,
    CLOSEOUT_RESULT, LIMITATIONS, SourceMemberSpec, ParentOverlapAuditConfig,
)
from .tem_parent_overlap_io import (
    FRAME_COLUMNS, PAIRWISE_COLUMNS, _acquire_file, _acquire_archive,
    _verify_hashes, _validate_zip, _extract_member, _prepare_output, _write_csv,
    _write_json, _manifest, _build_report,
)

def run_parent_overlap_audit(
    config: ParentOverlapAuditConfig,
    output_dir: str | Path,
    *,
    training_path: str | Path | None = None,
    source_archive_path: str | Path | None = None,
) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="mca-tem-parent-overlap-") as temp_name:
            temp = Path(temp_name)
            training, training_mode = _acquire_file(config.training_file, training_path, temp)
            archive, archive_mode = _acquire_archive(
                config.source_archive, source_archive_path, temp
            )
            training_hashes = _verify_hashes(training, config.training_file)
            archive_hashes = _verify_hashes(archive, config.source_archive)
            zip_inventory = _validate_zip(archive, config.source_archive.expected_members)
            parent_records = _training_parent_records(training, config)
            frame_rows: list[dict[str, Any]] = []
            pair_rows: list[dict[str, Any]] = []
            member_hashes: dict[str, str] = {}
            with zipfile.ZipFile(archive) as zipped:
                for member_index, member in enumerate(config.source_members):
                    extracted = temp / f"source-{member_index}.h5"
                    member_hash = _extract_member(zipped, member.image_member, extracted)
                    member_hashes[member.image_member] = member_hash
                    frames, pairs = _inspect_source_member(
                        extracted,
                        member=member,
                        member_sha256=member_hash,
                        parents=parent_records,
                        config=config,
                    )
                    frame_rows.extend(frames)
                    pair_rows.extend(pairs)
                    extracted.unlink(missing_ok=True)

        frame_table = output / "tem_parent_overlap_frame_inventory.csv"
        pair_table = output / "tem_parent_overlap_pairwise_comparisons.csv"
        summary_path = output / "parent_overlap_audit_summary.json"
        report_path = output / "parent_overlap_audit_report.md"
        manifest_path = output / "parent_overlap_audit_artifact_manifest.json"
        _write_csv(frame_table, frame_rows, FRAME_COLUMNS)
        _write_csv(pair_table, pair_rows, PAIRWISE_COLUMNS)
        equivalent = [row for row in frame_rows if row["overlap_status"] == OVERLAP_EQUIVALENT]
        review = [row for row in frame_rows if row["overlap_status"] == OVERLAP_REVIEW]
        not_detected = [row for row in frame_rows if row["overlap_status"] == OVERLAP_NOT_DETECTED]
        content_matches = [
            {
                "source_frame_id": row["source_frame_id"],
                "training_candidate_parent": int(row["best_training_candidate_parent"]),
                "matched_tile_count": int(row["best_exact_tile_match_count"]),
            }
            for row in equivalent
        ]
        summary: dict[str, Any] = {
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
                    "name": config.training_file.name,
                    **training_hashes,
                    "acquisition_mode": training_mode,
                },
                "source_image_archive": {
                    "name": config.source_archive.name,
                    **archive_hashes,
                    "acquisition_mode": archive_mode,
                },
                "source_member_sha256": member_hashes,
            },
            "pinned_notebook_contract": {
                "repository": config.notebook_repository,
                "commit": config.notebook_commit,
                "tiling_notebook": config.tiling_notebook,
                "tiling_notebook_blob_sha": config.tiling_notebook_blob_sha,
                "normalization_notebook": config.normalization_notebook,
                "normalization_notebook_blob_sha": config.normalization_notebook_blob_sha,
                "comparison_path": "aligned_grid_then_independent_per_tile_standardization",
            },
            "training_parent_reconstruction": {
                "status": "diagnostic_reconstruction_not_authoritative_mapping",
                "candidate_parent_count": config.parent_count,
                "patches_per_parent": config.grid_rows * config.grid_columns,
                "authoritative_patch_to_parent_mapping_available": False,
            },
            "comparison_contract": {
                "exact_match_rule": "all_corresponding_quantized_standardized_tile_hashes_match",
                "quantization_decimals": config.quantization_decimals,
                "signature_block_size": config.signature_block_size,
                "review_ncc_threshold": config.review_ncc_threshold,
                "negative_result_scope": "no_content_equivalent_overlap_under_audited_alignment_and_standardization",
            },
            "source_archive_inventory": {
                **zip_inventory,
                "data_member_crc_verified_during_stream_extraction": True,
            },
            "content_equivalent_matches": content_matches,
            "result_counts": {
                "training_candidate_parent_count": config.parent_count,
                "source_member_count": len(config.source_members),
                "source_frame_count": len(frame_rows),
                "pairwise_comparison_count": len(pair_rows),
                "content_equivalent_overlap_frame_count": len(equivalent),
                "review_required_frame_count": len(review),
                "no_content_equivalent_overlap_detected_frame_count": len(not_detected),
                "independent_external_validation_candidate_count": 0,
            },
            "external_validation_readiness": {
                "status": CLOSEOUT_RESULT,
                "independent_label_status": config.independent_label_status,
                "source_masks_are_independent_ground_truth": False,
                "authoritative_training_parent_mapping_available": False,
                "parent_disjointness_proven_for_nonmatching_frames": False,
                "independent_external_validation_candidate_count": 0,
            },
            "processing": {
                "tile_restandardization_for_identity_comparison_only": True,
                "source_values_written_to_outputs": False,
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
                "result": CLOSEOUT_RESULT,
                "strongest_evidence": (
                    f"All {len(frame_rows)} checksum-bound public source frames were compared with "
                    f"all {config.parent_count} reconstructed training parents using the pinned aligned "
                    "tiling and per-tile standardization path. Exact equivalence requires all tile hashes to match."
                ),
                "primary_limitation": (
                    "Training parent IDs are reconstructed rather than authoritative, and public masks are "
                    "source predictions rather than independent labels."
                ),
                "evidence_that_would_change_conclusion": (
                    "A source-issued immutable patch-to-parent/acquisition map plus a predeclared parent-disjoint "
                    "image set with independent labels never used for training, tuning, or model selection."
                ),
                "suitable_for": [
                    "content-equivalent parent-overlap exclusion",
                    "image-only external-candidate inventory",
                    "segmentation data leakage diagnostics",
                ],
                "not_suitable_for": [
                    "independent segmentation performance claims",
                    "unbiased generalization estimates",
                    "physical measurements or engineering release",
                ],
            },
            "limitations": list(LIMITATIONS),
        }
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary), encoding="utf-8")
        manifest = _manifest(
            output,
            [frame_table, pair_table, summary_path, report_path],
            config.case_id,
            training_hashes["sha256"],
            archive_hashes["sha256"],
        )
        _write_json(manifest_path, manifest)
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _training_parent_records(path: Path, config: ParentOverlapAuditConfig) -> list[dict[str, Any]]:
    records = []
    tiles_per_parent = config.grid_rows * config.grid_columns
    with h5py.File(path, "r") as handle:
        dataset = _validate_hdf5(
            handle, config.training_dataset_name, config.training_shape, config.dtype, path.name
        )
        for parent_index in range(config.parent_count):
            hashes: list[str] = []
            signatures: list[np.ndarray] = []
            for offset in range(tiles_per_parent):
                patch_index = parent_index * tiles_per_parent + offset
                patch = np.asarray(dataset[patch_index], dtype=np.float64)
                _validate_finite(patch, f"training patch {patch_index}")
                _validate_standardized(patch, config, f"training patch {patch_index}")
                hashes.append(_array_hash(patch, config.quantization_decimals))
                signatures.append(_block_signature(patch, config.signature_block_size))
            records.append({
                "parent_index": parent_index,
                "tile_hashes": tuple(hashes),
                "signature": np.concatenate(signatures),
            })
    return records


def _inspect_source_member(
    path: Path,
    *,
    member: SourceMemberSpec,
    member_sha256: str,
    parents: list[dict[str, Any]],
    config: ParentOverlapAuditConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frames: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    with h5py.File(path, "r") as handle:
        dataset = _validate_hdf5(
            handle,
            config.source_dataset_name,
            config.source_member_shape,
            config.dtype,
            member.image_member,
        )
        for frame_index in range(config.source_member_shape[0]):
            frame = np.asarray(dataset[frame_index], dtype=np.float64)
            _validate_finite(frame, f"{member.source_id} frame {frame_index}")
            _validate_standardized(frame, config, f"{member.source_id} frame {frame_index}")
            tile_hashes: list[str] = []
            signatures: list[np.ndarray] = []
            for row in range(config.grid_rows):
                for column in range(config.grid_columns):
                    tile = frame[
                        row * config.tile_height : (row + 1) * config.tile_height,
                        column * config.tile_width : (column + 1) * config.tile_width,
                    ]
                    standardized = _standardize(tile)
                    tile_hashes.append(_array_hash(standardized, config.quantization_decimals))
                    signatures.append(_block_signature(standardized, config.signature_block_size))
            frame_signature = np.concatenate(signatures)
            source_frame_id = f"{member.source_id}:frame-{frame_index}"
            comparisons = []
            for parent in parents:
                exact = sum(a == b for a, b in zip(tile_hashes, parent["tile_hashes"]))
                ncc, rmse, max_abs = _signature_metrics(frame_signature, parent["signature"])
                row = {
                    "source_id": member.source_id,
                    "frame_index": frame_index,
                    "source_frame_id": source_frame_id,
                    "source_member": member.image_member,
                    "source_member_sha256": member_sha256,
                    "training_candidate_parent": int(parent["parent_index"]),
                    "exact_tile_match_count": exact,
                    "exact_tile_match_fraction": exact / len(tile_hashes),
                    "signature_ncc": ncc,
                    "signature_rmse": rmse,
                    "signature_max_abs_difference": max_abs,
                    "all_aligned_tile_hashes_match": exact == len(tile_hashes),
                }
                pair_rows.append(row)
                comparisons.append(row)
            best = max(
                comparisons,
                key=lambda item: (
                    int(item["exact_tile_match_count"]),
                    float(item["signature_ncc"]),
                    -float(item["signature_rmse"]),
                    -int(item["training_candidate_parent"]),
                ),
            )
            if bool(best["all_aligned_tile_hashes_match"]):
                overlap_status = OVERLAP_EQUIVALENT
            elif int(best["exact_tile_match_count"]) > 0 or float(best["signature_ncc"]) >= config.review_ncc_threshold:
                overlap_status = OVERLAP_REVIEW
            else:
                overlap_status = OVERLAP_NOT_DETECTED
            frames.append({
                "source_id": member.source_id,
                "frame_index": frame_index,
                "source_frame_id": source_frame_id,
                "source_member": member.image_member,
                "source_member_sha256": member_sha256,
                "best_training_candidate_parent": int(best["training_candidate_parent"]),
                "best_exact_tile_match_count": int(best["exact_tile_match_count"]),
                "best_exact_tile_match_fraction": float(best["exact_tile_match_fraction"]),
                "best_signature_ncc": float(best["signature_ncc"]),
                "best_signature_rmse": float(best["signature_rmse"]),
                "best_signature_max_abs_difference": float(best["signature_max_abs_difference"]),
                "overlap_status": overlap_status,
                "external_validation_candidate_status": (
                    "excluded_training_parent_overlap" if overlap_status == OVERLAP_EQUIVALENT
                    else "image_only_candidate_independent_labels_absent"
                ),
                "independent_label_status": config.independent_label_status,
                "independent_external_validation_candidate": False,
            })
    return frames, pair_rows


def _validate_hdf5(
    handle: h5py.File,
    dataset_name: str,
    expected_shape: tuple[int, int, int],
    expected_dtype: str,
    label: str,
) -> h5py.Dataset:
    if list(handle.keys()) != [dataset_name]:
        raise ValueError(f"{label} must contain only dataset {dataset_name!r}.")
    if handle.attrs:
        raise ValueError(f"{label} root attributes changed from the pinned contract.")
    dataset = handle[dataset_name]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"{label} dataset is not HDF5 data.")
    if tuple(dataset.shape) != expected_shape:
        raise ValueError(f"{label} shape {tuple(dataset.shape)} != {expected_shape}.")
    if str(dataset.dtype) != expected_dtype:
        raise ValueError(f"{label} dtype {dataset.dtype} != {expected_dtype}.")
    if dataset.attrs:
        raise ValueError(f"{label} dataset attributes changed from the pinned contract.")
    return dataset


def _standardize(values: np.ndarray) -> np.ndarray:
    mean = float(values.mean())
    std = float(values.std())
    if not math.isfinite(std) or std <= 0:
        raise ValueError("cannot standardize a constant or non-finite tile.")
    return (values - mean) / std


def _validate_standardized(values: np.ndarray, config: ParentOverlapAuditConfig, label: str) -> None:
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


def _signature_metrics(left: np.ndarray, right: np.ndarray) -> tuple[float, float, float]:
    difference = left - right
    rmse = float(np.sqrt(np.mean(difference * difference)))
    max_abs = float(np.max(np.abs(difference)))
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    ncc = 1.0 if denominator == 0 and np.array_equal(left, right) else (
        0.0 if denominator == 0 else float(np.dot(left_centered, right_centered) / denominator)
    )
    return max(-1.0, min(1.0, ncc)), rmse, max_abs
