from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

USER_AGENT = "materials-characterization-analyzer-zenodo-metadata-audit/1.0"


class SrTiO3SaedMetadataAuditError(RuntimeError):
    """Raised when the SrTiO3 Zenodo metadata contract is violated."""


def _load_json(path: str | Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SrTiO3SaedMetadataAuditError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise SrTiO3SaedMetadataAuditError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise SrTiO3SaedMetadataAuditError("JSON root must be an object")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trusted_zenodo_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise SrTiO3SaedMetadataAuditError("Zenodo URL is missing")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise SrTiO3SaedMetadataAuditError("URL is outside trusted Zenodo")
    return value


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "source",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise SrTiO3SaedMetadataAuditError("config keys/schema do not match contract")
    source = value["source"]
    if not isinstance(source, dict):
        raise SrTiO3SaedMetadataAuditError("source config must be an object")
    required_source = {
        "repository",
        "record_id",
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_title",
        "landing_page_version_claim",
        "expected_files",
        "expected_description_terms",
    }
    if set(source) != required_source:
        raise SrTiO3SaedMetadataAuditError("source config keys do not match contract")
    if source.get("record_id") != 20300700:
        raise SrTiO3SaedMetadataAuditError("unexpected SrTiO3 Zenodo record id")
    _trusted_zenodo_url(source.get("record_url"))
    _trusted_zenodo_url(source.get("api_url"))
    files = source.get("expected_files")
    if not isinstance(files, list) or len(files) != 4:
        raise SrTiO3SaedMetadataAuditError("expected file inventory must contain four files")
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict) or set(record) != {"key", "md5"}:
            raise SrTiO3SaedMetadataAuditError("expected file record is invalid")
        key = record.get("key")
        md5 = record.get("md5")
        if not isinstance(key, str) or not key or key in seen:
            raise SrTiO3SaedMetadataAuditError("expected file key is invalid or duplicated")
        if not isinstance(md5, str) or not re.fullmatch(r"[0-9a-f]{32}", md5):
            raise SrTiO3SaedMetadataAuditError("expected file MD5 is invalid")
        seen.add(key)
    if "SAED.zip" not in seen:
        raise SrTiO3SaedMetadataAuditError("SAED.zip is absent from expected inventory")
    boundary = value["scientific_boundary"]
    if not isinstance(boundary, dict) or boundary.get("metadata_api_request_authorized") is not True:
        raise SrTiO3SaedMetadataAuditError("metadata API request is not authorized")
    if any(item is not False for key, item in boundary.items() if key != "metadata_api_request_authorized"):
        raise SrTiO3SaedMetadataAuditError("stronger data/analyzer actions must remain disabled")
    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise SrTiO3SaedMetadataAuditError("all fail-closed decision rules must be enabled")
    return value


