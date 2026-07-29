from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from mca.tem_external_validation_candidate_assessment import (
    DOMAIN_SHIFT_STATUS,
    RESULT,
    CandidateAssessmentConfig,
    DatasetPair,
    load_config,
    run_candidate_assessment,
    validate_public_config,
)


def _fixture() -> CandidateAssessmentConfig:
    config = CandidateAssessmentConfig(
        case_id="fixture_candidate_assessment",
        repository="fixture",
        doi="10.0000/fixture",
        published_date="2026-01-01",
        version_label="v1",
        license="fixture-only",
        total_size_gb=1.0,
        raw_image_count=3,
        curated_pair_count=2,
        materials=("Au", "Ag"),
        substrates=("C",),
        pixel_size_nm_range=(0.02, 0.04),
        electron_dose_e_per_a2_range=(80.0, 100.0),
        particle_diameter_nm_range=(2.0, 5.0),
        microscope="fixture microscope",
        camera="fixture camera",
        raw_image_shape=(4096, 4096),
        labeler_count=1,
        annotation_tool="fixture tool",
        image_dataset_key="images",
        label_dataset_key="labels",
        preprocessing_steps=("standardization", "patching"),
        target_material="cobalt oxide",
        overlapping_creator_names=("Shared Author",),
        immutable_cross_dataset_lineage_manifest_available=False,
        verified_not_used_for_target_model_training=False,
        pairs=(
            DatasetPair(
                pair_id="larger",
                material="Au",
                image_file="Larger_Images.h5",
                image_size_mb=20.0,
                label_file="Larger_Labels.h5",
                label_size_mb=10.0,
            ),
            DatasetPair(
                pair_id="smaller",
                material="Ag",
                image_file="Smaller_Images.h5",
                image_size_mb=8.0,
                label_file="Smaller_Labels.h5",
                label_size_mb=4.0,
            ),
        ),
    )
    config.validate()
    return config


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_public_config_is_pinned() -> None:
    config = load_config(
        "case_studies/dryad_hrtem_external_validation_candidate_assessment/"
        "case_config.json"
    )
    validate_public_config(config)
    assert config.doi == "10.7941/D1SP93"
    assert config.raw_image_count == 407
    assert config.curated_pair_count == 13
    assert config.materials == ("Au", "Ag", "CdSe")
    assert config.target_material == "cobalt oxide"
    assert config.overlapping_creator_names == ("Mary Scott",)
    assert not config.immutable_cross_dataset_lineage_manifest_available
    assert not config.verified_not_used_for_target_model_training


def test_assessment_is_deterministic_and_blocks_in_domain_validation(
    tmp_path: Path,
) -> None:
    config = _fixture()
    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = run_candidate_assessment(config, first)
    run_candidate_assessment(config, second)
    assert _artifact_hashes(first) == _artifact_hashes(second)
    assert summary["readiness"]["status"] == RESULT
    assert summary["readiness"]["cross_material_domain_shift_status"] == (
        DOMAIN_SHIFT_STATUS
    )
    assert not summary["readiness"]["model_evaluation_allowed_now"]
    assert summary["result_counts"] == {
        "candidate_pair_count": 2,
        "in_domain_material_pair_count": 0,
        "cross_material_pair_count": 2,
        "independent_in_domain_external_validation_pair_count": 0,
    }
    assert summary["pilot_recommendation"]["pair_id"] == "smaller"
    assert summary["pilot_recommendation"]["combined_size_mb"] == 12.0
    assert summary["scientific_closeout"]["status"] == "Diagnostic"
    assert all(value is False for value in summary["processing"].values())

    inventory = pd.read_csv(
        first / "tem_external_validation_candidate_inventory.csv"
    )
    assert len(inventory) == 2
    assert not inventory["in_domain_material_match"].any()
    assert set(inventory["candidate_status"]) == {DOMAIN_SHIFT_STATUS}

    manifest = json.loads(
        (first / "external_validation_candidate_artifact_manifest.json").read_text()
    )
    assert manifest["artifact_count"] == 3
    for record in manifest["artifacts"]:
        path = first / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_invalid_inventory_unknown_config_and_output_fail_closed(
    tmp_path: Path,
) -> None:
    config = _fixture()
    duplicate = CandidateAssessmentConfig(
        **{
            **config.__dict__,
            "pairs": (config.pairs[0], config.pairs[0]),
        }
    )
    with pytest.raises(ValueError, match="pair_id values must be unique"):
        duplicate.validate()

    bad_material = CandidateAssessmentConfig(
        **{
            **config.__dict__,
            "pairs": (
                DatasetPair(
                    pair_id="bad",
                    material="CdSe",
                    image_file="Bad_Images.h5",
                    image_size_mb=1,
                    label_file="Bad_Labels.h5",
                    label_size_mb=1,
                ),
                config.pairs[1],
            ),
        }
    )
    with pytest.raises(ValueError, match="pair material is absent"):
        bad_material.validate()

    payload = json.loads(
        Path(
            "case_studies/dryad_hrtem_external_validation_candidate_assessment/"
            "case_config.json"
        ).read_text()
    )
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown config keys"):
        CandidateAssessmentConfig.from_mapping(payload)

    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_candidate_assessment(config, output)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_assessment_contains_no_model_or_physical_measurement() -> None:
    text = Path(
        "src/mca/tem_external_validation_candidate_assessment.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "import torch",
        "import tensorflow",
        ".fit(",
        ".predict(",
        "segmentation_accuracy =",
        "particle_diameter_nm =",
    )
    for token in forbidden:
        assert token not in text
    assert '"model_training_performed": False' in text
    assert '"model_inference_performed": False' in text
    assert '"segmentation_accuracy_computed": False' in text
