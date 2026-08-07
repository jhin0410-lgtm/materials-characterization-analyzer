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
TVIPS_SPLIT_RE = re.compile(r"^(?P<prefix>.*)_(?P<index>\d{3})\.tvips$", re.IGNORECASE)
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
ZIP64_16 = 0xFFFF
ZIP64_32 = 0xFFFFFFFF


class Bir300RemoteInventoryError(RuntimeError):
    """Raised when bounded remote inventory or its evidence contract fails."""


def _load_json(path: str | Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise Bir300RemoteInventoryError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=reject_duplicates)
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


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "source_snapshot",
        "target_archive",
        "range_limits",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise Bir300RemoteInventoryError("remote inventory config keys/schema do not match contract")

    archive = value["target_archive"]
    if not isinstance(archive, dict) or set(archive) != {"key", "expected_bytes", "expected_md5"}:
        raise Bir300RemoteInventoryError("target_archive keys do not match contract")
    if not isinstance(archive["key"], str) or not archive["key"]:
        raise Bir300RemoteInventoryError("target archive key is invalid")
    if not isinstance(archive["expected_bytes"], int) or archive["expected_bytes"] <= 0:
        raise Bir300RemoteInventoryError("target archive byte count is invalid")
    md5 = archive["expected_md5"]
    if not isinstance(md5, str) or not re.fullmatch(r"[0-9a-f]{32}", md5):
        raise Bir300RemoteInventoryError("target archive MD5 is invalid")

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
    for key in expected_limits:
        if not isinstance(limits[key], int) or limits[key] <= 0:
            raise Bir300RemoteInventoryError(f"range limit must be positive: {key}")
    if limits["tail_probe_bytes"] < 65557:
        raise Bir300RemoteInventoryError("tail probe is too small for maximal ZIP EOCD/comment")

    boundary = value["scientific_boundary"]
    if not isinstance(boundary, dict):
        raise Bir300RemoteInventoryError("scientific_boundary must be an object")
    true_keys = {"http_range_metadata_probe_authorized", "central_directory_inventory_authorized"}
    if any(boundary.get(key) is not True for key in true_keys):
        raise Bir300RemoteInventoryError("bounded central-directory probing is not authorized")
    if any(value is not False for key, value in boundary.items() if key not in true_keys):
        raise Bir300RemoteInventoryError("stronger source/analyzer actions must remain disabled")

    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise Bir300RemoteInventoryError("all fail-closed decision rules must be enabled")
    return value


