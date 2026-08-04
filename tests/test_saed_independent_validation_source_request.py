from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "saed_independent_validation_source_request.py"
)
SPEC = importlib.util.spec_from_file_location("saed_source_request", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry_bundle(tmp_path: Path) -> Path:
    output = tmp_path / "registry"
    output.mkdir()

    inventory = output / "saed_candidate_inventory.csv"
    with inventory.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "candidate_id",
                "dedicated_source_audit_ready",
                "predeclared_external_evaluation_ready",
            ],
        )
        writer.writeheader()
        for index in range(3):
            writer.writerow(
                {
                    "candidate_id": f"candidate_{index}",
                    "dedicated_source_audit_ready": "false",
                    "predeclared_external_evaluation_ready": "false",
                }
            )

    summary = {
        "schema_version": "1.0",
        "case_id": module.REGISTRY_CASE_ID,
        "software_version": "0.10.0",
        "search_snapshot": {
            "search_date": "2026-08-02",
            "candidate_count": 3,
        },
        "target_contract": {
            "task": (
                "external validation of static selected-area electron "
                "diffraction pattern detection and calibrated d-spacing support"
            ),
            "acquisition_mode": "static_selected_area_diffraction",
            "minimum_independent_pattern_series": 2,
        },
        "result_counts": {
            "candidate_count": 3,
            "dedicated_source_audit_ready_count": 0,
        },
        "readiness": {
            "status": module.REGISTRY_RESULT,
            "public_search_supports_saed_evaluation_now": False,
        },
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
    }
    (output / "saed_candidate_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (output / "saed_candidate_report.md").write_text(
        "# Registry\n", encoding="utf-8"
    )
    protocol = {
        "schema_version": "1.0",
        "purpose": "bounded source audit before static SAED analyzer execution",
        "subset_requirements": {
            "minimum_independent_pattern_series": 2,
        },
    }
    (output / "saed_source_audit_protocol.json").write_text(
        json.dumps(protocol, indent=2) + "\n", encoding="utf-8"
    )

    artifacts = []
    for name in [
        "saed_candidate_inventory.csv",
        "saed_candidate_summary.json",
        "saed_candidate_report.md",
        "saed_source_audit_protocol.json",
    ]:
        path = output / name
        artifacts.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": _sha(path),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "case_id": module.REGISTRY_CASE_ID,
        "software_version": "0.10.0",
        "search_date": "2026-08-02",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    (output / "saed_candidate_artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return output


def _respondent() -> dict[str, str]:
    return {
        "name": "Repository Curator",
        "affiliation": "Microscopy Repository",
        "email": "curator@example.org",
        "authority": "repository_curator",
        "authority_basis": "Repository record custodian",
    }


def _candidate_response() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_case_id": module.CASE_ID,
        "response_status": "candidate_available",
        "respondent": _respondent(),
        "candidate": {
            "dataset_id": "saed-independent-001",
            "dataset_version": "1.0",
            "source_type": "external_public",
            "source_url": "https://example.org/records/saed-independent-001",
            "transfer_route": "HTTPS repository file endpoint",
            "reuse_license": "CC BY 4.0",
            "reuse_authorization_basis": "Repository license record",
            "collection_manifest_sha256": "a" * 64,
            "material_identity": "L-histidine hydrochloride monohydrate",
            "composition": "C6H10ClN3O2·H2O",
            "preparation_history": "Crystallized from aqueous solution",
            "acquisition_mode": "static_selected_area_diffraction",
            "accelerating_voltage_kv": 200.0,
            "detector_model": "Ceta-D",
            "detector_pixel_size_um": 14.0,
            "pattern_center_method": "Direct-beam calibration",
            "pattern_center_source": "Acquisition log and calibration image",
            "reciprocal_calibration_nm_inv_per_pixel": 0.0125,
            "reciprocal_calibration_source": "Camera-length calibration standard",
            "reference_protocol_id": "saed-reference-protocol-v1",
            "reference_type": "predeclared_reference_structures",
            "reference_identifiers": ["COD:2102215"],
            "reference_frozen_before_analyzer_execution": True,
            "analyzer_development_nonuse_attested": True,
            "patterns": [
                {
                    "pattern_id": "pattern-001",
                    "relative_path": "patterns/pattern_001.tif",
                    "bytes": 1024,
                    "sha256": "b" * 64,
                    "representation": "lossless_export",
                    "original_intensity_preserved": True,
                    "sample_id": "sample-001",
                    "sample_identity_provenance": "source_assigned",
                    "acquisition_id": "acq-001",
                    "acquisition_identity_provenance": "source_assigned",
                    "pattern_center_x_px": 1024.5,
                    "pattern_center_y_px": 1023.5,
                },
                {
                    "pattern_id": "pattern-002",
                    "relative_path": "patterns/pattern_002.tif",
                    "bytes": 2048,
                    "sha256": "c" * 64,
                    "representation": "raw_detector",
                    "original_intensity_preserved": True,
                    "sample_id": "sample-002",
                    "sample_identity_provenance": (
                        "operator_assigned_at_acquisition"
                    ),
                    "acquisition_id": "acq-002",
                    "acquisition_identity_provenance": (
                        "operator_assigned_at_acquisition"
                    ),
                    "pattern_center_x_px": 1022.5,
                    "pattern_center_y_px": 1025.0,
                },
            ],
        },
        "referrals": [],
        "notes": "The two acquisitions are independently collected.",
    }


