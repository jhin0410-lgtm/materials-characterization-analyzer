"""Evaluate the dated TEM external-validation candidate registry.

The engine is deliberately fail closed. Repository separation, filenames, and
rendered figure images never establish sample/acquisition independence or model-
evaluation readiness.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import __version__

CASE_ID = "tem_external_validation_candidate_registry"
SCHEMA_VERSION = "1.0"
RESULT = "no_public_candidate_ready_for_in_domain_external_validation"
READY_RESULT = "public_candidate_ready_for_dedicated_in_domain_validation_audit"
SUPPORTED_TARGET_TASK = "binary nanoparticle segmentation for cobalt-oxide TEM or HRTEM images"
SUPPORTED_TARGET_MATERIAL = "cobalt oxide"
SUPPORTED_TARGET_MODALITIES = frozenset({"TEM", "HRTEM"})

TARGET_SOURCE = "target_training_source"
IN_DOMAIN_READY = "in_domain_external_validation_ready"
METADATA_RESOLUTION = "metadata_resolution_required_before_image_audit"
ANNOTATION_PILOT = "annotation_pilot_candidate_not_validation_ready"
PROCESSED_IN_DOMAIN = "processed_in_domain_diagnostic_only"
CROSS_PHASE = "cross_phase_annotation_candidate_not_in_domain"
CROSS_MATERIAL = "diagnostic_cross_material_only"
WRONG_MODALITY = "excluded_wrong_microscopy_modality"
EXCLUDED_REPRESENTATION = "excluded_rendered_figure_representation"

_MATERIAL_RELATIONS = {
    "exact_cobalt_oxide",
    "heterojunction_contains_cobalt_oxide",
    "related_cobalt_phase",
    "not_cobalt_oxide",
}
_DOMAIN_RELATIONS = {
    "potentially_comparable_after_file_audit",
    "material_or_acquisition_domain_shift",
    "unknown_until_file_audit",
    "wrong_modality",
    "rendered_mixed_heterojunction_figure_images",
}
_RESOLVED_INVENTORIES = {"exact", "record_metadata_verified"}


class CandidateContractError(ValueError):
    """Raised when registry input violates the pinned schema."""


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    repository: str
    doi: str
    record_url: str
    title: str
    materials: tuple[str, ...]
    modalities: tuple[str, ...]
    file_inventory_status: str
    file_checksums_available: bool
    raw_or_lossless_tem_images_available: bool
    reported_tem_file_count: int | None
    independent_segmentation_labels_available: bool
    label_origin: str
    labeler_count: int | None
    blinded_labeling_verified: bool
    adjudicated_consensus_available: bool
    immutable_sample_ids_available: bool
    immutable_acquisition_ids_available: bool
    verified_not_used_for_target_training_or_model_selection: bool
    target_creator_name_overlap: bool
    target_material_relation: str
    imaging_domain_relation: str
    reuse_license: str
    reuse_license_verified: bool
    target_training_source: bool
    source_evidence: tuple[str, ...]
    next_validation_step: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], index: int) -> "Candidate":
        allowed = {
            "candidate_id",
            "repository",
            "doi",
            "record_url",
            "title",
            "materials",
            "modalities",
            "file_inventory_status",
            "file_checksums_available",
            "raw_or_lossless_tem_images_available",
            "reported_tem_file_count",
            "independent_segmentation_labels_available",
            "label_origin",
            "labeler_count",
            "blinded_labeling_verified",
            "adjudicated_consensus_available",
            "immutable_sample_ids_available",
            "immutable_acquisition_ids_available",
            "verified_not_used_for_target_training_or_model_selection",
            "target_creator_name_overlap",
            "target_material_relation",
            "imaging_domain_relation",
            "reuse_license",
            "reuse_license_verified",
            "target_training_source",
            "source_evidence",
            "next_validation_step",
        }
        _reject_unknown(payload, allowed, f"candidates[{index}]")
        candidate = cls(
            candidate_id=_text(payload, "candidate_id"),
            repository=_text(payload, "repository"),
            doi=_text(payload, "doi"),
            record_url=_https(payload, "record_url"),
            title=_text(payload, "title"),
            materials=_texts(payload, "materials"),
            modalities=_texts(payload, "modalities"),
            file_inventory_status=_text(payload, "file_inventory_status"),
            file_checksums_available=_boolean(payload, "file_checksums_available"),
            raw_or_lossless_tem_images_available=_boolean(
                payload, "raw_or_lossless_tem_images_available"
            ),
            reported_tem_file_count=_optional_integer(
                payload.get("reported_tem_file_count"), "reported_tem_file_count"
            ),
            independent_segmentation_labels_available=_boolean(
                payload, "independent_segmentation_labels_available"
            ),
            label_origin=_text(payload, "label_origin"),
            labeler_count=_optional_integer(payload.get("labeler_count"), "labeler_count"),
            blinded_labeling_verified=_boolean(
                payload, "blinded_labeling_verified"
            ),
            adjudicated_consensus_available=_boolean(
                payload, "adjudicated_consensus_available"
            ),
            immutable_sample_ids_available=_boolean(
                payload, "immutable_sample_ids_available"
            ),
            immutable_acquisition_ids_available=_boolean(
                payload, "immutable_acquisition_ids_available"
            ),
            verified_not_used_for_target_training_or_model_selection=_boolean(
                payload, "verified_not_used_for_target_training_or_model_selection"
            ),
            target_creator_name_overlap=_boolean(
                payload, "target_creator_name_overlap"
            ),
            target_material_relation=_text(payload, "target_material_relation"),
            imaging_domain_relation=_text(payload, "imaging_domain_relation"),
            reuse_license=_text(payload, "reuse_license"),
            reuse_license_verified=_boolean(payload, "reuse_license_verified"),
            target_training_source=_boolean(payload, "target_training_source"),
            source_evidence=_texts(payload, "source_evidence"),
            next_validation_step=_text(payload, "next_validation_step"),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.candidate_id):
            raise CandidateContractError(f"invalid candidate_id: {self.candidate_id!r}")
        if self.target_material_relation not in _MATERIAL_RELATIONS:
            raise CandidateContractError(
                f"unsupported target_material_relation for {self.candidate_id}"
            )
        if self.imaging_domain_relation not in _DOMAIN_RELATIONS:
            raise CandidateContractError(
                f"unsupported imaging_domain_relation for {self.candidate_id}"
            )
        if self.independent_segmentation_labels_available and self.labeler_count is None:
            raise CandidateContractError(
                f"{self.candidate_id} reports labels without labeler_count"
            )
        if not self.independent_segmentation_labels_available and (
            self.labeler_count not in (None, 0)
            or self.blinded_labeling_verified
            or self.adjudicated_consensus_available
        ):
            raise CandidateContractError(
                f"{self.candidate_id} reports annotation evidence without independent labels"
            )
        if self.blinded_labeling_verified and (self.labeler_count or 0) < 2:
            raise CandidateContractError(
                f"{self.candidate_id} cannot verify blinded labeling with fewer than two labelers"
            )
        if self.adjudicated_consensus_available and (self.labeler_count or 0) < 2:
            raise CandidateContractError(
                f"{self.candidate_id} cannot report adjudication with fewer than two labelers"
            )
        if self.target_training_source and not self.target_creator_name_overlap:
            raise CandidateContractError(
                "target training source must report creator overlap"
            )
        if (
            self.reported_tem_file_count == 0
            and self.raw_or_lossless_tem_images_available
        ):
            raise CandidateContractError(
                f"{self.candidate_id} reports zero TEM files but TEM availability"
            )


@dataclass(frozen=True)
class RegistryConfig:
    case_id: str
    search_date: str
    repositories_searched: tuple[str, ...]
    search_terms: tuple[str, ...]
    target_task: str
    target_material: str
    target_modalities: tuple[str, ...]
    target_training_creators: tuple[str, ...]
    candidates: tuple[Candidate, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RegistryConfig":
        _reject_unknown(
            payload,
            {"case_id", "search_snapshot", "target_contract", "candidates"},
            "config",
        )
        snapshot = _mapping(payload, "search_snapshot")
        target = _mapping(payload, "target_contract")
        _reject_unknown(
            snapshot,
            {"search_date", "repositories_searched", "search_terms"},
            "search_snapshot",
        )
        _reject_unknown(
            target,
            {"task", "material", "modalities", "target_training_creators"},
            "target_contract",
        )
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise CandidateContractError("candidates must be a non-empty list")
        candidates = tuple(
            Candidate.from_mapping(_mapping_value(item, f"candidates[{index}]"), index)
            for index, item in enumerate(raw_candidates)
        )
        config = cls(
            case_id=_text(payload, "case_id"),
            search_date=_date(snapshot, "search_date"),
            repositories_searched=_texts(snapshot, "repositories_searched"),
            search_terms=_texts(snapshot, "search_terms"),
            target_task=_text(target, "task"),
            target_material=_text(target, "material"),
            target_modalities=_texts(target, "modalities"),
            target_training_creators=_texts(target, "target_training_creators"),
            candidates=candidates,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise CandidateContractError(
                f"case_id mismatch: {self.case_id!r} != {CASE_ID!r}"
            )
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise CandidateContractError("candidate_id values must be unique")
        if self.target_task != SUPPORTED_TARGET_TASK:
            raise CandidateContractError(
                f"unsupported target task: {self.target_task!r}"
            )
        if self.target_material.casefold() != SUPPORTED_TARGET_MATERIAL:
            raise CandidateContractError(
                f"unsupported target material: {self.target_material!r}"
            )
        normalized_modalities = {_normalize_modality(value) for value in self.target_modalities}
        if normalized_modalities != SUPPORTED_TARGET_MODALITIES:
            raise CandidateContractError(
                "target modalities must be exactly TEM and HRTEM"
            )
        if not any(candidate.target_training_source for candidate in self.candidates):
            raise CandidateContractError("registry must contain the target-source control")


def load_registry_config(path: str | Path) -> RegistryConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise CandidateContractError("registry config must contain a JSON object")
    return RegistryConfig.from_mapping(payload)


def run_candidate_registry(
    config: RegistryConfig, output_dir: str | Path
) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    try:
        rows = [_candidate_row(candidate) for candidate in config.candidates]
        rows.sort(key=lambda row: (int(row["priority_rank"]), str(row["candidate_id"])))
        counts = _counts(rows)
        recommended = _recommendation(rows)
        protocol = _annotation_protocol()
        ready_count = counts["in_domain_external_validation_ready_count"]
        ready_candidate_available = ready_count > 0
        result = READY_RESULT if ready_candidate_available else RESULT
        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "search_snapshot": {
                "search_date": config.search_date,
                "repositories_searched": list(config.repositories_searched),
                "search_terms": list(config.search_terms),
                "candidate_count": len(rows),
                "globally_exhaustive": False,
            },
            "target_contract": {
                "task": config.target_task,
                "material": config.target_material,
                "modalities": list(config.target_modalities),
                "target_training_creators": list(config.target_training_creators),
            },
            "result_counts": counts,
            "readiness": {
                "status": result,
                "candidate_search_completed_for_snapshot": True,
                "search_is_globally_exhaustive": False,
                "independent_in_domain_external_validation_available": (
                    ready_candidate_available
                ),
                "public_search_supports_model_evaluation_now": (
                    ready_candidate_available
                ),
                "recommended_candidate_id": recommended["candidate_id"],
                "recommended_candidate_status": recommended["candidate_status"],
                "recommended_next_action": recommended["next_validation_step"],
                "model_retraining_is_current_priority": False,
            },
            "annotation_protocol": protocol,
            "processing": {
                "source_arrays_downloaded_by_registry": False,
                "source_arrays_modified": False,
                "labels_created": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_metrics_computed": False,
            },
            "scientific_closeout": {
                "status": "Supported",
                "result": result,
                "strongest_evidence": (
                    f"{len(rows)} public records were assessed against explicit material, "
                    "modality, file, representation, lineage, label, non-use, and licence "
                    "gates. Exact-material records remain blocked as target-source data, "
                    "processed single-particle data, or representations without the "
                    "lineage and labels required for independent validation."
                ),
                "primary_limitation": (
                    "No public candidate provides checksum-bound raw cobalt-oxide TEM images "
                    "with immutable sample/acquisition IDs, verified model-development non-use, "
                    "and independent adjudicated segmentation labels."
                ),
                "evidence_that_would_change_conclusion": (
                    "A newly acquired or author-released raw cobalt-oxide TEM set with immutable "
                    "sample/acquisition lineage, verified non-use, content-overlap clearance, "
                    "at least two blinded independent labels plus adjudication, and a frozen "
                    "evaluation manifest."
                ),
                "suitable_for": [
                    "public candidate triage",
                    "documenting candidate exclusions",
                    "planning independent data acquisition and annotation",
                ],
                "not_suitable_for": [
                    "segmentation accuracy estimation",
                    "model selection",
                    "independent performance claims",
                    "engineering release",
                ],
            },
        }

        inventory_path = output / "tem_external_validation_candidate_inventory.csv"
        summary_path = output / "tem_external_validation_candidate_summary.json"
        report_path = output / "tem_external_validation_candidate_report.md"
        protocol_path = output / "tem_external_validation_annotation_protocol.json"
        manifest_path = output / "tem_external_validation_candidate_manifest.json"
        _write_csv(inventory_path, rows, INVENTORY_COLUMNS)
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary, rows), encoding="utf-8")
        _write_json(protocol_path, protocol)
        _write_json(
            manifest_path,
            _manifest(
                output,
                [inventory_path, summary_path, report_path, protocol_path],
                config.search_date,
            ),
        )
        return summary
    except Exception:
        if output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _candidate_row(candidate: Candidate) -> dict[str, Any]:
    exact_target = candidate.target_material_relation == "exact_cobalt_oxide"
    material_candidate = candidate.target_material_relation in {
        "exact_cobalt_oxide",
        "heterojunction_contains_cobalt_oxide",
    }
    modality_tokens = {_normalize_modality(value) for value in candidate.modalities}
    has_tem_modality = bool(modality_tokens & SUPPORTED_TARGET_MODALITIES)
    modality_available = candidate.raw_or_lossless_tem_images_available and has_tem_modality
    rendered_exclusion = (
        candidate.imaging_domain_relation == "rendered_mixed_heterojunction_figure_images"
    )
    processed_in_domain = all(
        (
            exact_target,
            has_tem_modality,
            not candidate.raw_or_lossless_tem_images_available,
            candidate.file_inventory_status in _RESOLVED_INVENTORIES,
            not rendered_exclusion,
        )
    )
    annotation_contract_satisfied = all(
        (
            candidate.independent_segmentation_labels_available,
            (candidate.labeler_count or 0) >= 2,
            candidate.blinded_labeling_verified,
            candidate.adjudicated_consensus_available,
        )
    )
    ready = all(
        (
            exact_target,
            modality_available,
            candidate.file_inventory_status in _RESOLVED_INVENTORIES,
            candidate.file_checksums_available,
            annotation_contract_satisfied,
            candidate.immutable_sample_ids_available,
            candidate.immutable_acquisition_ids_available,
            candidate.verified_not_used_for_target_training_or_model_selection,
            candidate.reuse_license_verified,
            not candidate.target_creator_name_overlap,
            not candidate.target_training_source,
        )
    )

    blockers: list[str] = []
    if candidate.target_training_source:
        blockers.append("same_source_as_target_training_data")
    if not material_candidate:
        blockers.append("target_material_mismatch")
    if not modality_available:
        blockers.append("raw_or_lossless_tem_images_unavailable")
    if rendered_exclusion:
        blockers.append("rendered_figure_representation_not_raw_validation_data")
    if candidate.file_inventory_status not in _RESOLVED_INVENTORIES:
        blockers.append("exact_file_inventory_unresolved")
    if not candidate.file_checksums_available:
        blockers.append("file_checksums_unavailable")
    if not candidate.independent_segmentation_labels_available:
        blockers.append("independent_segmentation_labels_unavailable")
    if (candidate.labeler_count or 0) < 2:
        blockers.append("minimum_two_independent_labelers_unavailable")
    if not candidate.blinded_labeling_verified:
        blockers.append("blinded_labeling_unverified")
    if not candidate.adjudicated_consensus_available:
        blockers.append("adjudicated_consensus_unavailable")
    if not candidate.immutable_sample_ids_available:
        blockers.append("immutable_sample_ids_unavailable")
    if not candidate.immutable_acquisition_ids_available:
        blockers.append("immutable_acquisition_ids_unavailable")
    if not candidate.verified_not_used_for_target_training_or_model_selection:
        blockers.append("target_model_nonuse_unverified")
    if candidate.target_creator_name_overlap:
        blockers.append("target_creator_overlap")
    if not candidate.reuse_license_verified:
        blockers.append("reuse_license_unverified")

    if candidate.target_training_source:
        status, rank = TARGET_SOURCE, 90
    elif ready:
        status, rank = IN_DOMAIN_READY, 1
    elif processed_in_domain:
        status, rank = PROCESSED_IN_DOMAIN, 12
    elif rendered_exclusion:
        status, rank = EXCLUDED_REPRESENTATION, 15
    elif candidate.file_inventory_status not in _RESOLVED_INVENTORIES:
        status, rank = METADATA_RESOLUTION, 10
    elif candidate.imaging_domain_relation == "wrong_modality" or not has_tem_modality:
        status, rank = WRONG_MODALITY, 99
    elif exact_target and modality_available:
        status, rank = ANNOTATION_PILOT, 20
    elif candidate.target_material_relation == "related_cobalt_phase":
        status, rank = CROSS_PHASE, 40
    else:
        status, rank = CROSS_MATERIAL, 60

    return {
        "candidate_id": candidate.candidate_id,
        "priority_rank": rank,
        "candidate_status": status,
        "repository": candidate.repository,
        "doi": candidate.doi,
        "record_url": candidate.record_url,
        "title": candidate.title,
        "materials": " | ".join(candidate.materials),
        "modalities": " | ".join(candidate.modalities),
        "file_inventory_status": candidate.file_inventory_status,
        "file_checksums_available": candidate.file_checksums_available,
        "raw_or_lossless_tem_images_available": (
            candidate.raw_or_lossless_tem_images_available
        ),
        "reported_tem_file_count": candidate.reported_tem_file_count,
        "independent_segmentation_labels_available": (
            candidate.independent_segmentation_labels_available
        ),
        "label_origin": candidate.label_origin,
        "labeler_count": candidate.labeler_count,
        "blinded_labeling_verified": candidate.blinded_labeling_verified,
        "adjudicated_consensus_available": (
            candidate.adjudicated_consensus_available
        ),
        "immutable_sample_ids_available": candidate.immutable_sample_ids_available,
        "immutable_acquisition_ids_available": (
            candidate.immutable_acquisition_ids_available
        ),
        "verified_not_used_for_target_training_or_model_selection": (
            candidate.verified_not_used_for_target_training_or_model_selection
        ),
        "target_creator_name_overlap": candidate.target_creator_name_overlap,
        "target_material_relation": candidate.target_material_relation,
        "imaging_domain_relation": candidate.imaging_domain_relation,
        "reuse_license": candidate.reuse_license,
        "reuse_license_verified": candidate.reuse_license_verified,
        "target_training_source": candidate.target_training_source,
        "in_domain_external_validation_ready": ready,
        "evaluation_ready": ready,
        "blockers": " | ".join(blockers),
        "source_evidence": " | ".join(candidate.source_evidence),
        "next_validation_step": candidate.next_validation_step,
    }


def _recommendation(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    preference = (
        IN_DOMAIN_READY,
        METADATA_RESOLUTION,
        ANNOTATION_PILOT,
        PROCESSED_IN_DOMAIN,
        EXCLUDED_REPRESENTATION,
        CROSS_PHASE,
        CROSS_MATERIAL,
        TARGET_SOURCE,
        WRONG_MODALITY,
    )
    for status in preference:
        matching = [row for row in rows if row["candidate_status"] == status]
        if matching:
            return min(
                matching,
                key=lambda row: (int(row["priority_rank"]), str(row["candidate_id"])),
            )
    raise CandidateContractError("registry produced no recommendation")


def _counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    def count(status: str) -> int:
        return sum(row["candidate_status"] == status for row in rows)

    return {
        "candidate_count": len(rows),
        "in_domain_external_validation_ready_count": count(IN_DOMAIN_READY),
        "metadata_resolution_candidate_count": count(METADATA_RESOLUTION),
        "annotation_pilot_candidate_count": count(ANNOTATION_PILOT),
        "processed_in_domain_diagnostic_count": count(PROCESSED_IN_DOMAIN),
        "rendered_representation_exclusion_count": count(EXCLUDED_REPRESENTATION),
        "cross_phase_candidate_count": count(CROSS_PHASE),
        "diagnostic_cross_material_candidate_count": count(CROSS_MATERIAL),
        "excluded_control_count": count(TARGET_SOURCE) + count(WRONG_MODALITY),
    }


def _annotation_protocol() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "purpose": "predeclared independent cobalt-oxide TEM validation annotation",
        "annotation_requirements": {
            "minimum_independent_blinded_labelers": 2,
            "adjudication_required": True,
            "label_definition_frozen_before_annotation": True,
            "ambiguous_region_policy_predeclared": True,
            "labelers_can_view_model_predictions": False,
        },
        "independence_requirements": {
            "immutable_sample_ids_required": True,
            "immutable_acquisition_ids_required": True,
            "not_used_for_training": True,
            "not_used_for_threshold_selection": True,
            "not_used_for_hyperparameter_tuning": True,
            "not_used_for_model_selection": True,
            "content_overlap_audit_completed_before_inference": True,
        },
        "evaluation_freeze_requirements": {
            "test_manifest_checksum_frozen": True,
            "metrics_frozen_before_inference": True,
            "confidence_interval_method_frozen_before_inference": True,
            "exclusion_rules_frozen_before_inference": True,
            "single_final_inference_pass_preferred": True,
        },
        "prohibited_shortcuts": [
            "labeling from model predictions without independent blinded review",
            "selecting test images after viewing model performance",
            "joining images by filename inference or row order",
            "treating rendered publication figures as raw detector data",
            "using creator or repository separation as proof of acquisition independence",
        ],
    }


def _build_report(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    readiness = _mapping(summary, "readiness")
    counts = _mapping(summary, "result_counts")
    lines = [
        "# TEM External-Validation Candidate Registry",
        "",
        "**Evidence conclusion:** Supported for candidate triage",
        "",
        f"**Result:** `{readiness['status']}`",
        "",
        "## Result counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in counts.items())
    lines.extend(["", "## Candidates", ""])
    for row in rows:
        lines.append(
            f"- `{row['candidate_id']}` — `{row['candidate_status']}`; "
            f"blockers: {row['blockers'] or 'none'}"
        )
    lines.extend(
        [
            "",
            "## Next",
            "",
            str(readiness["recommended_next_action"]),
            "",
            "## Scientific boundary",
            "",
            "This registry does not train or evaluate a model. Rendered figure files, "
            "repository separation, and filenames do not establish independent validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
    return output


def _manifest(output: Path, paths: Sequence[Path], search_date: str) -> dict[str, Any]:
    artifacts = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "software_version": __version__,
        "search_date": search_date,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def _write_csv(
    path: Path, rows: Iterable[Mapping[str, Any]], columns: Sequence[str]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise CandidateContractError(f"{key} must be an object")
    return value


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateContractError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CandidateContractError(f"{key} must be non-empty text")
    return value.strip()


def _https(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise CandidateContractError(f"{key} must be an HTTPS URL")
    return value


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise CandidateContractError(f"{key} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise CandidateContractError(f"{key} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise CandidateContractError(f"{key} must be a boolean")
    return value


def _optional_integer(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CandidateContractError(f"{key} must be null or a non-negative integer")
    return value


def _normalize_modality(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _date(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CandidateContractError(f"{key} must use YYYY-MM-DD")
    return value


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CandidateContractError(f"unknown {context} keys: {unknown}")


INVENTORY_COLUMNS = (
    "candidate_id",
    "priority_rank",
    "candidate_status",
    "repository",
    "doi",
    "record_url",
    "title",
    "materials",
    "modalities",
    "file_inventory_status",
    "file_checksums_available",
    "raw_or_lossless_tem_images_available",
    "reported_tem_file_count",
    "independent_segmentation_labels_available",
    "label_origin",
    "labeler_count",
    "blinded_labeling_verified",
    "adjudicated_consensus_available",
    "immutable_sample_ids_available",
    "immutable_acquisition_ids_available",
    "verified_not_used_for_target_training_or_model_selection",
    "target_creator_name_overlap",
    "target_material_relation",
    "imaging_domain_relation",
    "reuse_license",
    "reuse_license_verified",
    "target_training_source",
    "in_domain_external_validation_ready",
    "evaluation_ready",
    "blockers",
    "source_evidence",
    "next_validation_step",
)
