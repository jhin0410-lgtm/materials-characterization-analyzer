#!/usr/bin/env python3
"""Run the W-Ta-Cr-V audit with bounded, format-aware inspection."""
from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_zenodo_wtacrv_tem_saed as engine


def bounded_header(path: Path) -> dict[str, Any]:
    """Read at most 32 bytes and apply version-specific DM3/DM4 offsets."""
    with path.open("rb") as handle:
        header = handle.read(32)
    result: dict[str, Any] = {
        "header_bytes": len(header),
        "header_hex": header[:16].hex(),
    }
    suffix = path.suffix.casefold()
    if suffix == ".dm3" and len(header) >= 12:
        result["digital_micrograph_version_big_endian"] = int.from_bytes(
            header[0:4], "big"
        )
        result["digital_micrograph_byte_order_marker"] = int.from_bytes(
            header[8:12], "big"
        )
    elif suffix == ".dm4" and len(header) >= 16:
        result["digital_micrograph_version_big_endian"] = int.from_bytes(
            header[0:4], "big"
        )
        result["digital_micrograph_declared_payload_bytes_big_endian"] = int.from_bytes(
            header[4:12], "big"
        )
        result["digital_micrograph_byte_order_marker"] = int.from_bytes(
            header[12:16], "big"
        )
    return result


def precise_microscopy_cues(path: str) -> list[str]:
    """Preserve modality/condition cues without matching unirradiated as irradiated."""
    pure = PurePosixPath(path)
    folded = path.casefold()
    basename = pure.name.casefold()
    parts = [part.casefold() for part in pure.parts]
    cues: list[str] = []
    if any(
        part == "tem" or part.startswith("tem ") or part.startswith("tem_")
        for part in parts
    ):
        cues.append("tem_folder")
    if any(
        part == "sem" or part.startswith("sem ") or part.startswith("sem_")
        for part in parts
    ):
        cues.append("sem_folder")
    if (
        "saed" in folded
        or "selected area" in folded
        or "diffraction" in folded
        or "diff" in basename
    ):
        cues.append("saed_name_cue")
    if any(
        term in folded for term in ("eds", "edx", "elemental map", "element map")
    ):
        cues.append("eds_name_cue")

    explicitly_unirradiated = any(
        term in folded
        for term in ("unirradiated", "un-irradiated", "as-depos", "as_depos", "as depos", "pristine")
    )
    explicitly_irradiated = any(
        term in folded for term in ("he-irr", "he_irr", "he irr", "implanted")
    ) or ("irradiat" in folded and not explicitly_unirradiated)
    if explicitly_irradiated:
        cues.append("irradiated_condition_cue")
    if explicitly_unirradiated:
        cues.append("as_deposited_condition_cue")
    if any(
        term in folded
        for term in ("calib", "camera length", "pattern centre", "pattern center")
    ):
        cues.append("calibration_or_centre_name_cue")
    return cues


def main() -> int:
    original_header = engine._dm_header
    original_cues = engine.microscopy_cues
    engine._dm_header = bounded_header
    engine.microscopy_cues = precise_microscopy_cues
    try:
        return engine.main()
    finally:
        engine._dm_header = original_header
        engine.microscopy_cues = original_cues


if __name__ == "__main__":
    raise SystemExit(main())
