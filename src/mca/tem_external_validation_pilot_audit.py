"""Checksum-bound real-data audit for one Dryad HRTEM image-label pair.

The audit validates repository metadata, downloaded bytes, HDF5 structure, patch
pairing, label values, image standardization, and content overlap against the
pinned cobalt-oxide training patches. It performs no model training or inference.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

import h5py
import numpy as np

from . import __version__
from .tem_external_validation_pilot_contract import (
    PilotAuditConfig,
    RemoteFileSpec,
    normalize_dryad_file_metadata,
)

PATCH_COLUMNS = (
    "pair_id",
    "patch_index",
    "image_sha256",
    "label_sha256",
    "image_mean",
    "image_std",
    "label_values",
    "foreground_pixel_fraction",
    "empty_label",
    "full_label",
)
OVERLAP_COLUMNS = (
    "pair_id",
    "patch_index",
    "best_training_patch_index",
    "best_training_candidate_parent",
    "best_signature_ncc",
    "exact_quantized_hash_match",
    "exact_match_training_patch_count",
    "overlap_status",
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
    output = _prepare_output(output_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="mca-dryad-pilot-") as temp_name:
            temp = Path(temp_name)
            image_meta, image = _resolve_dryad_file(
                config,
                config.image_file,
                local_path=image_path,
                api_metadata_path=image_api_metadata_path,
                temp=temp,
            )
            label_meta, labels = _resolve_dryad_file(
                config,
                config.label_file,
                local_path=label_path,
                api_metadata_path=label_api_metadata_path,
                temp=temp,
            )
            metadata_meta, metadata_csv = _resolve_dryad_file(
                config,
                config.processed_metadata_file,
                local_path=processed_metadata_path,
                api_metadata_path=processed_metadata_api_path,
                temp=temp,
            )
            training, training_mode = _acquire_training(config, training_path, temp)
            training_hashes = _verify_training(training, config)
            binding = _bind_processed_metadata(metadata_csv, config)
            pair_result = _inspect_pair(image, labels, config)
            overlap_rows = _compare_to_training(
                pair_result.pop("standardized_patch_hashes"),
                pair_result.pop("normalized_signatures"),
                training,
                config,
            )

        patch_table = output / "tem_pilot_patch_inventory.csv"
        overlap_table = output / "tem_pilot_training_overlap.csv"
        source_metadata_path = output / "pilot_source_metadata_binding.json"
        summary_path = output / "pilot_pair_audit_summary.json"
        report_path = output / "pilot_pair_audit_report.md"
        manifest_path = output / "pilot_pair_audit_artifact_manifest.json"

        _write_csv(patch_table, pair_result.pop("patch_rows"), PATCH_COLUMNS)
        _write_csv(overlap_table, overlap_rows, OVERLAP_COLUMNS)
        _write_json(source_metadata_path, binding)

        exact_rows = [row for row in overlap_rows if row["exact_quantized_hash_match"]]
        review_rows = [row for row in overlap_rows if row["overlap_status"] == "review_required"]
        overlap_clear = not exact_rows and not review_rows
        next_status = (
            "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"
            if overlap_clear
            else "blocked_by_possible_cross_dataset_content_overlap"
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
                "exact_content_match_patch_count": len(exact_rows),
                "review_required_patch_count": len(review_rows),
                "no_detected_overlap_patch_count": len(overlap_rows) - len(review_rows),
                "maximum_signature_ncc": max(
                    float(row["best_signature_ncc"]) for row in overlap_rows
                ),
                "exact_content_matches": [
                    {
                        "dryad_patch_index": int(row["patch_index"]),
                        "training_patch_index": int(row["best_training_patch_index"]),
                        "training_candidate_parent": int(
                            row["best_training_candidate_parent"]
                        ),
                    }
                    for row in exact_rows
                ],
            },
            "readiness": {
                "in_domain_cobalt_oxide_external_validation": False,
                "diagnostic_cross_material_stress_test_model_evaluation_performed": False,
                "data_audit_complete": True,
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
                    f"The exact Dryad API-bound image and label files contain "
                    f"{pair_result['patch_count']} same-index 512 x 512 patches; file bytes, "
                    "HDF5 structure, numeric standardization, binary labels, and content overlap "
                    "against all 256 pinned cobalt-oxide training patches were audited."
                ),
                "primary_limitation": (
                    "The pilot material is Au rather than cobalt oxide, one source creator overlaps, "
                    "the labels were produced by one human, and no authoritative cross-dataset "
                    "acquisition-lineage exclusion manifest is available."
                ),
                "evidence_that_would_change_conclusion": (
                    "A predeclared cobalt-oxide image set from independent acquisitions with expert "
                    "labels, immutable sample/acquisition lineage, and documented non-use in training, "
                    "tuning, threshold selection, and model selection."
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
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary), encoding="utf-8")
        manifest = _build_manifest(
            output,
            [patch_table, overlap_table, source_metadata_path, summary_path, report_path],
            config.case_id,
        )
        _write_json(manifest_path, manifest)
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _resolve_dryad_file(
    config: PilotAuditConfig,
    spec: RemoteFileSpec,
    *,
    local_path: str | Path | None,
    api_metadata_path: str | Path | None,
    temp: Path,
) -> tuple[dict[str, Any], Path]:
    api_url = config.api_file_endpoint_template.format(file_id=spec.file_id)
    raw_payload = (
        json.loads(Path(api_metadata_path).read_text(encoding="utf-8"))
        if api_metadata_path is not None
        else _fetch_json(api_url)
    )
    if not isinstance(raw_payload, Mapping):
        raise ValueError(f"Dryad API response for {spec.name} is not an object.")
    fallback_url = config.download_endpoint_template.format(file_id=spec.file_id)
    metadata = normalize_dryad_file_metadata(raw_payload, spec, fallback_url)
    metadata["api_url"] = api_url
    metadata["api_response_sha256"] = hashlib.sha256(
        json.dumps(raw_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    if local_path is None:
        destination = temp / spec.name
        _download(metadata["download_url"], destination)
        acquisition_mode = "downloaded_from_api_resolved_url"
    else:
        destination = Path(local_path)
        if not destination.is_file():
            raise FileNotFoundError(destination)
        acquisition_mode = "user_supplied_local_file"
    actual = _file_hashes(destination)
    if destination.stat().st_size != metadata["size_bytes"]:
        raise ValueError(
            f"Dryad size mismatch for {spec.name}: {destination.stat().st_size} != "
            f"{metadata['size_bytes']}"
        )
    if actual["md5"] != metadata["digest"]:
        raise ValueError(
            f"Dryad MD5 mismatch for {spec.name}: {actual['md5']} != {metadata['digest']}"
        )
    metadata.update(actual)
    metadata["acquisition_mode"] = acquisition_mode
    return metadata, destination


def _acquire_training(
    config: PilotAuditConfig, local_path: str | Path | None, temp: Path
) -> tuple[Path, str]:
    if local_path is not None:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path, "user_supplied_local_file"
    destination = temp / config.training.name
    _download(config.training.url, destination)
    return destination, "downloaded_from_pinned_zenodo_url"


def _verify_training(path: Path, config: PilotAuditConfig) -> dict[str, Any]:
    hashes = _file_hashes(path)
    if hashes["md5"] != config.training.md5:
        raise ValueError("pinned cobalt training MD5 mismatch.")
    if hashes["sha256"] != config.training.sha256:
        raise ValueError("pinned cobalt training SHA-256 mismatch.")
    return hashes


def _inspect_pair(image_path: Path, label_path: Path, config: PilotAuditConfig) -> dict[str, Any]:
    patch_rows: list[dict[str, Any]] = []
    patch_hashes: list[str] = []
    signatures: list[np.ndarray] = []
    label_values_seen: set[int] = set()
    image_means: list[float] = []
    image_stds: list[float] = []
    foreground_fractions: list[float] = []
    empty_count = 0
    full_count = 0

    with h5py.File(image_path, "r") as image_handle, h5py.File(label_path, "r") as label_handle:
        images = _single_dataset(image_handle, config.hdf5.image_dataset_name, "image file")
        labels = _single_dataset(label_handle, config.hdf5.label_dataset_name, "label file")
        expected_tail = (config.hdf5.patch_height, config.hdf5.patch_width)
        if images.ndim != 3 or tuple(images.shape[1:]) != expected_tail:
            raise ValueError(f"image shape {tuple(images.shape)} is not (N, {expected_tail[0]}, {expected_tail[1]}).")
        if labels.ndim != 3 or tuple(labels.shape[1:]) != expected_tail:
            raise ValueError(f"label shape {tuple(labels.shape)} is not (N, {expected_tail[0]}, {expected_tail[1]}).")
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
            if abs(mean) > config.hdf5.image_mean_abs_tolerance:
                raise ValueError(f"image patch {index} mean drift: {mean}")
            if abs(std - 1.0) > config.hdf5.image_std_abs_tolerance:
                raise ValueError(f"image patch {index} standard deviation drift: {std}")
            unique = np.unique(label)
            normalized_values: list[int] = []
            for value in unique.tolist():
                numeric = float(value)
                if not numeric.is_integer():
                    raise ValueError(f"non-integer label value in patch {index}: {value}")
                normalized_values.append(int(numeric))
            unexpected = set(normalized_values) - set(config.hdf5.allowed_label_values)
            if unexpected:
                raise ValueError(f"unexpected label values in patch {index}: {sorted(unexpected)}")
            label_values_seen.update(normalized_values)
            foreground = float(np.count_nonzero(label == 1) / label.size)
            empty = foreground == 0.0
            full = foreground == 1.0
            empty_count += int(empty)
            full_count += int(full)
            standardized = _standardize(image)
            patch_hash = _array_hash(standardized, config.overlap.quantization_decimals)
            signature = _normalized_signature(
                standardized, config.overlap.signature_block_size
            )
            patch_rows.append(
                {
                    "pair_id": config.pair_id,
                    "patch_index": index,
                    "image_sha256": _raw_array_hash(image),
                    "label_sha256": _raw_array_hash(label),
                    "image_mean": mean,
                    "image_std": std,
                    "label_values": ";".join(str(value) for value in normalized_values),
                    "foreground_pixel_fraction": foreground,
                    "empty_label": empty,
                    "full_label": full,
                }
            )
            patch_hashes.append(patch_hash)
            signatures.append(signature)
            image_means.append(mean)
            image_stds.append(std)
            foreground_fractions.append(foreground)

        return {
            "pairing_status": "same_index_structurally_validated",
            "image_dataset_name": config.hdf5.image_dataset_name,
            "label_dataset_name": config.hdf5.label_dataset_name,
            "image_shape": list(images.shape),
            "label_shape": list(labels.shape),
            "image_dtype": str(images.dtype),
            "label_dtype": str(labels.dtype),
            "image_root_attributes": _attributes(image_handle),
            "label_root_attributes": _attributes(label_handle),
            "image_dataset_attributes": _attributes(images),
            "label_dataset_attributes": _attributes(labels),
            "patch_count": int(images.shape[0]),
            "patch_shape": list(expected_tail),
            "observed_label_values": sorted(label_values_seen),
            "empty_label_patch_count": empty_count,
            "full_label_patch_count": full_count,
            "foreground_pixel_fraction_min": min(foreground_fractions),
            "foreground_pixel_fraction_median": float(np.median(foreground_fractions)),
            "foreground_pixel_fraction_max": max(foreground_fractions),
            "maximum_image_mean_abs": max(abs(value) for value in image_means),
            "maximum_image_std_abs_error": max(abs(value - 1.0) for value in image_stds),
            "source_values_written_to_outputs": False,
            "patch_rows": patch_rows,
            "standardized_patch_hashes": patch_hashes,
            "normalized_signatures": np.vstack(signatures),
        }


def _compare_to_training(
    dryad_hashes: Sequence[str],
    dryad_signatures: np.ndarray,
    training_path: Path,
    config: PilotAuditConfig,
) -> list[dict[str, Any]]:
    training_hashes: list[str] = []
    training_signatures: list[np.ndarray] = []
    with h5py.File(training_path, "r") as handle:
        dataset = _single_dataset(handle, config.training.dataset_name, "training file")
        if tuple(dataset.shape) != config.training.shape:
            raise ValueError(
                f"training shape {tuple(dataset.shape)} != {config.training.shape}."
            )
        for index in range(dataset.shape[0]):
            patch = np.asarray(dataset[index], dtype=np.float64)
            if not np.isfinite(patch).all():
                raise ValueError(f"non-finite training patch {index}.")
            standardized = _standardize(patch)
            training_hashes.append(
                _array_hash(standardized, config.overlap.quantization_decimals)
            )
            training_signatures.append(
                _normalized_signature(standardized, config.overlap.signature_block_size)
            )
    training_matrix = np.vstack(training_signatures)
    hash_to_indices: dict[str, list[int]] = {}
    for index, digest in enumerate(training_hashes):
        hash_to_indices.setdefault(digest, []).append(index)

    rows: list[dict[str, Any]] = []
    for patch_index, (digest, signature) in enumerate(zip(dryad_hashes, dryad_signatures)):
        scores = training_matrix @ signature
        best_index = int(np.argmax(scores))
        best_ncc = float(scores[best_index])
        exact_indices = hash_to_indices.get(digest, [])
        exact = bool(exact_indices)
        if exact:
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
                "exact_quantized_hash_match": exact,
                "exact_match_training_patch_count": len(exact_indices),
                "overlap_status": status,
            }
        )
    return rows


def _bind_processed_metadata(path: Path, config: PilotAuditConfig) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError("processed metadata CSV has no header.")
    rows = list(reader)
    exact: list[dict[str, str]] = []
    prefix: list[dict[str, str]] = []
    pair_prefix = config.image_file.name.removesuffix("_Images.h5")
    for row in rows:
        values = {str(value).strip() for value in row.values() if value is not None}
        if config.image_file.name in values and config.label_file.name in values:
            exact.append(row)
        elif any(pair_prefix in value for value in values):
            prefix.append(row)
    if len(exact) == 1:
        status = "exact_unique_row_binding"
        selected = exact[0]
    elif not exact and len(prefix) == 1:
        status = "unique_prefix_candidate_not_authoritative"
        selected = prefix[0]
    else:
        status = "unresolved_metadata_row_binding"
        selected = None
    return {
        "status": status,
        "header": list(reader.fieldnames),
        "row_count": len(rows),
        "exact_match_count": len(exact),
        "prefix_candidate_count": len(prefix),
        "selected_row": selected,
        "authoritative_patch_to_raw_parent_mapping_available": False,
    }


def _single_dataset(handle: h5py.File, name: str, label: str) -> h5py.Dataset:
    keys = list(handle.keys())
    if keys != [name]:
        raise ValueError(f"{label} must contain only dataset {name!r}; observed {keys!r}.")
    dataset = handle[name]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"{label} entry {name!r} is not a dataset.")
    return dataset


def _attributes(obj: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in obj.attrs.items():
        array = np.asarray(value)
        if array.ndim == 0:
            scalar = array.item()
            result[str(key)] = _json_scalar(scalar)
        else:
            result[str(key)] = [_json_scalar(item) for item in array.ravel().tolist()]
    return result


def _json_scalar(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _standardize(values: np.ndarray) -> np.ndarray:
    mean = float(values.mean())
    std = float(values.std())
    if not math.isfinite(std) or std <= 0:
        raise ValueError("cannot standardize a constant or non-finite patch.")
    return (values - mean) / std


def _array_hash(values: np.ndarray, decimals: int) -> str:
    rounded = np.round(np.asarray(values, dtype=np.float64), decimals=decimals)
    return hashlib.sha256(np.ascontiguousarray(rounded).tobytes()).hexdigest()


def _raw_array_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def _normalized_signature(values: np.ndarray, block: int) -> np.ndarray:
    height, width = values.shape
    signature = values.reshape(
        height // block, block, width // block, block
    ).mean(axis=(1, 3)).ravel()
    centered = signature - signature.mean()
    norm = float(np.linalg.norm(centered))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("cannot calculate NCC for a constant block signature.")
    return centered / norm


def _fetch_json(url: str, attempts: int = 5) -> Mapping[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "materials-characterization-analyzer/0.9"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("remote JSON response is not an object.")
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch JSON from {url}") from last_error


def _download(url: str, destination: Path, attempts: int = 5) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(attempts):
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "materials-characterization-analyzer/0.9"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            os.replace(partial, destination)
            return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


def _file_hashes(path: Path) -> dict[str, Any]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {
        "bytes": path.stat().st_size,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _build_manifest(output: Path, paths: Sequence[Path], case_id: str) -> dict[str, Any]:
    records = []
    for path in paths:
        records.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    pair = summary["hdf5_pair_audit"]
    overlap = summary["content_overlap_audit"]
    readiness = summary["readiness"]
    binding = summary["source"]["processed_metadata_binding"]
    return "\n".join(
        [
            "# Dryad HRTEM Pilot Pair Audit",
            "",
            f"- Evidence level: **{summary['scientific_closeout']['status']}**",
            f"- Result: `{summary['scientific_closeout']['result']}`",
            f"- Pair: `{summary['source']['pilot_pair']['pair_id']}`",
            f"- Material: `{summary['source']['pilot_pair']['material']}`",
            f"- Same-index image-label patches: `{pair['patch_count']}`",
            f"- Image shape: `{pair['image_shape']}`",
            f"- Label shape: `{pair['label_shape']}`",
            f"- Observed label values: `{pair['observed_label_values']}`",
            f"- Exact cobalt-training content matches: `{overlap['exact_content_match_patch_count']}`",
            f"- NCC review-required patches: `{overlap['review_required_patch_count']}`",
            f"- Maximum block-signature NCC: `{overlap['maximum_signature_ncc']}`",
            f"- Processed metadata binding: `{binding['status']}`",
            f"- Cross-material content-overlap gate passed: `{readiness['content_overlap_gate_passed']}`",
            "",
            "## Scientific boundary",
            "",
            summary["scientific_closeout"]["primary_limitation"],
            "",
            "No model was trained or executed and no segmentation performance metric was computed.",
            "This pair remains cross-material diagnostic evidence, not in-domain cobalt-oxide external validation.",
            "",
        ]
    )
