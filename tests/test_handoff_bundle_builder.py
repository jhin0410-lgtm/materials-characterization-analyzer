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
    (evidence / "source_manifest.json").write_text('{"source":"public"}\n', encoding="utf-8")
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


def test_build_handoff_cli_runs_end_to_end(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output = tmp_path / "bundle"

    assert build_cli_main(["--config", str(config), "--output", str(output)]) == 0
    assert (output / "characterization_handoff_bundle.json").is_file()
