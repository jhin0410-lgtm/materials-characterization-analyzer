from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import audit_zenodo_srtio3_saed_remote_inventory as remote  # noqa: E402

LOCAL_FILE_HEADER = struct.Struct("<4s5H3I2H")
LOCAL_SIGNATURE = b"PK\x03\x04"
TIFF_TYPE_SIZES = {
    1: 1,   # BYTE
    2: 1,   # ASCII
    3: 2,   # SHORT
    4: 4,   # LONG
    5: 8,   # RATIONAL
    6: 1,   # SBYTE
    7: 1,   # UNDEFINED
    8: 2,   # SSHORT
    9: 4,   # SLONG
    10: 8,  # SRATIONAL
    11: 4,  # FLOAT
    12: 8,  # DOUBLE
}
TIFF_TYPE_NAMES = {
    1: "BYTE",
    2: "ASCII",
    3: "SHORT",
    4: "LONG",
    5: "RATIONAL",
    6: "SBYTE",
    7: "UNDEFINED",
    8: "SSHORT",
    9: "SLONG",
    10: "SRATIONAL",
    11: "FLOAT",
    12: "DOUBLE",
}


class SrTiO3SaedTiffMetadataError(RuntimeError):
    """Raised when the bounded TIFF metadata contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SrTiO3SaedTiffMetadataError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise SrTiO3SaedTiffMetadataError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise SrTiO3SaedTiffMetadataError("JSON root must be an object")
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
        raise SrTiO3SaedTiffMetadataError("configured repository path is unsafe")
    return (PROJECT_ROOT / candidate).resolve(strict=True)


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "metadata_snapshot",
        "remote_inventory_config",
        "remote_inventory_snapshot",
        "target_members",
        "range_limits",
        "tiff_contract",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise SrTiO3SaedTiffMetadataError("TIFF metadata config keys/schema do not match contract")

    members = value["target_members"]
    if not isinstance(members, list) or members != [
        "SAED/23K.tif",
        "SAED/91K.tif",
        "SAED/172K.tif",
    ]:
        raise SrTiO3SaedTiffMetadataError("target_members must remain the three pinned substantive TIFFs")

    limits = value["range_limits"]
    expected_limits = {
        "maximum_compressed_prefix_bytes_per_member",
        "initial_tiff_header_bytes",
        "maximum_ifd_entries",
        "maximum_decompressed_metadata_bytes",
        "maximum_local_filename_bytes",
        "maximum_local_extra_bytes",
    }
    if not isinstance(limits, dict) or set(limits) != expected_limits:
        raise SrTiO3SaedTiffMetadataError("range_limits keys do not match contract")
    if any(not isinstance(item, int) or item <= 0 for item in limits.values()):
        raise SrTiO3SaedTiffMetadataError("all range limits must be positive integers")
    if limits["initial_tiff_header_bytes"] != 8:
        raise SrTiO3SaedTiffMetadataError("classic TIFF header read must remain exactly 8 bytes")
    if limits["maximum_decompressed_metadata_bytes"] > 65536:
        raise SrTiO3SaedTiffMetadataError("TIFF metadata decompression ceiling must not exceed 64 KiB")

    tiff = value["tiff_contract"]
    expected_tiff = {
        "allowed_magic",
        "required_first_ifd_offset",
        "supported_byte_orders",
        "recorded_tags",
    }
    if not isinstance(tiff, dict) or set(tiff) != expected_tiff:
        raise SrTiO3SaedTiffMetadataError("tiff_contract keys do not match contract")
    if tiff["allowed_magic"] != 42 or tiff["required_first_ifd_offset"] != 8:
        raise SrTiO3SaedTiffMetadataError("bounded audit requires classic TIFF with first IFD at byte 8")
    if tiff["supported_byte_orders"] != ["II", "MM"]:
        raise SrTiO3SaedTiffMetadataError("supported TIFF byte-order contract drifted")
    tags = tiff["recorded_tags"]
    if not isinstance(tags, dict) or not tags:
        raise SrTiO3SaedTiffMetadataError("recorded TIFF tag inventory is invalid")
    for tag, name in tags.items():
        if not str(tag).isdigit() or not isinstance(name, str) or not name:
            raise SrTiO3SaedTiffMetadataError("recorded TIFF tag mapping is invalid")

    boundary = value["scientific_boundary"]
    true_keys = {
        "remote_inventory_recheck_authorized",
        "selected_local_zip_header_read_authorized",
        "selected_compressed_member_prefix_read_authorized",
        "decompress_tiff_header_and_first_ifd_metadata_authorized",
    }
    if not isinstance(boundary, dict) or any(boundary.get(key) is not True for key in true_keys):
        raise SrTiO3SaedTiffMetadataError("required bounded TIFF metadata operations are not authorized")
    if any(item is not False for key, item in boundary.items() if key not in true_keys):
        raise SrTiO3SaedTiffMetadataError("stronger TIFF/source/analyzer actions must remain disabled")

    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise SrTiO3SaedTiffMetadataError("all fail-closed TIFF decision rules must be enabled")
    return value


def _recheck_remote_inventory(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], int]:
    metadata_path = _resolve_repo_path(str(config["metadata_snapshot"]))
    remote_config_path = _resolve_repo_path(str(config["remote_inventory_config"]))
    pinned_path = _resolve_repo_path(str(config["remote_inventory_snapshot"]))
    metadata = _load_json(metadata_path)
    remote_config = remote._validate_config(_load_json(remote_config_path))
    pinned = _load_json(pinned_path)
    target = remote._resolve_target(remote_config, metadata)

    archive_size = int(target["bytes"])
    limits = remote_config["range_limits"]
    tail_size = min(int(limits["tail_probe_bytes"]), archive_size)
    tail = remote.fetch_range(
        str(target["content_url"]),
        start=archive_size - tail_size,
        end=archive_size - 1,
        expected_total=archive_size,
    )
    eocd = remote.parse_eocd(tail, archive_size=archive_size)
    central_start = int(eocd["central_directory_offset"])
    central = remote.fetch_range(
        str(target["content_url"]),
        start=central_start,
        end=central_start + int(eocd["central_directory_bytes"]) - 1,
        expected_total=archive_size,
    )
    records = remote.parse_central_directory(
        central,
        expected_entries=int(eocd["entries_total"]),
        limits=limits,
    )
    summary = remote._summarize(records, _sha256_bytes(central))
    if pinned.get("zip_structure") != eocd:
        raise SrTiO3SaedTiffMetadataError("live SAED.zip structure differs from pinned inventory")
    pinned_summary = pinned.get("inventory_summary")
    if not isinstance(pinned_summary, Mapping):
        raise SrTiO3SaedTiffMetadataError("pinned remote inventory summary is invalid")
    for key in ("central_directory_sha256", "member_count", "member_paths"):
        if pinned_summary.get(key) != summary.get(key):
            raise SrTiO3SaedTiffMetadataError(f"live SAED.zip inventory drifted: {key}")

    target_paths = list(config["target_members"])
    selected: list[dict[str, Any]] = []
    for path in target_paths:
        matches = [record for record in records if record["member_path"] == path]
        if len(matches) != 1:
            raise SrTiO3SaedTiffMetadataError(f"target TIFF is not uniquely present: {path}")
        record = matches[0]
        if record["unsafe_path"] or record["is_directory"]:
            raise SrTiO3SaedTiffMetadataError(f"target TIFF path is unsafe or a directory: {path}")
        selected.append(record)
    return target, selected, eocd, len(tail) + len(central)


def _decode_local_name(raw: bytes, flags: int) -> str:
    encoding = "utf-8" if flags & 0x0800 else "cp437"
    try:
        return raw.decode(encoding, errors="strict").replace("\\", "/")
    except UnicodeDecodeError as exc:
        raise SrTiO3SaedTiffMetadataError("local ZIP filename is not decodable") from exc


def _read_compressed_prefix(
    *,
    target: Mapping[str, Any],
    record: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    archive_size = int(target["bytes"])
    url = str(target["content_url"])
    local_offset = int(record["local_header_offset"])
    fixed = remote.fetch_range(
        url,
        start=local_offset,
        end=local_offset + LOCAL_FILE_HEADER.size - 1,
        expected_total=archive_size,
    )
    (
        signature,
        version_needed,
        flags,
        compression,
        _mtime,
        _mdate,
        crc32,
        local_compressed,
        local_uncompressed,
        filename_len,
        extra_len,
    ) = LOCAL_FILE_HEADER.unpack(fixed)
    if signature != LOCAL_SIGNATURE:
        raise SrTiO3SaedTiffMetadataError("local ZIP header signature is invalid")
    limits = config["range_limits"]
    if filename_len <= 0 or filename_len > int(limits["maximum_local_filename_bytes"]):
        raise SrTiO3SaedTiffMetadataError("local ZIP filename length violates contract")
    if extra_len > int(limits["maximum_local_extra_bytes"]):
        raise SrTiO3SaedTiffMetadataError("local ZIP extra length violates contract")
    variable_len = filename_len + extra_len
    variable = remote.fetch_range(
        url,
        start=local_offset + LOCAL_FILE_HEADER.size,
        end=local_offset + LOCAL_FILE_HEADER.size + variable_len - 1,
        expected_total=archive_size,
    )
    filename = _decode_local_name(variable[:filename_len], flags)
    if filename != record["member_path"]:
        raise SrTiO3SaedTiffMetadataError("local ZIP filename differs from central directory")
    if flags & 0x0001:
        raise SrTiO3SaedTiffMetadataError("encrypted TIFF member is not authorized")
    if int(compression) != int(record["compression_method"]):
        raise SrTiO3SaedTiffMetadataError("local ZIP compression differs from central directory")
    if compression not in {0, 8}:
        raise SrTiO3SaedTiffMetadataError(
            f"unsupported ZIP compression for bounded TIFF prefix: {compression}"
        )
    if local_compressed not in {0, int(record["compressed_bytes"])}:
        raise SrTiO3SaedTiffMetadataError("local compressed size conflicts with central directory")
    if local_uncompressed not in {0, int(record["uncompressed_bytes"])}:
        raise SrTiO3SaedTiffMetadataError("local uncompressed size conflicts with central directory")
    central_crc = int(str(record["crc32_hex"]), 16)
    if crc32 not in {0, central_crc}:
        raise SrTiO3SaedTiffMetadataError("local CRC metadata conflicts with central directory")

    data_offset = local_offset + LOCAL_FILE_HEADER.size + variable_len
    prefix_size = min(
        int(record["compressed_bytes"]),
        int(limits["maximum_compressed_prefix_bytes_per_member"]),
    )
    compressed_prefix = remote.fetch_range(
        url,
        start=data_offset,
        end=data_offset + prefix_size - 1,
        expected_total=archive_size,
    )
    evidence = {
        "version_needed": int(version_needed),
        "flags": int(flags),
        "uses_data_descriptor": bool(flags & 0x0008),
        "compression_method": int(compression),
        "local_header_offset": local_offset,
        "data_offset": int(data_offset),
        "filename_bytes": int(filename_len),
        "extra_bytes": int(extra_len),
        "fixed_local_header_bytes_read": len(fixed),
        "variable_local_header_bytes_read": len(variable),
        "compressed_prefix_bytes_read": len(compressed_prefix),
        "compressed_prefix_sha256": _sha256_bytes(compressed_prefix),
    }
    return compressed_prefix, evidence


def _decompress_exact_prefix(compressed: bytes, compression: int, required: int) -> bytes:
    if required <= 0:
        raise SrTiO3SaedTiffMetadataError("required TIFF metadata length must be positive")
    if compression == 0:
        output = compressed[:required]
    elif compression == 8:
        try:
            output = zlib.decompressobj(-15).decompress(compressed, required)
        except zlib.error as exc:
            raise SrTiO3SaedTiffMetadataError("deflated TIFF prefix could not be decompressed") from exc
    else:  # pragma: no cover - caller rejects this first
        raise SrTiO3SaedTiffMetadataError("unsupported ZIP compression")
    if len(output) < required:
        raise SrTiO3SaedTiffMetadataError(
            f"bounded compressed prefix did not produce required TIFF metadata bytes: {len(output)} < {required}"
        )
    return output[:required]


def _endian_prefix(byte_order: bytes) -> str:
    if byte_order == b"II":
        return "<"
    if byte_order == b"MM":
        return ">"
    raise SrTiO3SaedTiffMetadataError(f"unsupported TIFF byte order marker: {byte_order!r}")


def _decode_inline_value(raw: bytes, type_id: int, count: int, endian: str) -> Any:
    size = TIFF_TYPE_SIZES.get(type_id)
    if size is None or size * count > 4:
        return None
    payload = raw[: size * count]
    if type_id == 2:
        return payload.rstrip(b"\x00").decode("ascii", errors="replace")
    if type_id in {1, 7}:
        values = list(payload)
    elif type_id == 6:
        values = list(struct.unpack(f"{endian}{count}b", payload))
    elif type_id == 3:
        values = list(struct.unpack(f"{endian}{count}H", payload))
    elif type_id == 8:
        values = list(struct.unpack(f"{endian}{count}h", payload))
    elif type_id == 4:
        values = list(struct.unpack(f"{endian}{count}I", payload))
    elif type_id == 9:
        values = list(struct.unpack(f"{endian}{count}i", payload))
    elif type_id == 11:
        values = list(struct.unpack(f"{endian}{count}f", payload))
    else:
        return None
    return values[0] if len(values) == 1 else values


def _parse_tiff_ifd(payload: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    if len(payload) < 8:
        raise SrTiO3SaedTiffMetadataError("TIFF metadata payload is shorter than classic header")
    byte_order_raw = payload[:2]
    endian = _endian_prefix(byte_order_raw)
    magic = struct.unpack_from(f"{endian}H", payload, 2)[0]
    first_ifd_offset = struct.unpack_from(f"{endian}I", payload, 4)[0]
    tiff_contract = config["tiff_contract"]
    if magic != int(tiff_contract["allowed_magic"]):
        raise SrTiO3SaedTiffMetadataError(f"classic TIFF magic mismatch: {magic}")
    if first_ifd_offset != int(tiff_contract["required_first_ifd_offset"]):
        raise SrTiO3SaedTiffMetadataError(
            "first TIFF IFD is not immediately after the 8-byte header; pixel-free bounded audit stops"
        )
    if len(payload) < first_ifd_offset + 2:
        raise SrTiO3SaedTiffMetadataError("TIFF metadata payload does not include IFD entry count")
    entry_count = struct.unpack_from(f"{endian}H", payload, first_ifd_offset)[0]
    if entry_count > int(config["range_limits"]["maximum_ifd_entries"]):
        raise SrTiO3SaedTiffMetadataError("TIFF first IFD entry count exceeds configured limit")
    required = first_ifd_offset + 2 + entry_count * 12 + 4
    if required > int(config["range_limits"]["maximum_decompressed_metadata_bytes"]):
        raise SrTiO3SaedTiffMetadataError("TIFF first IFD exceeds metadata decompression ceiling")
    if len(payload) < required:
        raise SrTiO3SaedTiffMetadataError("TIFF metadata payload does not include complete first IFD")

    recorded = {int(tag): name for tag, name in tiff_contract["recorded_tags"].items()}
    tags: dict[str, Any] = {}
    unknown_tag_count = 0
    offset = first_ifd_offset + 2
    for _ in range(entry_count):
        tag, type_id, count = struct.unpack_from(f"{endian}HHI", payload, offset)
        raw_value = payload[offset + 8 : offset + 12]
        type_size = TIFF_TYPE_SIZES.get(type_id)
        total_bytes = type_size * count if type_size is not None else None
        value_or_offset = struct.unpack(f"{endian}I", raw_value)[0]
        name = recorded.get(tag)
        if name is None:
            unknown_tag_count += 1
        else:
            inline = total_bytes is not None and total_bytes <= 4
            tags[name] = {
                "tag": int(tag),
                "type_id": int(type_id),
                "type_name": TIFF_TYPE_NAMES.get(type_id, "UNKNOWN"),
                "count": int(count),
                "storage": "inline" if inline else "out_of_line",
                "value": _decode_inline_value(raw_value, type_id, count, endian) if inline else None,
                "value_offset_if_out_of_line": int(value_or_offset) if not inline else None,
                "out_of_line_value_followed": False,
            }
        offset += 12
    next_ifd_offset = struct.unpack_from(f"{endian}I", payload, offset)[0]
    page_evidence = {
        "first_ifd_only": True,
        "next_ifd_offset": int(next_ifd_offset),
        "exact_page_count_supported": bool(next_ifd_offset == 0),
        "page_count_if_supported": 1 if next_ifd_offset == 0 else None,
        "minimum_page_count": 1 if next_ifd_offset == 0 else 2,
    }
    return {
        "byte_order": byte_order_raw.decode("ascii"),
        "magic": int(magic),
        "first_ifd_offset": int(first_ifd_offset),
        "first_ifd_entry_count": int(entry_count),
        "first_ifd_metadata_bytes": int(required),
        "recorded_tags": tags,
        "unrecorded_tag_count": int(unknown_tag_count),
        "page_count_evidence": page_evidence,
        "out_of_line_values_followed": False,
    }


def _required_ifd_bytes(
    compressed: bytes,
    *,
    compression: int,
    config: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    first = _decompress_exact_prefix(compressed, compression, 8)
    endian = _endian_prefix(first[:2])
    magic = struct.unpack_from(f"{endian}H", first, 2)[0]
    first_ifd_offset = struct.unpack_from(f"{endian}I", first, 4)[0]
    if magic != int(config["tiff_contract"]["allowed_magic"]):
        raise SrTiO3SaedTiffMetadataError(f"classic TIFF magic mismatch: {magic}")
    required_offset = int(config["tiff_contract"]["required_first_ifd_offset"])
    if first_ifd_offset != required_offset:
        raise SrTiO3SaedTiffMetadataError(
            "first TIFF IFD is not immediately after the 8-byte header; refusing broader decompression"
        )
    count_prefix = _decompress_exact_prefix(compressed, compression, required_offset + 2)
    entry_count = struct.unpack_from(f"{endian}H", count_prefix, required_offset)[0]
    if entry_count > int(config["range_limits"]["maximum_ifd_entries"]):
        raise SrTiO3SaedTiffMetadataError("TIFF first IFD entry count exceeds configured limit")
    required = required_offset + 2 + int(entry_count) * 12 + 4
    if required > int(config["range_limits"]["maximum_decompressed_metadata_bytes"]):
        raise SrTiO3SaedTiffMetadataError("TIFF first IFD exceeds metadata decompression ceiling")
    metadata = _decompress_exact_prefix(compressed, compression, required)
    return metadata, {
        "tiff_header_bytes_decompressed": 8,
        "ifd_entry_count_probe_bytes_decompressed": int(required_offset + 2),
        "maximum_metadata_prefix_bytes_decompressed": int(required),
        "pixel_array_decoded": False,
    }


def _scalar_tag(parsed: Mapping[str, Any], name: str) -> Any:
    tags = parsed.get("recorded_tags")
    if not isinstance(tags, Mapping):
        return None
    record = tags.get(name)
    if not isinstance(record, Mapping) or record.get("storage") != "inline":
        return None
    return record.get("value")


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    target, records, eocd, inventory_bytes = _recheck_remote_inventory(config)

    member_results: list[dict[str, Any]] = []
    total_member_range_bytes = 0
    for record in records:
        compressed, local = _read_compressed_prefix(
            target=target,
            record=record,
            config=config,
        )
        metadata, decompression = _required_ifd_bytes(
            compressed,
            compression=int(record["compression_method"]),
            config=config,
        )
        parsed = _parse_tiff_ifd(metadata, config)
        range_bytes = (
            int(local["fixed_local_header_bytes_read"])
            + int(local["variable_local_header_bytes_read"])
            + int(local["compressed_prefix_bytes_read"])
        )
        total_member_range_bytes += range_bytes
        member_results.append(
            {
                "path": record["member_path"],
                "compressed_bytes": int(record["compressed_bytes"]),
                "uncompressed_bytes": int(record["uncompressed_bytes"]),
                "zip_compression_method": int(record["compression_method"]),
                "full_member_downloaded": False,
                "local_zip_header": local,
                "tiff": parsed,
                "decompression_evidence": decompression,
                "metadata_prefix_sha256": _sha256_bytes(metadata),
            }
        )

    structural_fields = [
        "ImageWidth",
        "ImageLength",
        "BitsPerSample",
        "Compression",
        "PhotometricInterpretation",
        "SamplesPerPixel",
        "RowsPerStrip",
        "PlanarConfiguration",
        "TileWidth",
        "TileLength",
        "SampleFormat",
    ]
    comparisons: dict[str, Any] = {}
    for field in structural_fields:
        values = [_scalar_tag(item["tiff"], field) for item in member_results]
        comparisons[field] = {
            "values": values,
            "all_three_inline_values_available": all(value is not None for value in values),
            "all_three_equal_when_available": (
                len(set(json.dumps(value, sort_keys=True) for value in values)) == 1
                if all(value is not None for value in values)
                else None
            ),
        }

    dimensions_supported = all(
        _scalar_tag(item["tiff"], "ImageWidth") is not None
        and _scalar_tag(item["tiff"], "ImageLength") is not None
        for item in member_results
    )
    bit_depth_supported = all(
        _scalar_tag(item["tiff"], "BitsPerSample") is not None for item in member_results
    )

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "bounded_tiff_ifd_metadata_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "source": {
            "record_id": 20300700,
            "doi": "10.5281/zenodo.20300700",
            "license_id": "cc-by-4.0",
            "remote_inventory_snapshot_sha256": _sha256_file(
                _resolve_repo_path(str(config["remote_inventory_snapshot"]))
            ),
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
            "raw_tiff_bytes_retained": 0,
            "pixel_array_decoded": False,
            "four_d_stem_bytes_read": False,
        },
        "zip_structure": eocd,
        "members": member_results,
        "cross_member_structural_comparison": comparisons,
        "evidence_assessment": {
            "three_substantive_tiff_member_identity": "Supported",
            "classic_tiff_header_and_first_ifd_structure": "Supported",
            "image_dimensions": "Supported" if dimensions_supported else "Inconclusive",
            "bits_per_sample": "Supported" if bit_depth_supported else "Inconclusive",
            "raw_detector_native_intensity": "Inconclusive",
            "filename_k_suffix_temperature_semantics": "Inconclusive",
            "acquisition_independence": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "reference_reflection_truth": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "tiff_metadata_ready": True,
            "pixel_access_authorized": False,
            "four_d_stem_download_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "scientific_boundary": [
            "Only ZIP local-header bytes, bounded compressed prefixes, and the classic TIFF header plus first IFD metadata were accessed.",
            "No out-of-line TIFF tag value was followed and no TIFF pixel array was decoded or retained.",
            "The K-like filename suffix is not treated as temperature without authoritative source metadata.",
            "Three TIFF files are not treated as three independent acquisitions without lineage evidence.",
            "Dimensions and bit depth are format evidence only; detector-native intensity, pattern centre, reciprocal calibration, phase truth and external-validation readiness remain unresolved."
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
        description=(
            "Read only bounded ZIP/TIFF metadata for the three verified SrTiO3 SAED TIFF members; "
            "do not decode pixels."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_srtio3_saed_tiff_metadata/case_config.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/zenodo_srtio3_saed_tiff_metadata/tiff_metadata_snapshot.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (OSError, ValueError, SrTiO3SaedTiffMetadataError) as exc:
        print(f"SrTiO3 SAED TIFF metadata audit failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
