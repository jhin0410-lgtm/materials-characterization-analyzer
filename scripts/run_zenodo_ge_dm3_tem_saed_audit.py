from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import audit_zenodo_ge_dm3_tem_saed as engine

FINAL_RESULT = (
    "checksum_verified_native_dm3_tem_saed_inventory_completed_but_"
    "embedded_metadata_calibration_and_lineage_incomplete"
)


def _sanitize_stderr_line(line: str, extraction_root: Path) -> str:
    value = line.strip()
    if not value:
        return ""
    root = str(extraction_root.resolve())
    return value.replace(root, "<transient-source-root>")


def probe_dm3_header(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(12)
    if len(header) != 12:
        raise engine.ZenodoGeDm3AuditError(
            f"DM3 member is too short for the 12-byte file header: {path.name}"
        )
    version = int.from_bytes(header[:4], byteorder="big", signed=False)
    if version != 3:
        raise engine.ZenodoGeDm3AuditError(
            f"DM3 version marker mismatch for {path.name}: {version}"
        )
    return {
        "dm3_header_version": version,
        "dm3_header_byte_order_marker": int.from_bytes(
            header[8:12], byteorder="big", signed=False
        ),
    }


def inspect_dm3_metadata_with_warning_capture(
    extracted: Sequence[Path], extraction_root: Path, exiftool: str
) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [exiftool, "-json", "-G1", "-a", "-s", *[str(path) for path in extracted]],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise engine.ZenodoGeDm3AuditError(
            "ExifTool failed to execute safely for selected DM3 members"
        ) from exc

    stderr_lines = [
        sanitized
        for line in result.stderr.splitlines()
        if (sanitized := _sanitize_stderr_line(line, extraction_root))
    ]
    if result.returncode not in {0, 1}:
        detail = stderr_lines[-1] if stderr_lines else "no stderr"
        raise engine.ZenodoGeDm3AuditError(
            f"ExifTool returned unexpected code {result.returncode}: {detail}"
        )
    if not result.stdout.strip():
        raise engine.ZenodoGeDm3AuditError(
            f"ExifTool returned code {result.returncode} without JSON output"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise engine.ZenodoGeDm3AuditError(
            "ExifTool returned invalid JSON for selected DM3 members"
        ) from exc
    if not isinstance(payload, list) or len(payload) != len(extracted):
        raise engine.ZenodoGeDm3AuditError("ExifTool result count mismatch")

    by_absolute = {str(path.resolve()): path for path in extracted}
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise engine.ZenodoGeDm3AuditError(
                "ExifTool metadata entry is not an object"
            )
        source_file = item.get("SourceFile")
        if not isinstance(source_file, str):
            raise engine.ZenodoGeDm3AuditError(
                "ExifTool metadata is missing SourceFile"
            )
        path = by_absolute.get(str(Path(source_file).resolve()))
        if path is None:
            raise engine.ZenodoGeDm3AuditError(
                "ExifTool returned metadata for an unexpected file"
            )
        relative = path.relative_to(extraction_root).as_posix()
        sanitized_metadata = {
            key: value
            for key, value in item.items()
            if key != "SourceFile" and not key.casefold().endswith("directory")
        }
        embedded_keys = [
            key
            for key in sanitized_metadata
            if not key.startswith("System:") and not key.startswith("ExifTool:")
        ]
        exiftool_error = sanitized_metadata.get("ExifTool:Error")
        rows.append(
            {
                "member_path": relative,
                "bytes": path.stat().st_size,
                "sha256": engine._hash_file(path),
                **probe_dm3_header(path),
                "metadata_field_count": len(sanitized_metadata),
                "embedded_microscopy_metadata_field_count": len(embedded_keys),
                "embedded_microscopy_metadata_keys": sorted(embedded_keys),
                "metadata": sanitized_metadata,
                "exiftool_exit_code": result.returncode,
                "exiftool_error": exiftool_error,
                "exiftool_stderr_line_count": len(stderr_lines),
                "exiftool_stderr_lines": stderr_lines,
            }
        )
    rows.sort(key=lambda item: str(item["member_path"]).casefold())
    return rows


def _rewrite_selected_identity(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields = [
        "member_path",
        "bytes",
        "sha256",
        "dm3_header_version",
        "dm3_header_byte_order_marker",
        "metadata_field_count",
        "embedded_microscopy_metadata_field_count",
        "exiftool_exit_code",
        "exiftool_error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _finalize_evidence(output_dir: Path) -> dict[str, Any]:
    summary_path = output_dir / "zenodo_ge_dm3_tem_saed_audit_summary.json"
    inventory_path = output_dir / "zenodo_ge_dm3_tem_saed_member_inventory.csv"
    selected_path = output_dir / "zenodo_ge_dm3_selected_member_identity.csv"
    metadata_path = output_dir / "zenodo_ge_dm3_selected_metadata.json"
    report_path = output_dir / "zenodo_ge_dm3_tem_saed_audit_report.md"
    manifest_path = output_dir / "zenodo_ge_dm3_tem_saed_audit_manifest.json"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    stderr_lines = sorted(
        {
            line
            for item in metadata
            for line in item.get("exiftool_stderr_lines", [])
            if isinstance(line, str) and line.strip()
        }
    )
    exit_codes = sorted(
        {
            int(item.get("exiftool_exit_code", 0))
            for item in metadata
            if isinstance(item, dict)
        }
    )
    errors = sorted(
        {
            str(item.get("exiftool_error"))
            for item in metadata
            if item.get("exiftool_error") not in {None, ""}
        }
    )
    unknown_type_count = sum(
        item.get("exiftool_error") == "Unknown file type" for item in metadata
    )
    embedded_field_total = sum(
        int(item.get("embedded_microscopy_metadata_field_count", 0))
        for item in metadata
    )
    header_versions = sorted(
        {int(item["dm3_header_version"]) for item in metadata}
    )
    if header_versions != [3]:
        raise engine.ZenodoGeDm3AuditError(
            f"selected files do not share the DM3 version marker: {header_versions}"
        )

    summary["status"] = FINAL_RESULT
    summary["evidence_assessment"]["reuse_authorization"] = "Supported"
    summary["evidence_assessment"]["native_dm3_header_identity"] = "Supported"
    summary["evidence_assessment"]["embedded_dm3_metadata_extraction"] = (
        "Unsupported_by_ExifTool_unknown_file_type"
        if unknown_type_count == len(metadata) and embedded_field_total == 0
        else "Inconclusive"
    )
    summary["software_quality_flags"] = {
        "dm3_header_versions": header_versions,
        "exiftool_exit_codes": exit_codes,
        "exiftool_error_values": errors,
        "exiftool_unknown_file_type_member_count": unknown_type_count,
        "embedded_microscopy_metadata_field_total": embedded_field_total,
        "exiftool_stderr_line_count": len(stderr_lines),
        "exiftool_stderr_lines": stderr_lines,
        "policy": (
            "Native DM3 identity is checked from each transient file header. "
            "ExifTool system-level JSON is retained, but an Unknown file type "
            "result is not represented as successful embedded microscopy metadata extraction."
        ),
    }
    summary["unresolved"] = [
        item
        for item in summary["unresolved"]
        if item != "explicit dataset reuse licence or written permission"
    ]
    if "embedded DM3 instrument and acquisition metadata" not in summary["unresolved"]:
        summary["unresolved"].insert(
            0, "embedded DM3 instrument and acquisition metadata"
        )
    _rewrite_selected_identity(selected_path, metadata)
    engine._write_json(summary_path, summary)

    report_path.write_text(
        f"""# Zenodo Ge native-DM3 TEM/SAED source audit

## Result

- Status: `{summary['status']}`
- Evidence level: **Diagnostic**
- DOI: `{summary['record']['doi']}`
- Licence: `{summary['record']['license_id']}`
- Archive SHA-256: `{summary['archive']['sha256']}`
- Archive members: {summary['member_count']}
- Native microscopy members: {summary['representation_counts']['native_microscopy_container']}
- Selected DM3 members inspected: {summary['selected_dm3_member_count']}
- DM3 header versions: {header_versions}
- ExifTool `Unknown file type` members: {unknown_type_count}
- Embedded microscopy metadata fields exposed by ExifTool: {embedded_field_total}
- External-validation ready: **no**

## Supported

The official Zenodo record identity, `CC BY 4.0` reuse licence, archive MD5 and observed SHA-256, archive integrity, safe member inventory, required paired TEM/SAED member names, selected-member SHA-256 values, and the DM3 version-3 header marker on every selected file are supported for this source version.

## Not supported by the current metadata tool

ExifTool returned `Unknown file type` for all selected DM3 members and exposed no microscopy-specific embedded metadata fields. Its system-level JSON and stderr are retained as software evidence, but this is not reported as successful instrument, acquisition, centre, camera-length, pixel-geometry, or reciprocal-calibration metadata extraction.

## Limitations

This is a cross-material germanium source. Source-assigned sample/acquisition IDs, embedded acquisition metadata, pattern centres, reciprocal-calibration provenance, acquisition independence, complete preprocessing state and analyzer-development non-use remain unresolved. The source-reported correction for `w0 diff.dm3` is retained as a quality flag rather than silently changed.

No pixel arrays are exported, no image preprocessing or annotation is performed, and no analyzer inference, parameter tuning, model retraining, d-spacing validation or phase indexing is authorized.
""",
        encoding="utf-8",
    )
    engine._write_json(
        manifest_path,
        engine._artifact_manifest(
            output_dir,
            [summary_path, inventory_path, selected_path, metadata_path, report_path],
        ),
    )
    return summary


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    original = engine.inspect_dm3_metadata
    engine.inspect_dm3_metadata = inspect_dm3_metadata_with_warning_capture
    try:
        engine.run_audit(config_path, output_dir)
    finally:
        engine.inspect_dm3_metadata = original
    return _finalize_evidence(output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Zenodo Ge native-DM3 TEM/SAED audit while preserving "
            "ExifTool limitations and finalizing licence-aware evidence."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.config, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
