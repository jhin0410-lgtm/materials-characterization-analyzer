"""Discover and acquire a small, provenance-recorded public multimodal dataset subset.

This script does not interpret scientific results. It queries the Recherche Data
Gouv Dataverse metadata API, selects one DWCNT source file per configured
technique, downloads only those files, verifies available checksums, and writes
an inventory/readiness report for the end-to-end case study.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_ROOT = "https://entrepot.recherche.data.gouv.fr/api"
DEFAULT_CONFIG = Path("case_studies/public_carbon_multimodal/case_config.json")


def _request_bytes(url: str, *, timeout: int = 120) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "materials-characterization-analyzer-public-case/1.0",
            "Accept": "application/json, application/octet-stream, */*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} while requesting {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def _request_json(url: str) -> dict[str, Any]:
    payload = json.loads(_request_bytes(url).decode("utf-8"))
    if payload.get("status") not in {None, "OK"}:
        raise RuntimeError(f"Dataverse API returned non-OK status: {payload.get('status')}")
    return payload


def dataset_metadata_url(persistent_id: str) -> str:
    query = urllib.parse.urlencode({"persistentId": persistent_id})
    return f"{API_ROOT}/datasets/:persistentId/?{query}"


def datafile_download_url(datafile_id: int) -> str:
    return f"{API_ROOT}/access/datafile/{datafile_id}?format=original"


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def flatten_inventory(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {})
    version = data.get("latestVersion") or data.get("draftVersion") or {}
    files = version.get("files", [])
    inventory: list[dict[str, Any]] = []
    for entry in files:
        data_file = entry.get("dataFile", {})
        checksum = data_file.get("checksum") or {}
        filename = str(data_file.get("filename") or entry.get("label") or "")
        directory = str(entry.get("directoryLabel") or "")
        inventory.append(
            {
                "datafile_id": data_file.get("id"),
                "persistent_id": data_file.get("persistentId"),
                "filename": filename,
                "directory_label": directory,
                "path": f"{directory}/{filename}".strip("/"),
                "content_type": data_file.get("contentType"),
                "filesize": data_file.get("filesize"),
                "description": entry.get("description") or "",
                "checksum_type": checksum.get("type"),
                "checksum_value": checksum.get("value"),
                "restricted": bool(entry.get("restricted", False)),
            }
        )
    return inventory


def _normalized_text(record: dict[str, Any]) -> str:
    return " ".join(
        [
            str(record.get("path", "")),
            str(record.get("description", "")),
            str(record.get("content_type", "")),
        ]
    ).casefold()


def score_record(record: dict[str, Any], rule: dict[str, Any]) -> int | None:
    text = _normalized_text(record)
    suffix = Path(str(record.get("filename", ""))).suffix.casefold()
    extensions = {str(value).casefold() for value in rule.get("extensions", [])}
    if extensions and suffix not in extensions:
        return None
    for token in rule.get("required_tokens", []):
        if str(token).casefold() not in text:
            return None
    for token in rule.get("excluded_tokens", []):
        if str(token).casefold() in text:
            return None
    score = 100
    for token in rule.get("preferred_tokens", []):
        if str(token).casefold() in text:
            score += 20
    if record.get("restricted"):
        score -= 1_000
    if record.get("datafile_id") is None:
        score -= 1_000
    filename = str(record.get("filename", "")).casefold()
    if "raw" in filename or "raw" in str(record.get("directory_label", "")).casefold():
        score += 5
    return score


def select_files(
    inventory: list[dict[str, Any]], modalities: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any] | None], dict[str, list[dict[str, Any]]]]:
    selected: dict[str, dict[str, Any] | None] = {}
    candidates: dict[str, list[dict[str, Any]]] = {}
    for modality, rule in modalities.items():
        scored: list[tuple[int, dict[str, Any]]] = []
        for record in inventory:
            score = score_record(record, rule)
            if score is not None:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("path", ""))))
        candidates[modality] = [dict(record, selection_score=score) for score, record in scored]
        selected[modality] = candidates[modality][0] if candidates[modality] else None
    return selected, candidates


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_source_checksum(payload: bytes, record: dict[str, Any]) -> dict[str, Any]:
    checksum_type = str(record.get("checksum_type") or "").upper()
    expected = str(record.get("checksum_value") or "").lower()
    result = {
        "source_checksum_type": checksum_type or None,
        "source_checksum_expected": expected or None,
        "source_checksum_verified": None,
    }
    if not checksum_type or not expected:
        return result
    algorithms = {"MD5": "md5", "SHA-1": "sha1", "SHA-256": "sha256"}
    algorithm = algorithms.get(checksum_type)
    if algorithm is None:
        return result
    actual = hashlib.new(algorithm, payload).hexdigest().lower()
    result["source_checksum_actual"] = actual
    result["source_checksum_verified"] = actual == expected
    return result


def safe_filename(modality: str, source_filename: str) -> str:
    suffix = Path(source_filename).suffix.lower() or ".bin"
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(source_filename).stem).strip("_")
    return f"{modality}__{stem}{suffix}"


def preview_bytes(payload: bytes, record: dict[str, Any]) -> dict[str, Any]:
    content_type = str(record.get("content_type") or "")
    suffix = Path(str(record.get("filename") or "")).suffix.casefold()
    text_suffixes = {".csv", ".tab", ".tsv", ".txt", ".asc", ".dat"}
    result: dict[str, Any] = {"byte_count": len(payload)}
    if suffix in text_suffixes or content_type.startswith("text/"):
        text = payload.decode("utf-8", errors="replace")
        lines = text.splitlines()
        result.update(
            {
                "preview_type": "text",
                "line_count": len(lines),
                "first_lines": lines[:25],
            }
        )
    else:
        result["preview_type"] = "binary"
        result["first_32_bytes_hex"] = payload[:32].hex()
    return result


def write_markdown_report(
    output_path: Path,
    config: dict[str, Any],
    inventory: list[dict[str, Any]],
    selected: dict[str, dict[str, Any] | None],
    downloads: dict[str, dict[str, Any]],
) -> None:
    availability = config.get("availability_contract", {})
    lines = [
        "# Public Carbon Multimodal Discovery Report",
        "",
        f"- Case ID: `{config['case_id']}`",
        f"- Dataset DOI: `{config['dataset']['persistent_id']}`",
        f"- Dataset version: `{config['dataset']['version']}`",
        f"- License: `{config['dataset']['license']}`",
        f"- Inventory files: `{len(inventory)}`",
        f"- Primary source label: `{config['primary_sample']['source_label']}`",
        "",
        "## Modality Readiness",
        "",
        "| Modality | Dataset expectation | Selected source | Acquisition status |",
        "|---|---|---|---|",
    ]
    for modality in config["modalities"]:
        record = selected.get(modality)
        selected_path = record.get("path") if record else "—"
        status = downloads.get(modality, {}).get("status", "not_selected")
        lines.append(
            f"| {modality} | {availability.get(modality, 'unspecified')} | "
            f"`{selected_path}` | {status} |"
        )
    for modality in ("saed", "dsc"):
        lines.append(
            f"| {modality} | {availability.get(modality, 'not_provided')} | — | not_downloaded |"
        )
    lines.extend(
        [
            "",
            "## Scientific Boundary",
            "",
            "This report proves only that public source files were discovered, selected, downloaded, and checksummed. "
            "It does not prove that all techniques used the identical physical aliquot, that acquisition conditions are "
            "comparable, or that analyzer outputs are scientifically validated.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run(config_path: Path, output_dir: Path, *, download: bool) -> int:
    config = load_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_url = dataset_metadata_url(config["dataset"]["persistent_id"])
    payload = _request_json(metadata_url)
    inventory = flatten_inventory(payload)
    if not inventory:
        raise RuntimeError("Dataverse metadata contained no files.")

    selected, candidates = select_files(inventory, config["modalities"])
    (output_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "selection_candidates.json").write_text(
        json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "selected_files.json").write_text(
        json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    downloads: dict[str, dict[str, Any]] = {}
    raw_dir = output_dir / "raw"
    if download:
        raw_dir.mkdir(parents=True, exist_ok=True)
        for modality, record in selected.items():
            if record is None:
                downloads[modality] = {"status": "not_found"}
                continue
            if record.get("restricted"):
                downloads[modality] = {"status": "restricted", "record": record}
                continue
            datafile_id = record.get("datafile_id")
            if not isinstance(datafile_id, int):
                downloads[modality] = {"status": "missing_datafile_id", "record": record}
                continue
            file_payload = _request_bytes(datafile_download_url(datafile_id))
            destination = raw_dir / safe_filename(modality, str(record["filename"]))
            destination.write_bytes(file_payload)
            checksum = verify_source_checksum(file_payload, record)
            downloads[modality] = {
                "status": "downloaded",
                "local_path": str(destination),
                "source_path": record.get("path"),
                "source_persistent_id": record.get("persistent_id"),
                "datafile_id": datafile_id,
                "download_url": datafile_download_url(datafile_id),
                "downloaded_sha256": sha256_bytes(file_payload),
                **checksum,
                **preview_bytes(file_payload, record),
            }
    (output_dir / "downloads.json").write_text(
        json.dumps(downloads, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_markdown_report(
        output_dir / "discovery_report.md", config, inventory, selected, downloads
    )

    summary = {
        "case_id": config["case_id"],
        "dataset_persistent_id": config["dataset"]["persistent_id"],
        "inventory_count": len(inventory),
        "selected_modalities": [key for key, value in selected.items() if value is not None],
        "missing_modalities": [key for key, value in selected.items() if value is None],
        "download_status": {key: value.get("status") for key, value in downloads.items()},
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args.config, args.output, download=args.download)
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports actionable context.
        print(f"public carbon discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
