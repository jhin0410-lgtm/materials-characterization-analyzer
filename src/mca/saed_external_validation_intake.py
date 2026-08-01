"""Fail-closed intake for proposed external SAED validation datasets.

The intake verifies declared provenance, local file identity, calibration metadata,
and protocol-freeze state. It does not decode diffraction patterns, tune analyzer
parameters, perform indexing, or turn an intake pass into a crystallographic or
engineering claim.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from . import __version__

CASE_ID = "saed_external_validation_intake"
SCHEMA_VERSION = "1.0"

BLOCKED = "blocked_source_or_calibration_readiness"
PROTOCOL_READY = "ready_to_freeze_saed_analysis_protocol"
EVALUATION_READY = "ready_for_predeclared_saed_external_evaluation"

_SOURCE_TYPES = {"external_public", "new_acquisition", "private_acquisition"}
_IDENTITY_PROVENANCE = {
    "source_assigned",
    "operator_assigned_at_acquisition",
    "inferred",
}
_REPRESENTATIONS = {"raw_detector", "lossless_export", "rendered_figure"}
_CALIBRATION_METHODS = {
    "reciprocal_nm_inv_per_pixel",
    "camera_constant_nm_pixel",
    "reference_pair",
}
_REVIEW_STATUSES = {"not_run", "passed", "failed"}
_REFERENCE_TYPES = {"none", "source_author_assignments", "curated_structures"}


class SAEDIntakeContractError(ValueError):
    """Raised when a SAED intake manifest or local-file contract fails closed."""


@dataclass(frozen=True)
class DatasetContract:
    dataset_id: str
    dataset_version: str
    source_type: str
    license: str
    reuse_authorized: bool
    identity_provenance: str
    material_identity_source: str
    target_analyzer_development_nonuse_attested: bool
    creator_overlap_with_analyzer_development_source: bool
    cross_dataset_lineage_independence_attested: bool
    minimum_independent_samples: int
    minimum_independent_acquisitions: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "DatasetContract":
        allowed = {
            "dataset_id",
            "dataset_version",
            "source_type",
            "license",
            "reuse_authorized",
            "identity_provenance",
            "material_identity_source",
            "target_analyzer_development_nonuse_attested",
            "creator_overlap_with_analyzer_development_source",
            "cross_dataset_lineage_independence_attested",
            "minimum_independent_samples",
            "minimum_independent_acquisitions",
        }
        _reject_unknown(payload, allowed, "dataset")
        contract = cls(
            dataset_id=_identifier(payload, "dataset_id"),
            dataset_version=_text(payload, "dataset_version"),
            source_type=_text(payload, "source_type"),
            license=_text(payload, "license"),
            reuse_authorized=_boolean(payload, "reuse_authorized"),
            identity_provenance=_text(payload, "identity_provenance"),
            material_identity_source=_text(payload, "material_identity_source"),
            target_analyzer_development_nonuse_attested=_boolean(
                payload, "target_analyzer_development_nonuse_attested"
            ),
            creator_overlap_with_analyzer_development_source=_boolean(
                payload, "creator_overlap_with_analyzer_development_source"
            ),
            cross_dataset_lineage_independence_attested=_boolean(
                payload, "cross_dataset_lineage_independence_attested"
            ),
            minimum_independent_samples=_integer(
                payload, "minimum_independent_samples"
            ),
            minimum_independent_acquisitions=_integer(
                payload, "minimum_independent_acquisitions"
            ),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if self.source_type not in _SOURCE_TYPES:
            raise SAEDIntakeContractError(
                f"unsupported dataset.source_type: {self.source_type}"
            )
        if self.identity_provenance not in _IDENTITY_PROVENANCE:
            raise SAEDIntakeContractError(
                "dataset.identity_provenance must be source-assigned, "
                "operator-assigned at acquisition, or explicitly inferred"
            )
        if self.minimum_independent_samples < 2:
            raise SAEDIntakeContractError(
                "dataset.minimum_independent_samples must be at least 2"
            )
        if self.minimum_independent_acquisitions < 2:
            raise SAEDIntakeContractError(
                "dataset.minimum_independent_acquisitions must be at least 2"
            )


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    relative_path: str
    sha256: str
    sample_id: str
    acquisition_id: str
    material_id: str
    representation: str
    original_detector_intensity_available: bool
    file_format: str
    accelerating_voltage_kv: float
    camera_length_mm: float | None
    detector_model: str
    detector_pixel_size_um: float | None
    center_x_px: float
    center_y_px: float
    center_source: str
    calibration_method: str
    reciprocal_nm_inv_per_pixel: float | None
    camera_constant_nm_pixel: float | None
    reference_d_nm: float | None
    reference_radius_px: float | None
    calibration_source: str
    preprocessing_operations: tuple[str, ...]
    used_for_center_selection: bool
    used_for_smoothing_selection: bool
    used_for_prominence_selection: bool
    used_for_radius_bound_selection: bool
    used_for_candidate_count_selection: bool
    excluded: bool
    exclusion_reason: str | None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], index: int) -> "PatternRecord":
        allowed = {
            "pattern_id",
            "relative_path",
            "sha256",
            "sample_id",
            "acquisition_id",
            "material_id",
            "representation",
            "original_detector_intensity_available",
            "file_format",
            "accelerating_voltage_kv",
            "camera_length_mm",
            "detector_model",
            "detector_pixel_size_um",
            "center_x_px",
            "center_y_px",
            "center_source",
            "calibration_method",
            "reciprocal_nm_inv_per_pixel",
            "camera_constant_nm_pixel",
            "reference_d_nm",
            "reference_radius_px",
            "calibration_source",
            "preprocessing_operations",
            "used_for_center_selection",
            "used_for_smoothing_selection",
            "used_for_prominence_selection",
            "used_for_radius_bound_selection",
            "used_for_candidate_count_selection",
            "excluded",
            "exclusion_reason",
        }
        context = f"patterns[{index}]"
        _reject_unknown(payload, allowed, context)
        record = cls(
            pattern_id=_identifier(payload, "pattern_id"),
            relative_path=_relative_path(payload, "relative_path"),
            sha256=_sha256(payload, "sha256"),
            sample_id=_identifier(payload, "sample_id"),
            acquisition_id=_identifier(payload, "acquisition_id"),
            material_id=_identifier(payload, "material_id"),
            representation=_text(payload, "representation"),
            original_detector_intensity_available=_boolean(
                payload, "original_detector_intensity_available"
            ),
            file_format=_text(payload, "file_format"),
            accelerating_voltage_kv=_positive_float(
                payload, "accelerating_voltage_kv"
            ),
            camera_length_mm=_optional_positive_float(
                payload.get("camera_length_mm"), "camera_length_mm"
            ),
            detector_model=_text(payload, "detector_model"),
            detector_pixel_size_um=_optional_positive_float(
                payload.get("detector_pixel_size_um"), "detector_pixel_size_um"
            ),
            center_x_px=_nonnegative_float(payload, "center_x_px"),
            center_y_px=_nonnegative_float(payload, "center_y_px"),
            center_source=_text(payload, "center_source"),
            calibration_method=_text(payload, "calibration_method"),
            reciprocal_nm_inv_per_pixel=_optional_positive_float(
                payload.get("reciprocal_nm_inv_per_pixel"),
                "reciprocal_nm_inv_per_pixel",
            ),
            camera_constant_nm_pixel=_optional_positive_float(
                payload.get("camera_constant_nm_pixel"),
                "camera_constant_nm_pixel",
            ),
            reference_d_nm=_optional_positive_float(
                payload.get("reference_d_nm"), "reference_d_nm"
            ),
            reference_radius_px=_optional_positive_float(
                payload.get("reference_radius_px"), "reference_radius_px"
            ),
            calibration_source=_text(payload, "calibration_source"),
            preprocessing_operations=_string_tuple(
                payload, "preprocessing_operations"
            ),
            used_for_center_selection=_boolean(
                payload, "used_for_center_selection"
            ),
            used_for_smoothing_selection=_boolean(
                payload, "used_for_smoothing_selection"
            ),
            used_for_prominence_selection=_boolean(
                payload, "used_for_prominence_selection"
            ),
            used_for_radius_bound_selection=_boolean(
                payload, "used_for_radius_bound_selection"
            ),
            used_for_candidate_count_selection=_boolean(
                payload, "used_for_candidate_count_selection"
            ),
            excluded=_boolean(payload, "excluded"),
            exclusion_reason=_optional_text(
                payload.get("exclusion_reason"), "exclusion_reason"
            ),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if self.representation not in _REPRESENTATIONS:
            raise SAEDIntakeContractError(
                f"unsupported representation for {self.pattern_id}: "
                f"{self.representation}"
            )
        if self.calibration_method not in _CALIBRATION_METHODS:
            raise SAEDIntakeContractError(
                f"unsupported calibration_method for {self.pattern_id}: "
                f"{self.calibration_method}"
            )
        supplied = {
            "reciprocal_nm_inv_per_pixel": self.reciprocal_nm_inv_per_pixel,
            "camera_constant_nm_pixel": self.camera_constant_nm_pixel,
            "reference_d_nm": self.reference_d_nm,
            "reference_radius_px": self.reference_radius_px,
        }
        if self.calibration_method == "reciprocal_nm_inv_per_pixel":
            required = {"reciprocal_nm_inv_per_pixel"}
        elif self.calibration_method == "camera_constant_nm_pixel":
            required = {"camera_constant_nm_pixel"}
        else:
            required = {"reference_d_nm", "reference_radius_px"}
        for name, value in supplied.items():
            if (name in required) != (value is not None):
                raise SAEDIntakeContractError(
                    f"{self.pattern_id} calibration_method "
                    f"{self.calibration_method} has inconsistent {name}"
                )
        if len(set(self.preprocessing_operations)) != len(
            self.preprocessing_operations
        ):
            raise SAEDIntakeContractError(
                f"{self.pattern_id} preprocessing_operations contains duplicates"
            )
        normalized_operations = {item.lower() for item in self.preprocessing_operations}
        if "none" in normalized_operations and len(normalized_operations) != 1:
            raise SAEDIntakeContractError(
                f"{self.pattern_id} cannot combine preprocessing operation 'none' "
                "with other operations"
            )
        if self.excluded and self.exclusion_reason is None:
            raise SAEDIntakeContractError(
                f"excluded pattern {self.pattern_id} requires exclusion_reason"
            )
        if not self.excluded and self.exclusion_reason is not None:
            raise SAEDIntakeContractError(
                f"active pattern {self.pattern_id} cannot have exclusion_reason"
            )

    @property
    def used_for_parameter_selection(self) -> bool:
        return any(
            (
                self.used_for_center_selection,
                self.used_for_smoothing_selection,
                self.used_for_prominence_selection,
                self.used_for_radius_bound_selection,
                self.used_for_candidate_count_selection,
            )
        )


@dataclass(frozen=True)
class EvaluationProtocol:
    source_metadata_review_status: str
    file_content_audit_status: str
    calibration_review_status: str
    acquisition_independence_review_status: str
    content_overlap_audit_status: str
    analysis_parameters_frozen: bool
    indexing_protocol_frozen: bool
    reference_set_frozen: bool
    manifest_checksum_frozen: bool
    frozen_manifest_sha256: str | None
    frozen_protocol_id: str | None
    reference_type: str
    reference_identifier: str | None
    metrics_frozen: bool
    uncertainty_method_frozen: bool
    exclusion_rules_frozen: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "EvaluationProtocol":
        allowed = {
            "source_metadata_review_status",
            "file_content_audit_status",
            "calibration_review_status",
            "acquisition_independence_review_status",
            "content_overlap_audit_status",
            "analysis_parameters_frozen",
            "indexing_protocol_frozen",
            "reference_set_frozen",
            "manifest_checksum_frozen",
            "frozen_manifest_sha256",
            "frozen_protocol_id",
            "reference_type",
            "reference_identifier",
            "metrics_frozen",
            "uncertainty_method_frozen",
            "exclusion_rules_frozen",
        }
        _reject_unknown(payload, allowed, "evaluation_protocol")
        protocol = cls(
            source_metadata_review_status=_text(
                payload, "source_metadata_review_status"
            ),
            file_content_audit_status=_text(payload, "file_content_audit_status"),
            calibration_review_status=_text(payload, "calibration_review_status"),
            acquisition_independence_review_status=_text(
                payload, "acquisition_independence_review_status"
            ),
            content_overlap_audit_status=_text(
                payload, "content_overlap_audit_status"
            ),
            analysis_parameters_frozen=_boolean(
                payload, "analysis_parameters_frozen"
            ),
            indexing_protocol_frozen=_boolean(
                payload, "indexing_protocol_frozen"
            ),
            reference_set_frozen=_boolean(payload, "reference_set_frozen"),
            manifest_checksum_frozen=_boolean(
                payload, "manifest_checksum_frozen"
            ),
            frozen_manifest_sha256=_optional_sha256(
                payload.get("frozen_manifest_sha256"),
                "frozen_manifest_sha256",
            ),
            frozen_protocol_id=_optional_text(
                payload.get("frozen_protocol_id"), "frozen_protocol_id"
            ),
            reference_type=_text(payload, "reference_type"),
            reference_identifier=_optional_text(
                payload.get("reference_identifier"), "reference_identifier"
            ),
            metrics_frozen=_boolean(payload, "metrics_frozen"),
            uncertainty_method_frozen=_boolean(
                payload, "uncertainty_method_frozen"
            ),
            exclusion_rules_frozen=_boolean(payload, "exclusion_rules_frozen"),
        )
        protocol.validate()
        return protocol

    def validate(self) -> None:
        statuses = (
            self.source_metadata_review_status,
            self.file_content_audit_status,
            self.calibration_review_status,
            self.acquisition_independence_review_status,
            self.content_overlap_audit_status,
        )
        invalid = [status for status in statuses if status not in _REVIEW_STATUSES]
        if invalid:
            raise SAEDIntakeContractError(
                f"unsupported evaluation review status: {invalid[0]}"
            )
        if self.reference_type not in _REFERENCE_TYPES:
            raise SAEDIntakeContractError(
                f"unsupported evaluation_protocol.reference_type: "
                f"{self.reference_type}"
            )
        if self.reference_type == "none" and self.reference_identifier is not None:
            raise SAEDIntakeContractError(
                "reference_identifier must be null when reference_type is none"
            )
        if self.reference_type != "none" and self.reference_identifier is None:
            raise SAEDIntakeContractError(
                "reference_identifier is required for a non-none reference_type"
            )
        if self.manifest_checksum_frozen != (
            self.frozen_manifest_sha256 is not None
        ):
            raise SAEDIntakeContractError(
                "manifest_checksum_frozen and frozen_manifest_sha256 must agree"
            )

    @property
    def review_statuses(self) -> tuple[str, ...]:
        return (
            self.source_metadata_review_status,
            self.file_content_audit_status,
            self.calibration_review_status,
            self.acquisition_independence_review_status,
            self.content_overlap_audit_status,
        )


@dataclass(frozen=True)
class IntakeManifest:
    schema_version: str
    case_id: str
    dataset: DatasetContract
    patterns: tuple[PatternRecord, ...]
    evaluation_protocol: EvaluationProtocol
    raw_payload: Mapping[str, Any]
    canonical_sha256: str


def load_intake_manifest(path: str | Path) -> IntakeManifest:
    manifest_path = Path(path)
    try:
        payload = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SAEDIntakeContractError(
            f"could not read SAED intake manifest: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise SAEDIntakeContractError("SAED intake manifest root must be an object")
    return _manifest_from_mapping(payload)


def compute_intake_manifest_sha256(payload: Mapping[str, Any]) -> str:
    canonical = json.loads(json.dumps(payload))
    protocol = canonical.get("evaluation_protocol")
    if isinstance(protocol, dict):
        protocol["frozen_manifest_sha256"] = None
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_saed_external_validation_intake(
    manifest: IntakeManifest,
    data_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    root = Path(data_root)
    output = Path(output_dir)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise SAEDIntakeContractError(
            "data_root must be an existing non-symlink directory"
        )
    if output.exists():
        if not output.is_dir() or output.is_symlink():
            raise SAEDIntakeContractError(
                "output_dir must be a directory when it exists"
            )
        if any(output.iterdir()):
            raise SAEDIntakeContractError(
                "output_dir must be absent or empty; overwrite is not allowed"
            )
    created_output = not output.exists()
    output.mkdir(parents=True, exist_ok=True)
    try:
        if (
            manifest.evaluation_protocol.manifest_checksum_frozen
            and manifest.evaluation_protocol.frozen_manifest_sha256
            != manifest.canonical_sha256
        ):
            raise SAEDIntakeContractError(
                "frozen_manifest_sha256 does not match the canonical intake manifest"
            )

        verified_rows = [
            _verify_pattern_file(pattern, root) for pattern in manifest.patterns
        ]
        active_patterns = [
            pattern for pattern in manifest.patterns if not pattern.excluded
        ]
        active_hash_counts = Counter(pattern.sha256 for pattern in active_patterns)
        duplicate_active_hashes = {
            digest for digest, count in active_hash_counts.items() if count > 1
        }
        sample_count = len({pattern.sample_id for pattern in active_patterns})
        acquisition_count = len(
            {pattern.acquisition_id for pattern in active_patterns}
        )

        gates: dict[str, bool] = {
            "stable_dataset_identity": bool(
                manifest.dataset.dataset_id and manifest.dataset.dataset_version
            ),
            "reuse_authorized": manifest.dataset.reuse_authorized,
            "source_assigned_dataset_identity": (
                manifest.dataset.identity_provenance != "inferred"
            ),
            "material_identity_supported": bool(
                manifest.dataset.material_identity_source
            )
            and all(pattern.material_id for pattern in active_patterns),
            "target_analyzer_development_nonuse_attested": (
                manifest.dataset.target_analyzer_development_nonuse_attested
            ),
            "independent_lineage_supported": (
                not manifest.dataset.creator_overlap_with_analyzer_development_source
                or manifest.dataset.cross_dataset_lineage_independence_attested
            ),
            "minimum_independent_samples": (
                sample_count >= manifest.dataset.minimum_independent_samples
            ),
            "minimum_independent_acquisitions": (
                acquisition_count
                >= manifest.dataset.minimum_independent_acquisitions
            ),
            "raw_or_lossless_representation": bool(active_patterns)
            and all(
                pattern.representation in {"raw_detector", "lossless_export"}
                for pattern in active_patterns
            ),
            "original_detector_intensity_available": bool(active_patterns)
            and all(
                pattern.original_detector_intensity_available
                for pattern in active_patterns
            ),
            "no_exact_duplicate_active_pattern_content": (
                not duplicate_active_hashes
            ),
            "accelerating_voltage_and_detector_metadata": bool(active_patterns)
            and all(
                pattern.accelerating_voltage_kv > 0 and pattern.detector_model
                for pattern in active_patterns
            ),
            "traceable_pattern_center": bool(active_patterns)
            and all(
                pattern.center_x_px >= 0
                and pattern.center_y_px >= 0
                and pattern.center_source
                for pattern in active_patterns
            ),
            "traceable_reciprocal_calibration": bool(active_patterns)
            and all(pattern.calibration_source for pattern in active_patterns),
            "preprocessing_state_documented": bool(active_patterns)
            and all(pattern.preprocessing_operations for pattern in active_patterns),
            "not_used_for_analyzer_parameter_selection": bool(active_patterns)
            and not any(
                pattern.used_for_parameter_selection
                for pattern in active_patterns
            ),
            "all_declared_files_verified": len(verified_rows)
            == len(manifest.patterns),
        }
        failed_reviews = [
            status
            for status in manifest.evaluation_protocol.review_statuses
            if status == "failed"
        ]
        base_ready = all(gates.values()) and not failed_reviews
        protocol_complete = (
            base_ready
            and all(
                status == "passed"
                for status in manifest.evaluation_protocol.review_statuses
            )
            and manifest.evaluation_protocol.analysis_parameters_frozen
            and manifest.evaluation_protocol.indexing_protocol_frozen
            and manifest.evaluation_protocol.reference_set_frozen
            and manifest.evaluation_protocol.manifest_checksum_frozen
            and manifest.evaluation_protocol.frozen_manifest_sha256
            == manifest.canonical_sha256
            and manifest.evaluation_protocol.frozen_protocol_id is not None
            and manifest.evaluation_protocol.reference_type != "none"
            and manifest.evaluation_protocol.reference_identifier is not None
            and manifest.evaluation_protocol.metrics_frozen
            and manifest.evaluation_protocol.uncertainty_method_frozen
            and manifest.evaluation_protocol.exclusion_rules_frozen
        )
        unresolved = [name for name, passed in gates.items() if not passed]
        if failed_reviews:
            unresolved.append("failed_protocol_or_evidence_review")
        if not base_ready:
            status = BLOCKED
            next_action = (
                "Resolve the failed source, identity, calibration, independence, "
                "or file-integrity gates before analyzer execution. Do not infer "
                "metadata or tune detection parameters against these patterns."
            )
        elif protocol_complete:
            status = EVALUATION_READY
            next_action = (
                "Run the frozen SAED analysis and indexing protocol once, retain "
                "all unmatched candidates and sensitivity results, and keep "
                "crystallographic and engineering claims review-required."
            )
        else:
            status = PROTOCOL_READY
            next_action = (
                "Freeze center, calibration, smoothing, prominence, radius bounds, "
                "candidate matching, references, metrics, uncertainty, exclusions, "
                "and the canonical manifest before analyzer execution."
            )

        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "source_manifest": {
                "dataset_id": manifest.dataset.dataset_id,
                "dataset_version": manifest.dataset.dataset_version,
                "canonical_sha256": manifest.canonical_sha256,
            },
            "result_counts": {
                "declared_pattern_count": len(manifest.patterns),
                "active_pattern_count": len(active_patterns),
                "excluded_pattern_count": len(manifest.patterns)
                - len(active_patterns),
                "sample_count": sample_count,
                "acquisition_count": acquisition_count,
                "duplicate_active_pattern_content_count": len(
                    duplicate_active_hashes
                ),
                "failed_review_count": len(failed_reviews),
            },
            "evidence_gates": {
                **gates,
                "unresolved_evidence": unresolved,
            },
            "decision": {
                "status": status,
                "saed_protocol_freeze_ready": base_ready,
                "predeclared_saed_external_evaluation_ready": protocol_complete,
                "crystallographic_performance_claim_ready": False,
                "engineering_release_ready": False,
                "next_action": next_action,
            },
            "processing": {
                "source_patterns_modified": False,
                "source_arrays_exported": False,
                "pattern_decoding_performed": False,
                "analyzer_execution_performed": False,
                "parameter_tuning_performed": False,
                "phase_or_reflection_assignment_performed": False,
            },
            "scientific_closeout": {
                "status": (
                    "Diagnostic" if base_ready else "Inconclusive"
                ),
                "result": status,
                "strongest_evidence": (
                    "Checksum-bound local files and declared source, sample, "
                    "acquisition, center, calibration, and preprocessing metadata "
                    "were validated without modifying or decoding the patterns."
                ),
                "primary_limitation": (
                    "Intake validation does not independently establish material "
                    "identity, calibration truth, acquisition independence, "
                    "reflection assignments, indexing accuracy, or generalization."
                ),
                "suitable_for": [
                    "source and provenance intake",
                    "predeclared protocol preparation",
                ],
                "not_suitable_for": [
                    "parameter tuning",
                    "automatic phase identification",
                    "crystallographic performance claims",
                    "engineering release",
                ],
            },
        }

        patterns_path = output / "saed_validation_intake_patterns.csv"
        summary_path = output / "saed_validation_intake_summary.json"
        report_path = output / "saed_validation_intake_report.md"
        artifact_manifest_path = (
            output / "saed_validation_intake_artifact_manifest.json"
        )
        _write_csv(patterns_path, verified_rows)
        _write_json(summary_path, summary)
        report_path.write_text(_render_report(summary), encoding="utf-8")
        _write_json(
            artifact_manifest_path,
            _artifact_manifest(output, [patterns_path, summary_path, report_path]),
        )
        return summary
    except Exception:
        _cleanup_failed_output(output, created_output)
        raise


def _manifest_from_mapping(payload: Mapping[str, Any]) -> IntakeManifest:
    allowed = {
        "schema_version",
        "case_id",
        "dataset",
        "patterns",
        "evaluation_protocol",
    }
    _reject_unknown(payload, allowed, "manifest")
    schema_version = _text(payload, "schema_version")
    case_id = _text(payload, "case_id")
    if schema_version != SCHEMA_VERSION:
        raise SAEDIntakeContractError(
            f"unsupported schema_version: {schema_version}"
        )
    if case_id != CASE_ID:
        raise SAEDIntakeContractError(f"unsupported case_id: {case_id}")
    dataset_payload = _mapping(payload, "dataset")
    pattern_payloads = _sequence_of_mappings(payload, "patterns")
    protocol_payload = _mapping(payload, "evaluation_protocol")
    patterns = tuple(
        PatternRecord.from_mapping(item, index)
        for index, item in enumerate(pattern_payloads)
    )
    if not patterns:
        raise SAEDIntakeContractError("patterns must contain at least one record")
    _require_unique([pattern.pattern_id for pattern in patterns], "pattern_id")
    _require_unique(
        [pattern.relative_path for pattern in patterns], "pattern relative_path"
    )
    return IntakeManifest(
        schema_version=schema_version,
        case_id=case_id,
        dataset=DatasetContract.from_mapping(dataset_payload),
        patterns=patterns,
        evaluation_protocol=EvaluationProtocol.from_mapping(protocol_payload),
        raw_payload=payload,
        canonical_sha256=compute_intake_manifest_sha256(payload),
    )


def _verify_pattern_file(
    pattern: PatternRecord, data_root: Path
) -> dict[str, Any]:
    path = _resolve_relative_file(data_root, pattern.relative_path)
    digest = _hash_file(path)
    if digest != pattern.sha256:
        raise SAEDIntakeContractError(
            f"SHA-256 mismatch for pattern {pattern.pattern_id}"
        )
    return {
        "pattern_id": pattern.pattern_id,
        "relative_path": pattern.relative_path,
        "declared_sha256": pattern.sha256,
        "verified_sha256": digest,
        "bytes": path.stat().st_size,
        "sample_id": pattern.sample_id,
        "acquisition_id": pattern.acquisition_id,
        "material_id": pattern.material_id,
        "representation": pattern.representation,
        "original_detector_intensity_available": (
            pattern.original_detector_intensity_available
        ),
        "file_format": pattern.file_format,
        "accelerating_voltage_kv": pattern.accelerating_voltage_kv,
        "camera_length_mm": pattern.camera_length_mm,
        "detector_model": pattern.detector_model,
        "detector_pixel_size_um": pattern.detector_pixel_size_um,
        "center_x_px": pattern.center_x_px,
        "center_y_px": pattern.center_y_px,
        "center_source": pattern.center_source,
        "calibration_method": pattern.calibration_method,
        "calibration_source": pattern.calibration_source,
        "preprocessing_operations": "|".join(pattern.preprocessing_operations),
        "used_for_parameter_selection": pattern.used_for_parameter_selection,
        "excluded": pattern.excluded,
        "exclusion_reason": pattern.exclusion_reason,
    }


def _resolve_relative_file(root: Path, relative_path: str) -> Path:
    if root.is_symlink():
        raise SAEDIntakeContractError("data_root cannot be a symlink")
    pure = PurePosixPath(relative_path)
    candidate = root
    for part in pure.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise SAEDIntakeContractError(
                f"symlink paths are not allowed: {relative_path}"
            )
    if not candidate.exists() or not candidate.is_file():
        raise SAEDIntakeContractError(
            f"declared pattern file does not exist: {relative_path}"
        )
    root_resolved = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise SAEDIntakeContractError(
            f"pattern path escapes data_root: {relative_path}"
        )
    return resolved


def _artifact_manifest(output: Path, paths: Sequence[Path]) -> dict[str, Any]:
    records = []
    for path in paths:
        records.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
            }
        )
    return {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _render_report(summary: Mapping[str, Any]) -> str:
    decision = summary["decision"]
    counts = summary["result_counts"]
    unresolved = summary["evidence_gates"]["unresolved_evidence"]
    unresolved_text = ", ".join(unresolved) if unresolved else "none"
    return (
        "# SAED external-validation intake\n\n"
        f"- Status: `{decision['status']}`\n"
        f"- Active patterns: `{counts['active_pattern_count']}`\n"
        f"- Independent samples: `{counts['sample_count']}`\n"
        f"- Independent acquisitions: `{counts['acquisition_count']}`\n"
        f"- Duplicate active content: "
        f"`{counts['duplicate_active_pattern_content_count']}`\n"
        f"- Unresolved evidence: `{unresolved_text}`\n"
        f"- Protocol freeze ready: "
        f"`{str(decision['saed_protocol_freeze_ready']).lower()}`\n"
        f"- Predeclared external evaluation ready: "
        f"`{str(decision['predeclared_saed_external_evaluation_ready']).lower()}`\n\n"
        "## Next action\n\n"
        f"{decision['next_action']}\n\n"
        "## Scientific boundary\n\n"
        "This intake verifies declared metadata and local file identity only. "
        "It does not decode patterns, run the analyzer, tune parameters, assign "
        "phases or reflections, validate indexing accuracy, or authorize an "
        "engineering release.\n"
    )


def _cleanup_failed_output(output: Path, created_output: bool) -> None:
    if not output.exists() or not output.is_dir() or output.is_symlink():
        return
    if created_output:
        shutil.rmtree(output, ignore_errors=True)
        return
    for child in output.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["pattern_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SAEDIntakeContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SAEDIntakeContractError(
            f"{context} contains unknown field: {unknown[0]}"
        )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SAEDIntakeContractError(f"{key} must be an object")
    return value


def _sequence_of_mappings(
    payload: Mapping[str, Any], key: str
) -> list[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise SAEDIntakeContractError(f"{key} must be an array")
    if any(not isinstance(item, dict) for item in value):
        raise SAEDIntakeContractError(f"{key} entries must be objects")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SAEDIntakeContractError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SAEDIntakeContractError(f"{key} must be null or a non-empty string")
    return value.strip()


def _identifier(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
        raise SAEDIntakeContractError(
            f"{key} contains unsupported identifier characters"
        )
    return value


def _relative_path(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if "\\" in value:
        raise SAEDIntakeContractError(
            f"{key} must use POSIX separators and remain relative"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise SAEDIntakeContractError(
            f"{key} must be a safe relative POSIX path"
        )
    return pure.as_posix()


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    return _validate_sha256(payload.get(key), key)


def _optional_sha256(value: Any, key: str) -> str | None:
    if value is None:
        return None
    return _validate_sha256(value, key)


def _validate_sha256(value: Any, key: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", value
    ):
        raise SAEDIntakeContractError(f"{key} must be a 64-character SHA-256")
    return value.lower()


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise SAEDIntakeContractError(f"{key} must be boolean")
    return value


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SAEDIntakeContractError(f"{key} must be an integer")
    return value


def _positive_float(payload: Mapping[str, Any], key: str) -> float:
    return _validate_float(payload.get(key), key, positive=True)


def _nonnegative_float(payload: Mapping[str, Any], key: str) -> float:
    return _validate_float(payload.get(key), key, positive=False)


def _optional_positive_float(value: Any, key: str) -> float | None:
    if value is None:
        return None
    return _validate_float(value, key, positive=True)


def _validate_float(value: Any, key: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SAEDIntakeContractError(f"{key} must be numeric")
    number = float(value)
    if not (number == number and abs(number) != float("inf")):
        raise SAEDIntakeContractError(f"{key} must be finite")
    if positive and number <= 0:
        raise SAEDIntakeContractError(f"{key} must be positive")
    if not positive and number < 0:
        raise SAEDIntakeContractError(f"{key} must be nonnegative")
    return number


def _string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise SAEDIntakeContractError(
            f"{key} must be a non-empty array of strings"
        )
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SAEDIntakeContractError(
                f"{key} must contain non-empty strings"
            )
        cleaned.append(item.strip())
    return tuple(cleaned)


def _require_unique(values: Sequence[str], field: str) -> None:
    duplicates = sorted(
        value for value, count in Counter(values).items() if count > 1
    )
    if duplicates:
        raise SAEDIntakeContractError(
            f"duplicate {field}: {duplicates[0]}"
        )
