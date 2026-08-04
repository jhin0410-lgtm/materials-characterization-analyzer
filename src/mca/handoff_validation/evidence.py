"""Checksum-bound validation evidence writer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .common import BUNDLE_SCHEMA_VERSION
from .validator import validate_characterization_handoff_bundle

def write_handoff_bundle_validation(
    bundle_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Validate a bundle and write checksum-bound validation evidence."""

    summary = validate_characterization_handoff_bundle(bundle_dir)
    output = Path(output_dir)
    created = False
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output must be absent or an empty directory")
    else:
        output.mkdir(parents=True)
        created = True

    summary_path = output / "handoff_bundle_validation_summary.json"
    report_path = output / "handoff_bundle_validation_report.md"
    manifest_path = output / "handoff_bundle_validation_artifact_manifest.json"
    summary_bytes = (
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    report_bytes = _validation_report(summary).encode("utf-8")
    artifact_manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "case_id": "characterization_handoff_bundle_validation",
        "artifact_count": 2,
        "artifacts": [
            _payload_record(summary_path.name, summary_bytes),
            _payload_record(report_path.name, report_bytes),
        ],
    }
    manifest_bytes = (
        json.dumps(artifact_manifest, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
    ).encode("utf-8")

    temporary: list[Path] = []
    written: list[Path] = []
    payloads = {
        summary_path: summary_bytes,
        report_path: report_bytes,
        manifest_path: manifest_bytes,
    }
    try:
        for target, payload in payloads.items():
            temp = output / f".{target.name}.tmp"
            if temp.exists():
                raise FileExistsError(f"temporary validation artifact already exists: {temp}")
            temp.write_bytes(payload)
            temporary.append(temp)
        for target, temp in zip(payloads, temporary, strict=True):
            temp.replace(target)
            written.append(target)
    except Exception:
        for temp in temporary:
            temp.unlink(missing_ok=True)
        for target in written:
            target.unlink(missing_ok=True)
        if created:
            try:
                output.rmdir()
            except OSError:
                pass
        raise
    return {
        "summary": summary_path,
        "report": report_path,
        "artifact_manifest": manifest_path,
    }


def _payload_record(path: str, payload: bytes) -> dict[str, Any]:
    import hashlib

    return {
        "path": path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _validation_report(summary: Mapping[str, Any]) -> str:
    instruments = ", ".join(summary["instruments"])
    return f"""# Characterization handoff bundle validation

- Status: `{summary['status']}`
- Case ID: `{summary['case_id']}`
- Producer: `{summary['producer_repository']}`
- Samples: `{summary['sample_count']}`
- Measurements: `{summary['measurement_count']}`
- Features: `{summary['feature_count']}`
- Instruments: `{instruments}`
- Evidence level declared by producer: `{summary['evidence_level']}`
- Row-order join allowed: `false`
- Aggregation performed: `false`
- Missing metadata inferred: `false`
- Scientific comparability established: `false`
- Engineering release ready: `false`

## Boundary

{summary['scientific_boundary']}
"""
