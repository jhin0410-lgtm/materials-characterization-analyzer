from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from mca.saed_bir_metadata_resolution import (
    BIRResolutionContractError,
    REQUEST_READY,
    RESPONSE_BLOCKED,
    RESPONSE_READY,
    assess_author_response,
    build_request_package,
    cli_main,
    load_audit_bundle,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "audit"
    root.mkdir()
    summary = {
        "case_id": "saed_bir_200kev_metadata_audit",
        "result": "record_inventory_verified_but_source_not_ready_for_saed_evaluation",
        "source": {
            "record_id": "10999587",
            "doi": "10.5281/zenodo.10999587",
            "record_metadata_sha256": "a" * 64,
            "rights": ["cc-by-4.0"],
        },
        "publication_evidence": {
            "microscope": "Talos F200C",
            "detector": "DE Apollo direct electron detector",
            "accelerating_voltage_kv": 200,
            "output_shape": [2048, 2048],
            "output_format": "MRC",
        },
        "evidence_gates": {
            "explicit_reuse_terms_verified": True,
            "ready_for_bounded_archive_download": False,
            "ready_for_saed_validation_intake": False,
            "ready_for_predeclared_external_evaluation": False,
        },
    }
    plan = {
        "selected_archive": "AVAAGA_200kV_293K.zip",
        "selected_archive_bytes": 2_225_239_393,
        "download_authorized_now": False,
        "full_record_download_prohibited": True,
    }
    _write_json(root / "bir_metadata_audit_summary.json", summary)
    _write_json(root / "bir_bounded_subset_plan.json", plan)
    with (root / "bir_archive_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "bytes", "md5"])
        writer.writeheader()
        writer.writerow({
            "name": "AVAAGA_200kV_293K.zip",
            "bytes": 2_225_239_393,
            "md5": "f800d8b28b1b93f074b8a1d7c19dc930",
        })
    paths = [
        root / "bir_archive_inventory.csv",
        root / "bir_metadata_audit_summary.json",
        root / "bir_bounded_subset_plan.json",
    ]
    manifest = {
        "schema_version": "1.0",
        "case_id": "saed_bir_200kev_metadata_audit",
        "record_metadata_sha256": "a" * 64,
        "artifact_count": len(paths),
        "artifacts": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha(path)}
            for path in paths
        ],
    }
    _write_json(root / "bir_metadata_audit_manifest.json", manifest)
    return root


def _template(tmp_path: Path) -> tuple[dict, dict, Path]:
    audit = _audit_bundle(tmp_path)
    bundle = load_audit_bundle(audit)
    out = tmp_path / "request"
    build_request_package(bundle, out)
    payload = json.loads((out / "bir_author_response_template.json").read_text())
    return bundle, payload, audit


def _positive(payload: dict) -> dict:
    payload["respondent"].update({
        "name": "Authoritative Data Curator",
        "role": "data collector",
        "affiliation": "UCLA",
        "contact": "publication correspondence route",
        "authority_confirmed": True,
    })
    payload["representation"].update({
        "classification": "lossless_export",
        "classification_basis": "Original acquisition outputs preserving stored intensities.",
        "released_files_are_original_acquisition_outputs": True,
        "original_detector_intensity_available": True,
        "spatial_binning_description": "2x2 detector binning before acquisition write",
    })
    payload["instrument"].update({
        "detector_pixel_geometry": "native and 2x2-binned detector geometry documented",
        "coordinate_convention": "x right, y down, top-left origin, no transpose or flip",
    })
    payload["independence_attestation"].update({
        "sample_ids_are_source_assigned": True,
        "acquisition_ids_are_source_assigned": True,
        "series_are_independent_acquisitions": True,
        "attestation": "Two source-assigned crystals and acquisitions are independent.",
    })
    payload["analyzer_nonuse_attestation"]["attestation"] = "No proposed series was used for analyzer development or parameter selection."
    payload["reference_context"].update({
        "source_assignments_available": True,
        "bound_to_series": True,
        "description": "Source assignments exist but remain excluded from parameter tuning.",
    })
    payload["notes"] = ["none"]
    for index, series in enumerate(payload["series"], 1):
        series.update({
            "series_id": f"avaaga-series-{index:03d}",
            "member_path": f"AVAAGA/series-{index:03d}.mrc",
            "member_sha256": f"{index}" * 64,
            "sample_id": f"avaaga-crystal-{index:03d}",
            "acquisition_id": f"avaaga-acquisition-{index:03d}",
            "independent_sample": True,
            "independent_acquisition": True,
            "dtype": "int16",
        })
        series["center"].update({
            "method": "source_coordinates",
            "x_px": 1024.0,
            "y_px": 1024.0,
            "source": f"source calibration record {index}",
        })
        series["calibration"].update({
            "method": "reciprocal_nm_inv_per_pixel",
            "reciprocal_nm_inv_per_pixel": 0.002,
            "source": f"source reciprocal calibration {index}",
        })
    return payload


def test_request_package_is_fail_closed(tmp_path: Path) -> None:
    audit = _audit_bundle(tmp_path)
    bundle = load_audit_bundle(audit)
    summary = build_request_package(bundle, tmp_path / "request")
    assert summary["status"] == REQUEST_READY
    assert not summary["archive_download_authorized"]
    assert not summary["saed_validation_intake_ready"]
    manifest = json.loads((tmp_path / "request" / "bir_metadata_resolution_manifest.json").read_text())
    assert manifest["artifact_count"] == 4


