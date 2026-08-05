from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import stat
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from PIL import Image, UnidentifiedImageError

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
RESULT = "checksum_verified_public_tem_saed_archives_but_validation_metadata_incomplete"
NATIVE_MICROSCOPY_SUFFIXES = {
    ".dm3",
    ".dm4",
    ".emd",
    ".ser",
    ".mrc",
    ".mrcs",
    ".h5",
    ".hdf5",
}
LOSSLESS_RASTER_SUFFIXES = {".tif", ".tiff", ".png"}
RENDERED_RASTER_SUFFIXES = {".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
FORBIDDEN_SOURCE_SUFFIXES = {
    ".zip",
    *NATIVE_MICROSCOPY_SUFFIXES,
    *LOSSLESS_RASTER_SUFFIXES,
    *RENDERED_RASTER_SUFFIXES,
}


class RepodCoFeNiAuditError(RuntimeError):
    """Raised when the live source fails the pinned audit contract."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {"case_id", "audit_date", "source", "scientific_boundary"}
    if set(payload) != expected:
        raise RepodCoFeNiAuditError("unexpected top-level config keys")
    source_keys = {
        "repository",
        "persistent_id",
        "doi",
        "record_url",
        "api_base",
        "version_number",
        "version_minor_number",
        "version_state",
        "file_license_name",
        "expected_record_file_count",
        "target_files",
    }
    if set(payload["source"]) != source_keys:
        raise RepodCoFeNiAuditError("unexpected source config keys")
    target_names = [row["name"] for row in payload["source"]["target_files"]]
    if len(target_names) != len(set(target_names)):
        raise RepodCoFeNiAuditError("target filenames must be unique")
    return payload


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _stream_download(
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
    with urllib.request.urlopen(request, timeout=120) as response, destination.open(
        "wb"
    ) as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
            observed_bytes += len(chunk)
    if observed_bytes != expected_bytes:
        raise RepodCoFeNiAuditError(
            f"download byte mismatch for {destination.name}: "
            f"{observed_bytes} != {expected_bytes}"
        )
    if md5.hexdigest() != expected_md5:
        raise RepodCoFeNiAuditError(f"download MD5 mismatch for {destination.name}")
    return {
        "bytes": observed_bytes,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def _normalize_inventory(latest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in latest.get("files", []):
        data_file = item.get("dataFile") or {}
        checksum = data_file.get("checksum") or {}
        rows.append(
            {
                "id": data_file.get("id"),
                "name": data_file.get("filename"),
                "bytes": data_file.get("filesize"),
                "md5": checksum.get("value"),
                "checksum_type": checksum.get("type"),
                "content_type": data_file.get("contentType"),
                "description": item.get("description") or "",
                "restricted": item.get("restricted"),
                "license_name": item.get("licenseName"),
            }
        )
    return sorted(rows, key=lambda row: str(row["name"]))


def _verify_source(
    config: dict[str, Any], payload: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if payload.get("status") != "OK":
        raise RepodCoFeNiAuditError("Dataverse API status is not OK")
    latest = payload.get("data", {}).get("latestVersion")
    if not isinstance(latest, dict):
        raise RepodCoFeNiAuditError("latestVersion is missing")
    source = config["source"]
    if latest.get("versionNumber") != source["version_number"]:
        raise RepodCoFeNiAuditError("major version mismatch")
    if latest.get("versionMinorNumber") != source["version_minor_number"]:
        raise RepodCoFeNiAuditError("minor version mismatch")
    if latest.get("versionState") != source["version_state"]:
        raise RepodCoFeNiAuditError("version state mismatch")

    inventory = _normalize_inventory(latest)
    if len(inventory) != source["expected_record_file_count"]:
        raise RepodCoFeNiAuditError("record file-count mismatch")
    by_name = {row["name"]: row for row in inventory}
    targets: list[dict[str, Any]] = []
    for expected in source["target_files"]:
        observed = by_name.get(expected["name"])
        if observed is None:
            raise RepodCoFeNiAuditError(f"missing target file: {expected['name']}")
        for key in ("md5", "content_type"):
            if observed[key] != expected[key]:
                raise RepodCoFeNiAuditError(
                    f"target mismatch for {expected['name']} field {key}"
                )
        if observed["checksum_type"] != "MD5":
            raise RepodCoFeNiAuditError("unsupported checksum type")
        if observed["restricted"] is not False:
            raise RepodCoFeNiAuditError("target file is restricted")
        if observed["license_name"] != source["file_license_name"]:
            raise RepodCoFeNiAuditError("target file licence mismatch")
        targets.append({**observed, "declared_role": expected["declared_role"]})
    return inventory, targets


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.endswith("/"):
        return ""
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RepodCoFeNiAuditError(f"unsafe archive member path: {name}")
    return path.as_posix()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _hash_stream(handle: BinaryIO) -> tuple[int, str, bytes]:
    digest = hashlib.sha256()
    total = 0
    chunks: list[bytes] = []
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
        chunks.append(chunk)
        total += len(chunk)
    return total, digest.hexdigest(), b"".join(chunks)


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return repr(value)


def _inspect_image(blob: bytes) -> dict[str, Any]:
    try:
        with Image.open(io.BytesIO(blob)) as image:
            tags: dict[str, Any] = {}
            if hasattr(image, "tag_v2"):
                for tag in (256, 257, 258, 270, 282, 283, 296, 305, 306):
                    if tag in image.tag_v2:
                        tags[str(tag)] = _json_value(image.tag_v2.get(tag))
            return {
                "image_decodable": True,
                "image_format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
                "frames": getattr(image, "n_frames", 1),
                "metadata_keys": sorted(str(key) for key in image.info),
                "selected_tiff_tags": tags,
            }
    except (UnidentifiedImageError, OSError, ValueError):
        return {"image_decodable": False}


def _representation_class(suffix: str) -> str:
    if suffix in NATIVE_MICROSCOPY_SUFFIXES:
        return "native_microscopy_container"
    if suffix in LOSSLESS_RASTER_SUFFIXES:
        return "lossless_or_lossless-capable_raster_export"
    if suffix in RENDERED_RASTER_SUFFIXES:
        return "rendered_raster"
    return "other_or_unresolved"


def _role_cues(path: str) -> list[str]:
    lower = path.casefold()
    cues = []
    if "saed" in lower or "diffraction" in lower:
        cues.append("saed_or_diffraction_name_cue")
    if "hrtem" in lower:
        cues.append("hrtem_name_cue")
    elif "tem" in lower:
        cues.append("tem_name_cue")
    if "haadf" in lower or "stem" in lower:
        cues.append("stem_name_cue")
    return cues


def inspect_zip(path: Path, source_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RepodCoFeNiAuditError(f"ZIP CRC failure: {bad_member}")
        for info in archive.infolist():
            normalized = _safe_member_name(info.filename)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                raise RepodCoFeNiAuditError(
                    f"duplicate normalized archive path: {normalized}"
                )
            seen.add(key)
            if _is_symlink(info):
                raise RepodCoFeNiAuditError(f"symlink archive member: {normalized}")
            with archive.open(info, "r") as handle:
                observed_bytes, sha256, blob = _hash_stream(handle)
            if observed_bytes != info.file_size:
                raise RepodCoFeNiAuditError(
                    f"archive member byte mismatch: {normalized}"
                )
            suffix = Path(normalized).suffix.casefold()
            image = _inspect_image(blob)
            rows.append(
                {
                    "source_archive": source_name,
                    "member_path": normalized,
                    "bytes": observed_bytes,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "sha256": sha256,
                    "suffix": suffix,
                    "representation_class": _representation_class(suffix),
                    "role_cues": _role_cues(normalized),
                    **image,
                }
            )
    return rows


def inspect_standalone(path: Path, source_name: str) -> dict[str, Any]:
    blob = path.read_bytes()
    suffix = path.suffix.casefold()
    return {
        "source_archive": None,
        "member_path": source_name,
        "bytes": len(blob),
        "compressed_bytes": None,
        "crc32": None,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "suffix": suffix,
        "representation_class": _representation_class(suffix),
        "role_cues": _role_cues(source_name),
        **_inspect_image(blob),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "source_archive",
        "member_path",
        "bytes",
        "compressed_bytes",
        "crc32",
        "sha256",
        "suffix",
        "representation_class",
        "role_cues",
        "image_decodable",
        "image_format",
        "mode",
        "width",
        "height",
        "frames",
        "metadata_keys",
        "selected_tiff_tags",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            for key in ("role_cues", "metadata_keys", "selected_tiff_tags"):
                serialized[key] = json.dumps(row.get(key), ensure_ascii=False, sort_keys=True)
            writer.writerow(serialized)


def _write_manifest(output: Path, artifact_names: list[str]) -> None:
    artifacts = []
    for name in artifact_names:
        path = output / name
        blob = path.read_bytes()
        artifacts.append(
            {"path": name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
        )
    (output / "repod_cofeni_tem_saed_source_audit_manifest.json").write_text(
        json.dumps(
            {"schema_version": "1.0", "artifact_count": len(artifacts), "artifacts": artifacts},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _count(rows: list[dict[str, Any]], key: str, value: str) -> int:
    return sum(row.get(key) == value for row in rows)


def build_summary(
    config: dict[str, Any],
    inventory: list[dict[str, Any]],
    downloaded: list[dict[str, Any]],
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    saed_named = sum(
        "saed_or_diffraction_name_cue" in row["role_cues"] for row in members
    )
    tem_named = sum(
        any(cue in row["role_cues"] for cue in ("tem_name_cue", "hrtem_name_cue"))
        for row in members
    )
    return {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "result": RESULT,
        "source": {
            "repository": config["source"]["repository"],
            "doi": config["source"]["doi"],
            "record_url": config["source"]["record_url"],
            "version": [
                config["source"]["version_number"],
                config["source"]["version_minor_number"],
            ],
            "file_license_name": config["source"]["file_license_name"],
        },
        "record_file_count": len(inventory),
        "target_file_count": len(downloaded),
        "archive_count": sum(row["name"].casefold().endswith(".zip") for row in downloaded),
        "audited_member_count": len(members),
        "saed_named_member_count": saed_named,
        "tem_or_hrtem_named_member_count": tem_named,
        "native_microscopy_member_count": _count(
            members, "representation_class", "native_microscopy_container"
        ),
        "lossless_raster_member_count": _count(
            members,
            "representation_class",
            "lossless_or_lossless-capable_raster_export",
        ),
        "rendered_raster_member_count": _count(
            members, "representation_class", "rendered_raster"
        ),
        "raw_detector_status_resolved": False,
        "sample_acquisition_lineage_resolved": False,
        "tem_independent_segmentation_labels_available": False,
        "saed_static_selected_area_mode_confirmed_per_member": False,
        "saed_pattern_center_resolved": False,
        "saed_reciprocal_calibration_resolved": False,
        "source_archives_retained": False,
        "source_images_retained": False,
        "model_inference_performed": False,
        "annotation_performed": False,
        "primary_parameters_changed": False,
        "external_validation_ready": False,
        "engineering_decision_ready": False,
        "intake_decision": "accepted_for_bounded_diagnostic_only",
        "source_audit_closeout": {
            "status": "Supported",
            "strongest_evidence": "Repository version, licence, file identity, archive integrity, and member hashes are verified live against the pinned source contract.",
            "primary_limitation": "The public record does not establish member-level raw-detector status, immutable sample/acquisition lineage, independent TEM labels, or traceable SAED centre and reciprocal calibration.",
        },
        "analyzer_scientific_evidence_level": "Inconclusive",
        "allowed_use": [
            "archive and member integrity evidence",
            "format and metadata diagnostics",
            "explicit cross-material robustness exploration after a separately frozen protocol",
        ],
        "prohibited_claims": [
            "cobalt-oxide in-domain TEM segmentation performance",
            "calibrated SAED d-spacing accuracy",
            "phase, reflection, or zone-axis confirmation from analyzer output alone",
            "engineering readiness",
        ],
    }


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    transient = output / "_transient"
    transient.mkdir()
    succeeded = False
    try:
        config = load_config(config_path)
        source = config["source"]
        metadata_url = (
            f"{source['api_base']}/api/datasets/:persistentId/?"
            + urllib.parse.urlencode({"persistentId": source["persistent_id"]})
        )
        payload = _fetch_json(metadata_url)
        inventory, targets = _verify_source(config, payload)

        downloaded: list[dict[str, Any]] = []
        members: list[dict[str, Any]] = []
        for target in targets:
            path = transient / target["name"]
            hashes = _stream_download(
                f"{source['api_base']}/api/access/datafile/{target['id']}",
                path,
                expected_bytes=target["bytes"],
                expected_md5=target["md5"],
            )
            downloaded.append({**target, **hashes})
            if path.suffix.casefold() == ".zip":
                members.extend(inspect_zip(path, target["name"]))
            else:
                members.append(inspect_standalone(path, target["name"]))

        summary = build_summary(config, inventory, downloaded, members)
        inventory_payload = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "repository_inventory": inventory,
            "downloaded_targets": downloaded,
        }
        member_payload = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "member_count": len(members),
            "members": members,
        }
        (output / "official_source_inventory.json").write_text(
            json.dumps(inventory_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "archive_member_inventory.json").write_text(
            json.dumps(member_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _write_csv(output / "archive_member_inventory.csv", members)
        (output / "repod_cofeni_tem_saed_source_audit_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report = (
            "# RepOD CoFeNi TEM/HRTEM/SAED Source Audit\n\n"
            f"- Result: `{RESULT}`\n"
            f"- Record files: {summary['record_file_count']}\n"
            f"- Audited target files: {summary['target_file_count']}\n"
            f"- Audited archive/image members: {summary['audited_member_count']}\n"
            f"- TEM/HRTEM filename cues: {summary['tem_or_hrtem_named_member_count']}\n"
            f"- SAED/diffraction filename cues: {summary['saed_named_member_count']}\n"
            "- External validation ready: false\n"
            "- Analyzer scientific evidence: Inconclusive\n\n"
            "The public files are suitable for a bounded source and format audit. "
            "They are not promoted to external validation because member-level raw status, "
            "sample/acquisition lineage, independent TEM labels, and traceable SAED centre "
            "and reciprocal calibration remain unresolved. No source image, archive, model "
            "inference, annotation, or parameter tuning is retained in the evidence package.\n"
        )
        (output / "repod_cofeni_tem_saed_source_audit_report.md").write_text(
            report, encoding="utf-8"
        )
        _write_manifest(
            output,
            [
                "official_source_inventory.json",
                "archive_member_inventory.json",
                "archive_member_inventory.csv",
                "repod_cofeni_tem_saed_source_audit_summary.json",
                "repod_cofeni_tem_saed_source_audit_report.md",
            ],
        )
        for path in output.rglob("*"):
            if path.is_file() and path.suffix.casefold() in FORBIDDEN_SOURCE_SUFFIXES:
                raise RepodCoFeNiAuditError(f"source file leaked into evidence: {path}")
        succeeded = True
        return summary
    finally:
        shutil.rmtree(transient, ignore_errors=True)
        if not succeeded and output.exists():
            shutil.rmtree(output, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.config, args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
