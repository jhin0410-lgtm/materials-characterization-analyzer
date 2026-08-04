from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

CASE_ID = "tem_independent_validation_source_request"
SCHEMA_VERSION = "1.0"
REGISTRY_CASE_ID = "tem_external_validation_candidate_registry"
REGISTRY_RESULT = "no_public_candidate_ready_for_in_domain_external_validation"

REQUEST_READY = "independent_source_request_package_ready"
RESPONSE_READY = "candidate_response_ready_for_bounded_source_verification"
RESPONSE_BLOCKED = "candidate_response_received_but_source_not_ready"
NO_SOURCE = "no_candidate_source_declared"

_RESPONSE_STATUSES = {"candidate_available", "referral_only", "not_available"}
_AUTHORITIES = {"data_collector", "principal_investigator", "repository_curator", "data_custodian"}
_SOURCE_TYPES = {"external_public", "private_transfer", "new_acquisition", "private_acquisition"}
_MODALITIES = {"TEM", "HRTEM"}
_REPRESENTATIONS = {"raw_detector", "lossless_export", "rendered_figure"}
_IDENTITY_PROVENANCE = {"source_assigned", "operator_assigned_at_acquisition", "inferred"}
_PURITY_SCOPES = {"pure_cobalt_oxide", "mixed_or_composite", "unknown"}

_PLACEHOLDER_PATTERNS = (
    r"replace[-_/ ]?with",
    r"^replace[-_/ ]",
    r"\bunresolved\b",
    r"\bunknown\b",
    r"\bnot provided\b",
    r"\bnot available\b",
    r"\btbd\b",
    r"\btodo\b",
    r"^n/?a$",
)


class SourceRequestContractError(ValueError):
    """Raised when registry evidence or an author response fails closed."""


