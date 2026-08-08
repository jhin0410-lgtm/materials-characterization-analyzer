from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FigshareRruffReadinessError(RuntimeError):
    """Raised when the bounded Figshare/RRUFF metadata-readiness contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FigshareRruffReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise FigshareRruffReadinessError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise FigshareRruffReadinessError(f"JSON root must be an object: {resolved}")
    return payload


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FigshareRruffReadinessError("repository evidence path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FigshareRruffReadinessError("configured repository evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise FigshareRruffReadinessError("repository evidence resolved outside project root")
    return resolved


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "source",
        "network_limits",
        "authorized_operations",
        "scientific_target",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise FigshareRruffReadinessError("Figshare readiness config keys/schema mismatch")
    if config.get("case_id") != "figshare_rruff_peak_reference_readiness":
        raise FigshareRruffReadinessError("Figshare readiness case identity drifted")

    source = config.get("source")
    expected_source_keys = {
        "figshare_article_id",
        "api_url",
        "expected_title",
        "expected_current_version",
        "expected_base_doi",
        "publication_doi",
    }
    if not isinstance(source, dict) or set(source) != expected_source_keys:
        raise FigshareRruffReadinessError("source contract drifted")
    if source.get("figshare_article_id") != 7427393:
        raise FigshareRruffReadinessError("Figshare article ID drifted")
    if source.get("api_url") != "https://api.figshare.com/v2/articles/7427393":
        raise FigshareRruffReadinessError("Figshare API URL drifted")
    if source.get("expected_title") != "High-throughput Computation and Evaluation of Raman Spectra":
        raise FigshareRruffReadinessError("Figshare expected title drifted")
    if source.get("expected_current_version") != 2:
        raise FigshareRruffReadinessError("Figshare expected version drifted")
    if source.get("expected_base_doi") != "10.6084/m9.figshare.7427393":
        raise FigshareRruffReadinessError("Figshare base DOI drifted")
    if source.get("publication_doi") != "10.1038/s41597-019-0138-y":
        raise FigshareRruffReadinessError("publication DOI drifted")

    limits = config.get("network_limits")
    if not isinstance(limits, dict) or set(limits) != {
        "maximum_metadata_response_bytes",
        "timeout_seconds",
        "allowed_hosts",
    }:
        raise FigshareRruffReadinessError("network_limits contract drifted")
    ceiling = limits.get("maximum_metadata_response_bytes")
    if not isinstance(ceiling, int) or not 4096 <= ceiling <= 262144:
        raise FigshareRruffReadinessError("metadata response ceiling is invalid")
    timeout = limits.get("timeout_seconds")
    if not isinstance(timeout, int) or not 1 <= timeout <= 120:
        raise FigshareRruffReadinessError("network timeout is invalid")
    if limits.get("allowed_hosts") != ["api.figshare.com"]:
        raise FigshareRruffReadinessError("trusted Figshare API host set drifted")

    operations = config.get("authorized_operations")
    allowed_true = {
        "request_exact_figshare_article_metadata",
        "record_license_metadata",
        "record_file_inventory_metadata",
        "record_file_hash_metadata",
    }
    if not isinstance(operations, dict):
        raise FigshareRruffReadinessError("authorized_operations must be an object")
    if any(operations.get(key) is not True for key in allowed_true):
        raise FigshareRruffReadinessError("required metadata-only operations are not authorized")
    if any(value is not False for key, value in operations.items() if key not in allowed_true):
        raise FigshareRruffReadinessError("dataset-file/analyzer/claim operations must remain disabled")

    target = config.get("scientific_target")
    if not isinstance(target, dict) or target != {
        "future_claim": "peak_localization_agreement_on_frozen_reference_spectra",
        "source_acquisition_generalization_claim": False,
        "mineral_classification_claim": False,
        "vibrational_mode_assignment_claim": False,
        "quantitative_defect_or_crystallinity_claim": False,
    }:
        raise FigshareRruffReadinessError("scientific target drifted")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise FigshareRruffReadinessError("all Figshare fail-closed decision rules must be enabled")
    return config


def _validate_publication_evidence() -> tuple[Path, dict[str, Any]]:
    path = _resolve_repo_path(
        "case_studies/figshare_rruff_peak_reference_readiness/publication_evidence.json"
    )
    evidence = _load_json(path)
    if evidence.get("schema_version") != "1.0":
        raise FigshareRruffReadinessError("publication evidence schema drifted")
    if evidence.get("publication_doi") != "10.1038/s41597-019-0138-y":
        raise FigshareRruffReadinessError("publication evidence DOI drifted")
    if evidence.get("figshare_base_doi") != "10.6084/m9.figshare.7427393":
        raise FigshareRruffReadinessError("publication evidence Figshare DOI drifted")
    facts = evidence.get("supported_publication_facts")
    unresolved = evidence.get("unresolved_reference_provenance")
    if not isinstance(facts, Mapping) or not isinstance(unresolved, Mapping):
        raise FigshareRruffReadinessError("publication evidence fields are malformed")
    if any(value is not True for value in facts.values()):
        raise FigshareRruffReadinessError("required publication fact was not preserved")
    if unresolved.get("exact_algorithm_or_manual_protocol_used_to_extract_experimental_peak_locations") != "Inconclusive":
        raise FigshareRruffReadinessError("peak-extraction provenance was prematurely promoted")
    if unresolved.get("suitability_as_authoritative_physical_peak_truth") != "Inconclusive":
        raise FigshareRruffReadinessError("reference peak truth was prematurely promoted")
    return path, evidence


def _trusted_api_url(value: object, allowed_hosts: list[str]) -> str:
    if not isinstance(value, str) or not value:
        raise FigshareRruffReadinessError("Figshare API URL is missing")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in set(allowed_hosts):
        raise FigshareRruffReadinessError("Figshare API URL is outside trusted hosts")
    if parsed.path != "/v2/articles/7427393" or parsed.query or parsed.fragment:
        raise FigshareRruffReadinessError("Figshare API URL is not the exact predeclared article endpoint")
    return value


def _download_metadata(
    url: str,
    *,
    maximum_bytes: int,
    timeout_seconds: int,
    allowed_hosts: list[str],
) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(
        _trusted_api_url(url, allowed_hosts),
        headers={
            "User-Agent": "materials-characterization-analyzer-figshare-readiness/1.0",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise FigshareRruffReadinessError(f"Figshare API returned HTTP {status}")
        final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname not in set(allowed_hosts):
            raise FigshareRruffReadinessError("Figshare API redirected outside trusted hosts")
        if parsed.path != "/v2/articles/7427393":
            raise FigshareRruffReadinessError("Figshare API redirected away from pinned article")
        content_type = response.headers.get_content_type()
        if content_type not in {"application/json", "application/ld+json"}:
            raise FigshareRruffReadinessError(
                f"unexpected Figshare API content type: {content_type}"
            )
        payload = response.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            raise FigshareRruffReadinessError("Figshare metadata response exceeds configured ceiling")
    return payload, {
        "status": int(status),
        "final_url": final_url,
        "content_type": content_type,
    }


def _parse_metadata(payload: bytes, source: Mapping[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FigshareRruffReadinessError("Figshare metadata is not valid UTF-8 JSON") from exc
    if not isinstance(metadata, Mapping):
        raise FigshareRruffReadinessError("Figshare metadata root is not an object")
    if metadata.get("id") != source["figshare_article_id"]:
        raise FigshareRruffReadinessError("Figshare article ID does not match contract")
    if metadata.get("title") != source["expected_title"]:
        raise FigshareRruffReadinessError("Figshare title does not match contract")
    if metadata.get("version") != source["expected_current_version"]:
        raise FigshareRruffReadinessError("Figshare current version does not match contract")

    doi = metadata.get("doi")
    allowed_dois = {
        source["expected_base_doi"],
        f"{source['expected_base_doi']}.v{source['expected_current_version']}",
    }
    if doi not in allowed_dois:
        raise FigshareRruffReadinessError(f"unexpected Figshare DOI: {doi!r}")

    license_value = metadata.get("license")
    license_record: dict[str, Any]
    if isinstance(license_value, Mapping):
        license_record = {
            "id": license_value.get("id"),
            "name": license_value.get("name"),
            "url": license_value.get("url"),
            "metadata_present": bool(license_value.get("name") or license_value.get("id")),
        }
    else:
        license_record = {
            "id": None,
            "name": None,
            "url": None,
            "metadata_present": False,
        }

    raw_files = metadata.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise FigshareRruffReadinessError("Figshare metadata does not expose a non-empty file inventory")
    files: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for index, raw in enumerate(raw_files):
        if not isinstance(raw, Mapping):
            raise FigshareRruffReadinessError(f"Figshare files[{index}] is not an object")
        file_id = raw.get("id")
        name = raw.get("name")
        size = raw.get("size")
        if not isinstance(file_id, int) or file_id <= 0:
            raise FigshareRruffReadinessError(f"Figshare files[{index}] has invalid id")
        if file_id in seen_ids:
            raise FigshareRruffReadinessError(f"duplicate Figshare file id: {file_id}")
        seen_ids.add(file_id)
        if not isinstance(name, str) or not name.strip():
            raise FigshareRruffReadinessError(f"Figshare files[{index}] has invalid name")
        if not isinstance(size, int) or size < 0:
            raise FigshareRruffReadinessError(f"Figshare files[{index}] has invalid size")
        download_url = raw.get("download_url")
        files.append(
            {
                "id": file_id,
                "name": name,
                "size": size,
                "is_link_only": raw.get("is_link_only"),
                "download_url": download_url if isinstance(download_url, str) else None,
                "supplied_md5": raw.get("supplied_md5") if isinstance(raw.get("supplied_md5"), str) else None,
                "computed_md5": raw.get("computed_md5") if isinstance(raw.get("computed_md5"), str) else None,
            }
        )

    experimental_json_candidates = [
        record
        for record in files
        if record["name"].casefold().endswith(".json")
        and any(token in record["name"].casefold() for token in ("experiment", "rruff"))
    ]
    return {
        "article": {
            "id": metadata.get("id"),
            "title": metadata.get("title"),
            "doi": doi,
            "version": metadata.get("version"),
            "published_date": metadata.get("published_date"),
            "modified_date": metadata.get("modified_date"),
            "defined_type": metadata.get("defined_type"),
            "defined_type_name": metadata.get("defined_type_name"),
            "is_active": metadata.get("is_active"),
        },
        "license": license_record,
        "files": files,
        "experimental_json_candidates": experimental_json_candidates,
    }


def _license_disposition(license_record: Mapping[str, Any]) -> str:
    if not license_record.get("metadata_present"):
        return "Inconclusive"
    name = str(license_record.get("name") or "").casefold()
    if any(token in name for token in ("cc by", "creative commons attribution", "cc0", "public domain")):
        return "Supported"
    return "Diagnostic"


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    publication_path, publication_evidence = _validate_publication_evidence()

    source = config["source"]
    limits = config["network_limits"]
    payload, http = _download_metadata(
        str(source["api_url"]),
        maximum_bytes=int(limits["maximum_metadata_response_bytes"]),
        timeout_seconds=int(limits["timeout_seconds"]),
        allowed_hosts=list(limits["allowed_hosts"]),
    )
    parsed = _parse_metadata(payload, source)
    license_status = _license_disposition(parsed["license"])
    experimental_candidates = parsed["experimental_json_candidates"]
    candidate_status = "Supported" if experimental_candidates else "Inconclusive"
    hashes_present = all(
        bool(record["supplied_md5"] or record["computed_md5"])
        for record in parsed["files"]
    )

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "figshare_rruff_peak_reference_metadata_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "publication_evidence": {
            "path": str(publication_path.relative_to(PROJECT_ROOT)),
            "sha256": _sha256_file(publication_path),
            "candidate_role": publication_evidence["scientific_interpretation"]["candidate_role"],
            "peak_extraction_provenance": publication_evidence["unresolved_reference_provenance"]["exact_algorithm_or_manual_protocol_used_to_extract_experimental_peak_locations"],
            "authoritative_peak_truth_status": publication_evidence["unresolved_reference_provenance"]["suitability_as_authoritative_physical_peak_truth"],
        },
        "figshare_api": {
            **http,
            "response_bytes": len(payload),
            "response_sha256": _sha256_bytes(payload),
            "raw_metadata_retained": False,
        },
        "article": parsed["article"],
        "license": {
            **parsed["license"],
            "reuse_metadata_disposition": license_status,
            "paper_license_inferred_for_dataset": False,
        },
        "file_inventory": parsed["files"],
        "file_inventory_summary": {
            "file_count": len(parsed["files"]),
            "all_files_have_repository_md5_metadata": hashes_present,
            "experimental_json_candidate_count": len(experimental_candidates),
            "experimental_json_candidates": experimental_candidates,
            "dataset_file_payload_bytes_read": 0,
        },
        "evidence_assessment": {
            "figshare_article_identity_and_version": "Supported",
            "figshare_dataset_license_metadata": license_status,
            "figshare_file_identity_metadata": "Supported",
            "experimental_json_candidate_identity": candidate_status,
            "experimental_peak_annotation_provenance": "Diagnostic",
            "independent_authoritative_peak_position_truth": "Inconclusive",
            "raman_peak_localization_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "metadata_audit_ready": True,
            "dataset_file_download_authorized": False,
            "experimental_json_download_authorized": False,
            "rruff_spectrum_download_authorized": False,
            "raman_analyzer_execution_authorized": False,
            "parameter_tuning_authorized": False,
            "model_fit_or_training_authorized": False,
            "mineral_classification_claim_authorized": False,
            "vibrational_mode_assignment_claim_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": {
            "priority": 1,
            "requirement": "pin_exact_experimental_json_identity_and_resolve_peak_annotation_provenance_before_payload_download",
            "download_now": False,
            "why": (
                "Figshare metadata can provide a frozen version, explicit license metadata, and file-level identity. "
                "However, the paper does not yet establish the exact independent protocol used to create the experimental "
                "peak-location annotations, so those annotations must remain Diagnostic until their provenance is resolved."
            ),
        },
        "scientific_boundary": [
            "Only Figshare article metadata was requested; no Figshare dataset file or RRUFF spectrum byte was read.",
            "The dataset license is recorded only from Figshare metadata and is not inferred from the Scientific Data article license.",
            "Materials Project matches and computed Raman modes are not used to select, tune, or score the MCA peak detector.",
            "Experimental JSON peak locations remain reference annotations rather than authoritative physical truth until extraction provenance is resolved.",
            "No Raman analyzer execution, tuning, classification, vibrational assignment, external-validation claim, or engineering decision is authorized."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise FigshareRruffReadinessError(f"refusing to overwrite output: {output}")
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
            "Audit Figshare metadata for the frozen RRUFF experimental Raman peak-reference candidate "
            "without downloading dataset files or running the Raman analyzer."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (FigshareRruffReadinessError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
