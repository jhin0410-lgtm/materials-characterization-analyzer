#!/usr/bin/env python3
"""Run the TiSe2 audit with Dryad public-download compatibility."""
from __future__ import annotations

import hashlib
import sys
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


def public_file_stream_url(file_id: int) -> str:
    if not isinstance(file_id, int) or file_id <= 0:
        raise engine.AuditError("Dryad public file-stream ID must be positive")
    return f"https://datadryad.org/stash/downloads/file_stream/{file_id}"


def resolve_source_with_public_stream(config: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve API identity checks, then select Dryad's anonymous public stream."""
    result = _ORIGINAL_RESOLVE_SOURCE(config)
    result["api_download_url"] = result["download_url"]
    file_id = int(config["source"]["primary_file_id"])
    result["download_url"] = public_file_stream_url(file_id)
    return result


def stream_download_with_browser_headers(
    url: str, destination: Path, expected_bytes: int
) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "datadryad.org":
        raise engine.AuditError("download URL escaped pinned Dryad host")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _BROWSER_USER_AGENT,
            "Referer": _DATASET_REFERER,
            "Accept": "application/octet-stream,application/zip,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    count = 0
    with urllib.request.urlopen(request, timeout=1800) as response, destination.open("wb") as out:
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != "https" or not (
            final.hostname == "datadryad.org"
            or (isinstance(final.hostname, str) and final.hostname.endswith(".amazonaws.com"))
        ):
            raise engine.AuditError(
                f"Dryad public stream redirected to an untrusted host: {response.geturl()}"
            )
        while chunk := response.read(8 * 1024 * 1024):
            count += len(chunk)
            if count > expected_bytes:
                raise engine.AuditError("download exceeded Dryad-declared size")
            out.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    if count != expected_bytes:
        raise engine.AuditError(
            f"download byte mismatch: {count} != {expected_bytes}"
        )
    return {"bytes": count, "md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def main() -> int:
    original_record_id = engine._record_id
    original_resolve = engine.resolve_source
    original_download = engine.stream_download
    engine._record_id = record_id_with_link_fallback
    engine.resolve_source = resolve_source_with_public_stream
    engine.stream_download = stream_download_with_browser_headers
    try:
        return engine.main()
    finally:
        engine._record_id = original_record_id
        engine.resolve_source = original_resolve
        engine.stream_download = original_download


if __name__ == "__main__":
    raise SystemExit(main())
