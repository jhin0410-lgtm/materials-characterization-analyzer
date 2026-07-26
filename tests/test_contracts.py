from __future__ import annotations

import json
from pathlib import Path

import pytest

from mca.contracts import AnalysisResult, FeatureRecord, PreprocessingStep, write_analysis_manifest
from mca.provenance import build_analysis_result, preprocessing_fingerprint, sha256_file


def test_write_analysis_manifest_serializes_nested_contracts(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    step = PreprocessingStep("step-1", "test_operation", {"window": 5})
    feature = FeatureRecord(
        sample_id="sample-a",
        measurement_id="sample-a-xrd",
        instrument="xrd",
        feature_name="detected_peak_count",
        value=3,
        unit="count",
        method="test_method",
        source_file=str(source),
        source_sha256=sha256_file(source),
        preprocessing_id="abc123",
    )
    result = AnalysisResult(
        measurement_id="sample-a-xrd",
        sample_id="sample-a",
        instrument="xrd",
        source_file=str(source),
        source_sha256=sha256_file(source),
        preprocessing_steps=[step],
        features=[feature],
        software_version="0.2.0",
    )

    path = write_analysis_manifest([result], tmp_path / "manifest.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["analysis_count"] == 1
    assert payload["analyses"][0]["features"][0]["feature_name"] == "detected_peak_count"
    assert payload["analyses"][0]["preprocessing_steps"][0]["parameters"] == {"window": 5}


def test_sha256_file_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abc")

    assert sha256_file(source) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_preprocessing_fingerprint_changes_with_parameters() -> None:
    first = [PreprocessingStep("smooth", "savgol", {"window": 5})]
    second = [PreprocessingStep("smooth", "savgol", {"window": 7})]

    assert preprocessing_fingerprint("raman", first) == preprocessing_fingerprint("raman", first)
    assert preprocessing_fingerprint("raman", first) != preprocessing_fingerprint("raman", second)


def test_build_analysis_result_records_missing_raw_source_warning() -> None:
    result = build_analysis_result(
        measurement_id="sample-a-eds",
        sample_id="sample-a",
        instrument="eds",
    )

    assert result.source_file is None
    assert result.source_sha256 is None
    assert "raw_source_file_not_provided" in result.warnings


def test_feature_record_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="source_sha256"):
        FeatureRecord(
            sample_id="sample-a",
            measurement_id="sample-a-xrd",
            instrument="xrd",
            feature_name="detected_peak_count",
            value=1,
            unit="count",
            method="test",
            source_sha256="invalid",
        )
