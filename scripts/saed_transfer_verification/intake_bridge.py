from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import (
    _ALLOWED_IDENTITY_PROVENANCE,
    _ALLOWED_INTAKE_SOURCE_TYPES,
    _RESPONSE_REFERENCE_TO_INTAKE,
    _SELECTION_FLAGS,
    SAEDTransferVerificationError,
    _boolean,
    _hash,
    _identifier,
    _nonnegative_number,
    _positive_int,
    _positive_number,
    _relative,
    _safe_file,
    _sha256,
    _text,
    _text_list,
)


def _validate_verification_identity(
    verification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> None:
    bundle_sha = verification["response_artifact_manifest_sha256"]
    if bundle_sha != bundle["artifact_manifest_sha256"]:
        raise SAEDTransferVerificationError(
            "response_artifact_manifest_sha256 does not match the response bundle"
        )
    response_source_type = _text(candidate, "source_type")
    intake_source_type = verification["dataset_verification"]["intake_source_type"]
    if response_source_type in _ALLOWED_INTAKE_SOURCE_TYPES:
        if intake_source_type != response_source_type:
            raise SAEDTransferVerificationError(
                "intake_source_type must match the response source_type when directly compatible"
            )
    elif response_source_type == "private_transfer":
        if intake_source_type != "private_acquisition":
            raise SAEDTransferVerificationError(
                "private_transfer must be explicitly resolved as private_acquisition for intake"
            )
    else:
        raise SAEDTransferVerificationError(
            f"unsupported response source_type: {response_source_type}"
        )


def _verify_bounded_root_inventory(
    root: Path,
    verification: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> int:
    allowed = {verification["collection_manifest"]["relative_path"]}
    allowed.update(
        _relative(item, "relative_path") for item in candidate["patterns"]
    )
    observed: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SAEDTransferVerificationError(
                f"data-root contains a symlink outside the transfer contract: "
                f"{path.relative_to(root).as_posix()}"
            )
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            observed.add(relative)
    unexpected = sorted(observed - allowed)
    missing = sorted(allowed - observed)
    if unexpected:
        raise SAEDTransferVerificationError(
            f"data-root contains an unauthorized file: {unexpected[0]}"
        )
    if missing:
        raise SAEDTransferVerificationError(
            f"data-root is missing an authorized declared file: {missing[0]}"
        )
    return len(observed)


def _verify_collection_manifest(
    root: Path,
    verification: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    record = verification["collection_manifest"]
    path = _safe_file(root, record["relative_path"])
    observed_bytes = path.stat().st_size
    observed_sha256 = _hash(path)
    if observed_bytes != record["bytes"]:
        raise SAEDTransferVerificationError(
            "collection manifest byte count does not match verification record"
        )
    if observed_sha256 != record["sha256"]:
        raise SAEDTransferVerificationError(
            "collection manifest SHA-256 does not match verification record"
        )
    if observed_sha256 != _sha256(candidate, "collection_manifest_sha256"):
        raise SAEDTransferVerificationError(
            "collection manifest SHA-256 does not match authoritative response"
        )
    return {
        "relative_path": record["relative_path"],
        "bytes": observed_bytes,
        "sha256": observed_sha256,
    }


def _build_intake_dataset(
    candidate: Mapping[str, Any], verification: Mapping[str, Any]
) -> dict[str, Any]:
    patterns = candidate["patterns"]
    sample_provenances = {
        _text(item, "sample_identity_provenance") for item in patterns
    }
    acquisition_provenances = {
        _text(item, "acquisition_identity_provenance") for item in patterns
    }
    all_provenances = sample_provenances | acquisition_provenances
    if not all_provenances <= _ALLOWED_IDENTITY_PROVENANCE:
        raise SAEDTransferVerificationError(
            "inferred sample or acquisition identity cannot enter intake"
        )
    identity_provenance = (
        "source_assigned"
        if all_provenances == {"source_assigned"}
        else "operator_assigned_at_acquisition"
    )
    dataset_verification = verification["dataset_verification"]
    return {
        "dataset_id": _identifier(candidate, "dataset_id"),
        "dataset_version": _text(candidate, "dataset_version"),
        "source_type": dataset_verification["intake_source_type"],
        "license": _text(candidate, "reuse_license"),
        "reuse_authorized": dataset_verification["reuse_authorization_verified"],
        "identity_provenance": identity_provenance,
        "material_identity_source": dataset_verification[
            "material_identity_source"
        ],
        "target_analyzer_development_nonuse_attested": _boolean(
            candidate, "analyzer_development_nonuse_attested"
        ),
        "creator_overlap_with_analyzer_development_source": dataset_verification[
            "creator_overlap_with_analyzer_development_source"
        ],
        "cross_dataset_lineage_independence_attested": dataset_verification[
            "cross_dataset_lineage_independence_attested"
        ],
        "minimum_independent_samples": dataset_verification[
            "minimum_independent_samples"
        ],
        "minimum_independent_acquisitions": dataset_verification[
            "minimum_independent_acquisitions"
        ],
    }


def _build_intake_pattern(
    candidate: Mapping[str, Any],
    declared: Mapping[str, Any],
    supplemental: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "pattern_id": _identifier(declared, "pattern_id"),
        "relative_path": _relative(declared, "relative_path"),
        "sha256": _sha256(declared, "sha256"),
        "sample_id": _identifier(declared, "sample_id"),
        "acquisition_id": _identifier(declared, "acquisition_id"),
        "material_id": supplemental["material_id"],
        "representation": _text(declared, "representation"),
        "original_detector_intensity_available": _boolean(
            declared, "original_intensity_preserved"
        ),
        "file_format": supplemental["file_format"],
        "accelerating_voltage_kv": _positive_number(
            candidate, "accelerating_voltage_kv"
        ),
        "camera_length_mm": supplemental["camera_length_mm"],
        "detector_model": _text(candidate, "detector_model"),
        "detector_pixel_size_um": _positive_number(
            candidate, "detector_pixel_size_um"
        ),
        "center_x_px": _nonnegative_number(declared, "pattern_center_x_px"),
        "center_y_px": _nonnegative_number(declared, "pattern_center_y_px"),
        "center_source": _text(candidate, "pattern_center_source"),
        "calibration_method": "reciprocal_nm_inv_per_pixel",
        "reciprocal_nm_inv_per_pixel": _positive_number(
            candidate, "reciprocal_calibration_nm_inv_per_pixel"
        ),
        "camera_constant_nm_pixel": None,
        "reference_d_nm": None,
        "reference_radius_px": None,
        "calibration_source": _text(
            candidate, "reciprocal_calibration_source"
        ),
        "preprocessing_operations": supplemental[
            "preprocessing_operations"
        ],
        **{name: supplemental[name] for name in _SELECTION_FLAGS},
        "excluded": supplemental["excluded"],
        "exclusion_reason": supplemental["exclusion_reason"],
    }


def _initial_protocol(
    candidate: Mapping[str, Any], verification: Mapping[str, Any]
) -> dict[str, Any]:
    response_reference = _text(candidate, "reference_type")
    try:
        intake_reference = _RESPONSE_REFERENCE_TO_INTAKE[response_reference]
    except KeyError as exc:
        raise SAEDTransferVerificationError(
            f"response reference_type cannot be represented in intake: {response_reference}"
        ) from exc
    reference_identifier = verification["reference_verification"][
        "intake_reference_identifier"
    ]
    declared_ids = _text_list(candidate, "reference_identifiers")
    if reference_identifier not in declared_ids:
        raise SAEDTransferVerificationError(
            "intake_reference_identifier must be one of the declared references"
        )
    return {
        "source_metadata_review_status": "not_run",
        "file_content_audit_status": "not_run",
        "calibration_review_status": "not_run",
        "acquisition_independence_review_status": "not_run",
        "content_overlap_audit_status": "not_run",
        "analysis_parameters_frozen": False,
        "indexing_protocol_frozen": False,
        "reference_set_frozen": False,
        "manifest_checksum_frozen": False,
        "frozen_manifest_sha256": None,
        "frozen_protocol_id": None,
        "reference_type": intake_reference,
        "reference_identifier": reference_identifier,
        "metrics_frozen": False,
        "uncertainty_method_frozen": False,
        "exclusion_rules_frozen": False,
    }


def _intake_bridge_blockers(
    *,
    candidate: Mapping[str, Any],
    verification: Mapping[str, Any],
    intake_patterns: Sequence[Mapping[str, Any]],
) -> list[str]:
    active = [item for item in intake_patterns if not item["excluded"]]
    blockers: list[str] = []
    dataset = verification["dataset_verification"]
    if not dataset["reuse_authorization_verified"]:
        blockers.append("reuse_authorization_not_independently_verified")
    if dataset["creator_overlap_with_analyzer_development_source"]:
        blockers.append("creator_overlap_with_analyzer_development_source")
    if not dataset["cross_dataset_lineage_independence_attested"]:
        blockers.append("cross_dataset_lineage_independence_not_attested")
    if not _boolean(candidate, "analyzer_development_nonuse_attested"):
        blockers.append("analyzer_development_nonuse_not_attested")
    if len({item["sample_id"] for item in active}) < dataset[
        "minimum_independent_samples"
    ]:
        blockers.append("insufficient_independent_active_samples")
    if len({item["acquisition_id"] for item in active}) < dataset[
        "minimum_independent_acquisitions"
    ]:
        blockers.append("insufficient_independent_active_acquisitions")
    if any(any(item[name] for name in _SELECTION_FLAGS) for item in active):
        blockers.append("active_pattern_reused_for_parameter_selection")
    if not active:
        blockers.append("no_active_patterns")
    return blockers