def resolve_target(config: Mapping[str, Any], source_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if source_snapshot.get("execution_status") != "metadata_audit_completed":
        raise Bir300RemoteInventoryError("source snapshot is not a completed metadata audit")
    source = source_snapshot.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 10995139:
        raise Bir300RemoteInventoryError("source snapshot is not the pinned BIR record")
    if source.get("license_id") != "cc-by-4.0":
        raise Bir300RemoteInventoryError("dataset reuse terms differ from pinned metadata evidence")

    inventory = source_snapshot.get("file_inventory")
    if not isinstance(inventory, list):
        raise Bir300RemoteInventoryError("source file inventory is invalid")
    archive_config = config["target_archive"]
    matches = [
        item
        for item in inventory
        if isinstance(item, Mapping) and item.get("key") == archive_config["key"]
    ]
    if len(matches) != 1:
        raise Bir300RemoteInventoryError("target archive is not uniquely present")
    target = dict(matches[0])
    if target.get("bytes") != archive_config["expected_bytes"]:
        raise Bir300RemoteInventoryError("target archive byte count drifted")
    if target.get("md5") != archive_config["expected_md5"]:
        raise Bir300RemoteInventoryError("target archive repository MD5 drifted")
    url = target.get("content_url")
    parsed = urllib.parse.urlparse(url if isinstance(url, str) else "")
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise Bir300RemoteInventoryError("target archive URL is outside trusted Zenodo")
    return target


def _parse_content_range(value: str | None) -> tuple[int, int, int]:
    if not value:
        raise Bir300RemoteInventoryError("HTTP 206 omitted Content-Range")
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if match is None:
        raise Bir300RemoteInventoryError(f"invalid Content-Range: {value!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def fetch_range(url: str, *, start: int, end: int, expected_total: int) -> bytes:
    if start < 0 or end < start or end >= expected_total:
        raise Bir300RemoteInventoryError("requested range is outside pinned archive")
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
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in {"zenodo.org", "www.zenodo.org"}:
            raise Bir300RemoteInventoryError("range response redirected outside trusted Zenodo")
        observed = _parse_content_range(response.headers.get("Content-Range"))
        if observed != (start, end, expected_total):
            raise Bir300RemoteInventoryError("range response interval/size differs from pinned request")
        if response.headers.get("Content-Encoding") not in {None, "", "identity"}:
            raise Bir300RemoteInventoryError("range response unexpectedly applied content encoding")
        expected_length = end - start + 1
        payload = response.read(expected_length + 1)
        if len(payload) != expected_length:
            raise Bir300RemoteInventoryError("range response byte count is incorrect")
        return payload


def parse_eocd(tail: bytes, *, archive_size: int) -> dict[str, int]:
    position = tail.rfind(EOCD_SIGNATURE)
    if position < 0 or position + EOCD_STRUCT.size > len(tail):
        raise Bir300RemoteInventoryError("valid ZIP EOCD was not found in bounded tail")
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
        raise Bir300RemoteInventoryError("invalid EOCD signature")
    if position + EOCD_STRUCT.size + comment_length != len(tail):
        raise Bir300RemoteInventoryError("EOCD does not terminate at archive end")
    if disk_number != 0 or central_disk != 0 or entries_on_disk != entries_total:
        raise Bir300RemoteInventoryError("multi-disk ZIP requires separate review")
    if entries_total == ZIP64_16 or central_size == ZIP64_32 or central_offset == ZIP64_32:
        raise Bir300RemoteInventoryError("ZIP64 central directory requires separate review")
    if entries_total <= 0 or central_size <= 0:
        raise Bir300RemoteInventoryError("central directory is empty")
    if central_offset + central_size > archive_size - EOCD_STRUCT.size:
        raise Bir300RemoteInventoryError("central directory lies outside pinned archive")
    return {
        "entries_total": int(entries_total),
        "central_directory_bytes": int(central_size),
        "central_directory_offset": int(central_offset),
        "comment_bytes": int(comment_length),
    }


def parse_central_directory(
    payload: bytes,
    *,
    expected_entries: int,
    limits: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if expected_entries > int(limits["maximum_member_count"]):
        raise Bir300RemoteInventoryError("member count exceeds configured limit")
    records: list[dict[str, Any]] = []
    offset = 0
    while offset < len(payload):
        if offset + CENTRAL_STRUCT.size > len(payload):
            raise Bir300RemoteInventoryError("truncated central-directory entry")
        fields = CENTRAL_STRUCT.unpack_from(payload, offset)
        (
            signature,
            _made,
            _needed,
            flags,
            compression,
            _mtime,
            _mdate,
            crc32,
            compressed,
            uncompressed,
            filename_len,
            extra_len,
            comment_len,
            disk_start,
            _internal,
            _external,
            local_offset,
        ) = fields
        if signature != CENTRAL_SIGNATURE:
            raise Bir300RemoteInventoryError(f"unexpected central signature at {offset}")
        if disk_start != 0:
            raise Bir300RemoteInventoryError("multi-disk member requires separate review")
        if compressed == ZIP64_32 or uncompressed == ZIP64_32 or local_offset == ZIP64_32:
            raise Bir300RemoteInventoryError("ZIP64 member metadata requires separate review")
        if filename_len > int(limits["maximum_filename_bytes"]):
            raise Bir300RemoteInventoryError("member filename exceeds configured limit")
        if extra_len > int(limits["maximum_extra_bytes"]):
            raise Bir300RemoteInventoryError("member extra field exceeds configured limit")
        if comment_len > int(limits["maximum_comment_bytes"]):
            raise Bir300RemoteInventoryError("member comment exceeds configured limit")
        variable_start = offset + CENTRAL_STRUCT.size
        variable_end = variable_start + filename_len + extra_len + comment_len
        if variable_end > len(payload):
            raise Bir300RemoteInventoryError("central-directory variable fields are truncated")
        raw_name = payload[variable_start : variable_start + filename_len]
        encoding = "utf-8" if flags & 0x0800 else "cp437"
        try:
            filename = raw_name.decode(encoding, errors="strict").replace("\\", "/")
        except UnicodeDecodeError as exc:
            raise Bir300RemoteInventoryError("member filename is not decodable") from exc
        path = PurePosixPath(filename)
        basename = path.name
        split_match = TVIPS_SPLIT_RE.match(basename)
        split_prefix = split_match.group("prefix") if split_match else None
        split_index = int(split_match.group("index")) if split_match else None
        records.append(
            {
                "member_path": filename,
                "compressed_bytes": int(compressed),
                "uncompressed_bytes": int(uncompressed),
                "compression_method": int(compression),
                "crc32_hex": f"{crc32:08x}",
                "local_header_offset": int(local_offset),
                "unsafe_path": bool(path.is_absolute() or ".." in path.parts),
                "is_directory": filename.endswith("/"),
                "is_tvips": path.suffix.casefold() == ".tvips",
                "tvips_split_prefix": split_prefix,
                "tvips_split_index": split_index,
                "is_tvips_split_main_file": bool(split_match and split_index == 0),
            }
        )
        offset = variable_end
    if offset != len(payload) or len(records) != expected_entries:
        raise Bir300RemoteInventoryError("central-directory size/member count mismatch")
    return records


def summarize_inventory(records: list[dict[str, Any]], *, central_sha256: str) -> dict[str, Any]:
    tvips = [record for record in records if record["is_tvips"]]
    split_members = [record for record in tvips if record["tvips_split_index"] is not None]
    main_files = [record for record in split_members if record["is_tvips_split_main_file"]]
    split_series: dict[str, set[int]] = {}
    for record in split_members:
        split_series.setdefault(str(record["tvips_split_prefix"]), set()).add(
            int(record["tvips_split_index"])
        )
    missing_main = sorted(prefix for prefix, indexes in split_series.items() if 0 not in indexes)
    return {
        "member_count": int(len(records)),
        "directory_entry_count": int(sum(bool(record["is_directory"]) for record in records)),
        "unsafe_path_count": int(sum(bool(record["unsafe_path"]) for record in records)),
        "tvips_member_count": int(len(tvips)),
        "tvips_split_stream_member_count": int(len(split_members)),
        "tvips_split_stream_series_count": int(len(split_series)),
        "tvips_split_stream_main_file_count": int(len(main_files)),
        "tvips_nonstandard_filename_count": int(len(tvips) - len(split_members)),
        "tvips_split_series_missing_main_count": int(len(missing_main)),
        "tvips_split_series_missing_main": missing_main,
        "tvips_split_main_paths": sorted(str(record["member_path"]) for record in main_files),
        "tvips_member_paths": sorted(str(record["member_path"]) for record in tvips),
        "central_directory_sha256": central_sha256,
    }


def write_inventory_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(records[0]) if records else ["member_path"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def run_audit(*, config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_path = Path(config_path).expanduser().resolve(strict=True)
    config = validate_config(_load_json(config_path))
    source_snapshot_path = Path(config["source_snapshot"])
    if not source_snapshot_path.is_absolute():
        source_snapshot_path = Path.cwd() / source_snapshot_path
    source_snapshot_path = source_snapshot_path.resolve(strict=True)
    source_snapshot = _load_json(source_snapshot_path)
    target = resolve_target(config, source_snapshot)
    archive_size = int(target["bytes"])
    limits = config["range_limits"]

    tail_bytes = min(int(limits["tail_probe_bytes"]), archive_size)
    tail = fetch_range(
        target["content_url"],
        start=archive_size - tail_bytes,
        end=archive_size - 1,
        expected_total=archive_size,
    )
    eocd = parse_eocd(tail, archive_size=archive_size)
    if eocd["central_directory_bytes"] > int(limits["maximum_central_directory_bytes"]):
        raise Bir300RemoteInventoryError("central directory exceeds configured byte limit")
    central_start = eocd["central_directory_offset"]
    central = fetch_range(
        target["content_url"],
        start=central_start,
        end=central_start + eocd["central_directory_bytes"] - 1,
        expected_total=archive_size,
    )
    central_sha256 = hashlib.sha256(central).hexdigest()
    records = parse_central_directory(
        central,
        expected_entries=eocd["entries_total"],
        limits=limits,
    )
    summary = summarize_inventory(records, central_sha256=central_sha256)
    if summary["unsafe_path_count"]:
        raise Bir300RemoteInventoryError("archive contains unsafe member paths")

    output = Path(output_dir).expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    inventory_path = output / "remote_member_inventory.csv"
    write_inventory_csv(inventory_path, records)

    tvips_present = summary["tvips_member_count"] > 0
    split_compatible = (
        summary["tvips_split_stream_series_count"] > 0
        and summary["tvips_split_series_missing_main_count"] == 0
    )
    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "remote_central_directory_inventory_completed",
        "source": {
            "record_id": source_snapshot["source"]["record_id"],
            "doi": source_snapshot["source"]["doi"],
            "license_id": source_snapshot["source"]["license_id"],
            "source_snapshot_sha256": sha256_file(source_snapshot_path),
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
        "inventory_summary": summary,
        "outputs": {
            "member_inventory": inventory_path.name,
            "member_inventory_sha256": sha256_file(inventory_path),
        },
        "evidence_assessment": {
            "archive_member_name_and_central_directory_inventory": "Supported",
            "tvips_member_presence": "Supported" if tvips_present else "Unsupported",
            "hyperspy_split_stream_filename_compatibility": (
                "Supported" if split_compatible else "Unsupported"
            ),
            "tvips_internal_header_validity": "Inconclusive",
            "tvips_header_payload_metadata": "Inconclusive",
            "sample_and_acquisition_lineage": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "reference_reflection_truth": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "tvips_member_inventory_ready": bool(tvips_present),
            "hyperspy_split_stream_naming_ready": bool(split_compatible),
            "selected_member_header_inspection_authorized": False,
            "analyzer_execution_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": [
            "Do not infer an absent internal TVIPS header from filename structure alone.",
            "Because the discovered TVIPS filenames are not proven compatible with the established *_000.tvips split-stream convention, do not authorize a full archive download merely to try the reader.",
            "If further format evidence is justified, authorize a separate minimal member-prefix/header probe for one selected TVIPS member and compare the recovered header bytes with an established TVIPS parser contract.",
            "Require independent pattern-centre and reciprocal-calibration evidence before quantitative SAED indexing validation.",
            "Treat member paths as archive structure only, not immutable sample/acquisition lineage."
        ],
        "scientific_boundary": (
            "Only ZIP tail/central-directory metadata were read. No TVIPS member payload, "
            "diffraction pixels, or calibration header bytes were accessed."
        ),
        "config_sha256": sha256_file(config_path),
    }
    (output / "remote_inventory_snapshot.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read only remote ZIP tail/central-directory ranges for the smallest "
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
