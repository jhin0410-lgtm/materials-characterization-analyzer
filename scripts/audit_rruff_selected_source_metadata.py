from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RruffSelectedSourceMetadataError(RuntimeError):
    """Raised when the bounded selected-RRUFF metadata contract is violated."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RruffSelectedSourceMetadataError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise RruffSelectedSourceMetadataError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise RruffSelectedSourceMetadataError(f"JSON root must be an object: {resolved}")
    return payload


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RruffSelectedSourceMetadataError("repository path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RruffSelectedSourceMetadataError("configured repository path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise RruffSelectedSourceMetadataError("repository path resolved outside project root")
    return resolved


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_contract(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "predeclared_at",
        "selection_snapshot",
        "rruff_source_claims",
        "expected_selected_ids",
        "page_access",
        "authorized_operations",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise RruffSelectedSourceMetadataError("selected-source contract keys/schema mismatch")
    if config.get("case_id") != "rruff_selected_source_metadata_readiness":
        raise RruffSelectedSourceMetadataError("selected-source case identity drifted")

    selection_path = _resolve_repo_path(config.get("selection_snapshot"))
    claims_path = _resolve_repo_path(config.get("rruff_source_claims"))
    if selection_path.name != "verified_selection_snapshot.json":
        raise RruffSelectedSourceMetadataError("selection snapshot path drifted")
    if claims_path.name != "verified_source_claims_snapshot.json":
        raise RruffSelectedSourceMetadataError("RRUFF source claims path drifted")

    expected_ids = [
        "R060247",
        "R040073",
        "R110214",
        "R070417",
        "R040078",
        "R070307",
        "R040006",
        "X050046",
        "R060959",
        "R040040",
    ]
    if config.get("expected_selected_ids") != expected_ids:
        raise RruffSelectedSourceMetadataError("selected RRUFF ID list drifted")

    access = config.get("page_access")
    expected_access = {
        "legacy_url_template": "https://rruff.info/{rruff_id}",
        "allowed_hosts": ["rruff.info", "www.rruff.info", "rruff.net", "www.rruff.net"],
        "maximum_prefix_bytes_per_id": 524288,
        "timeout_seconds": 60,
    }
    if access != expected_access:
        raise RruffSelectedSourceMetadataError("RRUFF page access contract drifted")

    operations = config.get("authorized_operations")
    allowed_true = {
        "request_exact_selected_rruff_record_pages",
        "read_bounded_html_prefix_only",
        "parse_visible_record_page_text",
        "record_page_prefix_hash_and_final_url",
        "record_raman_section_presence",
        "record_processed_and_raw_download_label_presence",
        "record_broad_scan_instrument_text_and_wavelengths",
        "record_unoriented_or_oriented_text_presence",
    }
    if not isinstance(operations, dict):
        raise RruffSelectedSourceMetadataError("authorized_operations must be an object")
    if any(operations.get(key) is not True for key in allowed_true):
        raise RruffSelectedSourceMetadataError("required page-metadata operation is disabled")
    if any(value is not False for key, value in operations.items() if key not in allowed_true):
        raise RruffSelectedSourceMetadataError("spectrum/analyzer/replacement actions must remain disabled")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise RruffSelectedSourceMetadataError("all selected-source decision rules must be enabled")
    return config


def _validate_upstream(config: Mapping[str, Any]) -> dict[str, Any]:
    selection_path = _resolve_repo_path(config["selection_snapshot"])
    claims_path = _resolve_repo_path(config["rruff_source_claims"])
    selection = _load_json(selection_path)
    claims = _load_json(claims_path)

    if selection.get("selection_id") != "rruff-raman-target-blind-subset-v1":
        raise RruffSelectedSourceMetadataError("target-blind selection identity drifted")
    if selection.get("selected_ids") != config["expected_selected_ids"]:
        raise RruffSelectedSourceMetadataError("target-blind selected IDs drifted")
    boundary = selection.get("scientific_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("mca_raman_output_accessed") is not False:
        raise RruffSelectedSourceMetadataError("selection snapshot does not preserve target blindness")

    observations = claims.get("observations")
    assessment = claims.get("evidence_assessment")
    if not isinstance(observations, Mapping) or not isinstance(assessment, Mapping):
        raise RruffSelectedSourceMetadataError("RRUFF source claims are malformed")
    if observations.get("project_describes_data_as_free_access") is not True:
        raise RruffSelectedSourceMetadataError("RRUFF free-access source claim drifted")
    if assessment.get("explicit_reuse_rights_for_automated_acquisition_and_redistribution") != "Inconclusive":
        raise RruffSelectedSourceMetadataError("RRUFF reuse-rights boundary drifted")

    return {
        "selection_snapshot_sha256": _sha256_file(selection_path),
        "rruff_source_claims_sha256": _sha256_file(claims_path),
        "selected_id_count": len(config["expected_selected_ids"]),
        "reuse_rights_status": "Inconclusive",
    }


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(value))
    return re.sub(r"\s+", " ", normalized).strip()


def _visible_text(payload: bytes) -> tuple[str, list[str]]:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        decoded = payload.decode("latin-1")
    parser = _VisibleTextParser()
    parser.feed(decoded)
    parts = [_normalize_text(part) for part in parser.parts if _normalize_text(part)]
    return _normalize_text(" ".join(parts)), parts


def _fetch_page(rruff_id: str, access: Mapping[str, Any]) -> dict[str, Any]:
    url = str(access["legacy_url_template"]).format(rruff_id=rruff_id)
    parsed = urllib.parse.urlparse(url)
    allowed_hosts = set(access["allowed_hosts"])
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise RruffSelectedSourceMetadataError("constructed RRUFF page URL is outside trusted hosts")
    if parsed.path != f"/{rruff_id}":
        raise RruffSelectedSourceMetadataError("constructed RRUFF page URL path drifted")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "materials-characterization-analyzer-rruff-source-metadata/1.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
        },
    )
    prefix_limit = int(access["maximum_prefix_bytes_per_id"])
    try:
        with urllib.request.urlopen(request, timeout=int(access["timeout_seconds"])) as response:
            status = getattr(response, "status", None) or response.getcode()
            final_url = response.geturl()
            final = urllib.parse.urlparse(final_url)
            if final.scheme != "https" or final.hostname not in allowed_hosts:
                raise RruffSelectedSourceMetadataError(
                    f"RRUFF page redirected outside trusted hosts: {final.hostname}"
                )
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise RruffSelectedSourceMetadataError(
                    f"RRUFF page returned unexpected content type: {content_type}"
                )
            reported_length = response.headers.get("Content-Length")
            payload = response.read(prefix_limit)
        return {
            "request_url": url,
            "status": int(status),
            "final_url": final_url,
            "content_type": content_type,
            "payload": payload,
            "prefix_limit_bytes": prefix_limit,
            "reported_content_length": reported_length,
            "response_prefix_only": True,
            "network_error": None,
        }
    except urllib.error.HTTPError as exc:
        return {
            "request_url": url,
            "status": int(exc.code),
            "final_url": exc.geturl() or url,
            "content_type": None,
            "payload": b"",
            "prefix_limit_bytes": prefix_limit,
            "reported_content_length": None,
            "response_prefix_only": True,
            "network_error": f"HTTPError:{exc.code}",
        }
    except urllib.error.URLError as exc:
        return {
            "request_url": url,
            "status": None,
            "final_url": None,
            "content_type": None,
            "payload": b"",
            "prefix_limit_bytes": prefix_limit,
            "reported_content_length": None,
            "response_prefix_only": True,
            "network_error": f"URLError:{type(exc.reason).__name__}",
        }


def _inspect_page(rruff_id: str, fetched: Mapping[str, Any]) -> dict[str, Any]:
    payload = fetched["payload"]
    base = {
        "rruff_id": rruff_id,
        "request_url": fetched["request_url"],
        "status": fetched["status"],
        "final_url": fetched["final_url"],
        "content_type": fetched["content_type"],
        "prefix_limit_bytes": fetched["prefix_limit_bytes"],
        "reported_content_length": fetched["reported_content_length"],
        "response_prefix_only": fetched["response_prefix_only"],
        "network_error": fetched["network_error"],
        "full_page_read": False,
        "html_retained": False,
    }
    if not isinstance(payload, bytes) or not payload:
        return {
            **base,
            "response_prefix_bytes": 0,
            "response_prefix_sha256": None,
            "record_identity_present": False,
            "raman_section_present": False,
            "broad_scan_section_present": False,
            "processed_download_label_count": 0,
            "raw_download_label_count": 0,
            "wavelengths_nm": [],
            "unoriented_text_present": False,
            "oriented_text_present": False,
            "instrument_text_fragments": [],
            "raman_source_discoverability": "Inconclusive",
            "acquisition_metadata_readiness": "Inconclusive",
            "exact_annotation_to_spectrum_binding": "Inconclusive",
        }

    text, parts = _visible_text(payload)
    folded = text.casefold()
    wavelengths = sorted(
        {
            int(match)
            for match in re.findall(r"(?<!\d)(\d{3,4})\s*nm\b", folded)
            if 300 <= int(match) <= 2000
        }
    )
    instrument_fragments = [
        part[:300]
        for part in parts
        if "instrument settings" in part.casefold()
    ][:20]
    record_identity = rruff_id.casefold() in folded
    raman_section = "raman spectrum" in folded
    broad_scan = "broad scan with spectral artifacts" in folded
    processed_count = folded.count("raman data (processed)")
    raw_count = folded.count("raman data (raw)")
    source_discoverability = (
        "Supported"
        if record_identity and raman_section and (processed_count > 0 or raw_count > 0)
        else "Inconclusive"
    )
    acquisition_readiness = (
        "Diagnostic"
        if source_discoverability == "Supported" and (wavelengths or instrument_fragments)
        else "Inconclusive"
    )
    return {
        **base,
        "response_prefix_bytes": len(payload),
        "response_prefix_sha256": _sha256_bytes(payload),
        "record_identity_present": record_identity,
        "raman_section_present": raman_section,
        "broad_scan_section_present": broad_scan,
        "processed_download_label_count": processed_count,
        "raw_download_label_count": raw_count,
        "wavelengths_nm": wavelengths,
        "unoriented_text_present": "unoriented" in folded or "unorientated" in folded,
        "oriented_text_present": "oriented" in folded or "orientated" in folded,
        "instrument_text_fragments": instrument_fragments,
        "raman_source_discoverability": source_discoverability,
        "acquisition_metadata_readiness": acquisition_readiness,
        "exact_annotation_to_spectrum_binding": "Inconclusive",
    }


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_contract(_load_json(config_resolved))
    upstream = _validate_upstream(config)
    records = [
        _inspect_page(rruff_id, _fetch_page(rruff_id, config["page_access"]))
        for rruff_id in config["expected_selected_ids"]
    ]

    supported = sum(record["raman_source_discoverability"] == "Supported" for record in records)
    diagnostic_metadata = sum(record["acquisition_metadata_readiness"] == "Diagnostic" for record in records)
    network_failures = sum(record["network_error"] is not None for record in records)
    multiple_wavelength_ids = [
        record["rruff_id"] for record in records if len(record["wavelengths_nm"]) > 1
    ]
    likely_multiple_spectrum_ids = [
        record["rruff_id"]
        for record in records
        if record["processed_download_label_count"] + record["raw_download_label_count"] > 2
    ]
    prefix_bytes_total = sum(int(record["response_prefix_bytes"]) for record in records)

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "execution_status": "selected_rruff_source_metadata_audit_completed",
        "contract_sha256": _sha256_file(config_resolved),
        "upstream_evidence": upstream,
        "selected_ids": list(config["expected_selected_ids"]),
        "records": records,
        "summary": {
            "selected_id_count": len(records),
            "raman_source_discoverability_supported_count": supported,
            "acquisition_metadata_diagnostic_count": diagnostic_metadata,
            "network_failure_count": network_failures,
            "ids_with_multiple_visible_wavelengths": multiple_wavelength_ids,
            "ids_with_multiple_raman_download_labels": likely_multiple_spectrum_ids,
            "record_page_prefix_bytes_read_total": prefix_bytes_total,
            "full_record_pages_read": 0,
            "spectrum_payload_bytes_read": 0,
        },
        "evidence_assessment": {
            "target_blind_selection_identity": "Supported",
            "selected_record_page_prefix_inventory": "Supported" if network_failures == 0 else "Diagnostic",
            "raman_source_discoverability": "Supported" if supported == len(records) else "Diagnostic",
            "acquisition_metadata_context": "Diagnostic" if diagnostic_metadata else "Inconclusive",
            "exact_annotation_to_source_spectrum_binding": "Inconclusive",
            "rruff_spectrum_redistribution_rights": "Inconclusive",
            "raman_peak_localization_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "selected_source_metadata_audit_ready": True,
            "selected_id_replacement_authorized": False,
            "rruff_spectrum_download_authorized": False,
            "raman_analyzer_execution_authorized": False,
            "matching_tolerance_selection_authorized": False,
            "parameter_tuning_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": {
            "requirement": "predeclare_exact_candidate_spectrum_binding_rule_using_source_metadata_and_frozen_annotation_fields_before_any_spectrum_payload_download",
            "why": (
                "Bounded record-page prefixes can establish source discoverability and some acquisition context, "
                "but they do not prove the exact spectrum underlying each frozen published annotation. Multiple "
                "orientation, raw/processed, or wavelength candidates must remain explicit ambiguity until a separate mapping rule is frozen."
            ),
        },
        "scientific_boundary": [
            "Only the first 512 KiB of each selected RRUFF HTML record page was read; no full-page fallback was used.",
            "Missing metadata outside the bounded prefix remains Inconclusive rather than triggering additional page or spectrum access.",
            "No Raman data download link was followed and spectrum payload bytes read equals zero.",
            "Visible raw/processed labels and instrument text establish discoverability, not exact annotation-to-spectrum identity.",
            "No selected ID was replaced, no MCA Raman output was viewed, and no matching tolerance or parameter was tuned.",
            "RRUFF free-access/download statements are not silently converted into permission to commit or redistribute raw spectra."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise RruffSelectedSourceMetadataError(f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit bounded-prefix RRUFF Raman source metadata for the frozen target-blind subset."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (RruffSelectedSourceMetadataError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
