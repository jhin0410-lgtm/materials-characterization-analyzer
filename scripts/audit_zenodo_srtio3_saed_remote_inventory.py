from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_zenodo_bir_300kev_remote_inventory import (  # noqa: E402
    Bir300RemoteInventoryError,
    fetch_range,
    parse_central_directory,
    parse_eocd,
)


class SrTiO3SaedRemoteInventoryError(RuntimeError):
    """Raised when bounded SrTiO3 SAED archive inventory fails."""


def _load_json(path: str | Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SrTiO3SaedRemoteInventoryError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise SrTiO3SaedRemoteInventoryError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise SrTiO3SaedRemoteInventoryError("JSON root must be an object")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
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
        raise SrTiO3SaedRemoteInventoryError("remote inventory config keys/schema mismatch")
    archive = value["target_archive"]
    if not isinstance(archive, dict) or set(archive) != {"key", "expected_bytes", "expected_md5"}:
        raise SrTiO3SaedRemoteInventoryError("target archive contract is invalid")
    if archive.get("key") != "SAED.zip":
        raise SrTiO3SaedRemoteInventoryError("remote inventory must remain bounded to SAED.zip")
    if not isinstance(archive.get("expected_bytes"), int) or archive["expected_bytes"] <= 0:
        raise SrTiO3SaedRemoteInventoryError("target archive byte count is invalid")
    md5 = archive.get("expected_md5")
    if not isinstance(md5, str) or len(md5) != 32:
        raise SrTiO3SaedRemoteInventoryError("target archive MD5 is invalid")
    limits = value["range_limits"]
    required_limits = {
        "tail_probe_bytes",
        "maximum_central_directory_bytes",
        "maximum_member_count",
        "maximum_filename_bytes",
        "maximum_extra_bytes",
        "maximum_comment_bytes",
    }
    if not isinstance(limits, dict) or set(limits) != required_limits:
        raise SrTiO3SaedRemoteInventoryError("range limits are invalid")
    if any(not isinstance(limits[key], int) or limits[key] <= 0 for key in required_limits):
        raise SrTiO3SaedRemoteInventoryError("range limits must be positive integers")
    if limits["tail_probe_bytes"] < 65557:
        raise SrTiO3SaedRemoteInventoryError("tail probe is too small for ZIP EOCD/comment")
    boundary = value["scientific_boundary"]
    if not isinstance(boundary, dict):
        raise SrTiO3SaedRemoteInventoryError("scientific boundary must be an object")
    for key in ("http_range_metadata_probe_authorized", "central_directory_inventory_authorized"):
        if boundary.get(key) is not True:
            raise SrTiO3SaedRemoteInventoryError(f"bounded inventory action is not authorized: {key}")
    if any(
        item is not False
        for key, item in boundary.items()
        if key
        not in {
            "http_range_metadata_probe_authorized",
            "central_directory_inventory_authorized",
        }
    ):
        raise SrTiO3SaedRemoteInventoryError("stronger archive/analyzer actions must remain disabled")
    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise SrTiO3SaedRemoteInventoryError("all fail-closed decision rules must be enabled")
    return value


def _resolve_target(config: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot.get("execution_status") != "metadata_audit_completed":
        raise SrTiO3SaedRemoteInventoryError("source snapshot is not a completed metadata audit")
    source = snapshot.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 20300700:
        raise SrTiO3SaedRemoteInventoryError("source snapshot is not the pinned SrTiO3 record")
    if source.get("resource_type") != "dataset":
        raise SrTiO3SaedRemoteInventoryError("source record is no longer classified as dataset")
    if source.get("license_id") != "cc-by-4.0":
        raise SrTiO3SaedRemoteInventoryError("dataset reuse terms differ from pinned evidence")
    readiness = snapshot.get("readiness")
    if not isinstance(readiness, Mapping) or readiness.get("saed_archive_inventory_authorized") is not True:
        raise SrTiO3SaedRemoteInventoryError("source snapshot does not authorize SAED archive inventory")
    if readiness.get("four_d_stem_download_authorized") is not False:
        raise SrTiO3SaedRemoteInventoryError("4D-STEM boundary is not fail-closed")

    inventory = snapshot.get("file_inventory")
    if not isinstance(inventory, list):
        raise SrTiO3SaedRemoteInventoryError("source file inventory is invalid")
    expected = config["target_archive"]
    matches = [
        item
        for item in inventory
        if isinstance(item, Mapping) and item.get("key") == expected["key"]
    ]
    if len(matches) != 1:
        raise SrTiO3SaedRemoteInventoryError("SAED.zip is not uniquely present in source snapshot")
    target = dict(matches[0])
    if target.get("bytes") != expected["expected_bytes"]:
        raise SrTiO3SaedRemoteInventoryError("SAED.zip byte count drifted")
    if target.get("md5") != expected["expected_md5"]:
        raise SrTiO3SaedRemoteInventoryError("SAED.zip repository MD5 drifted")
    if not isinstance(target.get("content_url"), str):
        raise SrTiO3SaedRemoteInventoryError("SAED.zip content URL is missing")
    return target


def _extension(path: str) -> str:
    pure = PurePosixPath(path)
    if path.endswith("/"):
        return "<directory>"
    suffix = pure.suffix.casefold()
    return suffix if suffix else "<none>"


def _summarize(records: list[dict[str, Any]], central_sha256: str) -> dict[str, Any]:
    files = [record for record in records if not record["is_directory"]]
    extensions = Counter(_extension(str(record["member_path"])) for record in files)
    return {
        "member_count": int(len(records)),
        "file_member_count": int(len(files)),
        "directory_entry_count": int(sum(bool(record["is_directory"]) for record in records)),
        "unsafe_path_count": int(sum(bool(record["unsafe_path"]) for record in records)),
        "extension_counts": dict(sorted(extensions.items())),
        "member_paths": sorted(str(record["member_path"]) for record in files),
        "central_directory_sha256": central_sha256,
    }


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "member_path",
        "compressed_bytes",
        "uncompressed_bytes",
        "compression_method",
        "crc32_hex",
        "local_header_offset",
        "unsafe_path",
        "is_directory",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)


def run_audit(*, config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    source_snapshot_path = Path(config["source_snapshot"])
    if not source_snapshot_path.is_absolute():
        source_snapshot_path = (Path.cwd() / source_snapshot_path).resolve(strict=True)
    snapshot = _load_json(source_snapshot_path)
    target = _resolve_target(config, snapshot)

    archive_size = int(target["bytes"])
    tail_bytes = min(int(config["range_limits"]["tail_probe_bytes"]), archive_size)
    try:
        tail = fetch_range(
            target["content_url"],
            start=archive_size - tail_bytes,
            end=archive_size - 1,
            expected_total=archive_size,
        )
        eocd = parse_eocd(tail, archive_size=archive_size)
        central_bytes = int(eocd["central_directory_bytes"])
        if central_bytes > int(config["range_limits"]["maximum_central_directory_bytes"]):
            raise SrTiO3SaedRemoteInventoryError("central directory exceeds configured byte limit")
        central_start = int(eocd["central_directory_offset"])
        central = fetch_range(
            target["content_url"],
            start=central_start,
            end=central_start + central_bytes - 1,
            expected_total=archive_size,
        )
        records = parse_central_directory(
            central,
            expected_entries=int(eocd["entries_total"]),
            limits=config["range_limits"],
        )
    except Bir300RemoteInventoryError as exc:
        raise SrTiO3SaedRemoteInventoryError(str(exc)) from exc

    summary = _summarize(records, _sha256_bytes(central))
    if summary["unsafe_path_count"] != 0:
        raise SrTiO3SaedRemoteInventoryError("SAED.zip contains unsafe member paths")

    output_root = Path(output_dir).expanduser().resolve(strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    inventory_path = output_root / "remote_member_inventory.csv"
    _write_csv(inventory_path, records)

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "remote_central_directory_inventory_completed",
        "config_sha256": _sha256_file(config_resolved),
        "source_snapshot_sha256": _sha256_file(source_snapshot_path),
        "source": {
            "record_id": 20300700,
            "doi": "10.5281/zenodo.20300700",
            "license_id": "cc-by-4.0",
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
            "four_d_stem_bytes_read": False,
        },
        "zip_structure": {
            "entries_total": int(eocd["entries_total"]),
            "central_directory_bytes": central_bytes,
            "central_directory_offset": central_start,
            "comment_bytes": int(eocd["comment_bytes"]),
        },
        "inventory_summary": summary,
        "outputs": {"member_inventory_sha256": _sha256_file(inventory_path)},
        "evidence_assessment": {
            "archive_member_name_and_central_directory_inventory": "Supported",
            "saed_representation_classification_from_names_only": "Diagnostic",
            "raw_detector_native_intensity": "Inconclusive",
            "pattern_count_and_acquisition_independence": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "reference_reflection_truth": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "member_inventory_ready": True,
            "selected_member_payload_inspection_authorized": False,
            "four_d_stem_download_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "scientific_boundary": [
            "Only ZIP tail and central-directory metadata were accessed; no SAED member payload was read.",
            "Archive member names/extensions can narrow representation hypotheses but cannot establish detector-native intensity, acquisition independence or calibration.",
            "The 35 K and 69 K 4D-STEM NPY arrays were not accessed and remain a separate modality.",
            "This Diagnostic format inventory creates no SAED indexing, phase, analyzer-performance or engineering evidence."
        ],
    }
    snapshot_path = output_root / "remote_inventory_snapshot.json"
    snapshot_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect only the remote ZIP central directory of the SrTiO3 SAED.zip source."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_srtio3_saed_remote_inventory/case_config.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/zenodo_srtio3_saed_remote_inventory"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_dir=args.output)
    except (OSError, ValueError, SrTiO3SaedRemoteInventoryError) as exc:
        print(f"SrTiO3 SAED remote inventory failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
