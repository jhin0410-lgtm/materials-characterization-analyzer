"""Fail-closed metadata-resolution contract for the BIR-MicroED 200 keV lead.

The contract consumes the evidence bundle produced by ``saed-bir-metadata-audit``.
It generates an author request package and assesses a returned metadata response.
It never downloads archives, opens MRC arrays, estimates a pattern centre,
infers calibration, runs the SAED analyzer, or authorizes scientific claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from . import __version__

CASE_ID = "saed_bir_200kev_metadata_resolution"
SCHEMA_VERSION = "1.0"
AUDIT_CASE_ID = "saed_bir_200kev_metadata_audit"
AUDIT_RESULT = "record_inventory_verified_but_source_not_ready_for_saed_evaluation"
EXPECTED_RECORD_ID = "10999587"
EXPECTED_DOI = "10.5281/zenodo.10999587"
EXPECTED_ARCHIVE = "AVAAGA_200kV_293K.zip"
EXPECTED_ARCHIVE_MD5 = "f800d8b28b1b93f074b8a1d7c19dc930"
EXPECTED_ARCHIVE_BYTES = 2_225_239_393
EXPECTED_MICROSCOPE = "Talos F200C"
EXPECTED_DETECTOR = "DE Apollo direct electron detector"
EXPECTED_VOLTAGE_KV = 200.0

REQUEST_READY = "metadata_resolution_request_package_ready"
RESPONSE_READY = "metadata_response_ready_for_bounded_download_verification"
RESPONSE_BLOCKED = "metadata_response_received_but_source_not_ready"

_REPRESENTATIONS = {"raw_detector", "lossless_export", "not_eligible"}
_CENTER_METHODS = {"source_coordinates", "reproducible_procedure", "unresolved"}
_CALIBRATION_METHODS = {
    "reciprocal_nm_inv_per_pixel",
    "camera_constant_nm_pixel",
    "reference_pair",
    "unresolved",
}


class BIRResolutionContractError(ValueError):
    """Raised when an audit bundle or author response fails closed."""


def load_audit_bundle(audit_output: str | Path) -> dict[str, Any]:
    root = Path(audit_output)
    if not root.is_dir() or root.is_symlink():
        raise BIRResolutionContractError("audit-output must be a real directory")

    required = {
        "bir_archive_inventory.csv",
        "bir_metadata_audit_summary.json",
        "bir_bounded_subset_plan.json",
        "bir_metadata_audit_manifest.json",
    }
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise BIRResolutionContractError(
            f"audit bundle is missing required file: {missing[0]}"
        )

    manifest = _load_json(root / "bir_metadata_audit_manifest.json", "audit manifest")
    _reject_unknown(
        manifest,
        {"schema_version", "case_id", "record_metadata_sha256", "artifact_count", "artifacts"},
        "audit manifest",
    )
    if manifest.get("case_id") != AUDIT_CASE_ID:
        raise BIRResolutionContractError("audit manifest case_id mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise BIRResolutionContractError("audit manifest artifacts must be non-empty")
    if manifest.get("artifact_count") != len(artifacts):
        raise BIRResolutionContractError("audit manifest artifact_count mismatch")

    bound_paths: set[str] = set()
    for index, raw in enumerate(artifacts):
        item = _mapping_value(raw, f"audit artifact[{index}]")
        _reject_unknown(item, {"path", "bytes", "sha256"}, f"audit artifact[{index}]")
        relative = _relative_path(item, "path")
        if relative in bound_paths:
            raise BIRResolutionContractError("audit manifest paths must be unique")
        bound_paths.add(relative)
        path = root / PurePosixPath(relative)
        if not path.is_file() or path.is_symlink():
            raise BIRResolutionContractError(f"audit artifact missing or unsafe: {relative}")
        if path.stat().st_size != _positive_int(item, "bytes"):
            raise BIRResolutionContractError(f"audit artifact byte mismatch: {relative}")
        if _hash_file(path) != _sha256(item, "sha256"):
            raise BIRResolutionContractError(f"audit artifact SHA-256 mismatch: {relative}")

    for name in required - {"bir_metadata_audit_manifest.json"}:
        if name not in bound_paths:
            raise BIRResolutionContractError(
                f"audit manifest does not bind required file: {name}"
            )

    summary = _load_json(root / "bir_metadata_audit_summary.json", "audit summary")
    plan = _load_json(root / "bir_bounded_subset_plan.json", "subset plan")
    inventory = _read_inventory(root / "bir_archive_inventory.csv")
    return _validate_audit(summary, plan, inventory, manifest)


def _validate_audit(
    summary: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if summary.get("case_id") != AUDIT_CASE_ID or summary.get("result") != AUDIT_RESULT:
        raise BIRResolutionContractError("audit summary is not the pinned BIR state")
    source = _mapping(summary, "source")
    publication = _mapping(summary, "publication_evidence")
    gates = _mapping(summary, "evidence_gates")

    if str(source.get("record_id")) != EXPECTED_RECORD_ID:
        raise BIRResolutionContractError("audit record_id mismatch")
    if str(source.get("doi", "")).casefold() != EXPECTED_DOI.casefold():
        raise BIRResolutionContractError("audit DOI mismatch")
    record_hash = _sha256(source, "record_metadata_sha256")
    if record_hash != manifest.get("record_metadata_sha256"):
        raise BIRResolutionContractError("record metadata hash is not manifest-bound")
    rights = source.get("rights")
    if not isinstance(rights, list) or not rights or not gates.get("explicit_reuse_terms_verified"):
        raise BIRResolutionContractError("explicit reuse rights are not verified")
    if any(
        gates.get(key)
        for key in (
            "ready_for_bounded_archive_download",
            "ready_for_saed_validation_intake",
            "ready_for_predeclared_external_evaluation",
        )
    ):
        raise BIRResolutionContractError("input audit unexpectedly authorizes downstream work")

    if publication.get("microscope") != EXPECTED_MICROSCOPE:
        raise BIRResolutionContractError("publication microscope mismatch")
    if publication.get("detector") != EXPECTED_DETECTOR:
        raise BIRResolutionContractError("publication detector mismatch")
    if float(publication.get("accelerating_voltage_kv", 0)) != EXPECTED_VOLTAGE_KV:
        raise BIRResolutionContractError("publication voltage mismatch")
    if publication.get("output_shape") != [2048, 2048]:
        raise BIRResolutionContractError("publication output shape mismatch")
    if str(publication.get("output_format", "")).casefold() != "mrc":
        raise BIRResolutionContractError("publication output format mismatch")

    if plan.get("selected_archive") != EXPECTED_ARCHIVE:
        raise BIRResolutionContractError("unexpected selected archive")
    if plan.get("selected_archive_bytes") != EXPECTED_ARCHIVE_BYTES:
        raise BIRResolutionContractError("selected archive byte mismatch")
    if plan.get("download_authorized_now") is not False:
        raise BIRResolutionContractError("subset plan must remain download-blocked")
    if plan.get("full_record_download_prohibited") is not True:
        raise BIRResolutionContractError("full-record download must remain prohibited")

    rows = {str(row["name"]): row for row in inventory}
    selected = rows.get(EXPECTED_ARCHIVE)
    if selected is None:
        raise BIRResolutionContractError("selected archive missing from inventory")
    if int(selected["bytes"]) != EXPECTED_ARCHIVE_BYTES:
        raise BIRResolutionContractError("inventory archive byte mismatch")
    if str(selected["md5"]).casefold() != EXPECTED_ARCHIVE_MD5:
        raise BIRResolutionContractError("inventory archive MD5 mismatch")

    return {
        "record_id": EXPECTED_RECORD_ID,
        "doi": EXPECTED_DOI,
        "record_metadata_sha256": record_hash,
        "rights": list(rights),
        "archive_name": EXPECTED_ARCHIVE,
        "archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "archive_md5": EXPECTED_ARCHIVE_MD5,
        "microscope": EXPECTED_MICROSCOPE,
        "detector": EXPECTED_DETECTOR,
        "accelerating_voltage_kv": EXPECTED_VOLTAGE_KV,
    }


def build_request_package(bundle: Mapping[str, Any], output_dir: str | Path) -> dict[str, Any]:
    output, created = _prepare_output(output_dir)
    try:
        request = _request_payload(bundle)
        template = _response_template(bundle)
        summary = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "status": REQUEST_READY,
            "request_ready_for_correspondence": True,
            "archive_download_authorized": False,
            "saed_validation_intake_ready": False,
            "predeclared_external_evaluation_ready": False,
            "recommended_next_action": (
                "Send the request to an authoritative data collector, publication author, "
                "or repository curator and assess the completed JSON response before download."
            ),
        }
        request_json = output / "bir_metadata_resolution_request.json"
        template_json = output / "bir_author_response_template.json"
        request_md = output / "bir_metadata_resolution_request.md"
        summary_json = output / "bir_metadata_resolution_summary.json"
        manifest_json = output / "bir_metadata_resolution_manifest.json"
        _write_json(request_json, request)
        _write_json(template_json, template)
        request_md.write_text(_request_markdown(bundle, request), encoding="utf-8")
        _write_json(summary_json, summary)
        _write_json(
            manifest_json,
            _artifact_manifest(output, [request_json, template_json, request_md, summary_json]),
        )
        return summary
    except Exception:
        _cleanup_output(output, created)
        raise


def assess_author_response(
    bundle: Mapping[str, Any], response_path: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    payload = _load_json(Path(response_path), "author response")
    normalized, gates = _validate_response(bundle, payload)
    blockers = [key for key, value in gates.items() if not value]
    ready = not blockers
    output, created = _prepare_output(output_dir)
    try:
        assessment: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "status": RESPONSE_READY if ready else RESPONSE_BLOCKED,
            "response_contract_valid": True,
            "evidence_gates": gates,
            "blockers": blockers,
            "archive_download_authorized": False,
            "ready_for_bounded_archive_download_and_member_verification": ready,
            "saed_validation_intake_ready": False,
            "predeclared_external_evaluation_ready": False,
            "recommended_next_action": (
                "Download only the selected checksum-bound archive and independently verify "
                "the declared member inventory before constructing an intake manifest."
                if ready
                else "Resolve the listed metadata blockers; do not download or analyze the archive."
            ),
            "scientific_closeout": {
                "status": "Diagnostic" if ready else "Inconclusive",
                "primary_limitation": (
                    "Archive and member bytes have not yet been independently verified."
                    if ready
                    else "One or more source-readiness gates remain unresolved."
                ),
                "not_suitable_for": [
                    "SAED analyzer execution",
                    "parameter selection",
                    "reflection or phase indexing",
                    "d-spacing performance claims",
                    "engineering release",
                ],
            },
        }
        normalized_json = output / "bir_author_response_normalized.json"
        assessment_json = output / "bir_author_response_assessment.json"
        report_md = output / "bir_author_response_assessment.md"
        manifest_json = output / "bir_author_response_manifest.json"
        paths = [normalized_json, assessment_json, report_md]
        _write_json(normalized_json, normalized)
        _write_json(assessment_json, assessment)
        report_md.write_text(_assessment_markdown(bundle, assessment, normalized), encoding="utf-8")
        if ready:
            handoff_json = output / "saed_validation_intake_handoff_template.json"
            _write_json(handoff_json, _intake_handoff(bundle, normalized))
            paths.append(handoff_json)
        _write_json(manifest_json, _artifact_manifest(output, paths))
        return assessment
    except Exception:
        _cleanup_output(output, created)
        raise


def _request_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "request_type": "authoritative_source_metadata_resolution",
        "source": {
            "record_id": bundle["record_id"],
            "doi": bundle["doi"],
            "record_metadata_sha256": bundle["record_metadata_sha256"],
            "reuse_rights": bundle["rights"],
        },
        "selected_archive": {
            "name": bundle["archive_name"],
            "bytes": bundle["archive_bytes"],
            "md5": bundle["archive_md5"],
        },
        "requested_evidence": [
            "authoritative respondent identity and authority",
            "raw-detector, lossless-export, or not-eligible representation classification",
            "complete detector integration, binning, and preprocessing history",
            "detector pixel geometry and coordinate transformations",
            "member paths and SHA-256 values for at least two independent series",
            "immutable source-assigned sample and acquisition identifiers",
            "source-supported centre coordinates or a reproducible centre procedure",
            "traceable reciprocal calibration for each proposed series",
            "analyzer-development and parameter-selection non-use attestation",
            "source-reference context without using it for analyzer tuning",
        ],
        "readiness_rule": (
            "A valid positive response permits only bounded download and byte-level member "
            "verification. It does not permit analyzer execution or scientific claims."
        ),
    }


def _response_template(bundle: Mapping[str, Any]) -> dict[str, Any]:
    def series(index: int) -> dict[str, Any]:
        return {
            "series_id": f"replace-series-{index:03d}",
            "member_path": f"replace/member-{index:03d}.mrc",
            "member_sha256": "0" * 64,
            "material_id": "AVAAGA",
            "sample_id": f"replace-sample-{index:03d}",
            "acquisition_id": f"replace-acquisition-{index:03d}",
            "independent_sample": False,
            "independent_acquisition": False,
            "file_format": "MRC",
            "shape": [2048, 2048],
            "dtype": "replace-with-file-dtype",
            "center": {
                "method": "unresolved",
                "x_px": None,
                "y_px": None,
                "source": "replace-with-source-or-procedure",
            },
            "calibration": {
                "method": "unresolved",
                "reciprocal_nm_inv_per_pixel": None,
                "camera_constant_nm_pixel": None,
                "reference_d_nm": None,
                "reference_radius_px": None,
                "source": "replace-with-traceable-calibration-record",
            },
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "record": {
            "record_id": bundle["record_id"],
            "doi": bundle["doi"],
            "record_metadata_sha256": bundle["record_metadata_sha256"],
        },
        "selected_archive": {
            "name": bundle["archive_name"],
            "bytes": bundle["archive_bytes"],
            "md5": bundle["archive_md5"],
        },
        "respondent": {
            "name": "replace-with-name",
            "role": "replace-with-role",
            "affiliation": "replace-with-affiliation",
            "contact": "replace-with-contact-route",
            "authority_confirmed": False,
        },
        "representation": {
            "classification": "not_eligible",
            "classification_basis": "replace-with-authoritative-basis",
            "released_files_are_original_acquisition_outputs": False,
            "original_detector_intensity_available": False,
            "native_detector_frames_available": False,
            "native_frame_integration_count": 30,
            "spatial_binning_documented": True,
            "spatial_binning_description": "replace-with-binning-factor-and-operation",
            "additional_operations": ["native_frame_integration", "spatial_binning"],
        },
        "instrument": {
            "microscope": bundle["microscope"],
            "detector": bundle["detector"],
            "accelerating_voltage_kv": bundle["accelerating_voltage_kv"],
            "detector_pixel_geometry": "replace-with-native-and-post-binning-geometry",
            "coordinate_convention": "replace-with-axis-origin-transpose-flip-convention",
        },
        "series": [series(1), series(2)],
        "independence_attestation": {
            "sample_ids_are_source_assigned": False,
            "acquisition_ids_are_source_assigned": False,
            "series_are_independent_acquisitions": False,
            "attestation": "replace-with-authoritative-lineage-statement",
        },
        "analyzer_nonuse_attestation": {
            "used_for_analyzer_development": False,
            "used_for_center_selection": False,
            "used_for_smoothing_selection": False,
            "used_for_prominence_selection": False,
            "used_for_radius_bound_selection": False,
            "used_for_candidate_count_selection": False,
            "attestation": "replace-with-authoritative-non-use-statement",
        },
        "reference_context": {
            "source_assignments_available": False,
            "bound_to_series": False,
            "description": "replace-with-reference-context-or-none",
        },
        "notes": ["replace-with-uncertainties-or-none"],
    }


def _validate_response(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, bool]]:
    _reject_unknown(
        payload,
        {
            "schema_version",
            "case_id",
            "record",
            "selected_archive",
            "respondent",
            "representation",
            "instrument",
            "series",
            "independence_attestation",
            "analyzer_nonuse_attestation",
            "reference_context",
            "notes",
        },
        "author response",
    )
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("case_id") != CASE_ID:
        raise BIRResolutionContractError("author response schema or case mismatch")

    record = _mapping(payload, "record")
    _reject_unknown(record, {"record_id", "doi", "record_metadata_sha256"}, "record")
    if _text(record, "record_id") != bundle["record_id"]:
        raise BIRResolutionContractError("response record_id mismatch")
    if _text(record, "doi").casefold() != str(bundle["doi"]).casefold():
        raise BIRResolutionContractError("response DOI mismatch")
    if _sha256(record, "record_metadata_sha256") != bundle["record_metadata_sha256"]:
        raise BIRResolutionContractError("response record metadata hash mismatch")

    archive = _mapping(payload, "selected_archive")
    _reject_unknown(archive, {"name", "bytes", "md5"}, "selected_archive")
    if _text(archive, "name") != bundle["archive_name"]:
        raise BIRResolutionContractError("response archive name mismatch")
    if _positive_int(archive, "bytes") != bundle["archive_bytes"]:
        raise BIRResolutionContractError("response archive byte mismatch")
    if _md5(archive, "md5") != bundle["archive_md5"]:
        raise BIRResolutionContractError("response archive MD5 mismatch")

    respondent = _mapping(payload, "respondent")
    _reject_unknown(
        respondent,
        {"name", "role", "affiliation", "contact", "authority_confirmed"},
        "respondent",
    )
    respondent_norm = {
        "name": _text(respondent, "name"),
        "role": _text(respondent, "role"),
        "affiliation": _text(respondent, "affiliation"),
        "contact": _text(respondent, "contact"),
        "authority_confirmed": _boolean(respondent, "authority_confirmed"),
    }

    representation = _mapping(payload, "representation")
    _reject_unknown(
        representation,
        {
            "classification",
            "classification_basis",
            "released_files_are_original_acquisition_outputs",
            "original_detector_intensity_available",
            "native_detector_frames_available",
            "native_frame_integration_count",
            "spatial_binning_documented",
            "spatial_binning_description",
            "additional_operations",
        },
        "representation",
    )
    classification = _text(representation, "classification")
    if classification not in _REPRESENTATIONS:
        raise BIRResolutionContractError("unsupported representation classification")
    representation_norm = {
        "classification": classification,
        "classification_basis": _text(representation, "classification_basis"),
        "released_files_are_original_acquisition_outputs": _boolean(
            representation, "released_files_are_original_acquisition_outputs"
        ),
        "original_detector_intensity_available": _boolean(
            representation, "original_detector_intensity_available"
        ),
        "native_detector_frames_available": _boolean(
            representation, "native_detector_frames_available"
        ),
        "native_frame_integration_count": _positive_int(
            representation, "native_frame_integration_count"
        ),
        "spatial_binning_documented": _boolean(
            representation, "spatial_binning_documented"
        ),
        "spatial_binning_description": _text(
            representation, "spatial_binning_description"
        ),
        "additional_operations": list(_texts(representation, "additional_operations")),
    }

    instrument = _mapping(payload, "instrument")
    _reject_unknown(
        instrument,
        {
            "microscope",
            "detector",
            "accelerating_voltage_kv",
            "detector_pixel_geometry",
            "coordinate_convention",
        },
        "instrument",
    )
    instrument_norm = {
        "microscope": _text(instrument, "microscope"),
        "detector": _text(instrument, "detector"),
        "accelerating_voltage_kv": _positive_float(
            instrument, "accelerating_voltage_kv"
        ),
        "detector_pixel_geometry": _text(instrument, "detector_pixel_geometry"),
        "coordinate_convention": _text(instrument, "coordinate_convention"),
    }
    if instrument_norm["microscope"] != bundle["microscope"]:
        raise BIRResolutionContractError("response microscope mismatch")
    if instrument_norm["detector"] != bundle["detector"]:
        raise BIRResolutionContractError("response detector mismatch")
    if instrument_norm["accelerating_voltage_kv"] != bundle["accelerating_voltage_kv"]:
        raise BIRResolutionContractError("response accelerating voltage mismatch")

    raw_series = payload.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise BIRResolutionContractError("series must be a non-empty list")
    series = [_validate_series(item, index) for index, item in enumerate(raw_series)]

    independence = _mapping(payload, "independence_attestation")
    _reject_unknown(
        independence,
        {
            "sample_ids_are_source_assigned",
            "acquisition_ids_are_source_assigned",
            "series_are_independent_acquisitions",
            "attestation",
        },
        "independence_attestation",
    )
    independence_norm = {
        "sample_ids_are_source_assigned": _boolean(
            independence, "sample_ids_are_source_assigned"
        ),
        "acquisition_ids_are_source_assigned": _boolean(
            independence, "acquisition_ids_are_source_assigned"
        ),
        "series_are_independent_acquisitions": _boolean(
            independence, "series_are_independent_acquisitions"
        ),
        "attestation": _text(independence, "attestation"),
    }

    nonuse = _mapping(payload, "analyzer_nonuse_attestation")
    nonuse_keys = {
        "used_for_analyzer_development",
        "used_for_center_selection",
        "used_for_smoothing_selection",
        "used_for_prominence_selection",
        "used_for_radius_bound_selection",
        "used_for_candidate_count_selection",
        "attestation",
    }
    _reject_unknown(nonuse, nonuse_keys, "analyzer_nonuse_attestation")
    nonuse_norm: dict[str, Any] = {
        key: _boolean(nonuse, key) for key in sorted(nonuse_keys - {"attestation"})
    }
    nonuse_norm["attestation"] = _text(nonuse, "attestation")

    reference = _mapping(payload, "reference_context")
    _reject_unknown(
        reference,
        {"source_assignments_available", "bound_to_series", "description"},
        "reference_context",
    )
    reference_norm = {
        "source_assignments_available": _boolean(
            reference, "source_assignments_available"
        ),
        "bound_to_series": _boolean(reference, "bound_to_series"),
        "description": _text(reference, "description"),
    }
    notes = list(_texts(payload, "notes"))
    series_ids = [item["series_id"] for item in series]
    paths = [item["member_path"] for item in series]
    hashes = [item["member_sha256"] for item in series]
    samples = [item["sample_id"] for item in series]
    acquisitions = [item["acquisition_id"] for item in series]
    gates = {
        "respondent_authority_confirmed": (
            respondent_norm["authority_confirmed"]
            and all(
                _is_resolved_text(respondent_norm[key])
                for key in ("name", "role", "affiliation", "contact")
            )
        ),
        "representation_eligible": (
            classification in {"raw_detector", "lossless_export"}
            and representation_norm["released_files_are_original_acquisition_outputs"]
            and representation_norm["original_detector_intensity_available"]
            and _is_resolved_text(representation_norm["classification_basis"])
        ),
        "integration_and_binning_documented": (
            representation_norm["native_frame_integration_count"] == 30
            and representation_norm["spatial_binning_documented"]
            and _is_resolved_text(
                representation_norm["spatial_binning_description"]
            )
            and {"native_frame_integration", "spatial_binning"}.issubset(
                set(representation_norm["additional_operations"])
            )
        ),
        "instrument_geometry_documented": all(
            _is_resolved_text(instrument_norm[key])
            for key in ("detector_pixel_geometry", "coordinate_convention")
        ),
        "minimum_two_series": len(series) >= 2,
        "series_ids_unique": (
            len(series_ids) == len(set(series_ids))
            and all(_is_resolved_identifier(value) for value in series_ids)
        ),
        "member_paths_unique": (
            len(paths) == len(set(paths))
            and all(_is_resolved_text(value) for value in paths)
        ),
        "member_hashes_unique": len(hashes) == len(set(hashes)),
        "minimum_two_source_assigned_samples": (
            len(set(samples)) >= 2
            and all(_is_resolved_identifier(value) for value in samples)
            and independence_norm["sample_ids_are_source_assigned"]
            and _is_resolved_text(independence_norm["attestation"])
        ),
        "minimum_two_source_assigned_acquisitions": (
            len(set(acquisitions)) >= 2
            and all(_is_resolved_identifier(value) for value in acquisitions)
            and independence_norm["acquisition_ids_are_source_assigned"]
            and independence_norm["series_are_independent_acquisitions"]
            and _is_resolved_text(independence_norm["attestation"])
        ),
        "all_series_independence_flags_true": (
            all(
                item["independent_sample"] and item["independent_acquisition"]
                for item in series
            )
            and _is_resolved_text(independence_norm["attestation"])
        ),
        "all_member_checksums_declared": all(
            item["member_sha256"] != "0" * 64 for item in series
        ),
        "all_series_dtype_documented": all(
            _is_resolved_text(item["dtype"]) for item in series
        ),
        "all_centres_traceable": all(
            item["center"]["method"] != "unresolved"
            and _is_resolved_text(item["center"]["source"])
            for item in series
        ),
        "all_reciprocal_calibrations_traceable": all(
            item["calibration"]["method"] != "unresolved"
            and _is_resolved_text(item["calibration"]["source"])
            for item in series
        ),
        "analyzer_nonuse_attested": (
            all(
                value is False
                for key, value in nonuse_norm.items()
                if key != "attestation"
            )
            and _is_resolved_text(nonuse_norm["attestation"])
        ),
    }
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "record": {
            "record_id": bundle["record_id"],
            "doi": bundle["doi"],
            "record_metadata_sha256": bundle["record_metadata_sha256"],
        },
        "selected_archive": {
            "name": bundle["archive_name"],
            "bytes": bundle["archive_bytes"],
            "md5": bundle["archive_md5"],
        },
        "respondent": respondent_norm,
        "representation": representation_norm,
        "instrument": instrument_norm,
        "series": series,
        "independence_attestation": independence_norm,
        "analyzer_nonuse_attestation": nonuse_norm,
        "reference_context": reference_norm,
        "notes": notes,
    }
    return normalized, gates


def _validate_series(raw: Any, index: int) -> dict[str, Any]:
    item = _mapping_value(raw, f"series[{index}]")
    _reject_unknown(
        item,
        {
            "series_id",
            "member_path",
            "member_sha256",
            "material_id",
            "sample_id",
            "acquisition_id",
            "independent_sample",
            "independent_acquisition",
            "file_format",
            "shape",
            "dtype",
            "center",
            "calibration",
        },
        f"series[{index}]",
    )
    shape = item.get("shape")
    if shape != [2048, 2048]:
        raise BIRResolutionContractError(f"series[{index}].shape must equal [2048, 2048]")
    if _text(item, "file_format").casefold() != "mrc":
        raise BIRResolutionContractError(f"series[{index}] must use MRC")
    return {
        "series_id": _identifier(item, "series_id"),
        "member_path": _relative_path(item, "member_path"),
        "member_sha256": _sha256(item, "member_sha256"),
        "material_id": _identifier(item, "material_id"),
        "sample_id": _identifier(item, "sample_id"),
        "acquisition_id": _identifier(item, "acquisition_id"),
        "independent_sample": _boolean(item, "independent_sample"),
        "independent_acquisition": _boolean(item, "independent_acquisition"),
        "file_format": "MRC",
        "shape": [2048, 2048],
        "dtype": _text(item, "dtype"),
        "center": _validate_center(_mapping(item, "center"), index),
        "calibration": _validate_calibration(_mapping(item, "calibration"), index),
    }


def _validate_center(center: Mapping[str, Any], index: int) -> dict[str, Any]:
    _reject_unknown(center, {"method", "x_px", "y_px", "source"}, f"series[{index}].center")
    method = _text(center, "method")
    if method not in _CENTER_METHODS:
        raise BIRResolutionContractError(f"unsupported center method in series[{index}]")
    x = _optional_nonnegative(center.get("x_px"), "x_px")
    y = _optional_nonnegative(center.get("y_px"), "y_px")
    if method == "unresolved" and (x is not None or y is not None):
        raise BIRResolutionContractError(f"unresolved center in series[{index}] must not declare coordinates")
    if method != "unresolved" and (x is None or y is None):
        raise BIRResolutionContractError(f"resolved center in series[{index}] requires coordinates")
    return {"method": method, "x_px": x, "y_px": y, "source": _text(center, "source")}


def _validate_calibration(calibration: Mapping[str, Any], index: int) -> dict[str, Any]:
    _reject_unknown(
        calibration,
        {
            "method",
            "reciprocal_nm_inv_per_pixel",
            "camera_constant_nm_pixel",
            "reference_d_nm",
            "reference_radius_px",
            "source",
        },
        f"series[{index}].calibration",
    )
    method = _text(calibration, "method")
    if method not in _CALIBRATION_METHODS:
        raise BIRResolutionContractError(f"unsupported calibration method in series[{index}]")
    reciprocal = _optional_positive(calibration.get("reciprocal_nm_inv_per_pixel"), "reciprocal_nm_inv_per_pixel")
    constant = _optional_positive(calibration.get("camera_constant_nm_pixel"), "camera_constant_nm_pixel")
    reference_d = _optional_positive(calibration.get("reference_d_nm"), "reference_d_nm")
    reference_radius = _optional_positive(calibration.get("reference_radius_px"), "reference_radius_px")
    if (reference_d is None) != (reference_radius is None):
        raise BIRResolutionContractError(f"series[{index}] reference pair is incomplete")
    populated = {
        "reciprocal_nm_inv_per_pixel": reciprocal is not None,
        "camera_constant_nm_pixel": constant is not None,
        "reference_pair": reference_d is not None and reference_radius is not None,
    }
    if method == "unresolved" and any(populated.values()):
        raise BIRResolutionContractError(f"unresolved calibration in series[{index}] must not declare values")
    if method != "unresolved" and (not populated[method] or sum(populated.values()) != 1):
        raise BIRResolutionContractError(f"series[{index}] must declare exactly one calibration route")
    return {
        "method": method,
        "reciprocal_nm_inv_per_pixel": reciprocal,
        "camera_constant_nm_pixel": constant,
        "reference_d_nm": reference_d,
        "reference_radius_px": reference_radius,
        "source": _text(calibration, "source"),
    }


def _intake_handoff(bundle: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    patterns = []
    representation = response["representation"]["classification"]
    for index, series in enumerate(response["series"], 1):
        calibration = series["calibration"]
        patterns.append(
            {
                "pattern_id": f"bir-{index:03d}",
                "relative_path": series["member_path"],
                "sha256": series["member_sha256"],
                "sample_id": series["sample_id"],
                "acquisition_id": series["acquisition_id"],
                "material_id": series["material_id"],
                "representation": representation,
                "original_detector_intensity_available": True,
                "file_format": "MRC",
                "accelerating_voltage_kv": bundle["accelerating_voltage_kv"],
                "camera_length_mm": None,
                "detector_model": bundle["detector"],
                "detector_pixel_size_um": None,
                "center_x_px": series["center"]["x_px"],
                "center_y_px": series["center"]["y_px"],
                "center_source": series["center"]["source"],
                "calibration_method": calibration["method"],
                "reciprocal_nm_inv_per_pixel": calibration["reciprocal_nm_inv_per_pixel"],
                "camera_constant_nm_pixel": calibration["camera_constant_nm_pixel"],
                "reference_d_nm": calibration["reference_d_nm"],
                "reference_radius_px": calibration["reference_radius_px"],
                "calibration_source": calibration["source"],
                "preprocessing_operations": response["representation"]["additional_operations"],
                "used_for_center_selection": False,
                "used_for_smoothing_selection": False,
                "used_for_prominence_selection": False,
                "used_for_radius_bound_selection": False,
                "used_for_candidate_count_selection": False,
                "excluded": False,
                "exclusion_reason": None,
            }
        )
    return {
        "schema_version": "1.0",
        "case_id": "saed_external_validation_intake",
        "dataset": {
            "dataset_id": "bir-microed-200kev-zenodo-10999587-bounded",
            "dataset_version": bundle["record_metadata_sha256"],
            "source_type": "external_public",
            "license": ", ".join(bundle["rights"]),
            "reuse_authorized": True,
            "identity_provenance": "source_assigned",
            "material_identity_source": (
                "authoritative BIR metadata response bound to Zenodo record 10999587"
            ),
            "target_analyzer_development_nonuse_attested": True,
            "creator_overlap_with_analyzer_development_source": False,
            "cross_dataset_lineage_independence_attested": True,
            "minimum_independent_samples": 2,
            "minimum_independent_acquisitions": 2,
        },
        "patterns": patterns,
        "evaluation_protocol": {
            "source_metadata_review_status": "not_run",
            "file_content_audit_status": "not_run",
            "calibration_review_status": "not_run",
            "acquisition_independence_review_status": "not_run",
            "content_overlap_audit_status": "not_run",
            "analysis_parameters_frozen": False,
            "indexing_protocol_frozen": False,
            "reference_set_frozen": False,
            "manifest_checksum_frozen": False,
            "frozen_manifest_sha256": None,
            "frozen_protocol_id": None,
            "reference_type": "none",
            "reference_identifier": None,
            "metrics_frozen": False,
            "uncertainty_method_frozen": False,
            "exclusion_rules_frozen": False,
        },
    }


def _request_markdown(bundle: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    requested = "\n".join(
        f"{index}. {item}" for index, item in enumerate(request["requested_evidence"], 1)
    )
    return f"""# BIR-MicroED 200 keV metadata-resolution request

