from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

CASE_ID = "saed_independent_validation_source_request"
SCHEMA_VERSION = "1.0"
REGISTRY_CASE_ID = "saed_external_validation_candidate_registry"
REGISTRY_RESULT = "no_public_candidate_ready_for_predeclared_saed_evaluation"
REQUEST_READY = "independent_saed_source_request_package_ready"
RESPONSE_READY = "candidate_response_ready_for_bounded_saed_source_verification"
RESPONSE_BLOCKED = "candidate_response_received_but_saed_source_not_ready"
NO_SOURCE = "no_candidate_saed_source_declared"

_RESPONSE_STATUSES = {"candidate_available", "referral_only", "not_available"}
_AUTHORITIES = {"data_collector", "principal_investigator", "repository_curator", "data_custodian"}
_SOURCE_TYPES = {"external_public", "private_transfer", "new_acquisition", "private_acquisition"}
_REPRESENTATIONS = {"raw_detector", "lossless_export", "rendered_figure"}
_IDENTITY_PROVENANCE = {"source_assigned", "operator_assigned_at_acquisition", "inferred"}
_REFERENCE_TYPES = {"source_assignments", "predeclared_reference_structures"}
_PLACEHOLDER = re.compile(
    r"(replace[-_/ ]?with|\bunresolved\b|\bunknown\b|\bnot provided\b|"
    r"\bnot available\b|\btbd\b|\btodo\b|^n/?a$)",
    re.IGNORECASE,
)


class SAEDSourceRequestContractError(ValueError):
    """Raised when registry evidence or a source response fails closed."""


