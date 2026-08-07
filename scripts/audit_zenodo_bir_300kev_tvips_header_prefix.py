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

from scripts import audit_zenodo_bir_300kev_remote_inventory as remote  # noqa: E402

LOCAL_FILE_HEADER = struct.Struct("<4s5H3I2H")
LOCAL_SIGNATURE = b"PK\x03\x04"
TVIPS_GENERAL_HEADER = struct.Struct("<13I204s")


class Bir300TvipsHeaderPrefixError(RuntimeError):
    """Raised when the bounded selected-member header audit violates its contract."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Bir300TvipsHeaderPrefixError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise Bir300TvipsHeaderPrefixError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise Bir300TvipsHeaderPrefixError("JSON root must be an object")
    return value


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise Bir300TvipsHeaderPrefixError("configured repository path is unsafe")
    return (PROJECT_ROOT / candidate).resolve(strict=True)


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "case_id",
        "audit_date",
        "metadata_snapshot",
        "remote_inventory_config",
        "remote_inventory_snapshot",
        "target_member",
        "range_limits",
        "parser_contract",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != expected or value.get("schema_version") != "1.0":
        raise Bir300TvipsHeaderPrefixError("header-prefix config keys/schema do not match contract")

    target = value["target_member"]
    if not isinstance(target, dict) or set(target) != {
        "archive_key",
        "archive_bytes",
        "archive_md5",
        "member_path",
    }:
        raise Bir300TvipsHeaderPrefixError("target_member keys do not match contract")
    if not isinstance(target["archive_bytes"], int) or target["archive_bytes"] <= 0:
        raise Bir300TvipsHeaderPrefixError("archive_bytes must be positive")
    if not isinstance(target["member_path"], str) or not target["member_path"].endswith(".tvips"):
        raise Bir300TvipsHeaderPrefixError("target member must be an explicit .tvips path")

    limits = value["range_limits"]
    if not isinstance(limits, dict) or set(limits) != {
        "maximum_compressed_prefix_bytes",
        "required_decompressed_header_bytes",
        "maximum_local_filename_bytes",
        "maximum_local_extra_bytes",
    }:
        raise Bir300TvipsHeaderPrefixError("range_limits keys do not match contract")
    if any(not isinstance(item, int) or item <= 0 for item in limits.values()):
        raise Bir300TvipsHeaderPrefixError("all range limits must be positive integers")
    if limits["required_decompressed_header_bytes"] != TVIPS_GENERAL_HEADER.size:
        raise Bir300TvipsHeaderPrefixError("required TVIPS header size must remain 256 bytes")

    parser = value["parser_contract"]
    expected_parser = {
        "source_repository",
        "source_commit",
        "source_path",
        "general_header_bytes",
        "general_header_uint32_fields",
        "dummy_bytes",
        "allowed_versions",
        "allowed_bits_per_pixel",
        "frame_header_core_bytes",
    }
    if not isinstance(parser, dict) or set(parser) != expected_parser:
        raise Bir300TvipsHeaderPrefixError("parser_contract keys do not match contract")
    if parser["general_header_bytes"] != 256 or parser["dummy_bytes"] != 204:
        raise Bir300TvipsHeaderPrefixError("pinned RosettaSciIO header dimensions drifted")
    fields = parser["general_header_uint32_fields"]
    if not isinstance(fields, list) or len(fields) != 13 or len(set(fields)) != 13:
        raise Bir300TvipsHeaderPrefixError("TVIPS general-header field inventory is invalid")
    if parser["allowed_versions"] != [1, 2] or parser["allowed_bits_per_pixel"] != [8, 16]:
        raise Bir300TvipsHeaderPrefixError("pinned TVIPS parser value contract drifted")
    if parser["frame_header_core_bytes"] != 60:
        raise Bir300TvipsHeaderPrefixError("pinned frame-header core size drifted")

    boundary = value["scientific_boundary"]
    true_keys = {
        "remote_central_directory_recheck_authorized",
        "selected_local_zip_header_read_authorized",
        "selected_compressed_member_prefix_read_authorized",
        "decompress_only_first_256_header_bytes_authorized",
    }
    if not isinstance(boundary, dict) or any(boundary.get(key) is not True for key in true_keys):
        raise Bir300TvipsHeaderPrefixError("required bounded header operations are not authorized")
    if any(item is not False for key, item in boundary.items() if key not in true_keys):
        raise Bir300TvipsHeaderPrefixError("stronger source/analyzer operations must remain disabled")

    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise Bir300TvipsHeaderPrefixError("all fail-closed decision rules must be enabled")
    return value


def _recheck_remote_inventory(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    metadata_path = _resolve_repo_path(str(config["metadata_snapshot"]))
    remote_config_path = _resolve_repo_path(str(config["remote_inventory_config"]))
    remote_snapshot_path = _resolve_repo_path(str(config["remote_inventory_snapshot"]))
    metadata = load_json(metadata_path)
    remote_config = remote.validate_config(load_json(remote_config_path))
    pinned_remote = load_json(remote_snapshot_path)
    target = remote.resolve_target(remote_config, metadata)

    target_contract = config["target_member"]
    expected_target = (
        target_contract["archive_key"],
        target_contract["archive_bytes"],
        target_contract["archive_md5"],
    )
    observed_target = (target.get("key"), target.get("bytes"), target.get("md5"))
    if observed_target != expected_target:
        raise Bir300TvipsHeaderPrefixError("target archive no longer matches the pinned header contract")

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
    central_start = eocd["central_directory_offset"]
    central_end = central_start + eocd["central_directory_bytes"] - 1
    central = remote.fetch_range(
        str(target["content_url"]),
        start=central_start,
        end=central_end,
        expected_total=archive_size,
    )
    central_sha = sha256_bytes(central)
    records = remote.parse_central_directory(
        central,
        expected_entries=eocd["entries_total"],
        limits=limits,
    )
    summary = remote.summarize_inventory(records, central_sha256=central_sha)

    if pinned_remote.get("zip_structure") != eocd:
        raise Bir300TvipsHeaderPrefixError("live ZIP structure differs from verified remote inventory")
    pinned_summary = pinned_remote.get("inventory_summary")
    if not isinstance(pinned_summary, Mapping):
        raise Bir300TvipsHeaderPrefixError("verified remote inventory summary is invalid")
    for key in ("central_directory_sha256", "member_count", "tvips_member_paths"):
        if pinned_summary.get(key) != summary.get(key):
            raise Bir300TvipsHeaderPrefixError(
                f"live remote inventory differs from verified snapshot: {key}"
            )

    matches = [
        record
        for record in records
        if record["member_path"] == target_contract["member_path"]
    ]
    if len(matches) != 1:
        raise Bir300TvipsHeaderPrefixError("selected TVIPS member is not uniquely present")
    record = matches[0]
    if not record["is_tvips"] or record["unsafe_path"]:
        raise Bir300TvipsHeaderPrefixError("selected member is not a safe TVIPS member")
    return target, record, eocd, len(tail) + len(central)


def _decode_local_name(raw: bytes, flags: int) -> str:
    encoding = "utf-8" if flags & 0x0800 else "cp437"
    try:
        return raw.decode(encoding, errors="strict").replace("\\", "/")
    except UnicodeDecodeError as exc:
        raise Bir300TvipsHeaderPrefixError("local ZIP filename is not decodable") from exc


def _read_local_member_prefix(
    *,
    target: Mapping[str, Any],
    record: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[bytes | None, dict[str, Any]]:
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
        raise Bir300TvipsHeaderPrefixError("selected member local ZIP header signature is invalid")
    limits = config["range_limits"]
    if filename_len <= 0 or filename_len > int(limits["maximum_local_filename_bytes"]):
        raise Bir300TvipsHeaderPrefixError("local member filename length violates contract")
    if extra_len > int(limits["maximum_local_extra_bytes"]):
        raise Bir300TvipsHeaderPrefixError("local member extra length violates contract")
    variable_len = filename_len + extra_len
    variable = remote.fetch_range(
        url,
        start=local_offset + LOCAL_FILE_HEADER.size,
        end=local_offset + LOCAL_FILE_HEADER.size + variable_len - 1,
        expected_total=archive_size,
    )
    filename = _decode_local_name(variable[:filename_len], flags)
    if filename != record["member_path"]:
        raise Bir300TvipsHeaderPrefixError("local ZIP member name differs from central directory")
    if int(compression) != int(record["compression_method"]):
        raise Bir300TvipsHeaderPrefixError("local ZIP compression differs from central directory")
    if flags & 0x0001:
        raise Bir300TvipsHeaderPrefixError("encrypted TVIPS member is not authorized")
    if local_compressed not in {0, int(record["compressed_bytes"])}:
        raise Bir300TvipsHeaderPrefixError("local compressed size conflicts with central directory")
    if local_uncompressed not in {0, int(record["uncompressed_bytes"])}:
        raise Bir300TvipsHeaderPrefixError("local uncompressed size conflicts with central directory")
    central_crc = int(str(record["crc32_hex"]), 16)
    if crc32 not in {0, central_crc}:
        raise Bir300TvipsHeaderPrefixError("local CRC metadata conflicts with central directory")

    data_offset = local_offset + LOCAL_FILE_HEADER.size + variable_len
    compressed_bytes = int(record["compressed_bytes"])
    maximum_prefix = int(limits["maximum_compressed_prefix_bytes"])
    prefix_size = min(compressed_bytes, maximum_prefix)
    local_evidence = {
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
        "compressed_prefix_limit": maximum_prefix,
    }
    if compression not in {0, 8}:
        local_evidence["compressed_prefix_bytes_read"] = 0
        local_evidence["compression_supported_for_bounded_prefix"] = False
        return None, local_evidence

    compressed_prefix = remote.fetch_range(
        url,
        start=data_offset,
        end=data_offset + prefix_size - 1,
        expected_total=archive_size,
    )
    required = int(limits["required_decompressed_header_bytes"])
    if compression == 0:
        decompressed = compressed_prefix[:required]
    else:
        try:
            inflater = zlib.decompressobj(-15)
            decompressed = inflater.decompress(compressed_prefix, required)
        except zlib.error as exc:
            raise Bir300TvipsHeaderPrefixError(
                "selected deflate prefix could not be decompressed safely"
            ) from exc
    local_evidence["compressed_prefix_bytes_read"] = len(compressed_prefix)
    local_evidence["compressed_prefix_sha256"] = sha256_bytes(compressed_prefix)
    local_evidence["compression_supported_for_bounded_prefix"] = True
    local_evidence["decompressed_bytes_produced"] = len(decompressed)
    return decompressed if len(decompressed) >= required else None, local_evidence


def _parse_tvips_header(payload: bytes, parser: Mapping[str, Any]) -> dict[str, Any]:
    if len(payload) != TVIPS_GENERAL_HEADER.size:
        raise Bir300TvipsHeaderPrefixError("TVIPS general-header payload must be exactly 256 bytes")
    unpacked = TVIPS_GENERAL_HEADER.unpack(payload)
    names = [str(value) for value in parser["general_header_uint32_fields"]]
    values = {name: int(unpacked[index]) for index, name in enumerate(names)}
    dummy = unpacked[-1]
    checks = {
        "size_matches_256": values["size"] == int(parser["general_header_bytes"]),
        "version_supported": values["version"] in set(parser["allowed_versions"]),
        "dimensions_positive": 0 < values["dimx"] <= 32768 and 0 < values["dimy"] <= 32768,
        "bits_per_pixel_supported": values["bitsperpixel"] in set(parser["allowed_bits_per_pixel"]),
        "binning_positive": 0 < values["binx"] <= 64 and 0 < values["biny"] <= 64,
        "frame_header_core_compatible": (
            values["version"] == 2
            and values["frameheaderbytes"] >= int(parser["frame_header_core_bytes"])
        ),
    }
    structural_match = bool(
        checks["size_matches_256"]
        and checks["version_supported"]
        and checks["dimensions_positive"]
        and checks["bits_per_pixel_supported"]
        and checks["binning_positive"]
    )
    return {
        "fields": values,
        "checks": checks,
        "structural_match": structural_match,
        "header_sha256": sha256_bytes(payload),
        "dummy_sha256": sha256_bytes(dummy),
        "dummy_tvips_token_count": int(dummy.upper().count(b"TVIPS")),
        "dummy_printable_fraction": float(
            sum(32 <= byte <= 126 or byte in {9, 10, 13} for byte in dummy) / len(dummy)
        ),
    }


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = validate_config(load_json(config_resolved))
    target, record, eocd, inventory_bytes = _recheck_remote_inventory(config)
    header_payload, local = _read_local_member_prefix(
        target=target,
        record=record,
        config=config,
    )
    parsed_header = None
    if header_payload is not None:
        parsed_header = _parse_tvips_header(
            header_payload[: TVIPS_GENERAL_HEADER.size],
            config["parser_contract"],
        )

    local_bytes = int(local["fixed_local_header_bytes_read"]) + int(
        local["variable_local_header_bytes_read"]
    ) + int(local.get("compressed_prefix_bytes_read", 0))
    structural = parsed_header["structural_match"] if parsed_header is not None else None
    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "selected_tvips_header_prefix_audit_completed",
        "source": {
            "record_id": 10995139,
            "doi": "10.5281/zenodo.10995139",
            "dataset_license": "cc-by-4.0",
            "remote_inventory_snapshot_sha256": sha256_file(
                _resolve_repo_path(str(config["remote_inventory_snapshot"]))
            ),
        },
        "target_archive": {
            "key": target["key"],
            "bytes": int(target["bytes"]),
            "repository_md5": target["md5"],
            "full_archive_downloaded": False,
        },
        "selected_member": {
            "path": record["member_path"],
            "compressed_bytes": int(record["compressed_bytes"]),
            "uncompressed_bytes": int(record["uncompressed_bytes"]),
            "compression_method": int(record["compression_method"]),
            "full_member_downloaded": False,
        },
        "range_evidence": {
            "remote_inventory_bytes_read": int(inventory_bytes),
            "selected_member_range_bytes_read": int(local_bytes),
            "total_remote_bytes_read": int(inventory_bytes + local_bytes),
            "decompressed_header_bytes_retained": 0,
            "diffraction_pixel_array_decoded": False,
            "frame_payload_decoded": False,
        },
        "zip_structure": eocd,
        "local_member_header": local,
        "tvips_general_header": parsed_header,
        "parser_contract": {
            "source_repository": config["parser_contract"]["source_repository"],
            "source_commit": config["parser_contract"]["source_commit"],
            "source_path": config["parser_contract"]["source_path"],
            "general_header_bytes": 256,
        },
        "evidence_assessment": {
            "verified_remote_inventory_reproduced": "Supported",
            "selected_member_local_header_binding": "Supported",
            "tvips_general_header_structural_match": (
                "Supported" if structural is True else "Unsupported" if structural is False else "Inconclusive"
            ),
            "hyperspy_documented_split_stream_filename_compatibility": "Unsupported",
            "beam_energy_header_field": (
                "Diagnostic"
                if parsed_header is not None and parsed_header["fields"]["ht"] > 0
                else "Inconclusive"
            ),
            "camera_length_or_magnification_header_field": (
                "Diagnostic"
                if parsed_header is not None and parsed_header["fields"]["magtotal"] > 0
                else "Inconclusive"
            ),
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "sample_and_acquisition_lineage": "Inconclusive",
            "reference_reflection_truth": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "internal_header_structure_observed": bool(structural is True),
            "filename_adapter_or_staging_copy_may_be_investigated": bool(structural is True),
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": [
            "If the 256-byte general header structurally matches the pinned RosettaSciIO contract, inspect whether a temporary non-mutating filename adapter can present this single member as a reader-compatible file without claiming source-native split-stream naming.",
            "Do not interpret ht, pixelsize, magtotal, offsets, or binning as traceable reciprocal calibration until their acquisition semantics are supported by source metadata or an independently justified calibration protocol.",
            "Do not decode diffraction pixels or run SAED indexing until the calibration and reference protocol are frozen."
        ],
        "scientific_boundary": [
            "Only the ZIP inventory, selected local ZIP header, and a bounded compressed prefix of one TVIPS member were read.",
            "At most the first 256 decompressed member bytes were interpreted as the pinned RosettaSciIO general-header structure; no frame or diffraction pixel payload was decoded.",
            "A structural header match is format evidence only and does not establish sample lineage, calibration truth, reflection truth, analyzer performance, or external-validation readiness."
        ],
        "config_sha256": sha256_file(config_resolved),
    }
    output = Path(output_path).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read only the minimum selected TVIPS ZIP/member prefix needed to inspect the "
            "256-byte RosettaSciIO general-header structure."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_bir_300kev_saed_header_prefix/case_config.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (
        OSError,
        ValueError,
        zlib.error,
        remote.Bir300RemoteInventoryError,
        Bir300TvipsHeaderPrefixError,
    ) as exc:
        print(f"BIR 300 keV TVIPS header-prefix audit failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
