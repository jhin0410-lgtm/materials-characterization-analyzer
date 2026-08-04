"""Core fail-closed characterization handoff bundle validator."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..provenance import sha256_file
from .common import (
    BUNDLE_SCHEMA_VERSION, BUNDLE_TYPE, FEATURE_FILE_NAME, MANIFEST_FILE_NAME,
    SAMPLE_CONTEXT_FILE_NAME, SUPPORTED_EVIDENCE_LEVELS, VALIDATION_STATUS,
    _REQUIRED_EVIDENCE_REFERENCES, HandoffBundleValidationError, _file_record,
    _load_json_object, _nonempty_text, _object, _reject_unknown,
    _safe_direct_file, _unique_text_list, _verify_file_record,
)
from .tables import _validate_context_table, _validate_feature_table

def validate_characterization_handoff_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Validate bundle identity, checksums, schemas, joins, and claim boundaries.

    This function does not interpret scientific meaning, aggregate features, or
    establish that different measurements used the same physical aliquot.
    """

    root = Path(bundle_dir)
    if not root.is_dir() or root.is_symlink():
        raise HandoffBundleValidationError("bundle must be a real directory")
    root = root.resolve()

    manifest_path = _safe_direct_file(root, MANIFEST_FILE_NAME, "bundle manifest")
    manifest = _load_json_object(manifest_path, "bundle manifest")
    _reject_unknown(
        manifest,
        {
            "schema_version",
            "bundle_type",
            "case_id",
            "producer",
            "join_contract",
            "feature_table",
            "sample_context",
            "evidence_references",
            "scientific_closeout",
        },
        "bundle manifest",
    )
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise HandoffBundleValidationError("unsupported bundle schema_version")
    if manifest.get("bundle_type") != BUNDLE_TYPE:
        raise HandoffBundleValidationError("bundle_type mismatch")
    case_id = _nonempty_text(manifest, "case_id")

    producer = _object(manifest.get("producer"), "producer")
    _reject_unknown(
        producer,
        {"repository", "software_versions", "analysis_result_schema_versions"},
        "producer",
    )
    producer_repository = _nonempty_text(producer, "repository")
    software_versions = _unique_text_list(producer, "software_versions", allow_empty=True)
    result_schema_versions = _unique_text_list(
        producer, "analysis_result_schema_versions", allow_empty=True
    )

    join_contract = _object(manifest.get("join_contract"), "join_contract")
    expected_join = {
        "join_key": "sample_id",
        "row_order_join_allowed": False,
        "aggregation_performed": False,
        "missing_metadata_inferred": False,
    }
    if join_contract != expected_join:
        raise HandoffBundleValidationError("join_contract must match the fail-closed sample_id contract")

    feature_record = _file_record(manifest.get("feature_table"), "feature_table")
    context_record = _file_record(manifest.get("sample_context"), "sample_context")
    if feature_record["path"] != FEATURE_FILE_NAME:
        raise HandoffBundleValidationError("feature_table path mismatch")
    if context_record["path"] != SAMPLE_CONTEXT_FILE_NAME:
        raise HandoffBundleValidationError("sample_context path mismatch")

    feature_path = _verify_file_record(root, feature_record, "feature_table")
    context_path = _verify_file_record(root, context_record, "sample_context")
    feature_table = _validate_feature_table(feature_path, feature_record)
    context_table = _validate_context_table(context_path, context_record)

    feature_sample_ids = sorted(set(feature_table["sample_id"].astype(str)))
    context_sample_ids = sorted(set(context_table["sample_id"].astype(str)))
    if feature_sample_ids != context_sample_ids:
        raise HandoffBundleValidationError(
            "feature and sample-context sample_id sets must match exactly"
        )

    evidence = _object(manifest.get("evidence_references"), "evidence_references")
    if set(evidence) != _REQUIRED_EVIDENCE_REFERENCES:
        raise HandoffBundleValidationError(
            "evidence_references must contain source_manifest, analysis_manifest, and comparability_matrix"
        )
    evidence_summary: dict[str, dict[str, Any]] = {}
    for label in sorted(_REQUIRED_EVIDENCE_REFERENCES):
        record = _file_record(evidence.get(label), f"evidence_references.{label}")
        _verify_file_record(root, record, f"evidence_references.{label}")
        evidence_summary[label] = record

    closeout = _object(manifest.get("scientific_closeout"), "scientific_closeout")
    evidence_level = _nonempty_text(closeout, "evidence_level")
    if evidence_level not in SUPPORTED_EVIDENCE_LEVELS:
        raise HandoffBundleValidationError("unsupported scientific_closeout.evidence_level")

    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "status": VALIDATION_STATUS,
        "bundle_type": BUNDLE_TYPE,
        "case_id": case_id,
        "producer_repository": producer_repository,
        "software_versions": software_versions,
        "analysis_result_schema_versions": result_schema_versions,
        "bundle_manifest_sha256": sha256_file(manifest_path),
        "sample_count": len(feature_sample_ids),
        "measurement_count": int(feature_table["measurement_id"].nunique()),
        "feature_count": len(feature_table),
        "instruments": sorted(set(feature_table["instrument"].astype(str))),
        "quality_flag_counts": dict(
            sorted(Counter(feature_table["quality_flag"].astype(str)).items())
        ),
        "evidence_level": evidence_level,
        "sample_identity_consistent": True,
        "row_order_join_allowed": False,
        "aggregation_performed": False,
        "missing_metadata_inferred": False,
        "scientific_comparability_established": False,
        "engineering_release_ready": False,
        "evidence_references": evidence_summary,
        "scientific_boundary": (
            "Bundle validation establishes file integrity and contract consistency only; "
            "it does not establish identical physical aliquots, cross-modal comparability, "
            "causality, model readiness, or engineering suitability."
        ),
    }
