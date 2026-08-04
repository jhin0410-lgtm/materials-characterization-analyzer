from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SUPPORT_PATH = Path(__file__).with_name("saed_transfer_test_case.py")
SUPPORT_SPEC = importlib.util.spec_from_file_location("saed_transfer_test_case", SUPPORT_PATH)
assert SUPPORT_SPEC is not None and SUPPORT_SPEC.loader is not None
support = importlib.util.module_from_spec(SUPPORT_SPEC)
SUPPORT_SPEC.loader.exec_module(support)

module = support.module
_sha = support._sha
_write_json = support._write_json
_source_tree = support._source_tree
_response_bundle = support._response_bundle
_verification = support._verification
_case = support._case


def test_verified_transfer_generates_fail_closed_intake_draft(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    output = tmp_path / "output"

    summary = module.verify_transfer(response, verification, source, output)

    assert summary["status"] == module.READY
    assert summary["ready_to_run_saed_validation_intake"] is True
    assert summary["checksum_verified_pattern_count"] == 2
    assert summary["source_arrays_decoded"] is False
    assert summary["saed_external_evaluation_ready"] is False

    intake = json.loads(
        (output / "saed_external_validation_intake_draft.json").read_text(
            encoding="utf-8"
        )
    )
    assert intake["case_id"] == module.INTAKE_CASE_ID
    assert intake["dataset"]["identity_provenance"] == (
        "operator_assigned_at_acquisition"
    )
    assert intake["evaluation_protocol"]["source_metadata_review_status"] == (
        "not_run"
    )
    assert intake["evaluation_protocol"]["analysis_parameters_frozen"] is False
    assert intake["evaluation_protocol"]["reference_type"] == "curated_structures"
    assert all(
        pattern["calibration_method"] == "reciprocal_nm_inv_per_pixel"
        for pattern in intake["patterns"]
    )

    artifacts = json.loads(
        (output / "saed_transfer_verification_artifact_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifacts["artifact_count"] == 5
    for record in artifacts["artifacts"]:
        path = output / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert _sha(path) == record["sha256"]


def test_pattern_checksum_mismatch_fails_without_partial_output(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    (source / "patterns" / "pattern_001.tif").write_bytes(b"tampered")
    output = tmp_path / "output"

    with pytest.raises(
        module.SAEDTransferVerificationError,
        match="byte mismatch|SHA-256 mismatch",
    ):
        module.verify_transfer(response, verification, source, output)

    assert not output.exists()


def test_response_bundle_tampering_is_rejected(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    (response / "saed_independent_source_response_assessment.md").write_text(
        "# Tampered\n", encoding="utf-8"
    )

    with pytest.raises(
        module.SAEDTransferVerificationError,
        match="byte mismatch|SHA-256 mismatch",
    ):
        module.verify_transfer(
            response, verification, source, tmp_path / "output"
        )


def test_pattern_verification_set_must_match_declaration(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    payload = json.loads(verification.read_text(encoding="utf-8"))
    payload["pattern_verifications"] = payload["pattern_verifications"][:1]
    _write_json(verification, payload)

    with pytest.raises(
        module.SAEDTransferVerificationError,
        match="exactly match declared patterns",
    ):
        module.verify_transfer(
            response, verification, source, tmp_path / "output"
        )


def test_creator_overlap_preserved_as_blocker(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    payload = json.loads(verification.read_text(encoding="utf-8"))
    payload["dataset_verification"][
        "creator_overlap_with_analyzer_development_source"
    ] = True
    _write_json(verification, payload)

    summary = module.verify_transfer(
        response, verification, source, tmp_path / "output"
    )

    assert summary["status"] == module.BLOCKED
    assert summary["ready_to_run_saed_validation_intake"] is False
    assert "creator_overlap_with_analyzer_development_source" in summary[
        "blockers"
    ]
    assert (tmp_path / "output" / "saed_external_validation_intake_draft.json").is_file()


def test_parameter_selection_reuse_preserved_as_blocker(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    payload = json.loads(verification.read_text(encoding="utf-8"))
    payload["pattern_verifications"][0]["used_for_center_selection"] = True
    _write_json(verification, payload)

    summary = module.verify_transfer(
        response, verification, source, tmp_path / "output"
    )

    assert summary["status"] == module.BLOCKED
    assert "active_pattern_reused_for_parameter_selection" in summary["blockers"]
