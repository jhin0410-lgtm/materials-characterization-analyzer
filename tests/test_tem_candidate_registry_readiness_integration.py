from __future__ import annotations

import json
from pathlib import Path

import pytest

from mca.tem_candidate_registry_readiness import (
    build_tem_segmentation_readiness_with_registry,
)
from mca.tem_segmentation_readiness import EvidenceContractError, NOT_READY


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def _training() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "public_cobalt_oxide_tem_training_data_audit",
        "software_version": "0.9.3",
        "value_contract": {
            "all_images_finite": True,
            "all_labels_finite": True,
            "labels_binary": True,
            "label_channels_complementary_one_hot": True,
        },
        "notebook_split_audit": {"independent_parent_image_validation": False},
        "candidate_parent_grouping": {"authoritative_parent_ids_available": False},
        "result_counts": {"patch_pair_count": 256},
    }


def _parent() -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "public_cobalt_oxide_tem_parent_overlap_audit",
        "software_version": "0.9.3",
        "external_validation_readiness": {
            "source_masks_are_independent_ground_truth": False,
            "parent_disjointness_proven_for_nonmatching_frames": False,
        },
        "result_counts": {"independent_external_validation_candidate_count": 0},
    }


def _registry() -> dict:
    action = (
        "Exclude this public archive from independent segmentation validation. "
        "Acquire or obtain author-released raw cobalt-oxide TEM detector data with "
        "immutable sample/acquisition lineage before blinded annotation."
    )
    return {
        "schema_version": "1.0",
        "case_id": "tem_external_validation_candidate_registry",
        "software_version": "0.9.3",
        "result_counts": {"in_domain_external_validation_ready_count": 0},
        "readiness": {
            "candidate_search_completed_for_snapshot": True,
            "independent_in_domain_external_validation_available": False,
            "public_search_supports_model_evaluation_now": False,
            "recommended_candidate_id": "mendeley_8w66synjmx_cop_co2p_co3o4",
            "recommended_candidate_status": "excluded_rendered_figure_representation",
            "recommended_next_action": action,
        },
    }


def test_registry_refines_next_action_without_granting_evaluation(
    tmp_path: Path,
) -> None:
    training = _write(tmp_path / "training.json", _training())
    parent = _write(tmp_path / "parent.json", _parent())
    registry = _write(tmp_path / "registry.json", _registry())
    output = tmp_path / "out"
    summary = build_tem_segmentation_readiness_with_registry(
        training_summary_path=training,
        parent_overlap_summary_path=parent,
        candidate_registry_summary_path=registry,
        output_dir=output,
    )

    gates = summary["evidence_gates"]
    decision = summary["decision"]
    assert decision["status"] == NOT_READY
    assert not decision["scientific_in_domain_performance_evaluation_ready"]
    assert gates["candidate_registry_supplied"]
    assert gates["candidate_registry_search_completed_for_snapshot"]
    assert gates["candidate_registry_in_domain_ready_count"] == 0
    assert not gates["candidate_registry_supports_model_evaluation_now"]
    assert "Acquire or obtain" in decision["next_action"]
    assert "public_candidate_registry_has_no_evaluation_ready_set" in gates[
        "unresolved_evidence"
    ]
    manifest = json.loads(
        (output / "tem_segmentation_readiness_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["input_count"] == 3
    assert any(
        record["role"] == "external_validation_candidate_registry"
        for record in manifest["inputs"]
    )



def test_malformed_registry_fails_before_any_output_is_written(tmp_path: Path) -> None:
    training = _write(tmp_path / "training.json", _training())
    parent = _write(tmp_path / "parent.json", _parent())
    malformed = _registry()
    del malformed["readiness"]["recommended_next_action"]
    registry = _write(tmp_path / "registry.json", malformed)
    output = tmp_path / "out"
    with pytest.raises(EvidenceContractError, match="recommended_next_action"):
        build_tem_segmentation_readiness_with_registry(
            training_summary_path=training,
            parent_overlap_summary_path=parent,
            candidate_registry_summary_path=registry,
            output_dir=output,
        )
    assert not output.exists()