def load_registry_bundle(registry_output: str | Path) -> dict[str, Any]:
    root = Path(registry_output)
    if not root.is_dir() or root.is_symlink():
        raise SAEDSourceRequestContractError("registry-output must be a real directory")

    files = {
        "saed_candidate_inventory.csv",
        "saed_candidate_summary.json",
        "saed_candidate_report.md",
        "saed_source_audit_protocol.json",
        "saed_candidate_artifact_manifest.json",
    }
    for name in files:
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise SAEDSourceRequestContractError(f"registry bundle is missing required file: {name}")

    manifest_path = root / "saed_candidate_artifact_manifest.json"
    manifest = _load_json(manifest_path, "registry manifest")
    _only(
        manifest,
        {"schema_version", "case_id", "software_version", "search_date", "artifact_count", "artifacts"},
        "registry manifest",
    )
    if manifest.get("case_id") != REGISTRY_CASE_ID:
        raise SAEDSourceRequestContractError("registry manifest case_id mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or manifest.get("artifact_count") != len(artifacts):
        raise SAEDSourceRequestContractError("registry manifest artifact count mismatch")

    bound: set[str] = set()
    for index, raw in enumerate(artifacts):
        item = _object(raw, f"registry artifact[{index}]")
        _only(item, {"path", "bytes", "sha256"}, f"registry artifact[{index}]")
        relative = _relative(item, "path")
        if relative in bound:
            raise SAEDSourceRequestContractError("registry manifest paths must be unique")
        bound.add(relative)
        path = root / PurePosixPath(relative)
        if not path.is_file() or path.is_symlink():
            raise SAEDSourceRequestContractError(f"registry artifact missing or unsafe: {relative}")
        if path.stat().st_size != _positive_int(item, "bytes"):
            raise SAEDSourceRequestContractError(f"registry artifact byte mismatch: {relative}")
        if _hash(path) != _sha256(item, "sha256"):
            raise SAEDSourceRequestContractError(f"registry artifact SHA-256 mismatch: {relative}")

    required_bound = files - {"saed_candidate_artifact_manifest.json"}
    missing = sorted(required_bound - bound)
    if missing:
        raise SAEDSourceRequestContractError(f"registry manifest does not bind required file: {missing[0]}")

    summary = _load_json(root / "saed_candidate_summary.json", "registry summary")
    protocol = _load_json(root / "saed_source_audit_protocol.json", "source audit protocol")
    inventory = _read_inventory(root / "saed_candidate_inventory.csv")
    if summary.get("case_id") != REGISTRY_CASE_ID:
        raise SAEDSourceRequestContractError("registry summary case_id mismatch")

    target = _object(summary.get("target_contract"), "target_contract")
    counts = _object(summary.get("result_counts"), "result_counts")
    readiness = _object(summary.get("readiness"), "readiness")
    processing = _object(summary.get("processing"), "processing")
    if readiness.get("status") != REGISTRY_RESULT:
        raise SAEDSourceRequestContractError("registry is not in the pinned fail-closed state")
    if readiness.get("public_search_supports_saed_evaluation_now") is not False:
        raise SAEDSourceRequestContractError("registry unexpectedly supports SAED evaluation")

    candidate_count = _nonnegative_int(counts, "candidate_count")
    ready_count = _nonnegative_int(counts, "dedicated_source_audit_ready_count")
    if candidate_count != len(inventory):
        raise SAEDSourceRequestContractError("registry candidate count mismatch")
    if ready_count:
        raise SAEDSourceRequestContractError("registry source-audit-ready count must be zero")
    if any(str(row.get("predeclared_external_evaluation_ready", "")).casefold() != "false" for row in inventory):
        raise SAEDSourceRequestContractError("registry inventory contains an evaluation-ready row")

    prohibited = {
        "source_arrays_downloaded_by_registry",
        "source_arrays_modified",
        "archive_members_inspected",
        "pattern_decoding_performed",
        "center_estimation_performed",
        "calibration_inferred",
        "analyzer_execution_performed",
        "phase_or_reflection_assignment_performed",
    }
    if any(processing.get(key) is not False for key in prohibited):
        raise SAEDSourceRequestContractError("registry processing boundary mismatch")

    acquisition_mode = _text(target, "acquisition_mode")
    minimum_series = _positive_int(target, "minimum_independent_pattern_series")
    if acquisition_mode != "static_selected_area_diffraction" or minimum_series < 2:
        raise SAEDSourceRequestContractError("registry target contract mismatch")
    subset = _object(protocol.get("subset_requirements"), "subset_requirements")
    if subset.get("minimum_independent_pattern_series") != minimum_series:
        raise SAEDSourceRequestContractError("source audit protocol minimum-series mismatch")

    return {
        "candidate_count": candidate_count,
        "ready_candidate_count": ready_count,
        "target_task": _text(target, "task"),
        "target_acquisition_mode": acquisition_mode,
        "minimum_independent_pattern_series": minimum_series,
        "search_date": _text(manifest, "search_date"),
        "registry_manifest_sha256": _hash(manifest_path),
    }


def build_request_package(bundle: Mapping[str, Any], output_dir: str | Path) -> dict[str, Any]:
    output, created = _prepare_output(output_dir)
    try:
        request = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "purpose": "obtain a raw or demonstrably lossless calibrated static SAED source for predeclared external validation",
            "current_evidence_state": {
                "registry_search_date": bundle["search_date"],
                "registry_manifest_sha256": bundle["registry_manifest_sha256"],
                "assessed_candidate_count": bundle["candidate_count"],
                "ready_candidate_count": bundle["ready_candidate_count"],
                "conclusion": REGISTRY_RESULT,
            },
            "target_contract": {
                "task": bundle["target_task"],
                "acquisition_mode": bundle["target_acquisition_mode"],
                "representations": ["raw_detector", "lossless_export"],
                "minimum_independent_pattern_series": bundle["minimum_independent_pattern_series"],
                "source_assigned_material_identity_required": True,
                "immutable_sample_and_acquisition_ids_required": True,
                "accelerating_voltage_required": True,
                "detector_and_pixel_metadata_required": True,
                "traceable_pattern_center_required": True,
                "traceable_reciprocal_calibration_required": True,
                "frozen_reference_protocol_required": True,
                "analyzer_development_nonuse_attestation_required": True,
            },
            "requested_evidence": [
                "authoritative respondent identity and authority basis",
                "dataset identity, version, transfer route, reuse authorization and manifest SHA-256",
                "source-assigned material, sample and acquisition identities",
                "at least two independent static SAED pattern series",
                "per-pattern path, bytes, SHA-256 and raw or lossless representation",
                "accelerating voltage, detector model and detector pixel size",
                "traceable pattern centre and reciprocal calibration",
                "source assignments or a frozen independent reference protocol",
                "analyzer-development and parameter-selection non-use attestation",
            ],
            "response_template_file": "saed_independent_source_author_response_template.json",
            "decision_boundary": {
                "message_sent_by_software": False,
                "source_download_authorized": False,
                "saed_analyzer_execution_authorized": False,
                "center_or_calibration_inference_authorized": False,
                "parameter_selection_authorized": False,
                "phase_or_reflection_indexing_authorized": False,
                "external_performance_claim_authorized": False,
            },
        }
        summary = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "status": REQUEST_READY,
            "request_ready_for_correspondence": True,
            "message_sent": False,
            "source_download_authorized": False,
            "bounded_source_verification_ready": False,
            "saed_validation_intake_ready": False,
            "external_evaluation_ready": False,
            "recommended_next_action": "Send the correspondence and JSON template to an authoritative source holder, then assess the completed response before any transfer.",
        }
        paths = [
            output / "saed_independent_source_request.json",
            output / "saed_independent_source_author_response_template.json",
            output / "saed_independent_source_correspondence.md",
            output / "saed_independent_source_request_summary.json",
        ]
        _write_json(paths[0], request)
        _write_json(paths[1], _response_template(int(bundle["minimum_independent_pattern_series"])))
        paths[2].write_text(_correspondence(bundle), encoding="utf-8")
        _write_json(paths[3], summary)
        _write_json(output / "saed_independent_source_request_manifest.json", _artifact_manifest(output, paths))
        return summary
    except Exception:
        _cleanup_output(output, created)
        raise


