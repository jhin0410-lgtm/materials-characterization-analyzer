from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from mca.evidence_ladder import LEVELS, evaluate_evidence_ladder
from mca.handoff_bundle_builder import build_characterization_handoff_bundle_from_config
from mca.handoff_bundle_validation import (
    HandoffBundleValidationError,
    validate_characterization_handoff_bundle,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _write_base_evidence(tmp_path: Path) -> dict[str, Path]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source_manifest = evidence / "source_manifest.json"
    source_manifest.write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    analysis_manifest = evidence / "analysis_manifest.json"
    analysis_manifest.write_text(
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
    comparability_matrix = evidence / "comparability_matrix.csv"
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(comparability_matrix, index=False)
    return {
        "source_manifest": source_manifest,
        "analysis_manifest": analysis_manifest,
        "comparability_matrix": comparability_matrix,
    }


def _assessment(
    evidence: dict[str, Path],
    *,
    case_id: str = "generic-handoff-test",
    modality: str = "raman",
    supported_through: int = 4,
) -> dict[str, object]:
    levels: dict[str, dict[str, object]] = {}
    for index, level in enumerate(LEVELS):
        supported = index <= supported_through
        levels[level] = {
            "assessment": "Supported" if supported else "Unsupported",
            "evidence": [f"verified {level}"] if supported else [],
            "limitations": [] if supported else [f"unresolved {level}"],
        }
    declaration = {
        "schema_version": "1.0",
        "declaration_id": case_id,
        "subject": {
            "modality": modality,
            "source_material_domain": "reference-material",
            "target_material_domain": "target-material",
            "claim_scope": "method_validation",
        },
        "source_bindings": [
            {"role": role, "sha256": _sha256(path)}
            for role, path in sorted(evidence.items())
        ],
        "levels": levels,
        "limitations": ["Assessment maturity does not authorize downstream use."],
    }
    return evaluate_evidence_ladder(declaration)


def _write_config(
    tmp_path: Path,
    *,
    ladder: dict[str, object] | None,
) -> Path:
    evidence = _write_base_evidence(tmp_path)
    ladder_path: Path | None = None
    if ladder is not None:
        ladder_path = tmp_path / "ladder_assessment.json"
        ladder_path.write_text(
            json.dumps(ladder, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "case_id": "generic-handoff-test",
        "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
        "evidence_level": "Diagnostic",
        "sample_context_rows": [{"sample_id": "sample-a"}],
        "scientific_boundary": {
            "primary_limitation": "scientific maturity remains explicitly bounded"
        },
        "evidence": {
            "source_manifest": "evidence/source_manifest.json",
            "analysis_manifest": "evidence/analysis_manifest.json",
            "comparability_matrix": "evidence/comparability_matrix.csv",
        },
    }
    if ladder_path is not None:
        payload["scientific_evidence_ladder"] = ladder_path.name
    config = tmp_path / "handoff_config.json"
    config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config


def _configured_case(
    tmp_path: Path,
    *,
    case_id: str = "generic-handoff-test",
    modality: str = "raman",
    supported_through: int = 4,
) -> Path:
    evidence = _write_base_evidence(tmp_path)
    ladder = _assessment(
        evidence,
        case_id=case_id,
        modality=modality,
        supported_through=supported_through,
    )
    ladder_path = tmp_path / "ladder_assessment.json"
    ladder_path.write_text(
        json.dumps(ladder, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": "1.0",
        "case_id": "generic-handoff-test",
        "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
        "evidence_level": "Diagnostic",
        "sample_context_rows": [{"sample_id": "sample-a"}],
        "scientific_boundary": {
            "primary_limitation": "scientific maturity remains explicitly bounded"
        },
        "evidence": {
            "source_manifest": "evidence/source_manifest.json",
            "analysis_manifest": "evidence/analysis_manifest.json",
            "comparability_matrix": "evidence/comparability_matrix.csv",
        },
        "scientific_evidence_ladder": ladder_path.name,
    }
    config = tmp_path / "handoff_config.json"
    config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config


def test_valid_ladder_is_replayed_and_cross_bound_to_bundle(tmp_path: Path) -> None:
    config = _configured_case(tmp_path, supported_through=4)

    result = build_characterization_handoff_bundle_from_config(
        config,
        tmp_path / "bundle",
    )

    validation = result["validation"]
    assert validation["scientific_evidence_ladder_present"] is True
    ladder = validation["scientific_evidence_ladder"]
    assert ladder["highest_contiguous_supported_level"] == "L4_method_algorithm_validation"
    assert ladder["first_blocking_level"] == "L5_material_domain_validation"
    assert ladder["scientific_status_promoted"] is False
    assert ladder["downstream_use_authorized"] is False
    binding = validation["scientific_evidence_ladder_bundle_binding"]
    assert binding["case_id_bound"] is True
    assert binding["source_digests_bound"] is True
    assert binding["subject_modality_bound"] is True
    assert binding["required_source_roles"] == [
        "analysis_manifest",
        "comparability_matrix",
        "source_manifest",
    ]


def test_legacy_bundle_without_ladder_remains_valid(tmp_path: Path) -> None:
    config = _write_config(tmp_path, ladder=None)

    result = build_characterization_handoff_bundle_from_config(
        config,
        tmp_path / "bundle",
    )

    assert result["validation"]["scientific_evidence_ladder_present"] is False
    assert result["validation"]["scientific_evidence_ladder"] is None
    assert result["validation"]["scientific_evidence_ladder_bundle_binding"] is None


def test_whole_assessment_case_substitution_is_rejected(tmp_path: Path) -> None:
    config = _configured_case(tmp_path, case_id="different-case")

    with pytest.raises(HandoffBundleValidationError, match="declaration_id"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_whole_assessment_source_substitution_is_rejected(tmp_path: Path) -> None:
    evidence = _write_base_evidence(tmp_path)
    ladder = _assessment(evidence)
    ladder["declaration"]["source_bindings"][0]["sha256"] = "f" * 64
    ladder = evaluate_evidence_ladder(ladder["declaration"])
    ladder_path = tmp_path / "ladder_assessment.json"
    ladder_path.write_text(json.dumps(ladder), encoding="utf-8")
    config = tmp_path / "handoff_config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "generic-handoff-test",
                "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
                "evidence_level": "Diagnostic",
                "sample_context_rows": [{"sample_id": "sample-a"}],
                "scientific_boundary": {"primary_limitation": "test"},
                "evidence": {
                    "source_manifest": "evidence/source_manifest.json",
                    "analysis_manifest": "evidence/analysis_manifest.json",
                    "comparability_matrix": "evidence/comparability_matrix.csv",
                },
                "scientific_evidence_ladder": ladder_path.name,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffBundleValidationError, match="source binding mismatch"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_subject_modality_substitution_is_rejected(tmp_path: Path) -> None:
    config = _configured_case(tmp_path, modality="xrd")

    with pytest.raises(HandoffBundleValidationError, match="subject.modality"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_manifest_summary_substitution_is_rejected_after_build(tmp_path: Path) -> None:
    config = _configured_case(tmp_path)
    output = tmp_path / "bundle"
    build_characterization_handoff_bundle_from_config(config, output)
    manifest_path = output / "characterization_handoff_bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scientific_evidence_ladder"]["first_blocking_level"] = (
        "L8_engineering_decision_readiness"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(HandoffBundleValidationError, match="manifest summary"):
        validate_characterization_handoff_bundle(output)


def test_assessment_byte_tamper_is_rejected_after_build(tmp_path: Path) -> None:
    config = _configured_case(tmp_path)
    output = tmp_path / "bundle"
    result = build_characterization_handoff_bundle_from_config(config, output)
    ladder_path = Path(result["scientific_evidence_ladder_assessment"])
    ladder_path.write_text(ladder_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(HandoffBundleValidationError, match="checksum mismatch"):
        validate_characterization_handoff_bundle(output)
