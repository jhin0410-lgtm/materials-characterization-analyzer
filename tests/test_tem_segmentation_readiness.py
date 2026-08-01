from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mca.cli_entry import main as cli_main
from mca.tem_segmentation_readiness import (
    CROSS_MATERIAL_READY,
    NOT_READY,
    TRAINING_BLOCKED,
    EvidenceContractError,
    build_tem_segmentation_readiness,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _training(*, integrity: bool = True) -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "public_cobalt_oxide_tem_training_data_audit",
        "software_version": "0.9.3",
        "value_contract": {
            "all_images_finite": integrity,
            "all_labels_finite": True,
            "labels_binary": True,
            "label_channels_complementary_one_hot": True,
        },
        "notebook_split_audit": {
            "independent_parent_image_validation": False,
            "performance_claim_ready": False,
        },
        "candidate_parent_grouping": {
            "authoritative_parent_ids_available": False,
        },
        "result_counts": {"patch_pair_count": 256},
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": "not_ready_for_independent_model_performance_claims",
        },
    }


def _parent_overlap() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "public_cobalt_oxide_tem_parent_overlap_audit",
        "software_version": "0.9.3",
        "external_validation_readiness": {
            "source_masks_are_independent_ground_truth": False,
            "parent_disjointness_proven_for_nonmatching_frames": False,
        },
        "result_counts": {
            "independent_external_validation_candidate_count": 0,
        },
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": "no_independent_external_validation_set_available",
        },
    }


def _external_candidate() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "dryad_hrtem_external_validation_candidate_assessment",
        "software_version": "0.9.2",
        "result_counts": {
            "independent_in_domain_external_validation_pair_count": 0,
        },
        "target_comparison": {
            "gates": {
                "target_material_match": False,
                "immutable_cross_dataset_lineage_manifest_available": False,
                "verified_not_used_for_target_model_training": False,
                "creator_overlap_with_target_dataset": True,
                "multi_labeler_or_adjudication_evidence_available": False,
            }
        },
        "readiness": {"model_evaluation_allowed_now": False},
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": "not_ready_for_in_domain_external_validation",
        },
    }


def _pilot_readiness() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "dryad_hrtem_pilot_pair_audit",
        "status": "blocked_missing_dryad_api_token",
        "authenticated_real_data_download_available": False,
        "live_metadata_and_source_version_verified": True,
        "real_hdf5_audit_performed": False,
        "real_content_overlap_audit_performed": False,
    }


def _pilot_summary() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "dryad_hrtem_pilot_pair_audit",
        "software_version": "0.9.3",
        "readiness": {
            "content_overlap_gate_passed": True,
            "next_status": (
                "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"
            ),
        },
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": (
                "eligible_to_freeze_diagnostic_cross_material_stress_test_protocol"
            ),
        },
    }


def _paths(tmp_path: Path, *, integrity: bool = True) -> dict[str, Path]:
    return {
        "training": _write(tmp_path / "training.json", _training(integrity=integrity)),
        "parent": _write(tmp_path / "parent.json", _parent_overlap()),
        "candidate": _write(tmp_path / "candidate.json", _external_candidate()),
        "pilot_readiness": _write(
            tmp_path / "pilot-readiness.json", _pilot_readiness()
        ),
    }


def test_current_evidence_blocks_scientific_evaluation_but_allows_software_experiment(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    output = tmp_path / "out"
    summary = build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        external_candidate_summary_path=paths["candidate"],
        pilot_readiness_path=paths["pilot_readiness"],
        output_dir=output,
    )

    decision = summary["decision"]
    assert decision["status"] == NOT_READY
    assert decision["software_experiment_training_allowed"]
    assert not decision["scientific_in_domain_performance_evaluation_ready"]
    assert not decision["independent_performance_claim_ready"]
    assert not decision["diagnostic_cross_material_stress_test_ready"]
    assert not decision["model_retraining_is_current_priority"]
    assert summary["scientific_closeout"]["status"] == "Supported"
    assert summary["evidence_gates"]["external_pilot_metadata_verified"]
    assert "independent_in_domain_cobalt_oxide_validation_set" in summary[
        "evidence_gates"
    ]["unresolved_evidence"]
    assert "authenticated_external_pilot_hdf5_and_overlap_audit" in summary[
        "evidence_gates"
    ]["unresolved_evidence"]

    manifest = json.loads(
        (output / "tem_segmentation_readiness_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["input_count"] == 4
    assert manifest["artifact_count"] == 2
    for record in manifest["inputs"]:
        source = next(path for path in paths.values() if path.name == record["path"])
        assert record["bytes"] == source.stat().st_size
        assert record["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    for record in manifest["artifacts"]:
        artifact = output / record["path"]
        assert record["bytes"] == artifact.stat().st_size
        assert record["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_cross_material_pilot_never_becomes_in_domain_validation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    pilot_summary = _write(tmp_path / "pilot-summary.json", _pilot_summary())
    summary = build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        external_candidate_summary_path=paths["candidate"],
        pilot_readiness_path=paths["pilot_readiness"],
        pilot_summary_path=pilot_summary,
        output_dir=tmp_path / "out",
    )
    assert summary["decision"]["status"] == CROSS_MATERIAL_READY
    assert summary["decision"]["diagnostic_cross_material_stress_test_ready"]
    assert not summary["decision"][
        "scientific_in_domain_performance_evaluation_ready"
    ]
    assert not summary["decision"]["independent_performance_claim_ready"]


def test_training_integrity_failure_blocks_all_training(tmp_path: Path) -> None:
    paths = _paths(tmp_path, integrity=False)
    summary = build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        output_dir=tmp_path / "out",
    )
    assert summary["decision"]["status"] == TRAINING_BLOCKED
    assert not summary["decision"]["software_experiment_training_allowed"]


def test_optional_evidence_is_unresolved_not_assumed(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    summary = build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        output_dir=tmp_path / "out",
    )
    unresolved = summary["evidence_gates"]["unresolved_evidence"]
    assert "external_candidate_assessment_not_supplied" in unresolved
    assert "external_pilot_readiness_not_supplied" in unresolved
    assert not summary["evidence_gates"]["external_candidate_assessment_supplied"]


def test_wrong_case_id_fails_closed(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    payload = json.loads(paths["training"].read_text(encoding="utf-8"))
    payload["case_id"] = "wrong_case"
    _write(paths["training"], payload)
    with pytest.raises(EvidenceContractError, match="case_id mismatch"):
        build_tem_segmentation_readiness(
            training_summary_path=paths["training"],
            parent_overlap_summary_path=paths["parent"],
            output_dir=tmp_path / "out",
        )


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    output = tmp_path / "out"
    build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        output_dir=output,
    )
    with pytest.raises(FileExistsError, match="absent or empty"):
        build_tem_segmentation_readiness(
            training_summary_path=paths["training"],
            parent_overlap_summary_path=paths["parent"],
            output_dir=output,
        )


def test_cli_dispatch_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path)
    output = tmp_path / "cli-out"
    result = cli_main(
        [
            "tem-readiness",
            "--training-summary",
            str(paths["training"]),
            "--parent-overlap-summary",
            str(paths["parent"]),
            "--external-candidate-summary",
            str(paths["candidate"]),
            "--pilot-readiness",
            str(paths["pilot_readiness"]),
            "--output",
            str(output),
        ]
    )
    assert result == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == NOT_READY
    assert (output / "tem_segmentation_readiness_report.md").is_file()
