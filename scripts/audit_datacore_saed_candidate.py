"""Audit a public DataCORE SAED candidate without committing source microscopy files.

This probe downloads one declared ZIP file, verifies archive identity, inventories
members safely, inspects TIFF and Gatan DM4 arrays, compares corresponding
representations when possible, and records only metadata-derived evidence.
It does not tune the SAED analyzer, index reflections, assign a phase or zone
axis, or claim calibrated d-spacing accuracy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

USER_AGENT = "materials-characterization-analyzer-datacore-saed-audit/1.0"
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
METADATA_KEYWORDS = (
    "accelerating",
    "voltage",
    "camera length",
    "camera_length",
    "camera constant",
    "detector",
    "pixel size",
    "pixel_size",
    "binning",
    "exposure",
    "acquisition",
    "magnification",
    "date",
    "time",
)


class SourceAuditError(RuntimeError):
    """Raised when the public source cannot satisfy the software audit contract."""


def _request_bytes(url: str, *, timeout: int = 240) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip, */*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SourceAuditError(f"HTTP {exc.code} while downloading source: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SourceAuditError(f"Could not reach source repository: {exc.reason}") from exc
    if not payload:
        raise SourceAuditError("source repository returned an empty response")
    return payload, final_url


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    seen: set[str] = set()
    total = 0
    for info in members:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise SourceAuditError(f"unsafe ZIP member path: {info.filename}")
        normalized = path.as_posix().casefold()
        if normalized in seen:
            raise SourceAuditError(f"duplicate ZIP member path: {info.filename}")
        seen.add(normalized)
        if info.flag_bits & 0x1:
            raise SourceAuditError(f"encrypted ZIP member is unsupported: {info.filename}")
        if info.file_size > MAX_MEMBER_BYTES:
            raise SourceAuditError(f"ZIP member exceeds size limit: {info.filename}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise SourceAuditError("ZIP archive exceeds total uncompressed size limit")
    return members


def _jsonable(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return "<maximum-depth-reached>"
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, np.generic):
        return _jsonable(value.item(), depth=depth + 1)
    if isinstance(value, np.ndarray):
        if value.size <= 32:
            return _jsonable(value.tolist(), depth=depth + 1)
        return {"shape": list(value.shape), "dtype": str(value.dtype), "omitted": True}
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item, depth=depth + 1) for item in value]
    return str(value)


def _flatten(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten(item, child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            rows.extend(_flatten(item, f"{prefix}[{index}]"))
    else:
        rows.append((prefix, _jsonable(value)))
    return rows


def _selected_metadata(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for key, value in _flatten(metadata):
        normalized = re.sub(r"[_./-]+", " ", key.casefold())
        if any(keyword in normalized for keyword in METADATA_KEYWORDS):
            selected.append({"key": key, "value": value})
    return selected[:300]


def _array_record(array: np.ndarray) -> dict[str, Any]:
    data = np.asarray(array)
    finite = np.isfinite(data) if np.issubdtype(data.dtype, np.number) else None
    record: dict[str, Any] = {
        "shape": list(data.shape),
        "dtype": str(data.dtype),
        "element_count": int(data.size),
    }
    if finite is not None:
        record["all_finite"] = bool(np.all(finite))
        if data.size and np.any(finite):
            finite_values = data[finite]
            record.update(
                {
                    "minimum": float(np.min(finite_values)),
                    "maximum": float(np.max(finite_values)),
                    "mean": float(np.mean(finite_values)),
                }
            )
    return record


def _inspect_tiff(path: Path) -> tuple[dict[str, Any], list[np.ndarray]]:
    try:
        import tifffile
    except ImportError as exc:  # pragma: no cover - live workflow dependency
        raise SourceAuditError("tifffile is required for TIFF audit") from exc
    arrays: list[np.ndarray] = []
    with tifffile.TiffFile(path) as handle:
        for series in handle.series:
            arrays.append(np.asarray(series.asarray()))
        record = {
            "series_count": len(handle.series),
            "page_count": len(handle.pages),
            "byte_order": handle.byteorder,
            "is_imagej": bool(handle.is_imagej),
            "is_ome": bool(handle.is_ome),
            "arrays": [_array_record(array) for array in arrays],
        }
    return record, arrays


def _inspect_dm4(path: Path) -> tuple[dict[str, Any], list[np.ndarray]]:
    try:
        import hyperspy.api as hs
    except ImportError as exc:  # pragma: no cover - live workflow dependency
        raise SourceAuditError("hyperspy is required for DM4 audit") from exc
    loaded = hs.load(path, lazy=False)
    signals = list(loaded) if isinstance(loaded, (list, tuple)) else [loaded]
    arrays: list[np.ndarray] = []
    signal_records: list[dict[str, Any]] = []
    for signal in signals:
        array = np.asarray(signal.data)
        arrays.append(array)
        metadata = signal.metadata.as_dictionary()
        original_metadata = signal.original_metadata.as_dictionary()
        signal_records.append(
            {
                "array": _array_record(array),
                "signal_dimension": int(signal.axes_manager.signal_dimension),
                "navigation_dimension": int(signal.axes_manager.navigation_dimension),
                "axes": [
                    {
                        "name": axis.name,
                        "size": int(axis.size),
                        "scale": float(axis.scale),
                        "offset": float(axis.offset),
                        "units": axis.units,
                    }
                    for axis in signal.axes_manager
                ],
                "selected_metadata": _selected_metadata(metadata),
                "selected_original_metadata": _selected_metadata(original_metadata),
            }
        )
    return {"signal_count": len(signals), "signals": signal_records}, arrays


def _normalized_stem(path: str) -> str:
    name = PurePosixPath(path).stem.casefold()
    return re.sub(r"[^a-z0-9]+", "", name)


def _compare_arrays(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    a = np.asarray(left)
    b = np.asarray(right)
    result: dict[str, Any] = {
        "shape_equal": a.shape == b.shape,
        "dtype_equal": a.dtype == b.dtype,
        "exact_value_equal": False,
        "allclose": False,
    }
    if a.shape != b.shape:
        return result
    result["exact_value_equal"] = bool(np.array_equal(a, b, equal_nan=True))
    if np.issubdtype(a.dtype, np.number) and np.issubdtype(b.dtype, np.number):
        result["allclose"] = bool(np.allclose(a, b, rtol=1e-7, atol=1e-12, equal_nan=True))
        delta = a.astype(np.float64) - b.astype(np.float64)
        finite = np.isfinite(delta)
        if np.any(finite):
            result["maximum_absolute_difference"] = float(np.max(np.abs(delta[finite])))
            result["mean_absolute_difference"] = float(np.mean(np.abs(delta[finite])))
    return result


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise SourceAuditError("archive inventory is empty")
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(output: Path, paths: list[Path]) -> Path:
    records = []
    for path in paths:
        payload = path.read_bytes()
        records.append({"path": path.name, "bytes": len(payload), "sha256": _sha256(payload)})
    manifest_path = output / "source_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "datacore_chromium_telluride_saed_source_audit",
                "artifact_count": len(records),
                "artifacts": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def run(*, source_url: str, output: Path) -> dict[str, Any]:
    if output.exists() and (output.is_symlink() or not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    payload, final_url = _request_bytes(source_url)
    archive_sha256 = _sha256(payload)
    archive_path = output / "source.zip"
    archive_path.write_bytes(payload)

    inventory_rows: list[dict[str, Any]] = []
    inspected: dict[str, dict[str, Any]] = {}
    arrays_by_path: dict[str, list[np.ndarray]] = {}
    with zipfile.ZipFile(archive_path) as archive:
        members = _safe_members(archive)
        for info in members:
            path = PurePosixPath(info.filename).as_posix()
            member_payload = b"" if info.is_dir() else archive.read(info)
            suffix = PurePosixPath(path).suffix.casefold()
            inventory_rows.append(
                {
                    "path": path,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "sha256": "" if info.is_dir() else _sha256(member_payload),
                    "extension": suffix,
                    "is_directory": info.is_dir(),
                }
            )
            if info.is_dir() or suffix not in {".dm4", ".tif", ".tiff"}:
                continue
            extracted_path = output / "extracted" / path
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_bytes(member_payload)
            if suffix == ".dm4":
                record, arrays = _inspect_dm4(extracted_path)
            else:
                record, arrays = _inspect_tiff(extracted_path)
            inspected[path] = {
                "path": path,
                "bytes": len(member_payload),
                "sha256": _sha256(member_payload),
                "extension": suffix,
                **record,
            }
            arrays_by_path[path] = arrays

    dm4_paths = sorted(path for path in inspected if PurePosixPath(path).suffix.casefold() == ".dm4")
    tiff_paths = sorted(path for path in inspected if PurePosixPath(path).suffix.casefold() in {".tif", ".tiff"})
    tiffs_by_stem = {_normalized_stem(path): path for path in tiff_paths}
    comparisons: list[dict[str, Any]] = []
    for dm4_path in dm4_paths:
        tiff_path = tiffs_by_stem.get(_normalized_stem(dm4_path))
        if tiff_path is None:
            continue
        dm4_arrays = arrays_by_path[dm4_path]
        tiff_arrays = arrays_by_path[tiff_path]
        comparisons.append(
            {
                "dm4_path": dm4_path,
                "tiff_path": tiff_path,
                "dm4_array_count": len(dm4_arrays),
                "tiff_array_count": len(tiff_arrays),
                "array_comparisons": [
                    _compare_arrays(dm4_array, tiff_array)
                    for dm4_array, tiff_array in zip(dm4_arrays, tiff_arrays, strict=False)
                ],
            }
        )

    selected_metadata = [
        row
        for path in dm4_paths
        for signal in inspected[path].get("signals", [])
        for row in signal.get("selected_original_metadata", [])
    ]
    keys = "\n".join(str(row.get("key", "")).casefold() for row in selected_metadata)
    gates = {
        "archive_downloaded": True,
        "archive_is_valid_zip": True,
        "dm4_file_count_at_least_two": len(dm4_paths) >= 2,
        "tiff_file_count_at_least_two": len(tiff_paths) >= 2,
        "dm4_tiff_pair_count_at_least_two": len(comparisons) >= 2,
        "accelerating_voltage_metadata_found": "voltage" in keys,
        "camera_length_or_constant_metadata_found": "camera" in keys,
        "detector_metadata_found": "detector" in keys,
        "acquisition_metadata_found": "acquisition" in keys or "date" in keys or "time" in keys,
        "all_paired_arrays_exactly_equal": bool(comparisons)
        and all(
            comparison["array_comparisons"]
            and all(item["exact_value_equal"] for item in comparison["array_comparisons"])
            for comparison in comparisons
        ),
    }
    summary = {
        "schema_version": "1.0",
        "case_id": "datacore_chromium_telluride_saed_source_audit",
        "source": {
            "repository": "Indiana University DataCORE",
            "doi": "10.5967/ct7n-8275",
            "source_url": source_url.split("?", 1)[0],
            "resolved_url": final_url.split("?", 1)[0],
            "archive_bytes": len(payload),
            "archive_sha256": archive_sha256,
        },
        "counts": {
            "archive_member_count": len(inventory_rows),
            "dm4_file_count": len(dm4_paths),
            "tiff_file_count": len(tiff_paths),
            "dm4_tiff_pair_count": len(comparisons),
        },
        "inspected_files": [inspected[path] for path in sorted(inspected)],
        "representation_comparisons": comparisons,
        "evidence_gates": gates,
        "decision": {
            "raw_file_audit_completed": True,
            "eligible_for_calibrated_saed_validation_now": all(
                gates[key]
                for key in (
                    "dm4_file_count_at_least_two",
                    "dm4_tiff_pair_count_at_least_two",
                    "accelerating_voltage_metadata_found",
                    "camera_length_or_constant_metadata_found",
                    "acquisition_metadata_found",
                )
            ),
            "independent_acquisition_count_verified": False,
            "phase_or_zone_axis_claim_allowed": False,
            "d_spacing_accuracy_claim_allowed": False,
            "next_action": (
                "Review DM4 metadata and source publication, establish immutable sample/acquisition "
                "identity and calibration provenance, then freeze a validation protocol before analysis."
            ),
        },
        "scientific_boundary": {
            "source_arrays_modified": False,
            "analyzer_parameters_tuned": False,
            "saed_analysis_run": False,
            "reflection_indexing_performed": False,
            "phase_assignment_performed": False,
            "reported_zone_axes_used_as_ground_truth": False,
        },
    }

    inventory_path = output / "archive_inventory.csv"
    metadata_path = output / "source_audit_summary.json"
    _write_csv(inventory_path, inventory_rows)
    metadata_path.write_text(json.dumps(_jsonable(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive_path.unlink()
    for extracted in sorted((output / "extracted").rglob("*"), reverse=True):
        if extracted.is_file():
            extracted.unlink()
        elif extracted.is_dir():
            extracted.rmdir()
    (output / "extracted").rmdir()
    _write_manifest(output, [inventory_path, metadata_path])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(source_url=args.source_url, output=args.output)
    print(json.dumps(summary["decision"], sort_keys=True))


if __name__ == "__main__":
    main()
