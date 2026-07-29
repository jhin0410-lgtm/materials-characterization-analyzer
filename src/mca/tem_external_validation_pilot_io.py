"""I/O, hashing, and reporting helpers for the Dryad HRTEM pilot audit."""
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
    "patch_level_zero_mean_unit_std",
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


def resolve_dryad_file(
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
        else fetch_json(api_url)
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
        download(metadata["download_url"], destination)
        acquisition_mode = "downloaded_from_api_resolved_url"
    else:
        destination = Path(local_path)
        if not destination.is_file():
            raise FileNotFoundError(destination)
        acquisition_mode = "user_supplied_local_file"

    actual = file_hashes(destination)
    if actual["bytes"] != metadata["size_bytes"]:
        raise ValueError(
            f"Dryad size mismatch for {spec.name}: {actual['bytes']} != "
            f"{metadata['size_bytes']}"
        )
    algorithm = str(metadata["digest_algorithm"])
    if algorithm not in actual:
        raise ValueError(f"unsupported calculated digest algorithm: {algorithm!r}.")
    if actual[algorithm] != metadata["digest"]:
        raise ValueError(
            f"Dryad {algorithm} mismatch for {spec.name}: {actual[algorithm]} != "
            f"{metadata['digest']}"
        )
    metadata.update(actual)
    metadata["source_digest_verified"] = True
    metadata["acquisition_mode"] = acquisition_mode
    return metadata, destination


def acquire_training(
    config: PilotAuditConfig,
    local_path: str | Path | None,
    temp: Path,
) -> tuple[Path, str]:
    if local_path is not None:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path, "user_supplied_local_file"
    destination = temp / config.training.name
    download(config.training.url, destination)
    return destination, "downloaded_from_pinned_zenodo_url"


def verify_training(path: Path, config: PilotAuditConfig) -> dict[str, Any]:
    hashes = file_hashes(path)
    if hashes["md5"] != config.training.md5:
        raise ValueError("pinned cobalt training MD5 mismatch.")
    if hashes["sha256"] != config.training.sha256:
        raise ValueError("pinned cobalt training SHA-256 mismatch.")
    return hashes


def bind_processed_metadata(path: Path, config: PilotAuditConfig) -> dict[str, Any]:
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


def single_dataset(handle: h5py.File, name: str, label: str) -> h5py.Dataset:
    keys = list(handle.keys())
    if keys != [name]:
        raise ValueError(f"{label} must contain only dataset {name!r}; observed {keys!r}.")
    dataset = handle[name]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"{label} entry {name!r} is not a dataset.")
    return dataset


def object_attributes(obj: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in obj.attrs.items():
        array = np.asarray(value)
        if array.ndim == 0:
            result[str(key)] = json_scalar(array.item())
        else:
            result[str(key)] = [json_scalar(item) for item in array.ravel().tolist()]
    return result


def json_scalar(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalized_label_values(label: np.ndarray, patch_index: int) -> list[int]:
    values: list[int] = []
    for value in np.unique(label).tolist():
        numeric = float(value)
        if not numeric.is_integer():
            raise ValueError(f"non-integer label value in patch {patch_index}: {value}")
        values.append(int(numeric))
    return values


def standardize(values: np.ndarray) -> np.ndarray:
    mean = float(values.mean())
    std = float(values.std())
    if not math.isfinite(std) or std <= 0:
        raise ValueError("cannot standardize a constant or non-finite patch.")
    return (values - mean) / std


def array_hash(values: np.ndarray, decimals: int) -> str:
    rounded = np.round(np.asarray(values, dtype=np.float64), decimals=decimals)
    return hashlib.sha256(np.ascontiguousarray(rounded).tobytes()).hexdigest()


def raw_array_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def normalized_signature(values: np.ndarray, block: int) -> np.ndarray:
    height, width = values.shape
    signature = values.reshape(
        height // block, block, width // block, block
    ).mean(axis=(1, 3)).ravel()
    centered = signature - signature.mean()
    norm = float(np.linalg.norm(centered))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("cannot calculate NCC for a constant block signature.")
    return centered / norm


def fetch_json(url: str, attempts: int = 5) -> Mapping[str, Any]:
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


def download(url: str, destination: Path, attempts: int = 5) -> None:
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


def file_hashes(path: Path) -> dict[str, Any]:
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


def prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    return output


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_manifest(output: Path, paths: Sequence[Path], case_id: str) -> dict[str, Any]:
    records = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "artifact_count": len(records),
        "artifacts": records,
    }


def build_report(summary: Mapping[str, Any]) -> str:
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
            f"- Patch-level zero-mean/unit-std count: `{pair['patch_level_zero_mean_unit_std_count']}`",
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
            "The source reports standardization of 4096 x 4096 parent images before patching;",
            "individual 512 x 512 patches are not required to retain mean 0 and standard deviation 1.",
            "No model was trained or executed and no segmentation performance metric was computed.",
            "",
        ]
    )