def load_registry_bundle(registry_output: str | Path) -> dict[str, Any]:
    root = Path(registry_output)
    if not root.is_dir() or root.is_symlink():
        raise SourceRequestContractError("registry-output must be a real directory")

    names = {
        "tem_external_validation_candidate_inventory.csv",
        "tem_external_validation_candidate_summary.json",
        "tem_external_validation_candidate_report.md",
        "tem_external_validation_annotation_protocol.json",
        "tem_external_validation_candidate_manifest.json",
    }
    for name in sorted(names):
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise SourceRequestContractError(f"registry bundle is missing required file: {name}")

    manifest_path = root / "tem_external_validation_candidate_manifest.json"
    manifest = _load_json(manifest_path, "registry manifest")
    _reject_unknown(
        manifest,
        {"schema_version", "case_id", "software_version", "search_date", "artifact_count", "artifacts"},
        "registry manifest",
    )
    if manifest.get("case_id") != REGISTRY_CASE_ID:
        raise SourceRequestContractError("registry manifest case_id mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SourceRequestContractError("registry manifest artifacts must be non-empty")
    if manifest.get("artifact_count") != len(artifacts):
        raise SourceRequestContractError("registry manifest artifact_count mismatch")

    bound: set[str] = set()
    for index, raw in enumerate(artifacts):
        item = _mapping_value(raw, f"registry artifact[{index}]")
        _reject_unknown(item, {"path", "bytes", "sha256"}, f"registry artifact[{index}]")
        relative = _relative_path(item, "path")
        if relative in bound:
            raise SourceRequestContractError("registry manifest paths must be unique")
        bound.add(relative)
        path = root / PurePosixPath(relative)
        if not path.is_file() or path.is_symlink():
            raise SourceRequestContractError(f"registry artifact missing or unsafe: {relative}")
        if path.stat().st_size != _positive_int(item, "bytes"):
            raise SourceRequestContractError(f"registry artifact byte mismatch: {relative}")
        if _hash_file(path) != _sha256(item, "sha256"):
            raise SourceRequestContractError(f"registry artifact SHA-256 mismatch: {relative}")

    required_bound = names - {"tem_external_validation_candidate_manifest.json"}
    missing_bound = sorted(required_bound - bound)
    if missing_bound:
        raise SourceRequestContractError(
            f"registry manifest does not bind required file: {missing_bound[0]}"
        )

    summary = _load_json(
        root / "tem_external_validation_candidate_summary.json", "registry summary"
    )
    protocol = _load_json(
        root / "tem_external_validation_annotation_protocol.json", "annotation protocol"
    )
    inventory = _read_inventory(
        root / "tem_external_validation_candidate_inventory.csv"
    )

    if summary.get("case_id") != REGISTRY_CASE_ID:
        raise SourceRequestContractError("registry summary case_id mismatch")
    target = _mapping(summary, "target_contract")
    counts = _mapping(summary, "result_counts")
    readiness = _mapping(summary, "readiness")
    processing = _mapping(summary, "processing")
    if readiness.get("status") != REGISTRY_RESULT:
        raise SourceRequestContractError("registry is not in the pinned fail-closed state")
    if readiness.get("independent_in_domain_external_validation_available") is not False:
        raise SourceRequestContractError("registry unexpectedly reports a ready candidate")

    candidate_count = _nonnegative_int(counts, "candidate_count")
    ready_count = _nonnegative_int(counts, "in_domain_external_validation_ready_count")
    if candidate_count != len(inventory):
        raise SourceRequestContractError("registry candidate count mismatch")
    if ready_count != 0:
        raise SourceRequestContractError("registry ready-candidate count must be zero")
    for row in inventory:
        if str(row.get("evaluation_ready", "")).casefold() != "false":
            raise SourceRequestContractError("registry inventory contains an evaluation-ready row")

    prohibited = {
        "source_arrays_downloaded_by_registry",
        "source_arrays_modified",
        "labels_created",
        "model_training_performed",
        "model_inference_performed",
        "segmentation_metrics_computed",
    }
    if any(processing.get(key) is not False for key in prohibited):
        raise SourceRequestContractError("registry processing boundary mismatch")

    modalities = target.get("modalities")
    if modalities != ["TEM", "HRTEM"]:
        raise SourceRequestContractError("registry target modalities mismatch")
    creators = target.get("target_training_creators")
    if not isinstance(creators, list) or not all(
        isinstance(value, str) and value.strip() for value in creators
    ):
        raise SourceRequestContractError("target training creators must be a list of names")

    annotation_requirements = _mapping(protocol, "annotation_requirements")
    if annotation_requirements.get("minimum_independent_blinded_labelers") != 2:
        raise SourceRequestContractError("annotation protocol labeler minimum mismatch")

    return {
        "candidate_count": candidate_count,
        "ready_candidate_count": ready_count,
        "target_task": _text(target, "task"),
        "target_material": _text(target, "material"),
        "target_modalities": list(modalities),
        "target_training_creators": [str(value).strip() for value in creators],
        "search_date": _text(manifest, "search_date"),
        "registry_manifest_sha256": _hash_file(manifest_path),
    }


def build_request_package(bundle: Mapping[str, Any], output_dir: str | Path) -> dict[str, Any]:
    output, created = _prepare_output(output_dir)
    try:
        request = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "purpose": "obtain an independent raw or lossless cobalt-oxide TEM/HRTEM source for a blinded external-validation workflow",
            "current_evidence_state": {
                "registry_search_date": bundle["search_date"],
                "registry_manifest_sha256": bundle["registry_manifest_sha256"],
                "assessed_candidate_count": bundle["candidate_count"],
                "ready_candidate_count": bundle["ready_candidate_count"],
                "conclusion": REGISTRY_RESULT,
            },
            "target_contract": {
                "task": bundle["target_task"],
                "material": bundle["target_material"],
                "modalities": bundle["target_modalities"],
                "representations": ["raw_detector", "lossless_export"],
                "minimum_independent_samples": 2,
                "minimum_independent_acquisitions": 2,
                "pixel_calibration_required": True,
                "immutable_sample_and_acquisition_ids_required": True,
                "target_training_nonuse_attestation_required": True,
                "creator_disjointness_required": True,
                "independent_labels_required_before_evaluation": True,
            },
            "requested_evidence": [
                "authoritative respondent identity and authority basis",
                "dataset identifier, version, transfer route, manifest SHA-256, and reuse authorization",
                "composition, phase, purity scope, preparation and processing history",
                "creator list and target-training creator overlap declaration",
                "at least two source-assigned samples and two acquisitions",
                "per-image path, bytes, SHA-256, modality, representation, detector and instrument metadata",
                "per-image pixel calibration and calibration source",
                "attestation that no image was used for training, threshold selection, hyperparameter tuning or model selection",
                "available label provenance, while preserving blinded annotation requirements",
            ],
            "response_template_file": "tem_independent_source_author_response_template.json",
            "decision_boundary": {
                "email_sent_by_software": False,
                "source_download_authorized": False,
                "model_inference_authorized": False,
                "model_retraining_authorized": False,
                "parameter_selection_authorized": False,
                "external_performance_claim_authorized": False,
            },
        }
        template = _response_template()
        summary = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "status": REQUEST_READY,
            "request_ready_for_correspondence": True,
            "email_sent": False,
            "source_download_authorized": False,
            "bounded_source_verification_ready": False,
            "tem_validation_intake_ready": False,
            "external_evaluation_ready": False,
            "recommended_next_action": "Send the correspondence and JSON template to an authoritative independent data collector, custodian, curator or principal investigator, then assess the completed response before any transfer.",
        }
        request_path = output / "tem_independent_source_request.json"
        template_path = output / "tem_independent_source_author_response_template.json"
        correspondence_path = output / "tem_independent_source_correspondence.md"
        summary_path = output / "tem_independent_source_request_summary.json"
        manifest_path = output / "tem_independent_source_request_manifest.json"
        _write_json(request_path, request)
        _write_json(template_path, template)
        correspondence_path.write_text(_correspondence(bundle), encoding="utf-8")
        _write_json(summary_path, summary)
        _write_json(
            manifest_path,
            _artifact_manifest(output, [request_path, template_path, correspondence_path, summary_path]),
        )
        return summary
    except Exception:
        _cleanup_output(output, created)
        raise


