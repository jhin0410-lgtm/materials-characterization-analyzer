"""Validate a proposed independent TEM segmentation-validation dataset.

The intake verifies local file identity and a strict metadata contract. It does
not infer missing provenance, inspect microscopy semantics, train a model, run
inference, or turn an intake pass into a performance claim.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from . import __version__

CASE_ID = "tem_external_validation_intake"
SCHEMA_VERSION = "1.0"

BLOCKED = "blocked_dataset_or_image_readiness"
ANNOTATION_READY = "ready_for_blinded_annotation_pilot"
ANNOTATION_INCOMPLETE = "independent_annotation_incomplete"
PROTOCOL_FREEZE_REQUIRED = "ready_to_freeze_evaluation_protocol"
EVALUATION_READY = "ready_for_predeclared_external_evaluation"

_SOURCE_TYPES = {"external_public", "new_acquisition", "private_acquisition"}
_IDENTITY_PROVENANCE = {
    "source_assigned",
    "operator_assigned_at_acquisition",
    "inferred",
}
_MODALITIES = {"TEM", "HRTEM"}
_REPRESENTATIONS = {"raw_detector", "lossless_export", "rendered_figure"}
_ANNOTATION_ROLES = {"independent", "adjudicated_consensus"}
_AUDIT_STATUSES = {"not_run", "passed", "failed"}


class IntakeContractError(ValueError):
    """Raised when the manifest or local file contract fails closed."""


@dataclass(frozen=True)
class DatasetContract:
    dataset_id: str
    dataset_version: str
    source_type: str
    material_domain: str
    license: str
    reuse_authorized: bool
    identity_provenance: str
    target_training_nonuse_attested: bool
    target_creator_overlap: bool
    cross_dataset_lineage_independence_attested: bool
    minimum_independent_blinded_labelers: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "DatasetContract":
        allowed = {
            "dataset_id",
            "dataset_version",
            "source_type",
            "material_domain",
            "license",
            "reuse_authorized",
            "identity_provenance",
            "target_training_nonuse_attested",
            "target_creator_overlap",
            "cross_dataset_lineage_independence_attested",
            "minimum_independent_blinded_labelers",
        }
        _reject_unknown(payload, allowed, "dataset")
        contract = cls(
            dataset_id=_text(payload, "dataset_id"),
            dataset_version=_text(payload, "dataset_version"),
            source_type=_text(payload, "source_type"),
            material_domain=_text(payload, "material_domain"),
            license=_text(payload, "license"),
            reuse_authorized=_boolean(payload, "reuse_authorized"),
            identity_provenance=_text(payload, "identity_provenance"),
            target_training_nonuse_attested=_boolean(
                payload, "target_training_nonuse_attested"
            ),
            target_creator_overlap=_boolean(payload, "target_creator_overlap"),
            cross_dataset_lineage_independence_attested=_boolean(
                payload, "cross_dataset_lineage_independence_attested"
            ),
            minimum_independent_blinded_labelers=_integer(
                payload, "minimum_independent_blinded_labelers"
            ),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", self.dataset_id):
            raise IntakeContractError("dataset_id contains unsupported characters")
        if self.source_type not in _SOURCE_TYPES:
            raise IntakeContractError(f"unsupported source_type: {self.source_type}")
        if self.identity_provenance not in _IDENTITY_PROVENANCE:
            raise IntakeContractError(
                f"unsupported identity_provenance: {self.identity_provenance}"
            )
        if self.minimum_independent_blinded_labelers < 2:
            raise IntakeContractError(
                "minimum_independent_blinded_labelers must be at least 2"
            )


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    relative_path: str
    sha256: str
    sample_id: str
    acquisition_id: str
    modality: str
    representation: str
    original_detector_intensity_available: bool
    nm_per_pixel: float | None
    calibration_source: str | None
    used_for_training: bool
    used_for_threshold_selection: bool
    used_for_hyperparameter_tuning: bool
    used_for_model_selection: bool
    excluded: bool
    exclusion_reason: str | None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], index: int) -> "ImageRecord":
        allowed = {
            "image_id",
            "relative_path",
            "sha256",
            "sample_id",
            "acquisition_id",
            "modality",
            "representation",
            "original_detector_intensity_available",
            "nm_per_pixel",
            "calibration_source",
            "used_for_training",
            "used_for_threshold_selection",
            "used_for_hyperparameter_tuning",
            "used_for_model_selection",
            "excluded",
            "exclusion_reason",
        }
        _reject_unknown(payload, allowed, f"images[{index}]")
        record = cls(
            image_id=_identifier(payload, "image_id"),
            relative_path=_relative_path(payload, "relative_path"),
            sha256=_sha256(payload, "sha256"),
            sample_id=_identifier(payload, "sample_id"),
            acquisition_id=_identifier(payload, "acquisition_id"),
            modality=_text(payload, "modality"),
            representation=_text(payload, "representation"),
            original_detector_intensity_available=_boolean(
                payload, "original_detector_intensity_available"
            ),
            nm_per_pixel=_optional_positive_float(payload.get("nm_per_pixel"), "nm_per_pixel"),
            calibration_source=_optional_text(payload.get("calibration_source"), "calibration_source"),
            used_for_training=_boolean(payload, "used_for_training"),
            used_for_threshold_selection=_boolean(
                payload, "used_for_threshold_selection"
            ),
            used_for_hyperparameter_tuning=_boolean(
                payload, "used_for_hyperparameter_tuning"
            ),
            used_for_model_selection=_boolean(payload, "used_for_model_selection"),
            excluded=_boolean(payload, "excluded"),
            exclusion_reason=_optional_text(
                payload.get("exclusion_reason"), "exclusion_reason"
            ),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if self.modality not in _MODALITIES:
            raise IntakeContractError(
                f"unsupported modality for {self.image_id}: {self.modality}"
            )
        if self.representation not in _REPRESENTATIONS:
            raise IntakeContractError(
                f"unsupported representation for {self.image_id}: {self.representation}"
            )
        if (self.nm_per_pixel is None) != (self.calibration_source is None):
            raise IntakeContractError(
                f"{self.image_id} must supply both nm_per_pixel and calibration_source or neither"
            )
        if self.excluded and self.exclusion_reason is None:
            raise IntakeContractError(
                f"excluded image {self.image_id} requires exclusion_reason"
            )
        if not self.excluded and self.exclusion_reason is not None:
            raise IntakeContractError(
                f"active image {self.image_id} cannot have exclusion_reason"
            )

    @property
    def used_for_model_development(self) -> bool:
        return any(
            (
                self.used_for_training,
                self.used_for_threshold_selection,
                self.used_for_hyperparameter_tuning,
                self.used_for_model_selection,
            )
        )


@dataclass(frozen=True)
class AnnotationRecord:
    annotation_id: str
    image_id: str
    relative_path: str
    sha256: str
    labeler_id: str
    annotation_role: str
    blinded_to_model_predictions: bool
    label_definition_version: str
    used_for_training: bool
    used_for_threshold_selection: bool
    used_for_hyperparameter_tuning: bool
    used_for_model_selection: bool

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any], index: int
    ) -> "AnnotationRecord":
        allowed = {
            "annotation_id",
            "image_id",
            "relative_path",
            "sha256",
            "labeler_id",
            "annotation_role",
            "blinded_to_model_predictions",
            "label_definition_version",
            "used_for_training",
            "used_for_threshold_selection",
            "used_for_hyperparameter_tuning",
            "used_for_model_selection",
        }
        _reject_unknown(payload, allowed, f"annotations[{index}]")
        record = cls(
            annotation_id=_identifier(payload, "annotation_id"),
            image_id=_identifier(payload, "image_id"),
            relative_path=_relative_path(payload, "relative_path"),
            sha256=_sha256(payload, "sha256"),
            labeler_id=_identifier(payload, "labeler_id"),
            annotation_role=_text(payload, "annotation_role"),
            blinded_to_model_predictions=_boolean(
                payload, "blinded_to_model_predictions"
            ),
            label_definition_version=_text(payload, "label_definition_version"),
            used_for_training=_boolean(payload, "used_for_training"),
            used_for_threshold_selection=_boolean(
                payload, "used_for_threshold_selection"
            ),
            used_for_hyperparameter_tuning=_boolean(
                payload, "used_for_hyperparameter_tuning"
            ),
            used_for_model_selection=_boolean(payload, "used_for_model_selection"),
        )
        if record.annotation_role not in _ANNOTATION_ROLES:
            raise IntakeContractError(
                f"unsupported annotation_role for {record.annotation_id}"
            )
        return record

    @property
    def used_for_model_development(self) -> bool:
        return any(
            (
                self.used_for_training,
                self.used_for_threshold_selection,
                self.used_for_hyperparameter_tuning,
                self.used_for_model_selection,
            )
        )


@dataclass(frozen=True)
class EvaluationProtocol:
    source_metadata_review_status: str
    image_content_audit_status: str
    label_content_audit_status: str
    content_overlap_audit_status: str
    test_manifest_checksum_frozen: bool
    metrics_frozen: bool
    confidence_interval_method_frozen: bool
    exclusion_rules_frozen: bool
    frozen_protocol_id: str | None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "EvaluationProtocol":
        allowed = {
            "source_metadata_review_status",
            "image_content_audit_status",
            "label_content_audit_status",
            "content_overlap_audit_status",
            "test_manifest_checksum_frozen",
            "metrics_frozen",
            "confidence_interval_method_frozen",
            "exclusion_rules_frozen",
            "frozen_protocol_id",
        }
        _reject_unknown(payload, allowed, "evaluation_protocol")
        protocol = cls(
            source_metadata_review_status=_audit_status(
                payload, "source_metadata_review_status"
            ),
            image_content_audit_status=_audit_status(
                payload, "image_content_audit_status"
            ),
            label_content_audit_status=_audit_status(
                payload, "label_content_audit_status"
            ),
            content_overlap_audit_status=_audit_status(
                payload, "content_overlap_audit_status"
            ),
            test_manifest_checksum_frozen=_boolean(
                payload, "test_manifest_checksum_frozen"
            ),
            metrics_frozen=_boolean(payload, "metrics_frozen"),
            confidence_interval_method_frozen=_boolean(
                payload, "confidence_interval_method_frozen"
            ),
            exclusion_rules_frozen=_boolean(payload, "exclusion_rules_frozen"),
            frozen_protocol_id=_optional_text(
                payload.get("frozen_protocol_id"), "frozen_protocol_id"
            ),
        )
        if protocol.all_freeze_flags and protocol.frozen_protocol_id is None:
            raise IntakeContractError(
                "frozen_protocol_id is required when all protocol fields are frozen"
            )
        return protocol

    @property
    def all_audits_passed(self) -> bool:
        return all(
            status == "passed"
            for status in (
                self.source_metadata_review_status,
                self.image_content_audit_status,
                self.label_content_audit_status,
                self.content_overlap_audit_status,
            )
        )

    @property
    def all_freeze_flags(self) -> bool:
        return all(
            (
                self.test_manifest_checksum_frozen,
                self.metrics_frozen,
                self.confidence_interval_method_frozen,
                self.exclusion_rules_frozen,
            )
        )


@dataclass(frozen=True)
class IntakeManifest:
    case_id: str
    dataset: DatasetContract
    images: tuple[ImageRecord, ...]
    annotations: tuple[AnnotationRecord, ...]
    evaluation_protocol: EvaluationProtocol

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "IntakeManifest":
        _reject_unknown(
            payload,
            {
                "schema_version",
                "case_id",
                "dataset",
                "images",
                "annotations",
                "evaluation_protocol",
            },
            "manifest",
        )
        if _text(payload, "schema_version") != SCHEMA_VERSION:
            raise IntakeContractError("unsupported schema_version")
        images_raw = payload.get("images")
        annotations_raw = payload.get("annotations")
        if not isinstance(images_raw, list) or not images_raw:
            raise IntakeContractError("images must be a non-empty list")
        if not isinstance(annotations_raw, list):
            raise IntakeContractError("annotations must be a list")
        manifest = cls(
            case_id=_text(payload, "case_id"),
            dataset=DatasetContract.from_mapping(_mapping(payload, "dataset")),
            images=tuple(
                ImageRecord.from_mapping(
                    _mapping_value(item, f"images[{index}]"), index
                )
                for index, item in enumerate(images_raw)
            ),
            annotations=tuple(
                AnnotationRecord.from_mapping(
                    _mapping_value(item, f"annotations[{index}]"), index
                )
                for index, item in enumerate(annotations_raw)
            ),
            evaluation_protocol=EvaluationProtocol.from_mapping(
                _mapping(payload, "evaluation_protocol")
            ),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise IntakeContractError(
                f"case_id mismatch: {self.case_id!r} != {CASE_ID!r}"
            )
        _unique([image.image_id for image in self.images], "image_id")
        _unique([annotation.annotation_id for annotation in self.annotations], "annotation_id")
        image_ids = {image.image_id for image in self.images}
        unknown = sorted(
            {annotation.image_id for annotation in self.annotations} - image_ids
        )
        if unknown:
            raise IntakeContractError(
                f"annotations reference unknown image_id values: {unknown}"
            )


def load_intake_manifest(path: str | Path) -> IntakeManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise IntakeContractError("manifest must contain a JSON object")
    return IntakeManifest.from_mapping(payload)


def run_external_validation_intake(
    manifest: IntakeManifest,
    data_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    root = Path(data_root)
    if not root.is_dir():
        raise NotADirectoryError(root)
    output = _prepare_output(output_dir)
    try:
        file_rows: list[dict[str, Any]] = []
        image_hashes: Counter[str] = Counter()
        for image in manifest.images:
            record = _verify_local_file(
                root,
                relative_path=image.relative_path,
                expected_sha256=image.sha256,
                role="image",
                record_id=image.image_id,
            )
            image_hashes[record["sha256"]] += 1
            file_rows.append(
                {
                    **record,
                    "sample_id": image.sample_id,
                    "acquisition_id": image.acquisition_id,
                    "modality": image.modality,
                    "representation": image.representation,
                    "excluded": image.excluded,
                }
            )
        for annotation in manifest.annotations:
            file_rows.append(
                {
                    **_verify_local_file(
                        root,
                        relative_path=annotation.relative_path,
                        expected_sha256=annotation.sha256,
                        role="annotation",
                        record_id=annotation.annotation_id,
                    ),
                    "sample_id": "",
                    "acquisition_id": "",
                    "modality": "",
                    "representation": annotation.annotation_role,
                    "excluded": False,
                }
            )

        active_images = [image for image in manifest.images if not image.excluded]
        duplicate_active_content = sum(
            count - 1
            for digest, count in image_hashes.items()
            if count > 1
            and any(
                image.sha256 == digest and not image.excluded
                for image in manifest.images
            )
        )
        gates = _evaluate_gates(
            manifest,
            active_images=active_images,
            duplicate_active_content=duplicate_active_content,
        )
        decision = _decision(gates, annotations_present=bool(manifest.annotations))
        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "dataset": {
                "dataset_id": manifest.dataset.dataset_id,
                "dataset_version": manifest.dataset.dataset_version,
                "source_type": manifest.dataset.source_type,
                "material_domain": manifest.dataset.material_domain,
                "license": manifest.dataset.license,
            },
            "result_counts": {
                "image_count": len(manifest.images),
                "active_image_count": len(active_images),
                "excluded_image_count": len(manifest.images) - len(active_images),
                "sample_count": len({image.sample_id for image in active_images}),
                "acquisition_count": len(
                    {image.acquisition_id for image in active_images}
                ),
                "annotation_count": len(manifest.annotations),
                "duplicate_active_image_content_count": duplicate_active_content,
            },
            "evidence_gates": gates,
            "decision": decision,
            "processing": {
                "source_values_modified": False,
                "files_copied": False,
                "labels_remapped": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_metrics_computed": False,
                "physical_conversion_performed": False,
            },
            "scientific_closeout": {
                "status": "Supported",
                "result": decision["status"],
                "strongest_evidence": (
                    "Every declared image and annotation file was resolved beneath the "
                    "configured data root and matched its manifest SHA-256 before readiness "
                    "gates were evaluated."
                ),
                "primary_limitation": (
                    "This intake validates declared provenance and file identity. It does not "
                    "independently prove material identity, acquisition truth, label quality, "
                    "content disjointness, or segmentation performance."
                ),
                "evidence_that_would_change_conclusion": (
                    "Completion of any unresolved source, image-content, label-content, and "
                    "training-overlap audits plus a frozen predeclared evaluation protocol."
                ),
                "suitable_for": [
                    "file-integrity and manifest validation",
                    "annotation-pilot readiness gating",
                    "predeclared evaluation-protocol gating",
                ],
                "not_suitable_for": [
                    "segmentation accuracy estimation",
                    "independent performance claims",
                    "causal interpretation",
                    "engineering release",
                ],
            },
        }

        inventory_path = output / "tem_validation_intake_file_inventory.csv"
        summary_path = output / "tem_validation_intake_summary.json"
        report_path = output / "tem_validation_intake_report.md"
        manifest_path = output / "tem_validation_intake_artifact_manifest.json"
        _write_csv(inventory_path, file_rows)
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary), encoding="utf-8")
        _write_json(
            manifest_path,
            _artifact_manifest(
                output, [inventory_path, summary_path, report_path]
            ),
        )
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _evaluate_gates(
    manifest: IntakeManifest,
    *,
    active_images: Sequence[ImageRecord],
    duplicate_active_content: int,
) -> dict[str, Any]:
    dataset = manifest.dataset
    exact_material = dataset.material_domain.strip().lower() in {
        "cobalt oxide",
        "co3o4",
        "cobalt-oxide",
    }
    lineage_gate = (
        dataset.identity_provenance != "inferred"
        and dataset.cross_dataset_lineage_independence_attested
    )
    creator_gate = (
        not dataset.target_creator_overlap
        or dataset.cross_dataset_lineage_independence_attested
    )
    active_count_gate = len(active_images) >= 2
    sample_count = len({image.sample_id for image in active_images})
    acquisition_count = len({image.acquisition_id for image in active_images})
    independent_units_gate = sample_count >= 2 and acquisition_count >= 2
    representations_gate = bool(active_images) and all(
        image.representation in {"raw_detector", "lossless_export"}
        and image.original_detector_intensity_available
        for image in active_images
    )
    image_nonuse_gate = bool(active_images) and all(
        not image.used_for_model_development for image in active_images
    )
    duplicate_gate = duplicate_active_content == 0

    annotations_by_image: dict[str, list[AnnotationRecord]] = defaultdict(list)
    for annotation in manifest.annotations:
        annotations_by_image[annotation.image_id].append(annotation)

    annotation_details: dict[str, Any] = {}
    complete_images = 0
    for image in active_images:
        records = annotations_by_image.get(image.image_id, [])
        independent = [
            record for record in records if record.annotation_role == "independent"
        ]
        consensus = [
            record
            for record in records
            if record.annotation_role == "adjudicated_consensus"
        ]
        unique_blinded_labelers = {
            record.labeler_id
            for record in independent
            if record.blinded_to_model_predictions
            and not record.used_for_model_development
        }
        versions = {record.label_definition_version for record in records}
        complete = (
            len(unique_blinded_labelers)
            >= dataset.minimum_independent_blinded_labelers
            and len(consensus) == 1
            and consensus[0].blinded_to_model_predictions
            and not consensus[0].used_for_model_development
            and len(versions) == 1
        )
        complete_images += int(complete)
        annotation_details[image.image_id] = {
            "independent_annotation_count": len(independent),
            "unique_blinded_independent_labeler_count": len(
                unique_blinded_labelers
            ),
            "adjudicated_consensus_count": len(consensus),
            "label_definition_version_count": len(versions),
            "complete": complete,
        }

    annotations_complete = bool(active_images) and complete_images == len(active_images)
    protocol = manifest.evaluation_protocol
    protocol_ready = (
        annotations_complete
        and protocol.all_audits_passed
        and protocol.all_freeze_flags
        and protocol.frozen_protocol_id is not None
    )
    annotation_pilot_ready = all(
        (
            exact_material,
            dataset.reuse_authorized,
            dataset.target_training_nonuse_attested,
            lineage_gate,
            creator_gate,
            active_count_gate,
            independent_units_gate,
            representations_gate,
            image_nonuse_gate,
            duplicate_gate,
        )
    )

    unresolved: list[str] = []
    checks = {
        "exact_cobalt_oxide_material_domain": exact_material,
        "reuse_authorized": dataset.reuse_authorized,
        "identity_lineage_independence_attested": lineage_gate,
        "target_training_nonuse_attested": dataset.target_training_nonuse_attested,
        "creator_overlap_resolved_by_lineage": creator_gate,
        "minimum_two_active_images": active_count_gate,
        "minimum_two_samples_and_acquisitions": independent_units_gate,
        "raw_or_lossless_original_intensity_images": representations_gate,
        "image_level_model_development_nonuse": image_nonuse_gate,
        "no_exact_duplicate_active_image_content": duplicate_gate,
        "annotation_pilot_ready": annotation_pilot_ready,
        "independent_annotations_complete": annotations_complete,
        "source_metadata_review_passed": (
            protocol.source_metadata_review_status == "passed"
        ),
        "image_content_audit_passed": (
            protocol.image_content_audit_status == "passed"
        ),
        "label_content_audit_passed": (
            protocol.label_content_audit_status == "passed"
        ),
        "content_overlap_audit_passed": (
            protocol.content_overlap_audit_status == "passed"
        ),
        "evaluation_protocol_frozen": protocol.all_freeze_flags,
        "predeclared_external_evaluation_ready": protocol_ready,
    }
    unresolved.extend(key for key, passed in checks.items() if not passed)
    return {
        **checks,
        "annotation_completion_by_image": annotation_details,
        "unresolved_evidence": unresolved,
    }


def _decision(
    gates: Mapping[str, Any], *, annotations_present: bool
) -> dict[str, Any]:
    annotation_ready = bool(gates["annotation_pilot_ready"])
    annotations_complete = bool(gates["independent_annotations_complete"])
    evaluation_ready = bool(gates["predeclared_external_evaluation_ready"])
    if not annotation_ready:
        status = BLOCKED
        next_action = (
            "Resolve dataset lineage, representation, independent-unit, non-use, or "
            "duplicate-content blockers before annotation."
        )
    elif not annotations_present:
        status = ANNOTATION_READY
        next_action = (
            "Freeze the label definition and conduct blinded independent annotation with "
            "at least two labelers plus adjudicated consensus for every active image."
        )
    elif not annotations_complete:
        status = ANNOTATION_INCOMPLETE
        next_action = (
            "Complete blinded independent labels and exactly one adjudicated consensus per "
            "active image without exposing model predictions."
        )
    elif not evaluation_ready:
        status = PROTOCOL_FREEZE_REQUIRED
        next_action = (
            "Complete source, image, label, and content-overlap audits and freeze metrics, "
            "confidence intervals, exclusions, and the checksum-bound test manifest."
        )
    else:
        status = EVALUATION_READY
        next_action = (
            "Run the frozen model inference exactly as predeclared and preserve model, "
            "software, test-manifest, exclusions, metrics, and uncertainty versions."
        )
    return {
        "status": status,
        "blinded_annotation_pilot_ready": annotation_ready,
        "predeclared_external_model_evaluation_ready": evaluation_ready,
        "model_inference_allowed_now": evaluation_ready,
        "independent_performance_claim_ready": False,
        "engineering_release_ready": False,
        "model_retraining_is_current_priority": False,
        "next_action": next_action,
    }


def _verify_local_file(
    root: Path,
    *,
    relative_path: str,
    expected_sha256: str,
    role: str,
    record_id: str,
) -> dict[str, Any]:
    pure = PurePosixPath(relative_path)
    candidate = root.joinpath(*pure.parts)
    if candidate.is_symlink():
        raise IntakeContractError(f"symlink inputs are not allowed: {relative_path}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(relative_path) from exc
    root_resolved = root.resolve(strict=True)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise IntakeContractError(
            f"input escapes data_root: {relative_path}"
        ) from exc
    if not resolved.is_file():
        raise IntakeContractError(f"input is not a regular file: {relative_path}")
    digest = hashlib.sha256()
    size = 0
    with resolved.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    observed = digest.hexdigest()
    if observed != expected_sha256:
        raise IntakeContractError(
            f"SHA-256 mismatch for {relative_path}: {observed} != {expected_sha256}"
        )
    return {
        "record_id": record_id,
        "role": role,
        "relative_path": relative_path,
        "bytes": size,
        "sha256": observed,
    }


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
    return output


def _artifact_manifest(output: Path, artifacts: Sequence[Path]) -> dict[str, Any]:
    rows = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in artifacts
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "software_version": __version__,
        "artifact_count": len(rows),
        "artifacts": rows,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    decision = _mapping(summary, "decision")
    gates = _mapping(summary, "evidence_gates")
    unresolved = gates.get("unresolved_evidence")
    if not isinstance(unresolved, list):
        raise IntakeContractError("unresolved_evidence must be a list")
    lines = [
        "# TEM External-Validation Intake",
        "",
        "**Evidence conclusion:** Supported for intake gating",
        "",
        f"**Result:** `{decision['status']}`",
        "",
        "## Decision",
        "",
        f"- Blinded annotation pilot ready: `{str(decision['blinded_annotation_pilot_ready']).lower()}`",
        f"- Predeclared external evaluation ready: `{str(decision['predeclared_external_model_evaluation_ready']).lower()}`",
        f"- Independent performance claim ready: `{str(decision['independent_performance_claim_ready']).lower()}`",
        "",
        "## Unresolved evidence",
        "",
    ]
    lines.extend(f"- {item}" for item in unresolved)
    lines.extend(
        [
            "",
            "## Next",
            "",
            str(decision["next_action"]),
            "",
            "## Scientific boundary",
            "",
            "This intake verifies declared metadata and file SHA-256 values. It does not "
            "independently establish material identity, label quality, segmentation accuracy, "
            "or engineering readiness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    records = list(rows)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    columns = list(records[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in records:
            writer.writerow({column: row.get(column) for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise IntakeContractError(f"{key} must be an object")
    return value


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IntakeContractError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IntakeContractError(f"{key} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise IntakeContractError(f"{key} must be null or non-empty text")
    return value.strip()


def _identifier(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
        raise IntakeContractError(f"{key} contains unsupported characters")
    return value


def _relative_path(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).replace("\\", "/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise IntakeContractError(f"{key} must be a safe relative path")
    return pure.as_posix()


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise IntakeContractError(f"{key} must contain 64 lowercase hexadecimal characters")
    return value


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise IntakeContractError(f"{key} must be a boolean")
    return value


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise IntakeContractError(f"{key} must be an integer")
    return value


def _optional_positive_float(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IntakeContractError(f"{key} must be null or numeric")
    result = float(value)
    if result <= 0:
        raise IntakeContractError(f"{key} must be positive")
    return result


def _audit_status(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if value not in _AUDIT_STATUSES:
        raise IntakeContractError(f"unsupported {key}: {value}")
    return value


def _unique(values: Sequence[str], label: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise IntakeContractError(f"duplicate {label} values: {duplicates}")


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise IntakeContractError(f"unknown {context} keys: {unknown}")
