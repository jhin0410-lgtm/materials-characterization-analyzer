"""Download and inventory the public RWGS XRD/SEM-EDS dataset without interpreting it.

The script verifies the Zenodo-published MD5 checksums, safely extracts the two
small source archives, records SHA-256 provenance for every downloaded file,
extracts plain text from the synthesis-protocol DOCX, and writes a readiness
report. It deliberately does not choose a sample, infer SEM scale, convert EDS
spectra to composition, or run scientific analyzers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree


DEFAULT_CONFIG = Path("case_studies/public_rwgs_xrd_sem_eds/discovery_config.json")
USER_AGENT = "materials-characterization-analyzer-rwgs-discovery/1.0"


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def request_bytes(url: str, *, timeout: int = 120) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/octet-stream, application/zip, */*",
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


def digest(payload: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, payload).hexdigest().lower()


def verify_md5(payload: bytes, expected: str) -> str:
    actual = digest(payload, "md5")
    if actual != expected.lower():
        raise RuntimeError(f"MD5 mismatch: expected {expected.lower()}, received {actual}")
    return actual


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = posixpath.normpath(name.replace("\\", "/"))
    path = PurePosixPath(normalized)
    if path.is_absolute() or normalized in {".", ".."} or ".." in path.parts:
        raise ValueError(f"Unsafe ZIP member path: {name}")
    return path


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    return (unix_mode & 0o170000) == 0o120000


def inventory_zip(payload: bytes) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        for info in archive.infolist():
            safe_path = _safe_member_path(info.filename)
            if _is_symlink(info):
                raise ValueError(f"Symbolic links are not allowed in source ZIPs: {info.filename}")
            inventory.append(
                {
                    "path": safe_path.as_posix(),
                    "is_directory": info.is_dir(),
                    "size_bytes": info.file_size,
                    "compressed_size_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                    "suffix": Path(safe_path.name).suffix.lower(),
                }
            )
    return inventory


def extract_zip_safely(payload: bytes, output_dir: Path) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = inventory_zip(payload)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        for info in archive.infolist():
            safe_path = _safe_member_path(info.filename)
            if info.is_dir():
                (output_dir / Path(*safe_path.parts)).mkdir(parents=True, exist_ok=True)
                continue
            destination = output_dir / Path(*safe_path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
    return inventory


def extract_docx_text(payload: bytes) -> str:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("DOCX does not contain word/document.xml") from exc
    root = ElementTree.fromstring(document_xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        fragments = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        text = "".join(fragments).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def summarize_archive(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    files = [record for record in inventory if not record["is_directory"]]
    suffix_counts: dict[str, int] = {}
    for record in files:
        suffix = record["suffix"] or "<none>"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    return {
        "member_count": len(inventory),
        "file_count": len(files),
        "total_uncompressed_bytes": sum(int(record["size_bytes"]) for record in files),
        "suffix_counts": dict(sorted(suffix_counts.items())),
    }


def write_report(
    output_path: Path,
    config: dict[str, Any],
    downloads: dict[str, dict[str, Any]],
    archive_summaries: dict[str, dict[str, Any]],
) -> None:
    boundary = config["scientific_boundary"]
    lines = [
        "# Public RWGS XRD/SEM-EDS Discovery Report",
        "",
        f"- Case ID: `{config['case_id']}`",
        f"- Dataset DOI: `{config['dataset']['doi']}`",
        f"- Dataset version: `{config['dataset']['version']}`",
        f"- License: `{config['dataset']['license']}`",
        "",
        "## Download Verification",
        "",
        "| Source | Status | Bytes | Published MD5 verified | Downloaded SHA-256 |",
        "|---|---|---:|---|---|",
    ]
    for key, record in downloads.items():
        lines.append(
            f"| `{key}` | {record['status']} | {record['byte_count']} | "
            f"{record['md5_verified']} | `{record['sha256']}` |"
        )
    lines.extend(["", "## Archive Inventory", ""])
    for key, summary in archive_summaries.items():
        lines.extend(
            [
                f"### {key}",
                "",
                f"- Files: `{summary['file_count']}`",
                f"- Members including directories: `{summary['member_count']}`",
                f"- Uncompressed bytes: `{summary['total_uncompressed_bytes']}`",
                f"- Suffix counts: `{json.dumps(summary['suffix_counts'], sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Scientific Readiness Boundary",
            "",
            f"- Same study confirmed: `{str(boundary['same_study_confirmed']).lower()}`",
            f"- Same material class expected: `{str(boundary['same_material_class_expected']).lower()}`",
            f"- Same physical aliquot confirmed: `{str(boundary['same_physical_aliquot_confirmed']).lower()}`",
            f"- Sample mapping: `{boundary['sample_mapping_status']}`",
            f"- SEM scale: `{boundary['sem_scale_status']}`",
            f"- EDS quantification: `{boundary['eds_quantification_status']}`",
            "",
            "This discovery run validates acquisition and archive structure only. It does not prove that "
            "XRD, SEM, and EDS files correspond to the same physical aliquot, that SEM threshold "
            "segmentation is suitable, or that proprietary DAT files contain directly usable quantitative "
            "composition tables.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run(config_path: Path, output_dir: Path) -> int:
    config = load_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    extracted_dir = output_dir / "extracted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    downloads: dict[str, dict[str, Any]] = {}
    archive_inventories: dict[str, list[dict[str, Any]]] = {}
    archive_summaries: dict[str, dict[str, Any]] = {}

    for key, source in config["files"].items():
        payload = request_bytes(source["url"])
        actual_md5 = verify_md5(payload, source["md5"])
        destination = raw_dir / source["filename"]
        destination.write_bytes(payload)
        downloads[key] = {
            "status": "downloaded",
            "source_url": source["url"],
            "source_filename": source["filename"],
            "local_path": str(destination),
            "byte_count": len(payload),
            "published_md5": source["md5"].lower(),
            "actual_md5": actual_md5,
            "md5_verified": True,
            "sha256": digest(payload, "sha256"),
        }

        if source["filename"].lower().endswith(".zip"):
            inventory = extract_zip_safely(payload, extracted_dir / key)
            archive_inventories[key] = inventory
            archive_summaries[key] = summarize_archive(inventory)
        elif source["filename"].lower().endswith(".docx"):
            protocol_text = extract_docx_text(payload)
            (output_dir / "synthesis_protocol.txt").write_text(protocol_text, encoding="utf-8")

    (output_dir / "downloads.json").write_text(
        json.dumps(downloads, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "archive_inventories.json").write_text(
        json.dumps(archive_inventories, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "archive_summaries.json").write_text(
        json.dumps(archive_summaries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_report(output_dir / "discovery_report.md", config, downloads, archive_summaries)

    print(
        json.dumps(
            {
                "case_id": config["case_id"],
                "download_status": {key: value["status"] for key, value in downloads.items()},
                "archive_summaries": archive_summaries,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args.config, args.output)
    except (RuntimeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"Discovery failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
