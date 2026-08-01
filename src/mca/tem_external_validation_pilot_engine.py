"""Scientific comparison engine for the Dryad HRTEM pilot-pair audit."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from . import __version__
from .tem_external_validation_pilot_contract import PilotAuditConfig
from .tem_external_validation_pilot_io import (
    OVERLAP_COLUMNS,
    PATCH_COLUMNS,
    acquire_training,
    array_hash,
    bind_processed_metadata,
    build_manifest,
    build_report,
    normalized_label_values,
    normalized_signature,
    object_attributes,
    prepare_output,
    raw_array_hash,
    resolve_dryad_file,
    single_dataset,
    standardize,
    verify_training,
    write_csv,
    write_json,
)


def run_pilot_pair_audit(
    config: PilotAuditConfig,
    output_dir: str | Path,
    *,
    image_path: str | Path | None = None,
    label_path: str | Path | None = None,
    processed_metadata_path: str | Path | None = None,
    training_path: str | Path | None = None,
    image_api_metadata_path: str | Path | None = None,
    label_api_metadata_path: str | Path | None = None,
    processed_metadata_api_path: str | Path | None = None,
) -> dict[str, Any]:
    output = prepare_output(output_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="mca-dryad-pilot-") as temp_name:
            temp = Path(temp_name)
            source_version_cache: dict[str, Any] = {}
            image_meta, images_path = resolve_dryad_file(
                config,
                config.image_file,
                local_path=image_path,
                api_metadata_path=image_api_metadata_path,
                temp=temp,
                source_version_cache=source_version_cache,
            )
            label_meta, labels_path = resolve_dryad_file(
                config,
                config.label_file,
                local_path=label_path,
                api_metadata_path=label_api_metadata_path,
                temp=temp,
                source_version_cache=source_version_cache,
            )
            metadata_meta, metadata_csv = resolve_dryad_file(
                config,
                config.processed_metadata_file,
                local_path=processed_metadata_path,
                api_metadata_path=processed_metadata_api_path,
                temp=temp,
                source_version_cache=source_version_cache,
            )
            training, training_mode = acquire_training(config, training_path, temp)
            training_hashes = verify_training(training, config)
            binding = bind_processed_metadata(metadata_csv, config)
            pair_result = inspect_pair(images_path, labels_path, config)
            overlap_rows = compare_to_training(
                pair_result.pop("standardized_patch_hashes"),
                pair_result.pop("normalized_signatures"),
                training,
                config,
            )

        patch_rows = pair_result.pop("patch_rows")
        patch_table = output / "tem_pilot_patch_inventory.csv"
        overlap_table = output / "tem_pilot_training_overlap.csv"
        binding_path = output / "pilot_source_metadata_binding.json"
        summary_path = output / "pilot_pair_audit_summary.json"
        report_path = output / "pilot_pair_audit_report.md"
        manifest_path = output / "pilot_pair_audit_artifact_manifest.json"
        write_csv(patch_table, patch_rows, PATCH_COLUMNS)
        write_csv(overlap_table, overlap_rows, OVERLAP_COLUMNS)
        write_json(binding_path, binding)

        exact = [row for row in overlap_rows if row["overlap_status"] == "exact_content_match"]
        review = [row for row in overlap_rows if row["overlap_status"] == "review_required"]
        clear = [
            row
            for row in overlap_rows
            if row["overlap_status"] == "no_content_overlap_detected"
        ]
        if len(exact) + len(review) + len(clear) != len(overlap_rows):
            raise AssertionError("overlap statuses must be mutually exhaustive.")
        overlap_clear = not exact and not review
        binding_authoritative = binding["status"] == "exact_unique_row_binding"
        data_audit_complete = binding_authoritative
        if not binding_authoritative:
            next_status = "blocked_unresolved_processed_metadata_binding"
        elif not overlap_clear:
            next_status = "blocked_by_possible_cross_dataset_content_overlap"
        else:
            next_status = (
                "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"
            )
        summary: dict[str, Any] = {
            "schema_version": "1.0",
            "case_id": config.case_id,
            "software_version": __version__,
            "source": {
                "repository": config.repository,
                "doi": config.doi,
                "published_date": config.published_date,
                "version_label": config.version_label,
                "license": config.license,
                "pilot_pair": {
                    "pair_id": config.pair_id,
                    "material": config.material,
                    "particle_diameter_nm": config.particle_diameter_nm,
                    "magnification_kx": config.magnification_kx,
                    "electron_dose_e_per_a2": config.electron_dose_e_per_a2,
                    "substrate": config.substrate,
                    "microscope": config.microscope,
                    "camera": config.camera,
                    "labeler_count": config.labeler_count,
                    "annotation_tool": config.annotation_tool,
                },
                "files": {
                    "images": image_meta,
                    "labels": label_meta,
                    "processed_metadata": metadata_meta,
                },
                "processed_metadata_binding": binding,
            },
            "hdf5_pair_audit": pair_result,
            "cobalt_training_reference": {
                "repository": config.training.repository,
                "doi": config.training.doi,
                "record_id": config.training.record_id,
                "dataset_version": config.training.dataset_version,
                "name": config.training.name,
                "acquisition_mode": training_mode,
                **training_hashes,
                "shape": list(config.training.shape),
                "candidate_parent_count": config.training.candidate_parent_count,
                "candidate_parent_patch_count": config.training.candidate_parent_patch_count,
            },
            "target_model_provenance": {
                "repository": config.notebook_repository,
                "commit": config.notebook_commit,
                "notebook": config.notebook,
                "notebook_blob_sha": config.notebook_blob_sha,
                "verified_training_input_name": config.verified_training_input_name,
                "dryad_pilot_pair_named_as_training_input": config.dryad_pilot_pair_named_as_training_input,
                "authoritative_cross_dataset_acquisition_lineage_manifest_available": config.authoritative_cross_dataset_acquisition_lineage_manifest_available,
            },
            "content_overlap_audit": {
                "exact_match_rule": config.overlap.exact_match_rule,
                "quantization_decimals": config.overlap.quantization_decimals,
                "signature_block_size": config.overlap.signature_block_size,
                "review_ncc_threshold": config.overlap.review_ncc_threshold,
                "dryad_patch_count": len(overlap_rows),
                "training_patch_count": config.training.shape[0],
                "exact_content_match_patch_count": len(exact),
                "review_required_patch_count": len(review),
                "no_detected_overlap_patch_count": len(clear),
                "maximum_signature_ncc": max(
                    float(row["best_signature_ncc"]) for row in overlap_rows
                ),
                "exact_content_matches": [
                    {
                        "dryad_patch_index": int(row["patch_index"]),
                        "training_patch_index": int(row["best_training_patch_index"]),
                        "training_candidate_parent": int(row["best_training_candidate_parent"]),
                    }
                    for row in exact
                ],
            },
            "readiness": {
                "in_domain_cobalt_oxide_external_validation": False,
                "diagnostic_cross_material_stress_test_model_evaluation_performed": False,
                "data_audit_complete": data_audit_complete,
                "processed_metadata_binding_authoritative": binding_authoritative,
                "content_overlap_gate_passed": overlap_clear,
                "next_status": next_status,
                "authoritative_cross_dataset_acquisition_independence_proven": False,
                "multi_rater_annotation_uncertainty_available": False,
            },
            "processing": {
                "raw_values_modified": False,
                "labels_remapped": False,
                "outliers_removed": False,
                "smoothing_applied": False,
                "augmentation_performed": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_accuracy_computed": False,
                "physical_size_computed": False,
                "per_patch_restandardization_for_overlap_identity_only": True,
            },
            "scientific_closeout": {
                "status": "Diagnostic",
                "result": next_status,
                "strongest_evidence": (
                    f"The exact Dryad API-bound files contain {pair_result['patch_count']} "
                    "same-index 512 x 512 image-label patches; source-declared file digests, "
                    "HDF5 structure, finite numeric values, observed label encoding, patch "
                    "intensity distributions, and content overlap against all 256 pinned "
                    "cobalt-oxide training patches were audited."
                ),
                "primary_limitation": (
                    "The pilot material is Au rather than cobalt oxide, labels were produced "
                    "by one human, one creator overlaps, authoritative cross-dataset "
                    "acquisition-lineage exclusion is unavailable, and protocol readiness "
                    "also requires exact processed-metadata row binding."
                ),
                "evidence_that_would_change_conclusion": (
                    "A predeclared cobalt-oxide set from independent acquisitions with expert "
                    "labels, immutable sample/acquisition lineage, and documented non-use in "
                    "training, tuning, threshold selection, and model selection."
                ),
                "suitable_for": [
                    "source and HDF5 contract verification",
                    "image-label pairing diagnostics",
                    "cross-dataset content-leakage screening",
                    "planning a diagnostic cross-material stress test",
                ],
                "not_suitable_for": [
                    "in-domain cobalt-oxide external-validation claims",
                    "unbiased generalization estimates",
                    "physical measurement or engineering release",
                ],
            },
        }
        write_json(summary_path, summary)
        report_path.write_text(build_report(summary), encoding="utf-8")
        write_json(
            manifest_path,
            build_manifest(
                output,
                [patch_table, overlap_table, binding_path, summary_path, report_path],
                config.case_id,
            ),
        )
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def inspect_pair(
    image_path: Path,
    label_path: Path,
    config: PilotAuditConfig,
) -> dict[str, Any]:
    patch_rows: list[dict[str, Any]] = []
    patch_hashes: list[str] = []
    signatures: list[np.ndarray] = []
    label_values_seen: set[int] = set()
    means: list[float] = []
    stds: list[float] = []
    foregrounds: list[float] = []
    patch_standardized_count = 0
    empty_count = 0
    full_count = 0

    with h5py.File(image_path, "r") as image_handle, h5py.File(
        label_path, "r"
    ) as label_handle:
        images = single_dataset(image_handle, config.hdf5.image_dataset_name, "image file")
        labels = single_dataset(label_handle, config.hdf5.label_dataset_name, "label file")
        expected_tail = (config.hdf5.patch_height, config.hdf5.patch_width)
        if images.ndim != 3 or tuple(images.shape[1:]) != expected_tail:
            raise ValueError(f"image shape {tuple(images.shape)} is not (N, 512, 512).")
        if labels.ndim != 3 or tuple(labels.shape[1:]) != expected_tail:
            raise ValueError(f"label shape {tuple(labels.shape)} is not (N, 512, 512).")
        if images.shape[0] <= 0 or images.shape[0] != labels.shape[0]:
            raise ValueError("image and label patch counts must be equal and positive.")
        if images.dtype.kind not in "fiu" or labels.dtype.kind not in "biuf":
            raise ValueError("image and label datasets must be numeric.")

        for index in range(images.shape[0]):
            image = np.asarray(images[index], dtype=np.float64)
            label = np.asarray(labels[index])
            if not np.isfinite(image).all() or not np.isfinite(label).all():
                raise ValueError(f"non-finite values in patch {index}.")
            mean = float(image.mean())
            std = float(image.std())
            if not np.isfinite(std) or std <= 0:
                raise ValueError(f"constant or invalid image patch {index}: std={std}")
            patch_standardized = (
                abs(mean) <= config.hdf5.image_mean_abs_tolerance
                and abs(std - 1.0) <= config.hdf5.image_std_abs_tolerance
            )
            patch_standardized_count += int(patch_standardized)

            label_values = normalized_label_values(label, index)
            unexpected = set(label_values) - set(config.hdf5.allowed_label_values)
            if unexpected:
                raise ValueError(
                    f"unexpected label values in patch {index}: {sorted(unexpected)}"
                )
            label_values_seen.update(label_values)
            foreground = float(np.count_nonzero(label == 1) / label.size)
            empty = foreground == 0.0
            full = foreground == 1.0
            empty_count += int(empty)
            full_count += int(full)

            comparison_values = standardize(image)
            patch_hashes.append(
                array_hash(comparison_values, config.overlap.quantization_decimals)
            )
            signatures.append(
                normalized_signature(
                    comparison_values, config.overlap.signature_block_size
                )
            )
            patch_rows.append(
                {
                    "pair_id": config.pair_id,
                    "patch_index": index,
                    "image_sha256": raw_array_hash(image),
                    "label_sha256": raw_array_hash(label),
                    "image_mean": mean,
                    "image_std": std,
                    "patch_level_zero_mean_unit_std": patch_standardized,
                    "label_values": ";".join(str(value) for value in label_values),
                    "foreground_pixel_fraction": foreground,
                    "empty_label": empty,
                    "full_label": full,
                }
            )
            means.append(mean)
            stds.append(std)
            foregrounds.append(foreground)

        return {
            "pairing_status": "same_index_structurally_validated",
            "source_reported_standardization_scope": "4096x4096_parent_image_before_512x512_patching",
            "patch_level_zero_mean_unit_std_required": False,
            "patch_level_zero_mean_unit_std_count": patch_standardized_count,
            "image_dataset_name": config.hdf5.image_dataset_name,
            "label_dataset_name": config.hdf5.label_dataset_name,
            "image_shape": list(images.shape),
            "label_shape": list(labels.shape),
            "image_dtype": str(images.dtype),
            "label_dtype": str(labels.dtype),
            "image_root_attributes": object_attributes(image_handle),
            "label_root_attributes": object_attributes(label_handle),
            "image_dataset_attributes": object_attributes(images),
            "label_dataset_attributes": object_attributes(labels),
            "patch_count": int(images.shape[0]),
            "patch_shape": list(expected_tail),
            "observed_label_values": sorted(label_values_seen),
            "empty_label_patch_count": empty_count,
            "full_label_patch_count": full_count,
            "foreground_pixel_fraction_min": min(foregrounds),
            "foreground_pixel_fraction_median": float(np.median(foregrounds)),
            "foreground_pixel_fraction_max": max(foregrounds),
            "patch_mean_min": min(means),
            "patch_mean_median": float(np.median(means)),
            "patch_mean_max": max(means),
            "patch_std_min": min(stds),
            "patch_std_median": float(np.median(stds)),
            "patch_std_max": max(stds),
            "source_values_written_to_outputs": False,
            "patch_rows": patch_rows,
            "standardized_patch_hashes": patch_hashes,
            "normalized_signatures": np.vstack(signatures),
        }


def compare_to_training(
    dryad_hashes: list[str],
    dryad_signatures: np.ndarray,
    training_path: Path,
    config: PilotAuditConfig,
) -> list[dict[str, Any]]:
    training_hashes: list[str] = []
    training_signatures: list[np.ndarray] = []
    with h5py.File(training_path, "r") as handle:
        dataset = single_dataset(handle, config.training.dataset_name, "training file")
        if tuple(dataset.shape) != config.training.shape:
            raise ValueError(
                f"training shape {tuple(dataset.shape)} != {config.training.shape}."
            )
        for index in range(dataset.shape[0]):
            patch = np.asarray(dataset[index], dtype=np.float64)
            if not np.isfinite(patch).all():
                raise ValueError(f"non-finite training patch {index}.")
            values = standardize(patch)
            training_hashes.append(
                array_hash(values, config.overlap.quantization_decimals)
            )
            training_signatures.append(
                normalized_signature(values, config.overlap.signature_block_size)
            )

    matrix = np.vstack(training_signatures)
    hash_to_indices: dict[str, list[int]] = {}
    for index, digest in enumerate(training_hashes):
        hash_to_indices.setdefault(digest, []).append(index)

    rows: list[dict[str, Any]] = []
    for patch_index, (digest, signature) in enumerate(
        zip(dryad_hashes, dryad_signatures)
    ):
        scores = matrix @ signature
        best_index = int(np.argmax(scores))
        best_ncc = float(scores[best_index])
        exact_indices = hash_to_indices.get(digest, [])
        if exact_indices:
            best_index = int(exact_indices[0])
            status = "exact_content_match"
        elif best_ncc >= config.overlap.review_ncc_threshold:
            status = "review_required"
        else:
            status = "no_content_overlap_detected"
        rows.append(
            {
                "pair_id": config.pair_id,
                "patch_index": patch_index,
                "best_training_patch_index": best_index,
                "best_training_candidate_parent": (
                    best_index // config.training.candidate_parent_patch_count
                ),
                "best_signature_ncc": max(-1.0, min(1.0, best_ncc)),
                "exact_quantized_hash_match": bool(exact_indices),
                "exact_match_training_patch_count": len(exact_indices),
                "overlap_status": status,
            }
        )
    return rows