def assess_author_response(
    bundle: Mapping[str, Any],
    response_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    payload = _load_json(Path(response_path), "author response")
    normalized, gates, response_status = _validate_response(
        payload, int(bundle["minimum_independent_pattern_series"])
    )
    blockers = [name for name, passed in gates.items() if not passed]
    ready = response_status == "candidate_available" and not blockers
    status = RESPONSE_READY if ready else RESPONSE_BLOCKED if response_status == "candidate_available" else NO_SOURCE

    assessment = {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "status": status,
        "response_contract_valid": True,
        "response_status": response_status,
        "evidence_gates": gates,
        "source_blockers": blockers,
        "source_download_authorized": False,
        "ready_for_bounded_source_verification": ready,
        "saed_validation_intake_ready": False,
        "external_evaluation_ready": False,
        "saed_analyzer_execution_authorized": False,
        "phase_or_reflection_indexing_authorized": False,
        "recommended_next_action": (
            "Independently verify only the declared checksum-bound files and metadata before constructing a SAED intake manifest."
            if ready
            else "Contact the declared referral without downloading or analyzing any source."
            if response_status == "referral_only"
            else "Resolve the listed source blockers or obtain a different source; do not download or analyze data."
        ),
        "scientific_closeout": {
            "status": "Diagnostic" if ready else "Inconclusive",
            "strongest_evidence": "An authoritative declaration was assessed against explicit acquisition, representation, lineage, instrument, centre, calibration, checksum, reference-freeze and non-use gates.",
            "primary_limitation": (
                "Declared files and metadata have not been independently transferred and checksum-verified."
                if ready
                else "No declaration satisfied every source-readiness gate."
            ),
            "not_suitable_for": [
                "SAED analyzer execution",
                "center, calibration or parameter selection",
                "phase, reflection or zone-axis indexing",
                "external performance claims",
                "engineering release",
            ],
        },
    }

    output, created = _prepare_output(output_dir)
    try:
        paths = [
            output / "saed_independent_source_author_response_normalized.json",
            output / "saed_independent_source_response_assessment.json",
            output / "saed_independent_source_response_assessment.md",
        ]
        _write_json(paths[0], normalized)
        _write_json(paths[1], assessment)
        paths[2].write_text(_assessment_markdown(assessment), encoding="utf-8")
        if ready:
            candidate = _object(normalized.get("candidate"), "candidate")
            plan_path = output / "saed_bounded_source_verification_plan.json"
            _write_json(
                plan_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "case_id": CASE_ID,
                    "status": "bounded_saed_source_verification_plan_draft",
                    "dataset_id": candidate["dataset_id"],
                    "dataset_version": candidate["dataset_version"],
                    "collection_manifest_sha256": candidate["collection_manifest_sha256"],
                    "declared_patterns": [
                        {key: pattern[key] for key in ("pattern_id", "relative_path", "bytes", "sha256", "sample_id", "acquisition_id")}
                        for pattern in candidate["patterns"]
                    ],
                    "source_download_authorized": False,
                    "saed_validation_intake_ready": False,
                    "external_evaluation_ready": False,
                    "required_next_checks": [
                        "obtain explicit human authorization for the transfer route",
                        "transfer only the declared pattern files",
                        "verify bytes and SHA-256 independently",
                        "verify detector, voltage, centre and calibration metadata against source records",
                        "verify sample and acquisition independence",
                        "freeze the analysis and reference protocol before analyzer execution",
                        "construct the existing SAED external-validation intake manifest",
                    ],
                },
            )
            paths.append(plan_path)
        _write_json(output / "saed_independent_source_response_manifest.json", _artifact_manifest(output, paths))
        return assessment
    except Exception:
        _cleanup_output(output, created)
        raise