def assess_author_response(
    bundle: Mapping[str, Any], response_path: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    payload = _load_json(Path(response_path), "author response")
    normalized, gates, source_status = _validate_response(bundle, payload)
    blockers = [name for name, passed in gates.items() if not passed]
    ready = source_status == "candidate_available" and not blockers
    status = RESPONSE_READY if ready else (RESPONSE_BLOCKED if source_status == "candidate_available" else NO_SOURCE)

    output, created = _prepare_output(output_dir)
    try:
        assessment: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "status": status,
            "response_contract_valid": True,
            "response_status": source_status,
            "evidence_gates": gates,
            "source_blockers": blockers,
            "source_download_authorized": False,
            "ready_for_bounded_source_verification": ready,
            "tem_validation_intake_ready": False,
            "external_evaluation_ready": False,
            "model_inference_authorized": False,
            "model_retraining_authorized": False,
            "recommended_next_action": (
                "Independently verify only the declared checksum-bound files and metadata before constructing a TEM intake manifest."
                if ready
                else (
                    "Contact the declared referral without downloading or analyzing any source."
                    if source_status == "referral_only"
                    else "Resolve the listed source blockers or obtain a different independent source; do not download or analyze data."
                )
            ),
            "scientific_closeout": {
                "status": "Diagnostic" if ready else "Inconclusive",
                "strongest_evidence": "A structurally valid authoritative source declaration was assessed against explicit material, modality, representation, lineage, calibration, checksum, creator-disjointness and non-use gates.",
                "primary_limitation": (
                    "Declared files and metadata have not yet been independently transferred and checksum-verified."
                    if ready
                    else "No candidate declaration satisfied every source-readiness gate."
                ),
                "not_suitable_for": [
                    "TEM segmentation inference",
                    "model retraining or parameter selection",
                    "external performance claims",
                    "engineering release",
                ],
            },
        }
        normalized_path = output / "tem_independent_source_author_response_normalized.json"
        assessment_path = output / "tem_independent_source_response_assessment.json"
        report_path = output / "tem_independent_source_response_assessment.md"
        plan_path = output / "tem_bounded_source_verification_plan.json"
        manifest_path = output / "tem_independent_source_response_manifest.json"
        _write_json(normalized_path, normalized)
        _write_json(assessment_path, assessment)
        report_path.write_text(_assessment_markdown(assessment), encoding="utf-8")
        artifacts = [normalized_path, assessment_path, report_path]
        if ready:
            candidate = _mapping(normalized, "candidate")
            plan = {
                "schema_version": SCHEMA_VERSION,
                "case_id": CASE_ID,
                "status": "bounded_source_verification_plan_draft",
                "dataset_id": candidate["dataset_id"],
                "dataset_version": candidate["dataset_version"],
                "collection_manifest_sha256": candidate["collection_manifest_sha256"],
                "declared_files": [
                    {
                        "image_id": image["image_id"],
                        "relative_path": image["relative_path"],
                        "bytes": image["bytes"],
                        "sha256": image["sha256"],
                    }
                    for image in candidate["images"]
                ],
                "source_download_authorized": False,
                "tem_validation_intake_ready": False,
                "external_evaluation_ready": False,
                "required_next_checks": [
                    "obtain explicit human authorization for the transfer route",
                    "transfer only declared files",
                    "verify bytes and SHA-256 independently",
                    "verify microscopy metadata and calibration against source records",
                    "run content-overlap and target-development non-use audits",
                    "construct the existing TEM external-validation intake manifest",
                ],
            }
            _write_json(plan_path, plan)
            artifacts.append(plan_path)
        _write_json(manifest_path, _artifact_manifest(output, artifacts))
        return assessment
    except Exception:
        _cleanup_output(output, created)
        raise


