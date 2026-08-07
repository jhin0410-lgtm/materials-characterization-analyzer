from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import audit_zenodo_srtio3_saed_tiff_metadata as tiff  # noqa: E402


class SrTiO3SaedPrePixelMetadataError(RuntimeError):
    """Raised when the pre-pixel TIFF metadata contract is violated."""


def _load_json(path: str | Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SrTiO3SaedPrePixelMetadataError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise SrTiO3SaedPrePixelMetadataError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise SrTiO3SaedPrePixelMetadataError("JSON root must be an object")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SrTiO3SaedPrePixelMetadataError("configured repository path is unsafe")
    return (PROJECT_ROOT / candidate).resolve(strict=True)


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "tiff_metadata_config",
        "tiff_metadata_snapshot",
        "target_members",
        "pixel_boundary",
        "authorized_text_tags",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise SrTiO3SaedPrePixelMetadataError("pre-pixel config keys/schema do not match contract")
    if value["target_members"] != ["SAED/23K.tif", "SAED/91K.tif", "SAED/172K.tif"]:
        raise SrTiO3SaedPrePixelMetadataError("target member inventory drifted")
    pixel = value["pixel_boundary"]
    if not isinstance(pixel, dict) or set(pixel) != {
        "verified_first_strip_offset",
        "maximum_decompressed_prefix_bytes",
    }:
        raise SrTiO3SaedPrePixelMetadataError("pixel boundary contract is invalid")
    strip = pixel["verified_first_strip_offset"]
    prefix = pixel["maximum_decompressed_prefix_bytes"]
    if strip != 272 or prefix != 262 or prefix >= strip:
        raise SrTiO3SaedPrePixelMetadataError("pre-pixel prefix must remain 262 bytes before strip offset 272")
    tags = value["authorized_text_tags"]
    expected = [
        {"name": "ImageDescription", "offset": 194, "bytes": 24},
        {"name": "Software", "offset": 250, "bytes": 12},
    ]
    if tags != expected:
        raise SrTiO3SaedPrePixelMetadataError("authorized text tag ranges drifted")
    for tag in tags:
        if tag["offset"] < 0 or tag["bytes"] <= 0 or tag["offset"] + tag["bytes"] > prefix:
            raise SrTiO3SaedPrePixelMetadataError("authorized text range exceeds pre-pixel prefix")
        if tag["offset"] + tag["bytes"] > strip:
            raise SrTiO3SaedPrePixelMetadataError("authorized text range reaches pixel strip")
    boundary = value["scientific_boundary"]
    true_keys = {
        "recheck_tiff_structure_authorized",
        "decompress_only_verified_pre_pixel_prefix_authorized",
        "decode_authorized_ascii_text_tags_authorized",
    }
    if not isinstance(boundary, dict) or any(boundary.get(key) is not True for key in true_keys):
        raise SrTiO3SaedPrePixelMetadataError("required pre-pixel operations are not authorized")
    if any(item is not False for key, item in boundary.items() if key not in true_keys):
        raise SrTiO3SaedPrePixelMetadataError("pixel/source/analyzer actions must remain disabled")
    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise SrTiO3SaedPrePixelMetadataError("all fail-closed pre-pixel rules must be enabled")
    return value


def _decode_ascii(payload: bytes) -> dict[str, Any]:
    stripped = payload.rstrip(b"\x00")
    try:
        text = stripped.decode("ascii", errors="strict")
        valid = True
    except UnicodeDecodeError:
        text = None
        valid = False
    return {
        "ascii_valid": valid,
        "text": text,
        "raw_length": len(payload),
        "stripped_length": len(stripped),
        "sha256": _sha256_bytes(payload),
    }


def _assert_live_matches_pinned(
    *,
    record: Mapping[str, Any],
    local: Mapping[str, Any],
    parsed: Mapping[str, Any],
    metadata_sha: str,
    pinned: Mapping[str, Any],
) -> None:
    pinned_members = pinned.get("members")
    if not isinstance(pinned_members, list):
        raise SrTiO3SaedPrePixelMetadataError("pinned TIFF member inventory is invalid")
    matches = [item for item in pinned_members if isinstance(item, Mapping) and item.get("path") == record["member_path"]]
    if len(matches) != 1:
        raise SrTiO3SaedPrePixelMetadataError("live TIFF is not uniquely bound to pinned metadata")
    expected_member = matches[0]
    if int(record["compressed_bytes"]) != int(expected_member["compressed_bytes"]):
        raise SrTiO3SaedPrePixelMetadataError("TIFF compressed byte count drifted")
    if int(record["uncompressed_bytes"]) != int(expected_member["uncompressed_bytes"]):
        raise SrTiO3SaedPrePixelMetadataError("TIFF uncompressed byte count drifted")
    if local.get("compressed_prefix_sha256") != expected_member.get("compressed_prefix_sha256"):
        raise SrTiO3SaedPrePixelMetadataError("TIFF compressed prefix hash drifted")
    common = pinned.get("common_tiff_structure")
    if not isinstance(common, Mapping):
        raise SrTiO3SaedPrePixelMetadataError("pinned common TIFF structure is invalid")
    if metadata_sha != common.get("metadata_prefix_sha256"):
        raise SrTiO3SaedPrePixelMetadataError("TIFF first-IFD metadata hash drifted")
    checks = {
        "ImageWidth": common.get("ImageWidth"),
        "ImageLength": common.get("ImageLength"),
        "BitsPerSample": common.get("BitsPerSample"),
        "SampleFormat": common.get("SampleFormat"),
        "StripOffsets": common.get("StripOffsets"),
        "StripByteCounts": common.get("StripByteCounts"),
    }
    for tag, expected in checks.items():
        observed = tiff._scalar_tag(parsed, tag)
        if observed != expected:
            raise SrTiO3SaedPrePixelMetadataError(f"live TIFF tag drifted: {tag}")


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    tiff_config_path = _resolve_repo_path(str(config["tiff_metadata_config"]))
    tiff_config = tiff._validate_config(_load_json(tiff_config_path))
    pinned_path = _resolve_repo_path(str(config["tiff_metadata_snapshot"]))
    pinned = _load_json(pinned_path)
    if pinned.get("readiness", {}).get("pre_pixel_text_metadata_range_identified") is not True:
        raise SrTiO3SaedPrePixelMetadataError("pinned TIFF snapshot does not authorize pre-pixel text audit")

    target, records, eocd, inventory_bytes = tiff._recheck_remote_inventory(tiff_config)
    expected_paths = list(config["target_members"])
    if [record["member_path"] for record in records] != expected_paths:
        raise SrTiO3SaedPrePixelMetadataError("live TIFF member order/inventory differs from pre-pixel contract")

    prefix_required = int(config["pixel_boundary"]["maximum_decompressed_prefix_bytes"])
    strip_offset = int(config["pixel_boundary"]["verified_first_strip_offset"])
    member_results: list[dict[str, Any]] = []
    total_member_range_bytes = 0
    for record in records:
        compressed, local = tiff._read_compressed_prefix(
            target=target,
            record=record,
            config=tiff_config,
        )
        ifd_metadata, ifd_evidence = tiff._required_ifd_bytes(
            compressed,
            compression=int(record["compression_method"]),
            config=tiff_config,
        )
        parsed = tiff._parse_tiff_ifd(ifd_metadata, tiff_config)
        _assert_live_matches_pinned(
            record=record,
            local=local,
            parsed=parsed,
            metadata_sha=_sha256_bytes(ifd_metadata),
            pinned=pinned,
        )
        observed_strip = tiff._scalar_tag(parsed, "StripOffsets")
        if observed_strip != strip_offset:
            raise SrTiO3SaedPrePixelMetadataError("verified pixel strip boundary drifted")
        prefix = tiff._decompress_exact_prefix(
            compressed,
            int(record["compression_method"]),
            prefix_required,
        )
        if len(prefix) >= strip_offset:
            raise SrTiO3SaedPrePixelMetadataError("decompressed pre-pixel prefix reached pixel strip")
        texts: dict[str, Any] = {}
        for tag in config["authorized_text_tags"]:
            start = int(tag["offset"])
            end = start + int(tag["bytes"])
            if end > strip_offset or end > len(prefix):
                raise SrTiO3SaedPrePixelMetadataError("authorized text range is outside safe prefix")
            texts[str(tag["name"])] = _decode_ascii(prefix[start:end])
        member_range_bytes = (
            int(local["fixed_local_header_bytes_read"])
            + int(local["variable_local_header_bytes_read"])
            + int(local["compressed_prefix_bytes_read"])
        )
        total_member_range_bytes += member_range_bytes
        member_results.append(
            {
                "path": record["member_path"],
                "full_member_downloaded": False,
                "compressed_bytes": int(record["compressed_bytes"]),
                "uncompressed_bytes": int(record["uncompressed_bytes"]),
                "verified_first_strip_offset": strip_offset,
                "pre_pixel_prefix_bytes_decompressed": len(prefix),
                "pre_pixel_prefix_sha256": _sha256_bytes(prefix),
                "text_metadata": texts,
                "pixel_bytes_decompressed": 0,
                "ifd_recheck": {
                    "metadata_prefix_sha256": _sha256_bytes(ifd_metadata),
                    "first_ifd_metadata_bytes": int(ifd_evidence["maximum_metadata_prefix_bytes_decompressed"]),
                },
            }
        )

    comparison: dict[str, Any] = {}
    for tag in ("ImageDescription", "Software"):
        values = [item["text_metadata"][tag]["text"] for item in member_results]
        valid = [bool(item["text_metadata"][tag]["ascii_valid"]) for item in member_results]
        comparison[tag] = {
            "values": values,
            "all_ascii_valid": all(valid),
            "all_three_equal": len(set(values)) == 1 if all(valid) else None,
        }

    nonempty_software = all(
        isinstance(item["text_metadata"]["Software"]["text"], str)
        and bool(item["text_metadata"]["Software"]["text"].strip())
        for item in member_results
    )
    nonempty_description = all(
        isinstance(item["text_metadata"]["ImageDescription"]["text"], str)
        and bool(item["text_metadata"]["ImageDescription"]["text"].strip())
        for item in member_results
    )
    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "bounded_pre_pixel_text_metadata_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "source": {
            "record_id": 20300700,
            "doi": "10.5281/zenodo.20300700",
            "license_id": "cc-by-4.0",
            "tiff_metadata_snapshot_sha256": _sha256_file(pinned_path),
        },
        "target_archive": {
            "key": target["key"],
            "bytes": int(target["bytes"]),
            "repository_md5": target["md5"],
            "full_archive_downloaded": False,
        },
        "range_evidence": {
            "remote_inventory_bytes_read": int(inventory_bytes),
            "selected_member_range_bytes_read": int(total_member_range_bytes),
            "total_remote_bytes_read": int(inventory_bytes + total_member_range_bytes),
            "maximum_decompressed_prefix_per_member": prefix_required,
            "verified_first_pixel_strip_offset": strip_offset,
            "pixel_bytes_decompressed": 0,
            "raw_tiff_bytes_retained": 0,
            "four_d_stem_bytes_read": False,
        },
        "zip_structure": eocd,
        "members": member_results,
        "cross_member_text_comparison": comparison,
        "evidence_assessment": {
            "pre_pixel_image_description": "Supported" if nonempty_description else "Inconclusive",
            "pre_pixel_software_metadata": "Supported" if nonempty_software else "Inconclusive",
            "floating_point_tiff_export_context": "Diagnostic",
            "raw_detector_native_intensity": "Inconclusive",
            "filename_k_suffix_temperature_semantics": "Inconclusive",
            "acquisition_independence": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "pre_pixel_text_metadata_ready": True,
            "pixel_access_authorized": False,
            "four_d_stem_download_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "scientific_boundary": [
            "Only explicitly authorized TIFF text ranges ending before the verified first pixel strip were decoded.",
            "No pixel byte at or beyond strip offset 272 was decompressed or retained.",
            "Software/export metadata may identify representation provenance but does not prove detector-native intensity preservation.",
            "Filename K suffix, acquisition independence, pattern centre, reciprocal calibration and phase truth remain separate evidence requirements."
        ],
    }
    output = Path(output_path).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read only verified TIFF text metadata located before the first pixel strip."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_srtio3_saed_prepixel_metadata/case_config.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/zenodo_srtio3_saed_prepixel_metadata/prepixel_metadata_snapshot.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (OSError, ValueError, SrTiO3SaedPrePixelMetadataError) as exc:
        print(f"SrTiO3 SAED pre-pixel metadata audit failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
