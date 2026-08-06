#!/usr/bin/env python3
"""Run the TiSe2 audit with Dryad public-download compatibility."""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_dryad_tise2_saed_hrtem as engine

_ORIGINAL_RESOLVE_SOURCE = engine.resolve_source


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
    return f"https://datadryad.org/downloads/file_stream/{file_id}"


def resolve_source_with_public_stream(config: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve API identity checks, then select Dryad's anonymous public stream."""
    result = _ORIGINAL_RESOLVE_SOURCE(config)
    api_download_url = result["download_url"]
    file_id = int(config["source"]["primary_file_id"])
    result["api_download_url"] = api_download_url
    result["download_url"] = public_file_stream_url(file_id)
    return result


def main() -> int:
    original_record_id = engine._record_id
    original_resolve = engine.resolve_source
    engine._record_id = record_id_with_link_fallback
    engine.resolve_source = resolve_source_with_public_stream
    try:
        return engine.main()
    finally:
        engine._record_id = original_record_id
        engine.resolve_source = original_resolve


if __name__ == "__main__":
    raise SystemExit(main())
