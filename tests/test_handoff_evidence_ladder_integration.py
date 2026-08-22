from __future__ import annotations

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
from mca.provenance import sha256_file


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


def _write_case(tmp_path: Path, *, include_ladder: bool = True) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source = evidence / "source_manifest.json"
    analysis = evidence / "analysis_manifest.json"
    comparability = evidence / "comparability_matrix.csv"

    source.write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    analysis.write_text(
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
    ).to_csv(comparability, index=False)

    config: dict[str, object] = {
        "schema_version": "1.1" if include_ladder else "1.0",
        "case_id": "autonomous-research-ladder-test",
        "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
        "evidence_level": "Diagnostic",
        "sample_context_rows": [
            {
                "sample_id": "sample-a",
                "identical_physical_aliquot_confirmed": False,
            }
        ],
        "scientific_boundary": {
            "primary_limitation": "target-material validation is not established"
        },
        "evidence": {
            "source_manifest": "evidence/source_manifest.json",
            "analysis_manifest": "evidence/analysis_manifest.json",
            "comparability_matrix": "evidence/comparability_matrix.csv",
        },
    }

    if include_ladder:
        levels: dict[str, dict[str, object]] = {}
        for index, level in enumerate(LEVELS):
            supported = index <= 4
            levels[level] = {
                "assessment": "Supported" if supported else "Unsupported",
                "evidence": [f"verified {level}"] if supported else [],
                "limitations": [] if supported else [f"{level} is not yet established"],
            }
        declaration = {
            "schema_version": "1.0",
            "declaration_id": "autonomous-research-ladder-test",
            "subject": {
                "modality": "raman",
                "source_material_domain": "reference-material",
                "target_material_domain": "target-material",
                "claim_scope": "method_validation",
            },
            "source_bindings": [
                {"role": "source_manifest", "sha256": sha256_file(source)},
                {"role": "analysis_manifest", "sha256": sha256_file(analysis)},
                {"role": "comparability_matrix", "sha256": sha256_file(comparability)},
            ],
            "levels": levels,
            "limitations": ["The ladder identifies maturity only and authorizes no use."],
        }
        assessment = evaluate_evidence_ladder(declaration)
        ladder = evidence / "scientific_evidence_ladder_assessment.json"
        ladder.write_text(
            json.dumps(assessment, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        config["scientific_evidence_ladder"] = (
            "evidence/scientific_evidence_ladder_assessment.json"
        )

    config_path = tmp_path / "handoff_config.json"
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config_path


def test_schema_11_bundle_replays_ladder_and_exposes_first_blocker(tmp_path: Path) -> None:
    config = _write_case(tmp_path)
    output = tmp_path / "bundle"

    result = build_characterization_handoff_bundle_from_config(config, output)
    validation = result["validation"]

    assert result["config_schema_version"] == "1.1"
    assert validation["schema_version"] == "1.1"
    assert validation["scientific_evidence_ladder_present"] is True
    ladder = validation["scientific_evidence_ladder"]
    assert ladder["highest_contiguous_supported_level"] == "L4_method_algorithm_validation"
    assert ladder["first_blocking_level"] == "L5_material_domain_validation"
    assert ladder["scientific_status_promoted"] is False
    assert ladder["downstream_use_authorized"] is False
    assert validation["scientific_evidence_ladder_bundle_binding"] == {
        "case_id_bound": True,
        "required_source_roles": [
            "analysis_manifest",
            "comparability_matrix",
            "source_manifest",
        ],
        "source_digests_bound": True,
        "subject_modality_bound": True,
        "bundle_instruments": ["raman"],
    }


def test_legacy_schema_10_bundle_remains_valid_without_ladder(tmp_path: Path) -> None:
    config = _write_case(tmp_path, include_ladder=False)
    output = tmp_path / "bundle"

    result = build_characterization_handoff_bundle_from_config(config, output)
    validation = result["validation"]

    assert result["config_schema_version"] == "1.0"
    assert validation["schema_version"] == "1.0"
    assert validation["scientific_evidence_ladder_present"] is False
    assert validation["scientific_evidence_ladder"] is None


def test_ladder_artifact_tamper_fails_closed(tmp_path: Path) -> None:
    config = _write_case(tmp_path)
    output = tmp_path / "bundle"
    result = build_characterization_handoff_bundle_from_config(config, output)
    ladder_path = Path(result["scientific_evidence_ladder_assessment"])

    ladder_path.write_text(ladder_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(HandoffBundleValidationError, match="checksum mismatch"):
        validate_characterization_handoff_bundle(output)


def test_manifest_ladder_summary_substitution_fails_closed(tmp_path: Path) -> None:
    config = _write_case(tmp_path)
    output = tmp_path / "bundle"
    build_characterization_handoff_bundle_from_config(config, output)
    manifest_path = output / "characterization_handoff_bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scientific_evidence_ladder"]["first_blocking_level"] = (
        "L6_independent_external_validation"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HandoffBundleValidationError, match="manifest summary"):
        validate_characterization_handoff_bundle(output)


def test_ladder_source_binding_substitution_is_rejected_during_build(tmp_path: Path) -> None:
    config = _write_case(tmp_path)
    ladder_path = tmp_path / "evidence" / "scientific_evidence_ladder_assessment.json"
    assessment = json.loads(ladder_path.read_text(encoding="utf-8"))
    assessment["declaration"]["source_bindings"][0]["sha256"] = "f" * 64
    replay_input = {
        "schema_version": assessment["declaration"]["schema_version"],
        "declaration_id": assessment["declaration"]["declaration_id"],
        "subject": assessment["declaration"]["subject"],
        "source_bindings": assessment["declaration"]["source_bindings"],
        "levels": {
            level: {
                "assessment": assessment["declaration"]["levels"][level]["assessment"],
                "evidence": assessment["declaration"]["levels"][level]["evidence"],
                "limitations": assessment["declaration"]["levels"][level]["limitations"],
            }
            for level in LEVELS
        },
        "limitations": assessment["declaration"]["limitations"],
    }
    ladder_path.write_text(
        json.dumps(
            evaluate_evidence_ladder(replay_input),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match bundle evidence: source_manifest"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_schema_10_cannot_smuggle_ladder_extension(tmp_path: Path) -> None:
    config = _write_case(tmp_path)
    output = tmp_path / "bundle"
    build_characterization_handoff_bundle_from_config(config, output)
    manifest_path = output / "characterization_handoff_bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "1.0"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HandoffBundleValidationError, match="requires bundle schema_version 1.1"):
        validate_characterization_handoff_bundle(output)
