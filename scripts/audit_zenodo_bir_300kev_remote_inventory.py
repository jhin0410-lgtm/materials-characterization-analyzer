from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

USER_AGENT = "materials-characterization-analyzer-range-audit/1.0"
EOCD_SIGNATURE = b"PK\x05\x06"
CENTRAL_SIGNATURE = b"PK\x01\x02"
EOCD_STRUCT = struct.Struct("<4s4H2IH")
CENTRAL_STRUCT = struct.Struct("<4s6H3I5H2I")
TVIPS_SERIES_RE = re.compile(r"^(?P<prefix>.*)_(?P<index>\d{3})\.tvips$", re.IGNORECASE)
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
ZIP64_SENTINEL_16 = 0xFFFF
ZIP64_SENTINEL_32 = 0xFFFFFFFF


class Bir300RemoteInventoryError(RuntimeError):
    """Raised when bounded remote ZIP inventory or its scientific contract fails."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Bir300RemoteInventoryError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise Bir300RemoteInventoryError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise Bir300RemoteInventoryError("JSON root must be an object")
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise Bir300RemoteInventoryError(f"{field} must be a positive integer")
    return value


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    expected_top = {
        "schema_version",
        "case_id",
        "audit_date",
        "source_snapshot",
        "target_archive",
        "range_limits",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != expected_top:
        raise Bir300RemoteInventoryError("unexpected top-level config keys")
    if value["schema_version"] != "1.0":
        raise Bir300RemoteInventoryError("unsupported config schema_version")
    for field in ("case_id", "audit_date", "source_snapshot"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise Bir300RemoteInventoryError(f"{field} must be a non-empty string")

    archive = value["target_archive"]
    if not isinstance(archive, dict) or set(archive) != {
        "key",
        "expected_bytes",
        "expected_md5",
    }:
        raise Bir300RemoteInventoryError("target_archive keys do not match contract")
    if not isinstance(archive["key"], str) or not archive["key"].strip():
        raise Bir300RemoteInventoryError("target archive key is invalid")
    _require_positive_int(archive["expected_bytes"], "target_archive.expected_bytes")
    md5 = archive["expected_md5"]
    if (
        not isinstance(md5, str)
        or len(md5) != 32
        or any(char not in "0123456789abcdef" for char in md5.lower())
    ):
        raise Bir300RemoteInventoryError("target archive expected_md5 is invalid")

    limits = value["range_limits"]
    expected_limits = {
        "tail_probe_bytes",
        "maximum_central_directory_bytes",
        "maximum_member_count",
        "maximum_filename_bytes",
        "maximum_extra_bytes",
        "maximum_comment_bytes",
    }
    if not isinstance(limits, dict) or set(limits) != expected_limits:
        raise Bir300RemoteInventoryError("range_limits keys do not match contract")
    for field in expected_limits:
        _require_positive_int(limits[field], f"range_limits.{field}")
    if limits["tail_probe_bytes"] < 65557:
        raise Bir300RemoteInventoryError("tail probe is too small to cover a maximal ZIP comment")

    boundary = value["scientific_boundary"]
    expected_boundary = {
        "http_range_metadata_probe_authorized",
        "central_directory_inventory_authorized",
        "full_archive_download_authorized",
        "archive_member_payload_download_authorized",
        "source_file_retention_authorized",
        "tvips_pixel_array_access_authorized",
        "tvips_header_payload_inspection_authorized",
        "analyzer_inference_authorized",
        "parameter_tuning_authorized",
        "model_retraining_authorized",
        "phase_indexing_authorized",
        "external_validation_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if not isinstance(boundary, dict) or set(boundary) != expected_boundary:
        raise Bir300RemoteInventoryError("scientific_boundary keys do not match contract")
    required_true = {
        "http_range_metadata_probe_authorized",
        "central_directory_inventory_authorized",
    }
    if any(boundary[key] is not True for key in required_true):
        raise Bir300RemoteInventoryError("bounded range inventory is not authorized")
    if any(boundary[key] is not False for key in expected_boundary - required_true):
        raise Bir300RemoteInventoryError("stronger source/analyzer operations must remain disabled")

    rules = value["decision_rules"]
    expected_rules = {
        "range_support_is_required",
        "full_download_fallback_is_prohibited",
        "zip64_or_multidisk_requires_separate_review",
        "member_filename_is_not_acquisition_lineage",
        "main_header_series_presence_is_format_readiness_only",
        "tvips_inventory_does_not_establish_reciprocal_calibration",
    }
    if not isinstance(rules, dict) or set(rules) != expected_rules:
        raise Bir300RemoteInventoryError("decision_rules keys do not match contract")
    if any(rules[key] is not True for key in expected_rules):
        raise Bir300RemoteInventoryError("all fail-closed decision rules must be true")
    return value


def resolve_target_from_snapshot(
    config: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if snapshot.get("execution_status") != "metadata_audit_completed":
        raise Bir300RemoteInventoryError("source snapshot is not a completed metadata audit")
    source = snapshot.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 10995139:
        raise Bir300RemoteInventoryError("source snapshot is not the pinned BIR 300 keV record")
    if source.get("license_id") != "cc-by-4.0":
        raise Bir300RemoteInventoryError("source snapshot no longer supports the pinned dataset reuse terms")
    inventory = snapshot.get("file_inventory")
    if not isinstance(inventory, list):
        raise Bir300RemoteInventoryError("source snapshot file inventory is invalid")
    target_config = config["target_archive"]
    matches = [
        item
        for item in inventory
        if isinstance(item, Mapping) and item.get("key") == target_config["key"]
    ]
    if len(matches) != 1:
        raise Bir300RemoteInventoryError("target archive is not uniquely present in source snapshot")
    target = dict(matches[0])
    if target.get("bytes") != target_config["expected_bytes"]:
        raise Bir300RemoteInventoryError("target archive byte count differs from config")
    if target.get("md5") != target_config["expected_md5"]:
        raise Bir300RemoteInventoryError("target archive repository MD5 differs from config")
    url = target.get("content_url")
    if not isinstance(url, str) or not url:
        raise Bir300RemoteInventoryError("target archive content URL is missing")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise Bir300RemoteInventoryError("target archive URL is outside the pinned Zenodo host")
    return target


def _parse_content_range(value: str | None) -> tuple[int, int, int]:
    if not value:
        raise Bir300RemoteInventoryError("HTTP 206 response omitted Content-Range")
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if match is None:
        raise Bir300RemoteInventoryError(f"invalid Content-Range: {value!r}")
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def fetch_range(
    url: str,
    *,
    start: int,
    end: int,
    expected_total: int,
) -> bytes:
    if start < 0 or end < start or end >= expected_total:
        raise Bir300RemoteInventoryError("requested byte range is outside the pinned archive")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "identity",
            "Range": f"bytes={start}-{end}",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 206:
            raise Bir300RemoteInventoryError(
                f"server did not honor byte-range request (HTTP {status}); full-download fallback is prohibited"
            )
        final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
            raise Bir300RemoteInventoryError("range response redirected outside the pinned Zenodo host")
        observed_start, observed_end, observed_total = _parse_content_range(
            response.headers.get("Content-Range")
        )
        if (observed_start, observed_end, observed_total) != (start, end, expected_total):
            raise Bir300RemoteInventoryError("range response does not match the requested/pinned byte interval")
        encoding = response.headers.get("Content-Encoding")
        if encoding not in {None, "", "identity"}:
            raise Bir300RemoteInventoryError("range response unexpectedly applied content encoding")
        expected_length = end - start + 1
        payload = response.read(expected_length + 1)
        if len(payload) != expected_length:
            raise Bir300RemoteInventoryError("range response byte count is incorrect")
        return payload


def parse_eocd(tail: bytes, *, archive_size: int) -> dict[str, int]:
    position = tail.rfind(EOCD_SIGNATURE)
    if position < 0:
        raise Bir300RemoteInventoryError("ZIP end-of-central-directory signature was not found")
    if position + EOCD_STRUCT.size > len(tail):
        raise Bir300RemoteInventoryError("truncated ZIP end-of-central-directory record")
    (
        signature,
        disk_number,
        central_disk,
        entries_on_disk,
        entries_total,
        central_size,
        central_offset,
        comment_length,
    ) = EOCD_STRUCT.unpack_from(tail, position)
    if signature != EOCD_SIGNATURE:
        raise Bir300RemoteInventoryError("invalid ZIP end-of-central-directory signature")
    if position + EOCD_STRUCT.size + comment_length != len(tail):
        raise Bir300RemoteInventoryError("ZIP end-of-central-directory does not terminate at archive end")
    if disk_number != 0 or central_disk != 0 or entries_on_disk != entries_total:
        raise Bir300RemoteInventoryError("multi-disk ZIP requires separate review")
    if (
        entries_total == ZIP64_SENTINEL_16
        or central_size == ZIP64_SENTINEL_32
        or central_offset == ZIP64_SENTINEL_32
    ):
        raise Bir300RemoteInventoryError("ZIP64 central directory requires separate review")
    if entries_total <= 0 or central_size <= 0:
        raise Bir300RemoteInventoryError("ZIP central directory is empty")
    if central_offset + central_size > archive_size - EOCD_STRUCT.size:
        raise Bir300RemoteInventoryError("ZIP central directory lies outside the pinned archive")
    return {
        "entries_total": int(entries_total),
        "central_directory_bytes": int(central_size),
        "central_directory_offset": int(central_offset),
        "comment_bytes": int(comment_length),
    }


def _decode_filename(raw: bytes, flags: int) -> str:
    encoding = "utf-8" if flags & 0x0800 else "cp437"
    try:
        return raw.decode(encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise Bir300RemoteInventoryError(
            f"ZIP filename cannot be decoded as {encoding}"
        ) from exc


def parse_central_directory(
    payload: bytes,
    *,
    expected_entries: int,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if expected_entries > int(limits["maximum_member_count"]):
        raise Bir300RemoteInventoryError("ZIP member count exceeds configured limit")
    records: list[dict[str, Any]] = []
    offset = 0
    while offset < len(payload):
        if len(records) >= int(limits["maximum_member_count"]):
            raise Bir300RemoteInventoryError("ZIP member count exceeded configured limit")
        if offset + CENTRAL_STRUCT.size > len(payload):
            raise Bir300RemoteInventoryError("truncated ZIP central-directory entry")
        unpacked = CENTRAL_STRUCT.unpack_from(payload, offset)
        (
            signature,
            _version_made,
            _version_needed,
            flags,
            compression_method,
            _mod_time,
            _mod_date,
            crc32,
            compressed_size,
            uncompressed_size,
            filename_length,
            extra_length,
            comment_length,
            disk_start,
            _internal_attributes,
            _external_attributes,
            local_header_offset,
        ) = unpacked
        if signature != CENTRAL_SIGNATURE:
            raise Bir300RemoteInventoryError(
                f"unexpected central-directory signature at offset {offset}"
            )
        if disk_start != 0:
            raise Bir300RemoteInventoryError("multi-disk member requires separate review")
        if (
            compressed_size == ZIP64_SENTINEL_32
            or uncompressed_size == ZIP64_SENTINEL_32
            or local_header_offset == ZIP64_SENTINEL_32
        ):
            raise Bir300RemoteInventoryError("ZIP64 member metadata requires separate review")
        if filename_length > int(limits["maximum_filename_bytes"]):
            raise Bir300RemoteInventoryError("ZIP member filename exceeds configured limit")
        if extra_length > int(limits["maximum_extra_bytes"]):
            raise Bir300RemoteInventoryError("ZIP member extra field exceeds configured limit")
        if comment_length > int(limits["maximum_comment_bytes"]):
            raise Bir300RemoteInventoryError("ZIP member comment exceeds configured limit")
        variable_start = offset + CENTRAL_STRUCT.size
        variable_end = variable_start + filename_length + extra_length + comment_length
        if variable_end > len(payload):
            raise Bir300RemoteInventoryError("ZIP central-directory variable fields are truncated")
        raw_name = payload[variable_start : variable_start + filename_length]
        filename = _decode_filename(raw_name, flags)
        normalized_path = filename.replace("\\", "/")
        path = PurePosixPath(normalized_path)
        unsafe_path = path.is_absolute() or ".." in path.parts
        basename = path.name
        match = TVIPS_SERIES_RE.match(basename)
        series_prefix = match.group("prefix") if match else None
        frame_index = int(match.group("index")) if match else None
        suffix = path.suffix.casefold()
        records.append(
            {
                "member_path": normalized_path,
                "compressed_bytes": int(compressed_size),
                "uncompressed_bytes": int(uncompressed_size),
                "compression_method": int(compression_method),
                "crc32_hex": f"{crc32:08x}",
                "local_header_offset": int(local_header_offset),
                "unsafe_path": bool(unsafe_path),
                "is_directory": normalized_path.endswith("/"),
                "is_tvips": suffix == ".tvips",
                "tvips_series_prefix": series_prefix,
                "tvips_frame_index": frame_index,
                "is_tvips_main_header": bool(match and frame_index == 0),
            }
        )
        offset = variable_end
    if offset != len(payload):
        raise Bir300RemoteInventoryError("central-directory parser did not consume all bytes")
    if len(records) != expected_entries:
        raise Bir300RemoteInventoryError(
            f"central-directory entry count mismatch: {len(records)} != {expected_entries}"
        )
    return records


def summarize_inventory(
    records: list[dict[str, Any]],
    *,
    central_sha256: str,
) -> dict[str, Any]:
    tvips = [record for record in records if record["is_tvips"]]
    main_headers = [record for record in tvips if record["is_tvips_main_header"]]
    series: dict[str, set[int]] = {}
    unmatched_tvips = 0
    for record in tvips:
        prefix = record["tvips_series_prefix"]
        index = record["tvips_frame_index"]
        if prefix is None or index is None:
            unmatched_tvips += 1
            continue
        series.setdefault(str(prefix), set()).add(int(index))
    missing_main = sorted(prefix for prefix, indexes in series.items() if 0 not in indexes)
    return {
        "member_count": int(len(records)),
        "directory_entry_count": int(sum(bool(record["is_directory"]) for record in records)),
        "unsafe_path_count": int(sum(bool(record["unsafe_path"]) for record in records)),
        "tvips_member_count": int(len(tvips)),
        "tvips_series_count": int(len(series)),
        "tvips_main_header_count": int(len(main_headers)),
        "tvips_members_without_series_suffix_count": int(unmatched_tvips),
        "tvips_series_missing_main_header_count": int(len(missing_main)),
        "tvips_series_missing_main_header": missing_main,
        "tvips_main_header_paths": sorted(
            str(record["member_path"]) for record in main_headers
        ),
        "central_directory_sha256": central_sha256,
    }


def write_inventory_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "member_path",
        "compressed_bytes",
        "uncompressed_bytes",
        "compression_method",
        "crc32_hex",
        "local_header_offset",
        "unsafe_path",
        "is_directory",
        "is_tvips",
        "tvips_series_prefix",
        "tvips_frame_index",
        "is_tvips_main_header",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def run_audit(
    *,
    config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = validate_config(load_json(config_resolved))
    snapshot_path = Path(config["source_snapshot"])
    if not snapshot_path.is_absolute():
        snapshot_path = Path.cwd() / snapshot_path
    snapshot_path = snapshot_path.resolve(strict=True)
    snapshot = load_json(snapshot_path)
    target = resolve_target_from_snapshot(config, snapshot)
    archive_size = int(target["bytes"])
    limits = config["range_limits"]

    tail_probe = min(int(limits["tail_probe_bytes"]), archive_size)
    tail_start = archive_size - tail_probe
    tail = fetch_range(
        target["content_url"],
        start=tail_start,
        end=archive_size - 1,
        expected_total=archive_size,
    )
    eocd = parse_eocd(tail, archive_size=archive_size)
    if eocd["central_directory_bytes"] > int(limits["maximum_central_directory_bytes"]):
        raise Bir300RemoteInventoryError("central directory exceeds configured byte limit")
    if eocd["entries_total"] > int(limits["maximum_member_count"]):
        raise Bir300RemoteInventoryError("member count exceeds configured limit")
    central_start = eocd["central_directory_offset"]
    central_end = central_start + eocd["central_directory_bytes"] - 1
    central = fetch_range(
        target["content_url"],
        start=central_start,
        end=central_end,
        expected_total=archive_size,
    )
    central_sha256 = hashlib.sha256(central).hexdigest()
    records = parse_central_directory(
        central,
        expected_entries=eocd["entries_total"],
        limits=limits,
    )
    inventory_summary = summarize_inventory(records, central_sha256=central_sha256)
    if inventory_summary["unsafe_path_count"]:
        raise Bir300RemoteInventoryError("archive central directory contains unsafe member paths")

    output = Path(output_dir).expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    inventory_path = output / "remote_member_inventory.csv"
    write_inventory_csv(inventory_path, records)
    snapshot_out = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "remote_central_directory_inventory_completed",
        "source": {
            "record_id": snapshot["source"]["record_id"],
            "doi": snapshot["source"]["doi"],
            "license_id": snapshot["source"]["license_id"],
            "source_snapshot_sha256": sha256_file(snapshot_path),
        },
        "target_archive": {
            "key": target["key"],
            "bytes": archive_size,
            "repository_md5": target["md5"],
            "repository_md5_recomputed": False,
        },
        "http_range_evidence": {
            "range_support_verified": True,
            "tail_bytes_read": int(len(tail)),
            "central_directory_bytes_read": int(len(central)),
            "total_remote_bytes_read": int(len(tail) + len(central)),
            "full_archive_downloaded": False,
            "member_payload_bytes_read": False,
        },
        "zip_structure": eocd,
        "inventory_summary": inventory_summary,
        "outputs": {
            "member_inventory": inventory_path.name,
            "member_inventory_sha256": sha256_file(inventory_path),
        },
        "evidence_assessment": {
            "archive_member_name_and_central_directory_inventory": "Supported",
            "tvips_series_structure": (
                "Supported" if inventory_summary["tvips_member_count"] > 0 else "Unsupported"
            ),
            "tvips_main_header_series_presence": (
                "Supported" if inventory_summary["tvips_main_header_count"] > 0 else "Unsupported"
            ),
            "tvips_header_payload_metadata": "Inconclusive",
            "sample_and_acquisition_lineage": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "reference_reflection_truth": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "tvips_format_inventory_ready": bool(inventory_summary["tvips_member_count"] > 0),
            "selected_member_header_inspection_authorized": False,
            "analyzer_execution_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": [
            "Review whether each discovered TVIPS series has a _000.tvips main header required by established TVIPS readers.",
            "If series structure is viable, authorize only the minimum selected .tvips header/payload range needed to test metadata extraction with an established TVIPS reader; do not download every archive.",
            "Require explicit pattern-centre and reciprocal-calibration evidence before any quantitative SAED indexing validation.",
            "Treat member paths as format inventory only, not immutable sample or acquisition lineage."
        ],
        "scientific_boundary": (
            "This audit reads only ZIP tail/central-directory byte ranges and member metadata. "
            "It does not read TVIPS member payloads, diffraction pixels, or calibration headers, "
            "and it creates no analyzer-performance or phase-indexing evidence."
        ),
        "config_sha256": sha256_file(config_resolved),
    }
    (output / "remote_inventory_snapshot.json").write_text(
        json.dumps(snapshot_out, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return snapshot_out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read only remote ZIP tail and central-directory byte ranges for the smallest "
            "BIR-MicroED 300 keV archive. Full-download fallback is prohibited."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "case_studies/zenodo_bir_300kev_saed_remote_inventory/case_config.json"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_audit(config_path=args.config, output_dir=args.output)
    except (
        OSError,
        ValueError,
        urllib.error.HTTPError,
        urllib.error.URLError,
        Bir300RemoteInventoryError,
    ) as exc:
        print(f"BIR 300 keV remote inventory failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