def _validate_response(payload: Mapping[str, Any], minimum_series: int) -> tuple[dict[str, Any], dict[str, bool], str]:
    _only(
        payload,
        {"schema_version", "request_case_id", "response_status", "respondent", "candidate", "referrals", "notes"},
        "author response",
    )
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("request_case_id") != CASE_ID:
        raise SAEDSourceRequestContractError("response contract identity mismatch")
    response_status = _text(payload, "response_status")
    if response_status not in _RESPONSE_STATUSES:
        raise SAEDSourceRequestContractError(f"unsupported response_status: {response_status}")

    respondent = _respondent(payload.get("respondent"))
    referrals = _referrals(payload.get("referrals"))
    if response_status == "candidate_available":
        if referrals:
            raise SAEDSourceRequestContractError("candidate_available must not also declare referrals")
        candidate = _candidate(payload.get("candidate"), minimum_series)
        gates = _candidate_gates(candidate, respondent, minimum_series)
    else:
        if payload.get("candidate") is not None:
            raise SAEDSourceRequestContractError("non-candidate response must set candidate to null")
        if response_status == "referral_only" and not referrals:
            raise SAEDSourceRequestContractError("referral_only requires at least one referral")
        if response_status == "not_available" and referrals:
            raise SAEDSourceRequestContractError("not_available must not declare referrals")
        candidate = None
        gates = {"authoritative_response": respondent["authority"] in _AUTHORITIES}
    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        raise SAEDSourceRequestContractError("notes must be a string")
    return {
        "schema_version": SCHEMA_VERSION,
        "request_case_id": CASE_ID,
        "response_status": response_status,
        "respondent": respondent,
        "candidate": candidate,
        "referrals": referrals,
        "notes": notes.strip(),
    }, gates, response_status


def _respondent(value: Any) -> dict[str, str]:
    item = _object(value, "respondent")
    _only(item, {"name", "affiliation", "email", "authority", "authority_basis"}, "respondent")
    authority = _text(item, "authority")
    if authority not in _AUTHORITIES:
        raise SAEDSourceRequestContractError(f"unsupported respondent authority: {authority}")
    return {
        "name": _text(item, "name"),
        "affiliation": _text(item, "affiliation"),
        "email": _email(item, "email"),
        "authority": authority,
        "authority_basis": _text(item, "authority_basis"),
    }


