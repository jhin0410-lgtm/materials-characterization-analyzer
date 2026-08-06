#!/usr/bin/env python3
"""Fail-closed metadata and archive audit for the Zenodo W-Ta-Cr-V TEM dataset."""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image

from scripts import audit_zenodo_ge_dm3_tem_saed as base

RESULT = (
    "checksum_verified_wtacrv_tem_saed_archive_inventory_completed_but_"
    "calibration_acquisition_lineage_and_independence_incomplete"
)


class WTaCrVAuditError(RuntimeError):
    """Raised when the pinned source contract or bounded audit fails."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"case_id", "audit_date", "source", "limits", "scientific_boundary"}:
        raise WTaCrVAuditError("unexpected top-level config keys")
    source = payload["source"]
    expected_source = {
        "repository", "record_id", "doi", "record_url", "api_url",
        "expected_status", "expected_resource_type", "expected_title_substring",
        "allowed_license_ids", "target_file", "required_description_terms",
        "source_quality_flags",
    }
    if set(source) != expected_source:
        raise WTaCrVAuditError("unexpected source config keys")
    if set(source["target_file"]) != {"key", "md5"}:
        raise WTaCrVAuditError("unexpected target-file config keys")
    if not source["allowed_license_ids"]:
        raise WTaCrVAuditError("allowed_license_ids must be non-empty")
    limits = payload["limits"]
    expected_limits = {
        "minimum_archive_bytes", "maximum_archive_bytes", "maximum_member_count",
        "maximum_total_uncompressed_bytes", "maximum_single_member_bytes",
        "maximum_member_compression_ratio", "maximum_selected_member_count",
        "maximum_selected_uncompressed_bytes",
    }
    if set(limits) != expected_limits:
        raise WTaCrVAuditError("unexpected limit keys")
    if any(not isinstance(value, int) or value <= 0 for value in limits.values()):
        raise WTaCrVAuditError("all limits must be positive integers")
    boundary = payload["scientific_boundary"]
    required_true = {
        "source_archive_download_authorized", "archive_member_inventory_authorized",
        "bounded_selected_member_header_inspection_authorized",
    }
    required_false = {
        "source_archive_retention_authorized", "source_files_may_be_uploaded_as_artifacts",
        "archive_members_may_be_uploaded_as_artifacts", "pixel_array_export_authorized",
        "image_preprocessing_authorized", "model_inference_authorized",
        "annotation_authorized", "parameter_tuning_authorized",
        "model_retraining_authorized", "external_validation_claim_authorized",
        "phase_indexing_claim_authorized", "engineering_decision_claim_authorized",
    }
    if any(boundary.get(key) is not True for key in required_true):
        raise WTaCrVAuditError("required bounded audit operations are not authorized")
    if any(boundary.get(key) is not False for key in required_false):
        raise WTaCrVAuditError("scientific boundary must remain fail-closed")
    return payload


def _metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def verify_record(config: Mapping[str, Any], payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = config["source"]
    record = base.normalize_record(payload)
    exact = {
        "id": source["record_id"],
        "doi": source["doi"],
        "status": source["expected_status"],
        "resource_type_id": source["expected_resource_type"],
    }
    for key, expected in exact.items():
        if record.get(key) != expected:
            raise WTaCrVAuditError(
                f"record mismatch for {key}: {record.get(key)!r} != {expected!r}"
            )
    title = record.get("title")
    if not isinstance(title, str) or source["expected_title_substring"].casefold() not in title.casefold():
        raise WTaCrVAuditError(f"record title mismatch: {title!r}")
    license_id = record.get("license_id")
    allowed = {str(value).casefold() for value in source["allowed_license_ids"]}
    if not isinstance(license_id, str) or license_id.casefold() not in allowed:
        raise WTaCrVAuditError(f"record licence mismatch: {license_id!r}")

    description = str(_metadata(payload).get("description") or "")
    folded_description = description.casefold()
    missing_terms = [
        term for term in source["required_description_terms"]
        if str(term).casefold() not in folded_description
    ]
    if missing_terms:
        raise WTaCrVAuditError(f"record description lost required terms: {missing_terms}")

    files = record.get("files")
    if not isinstance(files, list):
        raise WTaCrVAuditError("normalized record files must be a list")
    matches = [item for item in files if item.get("key") == source["target_file"]["key"]]
    if len(matches) != 1:
        raise WTaCrVAuditError(f"target archive must occur exactly once: {len(matches)}")
    target = dict(matches[0])
    size = target.get("bytes")
    if not isinstance(size, int):
        raise WTaCrVAuditError("target archive byte count is invalid")
    limits = config["limits"]
    if not limits["minimum_archive_bytes"] <= size <= limits["maximum_archive_bytes"]:
        raise WTaCrVAuditError(f"target archive bytes outside frozen bounds: {size}")
    if target.get("checksum") != f"md5:{source['target_file']['md5']}":
        raise WTaCrVAuditError("target archive checksum changed")
    url = target.get("content_url")
    if not isinstance(url, str):
        raise WTaCrVAuditError("target archive content URL is missing")
    parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise WTaCrVAuditError("target archive URL escaped pinned Zenodo host")
    return record, target


def microscopy_cues(path: str) -> list[str]:
    p = PurePosixPath(path)
    folded = path.casefold()
    basename = p.name.casefold()
    parts = [part.casefold() for part in p.parts]
    cues: list[str] = []
    if any(part == "tem" or part.startswith("tem ") or part.startswith("tem_") for part in parts):
        cues.append("tem_folder")
    if any(part == "sem" or part.startswith("sem ") or part.startswith("sem_") for part in parts):
        cues.append("sem_folder")
    if "saed" in folded or "selected area" in folded or "diffraction" in folded or "diff" in basename:
        cues.append("saed_name_cue")
    if any(term in folded for term in ("eds", "edx", "elemental map", "element map")):
        cues.append("eds_name_cue")
    if any(term in folded for term in ("he-irr", "he_irr", "he irr", "irradiat", "implanted")):
        cues.append("irradiated_condition_cue")
    if any(term in folded for term in ("as-depos", "as_depos", "as depos", "pristine", "unirradiated")):
        cues.append("as_deposited_condition_cue")
    if any(term in folded for term in ("calib", "camera length", "pattern centre", "pattern center")):
        cues.append("calibration_or_centre_name_cue")
    return cues


def augment_inventory(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    augmented: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        row["wtacrv_role_cues"] = microscopy_cues(str(row["member_path"]))
        augmented.append(row)
    return augmented


def select_header_members(rows: Sequence[Mapping[str, Any]], limits: Mapping[str, int]) -> list[dict[str, Any]]:
    inspectable = {
        ".dm3", ".dm4", ".emd", ".ser", ".emi", ".mrc", ".mrcs",
        ".tif", ".tiff", ".bmp", ".png", ".jpg", ".jpeg", ".emsa", ".msa", ".txt",
    }
    candidates: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        cues = set(row.get("wtacrv_role_cues") or [])
        suffix = str(row.get("suffix") or "").casefold()
        if "tem_folder" not in cues or suffix not in inspectable:
            continue
        priority = (
            0 if "saed_name_cue" in cues else
            1 if "eds_name_cue" in cues else
            2 if row.get("representation_class") == "native_microscopy_container" else
            3
        )
        row["selection_priority"] = priority
        candidates.append(row)
    candidates.sort(
        key=lambda item: (
            int(item["selection_priority"]),
            int(item["uncompressed_bytes"]),
            str(item["member_path"]).casefold(),
        )
    )
    selected: list[dict[str, Any]] = []
    total = 0
    for row in candidates:
        size = int(row["uncompressed_bytes"])
        if len(selected) >= limits["maximum_selected_member_count"]:
            break
        if total + size > limits["maximum_selected_uncompressed_bytes"]:
            continue
        selected.append(row)
        total += size
    if not selected:
        raise WTaCrVAuditError("no bounded TEM-folder members were selectable")
    return selected


def _dm_header(path: Path) -> dict[str, Any]:
    header = path.read_bytes()[:32]
    result: dict[str, Any] = {
        "header_bytes": len(header),
        "header_hex": header[:16].hex(),
    }
    if path.suffix.casefold() in {".dm3", ".dm4"} and len(header) >= 12:
        result["digital_micrograph_version_big_endian"] = int.from_bytes(header[0:4], "big")
        result["digital_micrograph_byte_order_marker"] = int.from_bytes(header[8:12], "big")
    return result


def inspect_selected(paths: Sequence[Path], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        item: dict[str, Any] = {
            "member_path": relative,
            "bytes": path.stat().st_size,
            "sha256": base._hash_file(path),
            "suffix": path.suffix.casefold(),
            "header": _dm_header(path),
        }
        if path.suffix.casefold() in {".tif", ".tiff", ".bmp", ".png", ".jpg", ".jpeg"}:
            try:
                with Image.open(path) as image:
                    tags: dict[str, str] = {}
                    for key, value in getattr(image, "tag_v2", {}).items():
                        if key in {256, 257, 258, 259, 262, 270, 282, 283, 296, 305, 306, 315, 33432}:
                            tags[str(key)] = str(value)[:500]
                    item["image_header"] = {
                        "format": image.format,
                        "mode": image.mode,
                        "size": list(image.size),
                        "n_frames": getattr(image, "n_frames", 1),
                        "selected_tags": tags,
                    }
            except Exception as exc:
                item["image_header_error"] = type(exc).__name__
        rows.append(item)
    rows.sort(key=lambda item: str(item["member_path"]).casefold())
    return rows


def _write_inventory(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "member_path", "uncompressed_bytes", "packed_bytes", "compression_ratio",
        "modified", "crc", "suffix", "representation_class", "wtacrv_role_cues",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["wtacrv_role_cues"] = ";".join(row.get("wtacrv_role_cues") or [])
            writer.writerow(out)


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise WTaCrVAuditError("output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = base.fetch_json(config["source"]["api_url"])
    record, target = verify_record(config, payload)
    seven_zip = base.find_7z()

    with tempfile.TemporaryDirectory(prefix="wtacrv_tem_saed_") as temp_name:
        temp = Path(temp_name)
        archive = temp / config["source"]["target_file"]["key"]
        archive_identity = base.stream_download(
            str(target["content_url"]), archive,
            expected_bytes=int(target["bytes"]),
            expected_md5=config["source"]["target_file"]["md5"],
        )
        base.test_archive(archive, seven_zip)
        inventory = augment_inventory(base.list_archive(archive, seven_zip, config["limits"]))
        selected = select_header_members(inventory, config["limits"])
        extraction_root = temp / "selected"
        extracted = base.extract_selected_members(archive, seven_zip, selected, extraction_root)
        selected_metadata = inspect_selected(extracted, extraction_root)

    representation_counts = Counter(str(row["representation_class"]) for row in inventory)
    cue_counts = Counter(cue for row in inventory for cue in row["wtacrv_role_cues"])
    suffix_counts = Counter(str(row["suffix"]) for row in inventory)
    top_level_counts = Counter(PurePosixPath(str(row["member_path"])).parts[0] for row in inventory)
    selected_cue_counts = Counter(cue for row in selected for cue in row["wtacrv_role_cues"])
    calibration_header_hits = sorted({
        term
        for item in selected_metadata
        for value in (item.get("image_header") or {}).get("selected_tags", {}).values()
        for term in ("camera length", "accelerating voltage", "pixel size", "reciprocal", "calibration")
        if term in str(value).casefold()
    })

    summary = {
        "status": RESULT,
        "evidence_level": "Diagnostic",
        "record": record,
        "archive": {**archive_identity, "key": target["key"]},
        "member_count": len(inventory),
        "total_uncompressed_bytes": sum(int(row["uncompressed_bytes"]) for row in inventory),
        "representation_counts": dict(sorted(representation_counts.items())),
        "suffix_counts": dict(sorted(suffix_counts.items())),
        "top_level_member_counts": dict(sorted(top_level_counts.items())),
        "role_cue_counts": dict(sorted(cue_counts.items())),
        "selected_header_member_count": len(selected_metadata),
        "selected_role_cue_counts": dict(sorted(selected_cue_counts.items())),
        "selected_header_calibration_keyword_hits": calibration_header_hits,
        "evidence_assessment": {
            "record_and_archive_identity": "Supported",
            "safe_archive_integrity_and_inventory": "Supported",
            "source_declared_tem_saed_eds_scope": "Supported_by_record",
            "tem_folder_and_condition_name_cues": "Diagnostic",
            "selected_member_identity_and_file_headers": "Supported",
            "detector_native_intensity_preservation": "Inconclusive",
            "pattern_centre_and_reciprocal_calibration": (
                "Diagnostic_only" if calibration_header_hits else "Inconclusive"
            ),
            "acquisition_independence_and_development_non_use": "Inconclusive",
        },
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
            "authoritative sample and acquisition identifiers for every TEM and SAED file",
            "camera length, pattern centre, reciprocal-space calibration and detector geometry",
            "exposure, binning, gain, dark-current correction and saturation state",
            "whether raster members preserve detector-native intensities or are exported/processed images",
            "complete mapping between as-deposited and irradiated specimens and individual files",
            "independence from current analyzer development, threshold selection and tuning",
            "material-domain comparability with cobalt-oxide validation targets",
        ],
    }

    summary_path = output_dir / "zenodo_wtacrv_tem_saed_audit_summary.json"
    inventory_path = output_dir / "zenodo_wtacrv_member_inventory.csv"
    selected_path = output_dir / "zenodo_wtacrv_selected_member_identity.csv"
    metadata_path = output_dir / "zenodo_wtacrv_selected_header_metadata.json"
    report_path = output_dir / "zenodo_wtacrv_tem_saed_audit_report.md"
    manifest_path = output_dir / "zenodo_wtacrv_tem_saed_audit_manifest.json"
    base._write_json(summary_path, summary)
    _write_inventory(inventory_path, inventory)
    with selected_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["member_path", "uncompressed_bytes", "suffix", "representation_class", "wtacrv_role_cues"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in selected:
            out = dict(row)
            out["wtacrv_role_cues"] = ";".join(row.get("wtacrv_role_cues") or [])
            writer.writerow(out)
    base._write_json(metadata_path, selected_metadata)
    report_path.write_text(
        f"""# Zenodo W-Ta-Cr-V TEM/SAED source audit