def test_unresolved_response_is_valid_but_blocked(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    response = tmp_path / "response.json"
    _write_json(response, payload)
    result = assess_author_response(bundle, response, tmp_path / "assessment")
    assert result["status"] == RESPONSE_BLOCKED
    assert "representation_eligible" in result["blockers"]
    assert not (tmp_path / "assessment" / "saed_validation_intake_handoff_template.json").exists()


def test_positive_response_only_reaches_download_verification(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    response = tmp_path / "response.json"
    _write_json(response, _positive(payload))
    result = assess_author_response(bundle, response, tmp_path / "assessment")
    assert result["status"] == RESPONSE_READY
    assert result["ready_for_bounded_archive_download_and_member_verification"]
    assert not result["archive_download_authorized"]
    assert not result["saed_validation_intake_ready"]
    handoff = json.loads((tmp_path / "assessment" / "saed_validation_intake_handoff_template.json").read_text())
    assert handoff["dataset"]["identity_provenance"] == "source_assigned"
    assert len(handoff["patterns"]) == 2


def test_duplicate_sample_ids_block_readiness(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload = _positive(payload)
    payload["series"][1]["sample_id"] = payload["series"][0]["sample_id"]
    response = tmp_path / "response.json"
    _write_json(response, payload)
    result = assess_author_response(bundle, response, tmp_path / "assessment")
    assert not result["evidence_gates"]["minimum_two_source_assigned_samples"]


def test_placeholder_text_cannot_satisfy_readiness(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload = _positive(payload)
    payload["respondent"]["name"] = "replace-with-name"
    payload["representation"]["classification_basis"] = "unresolved"
    payload["instrument"]["coordinate_convention"] = "replace-with-convention"
    payload["series"][0]["sample_id"] = "replace-sample-001"
    payload["series"][0]["member_path"] = "replace/member-001.mrc"
    payload["series"][0]["dtype"] = "replace-with-file-dtype"
    payload["series"][0]["center"]["source"] = "unresolved"
    payload["series"][0]["calibration"]["source"] = "replace-with-calibration"
    payload["independence_attestation"]["attestation"] = "unresolved"
    payload["analyzer_nonuse_attestation"]["attestation"] = "replace-with-attestation"
    response = tmp_path / "response.json"
    _write_json(response, payload)
    result = assess_author_response(bundle, response, tmp_path / "assessment")
    assert result["status"] == RESPONSE_BLOCKED
    for gate in (
        "respondent_authority_confirmed",
        "representation_eligible",
        "instrument_geometry_documented",
        "member_paths_unique",
        "minimum_two_source_assigned_samples",
        "all_series_dtype_documented",
        "all_centres_traceable",
        "all_reciprocal_calibrations_traceable",
        "analyzer_nonuse_attested",
    ):
        assert not result["evidence_gates"][gate]


def test_identity_mismatch_rejected(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload["record"]["record_id"] = "wrong"
    response = tmp_path / "response.json"
    _write_json(response, payload)
    with pytest.raises(BIRResolutionContractError, match="record_id mismatch"):
        assess_author_response(bundle, response, tmp_path / "assessment")


def test_unknown_field_rejected(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload["unexpected"] = True
    response = tmp_path / "response.json"
    _write_json(response, payload)
    with pytest.raises(BIRResolutionContractError, match="unknown author response field"):
        assess_author_response(bundle, response, tmp_path / "assessment")


def test_duplicate_json_key_rejected(tmp_path: Path) -> None:
    bundle, _, _ = _template(tmp_path)
    response = tmp_path / "response.json"
    response.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(BIRResolutionContractError, match="duplicate JSON object key"):
        assess_author_response(bundle, response, tmp_path / "assessment")


def test_multiple_calibration_routes_rejected(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload = _positive(payload)
    payload["series"][0]["calibration"]["camera_constant_nm_pixel"] = 1.0
    response = tmp_path / "response.json"
    _write_json(response, payload)
    with pytest.raises(BIRResolutionContractError, match="exactly one calibration route"):
        assess_author_response(bundle, response, tmp_path / "assessment")


def test_unsafe_member_path_rejected(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload = _positive(payload)
    payload["series"][0]["member_path"] = "../series.mrc"
    response = tmp_path / "response.json"
    _write_json(response, payload)
    with pytest.raises(BIRResolutionContractError, match="safe relative path"):
        assess_author_response(bundle, response, tmp_path / "assessment")


def test_mutated_audit_artifact_rejected(tmp_path: Path) -> None:
    audit = _audit_bundle(tmp_path)
    with (audit / "bir_archive_inventory.csv").open("a", encoding="utf-8") as handle:
        handle.write("mutation")
    with pytest.raises(BIRResolutionContractError, match="byte mismatch"):
        load_audit_bundle(audit)


def test_nonempty_output_rejected(tmp_path: Path) -> None:
    audit = _audit_bundle(tmp_path)
    bundle = load_audit_bundle(audit)
    output = tmp_path / "out"
    output.mkdir()
    (output / "existing.txt").write_text("x")
    with pytest.raises(FileExistsError):
        build_request_package(bundle, output)


def test_cli_request_mode(tmp_path: Path) -> None:
    audit = _audit_bundle(tmp_path)
    assert cli_main(["--audit-output", str(audit), "--output", str(tmp_path / "out")]) == 0
