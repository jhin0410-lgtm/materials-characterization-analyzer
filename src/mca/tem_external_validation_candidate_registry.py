"""Build a dated, source-backed TEM external-validation candidate registry.

This registry performs metadata-level triage only. It never treats repository
separation as acquisition independence, never creates labels, and never runs a
model. Unknown evidence fails closed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__

CASE_ID = "tem_external_validation_candidate_registry"
SCHEMA_VERSION = "1.0"
RESULT = "no_public_candidate_ready_for_in_domain_external_validation"

TARGET_SOURCE = "target_training_source"
IN_DOMAIN_READY = "in_domain_external_validation_ready"
METADATA_RESOLUTION = "metadata_resolution_required_before_image_audit"
ANNOTATION_PILOT = "annotation_pilot_candidate_not_validation_ready"
CROSS_PHASE = "cross_phase_annotation_candidate_not_in_domain"
CROSS_MATERIAL = "diagnostic_cross_material_only"
WRONG_MODALITY = "excluded_wrong_microscopy_modality"

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
}


class CandidateContractError(ValueError):
    """Raised when the pinned registry contract is malformed."""


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
    def from_mapping(cls, value: Mapping[str, Any], index: int) -> "Candidate":
        allowed = {
            "candidate_id", "repository", "doi", "record_url", "title",
            "materials", "modalities", "file_inventory_status",
            "file_checksums_available", "raw_or_lossless_tem_images_available",
            "reported_tem_file_count", "independent_segmentation_labels_available",
            "label_origin", "labeler_count", "immutable_sample_ids_available",
            "immutable_acquisition_ids_available",
            "verified_not_used_for_target_training_or_model_selection",
            "target_creator_name_overlap", "target_material_relation",
            "imaging_domain_relation", "reuse_license", "reuse_license_verified",
            "target_training_source", "source_evidence", "next_validation_step",
        }
        _reject_unknown(value, allowed, f"candidates[{index}]")
        candidate = cls(
            candidate_id=_text(value, "candidate_id"),
            repository=_text(value, "repository"),
            doi=_text(value, "doi"),
            record_url=_https(value, "record_url"),
            title=_text(value, "title"),
            materials=_texts(value, "materials"),
            modalities=_texts(value, "modalities"),
            file_inventory_status=_text(value, "file_inventory_status"),
            file_checksums_available=_bool(value, "file_checksums_available"),
            raw_or_lossless_tem_images_available=_bool(
                value, "raw_or_lossless_tem_images_available"
            ),
            reported_tem_file_count=_optional_int(
                value.get("reported_tem_file_count"), "reported_tem_file_count"
            ),
            independent_segmentation_labels_available=_bool(
                value, "independent_segmentation_labels_available"
            ),
            label_origin=_text(value, "label_origin"),
            labeler_count=_optional_int(value.get("labeler_count"), "labeler_count"),
            immutable_sample_ids_available=_bool(
                value, "immutable_sample_ids_available"
            ),
            immutable_acquisition_ids_available=_bool(
                value, "immutable_acquisition_ids_available"
            ),
            verified_not_used_for_target_training_or_model_selection=_bool(
                value, "verified_not_used_for_target_training_or_model_selection"
            ),
            target_creator_name_overlap=_bool(value, "target_creator_name_overlap"),
            target_material_relation=_text(value, "target_material_relation"),
            imaging_domain_relation=_text(value, "imaging_domain_relation"),
            reuse_license=_text(value, "reuse_license"),
            reuse_license_verified=_bool(value, "reuse_license_verified"),
            target_training_source=_bool(value, "target_training_source"),
            source_evidence=_texts(value, "source_evidence"),
            next_validation_step=_text(value, "next_validation_step"),
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
        if self.target_training_source and not self.target_creator_name_overlap:
            raise CandidateContractError(
                "target training source must report creator overlap"
            )
        if self.reported_tem_file_count == 0 and self.raw_or_lossless_tem_images_available:
            raise CandidateContractError(
                f"{self.candidate_id} reports zero TEM files but TEM availability"
            )


@dataclass(frozen=True)
class RegistryConfig:
    case_id: str
    search_date: str
    target_task: str
    target_material: str
    target_modalities: tuple[str, ...]
    repositories_searched: tuple[str, ...]
    search_terms: tuple[str, ...]
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
            Candidate.from_mapping(_as_mapping(item, f"candidates[{index}]"), index)
            for index, item in enumerate(raw_candidates)
        )
        config = cls(
            case_id=_text(payload, "case_id"),
            search_date=_date(snapshot, "search_date"),
            target_task=_text(target, "task"),
            target_material=_text(target, "material"),
            target_modalities=_texts(target, "modalities"),
            repositories_searched=_texts(snapshot, "repositories_searched"),
            search_terms=_texts(snapshot, "search_terms"),
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
    """Evaluate the pinned public-source snapshot and write evidence artifacts."""
    output = _prepare_output(output_dir)
    try:
        rows = [_candidate_row(candidate) for candidate in config.candidates]
        rows.sort(key=lambda row: (int(row["priority_rank"]), str(row["candidate_id"])))
        counts = _counts(rows)
        recommended = next(
            row for row in rows if row["candidate_status"] == METADATA_RESOLUTION
        )
        protocol = _annotation_protocol()
        readiness = {
            "status": RESULT,
            "candidate_search_completed_for_snapshot": True,
            "search_is_globally_exhaustive": False,
            "independent_in_domain_external_validation_available": False,
            "public_search_supports_model_evaluation_now": False,
            "recommended_candidate_id": recommended["candidate_id"],
            "recommended_candidate_status": recommended["candidate_status"],
            "recommended_next_action": recommended["next_validation_step"],
            "model_retraining_is_current_priority": False,
        }
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
            "readiness": readiness,
            "annotation_protocol": protocol,
            "processing": {
                "source_arrays_downloaded": False,
                "source_arrays_modified": False,
                "labels_created": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_metrics_computed": False,
            },
            "scientific_closeout": {
                "status": "Supported",
                "result": RESULT,
                "strongest_evidence": (
                    "Six public records were screened against explicit material, modality, "
                    "file, lineage, label, non-use, and licence gates; none satisfies all "
                    "requirements for independent cobalt-oxide model evaluation."
                ),
                "primary_limitation": (
                    "The search is a dated non-exhaustive snapshot, and the leading Co3O4-"
                    "containing record lacks a resolved file inventory, checksums, immutable "
                    "sample/acquisition lineage, and independent segmentation labels."
                ),
                "evidence_that_would_change_conclusion": (
                    "Checksum-bound cobalt-oxide TEM files with immutable sample and "
                    "acquisition IDs, verified non-use, at least two blinded independent "
                    "labels plus adjudication, and a frozen evaluation manifest."
                ),
                "suitable_for": [
                    "public candidate triage",
                    "metadata-resolution prioritization",
                    "annotation-pilot protocol planning",
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
        "exact_cobalt_oxide", "heterojunction_contains_cobalt_oxide"
    }
    modality_available = candidate.raw_or_lossless_tem_images_available and any(
        "TEM" in value.upper() for value in candidate.modalities
    )
    ready = all(
        (
            exact_target,
            modality_available,
            candidate.file_checksums_available,
            candidate.independent_segmentation_labels_available,
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
        blockers.append("tem_or_hrtem_images_unavailable")
    if candidate.file_inventory_status not in {"exact", "record_metadata_verified"}:
        blockers.append("exact_file_inventory_unresolved")
    if not candidate.file_checksums_available:
        blockers.append("file_checksums_unavailable")
    if not candidate.independent_segmentation_labels_available:
        blockers.append("independent_segmentation_labels_unavailable")
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
    elif not modality_available or candidate.imaging_domain_relation == "wrong_modality":
        status, rank = WRONG_MODALITY, 99
    elif candidate.file_inventory_status not in {"exact", "record_metadata_verified"}:
        status, rank = METADATA_RESOLUTION, 10
    elif exact_target:
        status, rank = ANNOTATION_PILOT, 20
    elif candidate.target_material_relation == "related_cobalt_phase":
        status, rank = CROSS_PHASE, 40
    else:
        status, rank = CROSS_MATERIAL, 60

    return {
        "candidate_id": candidate.candidate_id,
        "priority_rank": rank,
        "repository": candidate.repository,
        "doi": candidate.doi,
        "record_url": candidate.record_url,
        "title": candidate.title,
        "materials": " | ".join(candidate.materials),
        "modalities": " | ".join(candidate.modalities),
        "file_inventory_status": candidate.file_inventory_status,
        "file_checksums_available": candidate.file_checksums_available,
        "raw_or_lossless_tem_images_available": candidate.raw_or_lossless_tem_images_available,
        "reported_tem_file_count": (
            "" if candidate.reported_tem_file_count is None
            else candidate.reported_tem_file_count
        ),
        "independent_segmentation_labels_available": candidate.independent_segmentation_labels_available,
        "label_origin": candidate.label_origin,
        "labeler_count": "" if candidate.labeler_count is None else candidate.labeler_count,
        "immutable_sample_ids_available": candidate.immutable_sample_ids_available,
        "immutable_acquisition_ids_available": candidate.immutable_acquisition_ids_available,
        "verified_not_used_for_target_training_or_model_selection": candidate.verified_not_used_for_target_training_or_model_selection,
        "target_creator_name_overlap": candidate.target_creator_name_overlap,
        "target_material_relation": candidate.target_material_relation,
        "imaging_domain_relation": candidate.imaging_domain_relation,
        "reuse_license": candidate.reuse_license,
        "reuse_license_verified": candidate.reuse_license_verified,
        "target_training_source": candidate.target_training_source,
        "in_domain_external_validation_ready": ready,
        "candidate_status": status,
        "blockers": "; ".join(blockers) if blockers else "none",
        "source_evidence": " | ".join(candidate.source_evidence),
        "next_validation_step": candidate.next_validation_step,
    }


def _counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    statuses = [str(row["candidate_status"]) for row in rows]
    return {
        "candidate_count": len(rows),
        "in_domain_external_validation_ready_count": statuses.count(IN_DOMAIN_READY),
        "metadata_resolution_candidate_count": statuses.count(METADATA_RESOLUTION),
        "annotation_pilot_candidate_count": statuses.count(ANNOTATION_PILOT),
        "cross_phase_candidate_count": statuses.count(CROSS_PHASE),
        "diagnostic_cross_material_candidate_count": statuses.count(CROSS_MATERIAL),
        "excluded_control_count": statuses.count(TARGET_SOURCE) + statuses.count(WRONG_MODALITY),
    }


def _annotation_protocol() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "purpose": "prepare an untouched external validation set, not training data",
        "annotation_requirements": {
            "minimum_independent_blinded_labelers": 2,
            "adjudication_required": True,
            "written_label_definition_frozen_before_annotation": True,
            "labelers_blinded_to_model_predictions": True,
            "ambiguous_region_policy_predeclared": True,
        },
        "independence_requirements": {
            "immutable_sample_ids_required": True,
            "immutable_acquisition_ids_required": True,
            "sample_and_acquisition_disjoint_from_training": True,
            "not_used_for_training": True,
            "not_used_for_hyperparameter_tuning": True,
            "not_used_for_threshold_selection": True,
            "not_used_for_model_selection": True,
            "content_overlap_audit_completed_before_inference": True,
        },
        "evaluation_freeze_requirements": {
            "metrics_predeclared": True,
            "confidence_interval_method_predeclared": True,
            "exclusion_rules_predeclared": True,
            "test_manifest_checksum_frozen": True,
            "single_final_inference_run_preferred": True,
        },
        "prohibited_shortcuts": [
            "treating source-predicted masks as independent ground truth",
            "splitting patches from one parent image across train and test",
            "selecting test images after viewing model predictions",
            "silently excluding difficult or ambiguous frames",
            "reporting cross-material performance as cobalt-oxide in-domain validation",
        ],
    }


def _build_report(summary: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> str:
    counts = _mapping(summary, "result_counts")
    readiness = _mapping(summary, "readiness")
    lines = [
        "# TEM External-Validation Candidate Registry", "",
        "**Evidence conclusion:** Supported for candidate triage", "",
        f"**Result:** `{readiness['status']}`", "",
        "## Search snapshot", "",
        f"- Search date: `{summary['search_snapshot']['search_date']}`",
        f"- Public candidates assessed: {counts['candidate_count']}",
        f"- In-domain evaluation-ready candidates: {counts['in_domain_external_validation_ready_count']}",
        "", "## Ranked candidates", "",
        "| Rank | Candidate | Status | Primary blockers |",
        "|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['priority_rank']} | `{row['candidate_id']}` | "
            f"`{row['candidate_status']}` | {row['blockers']} |"
        )
    lines.extend([
        "", "## Next", "",
        f"- Candidate: `{readiness['recommended_candidate_id']}`",
        f"- Status: `{readiness['recommended_candidate_status']}`",
        f"- Action: {readiness['recommended_next_action']}",
        "", "## Scientific boundary", "",
        "This is a dated, non-exhaustive metadata search. Repository, author, or filename separation does not prove acquisition independence. No model evaluation may begin until files, lineage, independent labels, verified non-use, and the frozen protocol all pass.",
    ])
    return "\n".join(lines) + "\n"


def _manifest(
    output: Path, artifacts: list[Path], search_date: str
) -> dict[str, Any]:
    records = [
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
        "search_date": search_date,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _prepare_output(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
    return output


def _write_csv(
    path: Path, rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
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


def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateContractError(f"{context} must be an object")
    return value


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CandidateContractError(f"unknown {context} keys: {unknown}")


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CandidateContractError(f"{key} must be non-empty text")
    return value.strip()


def _https(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise CandidateContractError(f"{key} must be an https URL")
    return value


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise CandidateContractError(f"{key} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise CandidateContractError(f"{key} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise CandidateContractError(f"{key} must be a boolean")
    return value


def _optional_int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CandidateContractError(f"{key} must be null or a non-negative integer")
    return value


def _date(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CandidateContractError(f"{key} must use YYYY-MM-DD")
    return value


INVENTORY_COLUMNS = (
    "candidate_id", "priority_rank", "repository", "doi", "record_url",
    "title", "materials", "modalities", "file_inventory_status",
    "file_checksums_available", "raw_or_lossless_tem_images_available",
    "reported_tem_file_count", "independent_segmentation_labels_available",
    "label_origin", "labeler_count", "immutable_sample_ids_available",
    "immutable_acquisition_ids_available",
    "verified_not_used_for_target_training_or_model_selection",
    "target_creator_name_overlap", "target_material_relation",
    "imaging_domain_relation", "reuse_license", "reuse_license_verified",
    "target_training_source", "in_domain_external_validation_ready",
    "candidate_status", "blockers", "source_evidence", "next_validation_step",
)
