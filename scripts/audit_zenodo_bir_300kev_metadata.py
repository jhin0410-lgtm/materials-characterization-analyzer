from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
SCHEMA_VERSION = "1.0"


class Bir300MetadataAuditError(RuntimeError):
    """Raised when the pinned BIR 300 keV metadata contract fails."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Bir300MetadataAuditError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        try:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
        except json.JSONDecodeError as exc:
            raise Bir300MetadataAuditError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise Bir300MetadataAuditError("JSON root must be an object")
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Bir300MetadataAuditError(f"{field} must be a non-empty string")
    return value.strip()


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    expected_top = {
        "schema_version",
        "case_id",
        "audit_date",
        "source",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != expected_top:
        raise Bir300MetadataAuditError("unexpected top-level config keys")
    if value["schema_version"] != SCHEMA_VERSION:
        raise Bir300MetadataAuditError("unsupported config schema_version")

    source = value["source"]
    expected_source = {
        "repository",
        "record_id",
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_title",
        "expected_version",
        "expected_files",
        "expected_description_terms",
    }
    if not isinstance(source, dict) or set(source) != expected_source:
        raise Bir300MetadataAuditError("unexpected source config keys")
    if source["repository"] != "Zenodo":
        raise Bir300MetadataAuditError("this audit is pinned to Zenodo")
    if not isinstance(source["record_id"], int) or source["record_id"] <= 0:
        raise Bir300MetadataAuditError("record_id must be a positive integer")
    for field in (
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_title",
        "expected_version",
    ):
        _require_string(source[field], f"source.{field}")
    api = urllib.parse.urlparse(source["api_url"])
    if api.scheme != "https" or api.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise Bir300MetadataAuditError("api_url must use the pinned Zenodo host")

    expected_files = source["expected_files"]
    if not isinstance(expected_files, list) or len(expected_files) != 6:
        raise Bir300MetadataAuditError("exactly six expected files are required")
    seen_keys: set[str] = set()
    for entry in expected_files:
        if not isinstance(entry, dict) or set(entry) != {"key", "md5"}:
            raise Bir300MetadataAuditError("expected file entries require key and md5")
        key = _require_string(entry["key"], "expected file key")
        md5 = _require_string(entry["md5"], "expected file md5").lower()
        if key in seen_keys:
            raise Bir300MetadataAuditError("expected file keys must be unique")
        seen_keys.add(key)
        if len(md5) != 32 or any(char not in "0123456789abcdef" for char in md5):
            raise Bir300MetadataAuditError(f"invalid expected MD5: {key}")
    terms = source["expected_description_terms"]
    if not isinstance(terms, list) or not terms:
        raise Bir300MetadataAuditError("expected_description_terms must be non-empty")
    for term in terms:
        _require_string(term, "expected description term")

    boundary = value["scientific_boundary"]
    boundary_keys = {
        "metadata_api_request_authorized",
        "source_archive_download_authorized",
        "source_file_retention_authorized",
        "archive_inventory_authorized",
        "pixel_array_access_authorized",
        "analyzer_inference_authorized",
        "parameter_tuning_authorized",
        "model_retraining_authorized",
        "phase_indexing_authorized",
        "external_validation_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if not isinstance(boundary, dict) or set(boundary) != boundary_keys:
        raise Bir300MetadataAuditError("scientific_boundary keys do not match contract")
    if boundary["metadata_api_request_authorized"] is not True:
        raise Bir300MetadataAuditError("metadata API access must be explicitly authorized")
    for key in boundary_keys - {"metadata_api_request_authorized"}:
        if boundary[key] is not False:
            raise Bir300MetadataAuditError(f"scientific boundary must remain fail-closed: {key}")

    rules = value["decision_rules"]
    rule_keys = {
        "missing_dataset_license_is_blocking_for_reuse",
        "article_license_cannot_substitute_for_dataset_license",
        "archive_identity_does_not_establish_tvips_member_identity",
        "filename_conditions_do_not_establish_acquisition_lineage",
        "static_diffraction_wording_does_not_establish_pattern_center_or_reciprocal_calibration",
        "cross_material_data_cannot_establish_cobalt_oxide_in_domain_performance",
    }
    if not isinstance(rules, dict) or set(rules) != rule_keys:
        raise Bir300MetadataAuditError("decision_rules keys do not match contract")
    if any(rules[key] is not True for key in rule_keys):
        raise Bir300MetadataAuditError("all fail-closed decision rules must be true")
    return value


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise Bir300MetadataAuditError("Zenodo API response must be an object")
    return value


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
        identifier = value.get("id") or value.get("title")
        return str(identifier) if identifier is not None else None
    rights = metadata.get("rights")
    if isinstance(rights, list) and rights:
        first = rights[0]
        if isinstance(first, Mapping):
            identifier = first.get("id") or first.get("title")
            return str(identifier) if identifier is not None else None
    return None


def normalize_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    files: list[dict[str, Any]] = []
    raw_files = payload.get("files") or []
    if not isinstance(raw_files, list):
        raise Bir300MetadataAuditError("record files must be a list")
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            raise Bir300MetadataAuditError("record file entry must be an object")
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
        "version": metadata.get("version"),
        "description": metadata.get("description"),
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
        "version": source["expected_version"],
        "resource_type_id": source["expected_resource_type"],
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise Bir300MetadataAuditError(
                f"record mismatch for {key}: {record.get(key)!r} != {value!r}"
            )

    description = record.get("description")
    if not isinstance(description, str):
        raise Bir300MetadataAuditError("record description is missing")
    description_folded = description.casefold()
    missing_terms = [
        term
        for term in source["expected_description_terms"]
        if str(term).casefold() not in description_folded
    ]
    if missing_terms:
        raise Bir300MetadataAuditError(
            "record description no longer contains pinned terms: " + ", ".join(missing_terms)
        )

    files = record.get("files")
    if not isinstance(files, list):
        raise Bir300MetadataAuditError("normalized files must be a list")
    if len(files) != len(source["expected_files"]):
        raise Bir300MetadataAuditError("record file count differs from the six-file contract")
    by_key = {item.get("key"): item for item in files if isinstance(item, Mapping)}
    expected_keys = {entry["key"] for entry in source["expected_files"]}
    if set(by_key) != expected_keys:
        raise Bir300MetadataAuditError("record file inventory differs from the pinned archive set")

    verified_files: list[dict[str, Any]] = []
    for expected_file in source["expected_files"]:
        observed = by_key[expected_file["key"]]
        if observed.get("checksum") != f"md5:{expected_file['md5']}":
            raise Bir300MetadataAuditError(
                f"record checksum changed: {expected_file['key']}"
            )
        size = observed.get("bytes")
        if not isinstance(size, int) or size <= 0:
            raise Bir300MetadataAuditError(
                f"record byte count is invalid: {expected_file['key']}"
            )
        content_url = observed.get("content_url")
        if not isinstance(content_url, str) or not content_url:
            raise Bir300MetadataAuditError(
                f"record content URL is missing: {expected_file['key']}"
            )
        parsed = urllib.parse.urlparse(content_url)
        if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
            raise Bir300MetadataAuditError(
                f"record content URL left the trusted Zenodo host: {expected_file['key']}"
            )
        verified_files.append(
            {
                "id": observed.get("id"),
                "key": observed.get("key"),
                "bytes": size,
                "md5": expected_file["md5"],
                "content_url": content_url,
            }
        )

    license_id = record.get("license_id")
    if license_id is not None and not isinstance(license_id, str):
        raise Bir300MetadataAuditError("dataset license metadata has an unexpected type")
    reuse_status = (
        "dataset_license_declared_review_required"
        if license_id
        else "dataset_license_missing_reuse_blocked"
    )
    return {
        "verified_files": verified_files,
        "license_id": license_id,
        "reuse_status": reuse_status,
    }


def build_snapshot(
    config: Mapping[str, Any],
    record: Mapping[str, Any],
    verification: Mapping[str, Any],
    *,
    config_sha256: str,
) -> dict[str, Any]:
    license_id = verification["license_id"]
    reuse_status = verification["reuse_status"]
    metadata_supported = True
    archive_audit_authorized = False
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "metadata_audit_completed",
        "source": {
            "repository": "Zenodo",
            "record_id": record["id"],
            "doi": record["doi"],
            "title": record["title"],
            "version": record["version"],
            "resource_type": record["resource_type_id"],
            "license_id": license_id,
            "publication_date": record["publication_date"],
            "created": record["created"],
            "updated": record["updated"],
        },
        "file_inventory": verification["verified_files"],
        "evidence_assessment": {
            "record_identity": "Supported",
            "six_archive_identity_and_repository_md5": "Supported",
            "dataset_reuse_terms": "Supported" if license_id else "Inconclusive",
            "tvips_member_identity_and_integrity": "Inconclusive",
            "sample_and_acquisition_lineage": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "reference_reflection_truth": "Inconclusive",
            "analyzer_development_independence": "Inconclusive",
            "scientific_evidence_level": "Inconclusive",
        },
        "readiness": {
            "metadata_supported": metadata_supported,
            "reuse_status": reuse_status,
            "archive_audit_authorized": archive_audit_authorized,
            "analyzer_execution_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": [
            "Pin and review the dataset-level reuse terms from the Zenodo record before any source-file reuse.",
            "If reuse is authorized, select a bounded archive-audit subset before considering the 36.5 GB collection.",
            "Inspect native .tvips member identity, file structure, detector/microscope metadata, acquisition-series identity, pattern-centre evidence and reciprocal calibration without analyzer inference.",
            "Keep the three compounds and two temperatures as separate source conditions and do not pool them with other BIR datasets solely to increase sample count.",
        ],
        "prohibited_inference": [
            "Do not use the article CC BY 4.0 licence as a substitute for dataset-level rights metadata.",
            "Do not infer sample or acquisition identity from filename order alone.",
            "Do not infer pattern centre, reciprocal calibration, detector-native intensity preservation or reflection truth from static-diffraction wording.",
            "Do not treat molecular-crystal data as in-domain cobalt-oxide performance evidence.",
        ],
        "config_sha256": config_sha256,
        "source_archive_downloaded": False,
        "source_bytes_retained": False,
        "analyzer_inference_performed": False,
    }


def run_audit(config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = validate_config(load_json(config_resolved))
    record = normalize_record(fetch_json(config["source"]["api_url"]))
    verification = verify_record(config, record)
    snapshot = build_snapshot(
        config,
        record,
        verification,
        config_sha256=sha256_file(config_resolved),
    )
    output = Path(output_path).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit only the Zenodo record metadata and six archive identities for "
            "BIR-MicroED 300 keV. This command does not download source archives."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_bir_300kev_saed_metadata_audit/case_config.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_audit(args.config, args.output)
    except (OSError, ValueError, Bir300MetadataAuditError) as exc:
        print(f"BIR 300 keV metadata audit failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
