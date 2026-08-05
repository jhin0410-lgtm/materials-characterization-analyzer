from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
RESULT = "zenodo_record_and_archive_identity_verified_without_source_download"


class ZenodoMetadataAuditError(RuntimeError):
    """Raised when the live Zenodo record violates the pinned metadata contract."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"case_id", "audit_date", "source", "bounded_plan"}:
        raise ZenodoMetadataAuditError("unexpected top-level config keys")
    source_keys = {
        "repository",
        "record_id",
        "doi",
        "record_url",
        "api_url",
        "expected_status",
        "expected_resource_type",
        "expected_license_id",
        "expected_file_count",
        "target_file",
    }
    if set(payload["source"]) != source_keys:
        raise ZenodoMetadataAuditError("unexpected source config keys")
    target_keys = {"key", "checksum", "minimum_bytes", "maximum_bytes"}
    if set(payload["source"]["target_file"]) != target_keys:
        raise ZenodoMetadataAuditError("unexpected target-file config keys")
    plan = payload["bounded_plan"]
    prohibited_true = {
        "source_archive_download_authorized",
        "source_files_may_be_uploaded_as_artifacts",
        "archive_members_may_be_uploaded_as_artifacts",
        "model_inference_authorized",
        "annotation_authorized",
        "parameter_tuning_authorized",
        "external_validation_claim_authorized",
        "engineering_decision_claim_authorized",
    }
    if any(plan[key] is not False for key in prohibited_true):
        raise ZenodoMetadataAuditError("metadata-only plan must remain fail-closed")
    return payload


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _license_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        identifier = value.get("id")
        return str(identifier) if identifier is not None else None
    return None


def _resource_type_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("resource_type")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        identifier = value.get("id") or value.get("type")
        return str(identifier) if identifier is not None else None
    return None


def normalize_record(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    files = []
    for item in payload.get("files") or []:
        links = item.get("links") or {}
        files.append(
            {
                "id": item.get("id"),
                "key": item.get("key"),
                "size": item.get("size"),
                "checksum": item.get("checksum"),
                "content_url": links.get("content") or links.get("self"),
            }
        )
    files.sort(key=lambda row: str(row["key"]))
    return {
        "id": payload.get("id"),
        "doi": payload.get("doi") or metadata.get("doi"),
        "status": payload.get("status"),
        "title": metadata.get("title"),
        "publication_date": metadata.get("publication_date"),
        "resource_type_id": _resource_type_id(metadata),
        "license_id": _license_id(metadata),
        "created": payload.get("created"),
        "updated": payload.get("updated"),
        "files": files,
    }


def verify_record(
    config: dict[str, Any], record: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source = config["source"]
    expected_pairs = {
        "id": source["record_id"],
        "doi": source["doi"],
        "status": source["expected_status"],
        "resource_type_id": source["expected_resource_type"],
        "license_id": source["expected_license_id"],
    }
    for key, expected in expected_pairs.items():
        if record.get(key) != expected:
            raise ZenodoMetadataAuditError(
                f"record mismatch for {key}: {record.get(key)!r} != {expected!r}"
            )
    files = record["files"]
    if len(files) != source["expected_file_count"]:
        raise ZenodoMetadataAuditError("record file-count mismatch")
    by_key = {row["key"]: row for row in files}
    target_config = source["target_file"]
    target = by_key.get(target_config["key"])
    if target is None:
        raise ZenodoMetadataAuditError("target archive is missing")
    if target["checksum"] != target_config["checksum"]:
        raise ZenodoMetadataAuditError("target archive checksum mismatch")
    if not isinstance(target["size"], int):
        raise ZenodoMetadataAuditError("target archive size is missing")
    if not (
        target_config["minimum_bytes"]
        <= target["size"]
        <= target_config["maximum_bytes"]
    ):
        raise ZenodoMetadataAuditError("target archive size is outside the bounded plan")
    if not target["content_url"]:
        raise ZenodoMetadataAuditError("target archive content URL is missing")
    return target, files


def build_summary(
    config: dict[str, Any], record: dict[str, Any], target: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "result": RESULT,
        "source": {
            "repository": "Zenodo",
            "record_id": record["id"],
            "doi": record["doi"],
            "status": record["status"],
            "resource_type_id": record["resource_type_id"],
            "license_id": record["license_id"],
            "publication_date": record["publication_date"],
            "created": record["created"],
            "updated": record["updated"],
            "file_count": len(record["files"]),
        },
        "target_archive": {
            "key": target["key"],
            "bytes": target["size"],
            "checksum": target["checksum"],
            "content_url_present": bool(target["content_url"]),
        },
        "metadata_audit_closeout": {
            "status": "Supported",
            "strongest_evidence": "The live Zenodo API confirms the published dataset identity, CC BY 4.0 licence, three-file inventory, target archive byte size, and archive MD5.",
            "primary_limitation": "The archive was not downloaded or inventoried; member formats, raw status, acquisition lineage, labels, SAED centre, and reciprocal calibration remain unresolved.",
        },
        "source_archive_downloaded": False,
        "source_files_retained": False,
        "model_inference_performed": False,
        "annotation_performed": False,
        "primary_parameters_changed": False,
        "archive_member_inventory_complete": False,
        "raw_detector_status_resolved": False,
        "sample_acquisition_lineage_resolved": False,
        "tem_independent_segmentation_labels_available": False,
        "saed_pattern_center_resolved": False,
        "saed_reciprocal_calibration_resolved": False,
        "external_validation_ready": False,
        "engineering_decision_ready": False,
        "analyzer_scientific_evidence_level": "Inconclusive",
        "next_action": "Review and pin the exact target byte count in the bounded acquisition plan before authorizing a transient archive download and member-only audit.",
    }


def _write_manifest(output: Path, names: list[str]) -> None:
    rows = []
    for name in names:
        path = output / name
        blob = path.read_bytes()
        rows.append(
            {"path": name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
        )
    (output / "zenodo_silver_tem_saed_metadata_audit_manifest.json").write_text(
        json.dumps({"schema_version": "1.0", "artifacts": rows}, indent=2) + "\n",
        encoding="utf-8",
    )


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    succeeded = False
    try:
        config = load_config(config_path)
        payload = fetch_json(config["source"]["api_url"])
        record = normalize_record(payload)
        target, files = verify_record(config, record)
        summary = build_summary(config, record, target)
        snapshot = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "record": record,
            "verified_target": target,
        }
        plan = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "record_id": record["id"],
            "doi": record["doi"],
            "target_archive": {
                "key": target["key"],
                "exact_bytes": target["size"],
                "checksum": target["checksum"],
                "content_url": target["content_url"],
            },
            "limits": {
                "maximum_archive_bytes": config["bounded_plan"][
                    "future_maximum_archive_bytes"
                ],
                "maximum_uncompressed_bytes": config["bounded_plan"][
                    "future_maximum_uncompressed_bytes"
                ],
                "maximum_member_count": config["bounded_plan"][
                    "future_maximum_member_count"
                ],
            },
            "authorization": {
                "source_archive_download_authorized": False,
                "source_artifact_upload_authorized": False,
                "model_inference_authorized": False,
                "annotation_authorized": False,
                "parameter_tuning_authorized": False,
            },
            "required_before_download": [
                "review exact byte count and checksum",
                "freeze archive member inventory-only objective",
                "preserve transient-source deletion and metadata-only artifact policy",
                "freeze stop conditions for encrypted, unsafe, oversized, or unsupported members",
            ],
            "file_inventory": files,
        }
        (output / "official_zenodo_record_snapshot.json").write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "bounded_archive_acquisition_plan.json").write_text(
            json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "zenodo_silver_tem_saed_metadata_audit_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report = (
            "# Zenodo Silver TEM/SAED Metadata Audit\n\n"
            f"- Result: `{RESULT}`\n"
            f"- Record ID: {record['id']}\n"
            f"- Files: {len(files)}\n"
            f"- Target archive: `{target['key']}`\n"
            f"- Exact bytes: {target['size']}\n"
            f"- Checksum: `{target['checksum']}`\n"
            "- Source archive downloaded: false\n"
            "- External validation ready: false\n"
            "- Analyzer scientific evidence: Inconclusive\n\n"
            "The public record identity and archive checksum are verified. The archive contents "
            "remain unaudited, so no inference, annotation, calibration, or scientific claim "
            "promotion is authorized.\n"
        )
        (output / "zenodo_silver_tem_saed_metadata_audit_report.md").write_text(
            report, encoding="utf-8"
        )
        _write_manifest(
            output,
            [
                "official_zenodo_record_snapshot.json",
                "bounded_archive_acquisition_plan.json",
                "zenodo_silver_tem_saed_metadata_audit_summary.json",
                "zenodo_silver_tem_saed_metadata_audit_report.md",
            ],
        )
        succeeded = True
        return summary
    finally:
        if not succeeded and output.exists():
            import shutil

            shutil.rmtree(output, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.config, args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