def _validate_response(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, bool], str]:
    _reject_unknown(
        payload,
        {"schema_version", "request_case_id", "response_status", "respondent", "candidate", "referrals", "notes"},
        "author response",
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SourceRequestContractError("response schema_version mismatch")
    if payload.get("request_case_id") != CASE_ID:
        raise SourceRequestContractError("response request_case_id mismatch")
    response_status = _text(payload, "response_status")
    if response_status not in _RESPONSE_STATUSES:
        raise SourceRequestContractError(f"unsupported response_status: {response_status}")
    respondent = _validate_respondent(_mapping(payload, "respondent"))
    referrals = _validate_referrals(payload.get("referrals"))
    notes = _optional_text(payload.get("notes"), "notes")

    candidate_raw = payload.get("candidate")
    if response_status != "candidate_available":
        if candidate_raw is not None:
            raise SourceRequestContractError("non-candidate response must set candidate to null")
        if response_status == "referral_only" and not referrals:
            raise SourceRequestContractError("referral_only response requires at least one referral")
        normalized = {
            "schema_version": SCHEMA_VERSION,
            "request_case_id": CASE_ID,
            "response_status": response_status,
            "respondent": respondent,
            "candidate": None,
            "referrals": referrals,
            "notes": notes,
        }
        return normalized, {}, response_status

    if referrals:
        raise SourceRequestContractError("candidate_available response must not include referrals")
    candidate = _validate_candidate(_mapping_value(candidate_raw, "candidate"))
    gates = _candidate_gates(bundle, respondent, candidate)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "request_case_id": CASE_ID,
        "response_status": response_status,
        "respondent": respondent,
        "candidate": candidate,
        "referrals": [],
        "notes": notes,
    }
    return normalized, gates, response_status


