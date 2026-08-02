"""Fail-closed registry for public SAED external-validation candidates.

The registry evaluates pinned repository metadata only. It does not download
or decode diffraction arrays, inspect archive members, estimate a pattern
centre, infer calibration, run the SAED analyzer, or perform indexing.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import __version__

CASE_ID = "saed_external_validation_candidate_registry"
SCHEMA_VERSION = "1.0"
RESULT = "no_public_candidate_ready_for_predeclared_saed_evaluation"
READY_RESULT = "public_candidate_ready_for_dedicated_saed_source_audit"

READY = "ready_for_dedicated_saed_source_audit"
CALIBRATION_RESOLUTION = "calibration_or_center_resolution_required"
METADATA_RESOLUTION = "metadata_or_file_inventory_resolution_required"
MODE_SHIFT = "diagnostic_3ded_or_microed_mode_shift"
ARCHIVED = "source_unavailable_or_archived"
RENDERED = "excluded_rendered_or_software_example"

SUPPORTED_TARGET_TASK = (
    "external validation of static selected-area electron diffraction pattern "
    "detection and calibrated d-spacing support"
)
SUPPORTED_ACQUISITION_MODE = "static_selected_area_diffraction"

_ACQUISITION_MODES = {
    "static_selected_area_diffraction",
    "continuous_rotation_3ded",
    "microed_rotation_series",
    "software_or_rendered_example",
    "unknown",
}
_FILE_INVENTORY_STATUSES = {
    "exact",
    "record_metadata_verified",
    "unresolved",
    "archived",
}
_RESOLVED_INVENTORIES = {"exact", "record_metadata_verified"}

INVENTORY_COLUMNS = (
    "candidate_id",
    "priority_rank",
    "candidate_status",
    "repository",
    "doi",
    "record_url",
    "title",
    "materials",
    "acquisition_mode",
    "file_inventory_status",
    "files_publicly_downloadable",
    "file_checksums_available",
    "raw_or_lossless_patterns_available",
    "reported_pattern_series_count",
    "immutable_sample_ids_available",
    "immutable_acquisition_ids_available",
    "accelerating_voltage_available",
    "detector_metadata_available",
    "detector_pixel_size_available",
    "pattern_center_traceable",
    "reciprocal_calibration_traceable",
    "source_reference_assignments_available",
    "independent_reference_structures_available",
    "reuse_license",
    "reuse_license_verified",
    "analyzer_development_nonuse_verified",
    "dedicated_source_audit_ready",
    "predeclared_external_evaluation_ready",
    "blockers",
    "source_evidence",
    "next_validation_step",
)


class SAEDCandidateContractError(ValueError):
    """Raised when a candidate-registry contract fails closed."""


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    repository: str
    doi: str
    record_url: str
    title: str
    materials: tuple[str, ...]
    acquisition_mode: str
    file_inventory_status: str
    files_publicly_downloadable: bool
    file_checksums_available: bool
    raw_or_lossless_patterns_available: bool
    reported_pattern_series_count: int | None
    immutable_sample_ids_available: bool
    immutable_acquisition_ids_available: bool
    accelerating_voltage_available: bool
    detector_metadata_available: bool
    detector_pixel_size_available: bool
    pattern_center_traceable: bool
    reciprocal_calibration_traceable: bool
    source_reference_assignments_available: bool
    independent_reference_structures_available: bool
    reuse_license: str
    reuse_license_verified: bool
    analyzer_development_nonuse_verified: bool
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
            "acquisition_mode",
            "file_inventory_status",
            "files_publicly_downloadable",
            "file_checksums_available",
            "raw_or_lossless_patterns_available",
            "reported_pattern_series_count",
            "immutable_sample_ids_available",
            "immutable_acquisition_ids_available",
            "accelerating_voltage_available",
            "detector_metadata_available",
            "detector_pixel_size_available",
            "pattern_center_traceable",
            "reciprocal_calibration_traceable",
            "source_reference_assignments_available",
            "independent_reference_structures_available",
            "reuse_license",
            "reuse_license_verified",
            "analyzer_development_nonuse_verified",
            "source_evidence",
            "next_validation_step",
        }
        _reject_unknown(payload, allowed, f"candidates[{index}]")
        candidate = cls(
            candidate_id=_identifier(payload, "candidate_id"),
            repository=_text(payload, "repository"),
            doi=_text(payload, "doi"),
            record_url=_https(payload, "record_url"),
            title=_text(payload, "title"),
            materials=_texts(payload, "materials"),
            acquisition_mode=_text(payload, "acquisition_mode"),
            file_inventory_status=_text(payload, "file_inventory_status"),
            files_publicly_downloadable=_boolean(
                payload, "files_publicly_downloadable"
            ),
            file_checksums_available=_boolean(
                payload, "file_checksums_available"
            ),
            raw_or_lossless_patterns_available=_boolean(
                payload, "raw_or_lossless_patterns_available"
            ),
            reported_pattern_series_count=_optional_integer(
                payload.get("reported_pattern_series_count"),
                "reported_pattern_series_count",
            ),
            immutable_sample_ids_available=_boolean(
                payload, "immutable_sample_ids_available"
            ),
            immutable_acquisition_ids_available=_boolean(
                payload, "immutable_acquisition_ids_available"
            ),
            accelerating_voltage_available=_boolean(
                payload, "accelerating_voltage_available"
            ),
            detector_metadata_available=_boolean(
                payload, "detector_metadata_available"
            ),
            detector_pixel_size_available=_boolean(
                payload, "detector_pixel_size_available"
            ),
            pattern_center_traceable=_boolean(
                payload, "pattern_center_traceable"
            ),
            reciprocal_calibration_traceable=_boolean(
                payload, "reciprocal_calibration_traceable"
            ),
            source_reference_assignments_available=_boolean(
                payload, "source_reference_assignments_available"
            ),
            independent_reference_structures_available=_boolean(
                payload, "independent_reference_structures_available"
            ),
            reuse_license=_text(payload, "reuse_license"),
            reuse_license_verified=_boolean(payload, "reuse_license_verified"),
            analyzer_development_nonuse_verified=_boolean(
                payload, "analyzer_development_nonuse_verified"
            ),
            source_evidence=_texts(payload, "source_evidence"),
            next_validation_step=_text(payload, "next_validation_step"),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        if self.acquisition_mode not in _ACQUISITION_MODES:
            raise SAEDCandidateContractError(
                f"unsupported acquisition_mode for {self.candidate_id}"
            )
        if self.file_inventory_status not in _FILE_INVENTORY_STATUSES:
            raise SAEDCandidateContractError(
                f"unsupported file_inventory_status for {self.candidate_id}"
            )
        if self.file_inventory_status == "archived" and self.files_publicly_downloadable:
            raise SAEDCandidateContractError(
                f"{self.candidate_id} cannot be archived and downloadable"
            )
        if (
            self.reported_pattern_series_count is not None
            and self.reported_pattern_series_count < 0
        ):
            raise SAEDCandidateContractError(
                f"{self.candidate_id} has a negative pattern-series count"
            )
        if (
            self.reported_pattern_series_count == 0
            and self.raw_or_lossless_patterns_available
        ):
            raise SAEDCandidateContractError(
                f"{self.candidate_id} reports raw patterns but zero series"
            )
        if self.detector_pixel_size_available and not self.detector_metadata_available:
            raise SAEDCandidateContractError(
                f"{self.candidate_id} reports pixel size without detector metadata"
            )


@dataclass(frozen=True)
class RegistryConfig:
    case_id: str
    search_date: str
    repositories_searched: tuple[str, ...]
    search_terms: tuple[str, ...]
    target_task: str
    target_acquisition_mode: str
    minimum_independent_pattern_series: int
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
            {"task", "acquisition_mode", "minimum_independent_pattern_series"},
            "target_contract",
        )
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise SAEDCandidateContractError("candidates must be a non-empty list")
        config = cls(
            case_id=_text(payload, "case_id"),
            search_date=_date(snapshot, "search_date"),
            repositories_searched=_texts(snapshot, "repositories_searched"),
            search_terms=_texts(snapshot, "search_terms"),
            target_task=_text(target, "task"),
            target_acquisition_mode=_text(target, "acquisition_mode"),
            minimum_independent_pattern_series=_integer(
                target, "minimum_independent_pattern_series"
            ),
            candidates=tuple(
                Candidate.from_mapping(
                    _mapping_value(item, f"candidates[{index}]"), index
                )
                for index, item in enumerate(raw_candidates)
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise SAEDCandidateContractError(
                f"case_id mismatch: {self.case_id!r} != {CASE_ID!r}"
            )
        if self.target_task != SUPPORTED_TARGET_TASK:
            raise SAEDCandidateContractError(
                f"unsupported target task: {self.target_task!r}"
            )
        if self.target_acquisition_mode != SUPPORTED_ACQUISITION_MODE:
            raise SAEDCandidateContractError(
                "target acquisition mode must be static selected-area diffraction"
            )
        if self.minimum_independent_pattern_series < 2:
            raise SAEDCandidateContractError(
                "minimum_independent_pattern_series must be at least 2"
            )
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise SAEDCandidateContractError("candidate_id values must be unique")
        if not any(
            item.acquisition_mode == SUPPORTED_ACQUISITION_MODE
            for item in self.candidates
        ):
            raise SAEDCandidateContractError(
                "registry must include at least one static SAED candidate"
            )


def load_registry_config(path: str | Path) -> RegistryConfig:
    config_path = Path(path)
    try:
        payload = json.loads(
            config_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SAEDCandidateContractError(
            f"could not read SAED candidate registry config: {config_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise SAEDCandidateContractError("registry config root must be an object")
    return RegistryConfig.from_mapping(payload)


def run_candidate_registry(
    config: RegistryConfig, output_dir: str | Path
) -> dict[str, Any]:
    output, created_output = _prepare_output(output_dir)
    try:
        rows = [
            _candidate_row(
                candidate,
                minimum_series=config.minimum_independent_pattern_series,
            )
            for candidate in config.candidates
        ]
        rows.sort(
            key=lambda row: (int(row["priority_rank"]), str(row["candidate_id"]))
        )
        counts = _counts(rows)
        recommended = _recommendation(rows)
        ready_available = counts["dedicated_source_audit_ready_count"] > 0
        result = READY_RESULT if ready_available else RESULT
        protocol = _source_audit_protocol(
            config.minimum_independent_pattern_series
        )
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
                "acquisition_mode": config.target_acquisition_mode,
                "minimum_independent_pattern_series": (
                    config.minimum_independent_pattern_series
                ),
            },
            "result_counts": counts,
            "readiness": {
                "status": result,
                "candidate_search_completed_for_snapshot": True,
                "search_is_globally_exhaustive": False,
                "public_candidate_ready_for_dedicated_source_audit": (
                    ready_available
                ),
                "public_search_supports_saed_evaluation_now": False,
                "recommended_candidate_id": recommended["candidate_id"],
                "recommended_candidate_status": recommended["candidate_status"],
                "recommended_next_action": recommended["next_validation_step"],
                "analyzer_execution_is_current_priority": False,
                "phase_or_reflection_indexing_is_current_priority": False,
            },
            "source_audit_protocol": protocol,
            "processing": {
                "source_arrays_downloaded_by_registry": False,
                "source_arrays_modified": False,
                "archive_members_inspected": False,
                "pattern_decoding_performed": False,
                "center_estimation_performed": False,
                "calibration_inferred": False,
                "analyzer_execution_performed": False,
                "phase_or_reflection_assignment_performed": False,
            },
            "scientific_closeout": {
                "status": "Supported",
                "result": result,
                "strongest_evidence": (
                    f"{len(rows)} public records were classified against explicit "
                    "downloadability, representation, acquisition-mode, sample and "
                    "acquisition identity, detector, centre, calibration, reference, "
                    "reuse, non-use, and minimum-series gates."
                ),
                "primary_limitation": (
                    "No pinned candidate currently combines a publicly downloadable "
                    "static SAED cohort with immutable sample and acquisition identities, "
                    "traceable centre and reciprocal calibration, suitable references, "
                    "and verified analyzer-development non-use."
                ),
                "evidence_that_would_change_conclusion": (
                    "A checksum-bound subset of at least two independent static SAED "
                    "pattern series whose source documentation resolves sample and "
                    "acquisition lineage, detector metadata, centre, reciprocal "
                    "calibration, reuse rights, and reference protocol."
                ),
                "suitable_for": [
                    "public source triage",
                    "candidate exclusion documentation",
                    "planning metadata requests and bounded downloads",
                ],
                "not_suitable_for": [
                    "SAED analyzer execution",
                    "parameter selection",
                    "reflection or phase indexing",
                    "crystallographic performance claims",
                    "engineering release",
                ],
            },
        }

        inventory_path = output / "saed_candidate_inventory.csv"
        summary_path = output / "saed_candidate_summary.json"
        report_path = output / "saed_candidate_report.md"
        protocol_path = output / "saed_source_audit_protocol.json"
        manifest_path = output / "saed_candidate_artifact_manifest.json"
        _write_csv(inventory_path, rows, INVENTORY_COLUMNS)
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary, rows), encoding="utf-8")
        _write_json(protocol_path, protocol)
        _write_json(
            manifest_path,
            _artifact_manifest(
                output,
                [inventory_path, summary_path, report_path, protocol_path],
                config.search_date,
            ),
        )
        return summary
    except Exception:
        _cleanup_failed_output(output, created_output)
        raise


def _candidate_row(
    candidate: Candidate, *, minimum_series: int
) -> dict[str, Any]:
    static_mode = candidate.acquisition_mode == SUPPORTED_ACQUISITION_MODE
    resolved_inventory = candidate.file_inventory_status in _RESOLVED_INVENTORIES
    enough_series = (
        candidate.reported_pattern_series_count is not None
        and candidate.reported_pattern_series_count >= minimum_series
    )
    reference_available = (
        candidate.source_reference_assignments_available
        or candidate.independent_reference_structures_available
    )
    dedicated_source_audit_ready = all(
        (
            static_mode,
            resolved_inventory,
            candidate.files_publicly_downloadable,
            candidate.file_checksums_available,
            candidate.raw_or_lossless_patterns_available,
            enough_series,
            candidate.immutable_sample_ids_available,
            candidate.immutable_acquisition_ids_available,
            candidate.accelerating_voltage_available,
            candidate.detector_metadata_available,
            candidate.pattern_center_traceable,
            candidate.reciprocal_calibration_traceable,
            reference_available,
            candidate.reuse_license_verified,
            candidate.analyzer_development_nonuse_verified,
        )
    )

    blockers: list[str] = []
    checks = (
        (static_mode, "static_selected_area_diffraction_mode_unavailable"),
        (resolved_inventory, "exact_file_inventory_unresolved"),
        (candidate.files_publicly_downloadable, "source_files_not_publicly_downloadable"),
        (candidate.file_checksums_available, "file_checksums_unavailable"),
        (candidate.raw_or_lossless_patterns_available, "raw_or_lossless_patterns_unavailable"),
        (enough_series, "minimum_independent_pattern_series_unresolved"),
        (candidate.immutable_sample_ids_available, "immutable_sample_ids_unavailable"),
        (candidate.immutable_acquisition_ids_available, "immutable_acquisition_ids_unavailable"),
        (candidate.accelerating_voltage_available, "accelerating_voltage_unavailable"),
        (candidate.detector_metadata_available, "detector_metadata_unavailable"),

        (candidate.pattern_center_traceable, "pattern_center_untraceable"),
        (candidate.reciprocal_calibration_traceable, "reciprocal_calibration_untraceable"),
        (reference_available, "reference_assignments_or_structures_unavailable"),
        (candidate.reuse_license_verified, "reuse_license_unverified"),
        (candidate.analyzer_development_nonuse_verified, "analyzer_development_nonuse_unverified"),
    )
    blockers.extend(message for passed, message in checks if not passed)

    if dedicated_source_audit_ready:
        status, rank = READY, 1
    elif not candidate.files_publicly_downloadable or (
        candidate.file_inventory_status == "archived"
    ):
        status, rank = ARCHIVED, 60
    elif not candidate.raw_or_lossless_patterns_available or (
        candidate.acquisition_mode == "software_or_rendered_example"
    ):
        status, rank = RENDERED, 70
    elif not static_mode:
        status, rank = MODE_SHIFT, 40
    elif not resolved_inventory:
        status, rank = METADATA_RESOLUTION, 20
    elif (
        not candidate.pattern_center_traceable
        or not candidate.reciprocal_calibration_traceable
        or not candidate.detector_metadata_available
        or not candidate.immutable_sample_ids_available
        or not candidate.immutable_acquisition_ids_available
    ):
        status, rank = CALIBRATION_RESOLUTION, 10
    else:
        status, rank = METADATA_RESOLUTION, 30

    return {
        "candidate_id": candidate.candidate_id,
        "priority_rank": rank,
        "candidate_status": status,
        "repository": candidate.repository,
        "doi": candidate.doi,
        "record_url": candidate.record_url,
        "title": candidate.title,
        "materials": " | ".join(candidate.materials),
        "acquisition_mode": candidate.acquisition_mode,
        "file_inventory_status": candidate.file_inventory_status,
        "files_publicly_downloadable": candidate.files_publicly_downloadable,
        "file_checksums_available": candidate.file_checksums_available,
        "raw_or_lossless_patterns_available": candidate.raw_or_lossless_patterns_available,
        "reported_pattern_series_count": candidate.reported_pattern_series_count,
        "immutable_sample_ids_available": candidate.immutable_sample_ids_available,
        "immutable_acquisition_ids_available": candidate.immutable_acquisition_ids_available,
        "accelerating_voltage_available": candidate.accelerating_voltage_available,
        "detector_metadata_available": candidate.detector_metadata_available,
        "detector_pixel_size_available": candidate.detector_pixel_size_available,
        "pattern_center_traceable": candidate.pattern_center_traceable,
        "reciprocal_calibration_traceable": candidate.reciprocal_calibration_traceable,
        "source_reference_assignments_available": candidate.source_reference_assignments_available,
        "independent_reference_structures_available": candidate.independent_reference_structures_available,
        "reuse_license": candidate.reuse_license,
        "reuse_license_verified": candidate.reuse_license_verified,
        "analyzer_development_nonuse_verified": candidate.analyzer_development_nonuse_verified,
        "dedicated_source_audit_ready": dedicated_source_audit_ready,
        "predeclared_external_evaluation_ready": False,
        "blockers": " | ".join(blockers),
        "source_evidence": " | ".join(candidate.source_evidence),
        "next_validation_step": candidate.next_validation_step,
    }


def _recommendation(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    for status in (
        READY,
        CALIBRATION_RESOLUTION,
        METADATA_RESOLUTION,
        MODE_SHIFT,
        ARCHIVED,
        RENDERED,
    ):
        matching = [row for row in rows if row["candidate_status"] == status]
        if matching:
            return min(
                matching,
                key=lambda row: (int(row["priority_rank"]), str(row["candidate_id"])),
            )
    raise SAEDCandidateContractError("registry produced no recommendation")


def _counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    def count(status: str) -> int:
        return sum(row["candidate_status"] == status for row in rows)

    return {
        "candidate_count": len(rows),
        "dedicated_source_audit_ready_count": count(READY),
        "calibration_or_center_resolution_count": count(CALIBRATION_RESOLUTION),
        "metadata_or_file_inventory_resolution_count": count(METADATA_RESOLUTION),
        "acquisition_mode_shift_diagnostic_count": count(MODE_SHIFT),
        "source_unavailable_or_archived_count": count(ARCHIVED),
        "rendered_or_software_example_exclusion_count": count(RENDERED),
    }


def _source_audit_protocol(minimum_series: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "purpose": "bounded source audit before static SAED analyzer execution",
        "subset_requirements": {
            "minimum_independent_pattern_series": minimum_series,
            "preserve_source_filenames_and_archive_member_paths": True,
            "record_archive_and_member_checksums": True,
            "immutable_sample_ids_required": True,
            "immutable_acquisition_ids_required": True,
            "raw_or_demonstrably_lossless_representation_required": True,
            "no_filename_or_visual_identity_inference": True,
        },
        "instrument_and_calibration_requirements": {
            "accelerating_voltage_required": True,
            "detector_model_required": True,
            "detector_pixel_size_required_when_relevant": True,
            "source_or_reproducible_pattern_center_required": True,
            "traceable_reciprocal_calibration_required": True,
            "preprocessing_state_required": True,
        },
        "independence_requirements": {
            "not_used_for_center_selection": True,
            "not_used_for_smoothing_selection": True,
            "not_used_for_prominence_selection": True,
            "not_used_for_radius_bound_selection": True,
            "not_used_for_candidate_count_selection": True,
            "content_overlap_audit_before_evaluation": True,
        },
        "evaluation_freeze_requirements": {
            "analysis_parameters_frozen_before_execution": True,
            "reference_set_frozen_before_execution": True,
            "indexing_protocol_frozen_before_execution": True,
            "metrics_and_uncertainty_frozen_before_execution": True,
            "exclusion_rules_frozen_before_execution": True,
            "canonical_manifest_checksum_frozen": True,
        },
        "prohibited_shortcuts": [
            "treating continuous-rotation 3DED frames as static SAED validation without a bounded mode-shift study",
            "inferring pattern centre or reciprocal calibration from analyzer output",
            "selecting files after viewing candidate detections",
            "using rendered publication figures as raw detector evidence",
            "promoting archive-level checksums to member-level identity without inspection",
        ],
    }


def _build_report(
    summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> str:
    readiness = summary["readiness"]
    counts = summary["result_counts"]
    lines = [
        "# SAED external-validation candidate registry",
        "",
        f"- Search date: `{summary['search_snapshot']['search_date']}`",
        f"- Status: `{readiness['status']}`",
        f"- Candidates assessed: `{counts['candidate_count']}`",
        f"- Dedicated source-audit ready: `{counts['dedicated_source_audit_ready_count']}`",
        f"- Recommended candidate: `{readiness['recommended_candidate_id']}`",
        f"- Recommended status: `{readiness['recommended_candidate_status']}`",
        "",
        "## Candidate decisions",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['candidate_id']} — `{row['candidate_status']}`",
                "",
                f"- DOI: `{row['doi']}`",
                f"- Acquisition mode: `{row['acquisition_mode']}`",
                f"- Blockers: `{row['blockers'] or 'none'}`",
                f"- Next action: {row['next_validation_step']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Scientific boundary",
            "",
            "The registry classifies pinned public metadata only. It does not "
            "download or decode diffraction arrays, inspect archive members, "
            "establish calibration truth, execute the analyzer, or validate "
            "phase or reflection assignments.",
            "",
        ]
    )
    return "\n".join(lines)


def _artifact_manifest(
    output: Path, paths: Sequence[Path], search_date: str
) -> dict[str, Any]:
    records = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _hash_file(path),
        }
        for path in paths
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "search_date": search_date,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    if output.exists():
        if not output.is_dir() or output.is_symlink() or any(output.iterdir()):
            raise FileExistsError("output must be an absent or empty directory")
        return output, False
    output.mkdir(parents=True)
    return output, True


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


def _write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
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
            raise SAEDCandidateContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SAEDCandidateContractError(
            f"unknown {context} field: {unknown[0]}"
        )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SAEDCandidateContractError(f"{key} must be an object")
    return value


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SAEDCandidateContractError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SAEDCandidateContractError(f"{key} must be a non-empty string")
    return value.strip()


def _identifier(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise SAEDCandidateContractError(
            f"{key} contains unsupported identifier characters"
        )
    return value


def _https(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise SAEDCandidateContractError(f"{key} must be an HTTPS URL")
    return value


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise SAEDCandidateContractError(
            f"{key} must be a non-empty string array"
        )
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SAEDCandidateContractError(
                f"{key} must contain non-empty strings"
            )
        cleaned.append(item.strip())
    if len(cleaned) != len(set(cleaned)):
        raise SAEDCandidateContractError(f"{key} must not contain duplicates")
    return tuple(cleaned)


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise SAEDCandidateContractError(f"{key} must be boolean")
    return value


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SAEDCandidateContractError(f"{key} must be an integer")
    return value


def _optional_integer(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SAEDCandidateContractError(f"{key} must be null or an integer")
    return value


def _date(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise SAEDCandidateContractError(f"{key} must be YYYY-MM-DD") from exc
    return value
