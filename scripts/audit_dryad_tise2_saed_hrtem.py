#!/usr/bin/env python3
"""Fail-closed metadata-only audit of the Dryad TiSe2 TEM/SAED archive."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from PIL import Image

USER_AGENT = "materials-characterization-analyzer-dryad-tise2-audit/1.0"
DRYAD_HOST = "datadryad.org"
ALLOWED_TEXT_BYTES = 2_000_000
TIFF_SAMPLE_LIMIT = 20
TIFF_SAMPLE_TOTAL_BYTES = 256_000_000

class AuditError(RuntimeError):
    """Raised when source identity, archive safety, or the frozen contract fails."""

def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {"case_id", "audit_date", "source", "limits", "scientific_boundary"}
    if set(payload) != expected:
        raise AuditError("unexpected top-level config keys")
    source = payload["source"]
    required_source = {
        "repository", "doi", "record_url", "primary_file_id", "primary_filename",
        "readme_file_id", "readme_filename", "expected_license", "expected_title",
        "source_quality_flags",
    }
    if set(source) != required_source:
        raise AuditError("unexpected source config keys")
    limits = payload["limits"]
    expected_limits = {
        "minimum_archive_bytes", "maximum_archive_bytes", "maximum_member_count",
        "maximum_total_uncompressed_bytes", "maximum_single_member_bytes",
        "maximum_compression_ratio", "maximum_text_member_bytes",
        "maximum_tiff_samples", "maximum_tiff_sample_bytes",
    }
    if set(limits) != expected_limits:
        raise AuditError("unexpected limit keys")
    if any(not isinstance(v, int) or v <= 0 for v in limits.values()):
        raise AuditError("limits must be positive integers")
    boundary = payload["scientific_boundary"]
    required_true = {
        "source_archive_download_authorized", "archive_member_inventory_authorized",
        "bounded_text_read_authorized", "bounded_tiff_header_inspection_authorized",
    }
    required_false = {
        "source_archive_retention_authorized", "source_files_may_be_uploaded_as_artifacts",
        "archive_members_may_be_uploaded_as_artifacts", "pixel_array_export_authorized",
        "image_preprocessing_authorized", "model_inference_authorized",
        "annotation_authorized", "parameter_tuning_authorized",
        "model_retraining_authorized", "phase_indexing_claim_authorized",
        "external_validation_claim_authorized", "engineering_decision_claim_authorized",
    }
    if any(boundary.get(k) is not True for k in required_true):
        raise AuditError("required bounded audit operations are not authorized")
    if any(boundary.get(k) is not False for k in required_false):
        raise AuditError("scientific boundary must remain fail-closed")
    return payload

def fetch_json(url: str) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != DRYAD_HOST:
        raise AuditError(f"untrusted Dryad API URL: {url}")
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise AuditError("Dryad API response must be an object")
    return payload

def _link(payload: Mapping[str, Any], base_url: str, *names: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        return None
    for name in names:
        value = links.get(name)
        href = value.get("href") if isinstance(value, Mapping) else value
        if isinstance(href, str) and href.strip():
            url = urllib.parse.urljoin(base_url, href.strip())
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname != DRYAD_HOST:
                raise AuditError(f"Dryad link escaped pinned host: {url}")
            return url
    return None

def normalize_doi(value: str) -> str:
    text = urllib.parse.unquote(value.strip())
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.lower()

def _doi_from_dataset_url(url: str) -> str:
    token = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])
    return normalize_doi(token)

def _record_name(record: Mapping[str, Any]) -> str | None:
    for key in ("path", "filename", "fileName", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None

def _record_id(record: Mapping[str, Any]) -> int | None:
    for key in ("id", "fileId", "file_id"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None

def _record_size(record: Mapping[str, Any]) -> int | None:
    for key in ("size", "filesize", "fileSize"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None

def _record_digest(record: Mapping[str, Any]) -> dict[str, str]:
    candidates: list[tuple[str, Any]] = []
    for key in ("digest", "checksum", "md5", "sha256"):
        if record.get(key) is not None:
            candidates.append((key, record.get(key)))
    result: dict[str, str] = {}
    for key, value in candidates:
        if isinstance(value, Mapping):
            for alg, digest in value.items():
                if isinstance(digest, str):
                    result[str(alg).lower()] = digest.lower().removeprefix(f"{str(alg).lower()}:")
        elif isinstance(value, str):
            text = value.strip().lower()
            if ":" in text:
                alg, digest = text.split(":", 1)
                result[alg] = digest
            elif key in {"md5", "sha256"}:
                result[key] = text
    return result

def _records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = payload.get("files")
    if isinstance(direct, list):
        return [x for x in direct if isinstance(x, Mapping)]
    embedded = payload.get("_embedded")
    if isinstance(embedded, Mapping):
        for key, value in embedded.items():
            if isinstance(value, list) and "file" in str(key).lower():
                return [x for x in value if isinstance(x, Mapping)]
    for key in ("data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, Mapping)]
    raise AuditError("Dryad file-list response has no file records")

def collect_files(start_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pages: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    url: str | None = start_url
    while url:
        if url in seen:
            raise AuditError("Dryad pagination cycle detected")
        seen.add(url)
        payload = fetch_json(url)
        pages.append(payload)
        records.extend(dict(x) for x in _records(payload))
        url = _link(payload, url, "next", "stash:next")
    return pages, records

def resolve_source(config: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source"]
    file_id = int(source["primary_file_id"])
    file_url = f"https://{DRYAD_HOST}/api/v2/files/{file_id}"
    file_payload = fetch_json(file_url)
    if _record_id(file_payload) not in {None, file_id}:
        raise AuditError("primary file ID mismatch")
    if _record_name(file_payload) != source["primary_filename"]:
        raise AuditError(f"primary filename mismatch: {_record_name(file_payload)!r}")
    version_url = _link(file_payload, file_url, "stash:version", "version")
    dataset_url = _link(file_payload, file_url, "stash:dataset", "dataset")
    if not version_url or not dataset_url:
        raise AuditError("Dryad file record lacks version or dataset linkage")
    if _doi_from_dataset_url(dataset_url) != normalize_doi(source["doi"]):
        raise AuditError("linked Dryad dataset DOI mismatch")
    version_payload = fetch_json(version_url)
    dataset_payload = fetch_json(dataset_url)
    explicit_doi = dataset_payload.get("doi") or dataset_payload.get("identifier")
    if isinstance(explicit_doi, str) and normalize_doi(explicit_doi) != normalize_doi(source["doi"]):
        raise AuditError("Dryad dataset payload DOI mismatch")
    observed_title = dataset_payload.get("title") or dataset_payload.get("name")
    if isinstance(observed_title, str) and source["expected_title"].casefold() not in observed_title.casefold():
        raise AuditError(f"dataset title mismatch: {observed_title!r}")
    license_value = dataset_payload.get("license")
    if isinstance(license_value, Mapping):
        license_text = str(license_value.get("id") or license_value.get("name") or license_value)
    else:
        license_text = str(license_value or "")
    if source["expected_license"].casefold() not in license_text.casefold():
        if not (source["expected_license"] == "CC0-1.0" and "cc0" in license_text.casefold()):
            raise AuditError(f"dataset licence mismatch: {license_text!r}")
    files_url = _link(version_payload, version_url, "stash:files", "files") or version_url.rstrip("/") + "/files"
    pages, records = collect_files(files_url)
    by_id = {_record_id(r): r for r in records}
    primary = by_id.get(file_id)
    readme = by_id.get(int(source["readme_file_id"]))
    if primary is None or readme is None:
        raise AuditError("expected Dryad file IDs are absent from version inventory")
    if _record_name(primary) != source["primary_filename"]:
        raise AuditError("version inventory primary filename mismatch")
    if _record_name(readme) != source["readme_filename"]:
        raise AuditError("version inventory README filename mismatch")
    size = _record_size(primary)
    if size is None:
        size = _record_size(file_payload)
    if size is None:
        raise AuditError("primary archive size is unavailable")
    limits = config["limits"]
    if not limits["minimum_archive_bytes"] <= size <= limits["maximum_archive_bytes"]:
        raise AuditError(f"archive size outside frozen bounds: {size}")
    download_url = _link(primary, files_url, "stash:download", "download")
    if download_url is None:
        download_url = f"https://{DRYAD_HOST}/downloads/file_stream/{file_id}"
    return {
        "file_api_url": file_url,
        "version_url": version_url,
        "dataset_url": dataset_url,
        "file_payload": file_payload,
        "version_payload": version_payload,
        "dataset_payload": dataset_payload,
        "file_pages": pages,
        "file_records": records,
        "primary_record": dict(primary),
        "readme_record": dict(readme),
        "expected_bytes": size,
        "upstream_digests": _record_digest(primary) or _record_digest(file_payload),
        "download_url": download_url,
        "license_observed": license_text,
        "title_observed": observed_title,
    }

def stream_download(url: str, destination: Path, expected_bytes: int) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != DRYAD_HOST:
        raise AuditError("download URL escaped pinned Dryad host")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    count = 0
    with urllib.request.urlopen(request, timeout=1800) as response, destination.open("wb") as out:
        while chunk := response.read(8 * 1024 * 1024):
            count += len(chunk)
            if count > expected_bytes:
                raise AuditError("download exceeded Dryad-declared size")
            out.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    if count != expected_bytes:
        raise AuditError(f"download byte mismatch: {count} != {expected_bytes}")
    return {"bytes": count, "md5": md5.hexdigest(), "sha256": sha256.hexdigest()}

def verify_upstream_digest(observed: Mapping[str, Any], upstream: Mapping[str, str]) -> dict[str, Any]:
    checked: list[str] = []
    for alg in ("md5", "sha256"):
        expected = upstream.get(alg)
        if expected:
            if observed[alg].lower() != expected.lower():
                raise AuditError(f"{alg} mismatch against Dryad metadata")
            checked.append(alg)
    return {"available": bool(upstream), "checked_algorithms": checked, "values": dict(upstream)}

def safe_member_path(name: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name:
        raise AuditError(f"unsafe ZIP member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AuditError(f"unsafe ZIP path: {name!r}")
    if ":" in path.parts[0]:
        raise AuditError(f"drive-like ZIP path: {name!r}")
    return path

def member_kind(path: PurePosixPath) -> str:
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        return "tiff_raster"
    if suffix in {".bmp", ".png"}:
        return "other_raster"
    if suffix in {".xlsx", ".xls", ".csv"}:
        return "processed_table"
    if suffix in {".txt", ".md", ".json", ".yaml", ".yml"}:
        return "metadata_or_readme"
    if suffix in {".dm3", ".dm4", ".emd", ".ser", ".emi", ".mrc", ".mrcs"}:
        return "native_microscopy_container"
    return "other"

def folder_from_path(path: PurePosixPath) -> str:
    return path.parts[0] if path.parts else ""

def fixed_folder_role(folder: str) -> tuple[str, str] | None:
    f = folder.casefold()
    if f == "fig2_data":
        return "experimental", "dataset README explicitly identifies Fig2_Data as experimental diffraction"
    if f in {"fig3_data", "fig4_data"}:
        return "simulated", "dataset README explicitly identifies this figure folder as simulated diffraction"
    return None

def classify_text(text: str) -> tuple[str, list[str]]:
    lower = text.casefold()
    experimental_terms = [
        "experimental", "measured", "measurement", "diffraction pattern", "saed",
        "hrtem", "tem image", "electron diffraction", "zone axis", "raw data",
    ]
    simulated_terms = ["simulated", "simulation", "calculated", "dft", "density functional"]
    exp_hits = sorted({term for term in experimental_terms if term in lower})
    sim_hits = sorted({term for term in simulated_terms if term in lower})
    if exp_hits and sim_hits:
        role = "mixed"
    elif exp_hits:
        role = "experimental"
    elif sim_hits:
        role = "simulated_or_computational"
    else:
        role = "unresolved"
    return role, exp_hits + sim_hits

def audit_zip(archive: Path, config: Mapping[str, Any], work_root: Path) -> dict[str, Any]:
    limits = config["limits"]
    rows: list[dict[str, Any]] = []
    folder_texts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tiff_candidates: list[zipfile.ZipInfo] = []
    total = 0
    normalized: set[str] = set()
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise AuditError(f"ZIP CRC test failed at {bad}")
        infos = zf.infolist()
        if len(infos) > limits["maximum_member_count"]:
            raise AuditError("ZIP member count exceeds frozen bound")
        for info in infos:
            if info.is_dir():
                continue
            path = safe_member_path(info.filename)
            key = path.as_posix().casefold()
            if key in normalized:
                raise AuditError(f"duplicate normalized ZIP path: {path}")
            normalized.add(key)
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and (stat.S_ISLNK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode)):
                raise AuditError(f"unsafe special ZIP member: {path}")
            if info.flag_bits & 0x1:
                raise AuditError(f"encrypted ZIP member: {path}")
            if info.file_size > limits["maximum_single_member_bytes"]:
                raise AuditError(f"member exceeds size bound: {path}")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits["maximum_compression_ratio"]:
                raise AuditError(f"member compression ratio exceeds bound: {path}")
            total += info.file_size
            if total > limits["maximum_total_uncompressed_bytes"]:
                raise AuditError("expanded ZIP exceeds total size bound")
            kind = member_kind(path)
            folder = folder_from_path(path)
            rows.append({
                "path": path.as_posix(),
                "folder": folder,
                "suffix": path.suffix.lower(),
                "kind": kind,
                "compressed_bytes": info.compress_size,
                "uncompressed_bytes": info.file_size,
                "crc32": f"{info.CRC:08x}",
            })
            if kind == "metadata_or_readme" and info.file_size <= limits["maximum_text_member_bytes"]:
                raw = zf.read(info)
                if len(raw) > ALLOWED_TEXT_BYTES:
                    raise AuditError("text member exceeded hard text-read guard")
                text = raw.decode("utf-8", errors="replace")
                role, hits = classify_text(text)
                folder_texts[folder].append({
                    "path": path.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw), "role_from_text": role, "matched_terms": hits,
                    "text_excerpt": " ".join(text.split())[:1200],
                })
            if kind == "tiff_raster":
                tiff_candidates.append(info)
        if not rows:
            raise AuditError("ZIP contains no regular files")

        folder_roles: list[dict[str, Any]] = []
        folders = sorted({row["folder"] for row in rows})
        for folder in folders:
            fixed = fixed_folder_role(folder)
            texts = folder_texts.get(folder, [])
            if fixed:
                role, reason = fixed
            else:
                observed_roles = {x["role_from_text"] for x in texts}
                observed_roles.discard("unresolved")
                if observed_roles == {"experimental"}:
                    role, reason = "experimental", "folder ReadMe text contains experimental-only cues"
                elif observed_roles <= {"simulated_or_computational"} and observed_roles:
                    role, reason = "simulated_or_computational", "folder ReadMe text contains simulation/computation-only cues"
                elif observed_roles:
                    role, reason = "mixed_or_ambiguous", "folder ReadMe text contains both experimental and simulation/computation cues"
                else:
                    role, reason = "unresolved", "no authoritative role statement found in bounded folder text"
            folder_roles.append({
                "folder": folder,
                "role": role,
                "reason": reason,
                "member_count": sum(1 for row in rows if row["folder"] == folder),
                "text_evidence": texts,
            })

        role_by_folder = {x["folder"]: x["role"] for x in folder_roles}
        experimental_tiffs = [
            info for info in tiff_candidates
            if role_by_folder.get(folder_from_path(PurePosixPath(info.filename))) == "experimental"
        ]
        selected: list[zipfile.ZipInfo] = []
        selected_bytes = 0
        for info in sorted(experimental_tiffs, key=lambda x: (x.file_size, x.filename.casefold())):
            if len(selected) >= min(TIFF_SAMPLE_LIMIT, limits["maximum_tiff_samples"]):
                break
            if selected_bytes + info.file_size > min(TIFF_SAMPLE_TOTAL_BYTES, limits["maximum_tiff_sample_bytes"]):
                continue
            selected.append(info)
            selected_bytes += info.file_size

        tiff_meta: list[dict[str, Any]] = []
        extract_root = work_root / "tiff_headers"
        extract_root.mkdir(parents=True)
        for info in selected:
            path = safe_member_path(info.filename)
            target = extract_root.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                while chunk := src.read(4 * 1024 * 1024):
                    dst.write(chunk)
            try:
                with Image.open(target) as image:
                    tags = {}
                    for key, value in getattr(image, "tag_v2", {}).items():
                        if key in {256, 257, 258, 259, 262, 270, 282, 283, 296, 305, 306, 315, 33432, 65000, 65001}:
                            tags[str(key)] = str(value)[:500]
                    info_row = {
                        "path": path.as_posix(),
                        "format": image.format,
                        "mode": image.mode,
                        "size": list(image.size),
                        "n_frames": getattr(image, "n_frames", 1),
                        "selected_tags": tags,
                        "calibration_keyword_hits": sorted({
                            term for term in ("camera length", "accelerating voltage", "voltage", "pixel size",
                                              "reciprocal", "calibration", "zone axis", "detector", "magnification")
                            if term in " ".join(tags.values()).casefold()
                        }),
                    }
            except Exception as exc:
                info_row = {"path": path.as_posix(), "error": type(exc).__name__}
            tiff_meta.append(info_row)

    return {
        "members": rows,
        "member_count": len(rows),
        "total_uncompressed_bytes": total,
        "representation_counts": {
            key: Counter(row["kind"] for row in rows).get(key, 0)
            for key in (
                "tiff_raster", "other_raster", "processed_table",
                "metadata_or_readme", "native_microscopy_container", "other"
            )
        },
        "folder_roles": folder_roles,
        "folder_role_counts": dict(Counter(x["role"] for x in folder_roles)),
        "tiff_header_sample": tiff_meta,
        "experimental_tiff_candidate_count": len(experimental_tiffs),
        "selected_tiff_header_count": len(tiff_meta),
    }

def artifact_manifest(output_dir: Path, paths: Iterable[Path]) -> dict[str, Any]:
    rows = []
    for path in paths:
        rel = path.relative_to(output_dir).as_posix()
        data = path.read_bytes()
        rows.append({"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    rows.sort(key=lambda x: x["path"])
    return {"artifact_count": len(rows), "artifacts": rows}

def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise AuditError("output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    source = resolve_source(config)
    with tempfile.TemporaryDirectory(prefix="dryad_tise2_") as tmp:
        work = Path(tmp)
        archive = work / config["source"]["primary_filename"]
        observed = stream_download(source["download_url"], archive, source["expected_bytes"])
        digest_status = verify_upstream_digest(observed, source["upstream_digests"])
        zip_result = audit_zip(archive, config, work)

    exp_folders = [x["folder"] for x in zip_result["folder_roles"] if x["role"] == "experimental"]
    simulated_folders = [x["folder"] for x in zip_result["folder_roles"] if x["role"] in {"simulated", "simulated_or_computational"}]
    mixed_folders = [x["folder"] for x in zip_result["folder_roles"] if x["role"] in {"mixed_or_ambiguous", "unresolved"}]
    calibration_hits = sorted({
        hit
        for item in zip_result["tiff_header_sample"]
        for hit in item.get("calibration_keyword_hits", [])
    })
    supported = {
        "dryad_dataset_identity": "Supported",
        "file_version_binding": "Supported",
        "archive_integrity": "Supported",
        "experimental_simulation_separation": (
            "Supported_for_explicit_Fig2_Fig3_Fig4_folders_and_Diagnostic_for_supplementary_folders"
        ),
        "reuse_authorization": "Supported",
        "native_detector_container_representation": (
            "Unsupported" if zip_result["representation_counts"].get("native_microscopy_container", 0) == 0 else "Supported"
        ),
        "reciprocal_calibration_and_pattern_centre": (
            "Diagnostic_only" if calibration_hits else "Inconclusive"
        ),
    }
    summary = {
        "status": "checksum_bound_archive_inventory_completed_with_experimental_simulation_separation_but_calibration_lineage_incomplete",
        "evidence_level": "Diagnostic",
        "source": {
            "repository": config["source"]["repository"],
            "doi": config["source"]["doi"],
            "record_url": config["source"]["record_url"],
            "title": source["title_observed"],
            "license": source["license_observed"],
            "version_url": source["version_url"],
            "dataset_url": source["dataset_url"],
            "primary_file_id": config["source"]["primary_file_id"],
            "primary_filename": config["source"]["primary_filename"],
            "upstream_digest_status": digest_status,
        },
        "archive": observed,
        "member_count": zip_result["member_count"],
        "total_uncompressed_bytes": zip_result["total_uncompressed_bytes"],
        "representation_counts": zip_result["representation_counts"],
        "folder_role_counts": zip_result["folder_role_counts"],
        "experimental_folders": exp_folders,
        "simulated_or_computational_folders": simulated_folders,
        "mixed_or_unresolved_folders": mixed_folders,
        "experimental_tiff_candidate_count": zip_result["experimental_tiff_candidate_count"],
        "selected_tiff_header_count": zip_result["selected_tiff_header_count"],
        "tiff_calibration_keyword_hits": calibration_hits,
        "evidence_assessment": supported,
        "readiness": {
            "cross_material_software_diagnostic_ready": True,
            "calibrated_saed_validation_ready": False,
            "external_scientific_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "processing": {
            "source_archive_retained": False,
            "source_members_retained": False,
            "pixel_arrays_exported": False,
            "image_preprocessing_performed": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "parameter_tuning_performed": False,
            "model_retraining_performed": False,
            "phase_indexing_performed": False,
        },
        "source_quality_flags": config["source"]["source_quality_flags"],
        "unresolved": [
            "authoritative sample and acquisition identifiers for every diffraction pattern",
            "camera length and reciprocal-space calibration provenance",
            "pattern centre and detector geometry",
            "exposure, binning, gain, dark-current and saturation state",
            "whether all TIFF/BMP files are detector-native or exported/processed rasters",
            "development-set non-use and independence from current analyzer design",
            "supplementary-folder experimental/simulated role where folder ReadMe is mixed or insufficient",
        ],
    }

    summary_path = output_dir / "dryad_tise2_saed_hrtem_audit_summary.json"
    inventory_path = output_dir / "dryad_tise2_member_inventory.csv"
    folders_path = output_dir / "dryad_tise2_folder_evidence.json"
    tiff_path = output_dir / "dryad_tise2_tiff_header_sample.json"
    report_path = output_dir / "dryad_tise2_saed_hrtem_audit_report.md"
    manifest_path = output_dir / "dryad_tise2_saed_hrtem_audit_manifest.json"
    write_json(summary_path, summary)
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "path", "folder", "suffix", "kind", "compressed_bytes", "uncompressed_bytes", "crc32"
        ])
        writer.writeheader()
        writer.writerows(zip_result["members"])
    write_json(folders_path, zip_result["folder_roles"])
    write_json(tiff_path, zip_result["tiff_header_sample"])
    report_path.write_text(
        f"""# Dryad TiSe2 SAED/HRTEM source audit

