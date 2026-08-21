"""Core fail-closed characterization handoff bundle validator."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..downstream_use_contract import (
    DownstreamUsePolicyError,
    validate_downstream_use_policy,
)
from ..handoff_evidence_ladder import (
    EvidenceLadderHandoffError,
    validate_scientific_evidence_ladder_bundle_binding,
    validate_scientific_evidence_ladder_record,
)
from ..provenance import sha256_file
from .common import (
    BUNDLE_SCHEMA_VERSION,
    BUNDLE_TYPE,
    EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION,
    FEATURE_FILE_NAME,
    MANIFEST_FILE_NAME,
    SAMPLE_CONTEXT_FILE_NAME,
    SUPPORTED_BUNDLE_SCHEMA_VERSIONS,
    SUPPORTED_EVIDENCE_LEVELS,
    VALIDATION_STATUS,
    _REQUIRED_EVIDENCE_REFERENCES,
    HandoffBundleValidationError,
    _file_record,
    _load_json_object,
    _nonempty_text,
    _object,
    _reject_unknown,
    _safe_direct_file,
    _unique_text_list,
    _verify_file_record,
)
from .evidence_binding import validate_evidence_identity_binding
from .tables import _validate_context_table, _validate_feature_table

EVIDENCE_IDENTITY_BINDING_CONTRACT_VERSION = "1.0"


def _evidence_binding_contract(manifest: dict[str, Any]) -> dict[str, Any] | None:
    raw = manifest.get("evidence_identity_binding_contract")
    if raw is None:
        return None
    contract = _object(raw, "evidence_identity_binding_contract")
    _reject_unknown(
        contract,
        {"schema_version", "required"},
        "evidence_identity_binding_contract",
    )
    if contract.get("schema_version") != EVIDENCE_IDENTITY_BINDING_CONTRACT_VERSION:
        raise HandoffBundleValidationError(
            "unsupported evidence_identity_binding_contract schema_version"
        )
    if contract.get("required") is not True:
        raise HandoffBundleValidationError(
            "evidence_identity_binding_contract.required must be true"
        )
    return {
        "schema_version": EVIDENCE_IDENTITY_BINDING_CONTRACT_VERSION,
        "required": True,
    }


def validate_characterization_handoff_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Validate bundle identity, checksums, schemas, joins, and claim boundaries.

    Schema 1.0 is the legacy closed manifest. Schema 1.1 is reserved for the
    independently replayable scientific-evidence-ladder extension. The explicit
    version boundary prevents older closed-world 1.0 consumers from silently
    accepting an extension they do not understand.
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
            "downstream_use_policy",
            "evidence_identity_binding_contract",
            "scientific_evidence_ladder",
        },
        "bundle manifest",
    )
    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        raise HandoffBundleValidationError(
            f"unsupported bundle schema_version: {schema_version}"
        )
    ladder_present = "scientific_evidence_ladder" in manifest
    if ladder_present and schema_version != EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION:
        raise HandoffBundleValidationError(
            "scientific_evidence_ladder requires bundle schema_version 1.1"
        )
    if not ladder_present and schema_version != BUNDLE_SCHEMA_VERSION:
        raise HandoffBundleValidationError(
            "bundle schema_version 1.1 requires scientific_evidence_ladder"
        )
    if manifest.get("bundle_type") != BUNDLE_TYPE:
        raise HandoffBundleValidationError("bundle_type mismatch")
    case_id = _nonempty_text(manifest, "case_id")
    binding_contract = _evidence_binding_contract(manifest)

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
        raise HandoffBundleValidationError(
            "join_contract must match the fail-closed sample_id contract"
        )

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
    instruments = sorted(set(feature_table["instrument"].astype(str)))

    evidence = _object(manifest.get("evidence_references"), "evidence_references")
    if set(evidence) != _REQUIRED_EVIDENCE_REFERENCES:
        raise HandoffBundleValidationError(
            "evidence_references must contain source_manifest, analysis_manifest, and comparability_matrix"
        )
    evidence_summary: dict[str, dict[str, Any]] = {}
    evidence_paths: dict[str, Path] = {}
    for label in sorted(_REQUIRED_EVIDENCE_REFERENCES):
        record = _file_record(evidence.get(label), f"evidence_references.{label}")
        evidence_paths[label] = _verify_file_record(
            root, record, f"evidence_references.{label}"
        )
        evidence_summary[label] = record

    if binding_contract is None:
        evidence_identity_binding: dict[str, Any] = {
            "contract_present": False,
            "legacy_checksum_only_validation": True,
            "semantic_identity_binding_established": False,
            "scientific_comparability_established": False,
        }
    else:
        evidence_identity_binding = {
            "contract_present": True,
            "contract": binding_contract,
            "legacy_checksum_only_validation": False,
            "semantic_identity_binding_established": True,
            **validate_evidence_identity_binding(
                case_id=case_id,
                feature_table=feature_table,
                source_manifest_path=evidence_paths["source_manifest"],
                analysis_manifest_path=evidence_paths["analysis_manifest"],
                comparability_matrix_path=evidence_paths["comparability_matrix"],
            ),
        }

    closeout = _object(manifest.get("scientific_closeout"), "scientific_closeout")
    evidence_level = _nonempty_text(closeout, "evidence_level")
    if evidence_level not in SUPPORTED_EVIDENCE_LEVELS:
        raise HandoffBundleValidationError(
            "unsupported scientific_closeout.evidence_level"
        )

    policy_present = "downstream_use_policy" in manifest
    downstream_use_policy: dict[str, Any] | None = None
    if policy_present:
        try:
            downstream_use_policy = validate_downstream_use_policy(
                _object(manifest.get("downstream_use_policy"), "downstream_use_policy"),
                scientific_evidence_level=evidence_level,
            )
        except DownstreamUsePolicyError as exc:
            raise HandoffBundleValidationError(
                f"invalid downstream_use_policy: {exc}"
            ) from exc
        independence_group_field = downstream_use_policy["independence_group_field"]
        if (
            independence_group_field is not None
            and independence_group_field not in context_table.columns
        ):
            raise HandoffBundleValidationError(
                "downstream_use_policy independence_group_field is absent from sample_context"
            )

    scientific_evidence_ladder: dict[str, Any] | None = None
    scientific_evidence_ladder_assessment_sha256: str | None = None
    scientific_evidence_ladder_bundle_binding: dict[str, Any] | None = None
    if ladder_present:
        try:
            scientific_evidence_ladder, _, ladder_assessment = (
                validate_scientific_evidence_ladder_record(
                    root,
                    manifest.get("scientific_evidence_ladder"),
                )
            )
            validate_scientific_evidence_ladder_bundle_binding(
                case_id=case_id,
                record=scientific_evidence_ladder,
                evidence_references=evidence_summary,
                instruments=instruments,
            )
        except EvidenceLadderHandoffError as exc:
            raise HandoffBundleValidationError(
                f"invalid scientific_evidence_ladder: {exc}"
            ) from exc
        scientific_evidence_ladder_bundle_binding = {
            "case_id_bound": True,
            "required_source_roles": sorted(_REQUIRED_EVIDENCE_REFERENCES),
            "source_digests_bound": True,
            "subject_modality_bound": True,
            "bundle_instruments": [item.strip().lower() for item in instruments],
        }
        scientific_evidence_ladder_assessment_sha256 = ladder_assessment[
            "assessment_sha256"
        ]

    return {
        "schema_version": schema_version,
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
        "instruments": instruments,
        "quality_flag_counts": dict(
            sorted(Counter(feature_table["quality_flag"].astype(str)).items())
        ),
        "evidence_level": evidence_level,
        "downstream_use_policy_present": policy_present,
        "downstream_use_policy": downstream_use_policy,
        "sample_identity_consistent": True,
        "evidence_identity_binding": evidence_identity_binding,
        "scientific_evidence_ladder_present": ladder_present,
        "scientific_evidence_ladder": scientific_evidence_ladder,
        "scientific_evidence_ladder_assessment_sha256": (
            scientific_evidence_ladder_assessment_sha256
        ),
        "scientific_evidence_ladder_bundle_binding": (
            scientific_evidence_ladder_bundle_binding
        ),
        "row_order_join_allowed": False,
        "aggregation_performed": False,
        "missing_metadata_inferred": False,
        "scientific_comparability_established": False,
        "engineering_release_ready": False,
        "evidence_references": evidence_summary,
        "scientific_boundary": (
            "Bundle validation establishes checksum integrity and sample-key consistency. "
            "The evidence identity binding can additionally establish exact analysis-feature "
            "reproduction and source/comparability identity coverage. The optional schema-1.1 "
            "L0-L8 scientific evidence ladder is independently replayed from its declaration "
            "and cross-bound to the bundle case, evidence files, and represented modality. "
            "It identifies maturity/blockers only. No handoff validation mode establishes "
            "identical physical aliquots, cross-modal scientific comparability, causality, "
            "downstream-use authorization, model readiness, or engineering suitability."
        ),
    }