def _fetch_record(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        _trusted_zenodo_url(url),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise SrTiO3SaedMetadataAuditError(f"Zenodo API returned HTTP {status}")
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in {"zenodo.org", "www.zenodo.org"}:
            raise SrTiO3SaedMetadataAuditError("Zenodo API redirected outside trusted host")
        payload = response.read(4_000_001)
        if len(payload) > 4_000_000:
            raise SrTiO3SaedMetadataAuditError("Zenodo metadata response exceeds 4 MB limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SrTiO3SaedMetadataAuditError("Zenodo metadata response is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SrTiO3SaedMetadataAuditError("Zenodo metadata root is not an object")
    return value


def _resource_type_id(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("resource_type")
    if isinstance(value, Mapping):
        raw = value.get("id")
        return str(raw) if isinstance(raw, str) else None
    return str(value) if isinstance(value, str) else None


def _license_id(metadata: Mapping[str, Any]) -> str | None:
    rights = metadata.get("rights")
    if isinstance(rights, list):
        ids = [str(item.get("id")) for item in rights if isinstance(item, Mapping) and isinstance(item.get("id"), str)]
        unique = sorted(set(ids))
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            return ";".join(unique)
    legacy = metadata.get("license")
    if isinstance(legacy, Mapping) and isinstance(legacy.get("id"), str):
        return str(legacy["id"])
    if isinstance(legacy, str) and legacy:
        return legacy
    return None


def _file_entries(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = record.get("files")
    entries: Any = None
    if isinstance(files, Mapping):
        entries = files.get("entries")
    if not isinstance(entries, Mapping):
        raise SrTiO3SaedMetadataAuditError("Zenodo file entries are not exposed as an object")
    result: list[dict[str, Any]] = []
    for map_key, raw in entries.items():
        if not isinstance(raw, Mapping):
            raise SrTiO3SaedMetadataAuditError("Zenodo file entry is not an object")
        key = raw.get("key") if isinstance(raw.get("key"), str) else str(map_key)
        size = raw.get("size")
        checksum = raw.get("checksum")
        links = raw.get("links")
        file_id = raw.get("id")
        if not isinstance(size, int) or size <= 0:
            raise SrTiO3SaedMetadataAuditError(f"invalid file size for {key}")
        if not isinstance(checksum, str) or not checksum.startswith("md5:"):
            raise SrTiO3SaedMetadataAuditError(f"repository checksum is not MD5 for {key}")
        md5 = checksum.split(":", 1)[1].lower()
        if not re.fullmatch(r"[0-9a-f]{32}", md5):
            raise SrTiO3SaedMetadataAuditError(f"invalid repository MD5 for {key}")
        if not isinstance(links, Mapping):
            raise SrTiO3SaedMetadataAuditError(f"missing file links for {key}")
        content_url = _trusted_zenodo_url(links.get("content"))
        result.append(
            {
                "id": str(file_id) if file_id is not None else None,
                "key": key,
                "bytes": int(size),
                "md5": md5,
                "content_url": content_url,
            }
        )
    return sorted(result, key=lambda item: item["key"])


def _validate_record(config: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source"]
    if record.get("id") != source["record_id"]:
        raise SrTiO3SaedMetadataAuditError("Zenodo record id drifted")
    status = record.get("status")
    if status != source["expected_status"]:
        raise SrTiO3SaedMetadataAuditError(f"Zenodo record status drifted: {status!r}")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        raise SrTiO3SaedMetadataAuditError("Zenodo metadata object is missing")
    if metadata.get("title") != source["expected_title"]:
        raise SrTiO3SaedMetadataAuditError("Zenodo title drifted")
    resource_type = _resource_type_id(metadata)
    if resource_type != source["expected_resource_type"]:
        raise SrTiO3SaedMetadataAuditError("Zenodo resource type drifted")
    description = str(metadata.get("description") or "")
    description_fold = description.casefold()
    for term in source["expected_description_terms"]:
        if str(term).casefold() not in description_fold:
            raise SrTiO3SaedMetadataAuditError(f"expected description term missing: {term}")

    inventory = _file_entries(record)
    expected = {item["key"]: item["md5"] for item in source["expected_files"]}
    observed = {item["key"]: item["md5"] for item in inventory}
    if observed != expected:
        raise SrTiO3SaedMetadataAuditError(
            f"Zenodo file inventory/MD5 drifted: expected={sorted(expected)}, observed={sorted(observed)}"
        )
    version_api = metadata.get("version") if isinstance(metadata.get("version"), str) else None
    return {
        "metadata": metadata,
        "inventory": inventory,
        "resource_type": resource_type,
        "license_id": _license_id(metadata),
        "version_api": version_api,
    }


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    record = _fetch_record(config["source"]["api_url"])
    verified = _validate_record(config, record)
    metadata = verified["metadata"]
    inventory = verified["inventory"]
    license_id = verified["license_id"]
    version_api = verified["version_api"]
    saed = next(item for item in inventory if item["key"] == "SAED.zip")

    license_status = "Supported" if license_id else "Inconclusive"
    snapshot = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "metadata_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "source": {
            "repository": "Zenodo",
            "record_id": config["source"]["record_id"],
            "doi": config["source"]["doi"],
            "title": metadata.get("title"),
            "resource_type": verified["resource_type"],
            "publication_date": metadata.get("publication_date"),
            "created": record.get("created"),
            "updated": record.get("updated"),
            "license_id": license_id,
            "version_landing_page_claim": config["source"]["landing_page_version_claim"],
            "version_api": version_api,
            "version_evidence_status": (
                "api_and_landing_claim_recorded_separately"
                if version_api is not None
                else "landing_page_claim_not_exposed_by_records_api"
            ),
        },
        "file_inventory": inventory,
        "saed_archive": saed,
        "evidence_assessment": {
            "record_identity": "Supported",
            "four_file_identity_and_repository_md5": "Supported",
            "dataset_reuse_terms": license_status,
            "saed_archive_identity": "Supported",
            "saed_static_representation": "Inconclusive",
            "pattern_count_and_acquisition_independence": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "four_d_stem_saed_modality_separation": "Supported",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Inconclusive",
        },
        "readiness": {
            "metadata_supported": True,
            "reuse_status": (
                "dataset_license_declared_review_required"
                if license_id
                else "dataset_license_missing_reuse_blocked"
            ),
            "saed_archive_inventory_authorized": bool(license_id),
            "four_d_stem_download_authorized": False,
            "pixel_array_access_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": [
            "Inspect only SAED.zip central-directory/member metadata before any 4D-STEM transfer.",
            "Determine whether SAED.zip contains raw/static diffraction arrays, rendered images, processed exports, or mixed representations.",
            "Count patterns and preserve acquisition/sample identity without inferring independence from filenames alone.",
            "Determine whether pattern centre and reciprocal calibration are embedded or traceable to authoritative acquisition metadata.",
            "Keep 35 K and 69 K 4D-STEM raw datasets separate from SAED evidence unless an explicit versioned relationship is supported."
        ],
        "prohibited_inference": [
            "Do not infer static-SAED representation from the SAED.zip filename alone.",
            "Do not infer independent acquisitions from member count or filename order.",
            "Do not infer calibration, phase truth or detector-native intensity preservation from repository hosting.",
            "Do not use the two 4D-STEM arrays merely to increase SAED sample count.",
            "Do not run analyzer inference or tune parameters at the metadata-audit stage."
        ],
        "source_archive_downloaded": False,
        "source_bytes_retained": False,
        "analyzer_inference_performed": False,
    }
    output = Path(output_path).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Zenodo metadata for the SrTiO3 SAED candidate.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_srtio3_saed_metadata_audit/case_config.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/zenodo_srtio3_saed_metadata_audit/metadata_snapshot.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (OSError, ValueError, SrTiO3SaedMetadataAuditError) as exc:
        print(f"SrTiO3 SAED metadata audit failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