def _referrals(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SAEDSourceRequestContractError("referrals must be a list")
    result = []
    for index, raw in enumerate(value):
        item = _object(raw, f"referrals[{index}]")
        _only(item, {"name", "affiliation", "email", "reason"}, f"referrals[{index}]")
        result.append({
            "name": _text(item, "name"),
            "affiliation": _text(item, "affiliation"),
            "email": _email(item, "email"),
            "reason": _text(item, "reason"),
        })
    return result


def _candidate(value: Any, minimum_series: int) -> dict[str, Any]:
    item = _object(value, "candidate")
    fields = {
        "dataset_id", "dataset_version", "source_type", "source_url", "transfer_route",
        "reuse_license", "reuse_authorization_basis", "collection_manifest_sha256",
        "material_identity", "composition", "preparation_history", "acquisition_mode", "accelerating_voltage_kv",
        "detector_model", "detector_pixel_size_um", "pattern_center_method",
        "pattern_center_source", "reciprocal_calibration_nm_inv_per_pixel",
        "reciprocal_calibration_source", "reference_protocol_id", "reference_type",
        "reference_identifiers", "reference_frozen_before_analyzer_execution",
        "analyzer_development_nonuse_attested", "patterns",
    }
    _only(item, fields, "candidate")
    source_type = _text(item, "source_type")
    if source_type not in _SOURCE_TYPES:
        raise SAEDSourceRequestContractError(f"unsupported source_type: {source_type}")
    acquisition_mode = _text(item, "acquisition_mode")
    if acquisition_mode != "static_selected_area_diffraction":
        raise SAEDSourceRequestContractError("candidate acquisition_mode must be static_selected_area_diffraction")
    reference_type = _text(item, "reference_type")
    if reference_type not in _REFERENCE_TYPES:
        raise SAEDSourceRequestContractError(f"unsupported reference_type: {reference_type}")
    patterns = _patterns(item.get("patterns"))
    if len(patterns) < minimum_series:
        raise SAEDSourceRequestContractError(f"candidate must declare at least {minimum_series} patterns")
    return {
        "dataset_id": _text(item, "dataset_id"),
        "dataset_version": _text(item, "dataset_version"),
        "source_type": source_type,
        "source_url": _https(item, "source_url"),
        "transfer_route": _text(item, "transfer_route"),
        "reuse_license": _text(item, "reuse_license"),
        "reuse_authorization_basis": _text(item, "reuse_authorization_basis"),
        "collection_manifest_sha256": _sha256(item, "collection_manifest_sha256"),
        "material_identity": _text(item, "material_identity"),
        "composition": _text(item, "composition"),
        "preparation_history": _text(item, "preparation_history"),
        "acquisition_mode": acquisition_mode,
        "accelerating_voltage_kv": _positive_number(item, "accelerating_voltage_kv"),
        "detector_model": _text(item, "detector_model"),
        "detector_pixel_size_um": _positive_number(item, "detector_pixel_size_um"),
        "pattern_center_method": _text(item, "pattern_center_method"),
        "pattern_center_source": _text(item, "pattern_center_source"),
        "reciprocal_calibration_nm_inv_per_pixel": _positive_number(item, "reciprocal_calibration_nm_inv_per_pixel"),
        "reciprocal_calibration_source": _text(item, "reciprocal_calibration_source"),
        "reference_protocol_id": _text(item, "reference_protocol_id"),
        "reference_type": reference_type,
        "reference_identifiers": _text_list(item, "reference_identifiers"),
        "reference_frozen_before_analyzer_execution": _boolean(item, "reference_frozen_before_analyzer_execution"),
        "analyzer_development_nonuse_attested": _boolean(item, "analyzer_development_nonuse_attested"),
        "patterns": patterns,
    }


def _patterns(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise SAEDSourceRequestContractError("candidate patterns must be a non-empty list")
    result = []
    ids: set[str] = set()
    paths: set[str] = set()
    acquisitions: set[str] = set()
    fields = {
        "pattern_id", "relative_path", "bytes", "sha256", "representation",
        "original_intensity_preserved", "sample_id", "sample_identity_provenance",
        "acquisition_id", "acquisition_identity_provenance", "pattern_center_x_px",
        "pattern_center_y_px",
    }
    for index, raw in enumerate(value):
        item = _object(raw, f"patterns[{index}]")
        _only(item, fields, f"patterns[{index}]")
        pattern_id = _text(item, "pattern_id")
        relative_path = _relative(item, "relative_path")
        acquisition_id = _text(item, "acquisition_id")
        representation = _text(item, "representation")
        sample_provenance = _text(item, "sample_identity_provenance")
        acquisition_provenance = _text(item, "acquisition_identity_provenance")
        if representation not in _REPRESENTATIONS:
            raise SAEDSourceRequestContractError(f"unsupported representation: {representation}")
        if sample_provenance not in _IDENTITY_PROVENANCE or acquisition_provenance not in _IDENTITY_PROVENANCE:
            raise SAEDSourceRequestContractError("unsupported identity provenance")
        if pattern_id in ids or relative_path in paths:
            raise SAEDSourceRequestContractError("pattern IDs and paths must be unique")
        if acquisition_id in acquisitions:
            raise SAEDSourceRequestContractError("acquisition_id values must be unique for independent patterns")
        ids.add(pattern_id)
        paths.add(relative_path)
        acquisitions.add(acquisition_id)
        result.append({
            "pattern_id": pattern_id,
            "relative_path": relative_path,
            "bytes": _positive_int(item, "bytes"),
            "sha256": _sha256(item, "sha256"),
            "representation": representation,
            "original_intensity_preserved": _boolean(item, "original_intensity_preserved"),
            "sample_id": _text(item, "sample_id"),
            "sample_identity_provenance": sample_provenance,
            "acquisition_id": acquisition_id,
            "acquisition_identity_provenance": acquisition_provenance,
            "pattern_center_x_px": _nonnegative_number(item, "pattern_center_x_px"),
            "pattern_center_y_px": _nonnegative_number(item, "pattern_center_y_px"),
        })
    return result


def _candidate_gates(
    candidate: Mapping[str, Any],
    respondent: Mapping[str, Any],
    minimum_series: int,
) -> dict[str, bool]:
    patterns = candidate["patterns"]
    allowed_identity = {"source_assigned", "operator_assigned_at_acquisition"}
    return {
        "authoritative_response": respondent["authority"] in _AUTHORITIES,
        "reuse_authorization_declared": bool(candidate["reuse_license"] and candidate["reuse_authorization_basis"]),
        "static_saed_acquisition_mode": candidate["acquisition_mode"] == "static_selected_area_diffraction",
        "minimum_independent_patterns": len(patterns) >= minimum_series,
        "raw_or_lossless_representations": all(p["representation"] in {"raw_detector", "lossless_export"} for p in patterns),
        "original_detector_intensity_preserved": all(p["original_intensity_preserved"] for p in patterns),
        "source_assigned_sample_identity": all(p["sample_identity_provenance"] in allowed_identity for p in patterns),
        "source_assigned_acquisition_identity": all(p["acquisition_identity_provenance"] in allowed_identity for p in patterns),
        "independent_acquisitions": len({p["acquisition_id"] for p in patterns}) == len(patterns),
        "accelerating_voltage_declared": candidate["accelerating_voltage_kv"] > 0,
        "detector_metadata_declared": bool(candidate["detector_model"] and candidate["detector_pixel_size_um"] > 0),
        "traceable_pattern_center": bool(candidate["pattern_center_method"] and candidate["pattern_center_source"]),
        "traceable_reciprocal_calibration": bool(
            candidate["reciprocal_calibration_nm_inv_per_pixel"] > 0
            and candidate["reciprocal_calibration_source"]
        ),
        "frozen_reference_protocol": bool(
            candidate["reference_frozen_before_analyzer_execution"]
            and candidate["reference_protocol_id"]
            and candidate["reference_identifiers"]
        ),
        "analyzer_development_nonuse_attested": candidate["analyzer_development_nonuse_attested"],
        "checksum_bound_pattern_inventory": all(p["bytes"] > 0 and len(p["sha256"]) == 64 for p in patterns),
    }


def _response_template(minimum_series: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_case_id": CASE_ID,
        "response_status": "candidate_available",
        "respondent": {
            "name": "REPLACE_WITH_NAME",
            "affiliation": "REPLACE_WITH_AFFILIATION",
            "email": "replace@example.org",
            "authority": "data_collector",
            "authority_basis": "REPLACE_WITH_AUTHORITY_BASIS",
        },
        "candidate": {
            "dataset_id": "REPLACE_WITH_DATASET_ID",
            "dataset_version": "REPLACE_WITH_VERSION",
            "source_type": "external_public",
            "source_url": "https://example.org/record",
            "transfer_route": "REPLACE_WITH_TRANSFER_ROUTE",
            "reuse_license": "REPLACE_WITH_LICENSE",
            "reuse_authorization_basis": "REPLACE_WITH_AUTHORIZATION_BASIS",
            "collection_manifest_sha256": "0" * 64,
            "material_identity": "REPLACE_WITH_SOURCE_ASSIGNED_MATERIAL",
            "composition": "REPLACE_WITH_COMPOSITION",
            "preparation_history": "REPLACE_WITH_PREPARATION_HISTORY",
            "acquisition_mode": "static_selected_area_diffraction",
            "accelerating_voltage_kv": 200.0,
            "detector_model": "REPLACE_WITH_DETECTOR_MODEL",
            "detector_pixel_size_um": 15.0,
            "pattern_center_method": "REPLACE_WITH_CENTER_METHOD",
            "pattern_center_source": "REPLACE_WITH_CENTER_SOURCE",
            "reciprocal_calibration_nm_inv_per_pixel": 0.01,
            "reciprocal_calibration_source": "REPLACE_WITH_CALIBRATION_SOURCE",
            "reference_protocol_id": "REPLACE_WITH_FROZEN_PROTOCOL_ID",
            "reference_type": "predeclared_reference_structures",
            "reference_identifiers": ["REPLACE_WITH_REFERENCE_IDENTIFIER"],
            "reference_frozen_before_analyzer_execution": True,
            "analyzer_development_nonuse_attested": False,
            "patterns": [
                {
                    "pattern_id": f"REPLACE_WITH_PATTERN_{i + 1}_ID",
                    "relative_path": f"patterns/pattern_{i + 1}.tif",
                    "bytes": 1,
                    "sha256": "0" * 64,
                    "representation": "lossless_export",
                    "original_intensity_preserved": False,
                    "sample_id": f"REPLACE_WITH_SAMPLE_{i + 1}_ID",
                    "sample_identity_provenance": "source_assigned",
                    "acquisition_id": f"REPLACE_WITH_ACQUISITION_{i + 1}_ID",
                    "acquisition_identity_provenance": "source_assigned",
                    "pattern_center_x_px": 0.0,
                    "pattern_center_y_px": 0.0,
                }
                for i in range(minimum_series)
            ],
        },
        "referrals": [],
        "notes": "",
    }


def _correspondence(bundle: Mapping[str, Any]) -> str:
    return f"""# SAED independent validation source correspondence

## Suggested subject

Request for checksum-bound raw or lossless calibrated static SAED data

## Suggested message

A dated public-source registry assessed {bundle["candidate_count"]} candidates and found no source ready for predeclared static-SAED evaluation.

Could you provide or refer us to a source with at least `{bundle["minimum_independent_pattern_series"]}` independent static SAED pattern series and authoritative metadata covering source-assigned material/sample/acquisition identity, raw or lossless intensity-preserving files, stable version and reuse authorization, byte sizes and SHA-256 values, accelerating voltage, detector and pixel metadata, a traceable pattern centre, reciprocal calibration, a frozen reference protocol, and analyzer-development non-use?

Please complete `saed_independent_source_author_response_template.json`.

This request does not authorize a download, analyzer execution, centre or calibration inference, parameter tuning, crystallographic indexing, or a performance claim.
"""


def _assessment_markdown(assessment: Mapping[str, Any]) -> str:
    blockers = assessment["source_blockers"]
    lines = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- None at declaration assessment."
    return f"""# SAED independent source response assessment

- Status: `{assessment["status"]}`
- Ready for bounded source verification: `{str(assessment["ready_for_bounded_source_verification"]).lower()}`
- Source download authorized: `false`
- SAED validation intake ready: `false`
- External evaluation ready: `false`

## Declaration-stage blockers

{lines}

A complete declaration remains diagnostic only. Source bytes, checksums, acquisition independence, detector metadata, centre, reciprocal calibration and the reference protocol still require independent verification.
"""


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output must be absent or an empty directory")
        return output, False
    output.mkdir(parents=True)
    return output, True


def _cleanup_output(output: Path, created: bool) -> None:
    if created:
        shutil.rmtree(output, ignore_errors=True)
    elif output.is_dir():
        for child in output.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() and not child.is_symlink() else child.unlink(missing_ok=True)


def _artifact_manifest(output: Path, paths: Sequence[Path]) -> dict[str, Any]:
    records = sorted(
        (
            {"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": _hash(path)}
            for path in paths
        ),
        key=lambda item: item["path"],
    )
    return {"schema_version": SCHEMA_VERSION, "case_id": CASE_ID, "artifact_count": len(records), "artifacts": records}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_inventory(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise SAEDSourceRequestContractError(f"could not read registry inventory: {path}") from exc


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise SAEDSourceRequestContractError(f"{label} must be a regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise SAEDSourceRequestContractError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise SAEDSourceRequestContractError(f"{label} root must be an object")
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SAEDSourceRequestContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _only(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SAEDSourceRequestContractError(f"{label} contains unknown field: {unknown[0]}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SAEDSourceRequestContractError(f"{label} must be an object")
    return dict(value)


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SAEDSourceRequestContractError(f"{key} must be a non-empty string")
    value = value.strip()
    if _PLACEHOLDER.search(value):
        raise SAEDSourceRequestContractError(f"{key} contains unresolved placeholder text")
    return value


def _text_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise SAEDSourceRequestContractError(f"{key} must be a non-empty list")
    return [_text({"item": item}, "item") for item in value]


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise SAEDSourceRequestContractError(f"{key} must be boolean")
    return value


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SAEDSourceRequestContractError(f"{key} must be a positive integer")
    return value


def _nonnegative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SAEDSourceRequestContractError(f"{key} must be a non-negative integer")
    return value


def _positive_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise SAEDSourceRequestContractError(f"{key} must be a positive number")
    return float(value)


def _nonnegative_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
        raise SAEDSourceRequestContractError(f"{key} must be a non-negative number")
    return float(value)


def _email(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise SAEDSourceRequestContractError(f"{key} must be a valid email address")
    return value


def _https(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise SAEDSourceRequestContractError(f"{key} must use https://")
    return value


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SAEDSourceRequestContractError(f"{key} must be a 64-character SHA-256")
    return value


def _relative(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "\\" in value or pure.as_posix() != value:
        raise SAEDSourceRequestContractError(f"{key} must be a safe normalized relative POSIX path")
    return value


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or assess a fail-closed independent SAED source request.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--registry-output", required=True)
    build.add_argument("--output", required=True)
    assess = subparsers.add_parser("assess")
    assess.add_argument("--registry-output", required=True)
    assess.add_argument("--response", required=True)
    assess.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bundle = load_registry_bundle(args.registry_output)
    result = build_request_package(bundle, args.output) if args.command == "build" else assess_author_response(bundle, args.response, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
