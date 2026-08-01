"""Audit Mendeley Data metadata for the CoP/Co2P/Co3O4 TEM candidate.

The audit resolves public dataset and file metadata only. It does not download
source arrays, infer sample identity from filenames, create labels, train a model,
or authorize segmentation-performance evaluation.
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
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import __version__

CASE_ID = "mendeley_cop_co2p_co3o4_tem_candidate_audit"
SCHEMA_VERSION = "1.0"
API_BASE = "https://api.data.mendeley.com"
PRIMARY_DATASET_ID = "8w66synjmx"
PRIMARY_DOI = "10.17632/8w66synjmx.1"

STATUS_API_BLOCKED = "blocked_public_api_metadata_access"
STATUS_NO_FILES = "no_public_files_returned"
STATUS_INVENTORY_RESOLVED = "file_inventory_resolved_annotation_not_ready"
STATUS_TEM_CANDIDATE_FOUND = "tem_file_candidates_resolved_lineage_not_ready"

TEM_PATTERN = re.compile(r"(?i)(?:^|[^a-z])(hr?tem|stem|transmission electron)(?:[^a-z]|$)")
NON_TEM_PATTERN = re.compile(r"(?i)(sem|xrd|xps|electro|cv|lsv|eis|raman|ftir)")
IMAGE_EXTENSIONS = {
    ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".dm3", ".dm4", ".emd",
    ".ser", ".h5", ".hdf5", ".zip", ".rar", ".7z", ".tar", ".gz",
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
        allowed = {"dataset_id", "version", "doi", "role", "expected_title_fragment"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"unknown dataset keys: {unknown}")
        dataset_id = _text(payload, "dataset_id")
        if not re.fullmatch(r"[a-z0-9]{10}", dataset_id):
            raise ValueError(f"invalid Mendeley dataset_id: {dataset_id!r}")
        version = _integer(payload, "version")
        if version <= 0:
            raise ValueError("version must be positive.")
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
        allowed = {"case_id", "api_base", "datasets"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"unknown config keys: {unknown}")
        entries = payload.get("datasets")
        if not isinstance(entries, list) or not entries:
            raise ValueError("datasets must be a non-empty list.")
        config = cls(
            case_id=_text(payload, "case_id"),
            api_base=_text(payload, "api_base").rstrip("/"),
            datasets=tuple(
                DatasetSpec.from_mapping(item)
                for item in entries
                if isinstance(item, Mapping)
            ),
        )
        if len(config.datasets) != len(entries):
            raise ValueError("every dataset entry must be an object.")
        config.validate()
        return config

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise ValueError(f"case_id must equal {CASE_ID!r}.")
        if self.api_base != API_BASE:
            raise ValueError(f"api_base must equal {API_BASE!r}.")
        ids = [item.dataset_id for item in self.datasets]
        dois = [item.doi for item in self.datasets]
        roles = [item.role for item in self.datasets]
        if (
            len(ids) != len(set(ids))
            or len(dois) != len(set(dois))
            or len(roles) != len(set(roles))
        ):
            raise ValueError("dataset ids, DOIs, and roles must be unique.")
        primary = [item for item in self.datasets if item.role == "primary_raw"]
        if len(primary) != 1:
            raise ValueError("exactly one primary_raw dataset is required.")
        if primary[0].dataset_id != PRIMARY_DATASET_ID or primary[0].doi != PRIMARY_DOI:
            raise ValueError("primary_raw dataset does not match the pinned candidate.")


Transport = Callable[[str, str], tuple[int, Mapping[str, str], Any]]


def load_config(path: str | Path) -> AuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("config must contain a JSON object.")
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
            dataset_result = _resolve_endpoint_family(
                request, config.api_base, spec, kind="dataset"
            )
            files_result = _resolve_endpoint_family(
                request, config.api_base, spec, kind="files"
            )
            dataset_payload = dataset_result["payload"]
            metadata = dataset_payload if isinstance(dataset_payload, Mapping) else {}
            title = _first_text(metadata, "name", "title")
            description = _first_text(metadata, "description")
            dataset_rows.append(
                {
                    "dataset_id": spec.dataset_id,
                    "role": spec.role,
                    "expected_doi": spec.doi,
                    "observed_doi": _extract_doi(metadata),
                    "expected_version": spec.version,
                    "observed_version": metadata.get("version"),
                    "title": title,
                    "title_fragment_match": spec.expected_title_fragment.lower()
                    in title.lower(),
                    "description": description,
                    "dataset_endpoint_status": dataset_result["status"],
                    "dataset_endpoint_variant": dataset_result["variant"],
                    "files_endpoint_status": files_result["status"],
                    "files_endpoint_variant": files_result["variant"],
                }
            )
            for item in _normalize_files_payload(files_result["payload"]):
                file_rows.append(_normalize_file(spec, item))
            snapshots.extend(
                [
                    _snapshot(spec, "dataset", dataset_result),
                    _snapshot(spec, "files", files_result),
                ]
            )

        primary_rows = [
            row for row in file_rows if row["dataset_id"] == PRIMARY_DATASET_ID
        ]
        successful_file_endpoints = [
            row for row in dataset_rows if int(row["files_endpoint_status"]) == 200
        ]
        tem_candidates = [
            row for row in primary_rows if row["tem_candidate_by_metadata"]
        ]
        checksum_complete = (
            all(bool(row["sha256"]) and int(row["size_bytes"]) > 0 for row in primary_rows)
            if primary_rows
            else False
        )

        if not successful_file_endpoints:
            status = STATUS_API_BLOCKED
        elif not file_rows:
            status = STATUS_NO_FILES
        elif tem_candidates:
            status = STATUS_TEM_CANDIDATE_FOUND
        else:
            status = STATUS_INVENTORY_RESOLVED

        summary = {
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
                "successful_file_endpoint_count": len(successful_file_endpoints),
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
                "primary_file_inventory_resolved": bool(primary_rows),
                "primary_checksums_and_sizes_complete": checksum_complete,
                "tem_candidates_resolved_by_filename_or_description": bool(tem_candidates),
                "candidate_file_ids": [row["file_id"] for row in tem_candidates],
                "candidate_filenames": [row["filename"] for row in tem_candidates],
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
            "next_action": _next_action(status, tem_candidates),
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
                "status": "Diagnostic" if file_rows else "Inconclusive",
                "result": status,
                "strongest_evidence": (
                    "The official public dataset API was queried for the pinned primary, "
                    "duplicate raw, and processed-data records, preserving file UUID, size, "
                    "source-declared SHA-256, folder identity, and descriptions where returned."
                ),
                "primary_limitation": (
                    "File-level metadata cannot establish which image regions contain Co3O4, "
                    "nor immutable sample/acquisition lineage, target-model non-use, independent "
                    "labels, or content disjointness."
                ),
                "evidence_that_would_change_conclusion": (
                    "Checksum-bound TEM files with source-supported sample and acquisition IDs, "
                    "a defensible Co3O4-bearing region map, verified non-use in model development, "
                    "training-content overlap clearance, and independently adjudicated labels."
                ),
                "suitable_for": [
                    "public file inventory and checksum resolution",
                    "metadata-based TEM candidate narrowing",
                    "planning a dedicated image and lineage audit",
                ],
                "not_suitable_for": [
                    "annotation before lineage resolution",
                    "external segmentation-performance evaluation",
                    "material-phase assignment from filenames",
                    "model selection or engineering release",
                ],
            },
        }

        dataset_csv = output / "mendeley_dataset_inventory.csv"
        file_csv = output / "mendeley_file_inventory.csv"
        summary_path = output / "mendeley_candidate_audit_summary.json"
        report_path = output / "mendeley_candidate_audit_report.md"
        snapshots_path = output / "mendeley_api_snapshots.json"
        manifest_path = output / "mendeley_candidate_audit_manifest.json"
        _write_csv(dataset_csv, dataset_rows)
        _write_csv(file_csv, file_rows)
        _write_json(summary_path, summary)
        _write_json(snapshots_path, {"snapshots": snapshots})
        report_path.write_text(
            _build_report(summary, dataset_rows, file_rows), encoding="utf-8"
        )
        _write_json(
            manifest_path,
            _manifest(
                output,
                [dataset_csv, file_csv, summary_path, report_path, snapshots_path],
            ),
        )
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _resolve_endpoint_family(
    request: Transport,
    api_base: str,
    spec: DatasetSpec,
    *,
    kind: str,
) -> dict[str, Any]:
    if kind == "dataset":
        paths = [
            (f"/datasets/{spec.dataset_id}", "datasets"),
            (f"/datasets/publics/{spec.dataset_id}", "datasets_publics"),
        ]
        params = {"version": str(spec.version), "fields": "*"}
    elif kind == "files":
        paths = [
            (f"/datasets/{spec.dataset_id}/files", "datasets"),
            (f"/datasets/publics/{spec.dataset_id}/files", "datasets_publics"),
        ]
        params = {"version": str(spec.version), "$start": "0", "$limit": "500"}
    else:
        raise ValueError(f"unsupported endpoint kind: {kind}")
    attempts: list[dict[str, Any]] = []
    for path, variant in paths:
        url = f"{api_base}{path}?{urllib.parse.urlencode(params)}"
        status, headers, payload = request(url, _accept(kind))
        attempts.append(
            {
                "variant": variant,
                "status": status,
                "headers": dict(headers),
                "payload": payload,
                "url_path": path,
            }
        )
        if status == 200:
            return attempts[-1] | {"attempts": attempts}
        if status not in {401, 403, 404}:
            break
    return attempts[-1] | {"attempts": attempts}


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
            raw = response.read()
            return response.status, dict(response.headers.items()), _decode_json(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, dict(exc.headers.items()), _decode_json(raw)
    except urllib.error.URLError as exc:
        return 0, {}, {"error": str(exc.reason)}


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"non_json_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _normalize_files_payload(payload: Any) -> list[Mapping[str, Any]]:
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
    file_id = _first_text(item, "id", "file_id")
    sha256 = _first_text(content, "sha256_hash", "sha256") or _first_text(
        item, "sha256_hash", "sha256"
    )
    size_value = content.get("size", item.get("size", 0))
    try:
        size_bytes = int(size_value)
    except (TypeError, ValueError):
        size_bytes = 0
    suffix = Path(filename).suffix.lower()
    searchable = f"{filename} {description}"
    tem_match = bool(TEM_PATTERN.search(searchable))
    non_tem_match = bool(NON_TEM_PATTERN.search(searchable))
    extension_supported = suffix in IMAGE_EXTENSIONS
    candidate = (tem_match and not non_tem_match) or (tem_match and extension_supported)
    return {
        "dataset_id": spec.dataset_id,
        "dataset_role": spec.role,
        "dataset_doi": spec.doi,
        "file_id": file_id,
        "filename": filename,
        "description": description,
        "folder_id": _first_text(item, "folder_id"),
        "content_type": _first_text(content, "content_type"),
        "size_bytes": size_bytes,
        "sha256": sha256,
        "last_modified_date": _first_text(item, "last_modified_date"),
        "file_status": _first_text(item, "status"),
        "filename_extension": suffix,
        "tem_keyword_match": tem_match,
        "non_tem_keyword_match": non_tem_match,
        "recognized_image_or_archive_extension": extension_supported,
        "tem_candidate_by_metadata": candidate,
        "material_or_sample_identity_inferred": False,
    }


def _snapshot(spec: DatasetSpec, kind: str, result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": spec.dataset_id,
        "role": spec.role,
        "kind": kind,
        "selected_variant": result["variant"],
        "selected_status": result["status"],
        "attempts": [
            {
                "variant": item["variant"],
                "status": item["status"],
                "url_path": item["url_path"],
                "response_sha256": hashlib.sha256(
                    json.dumps(item["payload"], sort_keys=True, default=str).encode(
                        "utf-8"
                    )
                ).hexdigest(),
            }
            for item in result["attempts"]
        ],
        "payload": _sanitize_payload(result["payload"]),
    }


def _sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        cleaned = {}
        for key, value in payload.items():
            if key in {"download_url", "view_url", "download_expiry_time"}:
                cleaned[key] = "redacted_ephemeral_url" if value else value
            else:
                cleaned[key] = _sanitize_payload(value)
        return cleaned
    if isinstance(payload, list):
        return [_sanitize_payload(item) for item in payload]
    return payload


def _accept(kind: str) -> str:
    if kind == "dataset":
        return "application/vnd.mendeley-public-dataset.1+json, application/json"
    return "application/json"


def _extract_doi(metadata: Mapping[str, Any]) -> str:
    value = metadata.get("doi")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return _first_text(value, "id", "doi")
    return ""


def _next_action(status: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    if status == STATUS_API_BLOCKED:
        return (
            "Preserve the HTTP evidence and determine whether the public API requires "
            "repository authentication or a different public endpoint before any file download."
        )
    if status == STATUS_NO_FILES:
        return (
            "Verify duplicate raw dataset records and repository file visibility; do not infer "
            "that the landing-page description proves downloadable TEM content."
        )
    if status == STATUS_TEM_CANDIDATE_FOUND:
        names = ", ".join(str(row["filename"]) for row in candidates[:5])
        return (
            "Run a checksum-bound selective download and file-format inventory for the metadata-"
            f"identified TEM candidates ({names}); then resolve Co3O4 region and immutable "
            "sample/acquisition lineage before annotation."
        )
    return (
        "Inspect archive or generic-file members without treating filenames as sample identity; "
        "resolve exact TEM members, checksums, Co3O4 binding, and acquisition lineage."
    )


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty.")
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
            writer.writerow({key: row.get(key) for key in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _manifest(output: Path, artifacts: Sequence[Path]) -> dict[str, Any]:
    rows = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in artifacts
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "software_version": __version__,
        "artifact_count": len(rows),
        "artifacts": rows,
    }


def _build_report(
    summary: Mapping[str, Any],
    datasets: Sequence[Mapping[str, Any]],
    files: Sequence[Mapping[str, Any]],
) -> str:
    readiness = summary["inventory_readiness"]
    gates = summary["lineage_and_annotation_gates"]
    lines = [
        "# Mendeley CoP/Co2P/Co3O4 TEM Candidate Audit",
        "",
        f"**Evidence level:** {summary['scientific_closeout']['status']}",
        "",
        f"**Result:** `{readiness['status']}`",
        "",
        "## Dataset endpoints",
        "",
    ]
    for row in datasets:
        lines.append(
            f"- `{row['dataset_id']}` ({row['role']}): dataset HTTP "
            f"`{row['dataset_endpoint_status']}`, files HTTP "
            f"`{row['files_endpoint_status']}`"
        )
    lines.extend(
        [
            "",
            "## Inventory",
            "",
            f"- Public files resolved: {summary['result_counts']['file_count']}",
            f"- Primary raw files: {summary['result_counts']['primary_file_count']}",
            f"- Primary TEM candidates by metadata: "
            f"{summary['result_counts']['primary_tem_candidate_file_count']}",
            "",
        ]
    )
    for row in files:
        marker = "TEM candidate" if row["tem_candidate_by_metadata"] else "not selected"
        lines.append(
            f"- `{row['dataset_id']}/{row['filename']}`: {row['size_bytes']} bytes, "
            f"SHA-256 `{row['sha256'] or 'missing'}`, {marker}"
        )
    lines.extend(["", "## Annotation and evaluation gates", ""])
    lines.extend(f"- `{key}`: `{str(value).lower()}`" for key, value in gates.items())
    lines.extend(
        [
            "",
            "## Next",
            "",
            str(summary["next_action"]),
            "",
            "## Scientific boundary",
            "",
            "This audit resolves public metadata only. It does not establish Co3O4-bearing "
            "regions, sample or acquisition independence, independent labels, or model "
            "evaluation readiness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _first_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text.")
    return value.strip()


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value
