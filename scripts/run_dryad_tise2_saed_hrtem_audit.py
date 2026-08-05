#!/usr/bin/env python3
"""Run the TiSe2 audit with Dryad link-encoded file-ID compatibility."""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_dryad_tise2_saed_hrtem as engine


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


def main() -> int:
    original = engine._record_id
    engine._record_id = record_id_with_link_fallback
    try:
        return engine.main()
    finally:
        engine._record_id = original


if __name__ == "__main__":
    raise SystemExit(main())
