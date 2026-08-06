#!/usr/bin/env python3
"""Run the TiSe2 audit and preserve fail-closed Dryad access evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_dryad_tise2_saed_hrtem as engine

_ORIGINAL_RESOLVE_SOURCE = engine.resolve_source
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
_DATASET_REFERER = (
    "https://datadryad.org/dataset/doi%3A10.5061/dryad.6djh9w1hw"
)
_MAX_PROBE_BYTES = 65_536
_ACCESS_STATUS = (
    "dryad_metadata_verified_but_anonymous_archive_download_not_"
    "reproducible_from_github_runner"
)


class DryadArchiveAccessBlocked(engine.AuditError):
    """Raised when a download endpoint returns an auth/interstitial response."""

    def __init__(self, message: str, attempt: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.attempt = dict(attempt)


def record_id_with_link_fallback(record: Mapping[str, Any]) -> int | None:
    """Resolve a Dryad file ID from a scalar field or a pinned file/download link."""
    for key in ("id", "fileId", "file_id"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    links = record.get("_links")
    if isinstance(links, Mapping):
        for name in ("self", "stash:download", "download"):
            value = links.get(name)
            href = value.get("href") if isinstance(value, Mapping) else value
            if not isinstance(href, str):
                continue
            parsed = urllib.parse.urlsplit(
                urllib.parse.urljoin("https://datadryad.org", href)
            )
            if parsed.scheme != "https" or parsed.hostname != "datadryad.org":
                raise engine.AuditError(f"Dryad file link escaped pinned host: {href}")
            token = parsed.path.rstrip("/").rsplit("/", 1)[-1]
            if token.isdigit():
                return int(token)
    return None


def public_file_stream_url(file_id: int, *, stash_prefix: bool = True) -> str:
    if not isinstance(file_id, int) or file_id <= 0:
        raise engine.AuditError("Dryad public file-stream ID must be positive")
    prefix = "/stash" if stash_prefix else ""
    return f"https://datadryad.org{prefix}/downloads/file_stream/{file_id}"


def resolve_source_with_public_stream(config: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve API identity checks, then select Dryad's anonymous public stream."""
    result = _ORIGINAL_RESOLVE_SOURCE(config)
    result["api_download_url"] = result["download_url"]
    file_id = int(config["source"]["primary_file_id"])
    result["download_url"] = public_file_stream_url(file_id)
    return result


def _trusted_final_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    trusted = host == "datadryad.org" or host.endswith(".amazonaws.com")
    if parsed.scheme != "https" or not trusted:
        raise engine.AuditError(f"Dryad response used an untrusted URL: {url}")
    return host, parsed.path


def _classification(status: int, content_type: str, sample: bytes) -> str:
    lower_type = content_type.casefold()
    lower_sample = sample[:1024].lstrip().lower()
    if status == 401:
        return "authentication_required"
    if status == 403:
        return "forbidden_to_automated_runner"
    if "html" in lower_type or lower_sample.startswith((b"<!doctype html", b"<html")):
        return "html_interstitial_not_archive"
    if status in {200, 206} and (
        "zip" in lower_type or sample.startswith(b"PK\x03\x04")
    ):
        return "archive_bytes_available"
    return "unexpected_nonarchive_response"


def _attempt_record(
    *,
    label: str,
    requested_url: str,
    final_url: str,
    status: int,
    headers: Mapping[str, str],
    sample: bytes,
) -> dict[str, Any]:
    final_host, final_path = _trusted_final_url(final_url)
    content_type = str(headers.get("Content-Type", ""))
    content_length = str(headers.get("Content-Length", ""))
    return {
        "label": label,
        "requested_host": urllib.parse.urlsplit(requested_url).hostname,
        "requested_path": urllib.parse.urlsplit(requested_url).path,
        "final_host": final_host,
        "final_path": final_path,
        "status_code": status,
        "content_type": content_type,
        "content_length_header": content_length,
        "sampled_bytes": len(sample),
        "sample_sha256": hashlib.sha256(sample).hexdigest(),
        "classification": _classification(status, content_type, sample),
    }


