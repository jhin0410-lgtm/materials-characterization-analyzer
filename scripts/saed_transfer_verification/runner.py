from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .common import (
    _ALLOWED_REPRESENTATIONS,
    BLOCKED,
    CASE_ID,
    INTAKE_CASE_ID,
    READY,
    SCHEMA_VERSION,
    SAEDTransferVerificationError,
    _INVENTORY_COLUMNS,
    _SELECTION_FLAGS,
    _artifact_manifest,
    _boolean,
    _cleanup_output,
    _hash,
    _object,
    _positive_int,
    _prepare_output,
    _relative,
    _safe_file,
    _safe_root,
    _sha256,
    _text,
    _write_csv,
    _write_json,
)
from .intake_bridge import (
    _build_intake_dataset,
    _build_intake_pattern,
    _initial_protocol,
    _intake_bridge_blockers,
    _validate_verification_identity,
    _verify_bounded_root_inventory,
    _verify_collection_manifest,
)
from .response_bundle import load_response_bundle
from .verification_record import load_verification_record


def verify_transfer(
    response_bundle: str | Path,
    verification_path: str | Path,
    data_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    bundle = load_response_bundle(response_bundle)
    verification = load_verification_record(verification_path)
    root = _safe_root(data_root)

    candidate = _object(bundle["normalized"].get("candidate"), "normalized candidate")
    _validate_verification_identity(verification, candidate, bundle)
    bounded_file_count = _verify_bounded_root_inventory(root, verification, candidate)
    collection_manifest = _verify_collection_manifest(root, verification, candidate)
    verification_record_sha256 = _hash(Path(verification_path))

    verification_by_id = {
        item["pattern_id"]: item for item in verification["pattern_verifications"]
    }
    declared_patterns = candidate["patterns"]
    declared_ids = {str(item["pattern_id"]) for item in declared_patterns}
    if set(verification_by_id) != declared_ids:
        missing = sorted(declared_ids - set(verification_by_id))
        extra = sorted(set(verification_by_id) - declared_ids)
        detail = f"missing={missing}, extra={extra}"
        raise SAEDTransferVerificationError(
            f"pattern_verifications must exactly match declared patterns: {detail}"
        )

    rows: list[dict[str, Any]] = []
    intake_patterns: list[dict[str, Any]] = []
    for declared in declared_patterns:
        pattern_id = _text(declared, "pattern_id")
        supplemental = verification_by_id[pattern_id]
        path = _safe_file(root, _relative(declared, "relative_path"))
        observed_bytes = path.stat().st_size
        observed_sha256 = _hash(path)
        declared_bytes = _positive_int(declared, "bytes")
        declared_sha256 = _sha256(declared, "sha256")
        if observed_bytes != declared_bytes:
            raise SAEDTransferVerificationError(
                f"pattern byte mismatch for {pattern_id}: "
                f"declared={declared_bytes}, observed={observed_bytes}"
            )
        if observed_sha256 != declared_sha256:
            raise SAEDTransferVerificationError(
                f"pattern SHA-256 mismatch for {pattern_id}"
            )
        if _text(declared, "representation") not in _ALLOWED_REPRESENTATIONS:
            raise SAEDTransferVerificationError(
                f"pattern representation is not raw/lossless: {pattern_id}"
            )
        if _boolean(declared, "original_intensity_preserved") is not True:
            raise SAEDTransferVerificationError(
                f"original detector intensity is not preserved: {pattern_id}"
            )

        parameter_reuse = any(supplemental[name] for name in _SELECTION_FLAGS)
        rows.append(
            {
                "pattern_id": pattern_id,
                "relative_path": declared["relative_path"],
                "declared_bytes": declared_bytes,
                "observed_bytes": observed_bytes,
                "declared_sha256": declared_sha256,
                "observed_sha256": observed_sha256,
                "size_matches": True,
                "sha256_matches": True,
                "sample_id": declared["sample_id"],
                "acquisition_id": declared["acquisition_id"],
                "material_id": supplemental["material_id"],
                "representation": declared["representation"],
                "file_format": supplemental["file_format"],
                "excluded": supplemental["excluded"],
                "parameter_selection_reuse": parameter_reuse,
            }
        )
        intake_patterns.append(
            _build_intake_pattern(candidate, declared, supplemental)
        )

    dataset = _build_intake_dataset(candidate, verification)
    protocol = _initial_protocol(candidate, verification)
    intake_manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_id": INTAKE_CASE_ID,
        "dataset": dataset,
        "patterns": intake_patterns,
        "evaluation_protocol": protocol,
    }

    blockers = _intake_bridge_blockers(
        candidate=candidate,
        verification=verification,
        intake_patterns=intake_patterns,
    )
    ready = not blockers
    status = READY if ready else BLOCKED

    summary = {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "status": status,
        "response_bundle_verified": True,
        "explicit_transfer_authorization_verified": True,
        "collection_manifest_verified": True,
        "response_artifact_manifest_sha256": bundle["artifact_manifest_sha256"],
        "transfer_verification_record_sha256": verification_record_sha256,
        "bounded_data_root_file_count": bounded_file_count,
        "transfer_authorization": verification["transfer_authorization"],
        "declared_pattern_count": len(declared_patterns),
        "checksum_verified_pattern_count": len(rows),
        "active_pattern_count": sum(not item["excluded"] for item in intake_patterns),
        "source_arrays_decoded": False,
        "image_content_inspected": False,
        "center_estimation_performed": False,
        "calibration_inferred": False,
        "saed_analyzer_execution_performed": False,
        "phase_or_reflection_indexing_performed": False,
        "ready_to_run_saed_validation_intake": ready,
        "saed_external_evaluation_ready": False,
        "engineering_release_ready": False,
        "blockers": blockers,
        "collection_manifest": collection_manifest,
        "recommended_next_action": (
            "Run the existing mca saed-validation-intake command on the generated draft; keep all review and protocol-freeze fields fail closed."
            if ready
            else "Resolve the listed transfer or independence blockers before running SAED validation intake."
        ),
        "scientific_closeout": {
            "status": "Diagnostic" if ready else "Inconclusive",
            "strongest_evidence": (
                "The authoritative response bundle, explicit transfer authorization, "
                "collection manifest, and every declared pattern byte count and SHA-256 "
                "were verified without decoding diffraction arrays."
            ),
            "primary_limitation": (
                "Source metadata, file content semantics, calibration, acquisition independence, "
                "content overlap, analysis parameters, indexing protocol, metrics, uncertainty, "
                "and exclusions remain unreviewed or unfrozen."
            ),
            "not_suitable_for": [
                "SAED analyzer execution",
                "center or calibration selection",
                "phase, reflection or zone-axis indexing",
                "external performance claims",
                "engineering release",
            ],
        },
    }

    output, created = _prepare_output(output_dir)
    try:
        inventory_path = output / "saed_verified_transfer_inventory.csv"
        verification_record_path = output / "saed_transfer_verification_record_normalized.json"
        intake_path = output / "saed_external_validation_intake_draft.json"
        summary_path = output / "saed_transfer_verification_summary.json"
        report_path = output / "saed_transfer_verification_report.md"
        manifest_path = output / "saed_transfer_verification_artifact_manifest.json"
        _write_csv(inventory_path, rows)
        _write_json(verification_record_path, verification)
        _write_json(intake_path, intake_manifest)
        _write_json(summary_path, summary)
        report_path.write_text(_report(summary), encoding="utf-8")
        _write_json(
            manifest_path,
            _artifact_manifest(
                output,
                [
                    inventory_path,
                    verification_record_path,
                    intake_path,
                    summary_path,
                    report_path,
                ],
            ),
        )
        return summary
    except Exception:
        _cleanup_output(output, created)
        raise


def _report(summary: Mapping[str, Any]) -> str:
    blockers = summary["blockers"]
    blocker_lines = (
        "\n".join(f"- `{item}`" for item in blockers)
        if blockers
        else "- None at transfer-verification stage."
    )
    return f"""# SAED independent source transfer verification

- Status: `{summary['status']}`
- Response bundle verified: `true`
- Explicit transfer authorization verified: `true`
- Collection manifest verified: `true`
- Checksum-verified patterns: `{summary['checksum_verified_pattern_count']}`
- Ready to run SAED validation intake: `{str(summary['ready_to_run_saed_validation_intake']).lower()}`
- SAED analyzer execution performed: `false`
- External evaluation ready: `false`

## Blockers

{blocker_lines}

This stage verifies transfer identity only. It does not decode diffraction arrays or validate image semantics, centre, reciprocal calibration, acquisition independence, crystallographic references, analyzer performance, or engineering readiness.
"""
