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
_ALLOWED_PROFILES = {"cross_material_tem_segmentation", "in_situ_tem_temporal"}
_COPYRIGHT_LIKE_LICENSES = {"copyright", "all-rights-reserved", "all rights reserved"}


class TemCandidateMetadataAuditError(RuntimeError):
    """Raised when a pinned TEM candidate metadata contract fails."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TemCandidateMetadataAuditError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        try:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
        except json.JSONDecodeError as exc:
            raise TemCandidateMetadataAuditError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise TemCandidateMetadataAuditError("JSON root must be an object")
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TemCandidateMetadataAuditError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field)


def _valid_md5(value: Any, field: str) -> str:
    md5 = _require_string(value, field).lower()
    if len(md5) != 32 or any(char not in "0123456789abcdef" for char in md5):
        raise TemCandidateMetadataAuditError(f"{field} must be a lowercase-compatible MD5")
    return md5


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    expected_top = {
        "schema_version",
        "case_id",
        "audit_date",
        "candidate_profile",
        "source",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != expected_top:
        raise TemCandidateMetadataAuditError("unexpected top-level config keys")
    if value["schema_version"] != SCHEMA_VERSION:
        raise TemCandidateMetadataAuditError("unsupported config schema_version")
    if value["candidate_profile"] not in _ALLOWED_PROFILES:
        raise TemCandidateMetadataAuditError("unsupported candidate_profile")

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
        "landing_page_version_claim",
        "expected_files",
        "expected_description_terms",
    }
    if not isinstance(source, dict) or set(source) != expected_source:
        raise TemCandidateMetadataAuditError("unexpected source config keys")
    if source["repository"] != "Zenodo":
        raise TemCandidateMetadataAuditError("this audit is pinned to Zenodo")
    if not isinstance(source["record_id"], int) or isinstance(source["record_id"], bool) or source["record_id"] <= 0:
        raise TemCandidateMetadataAuditError("record_id must be a positive integer")
    for field in (
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_title",
    ):
        _require_string(source[field], f"source.{field}")
    _optional_string(source["landing_page_version_claim"], "source.landing_page_version_claim")
    api = urllib.parse.urlparse(source["api_url"])
    if api.scheme != "https" or api.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise TemCandidateMetadataAuditError("api_url must use the pinned Zenodo host")

    expected_files = source["expected_files"]
    if not isinstance(expected_files, list) or not expected_files:
        raise TemCandidateMetadataAuditError("expected_files must be a non-empty list")
    seen_keys: set[str] = set()
    for index, entry in enumerate(expected_files):
        if not isinstance(entry, dict) or set(entry) != {"key", "md5"}:
            raise TemCandidateMetadataAuditError(
                f"expected_files[{index}] requires exactly key and md5"
            )
        key = _require_string(entry["key"], f"expected_files[{index}].key")
        _valid_md5(entry["md5"], f"expected_files[{index}].md5")
        if key in seen_keys:
            raise TemCandidateMetadataAuditError("expected file keys must be unique")
        seen_keys.add(key)

    terms = source["expected_description_terms"]
    if not isinstance(terms, list):
        raise TemCandidateMetadataAuditError("expected_description_terms must be a list")
    for index, term in enumerate(terms):
        _require_string(term, f"expected_description_terms[{index}]")

    boundary = value["scientific_boundary"]
    boundary_keys = {
        "metadata_api_request_authorized",
        "source_file_download_authorized",
        "remote_archive_inventory_authorized",
        "pixel_array_access_authorized",
        "model_weight_download_authorized",
        "model_execution_authorized",
        "analyzer_inference_authorized",
        "parameter_tuning_authorized",
        "model_retraining_authorized",
        "external_validation_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if not isinstance(boundary, dict) or set(boundary) != boundary_keys:
        raise TemCandidateMetadataAuditError("scientific_boundary keys do not match contract")
    if boundary["metadata_api_request_authorized"] is not True:
        raise TemCandidateMetadataAuditError("metadata API access must be explicitly authorized")
    for key in boundary_keys - {"metadata_api_request_authorized"}:
        if boundary[key] is not False:
            raise TemCandidateMetadataAuditError(f"scientific boundary must remain fail-closed: {key}")

    rules = value["decision_rules"]
    rule_keys = {
        "record_raw_tem_wording_does_not_prove_detector_native_or_lossless_representation",
        "filenames_or_folders_do_not_establish_immutable_acquisition_identity",
        "example_annotations_do_not_establish_complete_independent_ground_truth",
        "co_located_model_weights_do_not_establish_training_or_label_independence",
        "cross_material_tem_cannot_establish_cobalt_oxide_external_performance",
        "metadata_only_audit_cannot_establish_hdf5_schema_or_temporal_lineage",
        "declared_file_checksum_does_not_authorize_download_or_reuse",
    }
    if not isinstance(rules, dict) or set(rules) != rule_keys:
        raise TemCandidateMetadataAuditError("decision_rules keys do not match contract")
    if any(rules[key] is not True for key in rule_keys):
        raise TemCandidateMetadataAuditError("all fail-closed decision rules must be true")
    return value


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise TemCandidateMetadataAuditError("Zenodo API response must be an object")
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
    if isinstance(rights, list):
        for raw in rights:
            if not isinstance(raw, Mapping):
                continue
            identifier = raw.get("id") or raw.get("title")
            if identifier is not None:
                return str(identifier)
    return None


def normalize_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    raw_files = payload.get("files") or []
    if not isinstance(raw_files, list):
        raise TemCandidateMetadataAuditError("record files must be a list")
    files: list[dict[str, Any]] = []
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            raise TemCandidateMetadataAuditError("record file entry must be an object")
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
        "version_api": metadata.get("version"),
        "description": metadata.get("description"),
        "resource_type_id": _resource_type_id(metadata),
        "license_id": _license_id(metadata),
        "publication_date": metadata.get("publication_date"),
        "created": payload.get("created"),
        "updated": payload.get("updated"),
        "files": files,
    }


def _reuse_status(license_id: str | None) -> str:
    if license_id is None:
        return "reuse_terms_not_exposed_reuse_blocked"
    if license_id.strip().casefold() in _COPYRIGHT_LIKE_LICENSES:
        return "copyright_only_reuse_not_established"
    return "dataset_license_declared_manual_reuse_review_required"


def verify_record(config: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source"]
    expected = {
        "id": source["record_id"],
        "doi": source["doi"],
        "status": source["expected_status"],
        "title": source["expected_title"],
        "resource_type_id": source["expected_resource_type"],
    }
    for key, expected_value in expected.items():
        if record.get(key) != expected_value:
            raise TemCandidateMetadataAuditError(
                f"record mismatch for {key}: {record.get(key)!r} != {expected_value!r}"
            )

    landing_version = source["landing_page_version_claim"]
    api_version = record.get("version_api")
    if api_version is not None and not isinstance(api_version, str):
        raise TemCandidateMetadataAuditError("API version has an unexpected type")
    if landing_version is not None and api_version is not None and api_version != landing_version:
        raise TemCandidateMetadataAuditError(
            f"API version conflicts with landing-page claim: {api_version!r} != {landing_version!r}"
        )

    terms = source["expected_description_terms"]
    description = record.get("description")
    if terms:
        if not isinstance(description, str):
            raise TemCandidateMetadataAuditError("record description is missing")
        folded = description.casefold()
        missing_terms = [term for term in terms if str(term).casefold() not in folded]
        if missing_terms:
            raise TemCandidateMetadataAuditError(
                "record description no longer contains pinned terms: " + ", ".join(missing_terms)
            )

    files = record.get("files")
    if not isinstance(files, list):
        raise TemCandidateMetadataAuditError("record files are malformed")
    by_key = {item.get("key"): item for item in files if isinstance(item, Mapping)}
    expected_keys = {entry["key"] for entry in source["expected_files"]}
    if set(by_key) != expected_keys:
        raise TemCandidateMetadataAuditError("record file inventory differs from the pinned set")

    verified_files: list[dict[str, Any]] = []
    for expected_file in source["expected_files"]:
        observed = by_key[expected_file["key"]]
        expected_md5 = _valid_md5(expected_file["md5"], "expected md5")
        if observed.get("checksum") != f"md5:{expected_md5}":
            raise TemCandidateMetadataAuditError(
                f"record checksum changed: {expected_file['key']}"
            )
        size = observed.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise TemCandidateMetadataAuditError(
                f"record byte count is invalid: {expected_file['key']}"
            )
        content_url = observed.get("content_url")
        if not isinstance(content_url, str) or not content_url:
            raise TemCandidateMetadataAuditError(
                f"record content URL is missing: {expected_file['key']}"
            )
        parsed = urllib.parse.urlparse(content_url)
        if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
            raise TemCandidateMetadataAuditError(
                f"record content URL left the trusted Zenodo host: {expected_file['key']}"
            )
        verified_files.append(
            {
                "id": observed.get("id"),
                "key": observed.get("key"),
                "bytes": size,
                "md5": expected_md5,
                "content_url": content_url,
            }
        )

    license_id = record.get("license_id")
    if license_id is not None and not isinstance(license_id, str):
        raise TemCandidateMetadataAuditError("dataset license metadata has an unexpected type")
    return {
        "verified_files": verified_files,
        "license_id": license_id,
        "reuse_status": _reuse_status(license_id),
        "api_version": api_version,
        "landing_page_version_claim": landing_version,
    }


def _profile_assessment(profile: str, reuse_status: str) -> tuple[dict[str, str], list[str]]:
    reuse = (
        "Diagnostic"
        if reuse_status == "dataset_license_declared_manual_reuse_review_required"
        else "Inconclusive"
    )
    if profile == "cross_material_tem_segmentation":
        return (
            {
                "record_identity": "Supported",
                "file_identity_and_repository_md5": "Supported",
                "dataset_reuse_terms": reuse,
                "record_declared_raw_tem_for_15_samples": "Diagnostic",
                "detector_native_or_lossless_intensity_provenance": "Inconclusive",
                "immutable_sample_and_acquisition_identity": "Inconclusive",
                "annotation_provenance_and_completeness": "Inconclusive",
                "annotation_independence_from_target_model": "Inconclusive",
                "cobalt_oxide_material_domain_match": "Unsupported",
                "tem_segmentation_external_validation_ready": "Unsupported",
                "cross_material_software_robustness_use": "Inconclusive",
                "scientific_evidence_level": "Diagnostic",
            },
            [
                "Resolve dataset-level reuse authorization before any archive/member reuse.",
                "If reuse is authorized, perform a bounded remote archive/member inventory before downloading the 561 MB archive.",
                "Separate raw micrographs from segmented/annotated examples and preserve source-assigned sample identity.",
                "Audit annotation origin, completeness, and model-development non-use before any robustness comparison.",
                "Keep this source outside the Co3O4 external-validation claim domain.",
            ],
        )
    return (
        {
            "record_identity": "Supported",
            "file_identity_and_repository_md5": "Supported",
            "dataset_reuse_terms": reuse,
            "hdf5_schema": "Inconclusive",
            "trajectory_time_and_order_semantics": "Inconclusive",
            "immutable_sample_and_acquisition_identity": "Inconclusive",
            "model_development_coupling": "Inconclusive",
            "label_or_target_leakage_boundary": "Inconclusive",
            "cobalt_oxide_material_domain_match": "Unsupported",
            "temporal_in_situ_software_stress_test_ready": "Inconclusive",
            "external_validation_ready": "Unsupported",
            "scientific_evidence_level": "Inconclusive",
        },
        [
            "Resolve dataset-level reuse authorization before retrieving any source file.",
            "Do not transfer the 21 GB HDF5 file until a metadata-level need for its schema and trajectories is established.",
            "Determine HDF5 groups, trajectory/time ordering, sample/acquisition identity, and preprocessing only through a later separately authorized bounded audit.",
            "Audit how model_10k.pth was trained and whether labels, targets, or frames overlap the proposed software-stress-test subset.",
            "Use this source only for bounded temporal/in-situ software stress testing unless stronger task-matched evidence is independently established.",
        ],
    )


def build_snapshot(
    config: Mapping[str, Any],
    record: Mapping[str, Any],
    verification: Mapping[str, Any],
    *,
    config_sha256: str,
) -> dict[str, Any]:
    assessment, next_evidence = _profile_assessment(
        str(config["candidate_profile"]), str(verification["reuse_status"])
    )
    api_version = verification["api_version"]
    landing_version = verification["landing_page_version_claim"]
    if api_version is not None and landing_version is not None:
        version_status = "api_and_landing_page_consistent"
    elif landing_version is not None:
        version_status = "landing_page_claim_not_exposed_by_records_api"
    elif api_version is not None:
        version_status = "api_version_only"
    else:
        version_status = "version_not_explicitly_resolved"
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "candidate_profile": config["candidate_profile"],
        "execution_status": "metadata_audit_completed",
        "source": {
            "repository": "Zenodo",
            "record_id": record["id"],
            "doi": record["doi"],
            "title": record["title"],
            "version_api": api_version,
            "version_landing_page_claim": landing_version,
            "version_evidence_status": version_status,
            "resource_type": record["resource_type_id"],
            "license_id": verification["license_id"],
            "publication_date": record["publication_date"],
            "created": record["created"],
            "updated": record["updated"],
        },
        "file_inventory": verification["verified_files"],
        "evidence_assessment": assessment,
        "readiness": {
            "metadata_supported": True,
            "reuse_status": verification["reuse_status"],
            "source_download_authorized": False,
            "remote_archive_inventory_authorized": False,
            "pixel_array_access_authorized": False,
            "model_execution_authorized": False,
            "analyzer_execution_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": next_evidence,
        "scientific_boundary": config["scientific_boundary"],
        "decision_rules": config["decision_rules"],
        "config_sha256": config_sha256,
        "metadata_api_request_performed": True,
        "source_file_downloaded": False,
        "remote_archive_inventory_performed": False,
        "pixel_array_access_performed": False,
        "model_weights_downloaded": False,
        "model_execution_performed": False,
        "analyzer_inference_performed": False,
        "external_validation_claim_made": False,
        "engineering_decision_claim_made": False,
    }


def run(config_path: str | Path) -> dict[str, Any]:
    config_path = Path(config_path).resolve(strict=True)
    config = validate_config(load_json(config_path))
    record = normalize_record(fetch_json(config["source"]["api_url"]))
    verification = verify_record(config, record)
    return build_snapshot(
        config,
        record,
        verification,
        config_sha256=sha256_file(config_path),
    )


def write_json(path: str | Path, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Perform a metadata-only, fail-closed audit of a pinned public Zenodo TEM candidate. "
            "The command does not download source files, read pixels, or execute models."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    snapshot = run(args.config)
    write_json(args.output, snapshot)
    print(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
