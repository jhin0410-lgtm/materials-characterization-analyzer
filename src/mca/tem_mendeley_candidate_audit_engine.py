"""Resolve public Mendeley dataset and root-file metadata fail closed.

The engine uses the anonymous ``data.mendeley.com/public-api`` endpoints used by
the public landing pages. It does not download file bytes, infer sample identity,
create labels, or authorize model evaluation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import __version__

CASE_ID = "mendeley_cop_co2p_co3o4_tem_candidate_audit"
SCHEMA_VERSION = "1.0"
PUBLIC_API_BASE = "https://data.mendeley.com/public-api"
PRIMARY_DATASET_ID = "8w66synjmx"
PRIMARY_DOI = "10.17632/8w66synjmx.1"

STATUS_API_BLOCKED = "blocked_public_api_metadata_access"
STATUS_NO_FILES = "no_public_files_returned"
STATUS_INVENTORY_RESOLVED = "file_inventory_resolved_annotation_not_ready"
STATUS_TEM_CANDIDATE_FOUND = "tem_file_candidates_resolved_lineage_not_ready"

TEM_PATTERN = re.compile(
    r"(?i)(?:^|[^a-z])(?:tem|hrtem|stem|transmission electron)(?:[^a-z]|$)"
)
NON_TEM_PATTERN = re.compile(r"(?i)(sem|xrd|xps|electro|cv|lsv|eis|raman|ftir)")
PROBE_EVIDENCE_FILENAMES = (
    "mendeley_public_page_probe.json",
    "mendeley_anonymous_public_api_probe.json",
)

MICROSCOPY_EXTENSIONS = {
    ".tif",
    ".tiff",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".dm3",
    ".dm4",
    ".emd",
    ".ser",
    ".h5",
    ".hdf5",
}


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    version: int
    doi: str
    role: str
    expected_title_fragment: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "DatasetSpec":
        _reject_unknown(
            payload,
            {"dataset_id", "version", "doi", "role", "expected_title_fragment"},
            "dataset",
        )
        dataset_id = _text(payload, "dataset_id")
        if not re.fullmatch(r"[a-z0-9]{10}", dataset_id):
            raise ValueError(f"invalid Mendeley dataset_id: {dataset_id!r}")
        version = _integer(payload, "version")
        if version <= 0:
            raise ValueError("version must be positive")
        return cls(
            dataset_id=dataset_id,
            version=version,
            doi=_text(payload, "doi"),
            role=_text(payload, "role"),
            expected_title_fragment=_text(payload, "expected_title_fragment"),
        )


@dataclass(frozen=True)
class AuditConfig:
    case_id: str
    api_base: str
    datasets: tuple[DatasetSpec, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AuditConfig":
        _reject_unknown(payload, {"case_id", "api_base", "datasets"}, "config")
        entries = payload.get("datasets")
        if not isinstance(entries, list) or not entries:
            raise ValueError("datasets must be a non-empty list")
        datasets = tuple(
            DatasetSpec.from_mapping(_mapping_value(item, f"datasets[{index}]"))
            for index, item in enumerate(entries)
        )
        config = cls(
            case_id=_text(payload, "case_id"),
            api_base=_text(payload, "api_base").rstrip("/"),
            datasets=datasets,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise ValueError(f"case_id must equal {CASE_ID!r}")
        if self.api_base not in {
            PUBLIC_API_BASE,
            "https://api.data.mendeley.com",
        }:
            raise ValueError("unsupported Mendeley API base")
        ids = [item.dataset_id for item in self.datasets]
        roles = [item.role for item in self.datasets]
        if len(ids) != len(set(ids)) or len(roles) != len(set(roles)):
            raise ValueError("dataset ids and roles must be unique")
        primary = [item for item in self.datasets if item.role == "primary_raw"]
        if len(primary) != 1:
            raise ValueError("exactly one primary_raw dataset is required")
        if primary[0].dataset_id != PRIMARY_DATASET_ID or primary[0].doi != PRIMARY_DOI:
            raise ValueError("primary_raw dataset does not match the pinned candidate")


Transport = Callable[[str, str], tuple[int, Mapping[str, str], Any]]


def load_config(path: str | Path) -> AuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("config must contain a JSON object")
    return AuditConfig.from_mapping(payload)


def run_mendeley_candidate_audit(
    config: AuditConfig,
    output_dir: str | Path,
    *,
    transport: Transport | None = None,
) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    request = transport or _request_json
    try:
        dataset_rows: list[dict[str, Any]] = []
        file_rows: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []
        for spec in config.datasets:
            snapshot_url = (
                f"{config.api_base}/datasets/{spec.dataset_id}/snapshot/{spec.version}"
            )
            files_url = f"{config.api_base}/datasets/{spec.dataset_id}/files?" + (
                urllib.parse.urlencode(
                    {"folder_id": "root", "version": str(spec.version)}
                )
            )
            snapshot_status, snapshot_headers, snapshot_payload = request(
                snapshot_url, "application/json"
            )
            files_status, files_headers, files_payload = request(
                files_url,
                "application/vnd.mendeley-public-dataset.1+json, application/json",
            )
            metadata = snapshot_payload if isinstance(snapshot_payload, Mapping) else {}
            title = _first_text(metadata, "name", "title")
            dataset_rows.append(
                {
                    "dataset_id": spec.dataset_id,
                    "role": spec.role,
                    "expected_doi": spec.doi,
                    "observed_doi": _extract_doi(metadata),
                    "expected_version": spec.version,
                    "observed_version": metadata.get("version"),
                    "title": title,
                    "title_fragment_match": (
                        spec.expected_title_fragment.lower() in title.lower()
                    ),
                    "description": _first_text(metadata, "description"),
                    "license": _license_name(metadata),
                    "snapshot_status": snapshot_status,
                    "root_files_status": files_status,
                }
            )
            files = _normalize_files(files_payload) if files_status == 200 else []
            for item in files:
                file_rows.append(_normalize_file(spec, item))
            snapshots.extend(
                [
                    _snapshot_record(
                        spec,
                        "snapshot",
                        snapshot_status,
                        snapshot_headers,
                        snapshot_payload,
                    ),
                    _snapshot_record(
                        spec,
                        "root_files",
                        files_status,
                        files_headers,
                        files_payload,
                    ),
                ]
            )

        primary_rows = [
            row for row in file_rows if row["dataset_id"] == PRIMARY_DATASET_ID
        ]
        successful_file_sources = sum(
            int(row["root_files_status"] == 200) for row in dataset_rows
        )
        primary_dataset_row = next(
            row for row in dataset_rows if row["role"] == "primary_raw"
        )
        primary_root_files_request_succeeded = (
            primary_dataset_row["root_files_status"] == 200
        )
        tem_candidates = [
            row for row in primary_rows if row["tem_candidate_by_metadata"]
        ]
        primary_checksums_complete = _file_identity_complete(primary_rows)
        if not primary_root_files_request_succeeded:
            status = STATUS_API_BLOCKED
        elif not primary_rows:
            status = STATUS_NO_FILES
        elif tem_candidates:
            status = STATUS_TEM_CANDIDATE_FOUND
        else:
            status = STATUS_INVENTORY_RESOLVED

        duplicate_rows = [
            row for row in file_rows if row["dataset_role"] == "duplicate_raw_record"
        ]
        duplicate_checksums_complete = _file_identity_complete(duplicate_rows)
        duplicate_identical = (
            primary_checksums_complete
            and duplicate_checksums_complete
            and _file_signatures(primary_rows) == _file_signatures(duplicate_rows)
        )

        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": config.case_id,
            "software_version": __version__,
            "source": {
                "repository": "Mendeley Data / Digital Commons Data",
                "api_base": config.api_base,
                "primary_dataset_id": PRIMARY_DATASET_ID,
                "primary_doi": PRIMARY_DOI,
                "dataset_count": len(config.datasets),
            },
            "result_counts": {
                "dataset_count": len(dataset_rows),
                "successful_root_file_endpoint_count": successful_file_sources,
                "file_count": len(file_rows),
                "primary_file_count": len(primary_rows),
                "primary_tem_candidate_file_count": len(tem_candidates),
                "primary_checksum_complete_file_count": sum(
                    int(bool(row["sha256"]) and int(row["size_bytes"]) > 0)
                    for row in primary_rows
                ),
            },
            "inventory_readiness": {
                "status": status,
                "primary_root_files_request_succeeded": (
                    primary_root_files_request_succeeded
                ),
                "primary_file_inventory_resolved": bool(primary_rows),
                "primary_checksums_and_sizes_complete": primary_checksums_complete,
                "duplicate_raw_record_checksums_and_sizes_complete": (
                    duplicate_checksums_complete
                ),
                "tem_candidates_resolved_by_filename_or_description": bool(
                    tem_candidates
                ),
                "candidate_file_ids": [row["file_id"] for row in tem_candidates],
                "candidate_filenames": [row["filename"] for row in tem_candidates],
                "duplicate_raw_record_content_identical": duplicate_identical,
            },
            "lineage_and_annotation_gates": {
                "immutable_sample_ids_available": False,
                "immutable_acquisition_ids_available": False,
                "co3o4_region_binding_available": False,
                "target_training_nonuse_verified": False,
                "target_training_content_overlap_cleared": False,
                "independent_segmentation_labels_available": False,
                "annotation_pilot_ready": False,
                "external_model_evaluation_ready": False,
            },
            "next_action": _next_action(status, primary_rows, tem_candidates),
            "processing": {
                "source_files_downloaded": False,
                "source_arrays_inspected": False,
                "filename_used_as_sample_identity": False,
                "labels_created": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_metrics_computed": False,
            },
            "scientific_closeout": {
                "status": (
                    "Inconclusive" if status == STATUS_API_BLOCKED else "Diagnostic"
                ),
                "result": status,
                "strongest_evidence": (
                    "The anonymous public API returned immutable dataset snapshots and "
                    "root-file metadata, including file UUID, byte size, and source SHA-256."
                ),
                "primary_limitation": (
                    "Root-file metadata alone cannot identify Co3O4-bearing TEM members or "
                    "establish sample/acquisition lineage, non-use, independent labels, or "
                    "content disjointness."
                ),
                "evidence_that_would_change_conclusion": (
                    "A verified archive-member inventory followed by selective format and "
                    "embedded-metadata inspection, then source-supported lineage and blinded "
                    "independent annotation if the representation is suitable."
                ),
                "suitable_for": [
                    "public dataset and root-file inventory",
                    "source checksum resolution",
                    "duplicate-record detection",
                    "planning selective archive inspection",
                ],
                "not_suitable_for": [
                    "external segmentation-performance evaluation",
                    "material or sample assignment from filenames",
                    "model selection or engineering release",
                ],
            },
        }

        dataset_path = output / "mendeley_dataset_inventory.csv"
        file_path = output / "mendeley_file_inventory.csv"
        summary_path = output / "mendeley_candidate_audit_summary.json"
        report_path = output / "mendeley_candidate_audit_report.md"
        snapshots_path = output / "mendeley_api_snapshots.json"
        manifest_path = output / "mendeley_candidate_audit_manifest.json"
        _write_csv(dataset_path, dataset_rows)
        _write_csv(file_path, file_rows)
        _write_json(summary_path, summary)
        _write_json(snapshots_path, {"snapshots": snapshots})
        report_path.write_text(
            _build_report(summary, dataset_rows, file_rows), encoding="utf-8"
        )
        _write_json(
            manifest_path,
            _manifest(
                output,
                [dataset_path, file_path, summary_path, report_path, snapshots_path],
            ),
        )
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _request_json(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": f"materials-characterization-analyzer/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return (
                response.status,
                dict(response.headers.items()),
                _decode_json(response.read()),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), _decode_json(exc.read())
    except urllib.error.URLError as exc:
        return 0, {}, {"error": str(exc.reason)}


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "non_json_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }


def _normalize_files(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("results", "files", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
    return []


def _normalize_file(spec: DatasetSpec, item: Mapping[str, Any]) -> dict[str, Any]:
    content = item.get("content_details")
    if not isinstance(content, Mapping):
        content = {}
    filename = _first_text(item, "filename", "name")
    description = _first_text(item, "description")
    suffix = Path(filename).suffix.lower()
    searchable = f"{filename} {description}"
    tem_keyword = bool(TEM_PATTERN.search(searchable))
    non_tem_keyword = bool(NON_TEM_PATTERN.search(searchable))
    recognized_image = suffix in MICROSCOPY_EXTENSIONS
    candidate = tem_keyword and (recognized_image or not non_tem_keyword)
    size_value = content.get("size", item.get("size", 0))
    try:
        size_bytes = int(size_value)
    except (TypeError, ValueError):
        size_bytes = 0
    return {
        "dataset_id": spec.dataset_id,
        "dataset_role": spec.role,
        "dataset_doi": spec.doi,
        "file_id": _first_text(item, "id", "file_id"),
        "content_id": _first_text(content, "id"),
        "filename": filename,
        "description": description,
        "folder_id": _first_text(item, "folder_id"),
        "content_type": _first_text(content, "content_type"),
        "size_bytes": size_bytes,
        "sha256": _first_text(content, "sha256_hash", "sha256")
        or _first_text(item, "sha256_hash", "sha256"),
        "last_modified_date": _first_text(item, "last_modified_date"),
        "file_status": _first_text(item, "status"),
        "filename_extension": suffix,
        "tem_keyword_match": tem_keyword,
        "non_tem_keyword_match": non_tem_keyword,
        "recognized_microscopy_image_extension": recognized_image,
        "tem_candidate_by_metadata": candidate,
        "material_or_sample_identity_inferred": False,
    }


def _file_identity_complete(rows: Iterable[Mapping[str, Any]]) -> bool:
    records = list(rows)
    return bool(records) and all(
        isinstance(row.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(row["sha256"]).lower())
        and int(row.get("size_bytes", 0)) > 0
        for row in records
    )


def _file_signatures(rows: Iterable[Mapping[str, Any]]) -> set[tuple[Any, ...]]:
    return {
        (row["filename"], row["size_bytes"], row["sha256"])
        for row in rows
    }


def _snapshot_record(
    spec: DatasetSpec,
    kind: str,
    status: int,
    headers: Mapping[str, str],
    payload: Any,
) -> dict[str, Any]:
    return {
        "dataset_id": spec.dataset_id,
        "role": spec.role,
        "kind": kind,
        "status": status,
        "content_type": headers.get("Content-Type", ""),
        "payload_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
        "payload": _sanitize(payload),
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(
                token in lowered
                for token in ("download_url", "view_url", "expiry", "token")
            ):
                result[str(key)] = "redacted"
            else:
                result[str(key)] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and ("X-Amz-" in value or "Signature=" in value):
        return "redacted_ephemeral_url"
    return value


def _extract_doi(metadata: Mapping[str, Any]) -> str:
    value = metadata.get("doi")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return _first_text(value, "id", "doi")
    return ""


def _license_name(metadata: Mapping[str, Any]) -> str:
    value = metadata.get("licence") or metadata.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return _first_text(value, "name", "id")
    return ""


def _next_action(
    status: str,
    primary_rows: list[Mapping[str, Any]],
    tem_candidates: list[Mapping[str, Any]],
) -> str:
    if status == STATUS_API_BLOCKED:
        return "Preserve the HTTP evidence and resolve public API access before download."
    if status == STATUS_NO_FILES:
        return "Verify public root-file visibility; do not infer downloadable TEM content."
    if status == STATUS_TEM_CANDIDATE_FOUND:
        names = ", ".join(str(row["filename"]) for row in tem_candidates[:5])
        return (
            f"Checksum-verify and selectively inspect the identified TEM files ({names}); "
            "resolve Co3O4 region and immutable sample/acquisition lineage before annotation."
        )
    if primary_rows:
        names = ", ".join(str(row["filename"]) for row in primary_rows)
        return (
            f"Checksum-verify and inventory the public root archive ({names}) without "
            "extracting unrelated members; then inspect only microscopy-like members."
        )
    return "No usable public file metadata was resolved."


def refresh_mendeley_candidate_audit_manifest(
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    if not output.is_dir() or output.is_symlink():
        raise FileNotFoundError("candidate audit output directory is required")
    required_names = (
        "mendeley_dataset_inventory.csv",
        "mendeley_file_inventory.csv",
        "mendeley_candidate_audit_summary.json",
        "mendeley_candidate_audit_report.md",
        "mendeley_api_snapshots.json",
        *PROBE_EVIDENCE_FILENAMES,
    )
    paths = [output / name for name in required_names]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "candidate audit evidence is incomplete: " + ", ".join(missing)
        )
    manifest = _manifest(output, paths)
    _write_json(output / "mendeley_candidate_audit_manifest.json", manifest)
    return manifest


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
    return output


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    records = list(rows)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    columns = list(records[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in records:
            writer.writerow({column: row.get(column) for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _manifest(output: Path, paths: list[Path]) -> dict[str, Any]:
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
    }


def _build_report(
    summary: Mapping[str, Any],
    datasets: list[Mapping[str, Any]],
    files: list[Mapping[str, Any]],
) -> str:
    readiness = summary["inventory_readiness"]
    lines = [
        "# Mendeley CoP/Co2P/Co3O4 TEM Candidate Metadata Audit",
        "",
        f"**Evidence level:** {summary['scientific_closeout']['status']}",
        "",
        f"**Result:** `{readiness['status']}`",
        "",
        "## Dataset records",
        "",
    ]
    for row in datasets:
        lines.append(
            f"- `{row['dataset_id']}` ({row['role']}): snapshot HTTP "
            f"`{row['snapshot_status']}`, root files HTTP `{row['root_files_status']}`"
        )
    lines.extend(["", "## Root files", ""])
    for row in files:
        lines.append(
            f"- `{row['dataset_id']}/{row['filename']}`: {row['size_bytes']} bytes, "
            f"SHA-256 `{row['sha256'] or 'missing'}`"
        )
    lines.extend(
        [
            "",
            "## Next",
            "",
            str(summary["next_action"]),
            "",
            "## Scientific boundary",
            "",
            "Root-file metadata does not establish Co3O4-bearing regions, sample or "
            "acquisition independence, independent labels, or evaluation readiness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _first_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {context} keys: {unknown}")
