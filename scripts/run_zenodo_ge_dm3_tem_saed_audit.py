from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from scripts import audit_zenodo_ge_dm3_tem_saed as engine

FINAL_RESULT = (
    "checksum_verified_native_dm3_tem_saed_inventory_completed_but_"
    "calibration_and_lineage_metadata_incomplete"
)


def _sanitize_warning(line: str, extraction_root: Path) -> str:
    value = line.strip()
    if not value:
        return ""
    root = str(extraction_root.resolve())
    value = value.replace(root, "<transient-source-root>")
    return value


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

    warnings = [
        sanitized
        for line in result.stderr.splitlines()
        if (sanitized := _sanitize_warning(line, extraction_root))
    ]
    if result.returncode not in {0, 1}:
        detail = warnings[-1] if warnings else "no stderr"
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
        rows.append(
            {
                "member_path": relative,
                "bytes": path.stat().st_size,
                "sha256": engine._hash_file(path),
                "metadata_field_count": len(sanitized_metadata),
                "metadata": sanitized_metadata,
                "exiftool_exit_code": result.returncode,
                "exiftool_warning_count": len(warnings),
                "exiftool_warnings": warnings,
            }
        )
    rows.sort(key=lambda item: str(item["member_path"]).casefold())
    return rows


def _finalize_evidence(output_dir: Path) -> dict[str, Any]:
    summary_path = output_dir / "zenodo_ge_dm3_tem_saed_audit_summary.json"
    inventory_path = output_dir / "zenodo_ge_dm3_tem_saed_member_inventory.csv"
    selected_path = output_dir / "zenodo_ge_dm3_selected_member_identity.csv"
    metadata_path = output_dir / "zenodo_ge_dm3_selected_metadata.json"
    report_path = output_dir / "zenodo_ge_dm3_tem_saed_audit_report.md"
    manifest_path = output_dir / "zenodo_ge_dm3_tem_saed_audit_manifest.json"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    warning_lines = sorted(
        {
            warning
            for item in metadata
            for warning in item.get("exiftool_warnings", [])
            if isinstance(warning, str) and warning.strip()
        }
    )
    exit_codes = sorted(
        {
            int(item.get("exiftool_exit_code", 0))
            for item in metadata
            if isinstance(item, dict)
        }
    )

    summary["status"] = FINAL_RESULT
    summary["evidence_assessment"]["reuse_authorization"] = "Supported"
    summary["evidence_assessment"]["dm3_metadata_extraction"] = (
        "Supported_with_recorded_ExifTool_warnings"
        if warning_lines or any(code != 0 for code in exit_codes)
        else "Supported"
    )
    summary["software_quality_flags"] = {
        "exiftool_exit_codes": exit_codes,
        "exiftool_warning_count": len(warning_lines),
        "exiftool_warnings": warning_lines,
        "policy": (
            "ExifTool exit code 1 is accepted only when complete JSON for every "
            "selected member is present; warnings are retained in metadata evidence."
        ),
    }
    summary["unresolved"] = [
        item
        for item in summary["unresolved"]
        if item != "explicit dataset reuse licence or written permission"
    ]
    engine._write_json(summary_path, summary)

    report_path.write_text(
        f"""# Zenodo Ge native-DM3 TEM/SAED source audit

## Result

- Status: `{summary['status']}`
- Evidence level: **Diagnostic**
- DOI: `{summary['record']['doi']}`
- Licence: `{summary['record']['license_id']}`
- Archive SHA-256: `{summary['archive']['sha256']}`
- Native microscopy members: {summary['representation_counts']['native_microscopy_container']}
- Static-SAED filename cues: {summary['role_cue_counts']['static_saed_name_cue']}
- TEM filename cues: {summary['role_cue_counts']['tem_name_cue']}
- HRTEM filename cues: {summary['role_cue_counts']['hrtem_name_cue']}
- Selected DM3 members inspected: {summary['selected_dm3_member_count']}
- ExifTool warning count: {len(warning_lines)}
- External-validation ready: **no**

## Supported

The official Zenodo record identity, `CC BY 4.0` reuse licence, archive MD5 and observed SHA-256, archive integrity, safe member inventory, required paired TEM/SAED member names, native DM3 representation and selected-member identities are supported for this source version.

ExifTool produced complete JSON for every selected DM3 member. Any non-zero informational or warning exit state is recorded rather than silently discarded.

## Limitations

This is a cross-material germanium source. Source-assigned sample/acquisition IDs, pattern centres, reciprocal-calibration provenance, acquisition independence, complete preprocessing state and analyzer-development non-use remain unresolved. The record-reported correction for `w0 diff.dm3` is retained as a quality flag rather than silently changed.

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
            "non-fatal ExifTool warnings and finalizing licence-aware evidence."
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
