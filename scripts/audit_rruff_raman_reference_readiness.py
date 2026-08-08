from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RruffRamanReadinessError(RuntimeError):
    """Raised when the bounded RRUFF Raman readiness contract is violated."""


class _IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.visible_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        folded = tag.casefold()
        if folded in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if folded == "a" and not self._ignored_depth:
            attrs_map = {key.casefold(): value for key, value in attrs}
            self._href = attrs_map.get("href")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        folded = tag.casefold()
        if folded in {"script", "style", "noscript"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if folded == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if data.strip():
            self.visible_parts.append(data)
        if self._href is not None:
            self._text.append(data)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RruffRamanReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise RruffRamanReadinessError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise RruffRamanReadinessError(f"JSON root must be an object: {resolved}")
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
        raise RruffRamanReadinessError("repository path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RruffRamanReadinessError("configured repository path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise RruffRamanReadinessError("repository path resolved outside project root")
    return resolved


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "source_system",
        "source_claims_snapshot",
        "network_limits",
        "authorized_operations",
        "validation_target",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise RruffRamanReadinessError("RRUFF readiness config keys/schema mismatch")
    if config.get("case_id") != "rruff_raman_reference_readiness":
        raise RruffRamanReadinessError("RRUFF readiness case identity drifted")

    source = config.get("source_system")
    expected_source_keys = {
        "name",
        "official_index_url",
        "candidate_archive",
        "legacy_project_url",
        "current_project_url",
        "nasa_ahed_doi",
        "project_method_reference_doi",
    }
    if not isinstance(source, dict) or set(source) != expected_source_keys:
        raise RruffRamanReadinessError("source_system contract drifted")
    if source.get("name") != "RRUFF Project":
        raise RruffRamanReadinessError("source system name drifted")
    if source.get("official_index_url") != "https://www.rruff.net/zipped_data_files/raman/":
        raise RruffRamanReadinessError("official Raman index URL drifted")
    if source.get("candidate_archive") != "excellent_unoriented.zip":
        raise RruffRamanReadinessError("candidate archive drifted")
    if source.get("nasa_ahed_doi") != "10.48667/pre9-s770":
        raise RruffRamanReadinessError("NASA AHED catalog DOI drifted")
    if source.get("project_method_reference_doi") != "10.1515/9783110417104-003":
        raise RruffRamanReadinessError("RRUFF method-reference DOI drifted")

    snapshot_path = _resolve_repo_path(config.get("source_claims_snapshot"))
    if snapshot_path.name != "verified_source_claims_snapshot.json":
        raise RruffRamanReadinessError("source claims snapshot path drifted")

    limits = config.get("network_limits")
    if not isinstance(limits, dict) or set(limits) != {
        "maximum_index_response_bytes",
        "timeout_seconds",
        "allowed_hosts",
    }:
        raise RruffRamanReadinessError("network_limits contract drifted")
    if not isinstance(limits.get("maximum_index_response_bytes"), int) or not (
        1024 <= limits["maximum_index_response_bytes"] <= 131072
    ):
        raise RruffRamanReadinessError("index response ceiling is invalid")
    if not isinstance(limits.get("timeout_seconds"), int) or not 1 <= limits["timeout_seconds"] <= 120:
        raise RruffRamanReadinessError("network timeout is invalid")
    if limits.get("allowed_hosts") != ["www.rruff.net", "rruff.net"]:
        raise RruffRamanReadinessError("trusted RRUFF host set drifted")

    operations = config.get("authorized_operations")
    required_true = {
        "request_official_raman_index_html",
        "parse_candidate_link_from_index",
        "record_index_hash_and_listing_metadata",
    }
    if not isinstance(operations, dict):
        raise RruffRamanReadinessError("authorized_operations must be an object")
    if any(operations.get(key) is not True for key in required_true):
        raise RruffRamanReadinessError("required metadata-only operations are not authorized")
    if any(value is not False for key, value in operations.items() if key not in required_true):
        raise RruffRamanReadinessError("archive/analyzer/claim operations must remain disabled")

    target = config.get("validation_target")
    if not isinstance(target, dict) or target != {
        "future_claim": "peak_localization_agreement_against_independent_reference_only",
        "mineral_classification_claim": False,
        "vibrational_mode_assignment_claim": False,
        "quantitative_defect_or_crystallinity_claim": False,
    }:
        raise RruffRamanReadinessError("future Raman validation target drifted")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise RruffRamanReadinessError("all fail-closed RRUFF decision rules must be enabled")
    return config


def _validate_source_claims(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot.get("schema_version") != "1.0":
        raise RruffRamanReadinessError("source claims schema drifted")
    observations = snapshot.get("observations")
    assessment = snapshot.get("evidence_assessment")
    if not isinstance(observations, Mapping) or not isinstance(assessment, Mapping):
        raise RruffRamanReadinessError("source claims evidence is malformed")

    required_true = {
        "project_describes_data_as_free_access",
        "project_describes_public_release_after_review",
        "project_describes_mineral_characterization_with_xrd_and_chemical_composition",
        "project_describes_raman_acquisition_with_multiple_laser_wavelengths",
        "current_official_index_lists_excellent_unoriented_zip",
        "nasa_ahed_catalog_exposes_rruff_dataset_doi",
    }
    if any(observations.get(key) is not True for key in required_true):
        raise RruffRamanReadinessError("required reviewed RRUFF source observation drifted")
    required_false = {
        "explicit_machine_readable_dataset_license_observed_on_rruff_source",
        "explicit_redistribution_or_derived_dataset_license_observed_on_rruff_source",
        "archive_checksum_or_immutable_version_identifier_observed_on_rruff_index",
        "independent_peak_position_truth_observed",
    }
    if any(observations.get(key) is not False for key in required_false):
        raise RruffRamanReadinessError("unresolved RRUFF rights/version/truth field was promoted")

    expected_assessment = {
        "rruff_project_identity": "Supported",
        "public_reference_library_access": "Supported",
        "reviewed_mineral_reference_context": "Diagnostic",
        "current_bulk_archive_listing": "Supported",
        "explicit_reuse_rights_for_automated_acquisition_and_redistribution": "Inconclusive",
        "candidate_archive_immutable_version_identity": "Inconclusive",
        "independent_peak_position_truth": "Inconclusive",
        "raman_external_validation_readiness": "Inconclusive",
        "scientific_evidence_level": "Diagnostic",
    }
    for key, expected in expected_assessment.items():
        if assessment.get(key) != expected:
            raise RruffRamanReadinessError(f"source assessment drifted: {key}")
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_sha256": None,
        "rights_status": assessment["explicit_reuse_rights_for_automated_acquisition_and_redistribution"],
        "immutable_archive_identity_status": assessment["candidate_archive_immutable_version_identity"],
        "independent_peak_truth_status": assessment["independent_peak_position_truth"],
        "reference_context_status": assessment["reviewed_mineral_reference_context"],
    }


def _trusted_index_url(value: object, allowed_hosts: list[str]) -> str:
    if not isinstance(value, str) or not value:
        raise RruffRamanReadinessError("RRUFF index URL is missing")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in set(allowed_hosts):
        raise RruffRamanReadinessError("RRUFF index URL is outside trusted hosts")
    if parsed.path != "/zipped_data_files/raman/":
        raise RruffRamanReadinessError("RRUFF index URL path drifted")
    return value


def _download_index(url: str, *, maximum_bytes: int, timeout_seconds: int, allowed_hosts: list[str]) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(
        _trusted_index_url(url, allowed_hosts),
        headers={
            "User-Agent": "materials-characterization-analyzer-rruff-readiness/1.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise RruffRamanReadinessError(f"RRUFF index returned HTTP {status}")
        final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname not in set(allowed_hosts):
            raise RruffRamanReadinessError("RRUFF index redirected outside trusted hosts")
        if parsed.path != "/zipped_data_files/raman/":
            raise RruffRamanReadinessError("RRUFF index redirected away from pinned path")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise RruffRamanReadinessError(f"unexpected RRUFF index content type: {content_type}")
        payload = response.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            raise RruffRamanReadinessError("RRUFF index response exceeds configured ceiling")
        metadata = {
            "status": int(status),
            "final_url": final_url,
            "content_type": content_type,
            "last_modified": response.headers.get("Last-Modified"),
            "etag": response.headers.get("ETag"),
        }
    return payload, metadata


def _normalize_visible_text(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", html.unescape(" ".join(parts))).strip()


def _inspect_index(payload: bytes, candidate_archive: str) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RruffRamanReadinessError("RRUFF index is not UTF-8 HTML") from exc
    parser = _IndexParser()
    parser.feed(decoded)
    matches = [
        {"href": href, "text": text}
        for href, text in parser.links
        if text.strip() == candidate_archive or href.rstrip("/").endswith("/" + candidate_archive) or href == candidate_archive
    ]
    visible = _normalize_visible_text(parser.visible_parts)
    if len(matches) > 1:
        raise RruffRamanReadinessError("candidate archive appears more than once in RRUFF index")
    listed = len(matches) == 1
    listing_metadata: dict[str, str | None] = {
        "observed_last_modified_text": None,
        "observed_size_text": None,
    }
    if listed:
        escaped = re.escape(candidate_archive)
        match = re.search(
            rf"{escaped}\s+(\d{{4}}-\d{{2}}-\d{{2}}\s+\d{{2}}:\d{{2}})\s+([0-9.]+[KMGTP]?)\b",
            visible,
            flags=re.IGNORECASE,
        )
        if match:
            listing_metadata["observed_last_modified_text"] = match.group(1)
            listing_metadata["observed_size_text"] = match.group(2)
    return {
        "listed": listed,
        "link": matches[0] if listed else None,
        **listing_metadata,
    }


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    snapshot_path = _resolve_repo_path(config["source_claims_snapshot"])
    snapshot = _load_json(snapshot_path)
    source_claims = _validate_source_claims(snapshot)
    source_claims["snapshot_sha256"] = _sha256_file(snapshot_path)

    source = config["source_system"]
    limits = config["network_limits"]
    payload, http_metadata = _download_index(
        str(source["official_index_url"]),
        maximum_bytes=int(limits["maximum_index_response_bytes"]),
        timeout_seconds=int(limits["timeout_seconds"]),
        allowed_hosts=list(limits["allowed_hosts"]),
    )
    listing = _inspect_index(payload, str(source["candidate_archive"]))
    listing_status = "Supported" if listing["listed"] else "Unsupported"

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "rruff_raman_reference_readiness_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "source_claims": source_claims,
        "official_index": {
            **http_metadata,
            "response_bytes": len(payload),
            "response_sha256": _sha256_bytes(payload),
            "html_retained": False,
        },
        "candidate_archive": {
            "name": source["candidate_archive"],
            "listing_status": listing_status,
            "listed_link": listing["link"],
            "observed_last_modified_text": listing["observed_last_modified_text"],
            "observed_size_text": listing["observed_size_text"],
            "payload_bytes_read": 0,
            "archive_downloaded": False,
            "checksum_verified": False,
            "immutable_version_identity_established": False,
        },
        "evidence_assessment": {
            "rruff_project_identity": "Supported",
            "public_reference_library_access": "Supported",
            "candidate_bulk_archive_listing": listing_status,
            "reviewed_mineral_reference_context": "Diagnostic",
            "explicit_reuse_rights_for_automated_acquisition_and_redistribution": "Inconclusive",
            "candidate_archive_immutable_version_identity": "Inconclusive",
            "independent_peak_position_truth": "Inconclusive",
            "raman_external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "source_index_audit_ready": True,
            "automatic_acquisition_authorized": False,
            "candidate_archive_download_authorized": False,
            "spectrum_extraction_authorized": False,
            "raman_analyzer_execution_authorized": False,
            "parameter_tuning_authorized": False,
            "model_fit_or_training_authorized": False,
            "mineral_classification_claim_authorized": False,
            "vibrational_mode_assignment_claim_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "future_validation_target": config["validation_target"],
        "next_evidence": {
            "priority": 1,
            "requirement": "explicit_rruff_reuse_terms_and_immutable_candidate_spectrum_identity_before_any_spectrum_download",
            "why": (
                "RRUFF is a strong public reference-library candidate and the current official bulk listing is auditable, "
                "but public/free access is not treated as an explicit redistribution license, the bulk listing does not "
                "provide an immutable archive checksum/version identity, and mineral identity alone is not independent "
                "peak-position truth for the MCA Raman detector."
            ),
            "bulk_archive_download_required_now": False,
            "analyzer_execution_required_now": False,
        },
        "scientific_boundary": [
            "Only the official RRUFF Raman index HTML was requested; no ZIP or spectrum payload byte was read.",
            "The current listing establishes discoverability only and does not establish a stable immutable archive version.",
            "Free/public access is not silently converted into redistribution or derived-dataset permission.",
            "RRUFF mineral identity and quality-control context do not by themselves provide independent peak-position ground truth.",
            "No Raman analyzer execution, parameter tuning, mineral assignment, external-validation claim, or engineering decision is authorized."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise RruffRamanReadinessError(f"refusing to overwrite output: {output}")
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
            "Audit RRUFF Raman reference-source readiness from the official bulk index without "
            "downloading spectrum archives or running the Raman analyzer."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (RruffRamanReadinessError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
