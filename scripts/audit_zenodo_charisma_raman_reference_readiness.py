from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

USER_AGENT = "materials-characterization-analyzer-charisma-raman-readiness/1.0"
TRUSTED_ZENODO_HOSTS = {"zenodo.org", "www.zenodo.org"}


class CharismaRamanReadinessError(RuntimeError):
    """Raised when the bounded CHARISMA Raman metadata contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CharismaRamanReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise CharismaRamanReadinessError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise CharismaRamanReadinessError(f"JSON root must be an object: {resolved}")
    return payload


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CharismaRamanReadinessError("repository evidence path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CharismaRamanReadinessError("configured repository evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise CharismaRamanReadinessError("repository evidence resolved outside project root")
    return resolved


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _trusted_zenodo_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CharismaRamanReadinessError("Zenodo URL is missing")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in TRUSTED_ZENODO_HOSTS:
        raise CharismaRamanReadinessError("URL is outside trusted Zenodo hosts")
    return value


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "source",
        "publication_evidence",
        "scientific_target",
        "scientific_boundary",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise CharismaRamanReadinessError("CHARISMA readiness config keys/schema mismatch")
    if config.get("case_id") != "charisma_raman_reference_readiness":
        raise CharismaRamanReadinessError("CHARISMA readiness case identity drifted")

    source = config.get("source")
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
    }
    if not isinstance(source, dict) or set(source) != required_source:
        raise CharismaRamanReadinessError("Zenodo source contract drifted")
    if source.get("repository") != "Zenodo" or source.get("record_id") != 13387413:
        raise CharismaRamanReadinessError("Zenodo source identity drifted")
    if source.get("doi") != "10.5281/zenodo.13387413":
        raise CharismaRamanReadinessError("Zenodo DOI drifted")
    if source.get("expected_status") != "published" or source.get("expected_resource_type") != "other":
        raise CharismaRamanReadinessError("Zenodo status/resource-type contract drifted")
    if source.get("landing_page_version_claim") != "v1":
        raise CharismaRamanReadinessError("Zenodo landing-page version claim drifted")
    _trusted_zenodo_url(source.get("record_url"))
    api_url = _trusted_zenodo_url(source.get("api_url"))
    if urllib.parse.urlparse(api_url).path != "/api/records/13387413":
        raise CharismaRamanReadinessError("Zenodo API URL path drifted")

    files = source.get("expected_files")
    if not isinstance(files, list) or files != [
        {"key": "peak_fitting_spectra.nxs", "md5": "88485671e56662b00aaad9303dc653d6"}
    ]:
        raise CharismaRamanReadinessError("expected NeXus file identity drifted")

    publication_path = _resolve_repo_path(config.get("publication_evidence"))
    if publication_path.name != "publication_evidence.json":
        raise CharismaRamanReadinessError("publication evidence path drifted")

    target = config.get("scientific_target")
    expected_target = {
        "future_claim": "reference_material_peak_position_localization_and_wavelength_calibration_support",
        "materials": ["neon", "silicon", "calcite", "polystyrene"],
        "compound_or_phase_identification_claim": False,
        "vibrational_mode_assignment_claim": False,
        "quantitative_defect_or_crystallinity_claim": False,
        "cross_instrument_generalization_claim": False,
    }
    if target != expected_target:
        raise CharismaRamanReadinessError("scientific target drifted")

    boundary = config.get("scientific_boundary")
    allowed_true = {
        "metadata_api_request_authorized",
        "record_license_and_version_metadata_authorized",
        "record_file_identity_and_checksum_metadata_authorized",
    }
    if not isinstance(boundary, dict):
        raise CharismaRamanReadinessError("scientific_boundary must be an object")
    if any(boundary.get(key) is not True for key in allowed_true):
        raise CharismaRamanReadinessError("required metadata operations are not authorized")
    if any(value is not False for key, value in boundary.items() if key not in allowed_true):
        raise CharismaRamanReadinessError("NeXus/analyzer/claim operations must remain disabled")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise CharismaRamanReadinessError("all CHARISMA fail-closed rules must be enabled")
    return config


def _validate_publication_evidence(path: Path) -> dict[str, Any]:
    evidence = _load_json(path)
    publication = evidence.get("publication")
    facts = evidence.get("supported_publication_facts")
    assessment = evidence.get("current_evidence_assessment")
    if evidence.get("schema_version") != "1.0" or not isinstance(publication, Mapping):
        raise CharismaRamanReadinessError("publication evidence schema is invalid")
    if publication.get("doi") != "10.1177/00037028251330654":
        raise CharismaRamanReadinessError("publication DOI drifted")
    if publication.get("zenodo_dataset_doi") != "10.5281/zenodo.13387413":
        raise CharismaRamanReadinessError("publication-to-Zenodo binding drifted")
    if not isinstance(facts, Mapping) or any(value is not True for value in facts.values()):
        raise CharismaRamanReadinessError("required publication facts were not preserved")
    if not isinstance(assessment, Mapping):
        raise CharismaRamanReadinessError("publication evidence assessment is invalid")
    if assessment.get("exact_nexus_internal_structure") != "Inconclusive":
        raise CharismaRamanReadinessError("NeXus internal structure was prematurely promoted")
    if assessment.get("exact_reference_peak_truth_available_in_dataset") != "Inconclusive":
        raise CharismaRamanReadinessError("reference peak truth was prematurely promoted")
    return evidence


def _fetch_record(url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    request = urllib.request.Request(
        _trusted_zenodo_url(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise CharismaRamanReadinessError(f"Zenodo API returned HTTP {status}")
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if final.scheme != "https" or final.hostname not in TRUSTED_ZENODO_HOSTS:
            raise CharismaRamanReadinessError("Zenodo API redirected outside trusted hosts")
        if final.path != "/api/records/13387413":
            raise CharismaRamanReadinessError("Zenodo API redirected away from pinned record")
        content_type = response.headers.get_content_type()
        if content_type not in {"application/json", "application/ld+json"}:
            raise CharismaRamanReadinessError(f"unexpected Zenodo content type: {content_type}")
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise CharismaRamanReadinessError("Zenodo metadata response exceeds 2 MB ceiling")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CharismaRamanReadinessError("Zenodo metadata response is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CharismaRamanReadinessError("Zenodo metadata root is not an object")
    return value, {
        "status": int(status),
        "final_url": final_url,
        "content_type": content_type,
        "response_bytes": len(payload),
        "response_sha256": _sha256_bytes(payload),
    }


def _resource_type_id(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("resource_type")
    if isinstance(value, Mapping):
        for key in ("id", "type"):
            raw = value.get(key)
            if isinstance(raw, str) and raw:
                return raw
        return None
    return value if isinstance(value, str) and value else None


def _license_records(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    rights = metadata.get("rights")
    if isinstance(rights, list):
        for item in rights:
            if isinstance(item, Mapping):
                records.append({
                    "id": item.get("id") if isinstance(item.get("id"), str) else None,
                    "title": item.get("title") if isinstance(item.get("title"), Mapping) else item.get("title"),
                    "link": item.get("link") if isinstance(item.get("link"), str) else None,
                })
    if records:
        return records
    legacy = metadata.get("license")
    if isinstance(legacy, Mapping):
        return [{
            "id": legacy.get("id") if isinstance(legacy.get("id"), str) else None,
            "title": legacy.get("title") or legacy.get("name"),
            "link": legacy.get("link") or legacy.get("url"),
        }]
    if isinstance(legacy, str) and legacy:
        return [{"id": legacy, "title": None, "link": None}]
    return []


def _raw_file_records(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    files = record.get("files")
    if isinstance(files, Sequence) and not isinstance(files, (str, bytes, bytearray)):
        raw_records = list(files)
    elif isinstance(files, Mapping):
        entries = files.get("entries")
        if isinstance(entries, Mapping):
            raw_records = list(entries.values())
        elif isinstance(entries, Sequence) and not isinstance(entries, (str, bytes, bytearray)):
            raw_records = list(entries)
        else:
            raise CharismaRamanReadinessError("Zenodo file entries are not exposed in a supported schema")
    else:
        raise CharismaRamanReadinessError("Zenodo files field uses an unsupported schema")
    if not raw_records or any(not isinstance(item, Mapping) for item in raw_records):
        raise CharismaRamanReadinessError("Zenodo file inventory is empty or malformed")
    return [item for item in raw_records if isinstance(item, Mapping)]


def _file_inventory(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in _raw_file_records(record):
        key = raw.get("key")
        size = raw.get("size")
        checksum = raw.get("checksum")
        links = raw.get("links")
        file_id = raw.get("id")
        if not isinstance(key, str) or not key:
            raise CharismaRamanReadinessError("Zenodo file key is missing")
        if not isinstance(size, int) or size <= 0:
            raise CharismaRamanReadinessError(f"invalid Zenodo file size for {key}")
        if not isinstance(checksum, str) or not checksum.startswith("md5:"):
            raise CharismaRamanReadinessError(f"Zenodo checksum is not MD5 for {key}")
        md5 = checksum.split(":", 1)[1].casefold()
        if not re.fullmatch(r"[0-9a-f]{32}", md5):
            raise CharismaRamanReadinessError(f"invalid Zenodo MD5 for {key}")
        if not isinstance(links, Mapping):
            raise CharismaRamanReadinessError(f"missing Zenodo file links for {key}")
        content_candidate = links.get("content") or links.get("self") or links.get("download")
        content_url = _trusted_zenodo_url(content_candidate)
        result.append({
            "id": str(file_id) if file_id is not None else None,
            "key": key,
            "bytes": int(size),
            "md5": md5,
            "content_url": content_url,
        })
    keys = [row["key"] for row in result]
    if len(keys) != len(set(keys)):
        raise CharismaRamanReadinessError("Zenodo file inventory contains duplicate keys")
    return sorted(result, key=lambda row: row["key"])


def _validate_record(config: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source"]
    if record.get("id") != source["record_id"]:
        raise CharismaRamanReadinessError("Zenodo record ID drifted")
    if record.get("status") != source["expected_status"]:
        raise CharismaRamanReadinessError(f"Zenodo record status drifted: {record.get('status')!r}")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        raise CharismaRamanReadinessError("Zenodo metadata object is missing")
    if metadata.get("title") != source["expected_title"]:
        raise CharismaRamanReadinessError(
            f"Zenodo title drifted: {metadata.get('title')!r}"
        )
    resource_type = _resource_type_id(metadata)
    if resource_type != source["expected_resource_type"]:
        raise CharismaRamanReadinessError(f"Zenodo resource type drifted: {resource_type!r}")

    inventory = _file_inventory(record)
    expected = {row["key"]: row["md5"] for row in source["expected_files"]}
    observed = {row["key"]: row["md5"] for row in inventory}
    if observed != expected:
        raise CharismaRamanReadinessError(
            f"Zenodo file inventory/MD5 drifted: expected={expected}, observed={observed}"
        )
    return {
        "metadata": metadata,
        "resource_type": resource_type,
        "license_records": _license_records(metadata),
        "inventory": inventory,
        "version_api": metadata.get("version") if isinstance(metadata.get("version"), str) else None,
    }


def _license_disposition(records: list[dict[str, Any]]) -> str:
    if not records:
        return "Inconclusive"
    searchable = " ".join(
        str(value or "")
        for record in records
        for value in (record.get("id"), record.get("title"), record.get("link"))
    ).casefold()
    if any(token in searchable for token in ("cc-by-4.0", "cc by 4.0", "creativecommons.org/licenses/by/4.0")):
        return "Supported"
    return "Diagnostic"


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    publication_path = _resolve_repo_path(config["publication_evidence"])
    publication = _validate_publication_evidence(publication_path)
    record, http = _fetch_record(config["source"]["api_url"])
    verified = _validate_record(config, record)
    metadata = verified["metadata"]
    licenses = verified["license_records"]
    inventory = verified["inventory"]
    license_status = _license_disposition(licenses)
    nexus = inventory[0]

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "charisma_raman_reference_metadata_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "publication_evidence": {
            "path": str(publication_path.relative_to(PROJECT_ROOT)),
            "sha256": _sha256_file(publication_path),
            "publication_doi": publication["publication"]["doi"],
            "candidate_role": publication["scientific_interpretation"]["candidate_role"],
        },
        "zenodo_api": {
            **http,
            "raw_metadata_retained": False,
        },
        "source": {
            "repository": "Zenodo",
            "record_id": config["source"]["record_id"],
            "doi": config["source"]["doi"],
            "title": metadata.get("title"),
            "resource_type": verified["resource_type"],
            "publication_date": metadata.get("publication_date"),
            "created": record.get("created"),
            "updated": record.get("updated"),
            "version_api": verified["version_api"],
            "version_landing_page_claim": config["source"]["landing_page_version_claim"],
            "license_records": licenses,
            "license_metadata_disposition": license_status,
        },
        "file_inventory": inventory,
        "nexus_candidate": {
            **nexus,
            "payload_bytes_read": 0,
            "downloaded": False,
            "structure_inspected": False,
        },
        "evidence_assessment": {
            "zenodo_record_identity_and_file_checksum": "Supported",
            "dataset_license_metadata": license_status,
            "interlaboratory_reference_material_context": "Supported",
            "nexus_candidate_identity": "Supported",
            "nexus_internal_structure": "Inconclusive",
            "exact_reference_peak_truth_in_nexus": "Inconclusive",
            "raman_peak_position_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "metadata_audit_ready": True,
            "nexus_download_authorized": False,
            "nexus_structure_inspection_authorized": False,
            "spectrum_array_access_authorized": False,
            "validation_subset_selection_authorized": False,
            "raman_analyzer_execution_authorized": False,
            "parameter_tuning_authorized": False,
            "matching_tolerance_selection_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": {
            "priority": 1,
            "requirement": "predeclare_checksum_bound_nexus_structure_inventory_before_any_spectrum_or_mca_access",
            "why": (
                "The interlaboratory publication is directly relevant to peak-position and wavelength-calibration uncertainty, "
                "but scientific validation requires knowing which NeXus groups/datasets contain raw spectra, reference materials, "
                "instrument identity and fitted/reference peak results before MCA output or parameter choices are exposed."
            ),
        },
        "scientific_boundary": [
            "Only Zenodo API metadata was requested; the NeXus file payload was not read.",
            "Dataset license evidence is recorded only from Zenodo metadata and is not inferred from secondary catalog pages.",
            "Reference-material and interlaboratory context comes from the reviewed publication, while exact NeXus structure and peak truth remain unresolved.",
            "No spectrum array, validation subset, MCA Raman output, parameter tuning, matching tolerance, external-validation claim or engineering decision is authorized."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise CharismaRamanReadinessError(f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Zenodo metadata for the CHARISMA interlaboratory Raman reference-material dataset "
            "without downloading the NeXus file or running MCA Raman."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (CharismaRamanReadinessError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
