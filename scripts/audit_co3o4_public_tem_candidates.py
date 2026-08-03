from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"


def _fetch_json(url: str, accept: str = "application/json") -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _contains_cc_by_4(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False).casefold()
    markers = (
        "cc-by-4.0",
        "cc by 4.0",
        "creativecommons.org/licenses/by/4.0",
        "creative commons attribution 4.0",
    )
    return any(marker in text for marker in markers)


def _download(url: str, target: Path, expected_bytes: int, expected_sha256: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    observed_bytes = 0
    with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            digest.update(chunk)
            observed_bytes += len(chunk)
    if observed_bytes != expected_bytes:
        raise RuntimeError(
            f"downloaded archive byte mismatch: {observed_bytes} != {expected_bytes}"
        )
    observed_sha256 = digest.hexdigest()
    if observed_sha256 != expected_sha256:
        raise RuntimeError(
            f"downloaded archive SHA-256 mismatch: {observed_sha256} != {expected_sha256}"
        )


def _zenodo_inventory(config: dict[str, Any]) -> dict[str, Any]:
    expected = config["sources"]["zenodo_co3o4_nio"]
    payload = _fetch_json(f"https://zenodo.org/api/records/{expected['record_id']}")
    metadata = payload.get("metadata", {})
    if str(payload.get("id")) != expected["record_id"]:
        raise RuntimeError("Zenodo record identity mismatch")
    if str(payload.get("doi", "")).casefold() != expected["doi"].casefold():
        raise RuntimeError("Zenodo DOI mismatch")
    if not _contains_cc_by_4(metadata):
        raise RuntimeError("Zenodo CC BY 4.0 licence not resolved")

    observed_files: list[dict[str, Any]] = []
    for item in payload.get("files", []):
        checksum = str(item.get("checksum", ""))
        algorithm, separator, value = checksum.partition(":")
        if not separator:
            algorithm, value = "", checksum
        observed_files.append(
            {
                "name": item.get("key"),
                "bytes": int(item.get("size", 0)),
                "checksum_algorithm": algorithm.casefold(),
                "checksum": value.casefold(),
            }
        )
    if len(observed_files) != expected["expected_file_count"]:
        raise RuntimeError("Zenodo file-count mismatch")
    if sum(item["bytes"] for item in observed_files) != expected["expected_total_bytes"]:
        raise RuntimeError("Zenodo total-byte mismatch")
    for expected_file in expected["expected_files"]:
        match = next(
            (item for item in observed_files if item["name"] == expected_file["name"]),
            None,
        )
        if match is None:
            raise RuntimeError(f"Zenodo file missing: {expected_file['name']}")
        if match["bytes"] != expected_file["bytes"]:
            raise RuntimeError("Zenodo file byte mismatch")
        if match["checksum_algorithm"] != "md5":
            raise RuntimeError("Zenodo checksum algorithm mismatch")
        if match["checksum"] != expected_file["md5"]:
            raise RuntimeError("Zenodo file checksum mismatch")
    return {
        "record_id": str(payload.get("id")),
        "doi": payload.get("doi"),
        "title": metadata.get("title"),
        "license_verified": True,
        "files": observed_files,
        "tem_or_hrtem_file_count": 0,
    }



def _mendeley_inventory(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    expected = config["sources"]["mendeley_palygorskite_co3o4"]
    dataset_id = expected["dataset_id"]
    version = expected["version"]
    base = "https://data.mendeley.com/public-api"
    snapshot = _fetch_json(f"{base}/datasets/{dataset_id}/snapshot/{version}")
    if expected["doi"].casefold() not in json.dumps(snapshot).casefold():
        raise RuntimeError("Mendeley DOI mismatch")
    if not _contains_cc_by_4(snapshot):
        raise RuntimeError("Mendeley CC BY 4.0 licence not resolved")

    payload = _fetch_json(
        f"{base}/datasets/{dataset_id}/files?"
        + urllib.parse.urlencode({"folder_id": "root", "version": version}),
        "application/vnd.mendeley-public-dataset.1+json, application/json",
    )
    if isinstance(payload, dict):
        payload = payload.get("results") or payload.get("files") or payload.get("items") or []
    if not isinstance(payload, list):
        raise RuntimeError("Mendeley file response is not a list")

    observed_files: list[dict[str, Any]] = []
    for item in payload:
        content = item.get("content_details") or {}
        observed_files.append(
            {
                "file_id": item.get("id") or item.get("file_id"),
                "name": item.get("filename") or item.get("name") or "",
                "bytes": int(content.get("size", item.get("size", 0)) or 0),
                "sha256": (
                    content.get("sha256_hash")
                    or content.get("sha256")
                    or item.get("sha256_hash")
                    or item.get("sha256")
                    or ""
                ).casefold(),
                "last_modified_date": item.get("last_modified_date"),
            }
        )

    archive_name = expected["archive_name"]
    archive = next(
        (item for item in observed_files if item["name"] == archive_name),
        None,
    )
    if archive is None:
        raise RuntimeError("Mendeley archive missing")
    if not isinstance(archive["file_id"], str) or not archive["file_id"].strip():
        raise RuntimeError("Mendeley archive routing file_id missing")
    if archive["bytes"] <= 0:
        raise RuntimeError("Mendeley archive byte count must be positive")
    if re.fullmatch(r"[0-9a-f]{64}", archive["sha256"]) is None:
        raise RuntimeError("Mendeley archive SHA-256 is invalid")

    known_snapshots = expected.get("known_snapshots", [])
    matching_snapshot = next(
        (
            item
            for item in known_snapshots
            if item["name"] == archive["name"]
            and item["bytes"] == archive["bytes"]
            and item["sha256"] == archive["sha256"]
        ),
        None,
    )
    provenance = expected["provenance_policy"]
    identity_stable = (
        matching_snapshot is not None
        and not provenance["same_version_identity_drift_observed"]
    )
    endpoint = (
        "https://data.mendeley.com/public-files/datasets/"
        f"{dataset_id}/files/{archive['file_id']}/file_downloaded"
    )
    return (
        {
            "dataset_id": dataset_id,
            "version": version,
            "doi": expected["doi"],
            "title": snapshot.get("name") or snapshot.get("title"),
            "license_verified": True,
            "source_identity_basis": [
                "dataset_id",
                "version",
                "archive filename",
                "archive byte count",
                "archive SHA-256",
                "extracted representation",
            ],
            "observed_archive": archive,
            "known_snapshot_match": matching_snapshot is not None,
            "source_identity_stable_for_version": identity_stable,
            "same_version_identity_drift_observed": provenance[
                "same_version_identity_drift_observed"
            ],
            "observed_download_file_id": archive["file_id"],
            "file_id_used_only_for_download_routing": True,
            "files": observed_files,
        },
        endpoint,
    )


def _inspect_archive(
    archive_path: Path,
    extracted: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    expected = config["sources"]["mendeley_palygorskite_co3o4"]
    baseline = expected["known_wrong_modality_representation"]
    extracted.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["unar", "-quiet", "-output-directory", str(extracted), str(archive_path)],
        check=True,
    )
    members = sorted(path for path in extracted.rglob("*") if path.is_file())
    relative = [path.relative_to(extracted).as_posix() for path in members]
    if any(name.startswith("/") or ".." in Path(name).parts for name in relative):
        raise RuntimeError("archive contains unsafe member paths")

    images: list[dict[str, Any]] = []
    for path in members:
        try:
            with Image.open(path) as image:
                images.append(
                    {
                        "path": path.relative_to(extracted).as_posix(),
                        "format": image.format,
                        "mode": image.mode,
                        "size": [image.width, image.height],
                        "frames": getattr(image, "n_frames", 1),
                    }
                )
        except Exception:
            continue

    tem_pattern = re.compile(r"(^|[/_. -])(hrtem|tem)([/_. -]|$)", re.IGNORECASE)
    stem_pattern = re.compile(r"(^|[/_. -])stem([/_. -]|$)", re.IGNORECASE)
    tem_paths = [name for name in relative if tem_pattern.search(name)]
    stem_paths = [name for name in relative if stem_pattern.search(name)]
    detector_suffixes = {".dm3", ".dm4", ".emd", ".ser", ".tif", ".tiff"}
    detector_members = [
        name for name in relative if Path(name).suffix.casefold() in detector_suffixes
    ]

    observed_paths = sorted(item["path"] for item in images)
    baseline_images_match = (
        observed_paths == sorted(baseline["image_members"])
        and all(item["format"] == baseline["image_format"] for item in images)
        and all(item["mode"] == baseline["image_mode"] for item in images)
        and all(item["size"] == baseline["image_size"] for item in images)
        and all(item["frames"] == 1 for item in images)
    )
    baseline_match = (
        len(members) == baseline["member_count"]
        and baseline_images_match
        and not tem_paths
        and not stem_paths
        and not detector_members
    )
    return {
        "archive_member_count": len(members),
        "suffix_counts": dict(
            sorted(Counter(Path(name).suffix.casefold() or "<none>" for name in relative).items())
        ),
        "decodable_image_count": len(images),
        "decodable_images": images,
        "tem_or_hrtem_member_count": len(tem_paths),
        "stem_member_count": len(stem_paths),
        "microscopy_detector_file_count": len(detector_members),
        "tem_or_stem_candidate_paths": sorted(set(tem_paths + stem_paths)),
        "microscopy_detector_members": detector_members,
        "known_wrong_modality_representation_match": baseline_match,
    }


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    transient = output / "_transient"
    transient.mkdir()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        zenodo = _zenodo_inventory(config)
        mendeley, endpoint = _mendeley_inventory(config)
        observed_archive = mendeley["observed_archive"]
        archive_path = transient / observed_archive["name"]
        _download(
            endpoint,
            archive_path,
            observed_archive["bytes"],
            observed_archive["sha256"],
        )
        representation = _inspect_archive(archive_path, transient / "extracted", config)
        candidate_tem_content = bool(
            representation["tem_or_hrtem_member_count"]
            or representation["stem_member_count"]
            or representation["microscopy_detector_file_count"]
        )
        if candidate_tem_content:
            result = "source_representation_changed_manual_review_required"
        elif (
            mendeley["source_identity_stable_for_version"]
            and representation["known_wrong_modality_representation_match"]
        ):
            result = "assessed_public_records_do_not_expose_tem_validation_arrays"
        else:
            result = "source_identity_changed_but_current_archive_remains_wrong_modality"

        inventory = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "audit_date": config["audit_date"],
            "zenodo": zenodo,
            "mendeley": mendeley,
        }
        summary = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "result": result,
            **representation,
            "mendeley_known_snapshot_match": mendeley["known_snapshot_match"],
            "mendeley_source_identity_stable_for_version": mendeley[
                "source_identity_stable_for_version"
            ],
            "mendeley_same_version_identity_drift_observed": mendeley[
                "same_version_identity_drift_observed"
            ],
            "mendeley_observed_archive_bytes": observed_archive["bytes"],
            "mendeley_observed_archive_sha256": observed_archive["sha256"],
            "source_binaries_retained": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "manual_review_required": candidate_tem_content,
            "external_validation_ready": False,
            "scientific_closeout": {
                "status": "Supported" if not candidate_tem_content else "Inconclusive",
                "strongest_evidence": (
                    "The Zenodo record exposes only one spreadsheet. The current Mendeley "
                    "archive was verified against its API-declared byte count and SHA-256, "
                    "then inspected after extraction."
                ),
                "primary_limitation": (
                    "The same Mendeley DOI/version has exhibited archive-identity drift, and "
                    "the audit establishes only what is present in the current public snapshot."
                ),
                "not_suitable_for": [
                    "TEM segmentation inference",
                    "model retraining",
                    "external performance claims",
                    "engineering release",
                ],
            },
        }
        (output / "official_source_inventory.json").write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "co3o4_public_tem_candidate_audit_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        shutil.rmtree(transient, ignore_errors=True)