def test_build_request_package(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    bundle = module.load_registry_bundle(registry)
    output = tmp_path / "request"

    summary = module.build_request_package(bundle, output)

    assert summary["status"] == module.REQUEST_READY
    assert summary["source_download_authorized"] is False
    request = json.loads(
        (output / "saed_independent_source_request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request["current_evidence_state"]["assessed_candidate_count"] == 3
    assert (
        request["target_contract"]["minimum_independent_pattern_series"] == 2
    )
    assert request["decision_boundary"]["saed_analyzer_execution_authorized"] is False

    manifest = json.loads(
        (output / "saed_independent_source_request_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 4
    for record in manifest["artifacts"]:
        path = output / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert _sha(path) == record["sha256"]


def test_complete_response_creates_bounded_plan(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    bundle = module.load_registry_bundle(registry)
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(_candidate_response(), indent=2) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "assessment"

    assessment = module.assess_author_response(bundle, response, output)

    assert assessment["status"] == module.RESPONSE_READY
    assert assessment["ready_for_bounded_source_verification"] is True
    assert assessment["source_download_authorized"] is False
    assert assessment["saed_analyzer_execution_authorized"] is False
    assert not assessment["source_blockers"]

    plan = json.loads(
        (output / "saed_bounded_source_verification_plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(plan["declared_patterns"]) == 2
    assert plan["source_download_authorized"] is False
    assert plan["external_evaluation_ready"] is False


def test_referral_response_remains_fail_closed(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    bundle = module.load_registry_bundle(registry)
    response = tmp_path / "referral.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request_case_id": module.CASE_ID,
                "response_status": "referral_only",
                "respondent": _respondent(),
                "candidate": None,
                "referrals": [
                    {
                        "name": "Independent Collector",
                        "affiliation": "External Facility",
                        "email": "collector@example.org",
                        "reason": "Holds original detector exports",
                    }
                ],
                "notes": "No candidate files are held by this repository.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "assessment"

    assessment = module.assess_author_response(bundle, response, output)

    assert assessment["status"] == module.NO_SOURCE
    assert assessment["ready_for_bounded_source_verification"] is False
    assert not (output / "saed_bounded_source_verification_plan.json").exists()


def test_rendered_pattern_blocks_readiness(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    bundle = module.load_registry_bundle(registry)
    payload = _candidate_response()
    candidate = payload["candidate"]
    assert isinstance(candidate, dict)
    patterns = candidate["patterns"]
    assert isinstance(patterns, list)
    assert isinstance(patterns[0], dict)
    patterns[0]["representation"] = "rendered_figure"
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    assessment = module.assess_author_response(
        bundle, response, tmp_path / "assessment"
    )

    assert assessment["status"] == module.RESPONSE_BLOCKED
    assert "raw_or_lossless_representations" in assessment["source_blockers"]


def test_duplicate_acquisition_id_is_rejected(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    bundle = module.load_registry_bundle(registry)
    payload = _candidate_response()
    candidate = payload["candidate"]
    assert isinstance(candidate, dict)
    patterns = candidate["patterns"]
    assert isinstance(patterns, list)
    assert isinstance(patterns[0], dict)
    assert isinstance(patterns[1], dict)
    patterns[1]["acquisition_id"] = patterns[0]["acquisition_id"]
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(
        module.SAEDSourceRequestContractError,
        match="acquisition_id values must be unique",
    ):
        module.assess_author_response(
            bundle, response, tmp_path / "assessment"
        )


def test_registry_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    (registry / "saed_candidate_report.md").write_text(
        "# Tampered\n", encoding="utf-8"
    )

    with pytest.raises(
        module.SAEDSourceRequestContractError,
        match="SHA-256 mismatch",
    ):
        module.load_registry_bundle(registry)


def test_nonempty_output_is_not_overwritten(tmp_path: Path) -> None:
    registry = _registry_bundle(tmp_path)
    bundle = module.load_registry_bundle(registry)
    output = tmp_path / "request"
    output.mkdir()
    (output / "existing.txt").write_text(
        "do not overwrite", encoding="utf-8"
    )

    with pytest.raises(FileExistsError, match="absent or an empty directory"):
        module.build_request_package(bundle, output)
