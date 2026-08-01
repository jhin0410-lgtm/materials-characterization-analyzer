"""Checksum-bound audit for the PhaseT3M Co3O4 processed tilt-series candidate."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

import h5py
import numpy as np

from . import __version__

CASE_ID = "phaset3m_co3o4_tilt_series_candidate_audit"
SCHEMA_VERSION = "1.0"
RESULT = "processed_single_particle_diagnostic_only"


class PhaseT3MContractError(ValueError):
    """Raised when the pinned source contract or archive is invalid."""


@dataclass(frozen=True)
class AuditConfig:
    case_id: str
    record_id: int
    doi: str
    record_url: str
    title: str
    archive_name: str
    archive_md5: str
    target_member_basename: str
    source_material: str
    source_particle_count: int
    source_processing: tuple[str, ...]
    target_training_creator_overlap: bool
    reuse_license: str
    reuse_license_verified: bool
    max_member_count: int
    max_single_member_bytes: int
    max_total_uncompressed_bytes: int
    max_compression_ratio: float
    max_sample_values_per_dataset: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AuditConfig":
        _reject_unknown(
            payload,
            {"case_id", "source", "scientific_contract", "archive_safety", "inspection"},
            "config",
        )
        source = _mapping(payload, "source")
        contract = _mapping(payload, "scientific_contract")
        safety = _mapping(payload, "archive_safety")
        inspection = _mapping(payload, "inspection")
        _reject_unknown(
            source,
            {
                "record_id",
                "doi",
                "record_url",
                "title",
                "archive_name",
                "archive_md5",
                "target_member_basename",
                "source_material",
                "source_particle_count",
                "source_processing",
                "target_training_creator_overlap",
                "reuse_license",
                "reuse_license_verified",
            },
            "source",
        )
        _reject_unknown(
            contract,
            {
                "minimum_independent_samples",
                "minimum_independent_acquisitions",
                "raw_or_demonstrably_lossless_required",
                "independent_labels_required",
            },
            "scientific_contract",
        )
        _reject_unknown(
            safety,
            {
                "max_member_count",
                "max_single_member_bytes",
                "max_total_uncompressed_bytes",
                "max_compression_ratio",
            },
            "archive_safety",
        )
        _reject_unknown(
            inspection,
            {"max_sample_values_per_dataset"},
            "inspection",
        )
        if _integer(contract, "minimum_independent_samples") != 2:
            raise PhaseT3MContractError("minimum_independent_samples must remain 2")
        if _integer(contract, "minimum_independent_acquisitions") != 2:
            raise PhaseT3MContractError(
                "minimum_independent_acquisitions must remain 2"
            )
        for key in (
            "raw_or_demonstrably_lossless_required",
            "independent_labels_required",
        ):
            if not _boolean(contract, key):
                raise PhaseT3MContractError(f"{key} must remain true")
        config = cls(
            case_id=_text(payload, "case_id"),
            record_id=_integer(source, "record_id"),
            doi=_text(source, "doi"),
            record_url=_https(source, "record_url"),
            title=_text(source, "title"),
            archive_name=_filename(source, "archive_name"),
            archive_md5=_hex(source, "archive_md5", 32),
            target_member_basename=_filename(source, "target_member_basename"),
            source_material=_text(source, "source_material"),
            source_particle_count=_integer(source, "source_particle_count"),
            source_processing=_texts(source, "source_processing"),
            target_training_creator_overlap=_boolean(
                source, "target_training_creator_overlap"
            ),
            reuse_license=_text(source, "reuse_license"),
            reuse_license_verified=_boolean(source, "reuse_license_verified"),
            max_member_count=_positive_integer(safety, "max_member_count"),
            max_single_member_bytes=_positive_integer(
                safety, "max_single_member_bytes"
            ),
            max_total_uncompressed_bytes=_positive_integer(
                safety, "max_total_uncompressed_bytes"
            ),
            max_compression_ratio=_positive_float(safety, "max_compression_ratio"),
            max_sample_values_per_dataset=_positive_integer(
                inspection, "max_sample_values_per_dataset"
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise PhaseT3MContractError(f"case_id must equal {CASE_ID!r}")
        if self.record_id != 17336678:
            raise PhaseT3MContractError("record_id must remain pinned to 17336678")
        if self.doi != "10.5281/zenodo.17336678":
            raise PhaseT3MContractError("unexpected PhaseT3M DOI")
        if self.archive_name != "raw_tilt_data.zip":
            raise PhaseT3MContractError("unexpected archive_name")
        if self.target_member_basename != "Co3O4_denoised_tilt_series.h5":
            raise PhaseT3MContractError("unexpected target HDF5 basename")
        if self.source_material.casefold() != "co3o4":
            raise PhaseT3MContractError("source_material must be Co3O4")
        if self.source_particle_count != 1:
            raise PhaseT3MContractError(
                "source_particle_count must preserve the single-particle source claim"
            )
        required_processing = {"motion_corrected", "tilt_aligned", "denoised"}
        if not required_processing.issubset(set(self.source_processing)):
            raise PhaseT3MContractError(
                "source_processing must include motion_corrected, tilt_aligned, and denoised"
            )
        if not self.target_training_creator_overlap:
            raise PhaseT3MContractError(
                "target_training_creator_overlap must remain true for this source"
            )
        if self.max_single_member_bytes > self.max_total_uncompressed_bytes:
            raise PhaseT3MContractError(
                "max_single_member_bytes cannot exceed max_total_uncompressed_bytes"
            )
        if self.max_sample_values_per_dataset > 5_000_000:
            raise PhaseT3MContractError(
                "max_sample_values_per_dataset is unreasonably large"
            )


def load_config(path: str | Path) -> AuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise PhaseT3MContractError("config must contain a JSON object")
    return AuditConfig.from_mapping(payload)


def audit_phaset3m_candidate(
    config: AuditConfig,
    archive_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    archive = Path(archive_path)
    if not archive.is_file() or archive.is_symlink():
        raise FileNotFoundError(f"archive is not a regular file: {archive}")
    output, created_output = _prepare_output(output_dir)
    try:
        archive_hashes = _hashes(archive)
        if archive_hashes["md5"] != config.archive_md5:
            raise PhaseT3MContractError(
                "archive MD5 mismatch: "
                f"{archive_hashes['md5']} != {config.archive_md5}"
            )
        archive_rows, target_member = _inspect_archive(config, archive)
        with tempfile.TemporaryDirectory(prefix="mca-phaset3m-") as temp_name:
            extracted = Path(temp_name) / config.target_member_basename
            with zipfile.ZipFile(archive) as bundle, bundle.open(target_member) as source:
                with extracted.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
            if extracted.stat().st_size != target_member.file_size:
                raise PhaseT3MContractError(
                    "extracted HDF5 byte size does not match ZIP member metadata"
                )
            hdf5 = _inspect_hdf5(config, extracted)

        gates = {
            "archive_checksum_verified": True,
            "archive_member_inventory_verified": True,
            "target_hdf5_member_unique": True,
            "target_hdf5_structure_inspected": True,
            "exact_material_supported_by_source": True,
            "raw_detector_or_demonstrably_lossless_representation": False,
            "source_processing_is_predeclared": True,
            "minimum_two_independent_samples_available": False,
            "minimum_two_independent_acquisitions_available": False,
            "immutable_sample_ids_available": False,
            "immutable_acquisition_ids_available": False,
            "independent_segmentation_labels_available": False,
            "target_training_nonuse_verified": False,
            "target_creator_overlap_absent": False,
            "reuse_license_verified": config.reuse_license_verified,
            "ready_for_blinded_annotation_pilot": False,
            "ready_for_predeclared_external_evaluation": False,
        }
        blockers = [
            "source_representation_is_motion_corrected_tilt_aligned_and_denoised",
            "only_one_source_particle_reported",
            "independent_acquisition_count_not_established",
            "immutable_sample_and_acquisition_ids_unavailable",
            "independent_segmentation_labels_unavailable",
            "target_model_development_nonuse_unverified",
            "target_training_creator_overlap",
        ]
        if not config.reuse_license_verified:
            blockers.append("reuse_license_unverified")
        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "source": {
                "repository": "Zenodo",
                "record_id": config.record_id,
                "doi": config.doi,
                "record_url": config.record_url,
                "title": config.title,
                "archive_name": config.archive_name,
                "archive_bytes": archive.stat().st_size,
                "archive_md5": archive_hashes["md5"],
                "archive_sha256": archive_hashes["sha256"],
                "target_member": target_member.filename,
                "target_member_bytes": target_member.file_size,
                "source_material": config.source_material,
                "source_particle_count": config.source_particle_count,
                "source_processing": list(config.source_processing),
                "reuse_license": config.reuse_license,
                "reuse_license_verified": config.reuse_license_verified,
            },
            "archive_audit": {
                "member_count": len(archive_rows),
                "total_uncompressed_bytes": sum(
                    int(row["uncompressed_bytes"]) for row in archive_rows
                ),
                "target_member_count": sum(
                    bool(row["is_target_member"]) for row in archive_rows
                ),
            },
            "hdf5_audit": hdf5,
            "scientific_gates": gates,
            "blockers": blockers,
            "processing": {
                "source_archive_modified": False,
                "source_hdf5_modified": False,
                "source_arrays_exported": False,
                "labels_created": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_metrics_computed": False,
            },
            "scientific_closeout": {
                "status": "Diagnostic",
                "result": RESULT,
                "strongest_evidence": (
                    "The checksum-bound Zenodo archive contains one uniquely identified "
                    "Co3O4 HDF5 tilt-series member whose structure and source processing "
                    "state were inspected without exporting or modifying source arrays."
                ),
                "primary_limitation": (
                    "The source describes one nanoparticle and a motion-corrected, "
                    "tilt-aligned, denoised representation; it does not provide the "
                    "independent raw/lossless multi-sample acquisition and blinded labels "
                    "required for external segmentation validation."
                ),
                "evidence_that_would_change_conclusion": (
                    "Author-released raw detector frames with immutable sample and "
                    "acquisition IDs for at least two independent samples/acquisitions, "
                    "verified target-model non-use, content-overlap clearance, and two "
                    "blinded labels plus adjudicated consensus."
                ),
                "suitable_for": [
                    "HDF5 ingestion diagnostics",
                    "processed exact-material robustness exploration",
                    "tomography data-contract development",
                ],
                "not_suitable_for": [
                    "external segmentation accuracy estimation",
                    "model selection or retraining",
                    "independent generalization claims",
                    "engineering release",
                ],
            },
        }
        inventory_path = output / "phaset3m_archive_inventory.csv"
        hdf5_path = output / "phaset3m_hdf5_inventory.json"
        summary_path = output / "phaset3m_candidate_audit_summary.json"
        report_path = output / "phaset3m_candidate_audit_report.md"
        manifest_path = output / "phaset3m_candidate_audit_manifest.json"
        _write_csv(inventory_path, archive_rows)
        _write_json(hdf5_path, hdf5)
        _write_json(summary_path, summary)
        report_path.write_text(_report(summary), encoding="utf-8")
        _write_json(
            manifest_path,
            _manifest(output, [inventory_path, hdf5_path, summary_path, report_path]),
        )
        return summary
    except Exception:
        if output.exists() and output.is_dir() and not output.is_symlink():
            if created_output:
                shutil.rmtree(output, ignore_errors=True)
            else:
                for child in output.iterdir():
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
        raise


def _inspect_archive(
    config: AuditConfig, archive: Path
) -> tuple[list[dict[str, Any]], zipfile.ZipInfo]:
    rows: list[dict[str, Any]] = []
    targets: list[zipfile.ZipInfo] = []
    total_uncompressed = 0
    seen_paths: set[str] = set()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if not members:
            raise PhaseT3MContractError("archive is empty")
        if len(members) > config.max_member_count:
            raise PhaseT3MContractError("archive member count exceeds configured limit")
        for info in members:
            normalized = _safe_member_name(info.filename)
            if normalized in seen_paths:
                raise PhaseT3MContractError(
                    f"duplicate normalized ZIP member path: {normalized}"
                )
            seen_paths.add(normalized)
            mode = (info.external_attr >> 16) & 0xFFFF
            is_symlink = stat.S_ISLNK(mode)
            if is_symlink:
                raise PhaseT3MContractError(
                    f"symbolic-link ZIP member is not allowed: {info.filename}"
                )
            encrypted = bool(info.flag_bits & 0x1)
            if encrypted:
                raise PhaseT3MContractError(
                    f"encrypted ZIP member is not allowed: {info.filename}"
                )
            if info.file_size > config.max_single_member_bytes:
                raise PhaseT3MContractError(
                    f"ZIP member exceeds configured size limit: {info.filename}"
                )
            total_uncompressed += info.file_size
            if total_uncompressed > config.max_total_uncompressed_bytes:
                raise PhaseT3MContractError(
                    "ZIP total uncompressed size exceeds configured limit"
                )
            ratio = (
                float(info.file_size) / max(1, int(info.compress_size))
                if info.file_size
                else 0.0
            )
            if info.file_size >= 1024 * 1024 and ratio > config.max_compression_ratio:
                raise PhaseT3MContractError(
                    f"ZIP compression ratio exceeds configured limit: {info.filename}"
                )
            is_target = (
                not info.is_dir()
                and PurePosixPath(normalized).name == config.target_member_basename
            )
            if is_target:
                targets.append(info)
            rows.append(
                {
                    "member_path": normalized,
                    "uncompressed_bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "compression_ratio": round(ratio, 6),
                    "crc32": f"{info.CRC:08x}",
                    "compression_method": info.compress_type,
                    "encrypted": encrypted,
                    "is_symlink": is_symlink,
                    "is_directory": info.is_dir(),
                    "suffix": PurePosixPath(normalized).suffix.lower(),
                    "is_target_member": is_target,
                }
            )
    if len(targets) != 1:
        raise PhaseT3MContractError(
            "expected exactly one target HDF5 member; "
            f"found {len(targets)}"
        )
    return rows, targets[0]


def _inspect_hdf5(config: AuditConfig, path: Path) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    with h5py.File(path, "r") as handle:
        root_attrs = _attrs(handle.attrs)

        def visitor(name: str, item: h5py.Group | h5py.Dataset) -> None:
            if isinstance(item, h5py.Group):
                groups.append(
                    {
                        "path": f"/{name}" if name else "/",
                        "attribute_count": len(item.attrs),
                        "attributes": _attrs(item.attrs),
                    }
                )
                return
            record: dict[str, Any] = {
                "path": f"/{name}",
                "shape": list(item.shape),
                "ndim": item.ndim,
                "dtype": str(item.dtype),
                "element_count": int(item.size),
                "logical_nbytes": int(item.size * item.dtype.itemsize),
                "chunks": list(item.chunks) if item.chunks is not None else None,
                "compression": item.compression,
                "compression_opts": _json_safe(item.compression_opts),
                "shuffle": bool(item.shuffle),
                "fletcher32": bool(item.fletcher32),
                "scaleoffset": _json_safe(item.scaleoffset),
                "attribute_count": len(item.attrs),
                "attributes": _attrs(item.attrs),
            }
            record["numeric_sample"] = _numeric_sample(
                item, config.max_sample_values_per_dataset
            )
            datasets.append(record)

        handle.visititems(visitor)
    if not datasets:
        raise PhaseT3MContractError("target HDF5 contains no datasets")
    leading_dimensions = sorted(
        {
            int(record["shape"][0])
            for record in datasets
            if record["shape"] and int(record["shape"][0]) > 0
        }
    )
    return {
        "file_bytes": path.stat().st_size,
        "file_sha256": _hashes(path)["sha256"],
        "root_attributes": root_attrs,
        "group_count": len(groups),
        "dataset_count": len(datasets),
        "groups": groups,
        "datasets": datasets,
        "observed_leading_dimensions": leading_dimensions,
        "tilt_count_interpretation": (
            "not_inferred_from_shape_without_source schema binding"
        ),
    }


def _numeric_sample(dataset: h5py.Dataset, maximum: int) -> dict[str, Any] | None:
    if dataset.size == 0 or dataset.dtype.kind not in "biufc":
        return None
    if dataset.ndim == 0:
        values = np.asarray([dataset[()]])
    else:
        target_per_axis = max(1, int(round(maximum ** (1 / max(1, dataset.ndim)))))
        selection = tuple(
            slice(0, int(length), max(1, math.ceil(int(length) / target_per_axis)))
            for length in dataset.shape
        )
        values = np.asarray(dataset[selection])
        if values.size > maximum:
            indices = np.linspace(0, values.size - 1, num=maximum, dtype=np.int64)
            values = values.reshape(-1)[indices]
    flat = np.asarray(values).reshape(-1)
    if np.iscomplexobj(flat):
        finite = np.isfinite(flat.real) & np.isfinite(flat.imag)
        finite_values = np.abs(flat[finite])
        interpretation = "complex_magnitude"
    else:
        finite = np.isfinite(flat)
        finite_values = flat[finite]
        interpretation = "native_numeric_values"
    result: dict[str, Any] = {
        "sampled_value_count": int(flat.size),
        "finite_value_count": int(finite.sum()),
        "finite_fraction": float(finite.mean()) if flat.size else None,
        "interpretation": interpretation,
    }
    if finite_values.size:
        result.update(
            {
                "minimum": float(np.min(finite_values)),
                "maximum": float(np.max(finite_values)),
                "mean": float(np.mean(finite_values, dtype=np.float64)),
                "standard_deviation": float(
                    np.std(finite_values, dtype=np.float64)
                ),
            }
        )
        if dataset.dtype.kind in "biu":
            unique = np.unique(finite_values)
            result["unique_values"] = (
                [_json_safe(value) for value in unique.tolist()]
                if unique.size <= 64
                else None
            )
            result["unique_value_count_in_sample"] = int(unique.size)
    return result


def _safe_member_name(name: str) -> str:
    if "\x00" in name:
        raise PhaseT3MContractError("ZIP member path contains NUL")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not path.parts
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PhaseT3MContractError(f"unsafe ZIP member path: {name!r}")
    if path.parts[0].endswith(":"):
        raise PhaseT3MContractError(f"unsafe drive-qualified ZIP path: {name!r}")
    return path.as_posix()


def _attrs(attrs: h5py.AttributeManager) -> dict[str, Any]:
    return {str(key): _json_safe(attrs[key]) for key in sorted(attrs.keys())}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, np.ndarray):
        if value.size > 1024:
            return {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "value_omitted": True,
            }
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return repr(value)


def _hashes(path: Path) -> dict[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    return {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
        return output, False
    output.mkdir(parents=True)
    return output, True


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    columns = (
        "member_path",
        "uncompressed_bytes",
        "compressed_bytes",
        "compression_ratio",
        "crc32",
        "compression_method",
        "encrypted",
        "is_symlink",
        "is_directory",
        "suffix",
        "is_target_member",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _manifest(output: Path, paths: Iterable[Path]) -> dict[str, Any]:
    artifacts = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "software_version": __version__,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "raw_source_files_included": False,
    }


def _report(summary: Mapping[str, Any]) -> str:
    source = _mapping(summary, "source")
    gates = _mapping(summary, "scientific_gates")
    closeout = _mapping(summary, "scientific_closeout")
    lines = [
        "# PhaseT3M Co3O4 Tilt-Series Candidate Audit",
        "",
        f"**Scientific status:** {closeout['status']}",
        "",
        f"**Result:** `{closeout['result']}`",
        "",
        "## Source",
        "",
        f"- DOI: `{source['doi']}`",
        f"- archive MD5: `{source['archive_md5']}`",
        f"- archive SHA-256: `{source['archive_sha256']}`",
        f"- target member: `{source['target_member']}`",
        f"- source processing: {', '.join(source['source_processing'])}",
        "",
        "## Scientific gates",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in gates.items())
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            str(closeout["primary_limitation"]),
            "",
            "No source array was exported, relabeled, used for model training, or used "
            "for segmentation-performance estimation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise PhaseT3MContractError(f"{key} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PhaseT3MContractError(f"{key} must be non-empty text")
    return value.strip()


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise PhaseT3MContractError(f"{key} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise PhaseT3MContractError(f"{key} must contain non-empty text")
    return tuple(item.strip() for item in value)


def _https(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise PhaseT3MContractError(f"{key} must be an HTTPS URL")
    return value


def _filename(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise PhaseT3MContractError(f"{key} must be a basename")
    return value


def _hex(payload: Mapping[str, Any], key: str, length: int) -> str:
    value = _text(payload, key).lower()
    if len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise PhaseT3MContractError(f"{key} must be {length} lowercase hex characters")
    return value


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PhaseT3MContractError(f"{key} must be an integer")
    return value


def _positive_integer(payload: Mapping[str, Any], key: str) -> int:
    value = _integer(payload, key)
    if value <= 0:
        raise PhaseT3MContractError(f"{key} must be positive")
    return value


def _positive_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhaseT3MContractError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise PhaseT3MContractError(f"{key} must be finite and positive")
    return result


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise PhaseT3MContractError(f"{key} must be a boolean")
    return value


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise PhaseT3MContractError(f"unknown {context} keys: {unknown}")
