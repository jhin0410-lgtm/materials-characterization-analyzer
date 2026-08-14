from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from scripts.audit_zenodo_bir_300kev_remote_inventory import (
    fetch_range,
    parse_central_directory,
    parse_eocd,
)

SCHEMA_VERSION = "1.0"


class CarbonNitrideTemRemoteInventoryError(RuntimeError):
    """Raised when the bounded carbon-nitride ZIP inventory contract fails."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CarbonNitrideTemRemoteInventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise CarbonNitrideTemRemoteInventoryError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise CarbonNitrideTemRemoteInventoryError("JSON root must be an object")
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
    if set(value) != required or value.get("schema_version") != SCHEMA_VERSION:
        raise CarbonNitrideTemRemoteInventoryError(
            "remote inventory config keys/schema do not match contract"
        )
    archive = value["target_archive"]
    if not isinstance(archive, dict) or set(archive) != {
        "key",
        "expected_bytes",
        "expected_md5",
    }:
        raise CarbonNitrideTemRemoteInventoryError("target_archive keys do not match contract")
    if archive["key"] != "Whole dataset.zip":
        raise CarbonNitrideTemRemoteInventoryError("target archive is not the pinned carbon dataset")
    if archive["expected_bytes"] != 561160882:
        raise CarbonNitrideTemRemoteInventoryError("target archive byte count is not pinned")
    if archive["expected_md5"] != "b608d86084ccbbea802ff54c3f98380e":
        raise CarbonNitrideTemRemoteInventoryError("target archive MD5 is not pinned")

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
        raise CarbonNitrideTemRemoteInventoryError("range_limits keys do not match contract")
    for key in expected_limits:
        observed = limits[key]
        if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
            raise CarbonNitrideTemRemoteInventoryError(f"range limit must be positive: {key}")
    if limits["tail_probe_bytes"] < 65557:
        raise CarbonNitrideTemRemoteInventoryError("tail probe is too small for maximal ZIP EOCD/comment")

    boundary = value["scientific_boundary"]
    true_keys = {"http_range_metadata_probe_authorized", "central_directory_inventory_authorized"}
    if not isinstance(boundary, dict) or any(boundary.get(key) is not True for key in true_keys):
        raise CarbonNitrideTemRemoteInventoryError("bounded central-directory probing is not authorized")
    if any(item is not False for key, item in boundary.items() if key not in true_keys):
        raise CarbonNitrideTemRemoteInventoryError("stronger source/analyzer actions must remain disabled")

    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise CarbonNitrideTemRemoteInventoryError("all fail-closed decision rules must be enabled")
    return value


def resolve_target(
    config: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if source_snapshot.get("execution_status") != "metadata_audit_completed":
        raise CarbonNitrideTemRemoteInventoryError("source snapshot is not a completed metadata audit")
    source = source_snapshot.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 21222653:
        raise CarbonNitrideTemRemoteInventoryError("source snapshot is not the pinned carbon-nitride record")
    if source.get("license_id") != "cc-by-4.0":
        raise CarbonNitrideTemRemoteInventoryError("dataset license differs from the pinned API evidence")
    readiness = source_snapshot.get("readiness")
    if not isinstance(readiness, Mapping) or readiness.get("reuse_status") != (
        "dataset_license_declared_manual_reuse_review_required"
    ):
        raise CarbonNitrideTemRemoteInventoryError("source snapshot reuse state differs from pinned metadata evidence")

    inventory = source_snapshot.get("file_inventory")
    if not isinstance(inventory, list):
        raise CarbonNitrideTemRemoteInventoryError("source file inventory is invalid")
    archive_config = config["target_archive"]
    matches = [
        item
        for item in inventory
        if isinstance(item, Mapping) and item.get("key") == archive_config["key"]
    ]
    if len(matches) != 1:
        raise CarbonNitrideTemRemoteInventoryError("target archive is not uniquely present")
    target = dict(matches[0])
    if target.get("bytes") != archive_config["expected_bytes"]:
        raise CarbonNitrideTemRemoteInventoryError("target archive byte count drifted")
    if target.get("md5") != archive_config["expected_md5"]:
        raise CarbonNitrideTemRemoteInventoryError("target archive repository MD5 drifted")
    url = target.get("content_url")
    if not isinstance(url, str) or not url.startswith("https://zenodo.org/"):
        raise CarbonNitrideTemRemoteInventoryError("target archive URL is outside trusted Zenodo")
    return target


def _path_cues(record: Mapping[str, Any]) -> dict[str, Any]:
    member_path = str(record["member_path"])
    folded = member_path.casefold()
    suffix = PurePosixPath(member_path).suffix.casefold()
    return {
        "extension": suffix,
        "raw_path_cue": any(term in folded for term in ("raw", "original", "unprocessed")),
        "segmentation_path_cue": any(term in folded for term in ("segment", "mask")),
        "annotation_path_cue": any(term in folded for term in ("annotat", "label")),
        "tem_path_cue": "tem" in folded,
    }


def enrich_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item.update(_path_cues(record))
        enriched.append(item)
    return enriched


def summarize_inventory(records: list[dict[str, Any]], *, central_sha256: str) -> dict[str, Any]:
    files = [record for record in records if not record["is_directory"]]
    extensions = Counter(record["extension"] or "<no-extension>" for record in files)
    top_level = Counter()
    for record in files:
        parts = PurePosixPath(str(record["member_path"])).parts
        if parts:
            top_level[parts[0]] += 1
    return {
        "member_count": len(records),
        "file_count": len(files),
        "directory_entry_count": sum(bool(record["is_directory"]) for record in records),
        "unsafe_path_count": sum(bool(record["unsafe_path"]) for record in records),
        "raw_path_cue_count": sum(bool(record["raw_path_cue"]) for record in files),
        "segmentation_path_cue_count": sum(
            bool(record["segmentation_path_cue"]) for record in files
        ),
        "annotation_path_cue_count": sum(bool(record["annotation_path_cue"]) for record in files),
        "tem_path_cue_count": sum(bool(record["tem_path_cue"]) for record in files),
        "extension_counts": dict(sorted(extensions.items())),
        "top_level_path_counts": dict(sorted(top_level.items())),
        "central_directory_sha256": central_sha256,
    }


def _scientific_assessment(summary: Mapping[str, Any]) -> dict[str, str]:
    path_separation = (
        "Diagnostic"
        if summary["raw_path_cue_count"] > 0
        and (summary["segmentation_path_cue_count"] > 0 or summary["annotation_path_cue_count"] > 0)
        else "Inconclusive"
    )
    return {
        "remote_archive_structure": "Supported",
        "raw_vs_annotation_path_separation": path_separation,
        "detector_native_or_lossless_intensity_provenance": "Inconclusive",
        "immutable_sample_identity": "Inconclusive",
        "immutable_acquisition_identity": "Inconclusive",
        "annotation_provenance": "Inconclusive",
        "annotation_completeness": "Inconclusive",
        "annotation_independence_from_target_model": "Inconclusive",
        "co3o4_domain_match": "Unsupported",
        "external_validation_ready": "Unsupported",
        "cross_material_software_robustness_ready": "Inconclusive",
        "scientific_evidence_level": "Diagnostic",
    }


def write_inventory_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(records[0]) if records else ["member_path"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def run_audit(*, config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_file = Path(config_path).expanduser().resolve(strict=True)
    config = validate_config(load_json(config_file))
    source_snapshot_file = Path(config["source_snapshot"]).expanduser()
    if not source_snapshot_file.is_absolute():
        source_snapshot_file = (config_file.parent / source_snapshot_file).resolve(strict=True)
    source_snapshot = load_json(source_snapshot_file)
    target = resolve_target(config, source_snapshot)

    archive_size = int(target["bytes"])
    limits = config["range_limits"]
    tail_size = min(int(limits["tail_probe_bytes"]), archive_size)
    tail_start = archive_size - tail_size
    tail = fetch_range(
        str(target["content_url"]),
        start=tail_start,
        end=archive_size - 1,
        expected_total=archive_size,
    )
    eocd = parse_eocd(tail, archive_size=archive_size)
    if eocd["central_directory_bytes"] > int(limits["maximum_central_directory_bytes"]):
        raise CarbonNitrideTemRemoteInventoryError("central directory exceeds configured byte limit")
    if eocd["entries_total"] > int(limits["maximum_member_count"]):
        raise CarbonNitrideTemRemoteInventoryError("archive member count exceeds configured limit")

    central_start = eocd["central_directory_offset"]
    central_end = central_start + eocd["central_directory_bytes"] - 1
    central = fetch_range(
        str(target["content_url"]),
        start=central_start,
        end=central_end,
        expected_total=archive_size,
    )
    central_sha256 = hashlib.sha256(central).hexdigest()
    records = enrich_records(
        parse_central_directory(
            central,
            expected_entries=eocd["entries_total"],
            limits=limits,
        )
    )
    summary = summarize_inventory(records, central_sha256=central_sha256)
    if summary["unsafe_path_count"] != 0:
        raise CarbonNitrideTemRemoteInventoryError("archive contains unsafe member paths")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    inventory_path = output / "remote_member_inventory.csv"
    write_inventory_csv(inventory_path, records)
    retrieved_bytes = len(tail) + len(central)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "bounded_remote_inventory_completed",
        "source_snapshot": {
            "path": str(source_snapshot_file),
            "sha256": sha256_file(source_snapshot_file),
        },
        "target_archive": {
            "key": target["key"],
            "bytes": archive_size,
            "md5": target["md5"],
            "content_url": target["content_url"],
        },
        "range_probe": {
            "tail_start": tail_start,
            "tail_end": archive_size - 1,
            "tail_bytes": len(tail),
            "central_directory_start": central_start,
            "central_directory_end": central_end,
            "central_directory_bytes": len(central),
            "network_bytes_retrieved": retrieved_bytes,
            "archive_fraction_retrieved": retrieved_bytes / archive_size,
        },
        "zip_metadata": eocd,
        "inventory_summary": summary,
        "evidence_assessment": _scientific_assessment(summary),
        "next_evidence": [
            "Use member paths only to identify bounded raw/annotation groups; do not infer immutable sample or acquisition identity from folder names.",
            "If the inventory cleanly separates raw and annotated examples, select the minimum member subset needed for a later representation/header audit rather than downloading the full archive.",
            "Before any annotation robustness comparison, establish annotation provenance, completeness, and independence from the target model.",
            "Keep carbon nitride outside the Co3O4 external-validation claim domain."
        ],
        "scientific_boundary": config["scientific_boundary"],
        "decision_rules": config["decision_rules"],
        "config_sha256": sha256_file(config_file),
        "source_archive_downloaded": False,
        "member_file_content_downloaded": False,
        "pixel_array_access_performed": False,
        "analyzer_inference_performed": False,
        "external_validation_claim_made": False,
        "engineering_decision_claim_made": False,
    }
    snapshot_path = output / "verified_remote_inventory_snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect only the ZIP EOCD and central directory of the pinned carbon-nitride TEM archive. "
            "Full-download fallback and member-content access are prohibited."
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
