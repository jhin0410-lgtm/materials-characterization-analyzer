#!/usr/bin/env python3
"""Audit public Mendeley lunar TEM/SAED datasets without retaining source pixels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, deque
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

API_HOST = "api.data.mendeley.com"
LANDING_HOST = "data.mendeley.com"
USER_AGENT = "materials-characterization-analyzer-mendeley-lunar-audit/1.0"
DATASET_ACCEPT = "application/vnd.mendeley-public-dataset.1+json"
MAX_HEADER_BYTES_HARD = 65_536


class MendeleyAuditError(RuntimeError):
    """Raised when source identity, API trust, or bounded-audit rules fail."""


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _artifact_manifest(output_dir: Path, paths: Iterable[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    rows.sort(key=lambda item: item["path"])
    return {"artifact_count": len(rows), "artifacts": rows}


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"case_id", "audit_date", "sources", "limits", "scientific_boundary"}:
        raise MendeleyAuditError("unexpected top-level config keys")
    sources = payload["sources"]
    if not isinstance(sources, list) or not sources:
        raise MendeleyAuditError("sources must be a non-empty list")
    expected_source = {
        "dataset_id",
        "version",
        "doi",
        "landing_url",
        "expected_title_substring",
        "expected_description_terms",
        "expected_license_terms",
        "material_scope",
        "source_quality_flags",
    }
    seen_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping) or set(source) != expected_source:
            raise MendeleyAuditError("unexpected source config keys")
        dataset_id = str(source["dataset_id"])
        if dataset_id in seen_ids:
            raise MendeleyAuditError("duplicate dataset_id")
        seen_ids.add(dataset_id)
        if not isinstance(source["version"], int) or source["version"] <= 0:
            raise MendeleyAuditError("source version must be a positive integer")
        if not source["expected_description_terms"] or not source["expected_license_terms"]:
            raise MendeleyAuditError("expected source terms must be non-empty")
    limits = payload["limits"]
    expected_limits = {
        "maximum_file_records_per_dataset",
        "maximum_folder_records_per_dataset",
        "maximum_header_samples_per_dataset",
        "maximum_header_bytes_per_file",
        "maximum_total_header_bytes_per_dataset",
    }
    if set(limits) != expected_limits:
        raise MendeleyAuditError("unexpected limit keys")
    if any(not isinstance(value, int) or value <= 0 for value in limits.values()):
        raise MendeleyAuditError("all limits must be positive integers")
    if limits["maximum_header_bytes_per_file"] > MAX_HEADER_BYTES_HARD:
        raise MendeleyAuditError("header byte limit exceeds hard bound")
    boundary = payload["scientific_boundary"]
    required_true = {
        "public_metadata_fetch_authorized",
        "public_file_inventory_authorized",
        "bounded_file_header_probe_authorized",
    }
    required_false = {
        "source_file_retention_authorized",
        "source_files_may_be_uploaded_as_artifacts",
        "pixel_array_export_authorized",
        "image_preprocessing_authorized",
        "model_inference_authorized",
        "annotation_authorized",
        "parameter_tuning_authorized",
        "model_retraining_authorized",
        "phase_indexing_claim_authorized",
        "external_validation_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if any(boundary.get(key) is not True for key in required_true):
        raise MendeleyAuditError("required bounded operations are not authorized")
    if any(boundary.get(key) is not False for key in required_false):
        raise MendeleyAuditError("scientific boundary must remain fail-closed")
    return payload


def _trusted_api_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST:
        raise MendeleyAuditError(f"untrusted Mendeley API URL: {url}")


def _trusted_download_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    trusted = (
        host in {API_HOST, LANDING_HOST}
        or host.endswith(".mendeley.com")
        or host.endswith(".amazonaws.com")
        or host.endswith(".cloudfront.net")
    )
    if parsed.scheme != "https" or not trusted:
        raise MendeleyAuditError(f"untrusted Mendeley download URL: {url}")


def _request_json(url: str, *, accept: str = "application/json") -> tuple[Any, dict[str, Any]]:
    _trusted_api_url(url)
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            content_type = str(response.headers.get("Content-Type", ""))
            if "json" not in content_type.casefold() and not raw.lstrip().startswith((b"{", b"[")):
                raise MendeleyAuditError(
                    f"Mendeley API returned non-JSON content for {url}: {content_type}"
                )
            value = json.loads(raw)
            return value, {
                "status_code": int(getattr(response, "status", response.getcode())),
                "content_type": content_type,
                "response_bytes": len(raw),
                "response_sha256": _hash_bytes(raw),
                "final_url": response.geturl(),
            }
    except urllib.error.HTTPError as exc:
        sample = exc.read(MAX_HEADER_BYTES_HARD)
        raise MendeleyAuditError(
            f"Mendeley API returned HTTP {exc.code} for {url}; "
            f"sample_sha256={_hash_bytes(sample)}"
        ) from exc


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dataset_doi(payload: Mapping[str, Any]) -> str:
    doi = payload.get("doi")
    if isinstance(doi, Mapping):
        for key in ("id", "doi", "value"):
            value = _string(doi.get(key))
            if value:
                return value
    return _string(doi)


def _license_text(payload: Mapping[str, Any]) -> str:
    candidates: list[str] = []
    for key in ("data_licence", "data_license", "licence", "license"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            candidates.extend(_string(value.get(subkey)) for subkey in ("id", "name", "short_name", "url"))
        elif isinstance(value, str):
            candidates.append(value)
    return " | ".join(sorted({item for item in candidates if item}))


def _dataset_title(payload: Mapping[str, Any]) -> str:
    return _string(payload.get("name") or payload.get("title"))


def _dataset_description(payload: Mapping[str, Any]) -> str:
    return _string(payload.get("description"))


def _extract_list(payload: Any, keys: Sequence[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        embedded = payload.get("_embedded")
        if isinstance(embedded, Mapping):
            for key, value in embedded.items():
                if isinstance(value, list):
                    return [dict(item) for item in value if isinstance(item, Mapping)]
    raise MendeleyAuditError("Mendeley API collection response had no record list")


def _dataset_api_id(payload: Mapping[str, Any], fallback: str) -> str:
    value = payload.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def verify_dataset(source: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    title = _dataset_title(payload)
    description = _dataset_description(payload)
    doi = _dataset_doi(payload)
    licence = _license_text(payload)
    version = payload.get("version")
    if source["expected_title_substring"].casefold() not in title.casefold():
        raise MendeleyAuditError(f"dataset title mismatch for {source['dataset_id']}: {title!r}")
    if str(source["doi"]).casefold() != doi.casefold():
        raise MendeleyAuditError(f"dataset DOI mismatch for {source['dataset_id']}: {doi!r}")
    if version is not None and int(version) != int(source["version"]):
        raise MendeleyAuditError(f"dataset version mismatch for {source['dataset_id']}: {version!r}")
    missing_description = [
        term for term in source["expected_description_terms"]
        if str(term).casefold() not in description.casefold()
    ]
    if missing_description:
        raise MendeleyAuditError(
            f"dataset description lost expected terms for {source['dataset_id']}: "
            f"{missing_description}"
        )
    if not any(
        str(term).casefold() in licence.casefold()
        for term in source["expected_license_terms"]
    ):
        raise MendeleyAuditError(
            f"dataset licence mismatch for {source['dataset_id']}: {licence!r}"
        )
    return {
        "requested_dataset_id": source["dataset_id"],
        "api_dataset_id": _dataset_api_id(payload, str(source["dataset_id"])),
        "version": int(source["version"]),
        "doi": doi,
        "title": title,
        "description": description,
        "license_text": licence,
        "landing_url": source["landing_url"],
        "material_scope": source["material_scope"],
    }


def _file_id(record: Mapping[str, Any]) -> str:
    for key in ("id", "file_id", "uuid"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _file_name(record: Mapping[str, Any]) -> str:
    for key in ("filename", "name", "path"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _file_size(record: Mapping[str, Any]) -> int | None:
    candidates: list[Any] = [record.get("size")]
    details = record.get("content_details")
    if isinstance(details, Mapping):
        candidates.extend([details.get("size"), details.get("content_length")])
    for value in candidates:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _file_sha256(record: Mapping[str, Any]) -> str:
    details = record.get("content_details")
    candidates: list[Any] = [record.get("sha256_hash"), record.get("checksum")]
    if isinstance(details, Mapping):
        candidates.extend([details.get("sha256_hash"), details.get("checksum")])
    for value in candidates:
        if isinstance(value, str):
            text = value.strip().casefold().removeprefix("sha256:")
            if len(text) == 64 and all(char in "0123456789abcdef" for char in text):
                return text
    return ""


def _folder_id(record: Mapping[str, Any]) -> str:
    value = record.get("folder_id") or record.get("parent_id")
    return value.strip() if isinstance(value, str) else ""


def _content_type(record: Mapping[str, Any]) -> str:
    details = record.get("content_details")
    if isinstance(details, Mapping):
        return _string(details.get("content_type"))
    return _string(record.get("content_type"))


def _download_url(record: Mapping[str, Any]) -> str:
    details = record.get("content_details")
    if isinstance(details, Mapping):
        value = details.get("download_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _folder_name(record: Mapping[str, Any]) -> str:
    return _string(record.get("name") or record.get("title"))


def _folder_parent(record: Mapping[str, Any]) -> str:
    return _string(record.get("parent_id") or record.get("parent"))


def build_folder_paths(folders: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    by_id: dict[str, dict[str, str]] = {}
    for record in folders:
        folder_id = _string(record.get("id"))
        if not folder_id:
            continue
        by_id[folder_id] = {
            "name": _folder_name(record),
            "parent": _folder_parent(record),
        }
    paths: dict[str, str] = {}
    for folder_id in by_id:
        seen: set[str] = set()
        parts: deque[str] = deque()
        current = folder_id
        while current:
            if current in seen:
                raise MendeleyAuditError("Mendeley folder cycle detected")
            seen.add(current)
            node = by_id.get(current)
            if node is None:
                break
            if node["name"]:
                parts.appendleft(node["name"])
            current = node["parent"]
        paths[folder_id] = PurePosixPath(*parts).as_posix() if parts else ""
    return paths


def classify_path(path: str, filename: str) -> list[str]:
    folded = f"{path}/{filename}".casefold()
    basename = filename.casefold()
    cues: list[str] = []
    if any(term in folded for term in ("tem", "transmission electron")):
        cues.append("tem_cue")
    if any(term in folded for term in ("hrtem", "high-resolution", "high resolution")):
        cues.append("hrtem_cue")
    if any(term in folded for term in ("saed", "selected area", "diffraction")) or "diff" in basename:
        cues.append("saed_cue")
    if any(term in folded for term in ("bright-field", "bright field", "bf_", "_bf")):
        cues.append("bright_field_cue")
    if any(term in folded for term in ("sem", "scanning electron")):
        cues.append("sem_cue")
    if any(term in folded for term in ("eds", "edx", "energy-dispersive")):
        cues.append("eds_cue")
    if any(term in folded for term in ("nanosims", "ftir", "omat")):
        cues.append("non_tem_measurement_cue")
    return cues


def representation_from_name(filename: str, content_type: str) -> str:
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix in {".dm3", ".dm4", ".emd", ".ser", ".emi", ".mrc", ".mrcs"}:
        return "native_microscopy_container"
    if suffix in {".tif", ".tiff", ".png", ".bmp"}:
        return "raster_image"
    if suffix in {".jpg", ".jpeg", ".gif", ".webp"}:
        return "rendered_or_lossy_raster"
    if suffix in {".xlsx", ".xls", ".csv", ".txt", ".doc", ".docx", ".pdf"}:
        return "table_or_document"
    if "image/" in content_type.casefold():
        return "image_unresolved_extension"
    return "other_or_unresolved"


def normalize_files(
    records: Sequence[Mapping[str, Any]], folder_paths: Mapping[str, str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        file_id = _file_id(record)
        filename = _file_name(record)
        if not file_id or not filename:
            raise MendeleyAuditError("Mendeley file record lacks id or filename")
        if file_id in seen_ids:
            raise MendeleyAuditError(f"duplicate Mendeley file id: {file_id}")
        seen_ids.add(file_id)
        folder_id = _folder_id(record)
        folder_path = folder_paths.get(folder_id, "")
        path = PurePosixPath(folder_path, filename).as_posix() if folder_path else filename
        content_type = _content_type(record)
        rows.append(
            {
                "file_id": file_id,
                "filename": filename,
                "folder_id": folder_id,
                "folder_path": folder_path,
                "path": path,
                "bytes": _file_size(record),
                "sha256": _file_sha256(record),
                "content_type": content_type,
                "download_url": _download_url(record),
                "suffix": PurePosixPath(filename).suffix.casefold(),
                "representation_class": representation_from_name(filename, content_type),
                "role_cues": classify_path(folder_path, filename),
            }
        )
    rows.sort(key=lambda item: item["path"].casefold())
    return rows


def select_header_candidates(rows: Sequence[Mapping[str, Any]], limits: Mapping[str, int]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        cues = set(row.get("role_cues") or [])
        if not ({"tem_cue", "hrtem_cue", "saed_cue", "bright_field_cue"} & cues):
            continue
        priority = (
            0 if "saed_cue" in cues else
            1 if row.get("representation_class") == "native_microscopy_container" else
            2 if "hrtem_cue" in cues else
            3
        )
        row["selection_priority"] = priority
        candidates.append(row)
    candidates.sort(
        key=lambda item: (
            int(item["selection_priority"]),
            int(item["bytes"] or 0),
            str(item["path"]).casefold(),
        )
    )
    return candidates[: limits["maximum_header_samples_per_dataset"]]


def classify_header(filename: str, sample: bytes) -> dict[str, Any]:
    suffix = PurePosixPath(filename).suffix.casefold()
    result: dict[str, Any] = {
        "sampled_bytes": len(sample),
        "sample_sha256": _hash_bytes(sample),
        "magic_class": "unknown",
    }
    if suffix == ".dm3" and len(sample) >= 12:
        result.update(
            {
                "magic_class": "digital_micrograph_dm3",
                "digital_micrograph_version_big_endian": int.from_bytes(sample[0:4], "big"),
                "digital_micrograph_byte_order_marker": int.from_bytes(sample[8:12], "big"),
            }
        )
    elif suffix == ".dm4" and len(sample) >= 16:
        result.update(
            {
                "magic_class": "digital_micrograph_dm4",
                "digital_micrograph_version_big_endian": int.from_bytes(sample[0:4], "big"),
                "digital_micrograph_declared_payload_bytes_big_endian": int.from_bytes(sample[4:12], "big"),
                "digital_micrograph_byte_order_marker": int.from_bytes(sample[12:16], "big"),
            }
        )
    elif sample.startswith((b"II*\x00", b"MM\x00*")):
        result["magic_class"] = "tiff"
    elif sample.startswith(b"BM"):
        result["magic_class"] = "bmp"
    elif sample.startswith(b"\x89PNG\r\n\x1a\n"):
        result["magic_class"] = "png"
    elif sample.startswith(b"\xff\xd8\xff"):
        result["magic_class"] = "jpeg"
    elif sample.startswith(b"PK\x03\x04"):
        result["magic_class"] = "zip_or_office_container"
    elif sample.startswith(b"%PDF"):
        result["magic_class"] = "pdf"
    return result


def _download_endpoint(dataset_id: str, version: int, file_id: str) -> str:
    quoted_dataset = urllib.parse.quote(dataset_id, safe="")
    quoted_file = urllib.parse.quote(file_id, safe="")
    return (
        f"https://{API_HOST}/datasets/{quoted_dataset}/files/"
        f"{quoted_file}/file_downloaded?version={version}"
    )


def probe_file_header(
    dataset_api_id: str,
    version: int,
    row: Mapping[str, Any],
    maximum_bytes: int,
) -> dict[str, Any]:
    direct = _string(row.get("download_url"))
    url = direct or _download_endpoint(dataset_api_id, version, str(row["file_id"]))
    _trusted_download_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/octet-stream,*/*;q=0.8",
            "Range": f"bytes=0-{maximum_bytes - 1}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            _trusted_download_url(response.geturl())
            sample = response.read(maximum_bytes)
            status = int(getattr(response, "status", response.getcode()))
            result = {
                "file_id": row["file_id"],
                "path": row["path"],
                "filename": row["filename"],
                "declared_bytes": row.get("bytes"),
                "declared_sha256": row.get("sha256"),
                "suffix": row["suffix"],
                "representation_class": row["representation_class"],
                "role_cues": row["role_cues"],
                "status_code": status,
                "content_type": str(response.headers.get("Content-Type", "")),
                "content_length_header": str(response.headers.get("Content-Length", "")),
                "content_range_header": str(response.headers.get("Content-Range", "")),
                "final_host": urllib.parse.urlsplit(response.geturl()).hostname,
                "final_path": urllib.parse.urlsplit(response.geturl()).path,
            }
            result.update(classify_header(str(row["filename"]), sample))
            return result
    except urllib.error.HTTPError as exc:
        sample = exc.read(maximum_bytes)
        return {
            "file_id": row["file_id"],
            "path": row["path"],
            "filename": row["filename"],
            "declared_bytes": row.get("bytes"),
            "declared_sha256": row.get("sha256"),
            "suffix": row["suffix"],
            "representation_class": row["representation_class"],
            "role_cues": row["role_cues"],
            "status_code": int(exc.code),
            "content_type": str(exc.headers.get("Content-Type", "")),
            "content_length_header": str(exc.headers.get("Content-Length", "")),
            "content_range_header": str(exc.headers.get("Content-Range", "")),
            "final_host": urllib.parse.urlsplit(exc.geturl()).hostname,
            "final_path": urllib.parse.urlsplit(exc.geturl()).path,
            "sampled_bytes": len(sample),
            "sample_sha256": _hash_bytes(sample),
            "magic_class": "http_error_response",
        }


def _api_url(path: str, query: Mapping[str, Any] | None = None) -> str:
    url = f"https://{API_HOST}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return url


def fetch_dataset_records(source: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    dataset_slug = str(source["dataset_id"])
    version = int(source["version"])
    dataset_url = _api_url(
        f"/datasets/{urllib.parse.quote(dataset_slug, safe='')}",
        {"version": version},
    )
    dataset_payload, dataset_response = _request_json(dataset_url, accept=DATASET_ACCEPT)
    if not isinstance(dataset_payload, Mapping):
        raise MendeleyAuditError("Mendeley dataset response must be an object")
    verified = verify_dataset(source, dataset_payload)
    api_id = verified["api_dataset_id"]

    endpoint_ids = []
    for value in (api_id, dataset_slug):
        if value not in endpoint_ids:
            endpoint_ids.append(value)

    files_payload: Any | None = None
    files_response: dict[str, Any] | None = None
    files_url = ""
    file_errors: list[str] = []
    for endpoint_id in endpoint_ids:
        candidate = _api_url(
            f"/datasets/publics/{urllib.parse.quote(endpoint_id, safe='')}/files",
            {"version": version, "$start": 0, "$limit": limits["maximum_file_records_per_dataset"]},
        )
        try:
            files_payload, files_response = _request_json(candidate)
            files_url = candidate
            break
        except MendeleyAuditError as exc:
            file_errors.append(str(exc))
    if files_payload is None or files_response is None:
        raise MendeleyAuditError("all Mendeley public-file endpoints failed: " + " | ".join(file_errors))
    file_records = _extract_list(files_payload, ("files", "results", "items"))
    if len(file_records) > limits["maximum_file_records_per_dataset"]:
        raise MendeleyAuditError("Mendeley file count exceeds frozen bound")

    folders_payload: Any = []
    folders_response: dict[str, Any] = {
        "status_code": None,
        "content_type": "",
        "response_bytes": 0,
        "response_sha256": "",
        "final_url": "",
    }
    folders_url = ""
    folder_errors: list[str] = []
    for endpoint_id in endpoint_ids:
        candidate = _api_url(
            f"/datasets/publics/{urllib.parse.quote(endpoint_id, safe='')}/folders",
            {"version": version},
        )
        try:
            folders_payload, folders_response = _request_json(candidate)
            folders_url = candidate
            break
        except MendeleyAuditError as exc:
            folder_errors.append(str(exc))
    folder_records = _extract_list(folders_payload, ("folders", "results", "items")) if folders_payload != [] else []
    if len(folder_records) > limits["maximum_folder_records_per_dataset"]:
        raise MendeleyAuditError("Mendeley folder count exceeds frozen bound")

    folder_paths = build_folder_paths(folder_records)
    files = normalize_files(file_records, folder_paths)
    return {
        "verified_dataset": verified,
        "dataset_payload": dict(dataset_payload),
        "dataset_response": dataset_response,
        "dataset_url": dataset_url,
        "files_url": files_url,
        "files_response": files_response,
        "folder_url": folders_url,
        "folder_response": folders_response,
        "folder_errors": folder_errors,
        "folders": folder_records,
        "folder_paths": folder_paths,
        "files": files,
    }


def _write_inventory(path: Path, dataset_id: str, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "dataset_id",
        "file_id",
        "path",
        "folder_id",
        "folder_path",
        "filename",
        "bytes",
        "sha256",
        "content_type",
        "suffix",
        "representation_class",
        "role_cues",
        "download_url_present",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "dataset_id": dataset_id,
                    "file_id": row["file_id"],
                    "path": row["path"],
                    "folder_id": row["folder_id"],
                    "folder_path": row["folder_path"],
                    "filename": row["filename"],
                    "bytes": row["bytes"] if row["bytes"] is not None else "",
                    "sha256": row["sha256"],
                    "content_type": row["content_type"],
                    "suffix": row["suffix"],
                    "representation_class": row["representation_class"],
                    "role_cues": ";".join(row["role_cues"]),
                    "download_url_present": bool(row["download_url"]),
                }
            )


def audit_source(source: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, Any]:
    fetched = fetch_dataset_records(source, limits)
    files = fetched["files"]
    candidates = select_header_candidates(files, limits)
    headers: list[dict[str, Any]] = []
    total_sampled = 0
    for row in candidates:
        if total_sampled >= limits["maximum_total_header_bytes_per_dataset"]:
            break
        remaining = limits["maximum_total_header_bytes_per_dataset"] - total_sampled
        maximum = min(limits["maximum_header_bytes_per_file"], remaining)
        if maximum <= 0:
            break
        header = probe_file_header(
            fetched["verified_dataset"]["api_dataset_id"],
            int(source["version"]),
            row,
            maximum,
        )
        headers.append(header)
        total_sampled += int(header["sampled_bytes"])

    representation_counts = Counter(str(row["representation_class"]) for row in files)
    suffix_counts = Counter(str(row["suffix"] or "<none>") for row in files)
    role_counts = Counter(cue for row in files for cue in row["role_cues"])
    magic_counts = Counter(str(row["magic_class"]) for row in headers)
    native_header_count = sum(
        1 for row in headers if row["magic_class"] in {"digital_micrograph_dm3", "digital_micrograph_dm4"}
    )
    raster_header_count = sum(
        1 for row in headers if row["magic_class"] in {"tiff", "bmp", "png", "jpeg"}
    )
    all_file_sha_supported = bool(files) and all(bool(row["sha256"]) for row in files)
    all_file_sizes_supported = bool(files) and all(row["bytes"] is not None for row in files)

    return {
        "dataset": fetched["verified_dataset"],
        "api_evidence": {
            "dataset_url": fetched["dataset_url"],
            "dataset_response": fetched["dataset_response"],
            "files_url": fetched["files_url"],
            "files_response": fetched["files_response"],
            "folders_url": fetched["folder_url"],
            "folders_response": fetched["folder_response"],
            "folder_endpoint_errors": fetched["folder_errors"],
        },
        "files": files,
        "folders": fetched["folders"],
        "header_samples": headers,
        "file_count": len(files),
        "folder_count": len(fetched["folders"]),
        "total_declared_file_bytes": sum(int(row["bytes"] or 0) for row in files),
        "representation_counts": dict(sorted(representation_counts.items())),
        "suffix_counts": dict(sorted(suffix_counts.items())),
        "role_cue_counts": dict(sorted(role_counts.items())),
        "header_magic_counts": dict(sorted(magic_counts.items())),
        "header_sample_count": len(headers),
        "total_header_bytes_sampled": total_sampled,
        "native_header_count": native_header_count,
        "raster_header_count": raster_header_count,
        "all_file_sizes_present": all_file_sizes_supported,
        "all_file_sha256_present": all_file_sha_supported,
        "source_quality_flags": source["source_quality_flags"],
    }


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MendeleyAuditError("output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [audit_source(source, config["limits"]) for source in config["sources"]]
    dataset_summaries: list[dict[str, Any]] = []
    for result in results:
        dataset = result["dataset"]
        dataset_summaries.append(
            {
                "dataset_id": dataset["requested_dataset_id"],
                "api_dataset_id": dataset["api_dataset_id"],
                "version": dataset["version"],
                "doi": dataset["doi"],
                "title": dataset["title"],
                "license_text": dataset["license_text"],
                "material_scope": dataset["material_scope"],
                "file_count": result["file_count"],
                "folder_count": result["folder_count"],
                "total_declared_file_bytes": result["total_declared_file_bytes"],
                "representation_counts": result["representation_counts"],
                "suffix_counts": result["suffix_counts"],
                "role_cue_counts": result["role_cue_counts"],
                "header_magic_counts": result["header_magic_counts"],
                "header_sample_count": result["header_sample_count"],
                "total_header_bytes_sampled": result["total_header_bytes_sampled"],
                "native_header_count": result["native_header_count"],
                "raster_header_count": result["raster_header_count"],
                "all_file_sizes_present": result["all_file_sizes_present"],
                "all_file_sha256_present": result["all_file_sha256_present"],
            }
        )

    any_native = any(item["native_header_count"] > 0 for item in dataset_summaries)
    any_raster = any(item["raster_header_count"] > 0 for item in dataset_summaries)
    summary = {
        "status": (
            "mendeley_lunar_tem_saed_file_inventory_and_bounded_header_audit_completed_"
            "but_calibration_lineage_and_independence_incomplete"
        ),
        "evidence_level": "Diagnostic",
        "dataset_count": len(results),
        "datasets": dataset_summaries,
        "evidence_assessment": {
            "dataset_doi_version_title_and_license": "Supported",
            "public_file_inventory_identity": "Supported",
            "file_sha256_identity": (
                "Supported" if all(item["all_file_sha256_present"] for item in dataset_summaries)
                else "Partial"
            ),
            "native_microscopy_container_presence": (
                "Supported" if any_native else "Unsupported_in_bounded_header_sample"
            ),
            "raster_export_presence": "Supported" if any_raster else "Inconclusive",
            "detector_native_intensity_preservation": "Inconclusive",
            "pattern_centre_and_reciprocal_calibration": "Inconclusive",
            "sample_acquisition_lineage_and_independence": "Inconclusive",
        },
        "readiness": {
            "cross_material_file_interoperability_diagnostic_ready": True,
            "calibrated_saed_validation_ready": False,
            "external_scientific_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "processing": {
            "source_files_retained": False,
            "pixel_arrays_exported": False,
            "image_preprocessing_performed": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "parameter_tuning_performed": False,
            "model_retraining_performed": False,
            "phase_indexing_performed": False,
        },
        "unresolved": [
            "authoritative sample and acquisition identifiers for every TEM and SAED file",
            "camera length, pattern centre, detector geometry and reciprocal-space calibration",
            "exposure, binning, gain, dark-current correction and saturation state",
            "whether raster files preserve detector-native intensities or are rendered/exported products",
            "complete preprocessing history and any scale-bar or contrast modifications",
            "independence from current analyzer development, threshold selection and tuning",
            "material-domain comparability with cobalt-oxide validation targets",
        ],
    }

    summary_path = output_dir / "mendeley_lunar_tem_saed_audit_summary.json"
    datasets_path = output_dir / "mendeley_lunar_dataset_api_evidence.json"
    inventory_path = output_dir / "mendeley_lunar_file_inventory.csv"
    headers_path = output_dir / "mendeley_lunar_header_samples.json"
    report_path = output_dir / "mendeley_lunar_tem_saed_audit_report.md"
    manifest_path = output_dir / "mendeley_lunar_tem_saed_audit_manifest.json"
    _json_dump(summary_path, summary)
    _json_dump(
        datasets_path,
        [
            {
                "dataset": result["dataset"],
                "api_evidence": result["api_evidence"],
                "folders": result["folders"],
            }
            for result in results
        ],
    )
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "dataset_id",
                "file_id",
                "path",
                "folder_id",
                "folder_path",
                "filename",
                "bytes",
                "sha256",
                "content_type",
                "suffix",
                "representation_class",
                "role_cues",
                "download_url_present",
            ],
        )
        writer.writeheader()
        for result in results:
            dataset_id = result["dataset"]["requested_dataset_id"]
            for row in result["files"]:
                writer.writerow(
                    {
                        "dataset_id": dataset_id,
                        "file_id": row["file_id"],
                        "path": row["path"],
                        "folder_id": row["folder_id"],
                        "folder_path": row["folder_path"],
                        "filename": row["filename"],
                        "bytes": row["bytes"] if row["bytes"] is not None else "",
                        "sha256": row["sha256"],
                        "content_type": row["content_type"],
                        "suffix": row["suffix"],
                        "representation_class": row["representation_class"],
                        "role_cues": ";".join(row["role_cues"]),
                        "download_url_present": bool(row["download_url"]),
                    }
                )
    _json_dump(
        headers_path,
        [
            {
                "dataset_id": result["dataset"]["requested_dataset_id"],
                "headers": result["header_samples"],
            }
            for result in results
        ],
    )
    lines = [
        "# Mendeley lunar TEM/SAED source audit",
        "",
        "## Result",
        "",
        f"- Status: `{summary['status']}`",
        "- Evidence level: **Diagnostic**",
        f"- Datasets audited: `{len(results)}`",
        "- Calibrated-SAED validation ready: **no**",
        "",
    ]
    for item in dataset_summaries:
        lines.extend(
            [
                f"## {item['dataset_id']} v{item['version']}",
                "",
                f"- DOI: `{item['doi']}`",
                f"- Files: `{item['file_count']}`",
                f"- Declared bytes: `{item['total_declared_file_bytes']}`",
                f"- Representations: `{json.dumps(item['representation_counts'], sort_keys=True)}`",
                f"- Header magic: `{json.dumps(item['header_magic_counts'], sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Scientific boundary",
            "",
            "The repository metadata and bounded file headers support source identity and file-format diagnostics only. Original-data wording does not prove detector-native intensities, reciprocal calibration, sample lineage or acquisition independence.",
            "",
            "No complete source file or pixel array is retained. No preprocessing, analyzer inference, annotation, phase indexing, tuning or retraining is performed.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    _json_dump(
        manifest_path,
        _artifact_manifest(
            output_dir,
            [summary_path, datasets_path, inventory_path, headers_path, report_path],
        ),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
