from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.evidence_ladder import LEVELS, evaluate_evidence_ladder
from mca.handoff_bundle_builder import (
    HandoffBundleBuildError,
    build_characterization_handoff_bundle_from_config,
)
from mca.handoff_bundle_validation import (
    HandoffBundleValidationError,
    validate_characterization_handoff_bundle,
)
from mca.handoff_evidence_ladder import EvidenceLadderHandoffError
from mca.provenance import sha256_file

CASE_ID = "autonomous-research-handoff-case"


def _feature() -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-raman",
        "instrument": "raman",
        "feature_name": "candidate_count",
        "feature_label": None,
        "value": 2.0,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "producer-local/raman.txt",
        "source_sha256": "a" * 64,
        "preprocessing_id": "raman-preprocessing-v1",
        "quality_flag": "review_required",
    }


def _level(assessment: str) -> dict[str, object]:
    return {
        "assessment": assessment,
        "evidence": ["verified evidence"] if assessment == "Supported" else [],
        "limitations": [],
    }


def _write_inputs(
    tmp_path: Path,
    *,
    include_ladder: bool = True,
    declaration_id: str = CASE_ID,
    modality: str = "raman",
    wrong_binding_role: str | None = None,
    tamper_assessment_summary: bool = False,
) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source_path = evidence / "source_manifest.json"
    analysis_path = evidence / "analysis_manifest.json"
    comparability_path = evidence / "comparability_matrix.csv"

    source_path.write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    analysis_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.10.0",
                        "features": [_feature()],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(comparability_path, index=False)

    config: dict[str, object] = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
        "evidence_level": "Diagnostic",
        "sample_context_rows": [
            {
                "sample_id": "sample-a",
                "identical_physical_aliquot_confirmed": False,
            }
        ],
        "scientific_boundary": {
            "primary_limitation": "independent validation is not established"
        },
        "evidence": {
            "source_manifest": "evidence/source_manifest.json",
            "analysis_manifest": "evidence/analysis_manifest.json",
            "comparability_matrix": "evidence/comparability_matrix.csv",
        },
    }

    if include_ladder:
        binding_shas = {
            "source_manifest": sha256_file(source_path),
            "analysis_manifest": sha256_file(analysis_path),
            "comparability_matrix": sha256_file(comparability_path),
        }
        if wrong_binding_role is not None:
            binding_shas[wrong_binding_role] = "f" * 64
        declaration = {
            "schema_version": "1.0",
            "declaration_id": declaration_id,
            "subject": {
                "modality": modality,
                "source_material_domain": "reference-material",
                "target_material_domain": "target-material",
                "claim_scope": "method_validation",
            },
            "source_bindings": [
                {"role": role, "sha256": binding_shas[role]}
                for role in sorted(binding_shas)
            ],
            "levels": {
                level: _level("Supported" if index <= 4 else "Unsupported")
                for index, level in enumerate(LEVELS)
            },
            "limitations": ["target-material and independent validation remain open"],
        }
        assessment = evaluate_evidence_ladder(declaration)
        if tamper_assessment_summary:
            assessment["first_blocking_level"] = "L6_independent_external_validation"
        assessment_path = evidence / "evidence_ladder_assessment.json"
        assessment_path.write_text(
            json.dumps(assessment, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        config["scientific_evidence_ladder"] = (
            "evidence/evidence_ladder_assessment.json"
        )

    config_path = tmp_path / "handoff_config.json"
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def test_builder_exports_independently_replayed_ladder_without_promotion(
    tmp_path: Path,
) -> None:
    result = build_characterization_handoff_bundle_from_config(
        _write_inputs(tmp_path),
        tmp_path / "bundle",
    )

    validation = result["validation"]
    assert validation["scientific_evidence_ladder_present"] is True
    ladder = validation["scientific_evidence_ladder"]
    assert ladder["declaration_id"] == CASE_ID
    assert ladder["highest_contiguous_supported_level"] == "L4_method_algorithm_validation"
    assert ladder["first_blocking_level"] == "L5_material_domain_validation"
    assert ladder["scientific_status_promoted"] is False
    assert ladder["downstream_use_authorized"] is False
    binding = validation["scientific_evidence_ladder_bundle_binding"]
    assert binding["case_id_bound"] is True
    assert binding["source_digests_bound"] is True
    assert binding["subject_modality_bound"] is True
    assert validation["scientific_comparability_established"] is False
    assert validation["engineering_release_ready"] is False


def test_legacy_bundle_without_ladder_remains_valid(tmp_path: Path) -> None:
    result = build_characterization_handoff_bundle_from_config(
        _write_inputs(tmp_path, include_ladder=False),
        tmp_path / "bundle",
    )
    validation = result["validation"]
    assert validation["scientific_evidence_ladder_present"] is False
    assert validation["scientific_evidence_ladder"] is None
    assert validation["scientific_evidence_ladder_bundle_binding"] is None


def test_assessment_file_tamper_fails_checksum_validation(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_characterization_handoff_bundle_from_config(_write_inputs(tmp_path), output)
    assessment_path = output / "evidence_ladder_assessment.json"
    assessment_path.write_text(
        assessment_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(HandoffBundleValidationError, match="checksum mismatch"):
        validate_characterization_handoff_bundle(output)


def test_manifest_ladder_summary_substitution_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_characterization_handoff_bundle_from_config(_write_inputs(tmp_path), output)
    manifest_path = output / "characterization_handoff_bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scientific_evidence_ladder"]["first_blocking_level"] = (
        "L6_independent_external_validation"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(HandoffBundleValidationError, match="manifest summary"):
        validate_characterization_handoff_bundle(output)


def test_assessment_self_summary_substitution_is_replayed_not_trusted(tmp_path: Path) -> None:
    with pytest.raises(EvidenceLadderHandoffError, match="deterministic replay"):
        build_characterization_handoff_bundle_from_config(
            _write_inputs(tmp_path, tamper_assessment_summary=True),
            tmp_path / "bundle",
        )


def test_ladder_case_source_and_modality_substitutions_fail_closed(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    with pytest.raises(EvidenceLadderHandoffError, match="declaration_id"):
        build_characterization_handoff_bundle_from_config(
            _write_inputs(case_root, declaration_id="other-case"),
            case_root / "bundle",
        )

    source_root = tmp_path / "source"
    source_root.mkdir()
    with pytest.raises(EvidenceLadderHandoffError, match="source binding"):
        build_characterization_handoff_bundle_from_config(
            _write_inputs(source_root, wrong_binding_role="comparability_matrix"),
            source_root / "bundle",
        )

    modality_root = tmp_path / "modality"
    modality_root.mkdir()
    with pytest.raises(EvidenceLadderHandoffError, match="modality"):
        build_characterization_handoff_bundle_from_config(
            _write_inputs(modality_root, modality="xrd"),
            modality_root / "bundle",
        )


def test_ladder_input_basename_collision_fails_before_copy(tmp_path: Path) -> None:
    config_path = _write_inputs(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["scientific_evidence_ladder"] = "evidence/source_manifest.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(HandoffBundleBuildError, match="basenames must be unique"):
        build_characterization_handoff_bundle_from_config(
            config_path,
            tmp_path / "bundle",
        )
