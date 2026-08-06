#!/usr/bin/env python3
"""Audit Mendeley lunar source metadata and fail closed on OAuth-protected files."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_mendeley_lunar_tem_saed as engine

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
_MAX_RESPONSE_BYTES = 65_536
_MAX_LANDING_BYTES = 2_000_000
_STATUS = (
    "mendeley_public_landing_metadata_verified_but_file_inventory_and_"
    "header_audit_require_oauth_authorization"
)


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
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def visible_text(raw_html: bytes) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw_html.decode("utf-8", errors="replace"))
    return html.unescape(parser.text())


def _trusted_landing_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "data.mendeley.com":
        raise engine.MendeleyAuditError(f"untrusted Mendeley landing URL: {url}")


def fetch_public_landing(source: Mapping[str, Any]) -> dict[str, Any]:
    url = str(source["landing_url"])
    _trusted_landing_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != "data.mendeley.com":
            raise engine.MendeleyAuditError(
                f"Mendeley landing page redirected to an untrusted host: {response.geturl()}"
            )
        raw = response.read(_MAX_LANDING_BYTES + 1)
        if len(raw) > _MAX_LANDING_BYTES:
            raise engine.MendeleyAuditError("Mendeley landing HTML exceeded bounded size")
        content_type = str(response.headers.get("Content-Type", ""))
        if "html" not in content_type.casefold() and not raw.lstrip().lower().startswith(
            (b"<!doctype html", b"<html")
        ):
            raise engine.MendeleyAuditError("Mendeley landing response was not HTML")
        text = visible_text(raw)
        folded = text.casefold()
        title_term = str(source["expected_title_substring"])
        if title_term.casefold() not in folded:
            raise engine.MendeleyAuditError(
                f"public landing title mismatch for {source['dataset_id']}"
            )
        doi = str(source["doi"])
        if doi.casefold() not in folded:
            raise engine.MendeleyAuditError(
                f"public landing DOI mismatch for {source['dataset_id']}"
            )
        version_patterns = (
            f"version {source['version']}",
            f"v{source['version']}",
        )
        if not any(pattern.casefold() in folded for pattern in version_patterns):
            raise engine.MendeleyAuditError(
                f"public landing version mismatch for {source['dataset_id']}"
            )
        missing_description = [
            term
            for term in source["expected_description_terms"]
            if str(term).casefold() not in folded
        ]
        if missing_description:
            raise engine.MendeleyAuditError(
                f"public landing lost description terms for {source['dataset_id']}: "
                f"{missing_description}"
            )
        if not any(
            str(term).casefold() in folded
            for term in source["expected_license_terms"]
        ):
            raise engine.MendeleyAuditError(
                f"public landing licence mismatch for {source['dataset_id']}"
            )
        return {
            "status_code": int(getattr(response, "status", response.getcode())),
            "content_type": content_type,
            "response_bytes": len(raw),
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "final_host": final.hostname,
            "final_path": final.path,
            "title_term_verified": title_term,
            "doi_verified": doi,
            "version_verified": int(source["version"]),
            "description_terms_verified": list(source["expected_description_terms"]),
            "license_terms_matched": [
                str(term)
                for term in source["expected_license_terms"]
                if str(term).casefold() in folded
            ],
            "visible_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "visible_text_bytes": len(text.encode("utf-8")),
            "files_section_present": bool(
                re.search(r"\bfiles\b", text, flags=re.IGNORECASE)
            ),
            "download_all_control_present": "download all" in folded,
        }


def _api_endpoints(source: Mapping[str, Any]) -> list[tuple[str, str]]:
    dataset = urllib.parse.quote(str(source["dataset_id"]), safe="")
    version = int(source["version"])
    query = urllib.parse.urlencode({"version": version})
    return [
        ("dataset_metadata", f"https://api.data.mendeley.com/datasets/{dataset}?{query}"),
        ("dataset_snapshot", f"https://api.data.mendeley.com/datasets/{dataset}/snapshot?{query}"),
        ("dataset_versions", f"https://api.data.mendeley.com/datasets/{dataset}/versions"),
        ("public_files", f"https://api.data.mendeley.com/datasets/publics/{dataset}/files?{query}&%24start=0&%24limit=100"),
        ("public_folders", f"https://api.data.mendeley.com/datasets/publics/{dataset}/folders?{query}"),
        ("zip_metadata", f"https://api.data.mendeley.com/datasets/{dataset}/zip?{query}"),
        ("zip_download_redirect", f"https://api.data.mendeley.com/datasets/{dataset}/zip/file_downloaded?{query}"),
    ]


def _classification(status: int, content_type: str, sample: bytes) -> str:
    if status == 401:
        return "oauth_authorization_required"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    folded_type = content_type.casefold()
    lowered = sample.lstrip().lower()
    if "json" in folded_type or lowered.startswith((b"{", b"[")):
        return "json_response"
    if "html" in folded_type or lowered.startswith((b"<!doctype html", b"<html")):
        return "html_response"
    if status in {200, 206, 307}:
        return "other_success_response"
    return "other_error_response"


def probe_api(label: str, url: str) -> dict[str, Any]:
    engine._trusted_api_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": engine.DATASET_ACCEPT,
            "User-Agent": engine.USER_AGENT,
            "Range": f"bytes=0-{_MAX_RESPONSE_BYTES - 1}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            sample = response.read(_MAX_RESPONSE_BYTES)
            status = int(getattr(response, "status", response.getcode()))
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != "api.data.mendeley.com":
                raise engine.MendeleyAuditError(
                    f"API probe redirected to an untrusted host: {response.geturl()}"
                )
            content_type = str(response.headers.get("Content-Type", ""))
            return {
                "label": label,
                "requested_path": urllib.parse.urlsplit(url).path,
                "status_code": status,
                "content_type": content_type,
                "content_length_header": str(response.headers.get("Content-Length", "")),
                "sampled_bytes": len(sample),
                "sample_sha256": hashlib.sha256(sample).hexdigest(),
                "classification": _classification(status, content_type, sample),
                "final_host": final.hostname,
                "final_path": final.path,
            }
    except urllib.error.HTTPError as exc:
        sample = exc.read(_MAX_RESPONSE_BYTES)
        final = urllib.parse.urlsplit(exc.geturl())
        if final.scheme != "https" or final.hostname != "api.data.mendeley.com":
            raise engine.MendeleyAuditError(
                f"API error response used an untrusted host: {exc.geturl()}"
            )
        content_type = str(exc.headers.get("Content-Type", ""))
        return {
            "label": label,
            "requested_path": urllib.parse.urlsplit(url).path,
            "status_code": int(exc.code),
            "content_type": content_type,
            "content_length_header": str(exc.headers.get("Content-Length", "")),
            "sampled_bytes": len(sample),
            "sample_sha256": hashlib.sha256(sample).hexdigest(),
            "classification": _classification(int(exc.code), content_type, sample),
            "final_host": final.hostname,
            "final_path": final.path,
        }


def run_access_audit(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = engine.load_config(config_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise engine.MendeleyAuditError("output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for source in config["sources"]:
        landing = fetch_public_landing(source)
        dataset_attempts = [
            {"dataset_id": source["dataset_id"], **probe_api(label, url)}
            for label, url in _api_endpoints(source)
        ]
        attempts.extend(dataset_attempts)
        datasets.append(
            {
                "dataset_id": source["dataset_id"],
                "version": int(source["version"]),
                "doi": source["doi"],
                "landing_url": source["landing_url"],
                "material_scope": source["material_scope"],
                "landing_evidence": landing,
                "api_attempt_count": len(dataset_attempts),
                "api_classifications": sorted(
                    {item["classification"] for item in dataset_attempts}
                ),
                "source_quality_flags": source["source_quality_flags"],
            }
        )

    all_oauth = all(
        item["classification"] == "oauth_authorization_required"
        for item in attempts
    )
    summary = {
        "status": _STATUS,
        "evidence_level": "Diagnostic",
        "dataset_count": len(datasets),
        "datasets": datasets,
        "api_attempt_count": len(attempts),
        "all_documented_api_endpoints_require_oauth_in_current_runner": all_oauth,
        "evidence_assessment": {
            "public_landing_title_doi_version_description_and_license": "Supported",
            "public_landing_files_section_and_download_control_presence": "Supported",
            "anonymous_api_metadata_access_from_github_runner": (
                "Unsupported" if all_oauth else "Partial_or_changed"
            ),
            "public_file_uuid_size_sha256_and_folder_inventory": "Inconclusive",
            "native_microscopy_container_presence": "Inconclusive",
            "raster_export_presence": "Inconclusive",
            "detector_native_intensity_preservation": "Inconclusive",
            "pattern_centre_and_reciprocal_calibration": "Inconclusive",
            "sample_acquisition_lineage_and_independence": "Inconclusive",
        },
        "readiness": {
            "file_inventory_ready": False,
            "bounded_header_audit_ready": False,
            "cross_material_file_interoperability_diagnostic_ready": False,
            "calibrated_saed_validation_ready": False,
            "external_scientific_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "processing": {
            "source_files_retained": False,
            "api_response_bodies_retained": False,
            "landing_html_retained": False,
            "pixel_arrays_exported": False,
            "image_preprocessing_performed": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "parameter_tuning_performed": False,
            "model_retraining_performed": False,
            "phase_indexing_performed": False,
        },
        "next_required_evidence": [
            "authorized OAuth2 access to the documented public dataset metadata and files endpoints, or an official anonymous file-inventory export",
            "file UUID, declared byte count, SHA-256, folder identity and download URL for every TEM/HRTEM/SAED candidate",
            "a rerun of the bounded magic-header audit before any analyzer use",
        ],
    }

    summary_path = output_dir / "mendeley_lunar_access_audit_summary.json"
    attempts_path = output_dir / "mendeley_lunar_api_access_attempts.json"
    report_path = output_dir / "mendeley_lunar_access_audit_report.md"
    manifest_path = output_dir / "mendeley_lunar_access_audit_manifest.json"
    engine._json_dump(summary_path, summary)
    engine._json_dump(attempts_path, attempts)
    report_path.write_text(
        f"""# Mendeley lunar TEM/SAED access audit

