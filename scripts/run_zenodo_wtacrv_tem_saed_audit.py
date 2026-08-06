#!/usr/bin/env python3
"""Run the W-Ta-Cr-V audit with bounded file-header reads."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_zenodo_wtacrv_tem_saed as engine


def bounded_header(path: Path) -> dict[str, Any]:
    """Read at most 32 bytes instead of materializing the selected file."""
    with path.open("rb") as handle:
        header = handle.read(32)
    result: dict[str, Any] = {
        "header_bytes": len(header),
        "header_hex": header[:16].hex(),
    }
    if path.suffix.casefold() in {".dm3", ".dm4"} and len(header) >= 12:
        result["digital_micrograph_version_big_endian"] = int.from_bytes(
            header[0:4], "big"
        )
        result["digital_micrograph_byte_order_marker"] = int.from_bytes(
            header[8:12], "big"
        )
    return result


def main() -> int:
    original = engine._dm_header
    engine._dm_header = bounded_header
    try:
        return engine.main()
    finally:
        engine._dm_header = original


if __name__ == "__main__":
    raise SystemExit(main())
