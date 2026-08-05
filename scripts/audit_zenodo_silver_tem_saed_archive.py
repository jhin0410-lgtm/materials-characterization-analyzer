from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import stat
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
RESULT = "checksum_verified_archive_inventory_completed_but_scientific_validation_metadata_incomplete"

NATIVE_MICROSCOPY_SUFFIXES = {
    ".dm3",
    ".dm4",
    ".emd",
    ".ser",
    ".mrc",
    ".mrcs",
    ".h5",
    ".hdf5",
    ".hspy",
    ".zspy",
}
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
}
FORBIDDEN_EVIDENCE_SUFFIXES = {
    ".zip",
    *NATIVE_MICROSCOPY_SUFFIXES,
    *LOSSLESS_RASTER_SUFFIXES,
    *RENDERED_RASTER_SUFFIXES,
}
SUPPORTED_COMPRESSION = {
    zipfile.ZIP_STORED: "stored",
    zipfile.ZIP_DEFLATED: "deflated",
    zipfile.ZIP_BZIP2: "bzip2",
    zipfile.ZIP_LZMA: "lzma",
}


class ZenodoArchiveAuditError(RuntimeError):
    """Raised when source identity or archive safety violates the frozen contract."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"case_id", "audit_date", "source", "limits", "scientific_boundary"}:
        raise ZenodoArchiveAuditError("unexpected top-level config keys")
    source = payload["source"]
    expected_source_keys = {
        "repository",
        "record_id",
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_license_id",
        "target_file",
    }
    if set(source) != expected_source_keys:
        raise ZenodoArchiveAuditError("unexpected source config keys")
    if set(source["target_file"]) != {"key", "exact_bytes", "md5"}:
        raise ZenodoArchiveAuditError("unexpected target-file config keys")

    limits = payload["limits"]
    expected_limit_keys = {
        "maximum_archive_bytes",
        "maximum_member_count",
        "maximum_total_uncompressed_bytes",
        "maximum_single_member_bytes",
        "maximum_member_compression_ratio",
        "maximum_total_member_hash_bytes",
    }
    if set(limits) != expected_limit_keys:
        raise ZenodoArchiveAuditError("unexpected limit keys")
    if source["target_file"]["exact_bytes"] > limits["maximum_archive_bytes"]:
        raise ZenodoArchiveAuditError("pinned archive exceeds maximum archive bytes")

    boundary = payload["scientific_boundary"]
    required_false = {
        "source_archive_retention_authorized",
        "source_files_may_be_uploaded_as_artifacts",
        "archive_members_may_be_uploaded_as_artifacts",
        "image_preprocessing_authorized",
        "model_inference_authorized",
        "annotation_authorized",
        "parameter_tuning_authorized",
        "external_validation_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if boundary["source_archive_download_authorized"] is not True:
        raise ZenodoArchiveAuditError("source download must be explicitly authorized")
    if boundary["archive_member_inventory_authorized"] is not True:
        raise ZenodoArchiveAuditError("archive inventory must be explicitly authorized")
    if boundary["archive_member_hashing_authorized"] is not True:
        raise ZenodoArchiveAuditError("archive member hashing must be explicitly authorized")
    if any(boundary[key] is not False for key in required_false):
        raise ZenodoArchiveAuditError("scientific boundary must remain fail-closed")
    return payload


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _resource_type_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("resource_type")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        identifier = value.get("id") or value.get("type")
        return str(identifier) if identifier is not None else None
    return None


def _license_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        identifier = value.get("id")
        return str(identifier) if identifier is not None else None
    return None


def normalize_record(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    files: list[dict[str, Any]] = []
    for item in payload.get("files") or []:
        links = item.get("links") or {}
        files.append(
            {
                "id": item.get("id"),
                "key": item.get("key"),
                "bytes": item.get("size"),
                "checksum": item.get("checksum"),
                "content_url": links.get("content") or links.get("self"),
            }
        )
    files.sort(key=lambda row: str(row["key"]))
    return {
        "id": payload.get("id"),
        "doi": payload.get("doi") or metadata.get("doi"),
        "status": payload.get("status"),
        "resource_type_id": _resource_type_id(metadata),
        "license_id": _license_id(metadata),
        "publication_date": metadata.get("publication_date"),
        "created": payload.get("created"),
        "updated": payload.get("updated"),
        "files": files,
    }


def verify_record(config: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    source = config["source"]
    expected = {
        "id": source["record_id"],
        "doi": source["doi"],
        "status": source["expected_status"],
        "resource_type_id": source["expected_resource_type"],
        "license_id": source["expected_license_id"],
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise ZenodoArchiveAuditError(
                f"record mismatch for {key}: {record.get(key)!r} != {value!r}"
            )
    target_config = source["target_file"]
    by_key = {row["key"]: row for row in record["files"]}
    target = by_key.get(target_config["key"])
    if target is None:
        raise ZenodoArchiveAuditError("target archive is missing")
    if target["bytes"] != target_config["exact_bytes"]:
        raise ZenodoArchiveAuditError("target archive byte count changed")
    if target["checksum"] != f"md5:{target_config['md5']}":
        raise ZenodoArchiveAuditError("target archive checksum changed")
    content_url = target.get("content_url")
    if not isinstance(content_url, str) or not content_url:
        raise ZenodoArchiveAuditError("target archive content URL is missing")
    parsed = urllib.parse.urlparse(content_url)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise ZenodoArchiveAuditError("target content URL is outside the pinned Zenodo host")
    return target


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
    with urllib.request.urlopen(request, timeout=600) as response, destination.open(
        "wb"
    ) as handle:
        while chunk := response.read(4 * 1024 * 1024):
            handle.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
            observed_bytes += len(chunk)
            if observed_bytes > expected_bytes:
                raise ZenodoArchiveAuditError("download exceeded pinned byte count")
    if observed_bytes != expected_bytes:
        raise ZenodoArchiveAuditError(
            f"download byte mismatch: {observed_bytes} != {expected_bytes}"
        )
    if md5.hexdigest() != expected_md5:
        raise ZenodoArchiveAuditError("download MD5 mismatch")
    return {
        "bytes": observed_bytes,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.endswith("/"):
        return ""
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ZenodoArchiveAuditError(f"unsafe archive member path: {name}")
    return path.as_posix()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _representation_class(suffix: str) -> str:
    if suffix in NATIVE_MICROSCOPY_SUFFIXES:
        return "native_microscopy_container"
    if suffix in LOSSLESS_RASTER_SUFFIXES:
        return "lossless_or_lossless-capable_raster_export"
    if suffix in RENDERED_RASTER_SUFFIXES:
        return "rendered_raster"
    if suffix in TEXT_METADATA_SUFFIXES:
        return "metadata_or_document"
    return "other_or_unresolved"


def _role_cues(path: str) -> list[str]:
    lower = path.casefold()
    cues: list[str] = []
    if "saed" in lower or "diffraction" in lower:
        cues.append("saed_or_diffraction_name_cue")
    if "hrtem" in lower:
        cues.append("hrtem_name_cue")
    elif "tem" in lower:
        cues.append("tem_name_cue")
    if "haadf" in lower or "stem" in lower:
        cues.append("stem_name_cue")
    if "raw" in lower:
        cues.append("raw_name_cue_only")
    if "calib" in lower or "scale" in lower:
        cues.append("calibration_name_cue")
    if "meta" in lower or "readme" in lower:
        cues.append("metadata_name_cue")
    return cues


def _hash_member(handle: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    while chunk := handle.read(4 * 1024 * 1024):
        digest.update(chunk)
        total += len(chunk)
    return total, digest.hexdigest()


def inspect_archive(path: Path, limits: dict[str, Any]) -> dict[str, Any]:
    if not zipfile.is_zipfile(path):
        raise ZenodoArchiveAuditError("target is not a valid ZIP archive")

    rows: list[dict[str, Any]] = []
    infos: list[zipfile.ZipInfo] = []
    seen: set[str] = set()
    total_compressed = 0
    total_uncompressed = 0

    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                normalized = _safe_member_name(info.filename)
                if not normalized:
                    continue
                key = normalized.casefold()
                if key in seen:
                    raise ZenodoArchiveAuditError(
                        f"duplicate normalized archive path: {normalized}"
                    )
                seen.add(key)
                if info.flag_bits & 0x1:
                    raise ZenodoArchiveAuditError(
                        f"encrypted archive member is not allowed: {normalized}"
                    )
                if _is_symlink(info):
                    raise ZenodoArchiveAuditError(
                        f"symlink archive member is not allowed: {normalized}"
                    )
                compression_name = SUPPORTED_COMPRESSION.get(info.compress_type)
                if compression_name is None:
                    raise ZenodoArchiveAuditError(
                        f"unsupported compression method for {normalized}: {info.compress_type}"
                    )
                if info.file_size > limits["maximum_single_member_bytes"]:
                    raise ZenodoArchiveAuditError(
                        f"member exceeds single-member byte limit: {normalized}"
                    )
                ratio = (
                    float(info.file_size) / float(info.compress_size)
                    if info.compress_size > 0
                    else (0.0 if info.file_size == 0 else float("inf"))
                )
                if ratio > float(limits["maximum_member_compression_ratio"]):
                    raise ZenodoArchiveAuditError(
                        f"member compression ratio exceeds limit: {normalized}"
                    )
                suffix = Path(normalized).suffix.casefold()
                rows.append(
                    {
                        "member_path": normalized,
                        "bytes": info.file_size,
                        "compressed_bytes": info.compress_size,
                        "compression": compression_name,
                        "compression_ratio": ratio,
                        "crc32": f"{info.CRC:08x}",
                        "suffix": suffix,
                        "representation_class": _representation_class(suffix),
                        "role_cues": _role_cues(normalized),
                        "sha256": None,
                        "hash_status": "pending",
                    }
                )
                infos.append(info)
                total_compressed += info.compress_size
                total_uncompressed += info.file_size

            if len(rows) > limits["maximum_member_count"]:
                raise ZenodoArchiveAuditError("archive member count exceeds limit")
            if total_uncompressed > limits["maximum_total_uncompressed_bytes"]:
                raise ZenodoArchiveAuditError("total uncompressed bytes exceed limit")
            if total_uncompressed > limits["maximum_total_member_hash_bytes"]:
                raise ZenodoArchiveAuditError("member hashing budget would be exceeded")

            for row, info in zip(rows, infos, strict=True):
                with archive.open(info, "r") as handle:
                    observed_bytes, sha256 = _hash_member(handle)
                if observed_bytes != info.file_size:
                    raise ZenodoArchiveAuditError(
                        f"member byte mismatch after streaming: {row['member_path']}"
                    )
                row["sha256"] = sha256
                row["hash_status"] = "complete_crc_verified_at_eof"
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        if isinstance(exc, ZenodoArchiveAuditError):
            raise
        raise ZenodoArchiveAuditError(f"ZIP audit failed: {exc}") from exc

    overall_ratio = (
        float(total_uncompressed) / float(total_compressed)
        if total_compressed > 0
        else 0.0
    )
    return {
        "members": rows,
        "member_count": len(rows),
        "total_compressed_bytes": total_compressed,
        "total_uncompressed_bytes": total_uncompressed,
        "overall_compression_ratio": overall_ratio,
        "member_hashing_complete": all(row["sha256"] for row in rows),
        "crc_verification_complete": all(
            row["hash_status"] == "complete_crc_verified_at_eof" for row in rows
        ),
    }


def _count(rows: list[dict[str, Any]], representation: str) -> int:
    return sum(row["representation_class"] == representation for row in rows)


def _cue_count(rows: list[dict[str, Any]], cue: str) -> int:
    return sum(cue in row["role_cues"] for row in rows)


def build_summary(
    config: dict[str, Any],
    record: dict[str, Any],
    archive_hashes: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    rows = inventory["members"]
    return {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "result": RESULT,
        "source": {
            "repository": config["source"]["repository"],
            "record_id": record["id"],
            "doi": record["doi"],
            "status": record["status"],
            "resource_type_id": record["resource_type_id"],
            "license_id": record["license_id"],
            "publication_date": record["publication_date"],
        },
        "archive": {
            "key": config["source"]["target_file"]["key"],
            **archive_hashes,
            "member_count": inventory["member_count"],
            "total_compressed_bytes": inventory["total_compressed_bytes"],
            "total_uncompressed_bytes": inventory["total_uncompressed_bytes"],
            "overall_compression_ratio": inventory["overall_compression_ratio"],
            "member_hashing_complete": inventory["member_hashing_complete"],
            "crc_verification_complete": inventory["crc_verification_complete"],
        },
        "representation_counts": {
            "native_microscopy_container": _count(rows, "native_microscopy_container"),
            "lossless_or_lossless-capable_raster_export": _count(
                rows, "lossless_or_lossless-capable_raster_export"
            ),
            "rendered_raster": _count(rows, "rendered_raster"),
            "metadata_or_document": _count(rows, "metadata_or_document"),
            "other_or_unresolved": _count(rows, "other_or_unresolved"),
        },
        "name_cue_counts": {
            "saed_or_diffraction": _cue_count(rows, "saed_or_diffraction_name_cue"),
            "tem": _cue_count(rows, "tem_name_cue"),
            "hrtem": _cue_count(rows, "hrtem_name_cue"),
            "stem": _cue_count(rows, "stem_name_cue"),
            "raw_name_cue_only": _cue_count(rows, "raw_name_cue_only"),
            "calibration": _cue_count(rows, "calibration_name_cue"),
            "metadata": _cue_count(rows, "metadata_name_cue"),
        },
        "source_archive_retained": False,
        "source_members_retained": False,
        "image_preprocessing_performed": False,
        "model_inference_performed": False,
        "annotation_performed": False,
        "primary_parameters_changed": False,
        "raw_detector_status_resolved": False,
        "sample_acquisition_lineage_resolved": False,
        "tem_independent_segmentation_labels_available": False,
        "saed_static_selected_area_mode_confirmed_per_member": False,
        "saed_pattern_center_resolved": False,
        "saed_reciprocal_calibration_resolved": False,
        "source_audit_closeout": {
            "status": "Supported",
            "strongest_evidence": "The exact 1,417,789,651-byte public archive, repository MD5, computed SHA-256, ZIP safety constraints, member CRC values, and streamed member SHA-256 values are verified.",
            "primary_limitation": "Archive integrity and representation inventory do not establish raw-detector status, immutable sample/acquisition lineage, independent TEM labels, static-SAED acquisition, pattern centre, or reciprocal calibration.",
        },
        "analyzer_scientific_evidence_level": "Inconclusive",
        "intake_decision": "accepted_for_bounded_diagnostic_only",
        "external_validation_ready": False,
        "engineering_decision_ready": False,
        "allowed_use": [
            "checksum-bound archive and member identity evidence",
            "file-format and representation diagnostics",
            "metadata-gap assessment",
        ],
        "prohibited_claims": [
            "cobalt-oxide in-domain TEM segmentation performance",
            "calibrated SAED d-spacing accuracy",
            "phase, reflection, or zone-axis confirmation from analyzer output alone",
            "engineering readiness",
        ],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "member_path",
        "bytes",
        "compressed_bytes",
        "compression",
        "compression_ratio",
        "crc32",
        "sha256",
        "hash_status",
        "suffix",
        "representation_class",
        "role_cues",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["role_cues"] = json.dumps(row["role_cues"], ensure_ascii=False)
            writer.writerow(serialized)


def _write_manifest(output: Path, names: list[str]) -> None:
    artifacts = []
    for name in names:
        path = output / name
        blob = path.read_bytes()
        artifacts.append(
            {"path": name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
        )
    (output / "zenodo_silver_tem_saed_archive_audit_manifest.json").write_text(
        json.dumps(
            {"schema_version": "1.0", "artifact_count": len(artifacts), "artifacts": artifacts},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    transient = output / "_transient"
    transient.mkdir()
    succeeded = False
    try:
        config = load_config(config_path)
        payload = fetch_json(config["source"]["api_url"])
        record = normalize_record(payload)
        target = verify_record(config, record)

        archive_path = transient / config["source"]["target_file"]["key"]
        archive_hashes = stream_download(
            target["content_url"],
            archive_path,
            expected_bytes=config["source"]["target_file"]["exact_bytes"],
            expected_md5=config["source"]["target_file"]["md5"],
        )
        inventory = inspect_archive(archive_path, config["limits"])
        summary = build_summary(config, record, archive_hashes, inventory)

        record_snapshot = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "record": record,
            "verified_target": {
                "key": target["key"],
                "bytes": target["bytes"],
                "checksum": target["checksum"],
                "computed_sha256": archive_hashes["sha256"],
            },
        }
        inventory_payload = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "member_count": inventory["member_count"],
            "total_compressed_bytes": inventory["total_compressed_bytes"],
            "total_uncompressed_bytes": inventory["total_uncompressed_bytes"],
            "overall_compression_ratio": inventory["overall_compression_ratio"],
            "member_hashing_complete": inventory["member_hashing_complete"],
            "crc_verification_complete": inventory["crc_verification_complete"],
            "members": inventory["members"],
        }
        (output / "official_zenodo_record_snapshot.json").write_text(
            json.dumps(record_snapshot, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "archive_member_inventory.json").write_text(
            json.dumps(inventory_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _write_csv(output / "archive_member_inventory.csv", inventory["members"])
        (output / "zenodo_silver_tem_saed_archive_audit_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report = (
            "# Zenodo Silver TEM/SAED Archive Audit\n\n"
            f"- Result: `{RESULT}`\n"
            f"- Archive bytes: {summary['archive']['bytes']}\n"
            f"- Archive SHA-256: `{summary['archive']['sha256']}`\n"
            f"- Members: {summary['archive']['member_count']}\n"
            f"- Total uncompressed bytes: {summary['archive']['total_uncompressed_bytes']}\n"
            f"- Native microscopy containers: {summary['representation_counts']['native_microscopy_container']}\n"
            f"- Lossless-capable raster exports: {summary['representation_counts']['lossless_or_lossless-capable_raster_export']}\n"
            f"- Rendered rasters: {summary['representation_counts']['rendered_raster']}\n"
            f"- SAED/diffraction filename cues: {summary['name_cue_counts']['saed_or_diffraction']}\n"
            "- Source content retained: false\n"
            "- Model inference or parameter tuning: false\n"
            "- External validation ready: false\n"
            "- Analyzer scientific evidence: Inconclusive\n\n"
            "The archive and member identities are verified. Scientific validation remains "
            "blocked by unresolved raw status, sample/acquisition lineage, independent TEM "
            "labels, static-SAED acquisition, pattern centre, and reciprocal calibration.\n"
        )
        (output / "zenodo_silver_tem_saed_archive_audit_report.md").write_text(
            report, encoding="utf-8"
        )
        _write_manifest(
            output,
            [
                "official_zenodo_record_snapshot.json",
                "archive_member_inventory.json",
                "archive_member_inventory.csv",
                "zenodo_silver_tem_saed_archive_audit_summary.json",
                "zenodo_silver_tem_saed_archive_audit_report.md",
            ],
        )

        shutil.rmtree(transient, ignore_errors=True)
        leaked = [
            path
            for path in output.rglob("*")
            if path.is_file() and path.suffix.casefold() in FORBIDDEN_EVIDENCE_SUFFIXES
        ]
        if leaked:
            raise ZenodoArchiveAuditError(f"source content leaked into evidence: {leaked}")
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
