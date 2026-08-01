"""Inspect only the microscopy-like members in the verified Mendeley archive.

Source images are extracted to a temporary directory, inspected, hashed, and
deleted. The script exports metadata only; it does not persist or redistribute
source image bytes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from PIL import Image, TiffTags

BASE = "https://data.mendeley.com/public-api"
DATASET_ID = "8w66synjmx"
VERSION = 1
EXPECTED_ARCHIVE_NAME = "database.rar"
EXPECTED_ARCHIVE_SIZE = 3472702
EXPECTED_ARCHIVE_SHA256 = "db3204100545fe3a152c0a545d29ab7f27f85c86594de3e3484bb76020ad7edf"
MEMBERS = (
    "database/figure 1/figure 1b/0002 Ceta.tif",
    "database/figure 1/figure 1c-1e/0007 Ceta.tif",
    "database/figure 1/figure 1g/HAADF_HAADF.bmp",
    "database/figure 1/figure 1h/HAADF_Co.bmp",
    "database/figure 1/figure 1i/HAADF_P.bmp",
    "database/figure 1/figure 1j/HAADF_O.bmp",
)
TIFF_TAGS = {
    "BitsPerSample",
    "Compression",
    "DateTime",
    "ImageDescription",
    "ImageLength",
    "ImageWidth",
    "Make",
    "Model",
    "PhotometricInterpretation",
    "ResolutionUnit",
    "RowsPerStrip",
    "SamplesPerPixel",
    "Software",
    "XResolution",
    "YResolution",
}


def _root_file() -> Mapping[str, Any]:
    url = f"{BASE}/datasets/{DATASET_ID}/files?" + urllib.parse.urlencode(
        {"folder_id": "root", "version": str(VERSION)}
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.mendeley-public-dataset.1+json, application/json",
            "User-Agent": "materials-characterization-analyzer-image-inspection/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], Mapping):
        raise ValueError("primary dataset must expose one root archive")
    return payload[0]


def _download_archive(target: Path) -> None:
    item = _root_file()
    content = item.get("content_details")
    if not isinstance(content, Mapping):
        raise ValueError("archive metadata lacks content_details")
    name = item.get("filename")
    size = content.get("size")
    sha256 = content.get("sha256_hash")
    url = content.get("download_url")
    if name != EXPECTED_ARCHIVE_NAME or size != EXPECTED_ARCHIVE_SIZE or sha256 != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("public archive contract changed")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("archive download URL is unavailable")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "materials-characterization-analyzer-image-inspection/1.0"},
    )
    digest = hashlib.sha256()
    observed_size = 0
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            digest.update(chunk)
            observed_size += len(chunk)
    if observed_size != EXPECTED_ARCHIVE_SIZE or digest.hexdigest() != EXPECTED_ARCHIVE_SHA256:
        target.unlink(missing_ok=True)
        raise ValueError("downloaded archive failed size or SHA-256 verification")


def _extract(archive: Path, directory: Path) -> list[Path]:
    executable = shutil.which("7z") or shutil.which("7zz")
    if executable is None:
        raise RuntimeError("7z or 7zz is required")
    for member in MEMBERS:
        pure = PurePosixPath(member)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError(f"unsafe configured member: {member}")
    subprocess.run(
        [executable, "x", "-y", f"-o{directory}", str(archive), *MEMBERS],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    paths = [directory.joinpath(*PurePosixPath(member).parts) for member in MEMBERS]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"configured microscopy members not extracted: {missing}")
    return paths


def _clean_tag_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "bytes": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, tuple):
        return [_clean_tag_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = value if not isinstance(value, str) else value.strip()
        if isinstance(text, str) and len(text) > 500:
            return {"characters": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()}
        return text
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if isinstance(numerator, int) and isinstance(denominator, int):
        return {"numerator": numerator, "denominator": denominator}
    return str(value)[:500]


def _inspect(path: Path, member: str) -> dict[str, Any]:
    raw = path.read_bytes()
    with Image.open(path) as image:
        image.load()
        tags: dict[str, Any] = {}
        tag_v2 = getattr(image, "tag_v2", None)
        if tag_v2 is not None:
            for code, value in tag_v2.items():
                name = TiffTags.TAGS_V2.get(code, str(code))
                if name in TIFF_TAGS:
                    tags[name] = _clean_tag_value(value)
        extrema = image.getextrema()
        rendered_rgb = image.mode in {"RGB", "RGBA", "P", "CMYK"}
        quantitative_intensity_status = (
            "rendered_multichannel_intensity_not_raw_detector_counts"
            if rendered_rgb
            else "single_channel_intensity_requires_source_calibration_review"
        )
        role = (
            "haadf_or_element_map_rendered_image_not_segmentation_ground_truth"
            if "HAADF_" in Path(member).name
            else "rendered_tem_image_candidate_requires_visual_and_lineage_review"
        )
        return {
            "member_path": member,
            "file_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "format": image.format,
            "mode": image.mode,
            "width_px": image.width,
            "height_px": image.height,
            "frame_count": getattr(image, "n_frames", 1),
            "extrema": _clean_tag_value(extrema),
            "tiff_tags": tags,
            "rendered_multichannel": rendered_rgb,
            "original_detector_intensity_provenance_available": False,
            "pixel_calibration_available": False,
            "scale_bar_or_annotation_absence_verified": False,
            "co3o4_region_binding_available": False,
            "sample_id_available": False,
            "acquisition_id_available": False,
            "candidate_role": role,
            "quantitative_intensity_status": quantitative_intensity_status,
            "annotation_pilot_ready": False,
            "external_model_evaluation_ready": False,
        }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="mca-mendeley-images-") as temp_name:
        temp = Path(temp_name)
        archive = temp / EXPECTED_ARCHIVE_NAME
        _download_archive(archive)
        extracted = _extract(archive, temp / "extracted")
        rows = [_inspect(path, member) for path, member in zip(extracted, MEMBERS)]

    tiff_rows = [row for row in rows if row["format"] == "TIFF"]
    map_rows = [row for row in rows if "haadf_or_element_map" in row["candidate_role"]]
    all_rendered = all(bool(row["rendered_multichannel"]) for row in rows)
    summary = {
        "schema_version": "1.0",
        "case_id": "mendeley_cop_co2p_co3o4_microscopy_member_inspection",
        "source": {
            "dataset_id": DATASET_ID,
            "doi": "10.17632/8w66synjmx.1",
            "archive_name": EXPECTED_ARCHIVE_NAME,
            "archive_size_bytes": EXPECTED_ARCHIVE_SIZE,
            "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        },
        "result_counts": {
            "inspected_member_count": len(rows),
            "tiff_member_count": len(tiff_rows),
            "haadf_or_element_map_member_count": len(map_rows),
            "rendered_multichannel_member_count": sum(
                int(bool(row["rendered_multichannel"])) for row in rows
            ),
        },
        "representation": {
            "all_members_rendered_multichannel": all_rendered,
            "original_detector_intensity_provenance_available": False,
            "pixel_calibration_available": False,
            "co3o4_region_binding_available": False,
            "immutable_sample_or_acquisition_ids_available": False,
        },
        "readiness": {
            "metadata_and_file_hashes_resolved": True,
            "visual_review_required": True,
            "content_overlap_audit_required": True,
            "annotation_pilot_ready": False,
            "external_model_evaluation_ready": False,
        },
        "members": rows,
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": "rendered_microscopy_files_resolved_not_validation_ready",
            "strongest_evidence": (
                "Six microscopy-like archive members were selectively extracted from the "
                "source-checksum-verified archive and inspected without persisting source bytes."
            ),
            "primary_limitation": (
                "The files lack source-supported sample/acquisition IDs, Co3O4 region binding, "
                "independent labels, pixel calibration, and proven detector-intensity provenance."
            ),
            "evidence_that_would_change_conclusion": (
                "Author-supplied mapping from these files to immutable samples/acquisitions and "
                "Co3O4-bearing regions, plus non-use and overlap clearance before blinded annotation."
            ),
        },
    }

    table_path = output / "mendeley_microscopy_member_inventory.csv"
    summary_path = output / "mendeley_microscopy_member_inspection_summary.json"
    report_path = output / "mendeley_microscopy_member_inspection_report.md"
    manifest_path = output / "mendeley_microscopy_member_inspection_manifest.json"
    flat_rows = [
        {key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()}
        for row in rows
    ]
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(flat_rows)
    _write_json(summary_path, summary)
    report_path.write_text(_report(summary), encoding="utf-8")
    artifacts = [table_path, summary_path, report_path]
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


def _report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Mendeley Microscopy Member Inspection",
        "",
        "**Evidence level:** Diagnostic",
        "",
        f"**Result:** `{summary['scientific_closeout']['result']}`",
        "",
        "## Members",
        "",
    ]
    for row in summary["members"]:
        lines.append(
            f"- `{row['member_path']}`: {row['format']} {row['mode']} "
            f"{row['width_px']} x {row['height_px']} px, SHA-256 `{row['sha256']}`"
        )
    lines.extend(
        [
            "",
            "## Readiness",
            "",
            "- Annotation pilot ready: `false`",
            "- External model evaluation ready: `false`",
            "",
            "## Scientific boundary",
            "",
            "These are rendered microscopy files from a mixed CoP/Co2P/Co3O4 study. "
            "Their file presence does not establish Co3O4 segmentation targets, sample or "
            "acquisition independence, calibration, or independent labels.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(
        json.dumps(
            {
                "result": result["scientific_closeout"]["result"],
                "inspected_member_count": result["result_counts"]["inspected_member_count"],
                "all_members_rendered_multichannel": result["representation"][
                    "all_members_rendered_multichannel"
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