def _browser_headers(*, range_probe: bool) -> dict[str, str]:
    headers = {
        "User-Agent": _BROWSER_USER_AGENT,
        "Referer": _DATASET_REFERER,
        "Accept": "application/octet-stream,application/zip,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if range_probe:
        headers["Range"] = f"bytes=0-{_MAX_PROBE_BYTES - 1}"
    return headers


def probe_access(label: str, url: str) -> dict[str, Any]:
    """Probe one endpoint without downloading more than 64 KiB."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "datadryad.org":
        raise engine.AuditError("access probe escaped pinned Dryad host")
    request = urllib.request.Request(url, headers=_browser_headers(range_probe=True))
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            sample = response.read(_MAX_PROBE_BYTES)
            status = int(getattr(response, "status", response.getcode()))
            return _attempt_record(
                label=label,
                requested_url=url,
                final_url=response.geturl(),
                status=status,
                headers=response.headers,
                sample=sample,
            )
    except urllib.error.HTTPError as exc:
        sample = exc.read(_MAX_PROBE_BYTES)
        return _attempt_record(
            label=label,
            requested_url=url,
            final_url=exc.geturl(),
            status=int(exc.code),
            headers=exc.headers,
            sample=sample,
        )


def stream_download_with_browser_headers(
    url: str, destination: Path, expected_bytes: int
) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "datadryad.org":
        raise engine.AuditError("download URL escaped pinned Dryad host")
    request = urllib.request.Request(url, headers=_browser_headers(range_probe=False))
    try:
        response = urllib.request.urlopen(request, timeout=1800)
    except urllib.error.HTTPError as exc:
        sample = exc.read(_MAX_PROBE_BYTES)
        attempt = _attempt_record(
            label="selected_public_stream",
            requested_url=url,
            final_url=exc.geturl(),
            status=int(exc.code),
            headers=exc.headers,
            sample=sample,
        )
        raise DryadArchiveAccessBlocked(
            f"Dryad public stream returned HTTP {exc.code}", attempt
        ) from exc

    with response:
        final_host, _ = _trusted_final_url(response.geturl())
        content_type = str(response.headers.get("Content-Type", ""))
        initial = response.read(min(_MAX_PROBE_BYTES, expected_bytes))
        classification = _classification(
            int(getattr(response, "status", response.getcode())), content_type, initial
        )
        if classification != "archive_bytes_available":
            attempt = _attempt_record(
                label="selected_public_stream",
                requested_url=url,
                final_url=response.geturl(),
                status=int(getattr(response, "status", response.getcode())),
                headers=response.headers,
                sample=initial,
            )
            raise DryadArchiveAccessBlocked(
                "Dryad public stream returned a non-archive response", attempt
            )

        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        count = 0
        with destination.open("wb") as out:
            for chunk in (initial,):
                count += len(chunk)
                out.write(chunk)
                md5.update(chunk)
                sha256.update(chunk)
            while chunk := response.read(8 * 1024 * 1024):
                count += len(chunk)
                if count > expected_bytes:
                    raise engine.AuditError("download exceeded Dryad-declared size")
                out.write(chunk)
                md5.update(chunk)
                sha256.update(chunk)
        if count != expected_bytes:
            attempt = {
                "label": "selected_public_stream",
                "requested_host": parsed.hostname,
                "requested_path": parsed.path,
                "final_host": final_host,
                "final_path": urllib.parse.urlsplit(response.geturl()).path,
                "status_code": int(getattr(response, "status", response.getcode())),
                "content_type": content_type,
                "content_length_header": str(response.headers.get("Content-Length", "")),
                "sampled_bytes": min(count, _MAX_PROBE_BYTES),
                "sample_sha256": hashlib.sha256(initial).hexdigest(),
                "classification": "truncated_or_interstitial_response",
                "observed_total_bytes": count,
            }
            destination.unlink(missing_ok=True)
            raise DryadArchiveAccessBlocked(
                f"Dryad response byte count {count} did not match {expected_bytes}",
                attempt,
            )
        return {"bytes": count, "md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def _write_access_evidence(
    config: Mapping[str, Any],
    source: Mapping[str, Any],
    output_dir: Path,
    initial_attempt: Mapping[str, Any],
) -> dict[str, Any]:
    file_id = int(config["source"]["primary_file_id"])
    endpoints = [
        ("api_declared_download", str(source["api_download_url"])),
        ("legacy_public_stream", public_file_stream_url(file_id, stash_prefix=False)),
        ("stash_public_stream", public_file_stream_url(file_id, stash_prefix=True)),
    ]
    attempts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for attempt in [dict(initial_attempt)]:
        key = (str(attempt.get("requested_path")), str(attempt.get("classification")))
        seen.add(key)
        attempts.append(attempt)
    for label, url in endpoints:
        attempt = probe_access(label, url)
        key = (str(attempt.get("requested_path")), str(attempt.get("classification")))
        if key not in seen:
            seen.add(key)
            attempts.append(attempt)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": _ACCESS_STATUS,
        "evidence_level": "Diagnostic",
        "source": {
            "repository": config["source"]["repository"],
            "doi": config["source"]["doi"],
            "record_url": config["source"]["record_url"],
            "title": source["title_observed"],
            "license": source["license_observed"],
            "version_url": source["version_url"],
            "dataset_url": source["dataset_url"],
            "primary_file_id": file_id,
            "primary_filename": config["source"]["primary_filename"],
            "dryad_declared_bytes": source["expected_bytes"],
            "upstream_digests": source["upstream_digests"],
        },
        "access_attempt_count": len(attempts),
        "access_classifications": sorted(
            {str(item["classification"]) for item in attempts}
        ),
        "evidence_assessment": {
            "dryad_dataset_identity": "Supported",
            "file_version_binding": "Supported",
            "reuse_authorization": "Supported",
            "anonymous_archive_download_from_github_runner": "Unsupported",
            "archive_checksum_and_member_integrity": "Inconclusive",
            "experimental_simulation_member_separation": "Inconclusive_until_archive_access",
            "reciprocal_calibration_and_pattern_centre": "Inconclusive",
        },
        "readiness": {
            "archive_inventory_ready": False,
            "cross_material_software_diagnostic_ready": False,
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
            "parameter_tuning_performed": False,
            "model_retraining_performed": False,
            "phase_indexing_performed": False,
        },
        "next_required_evidence": [
            "a checksum-verifiable copy of Data_TiSe2.zip obtained through an authorized manual or repository-supported download path",
            "the exact Dryad file/version binding retained alongside the downloaded archive",
            "a rerun of the fail-closed ZIP/member audit before any analyzer use",
        ],
    }
    summary_path = output_dir / "dryad_tise2_access_audit_summary.json"
    attempts_path = output_dir / "dryad_tise2_access_attempts.json"
    report_path = output_dir / "dryad_tise2_access_audit_report.md"
    manifest_path = output_dir / "dryad_tise2_access_audit_manifest.json"
    engine.write_json(summary_path, summary)
    engine.write_json(attempts_path, attempts)
    report_path.write_text(
        f"""# Dryad TiSe2 archive-access audit

## Result

- Status: `{_ACCESS_STATUS}`
- Evidence level: **Diagnostic**
- DOI: `{config['source']['doi']}`
- File: `{config['source']['primary_filename']}`
- Dryad-declared bytes: `{source['expected_bytes']}`
- Access attempts: `{len(attempts)}`
- Anonymous archive download from GitHub runner: **unsupported**
- Archive integrity and member inventory: **inconclusive**

## Supported

The official Dryad API binds file ID `{file_id}` to the expected source version,
dataset DOI, title, licence and declared file size. These metadata checks completed
without using an inferred filename or an untrusted host.

## Access limitation

The API-declared endpoint and two public file-stream forms did not yield the declared
ZIP bytes to the GitHub-hosted runner. Responses were preserved only as bounded
status/header/body-hash evidence; HTML or authorization responses were not treated as
the archive. No authentication, cookie replay or access-control bypass was attempted.

## Scientific boundary

Because the archive bytes were not obtained, no ZIP member, TIFF header, experimental
folder or simulated folder has been independently inspected in this run. The source
remains a high-priority candidate, but calibrated-SAED validation, phase indexing,
model tuning, retraining and engineering claims remain unauthorized.
""",
        encoding="utf-8",
    )
    engine.write_json(
        manifest_path,
        engine.artifact_manifest(
            output_dir, [summary_path, attempts_path, report_path]
        ),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = engine.load_config(args.config)

    original_record_id = engine._record_id
    original_resolve = engine.resolve_source
    original_download = engine.stream_download
    engine._record_id = record_id_with_link_fallback
    engine.resolve_source = resolve_source_with_public_stream
    engine.stream_download = stream_download_with_browser_headers
    try:
        try:
            summary = engine.run(args.config, args.output)
        except DryadArchiveAccessBlocked as exc:
            source = resolve_source_with_public_stream(config)
            summary = _write_access_evidence(
                config, source, args.output, exc.attempt
            )
    finally:
        engine._record_id = original_record_id
        engine.resolve_source = original_resolve
        engine.stream_download = original_download
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