def _verify_registry(registry_output: Path) -> None:
    summary = json.loads(
        (registry_output / "tem_external_validation_candidate_summary.json")
        .read_text(encoding="utf-8")
    )
    counts = summary["result_counts"]
    if counts["candidate_count"] != 9:
        raise RuntimeError("registry candidate count mismatch")
    if counts["in_domain_external_validation_ready_count"] != 0:
        raise RuntimeError("registry unexpectedly reports a ready candidate")
    if counts["excluded_control_count"] != 5:
        raise RuntimeError("registry exclusion count mismatch")
    with (registry_output / "tem_external_validation_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}
    for candidate_id in (
        "zenodo_14160831_co3o4_nio_replication_package",
        "mendeley_kkk76z8g8z_current_public_archive",
    ):
        row = rows[candidate_id]
        if row["candidate_status"] != "excluded_wrong_microscopy_modality":
            raise RuntimeError(f"unexpected candidate status for {candidate_id}")
        if row["reported_tem_file_count"] != "0":
            raise RuntimeError(f"unexpected TEM file count for {candidate_id}")
        if row["evaluation_ready"] != "False":
            raise RuntimeError(f"candidate unexpectedly evaluation-ready: {candidate_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry-output", type=Path)
    args = parser.parse_args()
    summary = run(args.config, args.output)
    if args.registry_output is not None:
        _verify_registry(args.registry_output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 2 if summary["manual_review_required"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
