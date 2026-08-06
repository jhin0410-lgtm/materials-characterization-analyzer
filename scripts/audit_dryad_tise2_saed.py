from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any


class DryadTiSe2AuditError(RuntimeError):
    """Raised when the pinned source contract is not satisfied."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DryadTiSe2AuditError(f"expected JSON object: {path}")
    return value


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "materials-characterization-analyzer/0.11"}
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except Exception as exc:
        raise DryadTiSe2AuditError(f"failed to fetch Dryad JSON: {url}") from exc
    if not isinstance(payload, dict):
        raise DryadTiSe2AuditError(f"Dryad endpoint returned no object: {url}")
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
        raise DryadTiSe2AuditError("Dryad file-list response has no valid file array")
    return candidates


def _file_name(item: dict[str, Any]) -> str:
    for key in ("path", "name", "filename"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return PurePosixPath(value).name
    raise DryadTiSe2AuditError("Dryad file entry has no filename")


def _file_id(item: dict[str, Any]) -> int:
    try:
        file_id = int(item.get("id"))
    except (TypeError, ValueError) as exc:
        raise DryadTiSe2AuditError(
            f"Dryad file has no numeric ID: {_file_name(item)}"
        ) from exc
    if file_id <= 0:
        raise DryadTiSe2AuditError(f"Dryad file has invalid ID: {_file_name(item)}")
    return file_id


def _download_url(item: dict[str, Any]) -> str:
    """Use the public file URL emitted by the Dryad landing page."""

    return f"https://datadryad.org/downloads/file_stream/{_file_id(item)}"


def _download(url: str, target: Path, max_bytes: int) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "materials-characterization-analyzer/0.11"}
    )
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=180) as response, target.open(
            "wb"
        ) as handle:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise DryadTiSe2AuditError(
                        "Dryad archive exceeds configured byte limit"
                    )
                md5.update(chunk)
                sha256.update(chunk)
                handle.write(chunk)
    except DryadTiSe2AuditError:
        raise
    except Exception as exc:
        raise DryadTiSe2AuditError("failed to download Dryad archive") from exc
    return total, md5.hexdigest(), sha256.hexdigest()


def _normalize_title(value: str) -> str:
    unescaped = html.unescape(value)
    no_markup = re.sub(r"<[^>]+>", " ", unescaped)
    normalized = unicodedata.normalize("NFKD", no_markup).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _title_matches(title: str, expected_tokens: list[str]) -> bool:
    normalized = _normalize_title(title)
    return bool(expected_tokens) and all(
        _normalize_title(token) in normalized for token in expected_tokens
    )


def _safe_member(info: zipfile.ZipInfo) -> str:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise DryadTiSe2AuditError(f"unsafe ZIP member path: {info.filename}")
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
        for part in PurePosixPath(configured_prefix.replace("\\", "/")).parts
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
    if suffix in {str(value).casefold() for value in config["allowed_image_suffixes"]}:
        representation = "raster_image"
    elif suffix in {
        str(value).casefold() for value in config["allowed_table_suffixes"]
    }:
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


def _validate_record(config: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
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
    if not isinstance(doi, str) or str(config["dataset_doi"]).casefold() not in doi.casefold():
        raise DryadTiSe2AuditError("Dryad DOI does not match pinned source")

    version = _fetch_json(_link(dataset, "stash:version"))
    rows = _file_rows(_fetch_json(_link(version, "stash:files")))
    by_name = {_file_name(item): item for item in rows}
    if len(by_name) != len(rows):
        raise DryadTiSe2AuditError("duplicate top-level Dryad filenames")
    archive = by_name.get(str(config["expected_archive_name"]))
    readme = by_name.get(str(config["expected_readme_name"]))
    if archive is None or readme is None:
        raise DryadTiSe2AuditError("required Dryad archive or README is missing")
    if _file_id(archive) != int(config["expected_archive_file_id"]):
        raise DryadTiSe2AuditError("Dryad archive file ID does not match pinned source")
    if _file_id(readme) != int(config["expected_readme_file_id"]):
        raise DryadTiSe2AuditError("Dryad README file ID does not match pinned source")
    return title, archive, readme


def _inventory_archive(
    archive_path: Path, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    inventory: list[dict[str, Any]] = []
    total_uncompressed = 0
    with zipfile.ZipFile(archive_path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise DryadTiSe2AuditError(f"ZIP CRC failure: {bad}")
        infos = archive.infolist()
        if len(infos) > int(config["max_member_count"]):
            raise DryadTiSe2AuditError("ZIP member count exceeds configured limit")
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
                raise DryadTiSe2AuditError(f"oversized ZIP member: {path}")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > float(config["max_compression_ratio"]):
                raise DryadTiSe2AuditError(f"excessive compression ratio: {path}")
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
        raise DryadTiSe2AuditError("ZIP expanded-size limit exceeded")
    if not inventory:
        raise DryadTiSe2AuditError("ZIP contains no regular members")
    return inventory, total_uncompressed


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = _read_json(config_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DryadTiSe2AuditError("output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    title, archive_item, readme_item = _validate_record(config)
    with tempfile.TemporaryDirectory(prefix="dryad-tise2-") as temporary:
        archive_path = Path(temporary) / str(config["expected_archive_name"])
        byte_count, md5, sha256 = _download(
            _download_url(archive_item),
            archive_path,
            int(config["max_archive_bytes"]),
        )
        inventory, total_uncompressed = _inventory_archive(archive_path, config)

    paths = [str(row["path"]) for row in inventory]
    for prefix in (
        config["required_experimental_prefixes"]
        + config["required_simulation_prefixes"]
    ):
        if not any(_contains_partition(path, prefix) for path in paths):
            raise DryadTiSe2AuditError(f"required source partition missing: {prefix}")

    experimental = [row for row in inventory if row["source_class"] == "experimental"]
    simulation = [row for row in inventory if row["source_class"] == "simulation"]
    if not experimental or not simulation:
        raise DryadTiSe2AuditError("experimental/simulation partition is empty")
    if not any(row["representation"] == "raster_image" for row in experimental):
        raise DryadTiSe2AuditError("no experimental raster image found")

    source_counts = Counter(str(row["source_class"]) for row in inventory)
    representation_counts = Counter(str(row["representation"]) for row in inventory)
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
        "archive": {
            "name": config["expected_archive_name"],
            "file_id": _file_id(archive_item),
            "bytes": byte_count,
            "md5": md5,
            "sha256": sha256,
            "integrity_test_passed": True,
        },
        "member_count": len(inventory),
        "total_uncompressed_bytes": total_uncompressed,
        "source_class_counts": dict(sorted(source_counts.items())),
        "representation_counts": dict(sorted(representation_counts.items())),
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
            "pattern_centre_camera_length_and_reciprocal_calibration": "Inconclusive",
            "acquisition_lineage_and_independence": "Inconclusive",
        },
        "readiness": {
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "processing": {
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
            "whether TIFF/BMP files are direct lossless detector exports or publication derivatives",
            "complete preprocessing history for processed spreadsheets and line profiles",
            "independence from analyzer development and parameter selection",
        ],
    }

    summary_path = output_dir / "dryad_tise2_saed_audit_summary.json"
    inventory_path = output_dir / "dryad_tise2_saed_member_inventory.csv"
    report_path = output_dir / "dryad_tise2_saed_audit_report.md"
    manifest_path = output_dir / "dryad_tise2_saed_audit_manifest.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
        f"- Archive SHA-256: `{sha256}`\n"
        f"- Regular members: {len(inventory)}\n"
        f"- Experimental raster images: {summary['experimental_image_count']}\n"
        f"- Simulation raster images: {summary['simulation_image_count']}\n"
        "- External-validation ready: **no**\n\n"
        "Archive identity, integrity and experimental/simulation separation are "
        "supported. Detector provenance, acquisition identifiers, pattern centre, "
        "camera length and reciprocal calibration remain unresolved. No pixels, "
        "inference, tuning, retraining or phase indexing were retained or performed.\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            _manifest(output_dir, [summary_path, inventory_path, report_path]),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the Dryad TiSe2 SAED/HRTEM archive without retaining source data."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