## Result

- Status: `{RESULT}`
- Evidence level: **Diagnostic**
- DOI: `{record['doi']}`
- Licence: `{record['license_id']}`
- Archive bytes: `{archive_identity['bytes']}`
- Archive MD5: `{archive_identity['md5']}`
- Archive SHA-256: `{archive_identity['sha256']}`
- Regular members: `{len(inventory)}`
- Native microscopy containers: `{representation_counts.get('native_microscopy_container', 0)}`
- TEM-folder cues: `{cue_counts.get('tem_folder', 0)}`
- SAED-name cues: `{cue_counts.get('saed_name_cue', 0)}`
- EDS-name cues: `{cue_counts.get('eds_name_cue', 0)}`
- As-deposited cues: `{cue_counts.get('as_deposited_condition_cue', 0)}`
- Irradiated cues: `{cue_counts.get('irradiated_condition_cue', 0)}`
- Selected members inspected: `{len(selected_metadata)}`
- Calibrated-SAED validation ready: **no**

## Supported

The official Zenodo record, DOI, licence, target filename, repository MD5, observed
SHA-256, archive integrity, bounded member inventory and selected-member identities
are supported for this record version.

## Limitations

The deposit concerns a W-Ta-Cr-V refractory high-entropy alloy, not cobalt oxide.
Folder and filename cues are diagnostic and do not replace authoritative sample or
acquisition IDs. Native container or raster representation does not establish
calibrated d-spacing accuracy, detector-native intensity preservation, acquisition
independence or external scientific validity.

No source archive, member or pixel array is retained. No preprocessing, analyzer
inference, annotation, phase indexing, tuning or retraining is performed.
""",
        encoding="utf-8",
    )
    base._write_json(
        manifest_path,
        base._artifact_manifest(
            output_dir,
            [summary_path, inventory_path, selected_path, metadata_path, report_path],
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
