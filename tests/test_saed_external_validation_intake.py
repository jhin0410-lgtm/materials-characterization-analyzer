from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mca.cli_entry import main as cli_main
from mca.saed_external_validation_intake import (
    BLOCKED,
    EVALUATION_READY,
    PROTOCOL_READY,
    SAEDIntakeContractError,
    compute_intake_manifest_sha256,
    load_intake_manifest,
    run_saed_external_validation_intake,
)


def _write_file(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _pattern(
    pattern_id: str,
    relative_path: str,
    sha256: str,
    sample_id: str,
    acquisition_id: str,
    *,
    representation: str = "raw_detector",
    original_intensity: bool = True,
    used_for_center_selection: bool = False,
) -> dict:
    return {
        "pattern_id": pattern_id,
        "relative_path": relative_path,
        "sha256": sha256,
        "sample_id": sample_id,
        "acquisition_id": acquisition_id,
        "material_id": "co3o4",
        "representation": representation,
        "original_detector_intensity_available": original_intensity,
        "file_format": "TIFF",
        "accelerating_voltage_kv": 200.0,
        "camera_length_mm": 800.0,
        "detector_model": "source-declared-camera",
        "detector_pixel_size_um": 14.0,
        "center_x_px": 256.0,
        "center_y_px": 256.0,
        "center_source": "source metadata",
        "calibration_method": "camera_constant_nm_pixel",
        "reciprocal_nm_inv_per_pixel": None,
        "camera_constant_nm_pixel": 58.75,
        "reference_d_nm": None,
        "reference_radius_px": None,
        "calibration_source": "source calibration record",
        "preprocessing_operations": ["none"],
        "used_for_center_selection": used_for_center_selection,
        "used_for_smoothing_selection": False,
        "used_for_prominence_selection": False,
        "used_for_radius_bound_selection": False,
        "used_for_candidate_count_selection": False,
        "excluded": False,
        "exclusion_reason": None,
    }


def _protocol(*, complete: bool = False) -> dict:
    return {
        "source_metadata_review_status": "passed" if complete else "not_run",
        "file_content_audit_status": "passed" if complete else "not_run",
        "calibration_review_status": "passed" if complete else "not_run",
        "acquisition_independence_review_status": (
            "passed" if complete else "not_run"
        ),
        "content_overlap_audit_status": "passed" if complete else "not_run",
        "analysis_parameters_frozen": complete,
        "indexing_protocol_frozen": complete,
        "reference_set_frozen": complete,
        "manifest_checksum_frozen": complete,
        "frozen_manifest_sha256": None,
        "frozen_protocol_id": "saed-eval-v1" if complete else None,
        "reference_type": "curated_structures" if complete else "none",
        "reference_identifier": "cod-validated-co3o4-v1" if complete else None,
        "metrics_frozen": complete,
        "uncertainty_method_frozen": complete,
        "exclusion_rules_frozen": complete,
    }


def _manifest(patterns: list[dict], *, complete: bool = False) -> dict:
    payload = {
        "schema_version": "1.0",
        "case_id": "saed_external_validation_intake",
        "dataset": {
            "dataset_id": "external-saed-001",
            "dataset_version": "v1",
            "source_type": "new_acquisition",
            "license": "institution-approved research use",
            "reuse_authorized": True,
            "identity_provenance": "operator_assigned_at_acquisition",
            "material_identity_source": "operator sample log",
            "target_analyzer_development_nonuse_attested": True,
            "creator_overlap_with_analyzer_development_source": False,
            "cross_dataset_lineage_independence_attested": True,
            "minimum_independent_samples": 2,
            "minimum_independent_acquisitions": 2,
        },
        "patterns": patterns,
        "evaluation_protocol": _protocol(complete=complete),
    }
    if complete:
        payload["evaluation_protocol"]["frozen_manifest_sha256"] = (
            compute_intake_manifest_sha256(payload)
        )
    return payload


def _write_manifest(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _two_patterns(root: Path) -> list[dict]:
    first = _write_file(root, "patterns/a.tif", b"synthetic-saed-a")
    second = _write_file(root, "patterns/b.tif", b"synthetic-saed-b")
    return [
        _pattern("pattern-a", "patterns/a.tif", first, "sample-a", "acq-a"),
        _pattern("pattern-b", "patterns/b.tif", second, "sample-b", "acq-b"),
    ]


def test_checksum_bound_patterns_are_ready_to_freeze_protocol(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    manifest = load_intake_manifest(
        _write_manifest(tmp_path / "manifest.json", _manifest(_two_patterns(root)))
    )
    output = tmp_path / "out"
    summary = run_saed_external_validation_intake(manifest, root, output)

    assert summary["decision"]["status"] == PROTOCOL_READY
    assert summary["decision"]["saed_protocol_freeze_ready"]
    assert not summary["decision"][
        "predeclared_saed_external_evaluation_ready"
    ]
    assert not summary["decision"]["crystallographic_performance_claim_ready"]
    assert summary["result_counts"]["sample_count"] == 2
    assert summary["result_counts"]["acquisition_count"] == 2

    artifacts = json.loads(
        (output / "saed_validation_intake_artifact_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifacts["artifact_count"] == 3
    for record in artifacts["artifacts"]:
        path = output / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_rendered_or_non_original_patterns_are_blocked(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    patterns = _two_patterns(root)
    for pattern in patterns:
        pattern["representation"] = "rendered_figure"
        pattern["original_detector_intensity_available"] = False
    summary = run_saed_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(patterns))
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == BLOCKED
    assert "raw_or_lossless_representation" in summary["evidence_gates"][
        "unresolved_evidence"
    ]
    assert "original_detector_intensity_available" in summary[
        "evidence_gates"
    ]["unresolved_evidence"]


def test_duplicate_active_pattern_content_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    digest_a = _write_file(root, "patterns/a.tif", b"same")
    digest_b = _write_file(root, "patterns/b.tif", b"same")
    patterns = [
        _pattern("pattern-a", "patterns/a.tif", digest_a, "sample-a", "acq-a"),
        _pattern("pattern-b", "patterns/b.tif", digest_b, "sample-b", "acq-b"),
    ]
    summary = run_saed_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(patterns))
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == BLOCKED
    assert summary["result_counts"][
        "duplicate_active_pattern_content_count"
    ] == 1


def test_parameter_selection_reuse_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    patterns = _two_patterns(root)
    patterns[0]["used_for_center_selection"] = True
    summary = run_saed_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(patterns))
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == BLOCKED
    assert "not_used_for_analyzer_parameter_selection" in summary[
        "evidence_gates"
    ]["unresolved_evidence"]


def test_inferred_identity_is_visible_and_blocked(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    payload = _manifest(_two_patterns(root))
    payload["dataset"]["identity_provenance"] = "inferred"
    summary = run_saed_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", payload)
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == BLOCKED
    assert "source_assigned_dataset_identity" in summary["evidence_gates"][
        "unresolved_evidence"
    ]


def test_complete_frozen_protocol_reaches_only_predeclared_evaluation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    payload = _manifest(_two_patterns(root), complete=True)
    summary = run_saed_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", payload)
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == EVALUATION_READY
    assert summary["decision"]["predeclared_saed_external_evaluation_ready"]
    assert not summary["decision"]["crystallographic_performance_claim_ready"]
    assert not summary["decision"]["engineering_release_ready"]


def test_frozen_manifest_mutation_fails_without_partial_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    payload = _manifest(_two_patterns(root), complete=True)
    payload["patterns"][0]["center_x_px"] = 255.0
    output = tmp_path / "out"
    with pytest.raises(
        SAEDIntakeContractError, match="frozen_manifest_sha256"
    ):
        run_saed_external_validation_intake(
            load_intake_manifest(
                _write_manifest(tmp_path / "manifest.json", payload)
            ),
            root,
            output,
        )
    assert not output.exists()


def test_checksum_mismatch_preserves_caller_empty_output(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    patterns = _two_patterns(root)
    patterns[0]["sha256"] = "0" * 64
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(SAEDIntakeContractError, match="SHA-256 mismatch"):
        run_saed_external_validation_intake(
            load_intake_manifest(
                _write_manifest(
                    tmp_path / "manifest.json", _manifest(patterns)
                )
            ),
            root,
            output,
        )
    assert output.is_dir()
    assert not any(output.iterdir())


def test_inconsistent_calibration_contract_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    patterns = _two_patterns(root)
    patterns[0]["camera_constant_nm_pixel"] = None
    with pytest.raises(
        SAEDIntakeContractError, match="camera_constant_nm_pixel"
    ):
        load_intake_manifest(
            _write_manifest(
                tmp_path / "manifest.json", _manifest(patterns)
            )
        )


def test_unsafe_relative_path_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    patterns = _two_patterns(root)
    patterns[0]["relative_path"] = "../escape.tif"
    with pytest.raises(SAEDIntakeContractError, match="safe relative"):
        load_intake_manifest(
            _write_manifest(
                tmp_path / "manifest.json", _manifest(patterns)
            )
        )


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}',
        encoding="utf-8",
    )
    with pytest.raises(SAEDIntakeContractError, match="duplicate JSON"):
        load_intake_manifest(path)


def test_cli_dispatch_writes_summary(tmp_path: Path, capsys) -> None:
    root = tmp_path / "data"
    root.mkdir()
    manifest = _write_manifest(
        tmp_path / "manifest.json", _manifest(_two_patterns(root))
    )
    output = tmp_path / "out"
    assert (
        cli_main(
            [
                "saed-validation-intake",
                "--manifest",
                str(manifest),
                "--data-root",
                str(root),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == PROTOCOL_READY
    assert printed["active_pattern_count"] == 2
    assert output.joinpath("saed_validation_intake_summary.json").is_file()
