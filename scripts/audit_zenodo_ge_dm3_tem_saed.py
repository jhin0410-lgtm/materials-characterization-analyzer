from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
RESULT = (
    "checksum_verified_native_dm3_tem_saed_inventory_completed_but_"
    "calibration_lineage_and_reuse_metadata_incomplete"
)

NATIVE_MICROSCOPY_SUFFIXES = {".dm3", ".dm4", ".emd", ".ser", ".emi", ".mrc", ".mrcs"}
LOSSLESS_RASTER_SUFFIXES = {".tif", ".tiff", ".png", ".bmp"}
RENDERED_RASTER_SUFFIXES = {".jpg", ".jpeg", ".gif", ".webp"}
TEXT_METADATA_SUFFIXES = {
    ".txt",
    ".csv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".md",
    ".xlsx",
    ".xls",
    ".pdf",
    ".ras",
    ".emsa",
}
FORBIDDEN_EVIDENCE_SUFFIXES = {
    ".7z",
    ".zip",
    *NATIVE_MICROSCOPY_SUFFIXES,
    *LOSSLESS_RASTER_SUFFIXES,
    *RENDERED_RASTER_SUFFIXES,
}


class ZenodoGeDm3AuditError(RuntimeError):
    """Raised when source identity, archive safety, or the frozen audit contract fails."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_top = {"case_id", "audit_date", "source", "limits", "scientific_boundary"}
    if set(payload) != expected_top:
        raise ZenodoGeDm3AuditError("unexpected top-level config keys")

    source = payload["source"]
    expected_source = {
        "repository",
        "record_id",
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_title",
        "expected_license_id",
        "target_file",
        "required_member_basenames",
        "source_quality_flags",
    }
    if set(source) != expected_source:
        raise ZenodoGeDm3AuditError("unexpected source config keys")
    if set(source["target_file"]) != {"key", "md5"}:
        raise ZenodoGeDm3AuditError("unexpected target-file config keys")
    required_basenames = source["required_member_basenames"]
    if not isinstance(required_basenames, list) or not required_basenames:
        raise ZenodoGeDm3AuditError("required_member_basenames must be non-empty")
    normalized_required = [str(value).strip().casefold() for value in required_basenames]
    if any(not value for value in normalized_required):
        raise ZenodoGeDm3AuditError("required member basenames must be non-empty")
    if len(normalized_required) != len(set(normalized_required)):
        raise ZenodoGeDm3AuditError("required member basenames must be unique")

    limits = payload["limits"]
    expected_limits = {
        "maximum_archive_bytes",
        "maximum_member_count",
        "maximum_total_uncompressed_bytes",
        "maximum_single_member_bytes",
        "maximum_member_compression_ratio",
        "maximum_selected_member_count",
        "maximum_selected_uncompressed_bytes",
    }
    if set(limits) != expected_limits:
        raise ZenodoGeDm3AuditError("unexpected limit keys")
    if any(not isinstance(value, int) or value <= 0 for value in limits.values()):
        raise ZenodoGeDm3AuditError("all limits must be positive integers")

    boundary = payload["scientific_boundary"]
    required_true = {
        "source_archive_download_authorized",
        "archive_member_inventory_authorized",
        "selected_dm3_metadata_inspection_authorized",
    }
    required_false = {
        "source_archive_retention_authorized",
        "source_files_may_be_uploaded_as_artifacts",
        "archive_members_may_be_uploaded_as_artifacts",
        "pixel_array_export_authorized",
        "image_preprocessing_authorized",
        "model_inference_authorized",
        "annotation_authorized",
        "parameter_tuning_authorized",
        "model_retraining_authorized",
        "external_validation_claim_authorized",
        "phase_indexing_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if any(boundary.get(key) is not True for key in required_true):
        raise ZenodoGeDm3AuditError("required bounded source operations are not authorized")
    if any(boundary.get(key) is not False for key in required_false):
        raise ZenodoGeDm3AuditError("scientific boundary must remain fail-closed")
    return payload


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _resource_type_id(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("resource_type")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        identifier = value.get("id") or value.get("type")
        return str(identifier) if identifier is not None else None
    return None


def _license_id(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        identifier = value.get("id")
        return str(identifier) if identifier is not None else None
    return None


def normalize_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    files: list[dict[str, Any]] = []
    raw_files = payload.get("files")
    if raw_files is None:
        raw_files = []
    if not isinstance(raw_files, list):
        raise ZenodoGeDm3AuditError("record files must be a list")
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            raise ZenodoGeDm3AuditError("record file entry must be an object")
        links = raw.get("links")
        if not isinstance(links, Mapping):
            links = {}
        files.append(
            {
                "id": raw.get("id"),
                "key": raw.get("key"),
                "bytes": raw.get("size"),
                "checksum": raw.get("checksum"),
                "content_url": links.get("content") or links.get("self"),
            }
        )
    files.sort(key=lambda item: str(item.get("key")))
    return {
        "id": payload.get("id"),
        "doi": payload.get("doi") or metadata.get("doi"),
        "status": payload.get("status"),
        "title": metadata.get("title"),
        "resource_type_id": _resource_type_id(metadata),
        "license_id": _license_id(metadata),
        "publication_date": metadata.get("publication_date"),
        "created": payload.get("created"),
        "updated": payload.get("updated"),
        "files": files,
    }


def verify_record(config: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source"]
    expected = {
        "id": source["record_id"],
        "doi": source["doi"],
        "status": source["expected_status"],
        "title": source["expected_title"],
        "resource_type_id": source["expected_resource_type"],
        "license_id": source["expected_license_id"],
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise ZenodoGeDm3AuditError(
                f"record mismatch for {key}: {record.get(key)!r} != {value!r}"
            )

    target_config = source["target_file"]
    files = record.get("files")
    if not isinstance(files, list):
        raise ZenodoGeDm3AuditError("normalized record files must be a list")
    by_key = {item.get("key"): item for item in files if isinstance(item, Mapping)}
    target = by_key.get(target_config["key"])
    if not isinstance(target, Mapping):
        raise ZenodoGeDm3AuditError("target archive is missing")
    size = target.get("bytes")
    if not isinstance(size, int) or size <= 0:
        raise ZenodoGeDm3AuditError("target archive byte count is invalid")
    if size > config["limits"]["maximum_archive_bytes"]:
        raise ZenodoGeDm3AuditError("target archive exceeds maximum archive bytes")
    if target.get("checksum") != f"md5:{target_config['md5']}":
        raise ZenodoGeDm3AuditError("target archive checksum changed")
    content_url = target.get("content_url")
    if not isinstance(content_url, str) or not content_url:
        raise ZenodoGeDm3AuditError("target archive content URL is missing")
    parsed = urllib.parse.urlparse(content_url)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise ZenodoGeDm3AuditError("target content URL is outside the pinned Zenodo host")
    return dict(target)


def stream_download(
    url: str,
    destination: Path,
    *,
    expected_bytes: int,
    expected_md5: str,
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    observed_bytes = 0
    with urllib.request.urlopen(request, timeout=600) as response, destination.open("wb") as handle:
        while chunk := response.read(4 * 1024 * 1024):
            handle.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
            observed_bytes += len(chunk)
            if observed_bytes > expected_bytes:
                raise ZenodoGeDm3AuditError("download exceeded record-declared byte count")
    if observed_bytes != expected_bytes:
        raise ZenodoGeDm3AuditError(
            f"download byte mismatch: {observed_bytes} != {expected_bytes}"
        )
    if md5.hexdigest() != expected_md5:
        raise ZenodoGeDm3AuditError("download MD5 mismatch")
    return {
        "bytes": observed_bytes,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def find_7z() -> str:
    for candidate in ("7z", "7zz", "7za"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise ZenodoGeDm3AuditError("7z executable is required for the bounded archive audit")


def find_exiftool() -> str:
    resolved = shutil.which("exiftool")
    if not resolved:
        raise ZenodoGeDm3AuditError("exiftool is required for selected DM3 metadata inspection")
    return resolved


def run_checked(command: Sequence[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ZenodoGeDm3AuditError(f"command failed to execute safely: {command[0]}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip().splitlines()
        detail = stderr[-1] if stderr else "no stderr"
        raise ZenodoGeDm3AuditError(
            f"command returned {result.returncode}: {command[0]}: {detail}"
        )
    return result


def test_archive(archive_path: Path, seven_zip: str) -> None:
    run_checked([seven_zip, "t", "-y", str(archive_path)], timeout=900)


def parse_7z_slt(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    in_members = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("----------"):
            in_members = True
            current = {}
            continue
        if not in_members:
            continue
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        if key in current:
            raise ZenodoGeDm3AuditError(f"duplicate 7z listing field: {key}")
        current[key] = value
    if current:
        records.append(current)
    if not records:
        raise ZenodoGeDm3AuditError("7z listing contained no archive members")
    return records


def _safe_member_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.endswith("/"):
        return ""
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ZenodoGeDm3AuditError(f"unsafe archive member path: {value}")
    if "\x00" in normalized:
        raise ZenodoGeDm3AuditError("archive member path contains a NUL byte")
    return path.as_posix()


def _optional_nonnegative_int(record: Mapping[str, str], key: str) -> int | None:
    raw = record.get(key)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ZenodoGeDm3AuditError(f"invalid integer in 7z listing: {key}") from exc
    if value < 0:
        raise ZenodoGeDm3AuditError(f"negative integer in 7z listing: {key}")
    return value


def _representation_class(suffix: str) -> str:
    if suffix in NATIVE_MICROSCOPY_SUFFIXES:
        return "native_microscopy_container"
    if suffix in LOSSLESS_RASTER_SUFFIXES:
        return "lossless_or_lossless_capable_raster_export"
    if suffix in RENDERED_RASTER_SUFFIXES:
        return "rendered_raster"
    if suffix in TEXT_METADATA_SUFFIXES:
        return "metadata_or_document"
    return "other_or_unresolved"


def role_cues(path: str) -> list[str]:
    folded = path.casefold()
    basename = PurePosixPath(path).name.casefold()
    cues: list[str] = []
    if "diff" in basename or "saed" in basename:
        cues.append("static_saed_name_cue")
    if "hrtem" in folded or basename.startswith(("w1", "w2", "w3", "w4", "w5", "r1")):
        cues.append("hrtem_name_cue")
    if "tem" in basename or basename == "w0 150k.dm3":
        cues.append("tem_name_cue")
    if "eds" in basename or PurePosixPath(path).suffix.casefold() == ".emsa":
        cues.append("eds_name_cue")
    if "calib" in folded or "camera" in folded or "center" in folded or "centre" in folded:
        cues.append("calibration_or_centre_name_cue")
    return cues


def normalize_7z_inventory(
    records: Iterable[Mapping[str, str]], limits: Mapping[str, int]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_uncompressed = 0
    for raw in records:
        folder = raw.get("Folder") == "+"
        path_value = raw.get("Path")
        if not isinstance(path_value, str):
            raise ZenodoGeDm3AuditError("7z member is missing Path")
        if folder or path_value.endswith(("/", "\\")):
            continue
        path = _safe_member_path(path_value)
        if not path:
            continue
        folded_path = path.casefold()
        if folded_path in seen:
            raise ZenodoGeDm3AuditError(f"duplicate normalized archive path: {path}")
        seen.add(folded_path)
        encrypted = raw.get("Encrypted", "-")
        if encrypted not in {"-", ""}:
            raise ZenodoGeDm3AuditError(f"encrypted archive member: {path}")
        attributes = raw.get("Attributes", "")
        if attributes.startswith("L") or raw.get("Symbolic Link"):
            raise ZenodoGeDm3AuditError(f"linked archive member: {path}")
        size = _optional_nonnegative_int(raw, "Size")
        packed_size = _optional_nonnegative_int(raw, "Packed Size")
        if size is None:
            raise ZenodoGeDm3AuditError(f"archive member size is missing: {path}")
        if size > limits["maximum_single_member_bytes"]:
            raise ZenodoGeDm3AuditError(f"archive member exceeds size limit: {path}")
        total_uncompressed += size
        if total_uncompressed > limits["maximum_total_uncompressed_bytes"]:
            raise ZenodoGeDm3AuditError("archive exceeds total uncompressed byte limit")
        ratio = size / max(packed_size or size or 1, 1)
        if ratio > limits["maximum_member_compression_ratio"]:
            raise ZenodoGeDm3AuditError(f"archive member compression ratio is excessive: {path}")
        suffix = PurePosixPath(path).suffix.casefold()
        rows.append(
            {
                "member_path": path,
                "uncompressed_bytes": size,
                "packed_bytes": packed_size,
                "compression_ratio": ratio,
                "modified": raw.get("Modified"),
                "attributes": attributes,
                "crc": raw.get("CRC"),
                "encrypted": False,
                "method": raw.get("Method"),
                "block": raw.get("Block"),
                "suffix": suffix,
                "representation_class": _representation_class(suffix),
                "role_cues": role_cues(path),
            }
        )
        if len(rows) > limits["maximum_member_count"]:
            raise ZenodoGeDm3AuditError("archive exceeds member-count limit")
    if not rows:
        raise ZenodoGeDm3AuditError("archive contains no regular files")
    rows.sort(key=lambda item: str(item["member_path"]).casefold())
    return rows


def list_archive(archive_path: Path, seven_zip: str, limits: Mapping[str, int]) -> list[dict[str, Any]]:
    result = run_checked([seven_zip, "l", "-slt", str(archive_path)], timeout=300)
    return normalize_7z_inventory(parse_7z_slt(result.stdout), limits)


def verify_required_members(
    rows: Sequence[Mapping[str, Any]], required_basenames: Sequence[str]
) -> dict[str, str]:
    by_basename: dict[str, list[str]] = {}
    for row in rows:
        path = str(row["member_path"])
        by_basename.setdefault(PurePosixPath(path).name.casefold(), []).append(path)
    resolved: dict[str, str] = {}
    for raw in required_basenames:
        basename = raw.strip().casefold()
        matches = by_basename.get(basename, [])
        if len(matches) != 1:
            raise ZenodoGeDm3AuditError(
                f"required member basename must resolve exactly once: {raw}: {len(matches)}"
            )
        resolved[raw] = matches[0]
    return resolved


def select_dm3_members(
    rows: Sequence[Mapping[str, Any]], limits: Mapping[str, int]
) -> list[dict[str, Any]]:
    selected = [
        dict(row)
        for row in rows
        if row.get("suffix") == ".dm3"
        and any(
            cue in set(row.get("role_cues") or [])
            for cue in ("static_saed_name_cue", "tem_name_cue", "hrtem_name_cue", "eds_name_cue")
        )
    ]
    if not selected:
        raise ZenodoGeDm3AuditError("no relevant DM3 microscopy members were found")
    if len(selected) > limits["maximum_selected_member_count"]:
        raise ZenodoGeDm3AuditError("selected DM3 member count exceeds limit")
    total = sum(int(row["uncompressed_bytes"]) for row in selected)
    if total > limits["maximum_selected_uncompressed_bytes"]:
        raise ZenodoGeDm3AuditError("selected DM3 bytes exceed limit")
    return selected


def extract_selected_members(
    archive_path: Path,
    seven_zip: str,
    selected: Sequence[Mapping[str, Any]],
    destination: Path,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=False)
    members = [str(row["member_path"]) for row in selected]
    run_checked(
        [seven_zip, "x", "-y", f"-o{destination}", str(archive_path), "--", *members],
        timeout=900,
    )
    extracted: list[Path] = []
    for row in selected:
        path = destination.joinpath(*PurePosixPath(str(row["member_path"])).parts)
        if not path.is_file() or path.is_symlink():
            raise ZenodoGeDm3AuditError(f"selected member was not safely extracted: {row['member_path']}")
        if path.stat().st_size != int(row["uncompressed_bytes"]):
            raise ZenodoGeDm3AuditError(f"selected member size mismatch: {row['member_path']}")
        extracted.append(path)
    return extracted


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_dm3_metadata(
    extracted: Sequence[Path], extraction_root: Path, exiftool: str
) -> list[dict[str, Any]]:
    result = run_checked(
        [exiftool, "-json", "-G1", "-a", "-s", *[str(path) for path in extracted]],
        timeout=300,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ZenodoGeDm3AuditError("exiftool did not return valid JSON") from exc
    if not isinstance(payload, list) or len(payload) != len(extracted):
        raise ZenodoGeDm3AuditError("exiftool result count mismatch")

    by_absolute = {str(path.resolve()): path for path in extracted}
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ZenodoGeDm3AuditError("exiftool metadata entry is not an object")
        source_file = item.get("SourceFile")
        if not isinstance(source_file, str):
            raise ZenodoGeDm3AuditError("exiftool metadata is missing SourceFile")
        path = by_absolute.get(str(Path(source_file).resolve()))
        if path is None:
            raise ZenodoGeDm3AuditError("exiftool returned metadata for an unexpected file")
        relative = path.relative_to(extraction_root).as_posix()
        sanitized = {
            key: value
            for key, value in item.items()
            if key != "SourceFile" and not key.casefold().endswith("directory")
        }
        rows.append(
            {
                "member_path": relative,
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
                "metadata_field_count": len(sanitized),
                "metadata": sanitized,
            }
        )
    rows.sort(key=lambda item: str(item["member_path"]).casefold())
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_inventory(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "member_path",
        "uncompressed_bytes",
        "packed_bytes",
        "compression_ratio",
        "modified",
        "attributes",
        "crc",
        "encrypted",
        "method",
        "block",
        "suffix",
        "representation_class",
        "role_cues",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "role_cues": "|".join(row.get("role_cues") or [])})


def _write_selected_identity(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = ["member_path", "bytes", "sha256", "metadata_field_count"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def _artifact_manifest(root: Path, artifacts: Sequence[Path]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "case_id": "zenodo_ge_dm3_tem_saed_source_audit",
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
            }
            for path in artifacts
        ],
    }


def _count(rows: Sequence[Mapping[str, Any]], field: str, value: str) -> int:
    return sum(row.get(field) == value for row in rows)


def _cue_count(rows: Sequence[Mapping[str, Any]], cue: str) -> int:
    return sum(cue in set(row.get("role_cues") or []) for row in rows)


def _report(summary: Mapping[str, Any]) -> str:
    counts = summary["representation_counts"]
    cues = summary["role_cue_counts"]
    return f"""# Zenodo Ge native-DM3 TEM/SAED source audit

