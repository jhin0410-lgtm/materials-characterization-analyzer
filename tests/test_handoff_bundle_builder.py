from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.handoff_bundle_builder import (
    BUILD_STATUS,
    HandoffBundleBuildError,
    build_characterization_handoff_bundle_from_config,
)
from mca.handoff_bundle_builder_cli import main as build_cli_main
from mca.handoff_bundle_validation import VALIDATION_STATUS


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


def _config(tmp_path: Path) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "source_manifest.json").write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    (evidence / "analysis_manifest.json").write_text(
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
    ).to_csv(evidence / "comparability_matrix.csv", index=False)
    config = tmp_path / "handoff_config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "generic-handoff-test",
                "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
                "evidence_level": "Diagnostic",
                "sample_context_rows": [
                    {
                        "sample_id": "sample-a",
                        "identical_physical_aliquot_confirmed": False,
                    }
                ],
                "scientific_boundary": {
                    "primary_limitation": "aliquot identity is not confirmed"
                },
                "evidence": {
                    "source_manifest": "evidence/source_manifest.json",
                    "analysis_manifest": "evidence/analysis_manifest.json",
                    "comparability_matrix": "evidence/comparability_matrix.csv",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def test_build_handoff_from_relative_config_is_validated(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output = tmp_path / "bundle"

    result = build_characterization_handoff_bundle_from_config(config, output)

    assert result["status"] == BUILD_STATUS
    assert result["validation"]["status"] == VALIDATION_STATUS
    assert result["validation"]["scientific_comparability_established"] is False
    binding = result["validation"]["evidence_identity_binding"]
    assert binding["contract_present"] is True
    assert binding["contract"] == {"schema_version": "1.0", "required": True}
    assert binding["semantic_identity_binding_established"] is True
    assert binding["analysis_manifest_features_reproduced"] is True
    assert binding["source_sha256_coverage_verified"] is True
    assert binding["every_feature_row_source_sha256_bound"] is True
    assert binding["comparability_identity_coverage_verified"] is True
    assert binding["comparability_binding_axes"] == ["modality"]
    manifest = json.loads(
        (output / "characterization_handoff_bundle.json").read_text(encoding="utf-8")
    )
    assert manifest["evidence_identity_binding_contract"] == {
        "schema_version": "1.0",
        "required": True,
    }
    assert (output / "source_manifest.json").is_file()
    assert (output / "analysis_manifest.json").is_file()
    assert (output / "comparability_matrix.csv").is_file()
    assert not (tmp_path / ".bundle.building").exists()


def test_build_handoff_rejects_existing_output(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output = tmp_path / "bundle"
    output.mkdir()
    with pytest.raises(FileExistsError, match="must not already exist"):
        build_characterization_handoff_bundle_from_config(config, output)


def test_failed_writer_cleans_staging_directory(tmp_path: Path) -> None:
    config = _config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["sample_context_rows"][0]["sample_id"] = "wrong-sample"
    config.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="sample_id sets must match exactly"):
        build_characterization_handoff_bundle_from_config(config, output)
    assert not output.exists()
    assert not (tmp_path / ".bundle.building").exists()


def test_build_handoff_rejects_duplicate_evidence_basenames(tmp_path: Path) -> None:
    config = _config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["evidence"]["source_manifest"] = "evidence/analysis_manifest.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HandoffBundleBuildError, match="basenames must be unique"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_build_handoff_rejects_unbound_feature_source_digest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "evidence" / "source_manifest.json"
    source.write_text(
        json.dumps({"source": "public", "sha256": "b" * 64}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not checksum-bind every feature source_sha256"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_build_handoff_rejects_source_case_id_conflict(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "evidence" / "source_manifest.json"
    source.write_text(
        json.dumps({"case_id": "different-case", "source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="case_id does not match bundle case_id"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_build_handoff_rejects_unrelated_comparability_matrix(tmp_path: Path) -> None:
    config = _config(tmp_path)
    pd.DataFrame(
        {"modality": ["xrd"], "comparability_status": ["not_established"]}
    ).to_csv(tmp_path / "evidence" / "comparability_matrix.csv", index=False)
    with pytest.raises(ValueError, match="does not cover every feature instrument"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_build_handoff_accepts_uppercase_equivalent_source_digest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    analysis_path = tmp_path / "evidence" / "analysis_manifest.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["analyses"][0]["features"][0]["source_sha256"] = "A" * 64
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    source = tmp_path / "evidence" / "source_manifest.json"
    source.write_text(json.dumps({"source": "public", "sha256": "a" * 64}), encoding="utf-8")
    result = build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")
    assert result["validation"]["evidence_identity_binding"]["source_sha256_coverage_verified"] is True


def test_build_handoff_rejects_any_feature_row_without_source_digest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    analysis_path = tmp_path / "evidence" / "analysis_manifest.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    second = dict(analysis["analyses"][0]["features"][0])
    second["measurement_id"] = "sample-a-raman-2"
    second["feature_name"] = "secondary_candidate_count"
    second["source_sha256"] = None
    analysis["analyses"][0]["features"].append(second)
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    with pytest.raises(ValueError, match="every feature row must carry source_sha256"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_build_handoff_rejects_crossed_sample_instrument_pairs(tmp_path: Path) -> None:
    config = _config(tmp_path)
    analysis_path = tmp_path / "evidence" / "analysis_manifest.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    first = analysis["analyses"][0]["features"][0]
    first["sample_id"] = "sample-a"
    first["instrument"] = "raman"
    first["measurement_id"] = "sample-a-raman"
    second = dict(first)
    second["sample_id"] = "sample-b"
    second["instrument"] = "xrd"
    second["measurement_id"] = "sample-b-xrd"
    second["feature_name"] = "peak_count"
    analysis["analyses"][0]["features"] = [first, second]
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["sample_context_rows"] = [{"sample_id": "sample-a"}, {"sample_id": "sample-b"}]
    config.write_text(json.dumps(payload), encoding="utf-8")
    pd.DataFrame(
        {
            "sample_id": ["sample-a", "sample-b"],
            "modality": ["xrd", "raman"],
            "comparability_status": ["not_established", "not_established"],
        }
    ).to_csv(tmp_path / "evidence" / "comparability_matrix.csv", index=False)
    with pytest.raises(ValueError, match="sample_id/instrument pair"):
        build_characterization_handoff_bundle_from_config(config, tmp_path / "bundle")


def test_build_handoff_cli_runs_end_to_end(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output = tmp_path / "bundle"
    assert build_cli_main(["--config", str(config), "--output", str(output)]) == 0
    assert (output / "characterization_handoff_bundle.json").is_file()