## Result

- Status: `{_STATUS}`
- Evidence level: **Diagnostic**
- Datasets: `{len(datasets)}`
- Documented API probes: `{len(attempts)}`
- Anonymous file inventory ready: **no**
- Bounded file-header audit ready: **no**

## Supported

Both public landing pages expose the configured title, DOI, version, TEM/HRTEM/SAED
description terms, Files section, Download All control and CC BY 4.0 licence.

## Access limitation

The documented dataset metadata, snapshot, versions, public files, public folders,
ZIP metadata and ZIP-download redirect endpoints were probed without credentials.
Their bounded response status, content type and body hash are recorded, but response
bodies are not retained. OAuth-required responses are not interpreted as file
inventories or source data, and no authentication or access-control bypass is used.

## Scientific boundary

Because file UUIDs, sizes, SHA-256 values and headers were not obtained, this audit
does not establish DM3/DM4, TIFF/BMP or other source representations. Original-data
wording remains a source claim. Calibration, lineage, external validation, phase
indexing, analyzer inference, tuning, retraining and engineering use remain closed.
""",
        encoding="utf-8",
    )
    engine._json_dump(
        manifest_path,
        engine._artifact_manifest(
            output_dir, [summary_path, attempts_path, report_path]
        ),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run_access_audit(args.config, args.output),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
