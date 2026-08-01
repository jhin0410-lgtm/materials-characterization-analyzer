"""Checksum-verify and inventory the public Mendeley raw-data archive.

The archive is downloaded to a temporary directory, verified against the
source-declared SHA-256 and byte size, listed with 7-Zip, and deleted. Archive
members are not extracted by this step.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

BASE = "https://data.mendeley.com/public-api"
PRIMARY_ID = "8w66synjmx"
DUPLICATE_ID = "zhnbzhjrtr"
VERSION = 1
TEM_PATTERN = re.compile(r"(?i)(?:^|[^a-z])(?:tem|hrtem|stem|transmission electron)(?:[^a-z]|$)")
IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".dm3", ".dm4", ".emd", ".ser"}


def _json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.mendeley-public-dataset.1+json, application/json",
            "User-Agent": "materials-characterization-analyzer-archive-audit/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _root_files(dataset_id: str) -> list[Mapping[str, Any]]:
    url = f"{BASE}/datasets/{dataset_id}/files?" + urllib.parse.urlencode(
        {"folder_id": "root", "version": str(VERSION)}
    )
    payload = _json(url)
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise ValueError(f"unexpected root-file payload for {dataset_id}")
    return list(payload)


def _one_archive(dataset_id: str) -> Mapping[str, Any]:
    files = _root_files(dataset_id)
    if len(files) != 1:
        raise ValueError(f"{dataset_id} must expose exactly one root file, found {len(files)}")
    item = files[0]
    content = item.get("content_details")
    if not isinstance(content, Mapping):
        raise ValueError(f"{dataset_id} root file lacks content_details")
    filename = item.get("filename")
    if not isinstance(filename, str) or not filename.lower().endswith(".rar"):
        raise ValueError(f"{dataset_id} root file is not the expected RAR archive")
    return item


def _metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    content = item["content_details"]
    assert isinstance(content, Mapping)
    size = content.get("size", item.get("size"))
    sha256 = content.get("sha256_hash")
    download_url = content.get("download_url")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("source archive size must be a positive integer")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("source archive SHA-256 is missing or invalid")
    if not isinstance(download_url, str) or not download_url.startswith("https://"):
        raise ValueError("source archive download URL is missing")
    return {
        "file_id": str(item.get("id", "")),
        "content_id": str(content.get("id", "")),
        "filename": str(item["filename"]),
        "size_bytes": size,
        "sha256": sha256,
        "content_type": str(content.get("content_type", "")),
        "download_url": download_url,
    }


def _download(meta: Mapping[str, Any], target: Path) -> None:
    request = urllib.request.Request(
        str(meta["download_url"]),
        headers={"User-Agent": "materials-characterization-analyzer-archive-audit/1.0"},
    )
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    if size != int(meta["size_bytes"]):
        target.unlink(missing_ok=True)
        raise ValueError(f"downloaded archive size mismatch: {size} != {meta['size_bytes']}")
    observed = digest.hexdigest()
    if observed != meta["sha256"]:
        target.unlink(missing_ok=True)
        raise ValueError(f"downloaded archive SHA-256 mismatch: {observed}")


def _list_archive(path: Path) -> list[dict[str, Any]]:
    executable = shutil.which("7z") or shutil.which("7zz")
    if executable is None:
        raise RuntimeError("7z or 7zz is required for RAR inventory")
    process = subprocess.run(
        [executable, "l", "-slt", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in process.stdout.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            current[key.strip()] = value.strip()
    if current:
        records.append(current)

    members: list[dict[str, Any]] = []
    for record in records:
        name = record.get("Path", "")
        if not name or Path(name).resolve() == path.resolve():
            continue
        is_dir = record.get("Folder") == "+" or record.get("Attributes", "").startswith("D")
        normalized = name.replace("\\", "/")
        pure = PurePosixPath(normalized)
        unsafe = pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts)
        size_text = record.get("Size", "0")
        try:
            size = int(size_text)
        except ValueError:
            size = -1
        suffix = pure.suffix.lower()
        searchable = normalized
        members.append(
            {
                "path": normalized,
                "is_directory": is_dir,
                "path_safe": not unsafe,
                "size_bytes": size,
                "packed_size_bytes": _optional_int(record.get("Packed Size")),
                "crc": record.get("CRC", ""),
                "method": record.get("Method", ""),
                "modified": record.get("Modified", ""),
                "extension": suffix,
                "tem_keyword_match": bool(TEM_PATTERN.search(searchable)),
                "recognized_microscopy_image_extension": suffix in IMAGE_EXTENSIONS,
                "tem_candidate_by_member_metadata": (
                    not is_dir
                    and not unsafe
                    and (bool(TEM_PATTERN.search(searchable)) or suffix in IMAGE_EXTENSIONS)
                ),
                "material_or_sample_identity_inferred": False,
            }
        )
    if not members:
        raise ValueError("RAR inventory contains no member records")
    if any(not row["path_safe"] for row in members):
        raise ValueError("RAR inventory contains an unsafe member path")
    return members


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit(output: Path) -> dict[str, Any]:
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)

    primary = _metadata(_one_archive(PRIMARY_ID))
    duplicate = _metadata(_one_archive(DUPLICATE_ID))
    same_content = (
        primary["filename"] == duplicate["filename"]
        and primary["size_bytes"] == duplicate["size_bytes"]
        and primary["sha256"] == duplicate["sha256"]
    )
    if not same_content:
        raise ValueError("primary and duplicate raw records no longer expose identical content")

    try:
        with tempfile.TemporaryDirectory(prefix="mca-mendeley-archive-") as temp_name:
            archive = Path(temp_name) / primary["filename"]
            _download(primary, archive)
            members = _list_archive(archive)
    finally:
        primary.pop("download_url", None)
        duplicate.pop("download_url", None)

    files = [row for row in members if not row["is_directory"]]
    candidates = [row for row in files if row["tem_candidate_by_member_metadata"]]
    total_uncompressed = sum(max(0, int(row["size_bytes"])) for row in files)
    summary = {
        "schema_version": "1.0",
        "case_id": "mendeley_cop_co2p_co3o4_public_archive_audit",
        "source": {
            "primary_dataset_id": PRIMARY_ID,
            "primary_doi": "10.17632/8w66synjmx.1",
            "duplicate_dataset_id": DUPLICATE_ID,
            "duplicate_doi": "10.17632/zhnbzhjrtr.1",
            "primary_archive": primary,
            "duplicate_archive": duplicate,
            "duplicate_raw_record_content_identical": same_content,
        },
        "archive_inventory": {
            "member_count": len(members),
            "file_count": len(files),
            "directory_count": len(members) - len(files),
            "total_uncompressed_file_bytes": total_uncompressed,
            "all_member_paths_safe": True,
            "tem_candidate_member_count": len(candidates),
            "tem_candidate_member_paths": [row["path"] for row in candidates],
        },
        "readiness": {
            "archive_checksum_and_size_verified": True,
            "duplicate_record_independence": False,
            "member_inventory_resolved": True,
            "co3o4_region_binding_available": False,
            "immutable_sample_ids_available": False,
            "immutable_acquisition_ids_available": False,
            "target_training_nonuse_verified": False,
            "independent_segmentation_labels_available": False,
            "annotation_pilot_ready": False,
            "external_model_evaluation_ready": False,
        },
        "next_action": (
            "Selectively extract only metadata-identified microscopy members, inspect file "
            "formats and embedded metadata, and resolve Co3O4-bearing regions plus immutable "
            "sample/acquisition lineage before any annotation."
            if candidates
            else
            "No TEM member was identifiable from archive member metadata; inspect source "
            "documentation or archive contents without inferring material identity from generic filenames."
        ),
        "processing": {
            "archive_downloaded_temporarily": True,
            "archive_persisted": False,
            "archive_members_extracted": False,
            "source_arrays_inspected": False,
            "labels_created": False,
            "model_training_performed": False,
            "model_inference_performed": False,
        },
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": "archive_inventory_resolved_annotation_not_ready",
            "strongest_evidence": (
                "The two raw-data DOI records expose byte-identical database.rar archives. "
                "The primary archive was source-checksum verified and inventoried without extraction."
            ),
            "primary_limitation": (
                "Archive-member names and formats do not establish Co3O4 region identity, "
                "sample/acquisition lineage, independence from target development, or labels."
            ),
            "evidence_that_would_change_conclusion": (
                "Source-supported sample/acquisition mapping for Co3O4-bearing TEM members, "
                "verified model-development non-use and content disjointness, followed by "
                "blinded independent annotation and adjudication."
            ),
        },
    }

    inventory_path = output / "mendeley_archive_member_inventory.csv"
    summary_path = output / "mendeley_public_archive_audit_summary.json"
    report_path = output / "mendeley_public_archive_audit_report.md"
    manifest_path = output / "mendeley_public_archive_audit_manifest.json"
    _write_csv(inventory_path, members)
    _write_json(summary_path, summary)
    report_path.write_text(_report(summary, candidates), encoding="utf-8")
    artifacts = [inventory_path, summary_path, report_path]
    manifest = {
        "schema_version": "1.0",
        "case_id": summary["case_id"],
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in artifacts
        ],
    }
    _write_json(manifest_path, manifest)
    return summary


def _report(summary: Mapping[str, Any], candidates: list[Mapping[str, Any]]) -> str:
    source = summary["source"]
    inventory = summary["archive_inventory"]
    lines = [
        "# Mendeley CoP/Co2P/Co3O4 Public Archive Audit",
        "",
        "**Evidence level:** Diagnostic",
        "",
        "**Result:** `archive_inventory_resolved_annotation_not_ready`",
        "",
        "## Source integrity",
        "",
        f"- Archive: `{source['primary_archive']['filename']}`",
        f"- Bytes: {source['primary_archive']['size_bytes']}",
        f"- SHA-256: `{source['primary_archive']['sha256']}`",
        f"- Duplicate DOI exposes identical content: `{str(source['duplicate_raw_record_content_identical']).lower()}`",
        "",
        "## Inventory",
        "",
        f"- Members: {inventory['member_count']}",
        f"- Files: {inventory['file_count']}",
        f"- TEM candidates by member metadata: {inventory['tem_candidate_member_count']}",
    ]
    lines.extend(f"- `{row['path']}`" for row in candidates)
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "The archive was checksum verified and listed only. No member was extracted, no "
            "Co3O4 region or sample identity was inferred, and no annotation or model evaluation "
            "is authorized.",
            "",
            "## Next",
            "",
            str(summary["next_action"]),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output)
    print(
        json.dumps(
            {
                "result": result["scientific_closeout"]["result"],
                "duplicate_raw_record_content_identical": result["source"][
                    "duplicate_raw_record_content_identical"
                ],
                "member_count": result["archive_inventory"]["member_count"],
                "tem_candidate_member_paths": result["archive_inventory"][
                    "tem_candidate_member_paths"
                ],
                "annotation_pilot_ready": result["readiness"]["annotation_pilot_ready"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