def _validate_respondent(payload: Mapping[str, Any]) -> dict[str, Any]:
    _reject_unknown(payload, {"name", "affiliation", "email", "authority", "authority_basis"}, "respondent")
    authority = _text(payload, "authority")
    if authority not in _AUTHORITIES:
        raise SourceRequestContractError(f"unsupported respondent authority: {authority}")
    return {
        "name": _resolved_text(payload, "name"),
        "affiliation": _resolved_text(payload, "affiliation"),
        "email": _email(payload, "email"),
        "authority": authority,
        "authority_basis": _resolved_text(payload, "authority_basis"),
    }


def _validate_referrals(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SourceRequestContractError("referrals must be a list")
    output: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        item = _mapping_value(raw, f"referrals[{index}]")
        _reject_unknown(item, {"name", "affiliation", "email", "reason"}, f"referrals[{index}]")
        output.append(
            {
                "name": _resolved_text(item, "name"),
                "affiliation": _resolved_text(item, "affiliation"),
                "email": _email(item, "email"),
                "reason": _resolved_text(item, "reason"),
            }
        )
    return output


def _validate_candidate(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "dataset_id", "dataset_version", "source_type", "repository_or_transfer_method",
        "persistent_identifier", "collection_manifest_sha256", "license", "reuse_authorized",
        "material", "creator_names", "target_creator_overlap", "target_training_nonuse_attested",
        "cross_dataset_lineage_independence_attested", "images", "labels",
    }
    _reject_unknown(payload, allowed, "candidate")
    source_type = _text(payload, "source_type")
    if source_type not in _SOURCE_TYPES:
        raise SourceRequestContractError(f"unsupported source_type: {source_type}")
    creators_raw = payload.get("creator_names")
    if not isinstance(creators_raw, list) or not creators_raw:
        raise SourceRequestContractError("creator_names must be a non-empty list")
    creators = [_resolved_string(value, f"creator_names[{index}]") for index, value in enumerate(creators_raw)]
    images_raw = payload.get("images")
    if not isinstance(images_raw, list) or not images_raw:
        raise SourceRequestContractError("images must be a non-empty list")
    images = [_validate_image(_mapping_value(raw, f"images[{index}]"), index) for index, raw in enumerate(images_raw)]
    image_ids = [image["image_id"] for image in images]
    image_paths = [image["relative_path"] for image in images]
    if len(set(image_ids)) != len(image_ids):
        raise SourceRequestContractError("image_id values must be unique")
    if len(set(image_paths)) != len(image_paths):
        raise SourceRequestContractError("image relative paths must be unique")
    return {
        "dataset_id": _identifier(payload, "dataset_id"),
        "dataset_version": _resolved_text(payload, "dataset_version"),
        "source_type": source_type,
        "repository_or_transfer_method": _resolved_text(payload, "repository_or_transfer_method"),
        "persistent_identifier": _resolved_text(payload, "persistent_identifier"),
        "collection_manifest_sha256": _sha256(payload, "collection_manifest_sha256"),
        "license": _resolved_text(payload, "license"),
        "reuse_authorized": _boolean(payload, "reuse_authorized"),
        "material": _validate_material(_mapping(payload, "material")),
        "creator_names": creators,
        "target_creator_overlap": _boolean(payload, "target_creator_overlap"),
        "target_training_nonuse_attested": _boolean(payload, "target_training_nonuse_attested"),
        "cross_dataset_lineage_independence_attested": _boolean(payload, "cross_dataset_lineage_independence_attested"),
        "images": images,
        "labels": _validate_labels(_mapping(payload, "labels")),
    }


def _validate_material(payload: Mapping[str, Any]) -> dict[str, str]:
    _reject_unknown(payload, {"composition", "phase", "purity_scope", "processing_history", "comparability_notes"}, "material")
    purity = _text(payload, "purity_scope")
    if purity not in _PURITY_SCOPES:
        raise SourceRequestContractError(f"unsupported purity_scope: {purity}")
    return {
        "composition": _resolved_text(payload, "composition"),
        "phase": _resolved_text(payload, "phase"),
        "purity_scope": purity,
        "processing_history": _resolved_text(payload, "processing_history"),
        "comparability_notes": _resolved_text(payload, "comparability_notes"),
    }


def _validate_image(payload: Mapping[str, Any], index: int) -> dict[str, Any]:
    allowed = {
        "image_id", "relative_path", "bytes", "sha256", "sample_id", "acquisition_id",
        "identity_provenance", "modality", "representation", "original_detector_intensity_available",
        "instrument", "detector", "accelerating_voltage_kv", "nm_per_pixel", "calibration_source",
        "acquisition_date", "acquisition_conditions", "used_for_training", "used_for_threshold_selection",
        "used_for_hyperparameter_tuning", "used_for_model_selection",
    }
    _reject_unknown(payload, allowed, f"images[{index}]")
    identity = _text(payload, "identity_provenance")
    if identity not in _IDENTITY_PROVENANCE:
        raise SourceRequestContractError(f"unsupported identity_provenance: {identity}")
    modality = _text(payload, "modality")
    if modality not in _MODALITIES:
        raise SourceRequestContractError(f"unsupported modality: {modality}")
    representation = _text(payload, "representation")
    if representation not in _REPRESENTATIONS:
        raise SourceRequestContractError(f"unsupported representation: {representation}")
    voltage = _positive_number(payload, "accelerating_voltage_kv")
    nm_per_pixel = _positive_number(payload, "nm_per_pixel")
    date = _resolved_text(payload, "acquisition_date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SourceRequestContractError("acquisition_date must use YYYY-MM-DD")
    return {
        "image_id": _identifier(payload, "image_id"),
        "relative_path": _relative_path(payload, "relative_path"),
        "bytes": _positive_int(payload, "bytes"),
        "sha256": _sha256(payload, "sha256"),
        "sample_id": _identifier(payload, "sample_id"),
        "acquisition_id": _identifier(payload, "acquisition_id"),
        "identity_provenance": identity,
        "modality": modality,
        "representation": representation,
        "original_detector_intensity_available": _boolean(payload, "original_detector_intensity_available"),
        "instrument": _resolved_text(payload, "instrument"),
        "detector": _resolved_text(payload, "detector"),
        "accelerating_voltage_kv": voltage,
        "nm_per_pixel": nm_per_pixel,
        "calibration_source": _resolved_text(payload, "calibration_source"),
        "acquisition_date": date,
        "acquisition_conditions": _resolved_text(payload, "acquisition_conditions"),
        "used_for_training": _boolean(payload, "used_for_training"),
        "used_for_threshold_selection": _boolean(payload, "used_for_threshold_selection"),
        "used_for_hyperparameter_tuning": _boolean(payload, "used_for_hyperparameter_tuning"),
        "used_for_model_selection": _boolean(payload, "used_for_model_selection"),
    }


def _validate_labels(payload: Mapping[str, Any]) -> dict[str, Any]:
    _reject_unknown(
        payload,
        {"available", "label_definition_version", "independent_labeler_count", "blinded_to_model_predictions", "adjudicated_consensus_available", "file_manifest_sha256"},
        "labels",
    )
    available = _boolean(payload, "available")
    version = _optional_resolved_text(payload.get("label_definition_version"), "label_definition_version")
    count = _nonnegative_int(payload, "independent_labeler_count")
    blinded = _boolean(payload, "blinded_to_model_predictions")
    consensus = _boolean(payload, "adjudicated_consensus_available")
    file_hash = _optional_sha256(payload.get("file_manifest_sha256"), "file_manifest_sha256")
    if not available and any((version is not None, count != 0, blinded, consensus, file_hash is not None)):
        raise SourceRequestContractError("unavailable labels must not declare label artifacts")
    if available and (version is None or file_hash is None):
        raise SourceRequestContractError("available labels require definition version and manifest SHA-256")
    return {
        "available": available,
        "label_definition_version": version,
        "independent_labeler_count": count,
        "blinded_to_model_predictions": blinded,
        "adjudicated_consensus_available": consensus,
        "file_manifest_sha256": file_hash,
    }


def _candidate_gates(
    bundle: Mapping[str, Any], respondent: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, bool]:
    images = candidate["images"]
    target_creators = {_normalize_name(value) for value in bundle["target_training_creators"]}
    declared_creators = {_normalize_name(value) for value in candidate["creator_names"]}
    model_nonuse = all(
        not any(
            image[key]
            for key in (
                "used_for_training",
                "used_for_threshold_selection",
                "used_for_hyperparameter_tuning",
                "used_for_model_selection",
            )
        )
        for image in images
    )
    return {
        "authoritative_respondent": respondent["authority"] in _AUTHORITIES,
        "reuse_authorized": candidate["reuse_authorized"],
        "pure_cobalt_oxide_scope": candidate["material"]["purity_scope"] == "pure_cobalt_oxide",
        "target_creator_disjoint": not candidate["target_creator_overlap"] and target_creators.isdisjoint(declared_creators),
        "target_training_nonuse_attested": candidate["target_training_nonuse_attested"],
        "cross_dataset_lineage_independence_attested": candidate["cross_dataset_lineage_independence_attested"],
        "minimum_two_independent_samples": len({image["sample_id"] for image in images}) >= 2,
        "minimum_two_independent_acquisitions": len({image["acquisition_id"] for image in images}) >= 2,
        "source_assigned_or_acquisition_assigned_identity": all(image["identity_provenance"] != "inferred" for image in images),
        "target_tem_or_hrtem_modality": all(image["modality"] in _MODALITIES for image in images),
        "raw_or_lossless_representation": all(image["representation"] in {"raw_detector", "lossless_export"} for image in images),
        "original_detector_intensity_available": all(image["original_detector_intensity_available"] for image in images),
        "pixel_calibration_declared": all(image["nm_per_pixel"] > 0 and bool(image["calibration_source"]) for image in images),
        "per_file_checksums_declared": all(image["bytes"] > 0 and len(image["sha256"]) == 64 for image in images),
        "no_target_model_development_use": model_nonuse,
    }


def _response_template() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_case_id": CASE_ID,
        "response_status": "not_available",
        "respondent": {
            "name": "replace-with-name",
            "affiliation": "replace-with-affiliation",
            "email": "replace-with-email@example.org",
            "authority": "data_custodian",
            "authority_basis": "replace-with-authority-basis",
        },
        "candidate": None,
        "referrals": [],
        "notes": "No eligible independent candidate is currently available.",
    }


def _correspondence(bundle: Mapping[str, Any]) -> str:
    creators = ", ".join(bundle["target_training_creators"])
    return f"""# Independent cobalt-oxide TEM/HRTEM source request

**Suggested subject:** Request for independent raw/lossless cobalt-oxide TEM/HRTEM data and provenance

We are preparing a strictly separated external-validation workflow for `{bundle['target_task']}`. A checksum-bound public-source audit assessed `{bundle['candidate_count']}` candidates and found no source currently ready for independent evaluation.

We are seeking an eligible dataset containing at least `2` independent samples and at least `2` independent acquisitions of cobalt oxide, acquired as TEM or HRTEM and retained as raw detector data or a demonstrably lossless export.

Please complete the attached JSON template with:

- authoritative respondent and reuse authority;
- dataset identity, version, transfer route, collection-manifest SHA-256 and reuse terms;
- composition, phase, purity and processing history;
- source-assigned sample and acquisition identifiers;
- per-image path, bytes, SHA-256, modality, representation, instrument, detector and pixel calibration;
- confirmation that the source was not used for training, threshold selection, hyperparameter tuning or model selection;
- creator names so they can be compared against the target-training creators: {creators}.

The request does not authorize a download, annotation, model inference, retraining, parameter selection or a performance claim. A completed response only permits a separate bounded checksum-verification decision.
"""


def _assessment_markdown(assessment: Mapping[str, Any]) -> str:
    blockers = assessment["source_blockers"]
    lines = [
        "# Independent TEM source response assessment",
        "",
        f"**Status:** `{assessment['status']}`",
        "",
        f"**Ready for bounded source verification:** `{assessment['ready_for_bounded_source_verification']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{value}`" for value in blockers) if blockers else lines.append("- none")
    lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            "No download, TEM intake, model inference, retraining, parameter selection, external performance claim or engineering release is authorized by this assessment.",
        ]
    )
    return "\n".join(lines) + "\n"


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    created = False
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
        created = True
    return output, created


