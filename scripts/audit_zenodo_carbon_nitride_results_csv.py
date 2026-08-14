from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import struct
import urllib.parse
import zlib
from pathlib import Path
from typing import Any, Mapping

if __package__:
    from scripts.audit_zenodo_bir_300kev_remote_inventory import fetch_range
else:
    from audit_zenodo_bir_300kev_remote_inventory import fetch_range

SCHEMA_VERSION = "1.0"
_LOCAL_FILE_HEADER_SIGNATURE = 0x04034B50


class CarbonNitrideResultsCsvAuditError(RuntimeError):
    """Raised when the selected ZIP member audit violates its bounded contract."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CarbonNitrideResultsCsvAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise CarbonNitrideResultsCsvAuditError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise CarbonNitrideResultsCsvAuditError("JSON root must be an object")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        "selected_member",
        "limits",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != required or value.get("schema_version") != SCHEMA_VERSION:
        raise CarbonNitrideResultsCsvAuditError("config keys/schema do not match contract")
    archive = value["target_archive"]
    if not isinstance(archive, dict) or archive != {
        "key": "Whole dataset.zip",
        "expected_bytes": 561160882,
        "expected_md5": "b608d86084ccbbea802ff54c3f98380e",
    }:
        raise CarbonNitrideResultsCsvAuditError("target archive does not match pinned metadata")
    member = value["selected_member"]
    expected_member_keys = {
        "member_path",
        "local_header_offset",
        "compression_method",
        "compressed_bytes",
        "uncompressed_bytes",
        "crc32_hex",
    }
    if not isinstance(member, dict) or set(member) != expected_member_keys:
        raise CarbonNitrideResultsCsvAuditError("selected_member keys do not match contract")
    if member["member_path"] != "Zenodo/Segmented images/CN-1-Na_20000x/results.csv":
        raise CarbonNitrideResultsCsvAuditError("selected member path is not pinned")
    if member["local_header_offset"] != 480651532:
        raise CarbonNitrideResultsCsvAuditError("selected member local-header offset is not pinned")
    if member["compression_method"] != 8:
        raise CarbonNitrideResultsCsvAuditError("selected member compression method is not pinned")
    if member["compressed_bytes"] != 10881 or member["uncompressed_bytes"] != 35135:
        raise CarbonNitrideResultsCsvAuditError("selected member byte counts are not pinned")
    if member["crc32_hex"] != "62f263da":
        raise CarbonNitrideResultsCsvAuditError("selected member CRC32 is not pinned")

    limits = value["limits"]
    expected_limits = {
        "maximum_local_header_bytes",
        "maximum_compressed_member_bytes",
        "maximum_uncompressed_member_bytes",
        "maximum_csv_rows",
        "maximum_csv_columns",
        "maximum_cell_characters",
    }
    if not isinstance(limits, dict) or set(limits) != expected_limits:
        raise CarbonNitrideResultsCsvAuditError("limits keys do not match contract")
    for key, observed in limits.items():
        if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
            raise CarbonNitrideResultsCsvAuditError(f"limit must be positive: {key}")
    if member["compressed_bytes"] > limits["maximum_compressed_member_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected member exceeds compressed-byte limit")
    if member["uncompressed_bytes"] > limits["maximum_uncompressed_member_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected member exceeds uncompressed-byte limit")

    boundary = value["scientific_boundary"]
    true_keys = {"http_range_member_probe_authorized", "selected_csv_member_content_authorized"}
    if not isinstance(boundary, dict) or any(boundary.get(key) is not True for key in true_keys):
        raise CarbonNitrideResultsCsvAuditError("selected CSV member access is not authorized")
    if any(observed is not False for key, observed in boundary.items() if key not in true_keys):
        raise CarbonNitrideResultsCsvAuditError("stronger content/analyzer actions must remain disabled")
    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(observed is not True for observed in rules.values()):
        raise CarbonNitrideResultsCsvAuditError("all fail-closed decision rules must be enabled")
    return value


def resolve_archive(config: Mapping[str, Any], source_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    source = source_snapshot.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 21222653:
        raise CarbonNitrideResultsCsvAuditError("source snapshot is not the pinned carbon-nitride record")
    if source.get("license_id") != "cc-by-4.0":
        raise CarbonNitrideResultsCsvAuditError("source license differs from pinned metadata")
    files = source_snapshot.get("file_inventory")
    if not isinstance(files, list):
        raise CarbonNitrideResultsCsvAuditError("source file inventory is invalid")
    matches = [item for item in files if isinstance(item, Mapping) and item.get("key") == "Whole dataset.zip"]
    if len(matches) != 1:
        raise CarbonNitrideResultsCsvAuditError("target archive is not uniquely present")
    target = dict(matches[0])
    if target.get("bytes") != config["target_archive"]["expected_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("archive byte count drifted")
    if target.get("md5") != config["target_archive"]["expected_md5"]:
        raise CarbonNitrideResultsCsvAuditError("archive MD5 drifted")
    url = target.get("content_url")
    if not isinstance(url, str):
        raise CarbonNitrideResultsCsvAuditError("archive content URL is missing")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise CarbonNitrideResultsCsvAuditError("archive content URL left trusted Zenodo")
    return target


def parse_local_header(header: bytes, *, expected_member: Mapping[str, Any], limits: Mapping[str, Any]) -> dict[str, Any]:
    if len(header) != 30:
        raise CarbonNitrideResultsCsvAuditError("local ZIP header probe must be exactly 30 bytes")
    (
        signature,
        version_needed,
        flags,
        compression_method,
        mod_time,
        mod_date,
        crc32_header,
        compressed_size_header,
        uncompressed_size_header,
        filename_length,
        extra_length,
    ) = struct.unpack("<IHHHHHIIIHH", header)
    if signature != _LOCAL_FILE_HEADER_SIGNATURE:
        raise CarbonNitrideResultsCsvAuditError("selected member local-header signature mismatch")
    if flags & 0x0001:
        raise CarbonNitrideResultsCsvAuditError("encrypted ZIP members are prohibited")
    if compression_method not in {0, 8} or compression_method != expected_member["compression_method"]:
        raise CarbonNitrideResultsCsvAuditError("selected member compression method mismatch")
    if filename_length <= 0 or filename_length > limits["maximum_local_header_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected member filename length exceeds bounded header limit")
    if extra_length > limits["maximum_local_header_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected member extra-field length exceeds bounded header limit")
    return {
        "version_needed": version_needed,
        "flags": flags,
        "compression_method": compression_method,
        "mod_time": mod_time,
        "mod_date": mod_date,
        "crc32_header_hex": f"{crc32_header:08x}",
        "compressed_size_header": compressed_size_header,
        "uncompressed_size_header": uncompressed_size_header,
        "filename_length": filename_length,
        "extra_length": extra_length,
    }


def decode_member_name(value: bytes, *, flags: int) -> str:
    encoding = "utf-8" if flags & 0x0800 else "cp437"
    try:
        return value.decode(encoding)
    except UnicodeDecodeError as exc:
        raise CarbonNitrideResultsCsvAuditError("selected member filename cannot be decoded") from exc


def decompress_selected_member(compressed: bytes, *, member: Mapping[str, Any]) -> bytes:
    method = member["compression_method"]
    try:
        if method == 0:
            raw = compressed
        elif method == 8:
            raw = zlib.decompress(compressed, -zlib.MAX_WBITS)
        else:
            raise CarbonNitrideResultsCsvAuditError("unsupported selected-member compression method")
    except zlib.error as exc:
        raise CarbonNitrideResultsCsvAuditError("selected member deflate stream is invalid") from exc
    if len(raw) != member["uncompressed_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected member decompressed length mismatch")
    crc = zlib.crc32(raw) & 0xFFFFFFFF
    if f"{crc:08x}" != member["crc32_hex"]:
        raise CarbonNitrideResultsCsvAuditError("selected member CRC32 mismatch")
    return raw


def parse_csv(raw: bytes, *, limits: Mapping[str, Any]) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CarbonNitrideResultsCsvAuditError("selected CSV is not UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not reader.fieldnames:
        raise CarbonNitrideResultsCsvAuditError("selected CSV has no header")
    columns = [str(value) for value in reader.fieldnames]
    if len(columns) > limits["maximum_csv_columns"]:
        raise CarbonNitrideResultsCsvAuditError("selected CSV exceeds column limit")
    if len(set(columns)) != len(columns):
        raise CarbonNitrideResultsCsvAuditError("selected CSV contains duplicate column names")
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader, start=1):
        if index > limits["maximum_csv_rows"]:
            raise CarbonNitrideResultsCsvAuditError("selected CSV exceeds row limit")
        normalized: dict[str, str] = {}
        for column in columns:
            value = row.get(column)
            cell = "" if value is None else str(value)
            if len(cell) > limits["maximum_cell_characters"]:
                raise CarbonNitrideResultsCsvAuditError("selected CSV cell exceeds character limit")
            normalized[column] = cell
        rows.append(normalized)
    if not rows:
        raise CarbonNitrideResultsCsvAuditError("selected CSV has no data rows")

    nonempty_counts = {column: sum(bool(row[column].strip()) for row in rows) for column in columns}
    numeric_counts: dict[str, int] = {}
    for column in columns:
        count = 0
        for row in rows:
            cell = row[column].strip()
            if not cell:
                continue
            try:
                float(cell)
            except ValueError:
                continue
            count += 1
        numeric_counts[column] = count
    return {
        "text": text,
        "columns": columns,
        "row_count": len(rows),
        "nonempty_counts": nonempty_counts,
        "numeric_counts": numeric_counts,
        "first_row": rows[0],
    }


def classify_csv_semantics(summary: Mapping[str, Any]) -> dict[str, str]:
    columns = [str(value).casefold() for value in summary["columns"]]
    object_measurement_terms = {
        "area",
        "perimeter",
        "centroid",
        "diameter",
        "eccentricity",
        "solidity",
        "orientation",
        "label",
        "object",
    }
    matching = sorted(
        {term for term in object_measurement_terms if any(term in column for column in columns)}
    )
    return {
        "csv_role_as_segmentation_object_measurement_output": (
            "Supported" if matching else "Inconclusive"
        ),
        "independent_human_annotation_protocol": "Inconclusive",
        "independent_ground_truth_mask_status": "Inconclusive",
        "annotation_provenance": "Inconclusive",
        "annotation_completeness_across_15_raw_groups": "Unsupported",
        "co3o4_external_validation_use": "Unsupported",
        "scientific_evidence_level": "Diagnostic",
        "matching_object_measurement_terms": ",".join(matching),
    }


def run_audit(*, config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_file = Path(config_path).expanduser().resolve(strict=True)
    config = validate_config(load_json(config_file))
    source_snapshot_file = Path(config["source_snapshot"]).expanduser()
    if not source_snapshot_file.is_absolute():
        source_snapshot_file = (config_file.parent / source_snapshot_file).resolve(strict=True)
    source_snapshot = load_json(source_snapshot_file)
    archive = resolve_archive(config, source_snapshot)
    member = config["selected_member"]
    limits = config["limits"]
    archive_size = int(archive["bytes"])

    header_start = int(member["local_header_offset"])
    header = fetch_range(str(archive["content_url"]), start=header_start, end=header_start + 29, expected_total=archive_size)
    local = parse_local_header(header, expected_member=member, limits=limits)
    name_extra_bytes = int(local["filename_length"]) + int(local["extra_length"])
    if 30 + name_extra_bytes > limits["maximum_local_header_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected member local header exceeds byte limit")
    name_extra = fetch_range(
        str(archive["content_url"]),
        start=header_start + 30,
        end=header_start + 30 + name_extra_bytes - 1,
        expected_total=archive_size,
    )
    filename_bytes = name_extra[: local["filename_length"]]
    member_name = decode_member_name(filename_bytes, flags=int(local["flags"]))
    if member_name != member["member_path"]:
        raise CarbonNitrideResultsCsvAuditError("selected member local filename mismatch")
    data_start = header_start + 30 + name_extra_bytes
    data_end = data_start + int(member["compressed_bytes"]) - 1
    compressed = fetch_range(
        str(archive["content_url"]),
        start=data_start,
        end=data_end,
        expected_total=archive_size,
    )
    if len(compressed) != member["compressed_bytes"]:
        raise CarbonNitrideResultsCsvAuditError("selected compressed member length mismatch")
    raw = decompress_selected_member(compressed, member=member)
    parsed = parse_csv(raw, limits=limits)
    semantics = classify_csv_semantics(parsed)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    selected_csv = output / "selected_results.csv"
    selected_csv.write_bytes(raw)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "bounded_selected_csv_member_completed",
        "source_snapshot": {
            "path": config["source_snapshot"],
            "sha256": sha256_file(source_snapshot_file),
        },
        "target_archive": {
            "key": archive["key"],
            "bytes": archive_size,
            "md5": archive["md5"],
        },
        "selected_member": {
            **member,
            "local_header_flags": local["flags"],
            "local_header_version_needed": local["version_needed"],
            "content_sha256": sha256_bytes(raw),
        },
        "range_probe": {
            "local_header_bytes": len(header) + len(name_extra),
            "compressed_member_bytes": len(compressed),
            "network_bytes_retrieved": len(header) + len(name_extra) + len(compressed),
            "archive_fraction_retrieved": (
                len(header) + len(name_extra) + len(compressed)
            )
            / archive_size,
        },
        "csv_summary": {
            "columns": parsed["columns"],
            "row_count": parsed["row_count"],
            "nonempty_counts": parsed["nonempty_counts"],
            "numeric_counts": parsed["numeric_counts"],
            "first_row": parsed["first_row"],
        },
        "evidence_assessment": semantics,
        "next_evidence": [
            "Treat this CSV as one segmented-example result artifact only; do not infer a human annotation protocol from numeric/object columns.",
            "Do not download image members unless a named representation or mapping question remains after the CSV semantics are resolved.",
            "If segmentation robustness is pursued, establish source-to-raw-image mapping for the selected example and annotation-generation provenance before comparing masks.",
            "Keep all carbon-nitride results outside the Co3O4 in-domain external-validation claim."
        ],
        "scientific_boundary": config["scientific_boundary"],
        "decision_rules": config["decision_rules"],
        "config_sha256": sha256_file(config_file),
        "source_archive_downloaded": False,
        "other_member_content_downloaded": False,
        "image_member_content_downloaded": False,
        "pixel_array_access_performed": False,
        "analyzer_inference_performed": False,
        "external_validation_claim_made": False,
        "engineering_decision_claim_made": False,
    }
    (output / "verified_results_csv_snapshot.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve exactly one pinned small results.csv ZIP member by HTTP Range, verify "
            "its ZIP metadata/CRC, and summarize its tabular semantics. Image member access is prohibited."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    snapshot = run_audit(config_path=args.config, output_dir=args.output)
    print(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
