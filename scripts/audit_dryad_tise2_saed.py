from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


class DryadTiSe2AuditError(RuntimeError):
    """Raised when the pinned source contract is not satisfied."""


class DryadAccessError(DryadTiSe2AuditError):
    """Raised when a pinned Dryad download route rejects access."""

    def __init__(self, route: str, status: int | None, reason: str) -> None:
        super().__init__(f"Dryad access failed for {route}: {status} {reason}")
        self.route = route
        self.status = status
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "http_status": self.status,
            "reason": self.reason,
        }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DryadTiSe2AuditError(f"expected JSON object: {path}")
    return value


def _request(url: str) -> urllib.request.Request:
    headers = {
        "User-Agent": "materials-characterization-analyzer/0.11",
        "Accept": (
            "application/json, application/zip, "
            "application/octet-stream;q=0.9, */*;q=0.1"
        ),
    }
    token = os.environ.get("DRYAD_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(_request(url), timeout=90) as response:
            payload = json.load(response)
    except Exception as exc:
        raise DryadTiSe2AuditError(
            f"failed to fetch Dryad JSON: {url}"
        ) from exc
    if not isinstance(payload, dict):
        raise DryadTiSe2AuditError(
            f"Dryad endpoint returned no object: {url}"
        )
    return payload


def _link(payload: dict[str, Any], relation: str) -> str:
    links = payload.get("_links")
    item = links.get(relation) if isinstance(links, dict) else None
    href = item.get("href") if isinstance(item, dict) else item
    if not isinstance(href, str) or not href:
        raise DryadTiSe2AuditError(f"missing Dryad link: {relation}")
    return urllib.parse.urljoin("https://datadryad.org", href)


def _file_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: Any = None
    embedded = payload.get("_embedded")
    if isinstance(embedded, dict):
        for key in ("stash:files", "files"):
            if isinstance(embedded.get(key), list):
                candidates = embedded[key]
                break
    if candidates is None:
        for key in ("files", "items"):
            if isinstance(payload.get(key), list):
                candidates = payload[key]
                break
    if not isinstance(candidates, list) or not all(
        isinstance(item, dict) for item in candidates
    ):
        raise DryadTiSe2AuditError(
            "Dryad file-list response has no valid file array"
        )
    return candidates


def _file_name(item: dict[str, Any]) -> str:
    for key in ("path", "name", "filename"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return PurePosixPath(value).name
    raise DryadTiSe2AuditError("Dryad file entry has no filename")


def _file_id(item: dict[str, Any]) -> int:
    candidates: set[int] = set()
    for key in ("id", "fileId", "file_id", "stashId", "stash_id"):
        value = item.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            candidates.add(parsed)

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        elif isinstance(value, str):
            for match in re.finditer(
                r"(?:files|file_stream)/(\d+)"
                r"(?:/download)?(?:$|[?#])",
                value,
            ):
                candidates.add(int(match.group(1)))

    collect(item.get("_links"))
    if len(candidates) != 1:
        raise DryadTiSe2AuditError(
            "Dryad file ID is missing or ambiguous for "
            f"{_file_name(item)}: {sorted(candidates)}"
        )
    return next(iter(candidates))


def _download(
    url: str,
    target: Path,
    max_bytes: int,
    route: str,
) -> tuple[int, str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(
            _request(url), timeout=180
        ) as response, target.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise DryadTiSe2AuditError(
                        "Dryad download exceeds configured byte limit"
                    )
                md5.update(chunk)
                sha256.update(chunk)
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        target.unlink(missing_ok=True)
        raise DryadAccessError(
            route=route,
            status=exc.code,
            reason=str(exc.reason),
        ) from exc
    except urllib.error.URLError as exc:
        target.unlink(missing_ok=True)
        raise DryadAccessError(
            route=route,
            status=None,
            reason=str(exc.reason),
        ) from exc
    except DryadTiSe2AuditError:
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise DryadTiSe2AuditError(
            f"unexpected Dryad download failure for {route}"
        ) from exc
    return total, md5.hexdigest(), sha256.hexdigest()


def _stream_copy(
    source: BinaryIO,
    target: Path,
    max_bytes: int,
) -> tuple[int, str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    total = 0
    with target.open("wb") as handle:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise DryadTiSe2AuditError(
                    "embedded Dryad archive exceeds configured byte limit"
                )
            md5.update(chunk)
            sha256.update(chunk)
            handle.write(chunk)
    return total, md5.hexdigest(), sha256.hexdigest()


def _normalize_title(value: str) -> str:
    unescaped = html.unescape(value)
    no_markup = re.sub(r"<[^>]+>", " ", unescaped)
    normalized = unicodedata.normalize("NFKD", no_markup).casefold()
    return "".join(
        character for character in normalized if character.isalnum()
    )


def _title_matches(title: str, expected_tokens: list[str]) -> bool:
    normalized = _normalize_title(title)
    return bool(expected_tokens) and all(
        _normalize_title(token) in normalized for token in expected_tokens
    )


def _safe_member(info: zipfile.ZipInfo) -> str:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise DryadTiSe2AuditError(
            f"unsafe ZIP member path: {info.filename}"
        )
    if not info.is_dir():
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) == 0o120000:
            raise DryadTiSe2AuditError(
                f"symbolic link ZIP member rejected: {info.filename}"
            )
    return path.as_posix()


def _contains_partition(path: str, configured_prefix: str) -> bool:
    path_parts = tuple(
        part.casefold()
        for part in PurePosixPath(path.replace("\\", "/")).parts
        if part not in ("", ".")
    )
    prefix_parts = tuple(
        part.casefold()
        for part in PurePosixPath(
            configured_prefix.replace("\\", "/")
        ).parts
        if part not in ("", ".")
    )
    width = len(prefix_parts)
    return bool(width) and any(
        path_parts[index : index + width] == prefix_parts
        for index in range(max(0, len(path_parts) - width + 1))
    )


def _classify(path: str, config: dict[str, Any]) -> tuple[str, str]:
    groups = (
        ("experimental", config["required_experimental_prefixes"]),
        ("simulation", config["required_simulation_prefixes"]),
        ("supplementary_or_mixed", config["supplementary_prefixes"]),
    )
    source_class = "unresolved"
    for label, prefixes in groups:
        if any(_contains_partition(path, prefix) for prefix in prefixes):
            source_class = label
            break

    suffix = PurePosixPath(path).suffix.casefold()
    image_suffixes = {
        str(value).casefold() for value in config["allowed_image_suffixes"]
    }
    table_suffixes = {
        str(value).casefold() for value in config["allowed_table_suffixes"]
    }
    if suffix in image_suffixes:
        representation = "raster_image"
    elif suffix in table_suffixes:
        representation = "table_or_text"
    else:
        representation = "other"
    return source_class, representation


def _manifest(root: Path, files: list[Path]) -> dict[str, Any]:
    artifacts = []
    for path in files:
        data = path.read_bytes()
        artifacts.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return {"artifact_count": len(artifacts), "artifacts": artifacts}


def _validate_record(
    config: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    dataset = _fetch_json(str(config["dataset_api_url"]))
    title = dataset.get("title")
    tokens = config.get("expected_title_tokens")
    if (
        not isinstance(title, str)
        or not isinstance(tokens, list)
        or not all(isinstance(token, str) for token in tokens)
        or not _title_matches(title, tokens)
    ):
        raise DryadTiSe2AuditError(
            "Dryad dataset title does not match pinned source identity tokens"
        )
    doi = dataset.get("identifier") or dataset.get("doi")
    expected_doi = str(config["dataset_doi"])
    if not isinstance(doi, str) or expected_doi.casefold() not in doi.casefold():
        raise DryadTiSe2AuditError(
            "Dryad DOI does not match pinned source"
        )

    version = _fetch_json(_link(dataset, "stash:version"))
    rows = _file_rows(_fetch_json(_link(version, "stash:files")))
    by_name = {_file_name(item): item for item in rows}
    if len(by_name) != len(rows):
        raise DryadTiSe2AuditError(
            "duplicate top-level Dryad filenames"
        )
    archive = by_name.get(str(config["expected_archive_name"]))
    readme = by_name.get(str(config["expected_readme_name"]))
    if archive is None or readme is None:
        raise DryadTiSe2AuditError(
            "required Dryad archive or README is missing"
        )
    if _file_id(archive) != int(config["expected_archive_file_id"]):
        raise DryadTiSe2AuditError(
            "Dryad archive file ID does not match pinned source"
        )
    if _file_id(readme) != int(config["expected_readme_file_id"]):
        raise DryadTiSe2AuditError(
            "Dryad README file ID does not match pinned source"
        )
    return title, archive, readme


def _extract_archive_from_bundle(
    bundle_path: Path,
    archive_path: Path,
    config: dict[str, Any],
) -> tuple[int, str, str, int]:
    try:
        bundle = zipfile.ZipFile(bundle_path)
    except zipfile.BadZipFile as exc:
        raise DryadTiSe2AuditError(
            "Dryad dataset download is not a ZIP bundle"
        ) from exc

    with bundle:
        infos = bundle.infolist()
        if len(infos) > int(config["max_bundle_member_count"]):
            raise DryadTiSe2AuditError(
                "Dryad bundle member count exceeds configured limit"
            )
        seen: set[str] = set()
        regular: list[tuple[str, zipfile.ZipInfo]] = []
        for info in infos:
            path = _safe_member(info)
            key = path.casefold()
            if key in seen:
                raise DryadTiSe2AuditError(
                    f"duplicate case-folded Dryad bundle path: {path}"
                )
            seen.add(key)
            if not info.is_dir():
                regular.append((path, info))

        archive_matches = [
            info
            for path, info in regular
            if PurePosixPath(path).name
            == str(config["expected_archive_name"])
        ]
        readme_matches = [
            info
            for path, info in regular
            if PurePosixPath(path).name
            == str(config["expected_readme_name"])
        ]
        if len(archive_matches) != 1 or len(readme_matches) != 1:
            raise DryadTiSe2AuditError(
                "Dryad dataset bundle does not uniquely contain the "
                "pinned archive and README"
            )
        archive_info = archive_matches[0]
        if archive_info.file_size > int(config["max_archive_bytes"]):
            raise DryadTiSe2AuditError(
                "embedded Dryad archive exceeds configured byte limit"
            )
        with bundle.open(archive_info, "r") as source:
            bytes_, md5, sha256 = _stream_copy(
                source,
                archive_path,
                int(config["max_archive_bytes"]),
            )
        if bytes_ != archive_info.file_size:
            raise DryadTiSe2AuditError(
                "embedded Dryad archive byte count mismatch"
            )
        return bytes_, md5, sha256, len(regular)


def _inventory_archive(
    archive_path: Path,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    inventory: list[dict[str, Any]] = []
    total_uncompressed = 0
    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise DryadTiSe2AuditError(
            "pinned Dryad archive is not a valid ZIP"
        ) from exc

    with archive:
        bad = archive.testzip()
        if bad is not None:
            raise DryadTiSe2AuditError(f"ZIP CRC failure: {bad}")
        infos = archive.infolist()
        if len(infos) > int(config["max_member_count"]):
            raise DryadTiSe2AuditError(
                "ZIP member count exceeds configured limit"
            )
        seen: set[str] = set()
        for info in infos:
            path = _safe_member(info)
            key = path.casefold()
            if key in seen:
                raise DryadTiSe2AuditError(
                    f"duplicate case-folded ZIP path: {path}"
                )
            seen.add(key)
            if info.is_dir():
                continue
            total_uncompressed += info.file_size
            if info.file_size > int(config["max_member_bytes"]):
                raise DryadTiSe2AuditError(
                    f"oversized ZIP member: {path}"
                )
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > float(config["max_compression_ratio"]):
                raise DryadTiSe2AuditError(
                    f"excessive compression ratio: {path}"
                )
            source_class, representation = _classify(path, config)
            inventory.append(
                {
                    "path": path,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "suffix": PurePosixPath(path).suffix.casefold(),
                    "source_class": source_class,
                    "representation": representation,
                    "diffraction_name_cue": any(
                        cue in path.casefold()
                        for cue in ("diff", "saed", "diffraction")
                    ),
                    "hrtem_name_cue": "hrtem" in path.casefold(),
                }
            )
    if total_uncompressed > int(config["max_total_uncompressed_bytes"]):
        raise DryadTiSe2AuditError(
            "ZIP expanded-size limit exceeded"
        )
    if not inventory:
        raise DryadTiSe2AuditError("ZIP contains no regular members")
    return inventory, total_uncompressed


def _write_blocked_evidence(
    output_dir: Path,
    config: dict[str, Any],
    title: str,
    archive_item: dict[str, Any],
    readme_item: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "record_verified_but_anonymous_download_blocked",
        "evidence_level": "Diagnostic",
        "record": {
            "doi": config["dataset_doi"],
            "title": title,
            "normalized_title": _normalize_title(title),
            "archive_name": config["expected_archive_name"],
            "archive_file_id": _file_id(archive_item),
            "readme_name": config["expected_readme_name"],
            "readme_file_id": _file_id(readme_item),
        },
        "access_attempts": attempts,
        "evidence_assessment": {
            "record_and_file_identity": "Supported",
            "anonymous_source_download": "Unsupported",
            "archive_integrity": "Inconclusive",
            "experiment_simulation_partition": "Inconclusive",
            "lossless_measurement_provenance": "Inconclusive",
            "pattern_centre_camera_length_and_reciprocal_calibration": (
                "Inconclusive"
            ),
            "acquisition_lineage_and_independence": "Inconclusive",
        },
        "readiness": {
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "processing": {
            "source_bundle_retained": False,
            "source_archive_retained": False,
            "source_members_retained": False,
            "pixel_arrays_exported": False,
            "model_inference_performed": False,
            "parameter_tuning_performed": False,
            "model_retraining_performed": False,
            "phase_indexing_performed": False,
        },
        "unresolved": [
            "authenticated or otherwise repository-supported source download",
            "archive checksum and member inventory",
            "archive-level verification of experimental and simulated folders",
            "detector, exposure, camera length and reciprocal calibration",
            "acquisition identity, sample-region mapping and independence",
        ],
    }

    summary_path = output_dir / "dryad_tise2_saed_audit_summary.json"
    attempts_path = output_dir / "dryad_tise2_saed_access_attempts.csv"
    report_path = output_dir / "dryad_tise2_saed_audit_report.md"
    manifest_path = output_dir / "dryad_tise2_saed_audit_manifest.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with attempts_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["route", "http_status", "reason"],
        )
        writer.writeheader()
        writer.writerows(attempts)
    report_path.write_text(
        "# Dryad TiSe2 SAED/HRTEM source-access audit\n\n"
        f"- Status: `{summary['status']}`\n"
        f"- DOI: `{config['dataset_doi']}`\n"
        f"- Archive file ID: `{_file_id(archive_item)}`\n"
        "- Anonymous source download: **unsupported in the audited runner**\n"
        "- Archive integrity: **inconclusive**\n"
        "- External-validation ready: **no**\n\n"
        "The official record and file identities were verified. The official "
        "dataset-bundle and public individual-file routes rejected the audited "
        "anonymous GitHub runner, so no archive bytes were inspected or retained. "
        "A valid DRYAD_API_TOKEN may be supplied in a controlled environment to "
        "resume the same fail-closed archive audit. No pixels, inference, tuning, "
        "retraining or phase indexing were performed.\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            _manifest(
                output_dir,
                [summary_path, attempts_path, report_path],
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def _write_archive_evidence(
    output_dir: Path,
    config: dict[str, Any],
    title: str,
    archive_item: dict[str, Any],
    readme_item: dict[str, Any],
    route: str,
    bundle_identity: dict[str, Any] | None,
    archive_identity: dict[str, Any],
    inventory: list[dict[str, Any]],
    total_uncompressed: int,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    paths = [str(row["path"]) for row in inventory]
    for prefix in (
        config["required_experimental_prefixes"]
        + config["required_simulation_prefixes"]
    ):
        if not any(_contains_partition(path, prefix) for path in paths):
            raise DryadTiSe2AuditError(
                f"required source partition missing: {prefix}"
            )

    experimental = [
        row for row in inventory if row["source_class"] == "experimental"
    ]
    simulation = [
        row for row in inventory if row["source_class"] == "simulation"
    ]
    if not experimental or not simulation:
        raise DryadTiSe2AuditError(
            "experimental/simulation partition is empty"
        )
    if not any(
        row["representation"] == "raster_image" for row in experimental
    ):
        raise DryadTiSe2AuditError(
            "no experimental raster image found"
        )

    source_counts = Counter(
        str(row["source_class"]) for row in inventory
    )
    representation_counts = Counter(
        str(row["representation"]) for row in inventory
    )
    calibration_cues = [
        path
        for path in paths
        if any(
            cue in path.casefold()
            for cue in (
                "calibration",
                "camera length",
                "camera_length",
                "pattern center",
                "pattern centre",
                "pixel size",
                "pixel_size",
            )
        )
    ]
    summary: dict[str, Any] = {
        "status": (
            "archive_identity_and_experiment_simulation_partition_verified_"
            "but_calibration_and_acquisition_lineage_incomplete"
        ),
        "evidence_level": "Diagnostic",
        "record": {
            "doi": config["dataset_doi"],
            "title": title,
            "normalized_title": _normalize_title(title),
            "archive_file_id": _file_id(archive_item),
            "readme_file_id": _file_id(readme_item),
        },
        "successful_download_route": route,
        "access_attempts_before_success": attempts,
        "dataset_bundle": bundle_identity,
        "archive": archive_identity,
        "member_count": len(inventory),
        "total_uncompressed_bytes": total_uncompressed,
        "source_class_counts": dict(sorted(source_counts.items())),
        "representation_counts": dict(
            sorted(representation_counts.items())
        ),
        "experimental_image_count": sum(
            row["source_class"] == "experimental"
            and row["representation"] == "raster_image"
            for row in inventory
        ),
        "simulation_image_count": sum(
            row["source_class"] == "simulation"
            and row["representation"] == "raster_image"
            for row in inventory
        ),
        "diffraction_name_cue_count": sum(
            bool(row["diffraction_name_cue"]) for row in inventory
        ),
        "hrtem_name_cue_count": sum(
            bool(row["hrtem_name_cue"]) for row in inventory
        ),
        "calibration_or_centre_name_cues": calibration_cues,
        "evidence_assessment": {
            "record_and_archive_identity": "Supported",
            "archive_integrity": "Supported",
            "experiment_simulation_partition": "Supported",
            "lossless_measurement_provenance": "Inconclusive",
            "pattern_centre_camera_length_and_reciprocal_calibration": (
                "Inconclusive"
            ),
            "acquisition_lineage_and_independence": "Inconclusive",
        },
        "readiness": {
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "processing": {
            "source_bundle_retained": False,
            "source_archive_retained": False,
            "source_members_retained": False,
            "pixel_arrays_exported": False,
            "model_inference_performed": False,
            "parameter_tuning_performed": False,
            "model_retraining_performed": False,
            "phase_indexing_performed": False,
        },
        "unresolved": [
            "authoritative mapping of every raster to acquisition ID and sample region",
            "detector, exposure, camera length and reciprocal-space calibration provenance",
            "whether TIFF/BMP files are detector exports or publication derivatives",
            "complete preprocessing history for spreadsheets and line profiles",
            "independence from analyzer development and parameter selection",
        ],
    }

    summary_path = output_dir / "dryad_tise2_saed_audit_summary.json"
    inventory_path = output_dir / "dryad_tise2_saed_member_inventory.csv"
    report_path = output_dir / "dryad_tise2_saed_audit_report.md"
    manifest_path = output_dir / "dryad_tise2_saed_audit_manifest.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inventory[0]))
        writer.writeheader()
        writer.writerows(inventory)
    report_path.write_text(
        "# Dryad TiSe2 SAED/HRTEM source audit\n\n"
        f"- Status: `{summary['status']}`\n"
        f"- DOI: `{config['dataset_doi']}`\n"
        f"- Archive file ID: `{_file_id(archive_item)}`\n"
        f"- Archive SHA-256: `{archive_identity['sha256']}`\n"
        f"- Regular members: {len(inventory)}\n"
        f"- Experimental raster images: "
        f"{summary['experimental_image_count']}\n"
        f"- Simulation raster images: "
        f"{summary['simulation_image_count']}\n"
        "- External-validation ready: **no**\n\n"
        "Archive identity, integrity and experimental/simulation separation are "
        "supported. Detector provenance, acquisition identifiers, pattern centre, "
        "camera length and reciprocal calibration remain unresolved. No source "
        "bundle, source archive, pixels, inference, tuning, retraining or phase "
        "indexing were retained or performed.\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            _manifest(
                output_dir,
                [summary_path, inventory_path, report_path],
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = _read_json(config_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DryadTiSe2AuditError(
            "output directory must be absent or empty"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    title, archive_item, readme_item = _validate_record(config)
    attempts: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="dryad-tise2-") as temporary:
        temporary_root = Path(temporary)
        bundle_path = temporary_root / "dryad_dataset_bundle.zip"
        archive_path = temporary_root / str(config["expected_archive_name"])
        bundle_identity: dict[str, Any] | None = None
        successful_route: str | None = None

        try:
            bundle_bytes, bundle_md5, bundle_sha256 = _download(
                str(config["dataset_bundle_download_url"]),
                bundle_path,
                int(config["max_bundle_bytes"]),
                route="official_dataset_bundle",
            )
            (
                archive_bytes,
                archive_md5,
                archive_sha256,
                bundle_member_count,
            ) = _extract_archive_from_bundle(
                bundle_path,
                archive_path,
                config,
            )
            bundle_identity = {
                "bytes": bundle_bytes,
                "md5": bundle_md5,
                "sha256": bundle_sha256,
                "regular_member_count": bundle_member_count,
            }
            successful_route = "official_dataset_bundle"
        except DryadAccessError as exc:
            attempts.append(exc.as_dict())
            public_url = (
                "https://datadryad.org/downloads/file_stream/"
                f"{_file_id(archive_item)}"
            )
            try:
                archive_bytes, archive_md5, archive_sha256 = _download(
                    public_url,
                    archive_path,
                    int(config["max_archive_bytes"]),
                    route="public_individual_file",
                )
                successful_route = "public_individual_file"
            except DryadAccessError as fallback_exc:
                attempts.append(fallback_exc.as_dict())
                return _write_blocked_evidence(
                    output_dir=output_dir,
                    config=config,
                    title=title,
                    archive_item=archive_item,
                    readme_item=readme_item,
                    attempts=attempts,
                )

        if successful_route is None:
            raise DryadTiSe2AuditError(
                "no Dryad source-download route completed"
            )
        inventory, total_uncompressed = _inventory_archive(
            archive_path,
            config,
        )
        archive_identity = {
            "name": config["expected_archive_name"],
            "file_id": _file_id(archive_item),
            "bytes": archive_bytes,
            "md5": archive_md5,
            "sha256": archive_sha256,
            "integrity_test_passed": True,
        }

    return _write_archive_evidence(
        output_dir=output_dir,
        config=config,
        title=title,
        archive_item=archive_item,
        readme_item=readme_item,
        route=successful_route,
        bundle_identity=bundle_identity,
        archive_identity=archive_identity,
        inventory=inventory,
        total_uncompressed=total_uncompressed,
        attempts=attempts,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the Dryad TiSe2 SAED/HRTEM archive without retaining "
            "source data."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.config, args.output),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