## Result

- Status: `{summary['status']}`
- Evidence level: **Diagnostic**
- DOI: `{summary['source']['doi']}`
- Licence: `{summary['source']['license']}`
- Archive bytes: `{observed['bytes']}`
- Archive SHA-256: `{observed['sha256']}`
- Regular members: `{zip_result['member_count']}`
- Experimental folders: {', '.join(exp_folders) or 'none'}
- Simulated/computational folders: {', '.join(simulated_folders) or 'none'}
- Mixed or unresolved supplementary folders: {', '.join(mixed_folders) or 'none'}
- Native microscopy containers: `{zip_result['representation_counts'].get('native_microscopy_container', 0)}`
- TIFF header samples: `{zip_result['selected_tiff_header_count']}`
- Calibrated-SAED validation ready: **no**

## Supported

The Dryad DOI, primary file/version binding, archive byte count, observed hashes,
ZIP CRC integrity, safe member inventory, and the explicit separation of experimental
`Fig2_Data` from simulated `Fig3_Data` and `Fig4_Data` are supported for the audited
source version. Dryad reuse authorization is supported.

## Limitations

This dataset is TiSe2, not cobalt oxide. TIFF/BMP labels such as “raw” or “original”
do not prove detector-native intensity preservation. Camera length, pattern centre,
detector geometry, acquisition IDs and reciprocal calibration remain unresolved.
Supplementary folders are classified only from their bounded ReadMe evidence and are
not promoted when the text is mixed or insufficient.

No source archive, microscopy member or pixel array is retained. No image
preprocessing, analyzer inference, parameter tuning, retraining, d-spacing validation,
phase indexing or engineering claim is performed.
""",
        encoding="utf-8",
    )
    write_json(manifest_path, artifact_manifest(
        output_dir, [summary_path, inventory_path, folders_path, tiff_path, report_path]
    ))
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