## Result

- Status: `{summary['status']}`
- Evidence level: **Diagnostic**
- DOI: `{summary['record']['doi']}`
- Archive SHA-256: `{summary['archive']['sha256']}`
- Native microscopy members: {counts['native_microscopy_container']}
- Static-SAED filename cues: {cues['static_saed_name_cue']}
- TEM filename cues: {cues['tem_name_cue']}
- HRTEM filename cues: {cues['hrtem_name_cue']}
- External-validation ready: **no**

## Supported

The Zenodo record identity, archive MD5 and observed SHA-256, archive integrity, safe member inventory, required paired TEM/SAED member names, native DM3 representation and selected-member identities are supported for this source version.

## Limitations

This is a cross-material germanium source. The public record has no licence identifier, and source-assigned sample/acquisition IDs, pattern centres, reciprocal calibration provenance, acquisition independence and analyzer-development non-use remain unresolved. The record-reported correction for `w0 diff.dm3` is retained as a quality flag rather than silently changed.

No pixel arrays are exported, no image preprocessing or annotation is performed, and no analyzer inference, parameter tuning, model retraining, d-spacing validation or phase indexing is authorized.
"""


def run_audit(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if output_dir.exists():
        if output_dir.is_symlink() or any(output_dir.iterdir()):
            raise ZenodoGeDm3AuditError("output directory must be absent or empty")
        output_dir.rmdir()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        record = normalize_record(fetch_json(config["source"]["api_url"]))
        target = verify_record(config, record)
        seven_zip = find_7z()
        exiftool = find_exiftool()

        with tempfile.TemporaryDirectory(prefix="zenodo-ge-dm3-") as temp_name:
            temp_root = Path(temp_name)
            archive_path = temp_root / config["source"]["target_file"]["key"]
            archive_identity = stream_download(
                str(target["content_url"]),
                archive_path,
                expected_bytes=int(target["bytes"]),
                expected_md5=config["source"]["target_file"]["md5"],
            )
            test_archive(archive_path, seven_zip)
            inventory = list_archive(archive_path, seven_zip, config["limits"])
            required_members = verify_required_members(
                inventory, config["source"]["required_member_basenames"]
            )
            selected = select_dm3_members(inventory, config["limits"])
            extraction_root = temp_root / "selected"
            extracted = extract_selected_members(
                archive_path, seven_zip, selected, extraction_root
            )
            selected_metadata = inspect_dm3_metadata(extracted, extraction_root, exiftool)

        representation_counts = {
            value: _count(inventory, "representation_class", value)
            for value in (
                "native_microscopy_container",
                "lossless_or_lossless_capable_raster_export",
                "rendered_raster",
                "metadata_or_document",
                "other_or_unresolved",
            )
        }
        role_cue_counts = {
            cue: _cue_count(inventory, cue)
            for cue in (
                "static_saed_name_cue",
                "tem_name_cue",
                "hrtem_name_cue",
                "eds_name_cue",
                "calibration_or_centre_name_cue",
            )
        }
        if representation_counts["native_microscopy_container"] < len(required_members):
            raise ZenodoGeDm3AuditError("native microscopy inventory is smaller than required set")
        if role_cue_counts["static_saed_name_cue"] < 4:
            raise ZenodoGeDm3AuditError("fewer than four static-SAED name cues were found")
        if role_cue_counts["tem_name_cue"] < 4:
            raise ZenodoGeDm3AuditError("fewer than four TEM name cues were found")

        summary = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "audit_date": config["audit_date"],
            "status": RESULT,
            "record": record,
            "archive": {
                "key": target["key"],
                **archive_identity,
                "integrity_test_passed": True,
            },
            "member_count": len(inventory),
            "total_uncompressed_bytes": sum(int(row["uncompressed_bytes"]) for row in inventory),
            "representation_counts": representation_counts,
            "role_cue_counts": role_cue_counts,
            "required_members": required_members,
            "selected_dm3_member_count": len(selected_metadata),
            "source_quality_flags": list(config["source"]["source_quality_flags"]),
            "evidence_assessment": {
                "record_and_archive_identity": "Supported",
                "archive_integrity_and_safe_inventory": "Supported",
                "native_dm3_tem_saed_representation": "Supported",
                "record_declared_same_location_tem_saed_pairs": "Supported",
                "source_assigned_sample_and_acquisition_lineage": "Inconclusive",
                "pattern_centre_and_reciprocal_calibration": "Inconclusive",
                "reuse_authorization": "Inconclusive",
                "independent_tem_segmentation_validation": "Inconclusive",
                "calibrated_static_saed_validation": "Inconclusive",
            },
            "processing": {
                "source_archive_retained": False,
                "source_members_retained": False,
                "pixel_arrays_exported": False,
                "image_preprocessing_performed": False,
                "annotations_created": False,
                "model_inference_performed": False,
                "parameter_tuning_performed": False,
                "model_retraining_performed": False,
                "phase_indexing_performed": False,
            },
            "readiness": {
                "external_validation_ready": False,
                "engineering_decision_ready": False,
                "allowed_use": [
                    "native-DM3 format interoperability",
                    "archive and member identity diagnostics",
                    "TEM/SAED pairing and metadata-gap assessment",
                    "cross-material static-SAED software diagnostics under frozen parameters",
                ],
            },
            "unresolved": [
                "explicit dataset reuse licence or written permission",
                "source-assigned immutable sample and acquisition IDs",
                "minimum independent sample and acquisition count",
                "pattern-specific centre and reciprocal calibration provenance",
                "documented preprocessing state for every DM3 member",
                "verified non-use in analyzer development and selection",
                "task-matched crystallographic references frozen before inference",
            ],
        }

        summary_path = stage / "zenodo_ge_dm3_tem_saed_audit_summary.json"
        inventory_path = stage / "zenodo_ge_dm3_tem_saed_member_inventory.csv"
        selected_path = stage / "zenodo_ge_dm3_selected_member_identity.csv"
        metadata_path = stage / "zenodo_ge_dm3_selected_metadata.json"
        report_path = stage / "zenodo_ge_dm3_tem_saed_audit_report.md"
        manifest_path = stage / "zenodo_ge_dm3_tem_saed_audit_manifest.json"
        _write_json(summary_path, summary)
        _write_inventory(inventory_path, inventory)
        _write_selected_identity(selected_path, selected_metadata)
        _write_json(metadata_path, selected_metadata)
        report_path.write_text(_report(summary), encoding="utf-8")
        _write_json(
            manifest_path,
            _artifact_manifest(
                stage,
                [summary_path, inventory_path, selected_path, metadata_path, report_path],
            ),
        )

        leaked = [
            path
            for path in stage.rglob("*")
            if path.is_file() and path.suffix.casefold() in FORBIDDEN_EVIDENCE_SUFFIXES
        ]
        if leaked:
            raise ZenodoGeDm3AuditError("source-like files leaked into final evidence")
        stage.rename(output_dir)
        return summary
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Zenodo 15082448 native DM3 TEM/HRTEM/SAED source files without "
            "retaining source images or running analyzer inference."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_audit(args.config, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