def _cleanup_output(output: Path, created: bool) -> None:
    if created:
        shutil.rmtree(output, ignore_errors=True)
    elif output.is_dir():
        for child in output.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)


def _artifact_manifest(output: Path, paths: Sequence[Path]) -> dict[str, Any]:
    artifacts = [
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
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def _load_json(path: Path, context: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise SourceRequestContractError(f"{context} must be a real file")

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise SourceRequestContractError(f"duplicate JSON key in {context}: {key}")
            output[key] = value
        return output

    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    except SourceRequestContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceRequestContractError(f"invalid {context}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceRequestContractError(f"{context} must contain a JSON object")
    return payload


def _read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not rows[0].keys():
        raise SourceRequestContractError("candidate inventory must be non-empty")
    required = {"candidate_id", "evaluation_ready"}
    if not required.issubset(rows[0]):
        raise SourceRequestContractError("candidate inventory is missing required columns")
    return rows


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _mapping_value(payload.get(key), key)


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SourceRequestContractError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SourceRequestContractError(f"{key} must be non-empty text")
    return value.strip()


def _resolved_text(payload: Mapping[str, Any], key: str) -> str:
    return _resolved_string(_text(payload, key), key)


def _resolved_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceRequestContractError(f"{context} must be non-empty text")
    text = value.strip()
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _PLACEHOLDER_PATTERNS):
        raise SourceRequestContractError(f"{context} contains unresolved placeholder text")
    return text


def _optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SourceRequestContractError(f"{context} must be null or non-empty text")
    return value.strip()


def _optional_resolved_text(value: Any, context: str) -> str | None:
    text = _optional_text(value, context)
    return None if text is None else _resolved_string(text, context)


def _email(payload: Mapping[str, Any], key: str) -> str:
    value = _resolved_text(payload, key)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise SourceRequestContractError(f"{key} must be a valid email address")
    return value


def _identifier(payload: Mapping[str, Any], key: str) -> str:
    value = _resolved_text(payload, key)
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
        raise SourceRequestContractError(f"{key} contains unsupported characters")
    return value


def _relative_path(payload: Mapping[str, Any], key: str) -> str:
    value = _resolved_text(payload, key)
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise SourceRequestContractError(f"{key} must be a safe relative POSIX path")
    if "\\" in value or value != pure.as_posix():
        raise SourceRequestContractError(f"{key} must be a normalized POSIX path")
    return value


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SourceRequestContractError(f"{key} must be a SHA-256 hex digest")
    return value


def _optional_sha256(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise SourceRequestContractError(f"{context} must be null or a SHA-256 hex digest")
    return value.casefold()


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise SourceRequestContractError(f"{key} must be a boolean")
    return value


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SourceRequestContractError(f"{key} must be a positive integer")
    return value


def _nonnegative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourceRequestContractError(f"{key} must be a non-negative integer")
    return value


def _positive_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0 < float(value) < float("inf")):
        raise SourceRequestContractError(f"{key} must be a finite positive number")
    return float(value)


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SourceRequestContractError(f"unknown {context} keys: {unknown}")


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a send-ready request package")
    build.add_argument("--registry-output", required=True)
    build.add_argument("--output", required=True)
    assess = sub.add_parser("assess", help="assess an authoritative source response")
    assess.add_argument("--registry-output", required=True)
    assess.add_argument("--response", required=True)
    assess.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bundle = load_registry_bundle(args.registry_output)
    if args.command == "build":
        result = build_request_package(bundle, args.output)
    else:
        result = assess_author_response(bundle, args.response, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