This request concerns Zenodo record `{bundle['doi']}` and publication
`10.1107/S2052252524012132`.

The official record identity, archive-level checksums, and `CC BY 4.0` reuse
terms have already been verified. The proposed first bounded archive is
`{bundle['archive_name']}` ({bundle['archive_bytes']} bytes, MD5
`{bundle['archive_md5']}`).

Please return the completed `bir_author_response_template.json` through an
authoritative data collector, publication author, or repository-curator route.
Do not infer values from filenames or image appearance.

## Requested evidence

{requested}

## Decision boundary

A complete positive response permits only bounded archive download and
independent checksum/member verification. It does not permit analyzer
execution, parameter selection, reflection or phase indexing, d-spacing
performance claims, or engineering use.
"""


def _assessment_markdown(
    bundle: Mapping[str, Any],
    assessment: Mapping[str, Any],
    response: Mapping[str, Any],
) -> str:
    lines = [
        "# BIR-MicroED author metadata-response assessment",
        "",
        f"- Status: `{assessment['status']}`",
        f"- Record: `{bundle['doi']}`",
        f"- Archive: `{bundle['archive_name']}`",
        f"- Respondent: `{response['respondent']['name']}`",
        f"- Representation: `{response['representation']['classification']}`",
        f"- Series declared: `{len(response['series'])}`",
        f"- Ready for bounded download verification: `{str(assessment['ready_for_bounded_archive_download_and_member_verification']).lower()}`",
        "- SAED validation intake ready: `false`",
        "- Predeclared external evaluation ready: `false`",
        "",
        "## Evidence gates",
        "",
    ]
    lines.extend(
        f"- `{key}`: `{str(value).lower()}`"
        for key, value in assessment["evidence_gates"].items()
    )
    if assessment["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in assessment["blockers"])
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "This assessment validates metadata and declared lineage only. Archive and MRC bytes remain unverified, and no analyzer or crystallographic result is authorized.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_inventory(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise BIRResolutionContractError("could not read archive inventory") from exc
    if not rows:
        raise BIRResolutionContractError("archive inventory is empty")
    for index, row in enumerate(rows):
        if not {"name", "bytes", "md5"}.issubset(row):
            raise BIRResolutionContractError(f"archive inventory row {index} is incomplete")
        try:
            row["bytes"] = int(row["bytes"])
        except (TypeError, ValueError) as exc:
            raise BIRResolutionContractError(f"archive inventory row {index} has invalid bytes") from exc
        if row["bytes"] <= 0 or not re.fullmatch(r"[0-9a-fA-F]{32}", str(row["md5"])):
            raise BIRResolutionContractError(f"archive inventory row {index} is invalid")
    return rows


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise BIRResolutionContractError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, Mapping):
        raise BIRResolutionContractError(f"{label} root must be an object")
    return payload


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


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    if output.exists():
        if not output.is_dir() or output.is_symlink() or any(output.iterdir()):
            raise FileExistsError("output must be an absent or empty directory")
        return output, False
    output.mkdir(parents=True)
    return output, True


def _cleanup_output(output: Path, created: bool) -> None:
    if not output.exists() or not output.is_dir() or output.is_symlink():
        return
    if created:
        shutil.rmtree(output, ignore_errors=True)
        return
    for child in output.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


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


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BIRResolutionContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise BIRResolutionContractError(f"unknown {context} field: {unknown[0]}")


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise BIRResolutionContractError(f"{key} must be an object")
    return value


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BIRResolutionContractError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BIRResolutionContractError(f"{key} must be a non-empty string")
    return value.strip()


def _identifier(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise BIRResolutionContractError(f"{key} is not a stable identifier")
    return value


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise BIRResolutionContractError(f"{key} must be boolean")
    return value


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BIRResolutionContractError(f"{key} must be a positive integer")
    return value


def _positive_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise BIRResolutionContractError(f"{key} must be a positive number")
    return float(value)


def _optional_positive(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise BIRResolutionContractError(f"{key} must be null or positive")
    return float(value)


def _optional_nonnegative(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise BIRResolutionContractError(f"{key} must be null or non-negative")
    return float(value)


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise BIRResolutionContractError(f"{key} must be a non-empty string array")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BIRResolutionContractError(f"{key} must contain non-empty strings")
        cleaned.append(item.strip())
    if len(cleaned) != len(set(cleaned)):
        raise BIRResolutionContractError(f"{key} must not contain duplicates")
    return tuple(cleaned)


def _relative_path(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if "\\" in value:
        raise BIRResolutionContractError(f"{key} must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BIRResolutionContractError(f"{key} must be a safe relative path")
    return path.as_posix()


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BIRResolutionContractError(f"{key} must be 64 hexadecimal characters")
    return value


def _md5(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).casefold()
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise BIRResolutionContractError(f"{key} must be 32 hexadecimal characters")
    return value


_UNRESOLVED_TEXT = {
    "n/a",
    "not available",
    "not provided",
    "tbd",
    "todo",
    "unknown",
    "unresolved",
}
_PLACEHOLDER_PREFIXES = (
    "replace-",
    "replace/",
    "replace_",
    "replace with",
    "replace-with",
)


def _is_resolved_text(value: str) -> bool:
    normalized = " ".join(value.strip().casefold().split())
    return bool(normalized) and normalized not in _UNRESOLVED_TEXT and not normalized.startswith(
        _PLACEHOLDER_PREFIXES
    )


def _is_resolved_identifier(value: str) -> bool:
    return _is_resolved_text(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate or assess the BIR-MicroED 200 keV metadata-resolution "
            "contract without downloading diffraction arrays."
        )
    )
    parser.add_argument(
        "--audit-output",
        required=True,
        help="Output directory from mca saed-bir-metadata-audit",
    )
    parser.add_argument(
        "--response",
        help="Completed authoritative response JSON; omit to generate request package",
    )
    parser.add_argument("--output", required=True, help="Absent or empty output directory")
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bundle = load_audit_bundle(args.audit_output)
    result = (
        assess_author_response(bundle, args.response, args.output)
        if args.response
        else build_request_package(bundle, args.output)
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "archive_download_authorized": result["archive_download_authorized"],
                "saed_validation_intake_ready": result["saed_validation_intake_ready"],
                "predeclared_external_evaluation_ready": result[
                    "predeclared_external_evaluation_ready"
                ],
                "recommended_next_action": result["recommended_next_action"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
