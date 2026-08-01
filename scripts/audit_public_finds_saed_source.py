"""Audit the public FINDS SAED example archive without persisting source images.

The audit verifies the pinned Zenodo archive, safely inventories ZIP members,
parses FINDS project files, resolves referenced images and optional d-spacing
files, and records image shape, stored representation, center bounds, and camera
constant conversion. It does not run SAED analysis or assign material, phase,
reflection, or zone-axis identity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

API_URL = "https://zenodo.org/api/records/{record_id}"
USER_AGENT = "materials-characterization-analyzer-finds-saed-audit/1.0"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".ijm", ".md", ".csv"}


class SourceAuditError(RuntimeError):
    """Raised when the pinned SAED source contract cannot be verified."""


def _request_bytes(url: str, *, timeout: int = 180) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SourceAuditError(f"HTTP {exc.code} while requesting source: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SourceAuditError(f"Could not reach source repository: {exc.reason}") from exc


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("case_id") != "public_finds_saed_source_audit":
        raise SourceAuditError("invalid FINDS SAED case config")
    return payload


def _record_files(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files")
    if isinstance(files, Mapping) and isinstance(files.get("entries"), Mapping):
        iterable = files["entries"].items()
    elif isinstance(files, list):
        iterable = ((None, item) for item in files)
    else:
        raise SourceAuditError("Zenodo metadata did not expose a supported file inventory")
    records = []
    for fallback_name, value in iterable:
        if not isinstance(value, Mapping):
            continue
        links = value.get("links") if isinstance(value.get("links"), Mapping) else {}
        records.append(
            {
                "filename": str(value.get("key") or value.get("filename") or fallback_name or ""),
                "size": value.get("size"),
                "checksum": value.get("checksum"),
                "content_url": links.get("content") or links.get("self") or value.get("download"),
                "file_id": value.get("id"),
            }
        )
    return records


def _license_identifier(metadata: Mapping[str, Any]) -> str | None:
    record_metadata = metadata.get("metadata")
    if not isinstance(record_metadata, Mapping):
        return None
    rights = record_metadata.get("rights")
    if isinstance(rights, list):
        identifiers = []
        for right in rights:
            if isinstance(right, Mapping):
                value = right.get("id") or right.get("title")
                if value:
                    identifiers.append(str(value))
        if identifiers:
            return " | ".join(identifiers)
    license_value = record_metadata.get("license")
    if isinstance(license_value, Mapping):
        value = license_value.get("id") or license_value.get("title")
        return str(value) if value else None
    if isinstance(license_value, str) and license_value.strip():
        return license_value.strip()
    return None


def _verify_archive(payload: bytes, configured: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    expected_algorithm = str(configured["checksum_algorithm"]).lower()
    expected_digest = str(configured["checksum"]).lower()
    repository_checksum = record.get("checksum")
    if isinstance(repository_checksum, str) and ":" in repository_checksum:
        algorithm, digest = repository_checksum.split(":", 1)
        if algorithm.lower() != expected_algorithm or digest.lower() != expected_digest:
            raise SourceAuditError("repository checksum differs from pinned archive contract")
    observed = hashlib.new(expected_algorithm, payload).hexdigest().lower()
    if observed != expected_digest:
        raise SourceAuditError("downloaded archive checksum mismatch")
    repository_size = record.get("size")
    if isinstance(repository_size, int) and repository_size != len(payload):
        raise SourceAuditError("downloaded archive byte size differs from repository metadata")
    configured_size = configured.get("expected_size_bytes")
    if configured_size is not None and configured_size != len(payload):
        raise SourceAuditError("downloaded archive byte size differs from pinned contract")
    return {
        "filename": configured["filename"],
        "bytes": len(payload),
        "source_checksum_algorithm": expected_algorithm,
        "source_checksum": expected_digest,
        "source_checksum_verified": True,
        "downloaded_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    seen: set[str] = set()
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
    return members


def _decode_text(payload: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise SourceAuditError("text member could not be decoded")


def _parse_float(value: str) -> float | None:
    try:
        number = float(value.strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _resolve_member_path(project_path: str, reference: str, inventory: Mapping[str, str]) -> str | None:
    reference_path = PurePosixPath(reference.replace("\\", "/"))
    candidates = [reference_path]
    parent = PurePosixPath(project_path).parent
    candidates.append(parent / reference_path)
    basename = reference_path.name.casefold()
    for candidate in candidates:
        match = inventory.get(candidate.as_posix().casefold())
        if match:
            return match
    basename_matches = [path for key, path in inventory.items() if PurePosixPath(path).name.casefold() == basename]
    return basename_matches[0] if len(basename_matches) == 1 else None


def _project_candidate(
    path: str,
    payload: bytes,
    inventory: Mapping[str, str],
) -> dict[str, Any] | None:
    text, encoding = _decode_text(payload)
    lines = [line.strip() for line in text.splitlines()]
    if len(lines) < 4:
        return None
    camera_constant = _parse_float(lines[1])
    center_x = _parse_float(lines[2])
    center_y = _parse_float(lines[3])
    if camera_constant is None or camera_constant <= 0 or center_x is None or center_y is None:
        return None
    image_path = _resolve_member_path(path, lines[0], inventory)
    d_values_reference = lines[4] if len(lines) >= 5 and lines[4] else None
    d_values_path = (
        _resolve_member_path(path, d_values_reference, inventory)
        if d_values_reference
        else None
    )
    return {
        "project_path": path,
        "project_encoding": encoding,
        "image_reference": lines[0],
        "image_path": image_path,
        "camera_constant_angstrom_pixel": camera_constant,
        "camera_constant_nm_pixel": 0.1 * camera_constant,
        "reciprocal_nm_inv_per_pixel": 10.0 / camera_constant,
        "center_x_px": center_x,
        "center_y_px": center_y,
        "d_values_reference": d_values_reference,
        "d_values_path": d_values_path,
    }


def _inspect_image(payload: bytes, path: str, project: Mapping[str, Any]) -> dict[str, Any]:
    array = np.frombuffer(payload, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SourceAuditError(f"referenced image could not be decoded: {path}")
    original_shape = list(image.shape)
    channel_count = 1 if image.ndim == 2 else int(image.shape[2])
    if image.ndim == 3:
        if channel_count == 4:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        elif channel_count == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            raise SourceAuditError(f"unsupported image channel count: {channel_count}")
    else:
        gray = image
    height, width = gray.shape
    center_x = float(project["center_x_px"])
    center_y = float(project["center_y_px"])
    center_in_bounds = 0 <= center_x <= width - 1 and 0 <= center_y <= height - 1
    full_annulus = min(center_x, center_y, width - 1 - center_x, height - 1 - center_y)
    suffix = PurePosixPath(path).suffix.lower()
    return {
        "path": path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source_extension": suffix,
        "source_representation": (
            "lossy_jpeg_rendered_image" if suffix in {".jpg", ".jpeg"} else "lossless_or_unresolved_image_container"
        ),
        "dtype": str(gray.dtype),
        "original_shape": original_shape,
        "grayscale_shape": [height, width],
        "channel_count": channel_count,
        "minimum_intensity": int(gray.min()),
        "maximum_intensity": int(gray.max()),
        "center_in_bounds": center_in_bounds,
        "maximum_complete_annulus_radius_px": float(full_annulus),
        "project_center_x_px": center_x,
        "project_center_y_px": center_y,
        "camera_constant_angstrom_pixel": project["camera_constant_angstrom_pixel"],
        "camera_constant_nm_pixel": project["camera_constant_nm_pixel"],
        "reciprocal_nm_inv_per_pixel": project["reciprocal_nm_inv_per_pixel"],
        "saed_analyzer_extension_supported_directly": suffix in {".png", ".tif", ".tiff", ".bmp"},
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise SourceAuditError("archive inventory is empty")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def _write_manifest(output: Path, paths: Sequence[Path]) -> None:
    records = []
    for path in paths:
        payload = path.read_bytes()
        records.append({
            "path": path.name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    (output / "source_audit_manifest.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "case_id": "public_finds_saed_source_audit",
            "artifact_count": len(records),
            "artifacts": records,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and (output.is_symlink() or not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    config = _load_config(config_path)
    metadata_payload = _request_bytes(API_URL.format(record_id=config["dataset"]["record_id"]))
    metadata = json.loads(metadata_payload.decode("utf-8"))
    records = _record_files(metadata)
    record = next((item for item in records if item["filename"] == config["archive"]["filename"]), None)
    if record is None:
        raise SourceAuditError("pinned FINDS archive is missing")
    content_url = record.get("content_url")
    if not isinstance(content_url, str) or not content_url.startswith("https://"):
        raise SourceAuditError("pinned FINDS archive has no HTTPS content URL")
    archive_payload = _request_bytes(content_url)
    archive_record = _verify_archive(archive_payload, config["archive"], record)

    inventory_rows: list[dict[str, Any]] = []
    projects: list[dict[str, Any]] = []
    image_records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mca-finds-saed-"):
        with zipfile.ZipFile(Path(tempfile.gettempdir()) / "unused", mode="w") if False else zipfile.ZipFile(
            __import__("io").BytesIO(archive_payload)
        ) as archive:
            members = _safe_members(archive)
            path_lookup = {PurePosixPath(info.filename).as_posix().casefold(): PurePosixPath(info.filename).as_posix() for info in members}
            payload_by_path: dict[str, bytes] = {}
            for info in members:
                path = PurePosixPath(info.filename).as_posix()
                if info.is_dir():
                    payload = b""
                else:
                    payload = archive.read(info)
                    payload_by_path[path] = payload
                suffix = PurePosixPath(path).suffix.lower()
                inventory_rows.append({
                    "path": path,
                    "is_directory": info.is_dir(),
                    "uncompressed_bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "sha256": hashlib.sha256(payload).hexdigest() if not info.is_dir() else None,
                    "suffix": suffix,
                    "member_class": (
                        "image" if suffix in IMAGE_EXTENSIONS else "text" if suffix in TEXT_EXTENSIONS else "other"
                    ),
                })
            for path, payload in payload_by_path.items():
                if PurePosixPath(path).suffix.lower() != ".txt" or len(payload) > 100_000:
                    continue
                candidate = _project_candidate(path, payload, path_lookup)
                if candidate is not None:
                    projects.append(candidate)
            for project in projects:
                image_path = project.get("image_path")
                if not isinstance(image_path, str):
                    continue
                image_payload = payload_by_path.get(image_path)
                if image_payload is None:
                    continue
                image_records.append(_inspect_image(image_payload, image_path, project))

    license_id = _license_identifier(metadata)
    resolved = [project for project in projects if project.get("image_path")]
    analyzable = [
        image for image in image_records
        if image["center_in_bounds"]
        and image["maximum_complete_annulus_radius_px"] >= 16
        and image["dtype"] in {"uint8", "uint16"}
    ]
    status = (
        "project_calibration_and_images_resolved_adapter_review_ready"
        if analyzable and license_id
        else "source_resolved_analysis_blocked"
    )
    summary = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "source": {
            "repository": config["dataset"]["repository"],
            "record_id": config["dataset"]["record_id"],
            "doi": config["dataset"]["doi"],
            "version": config["dataset"]["version"],
            "title": config["dataset"]["title"],
            "license": license_id,
            "archive": archive_record,
            "source_images_persisted": False,
        },
        "result_counts": {
            "archive_member_count": len(inventory_rows),
            "image_member_count": sum(row["member_class"] == "image" for row in inventory_rows),
            "project_candidate_count": len(projects),
            "resolved_project_image_count": len(resolved),
            "analyzable_project_image_count": len(analyzable),
        },
        "projects": projects,
        "images": image_records,
        "readiness": {
            "status": status,
            "archive_checksum_verified": True,
            "license_resolved": license_id is not None,
            "project_camera_constant_resolved": any(project["camera_constant_angstrom_pixel"] > 0 for project in projects),
            "project_center_resolved": any(project["center_x_px"] >= 0 and project["center_y_px"] >= 0 for project in projects),
            "source_images_persisted": False,
            "saed_analyzer_executed": False,
            "material_identity_resolved": False,
            "phase_or_zone_axis_assignment_performed": False,
        },
        "scientific_closeout": {
            "status": "Diagnostic" if analyzable else "Inconclusive",
            "result": status,
            "strongest_evidence": (
                "The pinned Zenodo archive and each ZIP member were checksum-bound, and FINDS project files were parsed into explicit image, camera-constant, and center records."
            ),
            "primary_limitation": (
                "The software-example archive does not by itself establish raw detector provenance, material identity, acquisition metadata, or crystallographic ground truth."
            ),
        },
    }
    inventory_path = output / "archive_inventory.csv"
    summary_path = output / "source_audit_summary.json"
    report_path = output / "source_audit_report.md"
    _write_csv(inventory_path, inventory_rows)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(
        "\n".join([
            "# Public FINDS SAED Source Audit",
            "",
            f"**Evidence level:** {summary['scientific_closeout']['status']}",
            "",
            f"**Result:** `{status}`",
            "",
            f"- Archive members: `{len(inventory_rows)}`",
            f"- Image members: `{summary['result_counts']['image_member_count']}`",
            f"- FINDS project candidates: `{len(projects)}`",
            f"- Resolved project images: `{len(resolved)}`",
            f"- License: `{license_id or 'unresolved'}`",
            "- Source images persisted: `false`",
            "- SAED analyzer executed: `false`",
            "",
            "This audit does not assign material, phase, reflection, or zone-axis identity.",
            "",
        ]),
        encoding="utf-8",
    )
    _write_manifest(output, [inventory_path, summary_path, report_path])
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("case_studies/public_finds_saed/case_config.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = run(args.config, args.output)
    print(json.dumps({
        "status": summary["readiness"]["status"],
        "license": summary["source"]["license"],
        "project_count": summary["result_counts"]["project_candidate_count"],
        "resolved_image_count": summary["result_counts"]["resolved_project_image_count"],
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
