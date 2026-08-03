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
    archive_expected = expected["archive"]
    archive = next(
        (item for item in observed_files if item["name"] == archive_expected["name"]),
        None,
    )
    if archive is None:
        raise RuntimeError("Mendeley archive missing")
    for key in ("file_id", "bytes", "sha256"):
        if archive[key] != archive_expected[key]:
            raise RuntimeError(f"Mendeley archive {key} mismatch")
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
    extracted.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["unar", "-quiet", "-output-directory", str(extracted), str(archive_path)],
        check=True,
    )
    members = sorted(path for path in extracted.rglob("*") if path.is_file())
    relative = [path.relative_to(extracted).as_posix() for path in members]
    if len(members) != expected["expected_member_count"]:
        raise RuntimeError(f"archive member-count mismatch: {len(members)}")
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
    observed_paths = sorted(item["path"] for item in images)
    if observed_paths != sorted(expected["expected_image_members"]):
        raise RuntimeError(f"image-member mismatch: {observed_paths}")
    for image in images:
        if image["format"] != expected["expected_image_format"]:
            raise RuntimeError("image-format mismatch")
        if image["mode"] != expected["expected_image_mode"]:
            raise RuntimeError("image-mode mismatch")
        if image["size"] != expected["expected_image_size"]:
            raise RuntimeError("image-size mismatch")
        if image["frames"] != 1:
            raise RuntimeError("unexpected multi-frame image")

    tem_pattern = re.compile(r"(^|[/_. -])(hrtem|tem)([/_. -]|$)", re.IGNORECASE)
    tem_paths = [name for name in relative if tem_pattern.search(name)]
    if tem_paths:
        raise RuntimeError(f"unexpected TEM/HRTEM paths: {tem_paths}")
    detector_suffixes = {".dm3", ".dm4", ".emd", ".ser", ".tif", ".tiff"}
    detector_members = [
        name for name in relative if Path(name).suffix.casefold() in detector_suffixes
    ]
    if detector_members:
        raise RuntimeError(f"unexpected microscopy detector files: {detector_members}")
    return {
        "archive_member_count": len(members),
        "suffix_counts": dict(
            sorted(Counter(Path(name).suffix.casefold() or "<none>" for name in relative).items())
        ),
        "decodable_image_count": len(images),
        "decodable_images": images,
        "tem_or_hrtem_member_count": len(tem_paths),
        "microscopy_detector_file_count": len(detector_members),
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
        archive_expected = config["sources"]["mendeley_palygorskite_co3o4"]["archive"]
        archive_path = transient / archive_expected["name"]
        _download(
            endpoint,
            archive_path,
            archive_expected["bytes"],
            archive_expected["sha256"],
        )
        representation = _inspect_archive(archive_path, transient / "extracted", config)
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
            "result": "assessed_public_records_do_not_expose_tem_validation_arrays",
            **representation,
            "source_binaries_retained": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "external_validation_ready": False,
            "scientific_closeout": {
                "status": "Supported",
                "strongest_evidence": (
                    "The Zenodo record exposes only one spreadsheet and the checksum-bound "
                    "Mendeley archive contains 760 members with only three SEM PNG images."
                ),
                "primary_limitation": (
                    "The audit establishes public-file absence for the pinned snapshots, not "
                    "that the original investigators never acquired TEM data."
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
