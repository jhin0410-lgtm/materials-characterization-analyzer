from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    CASE_ID,
    SCHEMA_VERSION,
    SOURCE_REQUEST_CASE_ID,
    _ALLOWED_INTAKE_SOURCE_TYPES,
    _SELECTION_FLAGS,
    SAEDTransferVerificationError,
    _at_least_two,
    _boolean,
    _date,
    _identifier,
    _load_json,
    _object,
    _only,
    _optional_positive_number,
    _optional_text,
    _positive_int,
    _relative,
    _sha256,
    _text,
    _text_list,
)


def load_verification_record(path: str | Path) -> dict[str, Any]:
    payload = _load_json(Path(path), "transfer verification record")
    _only(
        payload,
        {
            "schema_version",
            "case_id",
            "response_case_id",
            "response_artifact_manifest_sha256",
            "transfer_authorization",
            "collection_manifest",
            "dataset_verification",
            "reference_verification",
            "pattern_verifications",
        },
        "transfer verification record",
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SAEDTransferVerificationError(
            "transfer verification schema_version mismatch"
        )
    if payload.get("case_id") != CASE_ID:
        raise SAEDTransferVerificationError(
            "transfer verification case_id mismatch"
        )
    if payload.get("response_case_id") != SOURCE_REQUEST_CASE_ID:
        raise SAEDTransferVerificationError(
            "transfer verification response_case_id mismatch"
        )
    response_manifest_sha = _sha256(payload, "response_artifact_manifest_sha256")

    authorization = _object(
        payload.get("transfer_authorization"), "transfer_authorization"
    )
    _only(
        authorization,
        {
            "authorized",
            "authorized_by",
            "authority_basis",
            "authorized_at",
            "scope",
        },
        "transfer_authorization",
    )
    if _boolean(authorization, "authorized") is not True:
        raise SAEDTransferVerificationError(
            "transfer_authorization.authorized must be true"
        )
    authorized_at = _date(authorization, "authorized_at")
    scope = _text(authorization, "scope")
    if scope != "declared_patterns_and_collection_manifest_only":
        raise SAEDTransferVerificationError(
            "transfer authorization scope must be declared patterns and collection manifest only"
        )

    collection = _object(payload.get("collection_manifest"), "collection_manifest")
    _only(
        collection,
        {"relative_path", "sha256", "bytes"},
        "collection_manifest",
    )
    collection_record = {
        "relative_path": _relative(collection, "relative_path"),
        "sha256": _sha256(collection, "sha256"),
        "bytes": _positive_int(collection, "bytes"),
    }

    dataset = _object(
        payload.get("dataset_verification"), "dataset_verification"
    )
    _only(
        dataset,
        {
            "intake_source_type",
            "source_type_mapping_basis",
            "reuse_authorization_verified",
            "material_identity_source",
            "creator_overlap_with_analyzer_development_source",
            "cross_dataset_lineage_independence_attested",
            "minimum_independent_samples",
            "minimum_independent_acquisitions",
        },
        "dataset_verification",
    )
    intake_source_type = _text(dataset, "intake_source_type")
    if intake_source_type not in _ALLOWED_INTAKE_SOURCE_TYPES:
        raise SAEDTransferVerificationError(
            f"unsupported intake_source_type: {intake_source_type}"
        )
    dataset_record = {
        "intake_source_type": intake_source_type,
        "source_type_mapping_basis": _text(dataset, "source_type_mapping_basis"),
        "reuse_authorization_verified": _boolean(
            dataset, "reuse_authorization_verified"
        ),
        "material_identity_source": _text(dataset, "material_identity_source"),
        "creator_overlap_with_analyzer_development_source": _boolean(
            dataset, "creator_overlap_with_analyzer_development_source"
        ),
        "cross_dataset_lineage_independence_attested": _boolean(
            dataset, "cross_dataset_lineage_independence_attested"
        ),
        "minimum_independent_samples": _at_least_two(
            dataset, "minimum_independent_samples"
        ),
        "minimum_independent_acquisitions": _at_least_two(
            dataset, "minimum_independent_acquisitions"
        ),
    }

    reference = _object(
        payload.get("reference_verification"), "reference_verification"
    )
    _only(
        reference,
        {
            "intake_reference_identifier",
            "reference_identifier_selection_basis",
        },
        "reference_verification",
    )
    reference_record = {
        "intake_reference_identifier": _text(
            reference, "intake_reference_identifier"
        ),
        "reference_identifier_selection_basis": _text(
            reference, "reference_identifier_selection_basis"
        ),
    }

    patterns = payload.get("pattern_verifications")
    if not isinstance(patterns, list) or not patterns:
        raise SAEDTransferVerificationError(
            "pattern_verifications must be a non-empty list"
        )
    normalized_patterns = [
        _pattern_verification(item, index) for index, item in enumerate(patterns)
    ]
    ids = [item["pattern_id"] for item in normalized_patterns]
    if len(ids) != len(set(ids)):
        raise SAEDTransferVerificationError(
            "pattern_verification pattern_id values must be unique"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "response_case_id": SOURCE_REQUEST_CASE_ID,
        "response_artifact_manifest_sha256": response_manifest_sha,
        "transfer_authorization": {
            "authorized": True,
            "authorized_by": _text(authorization, "authorized_by"),
            "authority_basis": _text(authorization, "authority_basis"),
            "authorized_at": authorized_at,
            "scope": scope,
        },
        "collection_manifest": collection_record,
        "dataset_verification": dataset_record,
        "reference_verification": reference_record,
        "pattern_verifications": normalized_patterns,
    }


def _pattern_verification(value: Any, index: int) -> dict[str, Any]:
    item = _object(value, f"pattern_verifications[{index}]")
    allowed = {
        "pattern_id",
        "material_id",
        "file_format",
        "camera_length_mm",
        "preprocessing_operations",
        *_SELECTION_FLAGS,
        "excluded",
        "exclusion_reason",
    }
    _only(item, allowed, f"pattern_verifications[{index}]")
    preprocessing = _text_list(item, "preprocessing_operations")
    normalized = {entry.casefold() for entry in preprocessing}
    if len(normalized) != len(preprocessing):
        raise SAEDTransferVerificationError(
            "preprocessing_operations must not contain duplicates"
        )
    if "none" in normalized and len(normalized) != 1:
        raise SAEDTransferVerificationError(
            "preprocessing operation 'none' cannot be combined with other operations"
        )
    excluded = _boolean(item, "excluded")
    exclusion_reason = _optional_text(item.get("exclusion_reason"), "exclusion_reason")
    if excluded != (exclusion_reason is not None):
        raise SAEDTransferVerificationError(
            "excluded and exclusion_reason must agree"
        )
    record = {
        "pattern_id": _text(item, "pattern_id"),
        "material_id": _identifier(item, "material_id"),
        "file_format": _text(item, "file_format"),
        "camera_length_mm": _optional_positive_number(
            item.get("camera_length_mm"), "camera_length_mm"
        ),
        "preprocessing_operations": preprocessing,
        "excluded": excluded,
        "exclusion_reason": exclusion_reason,
    }
    for flag in _SELECTION_FLAGS:
        record[flag] = _boolean(item, flag)
    return record
