from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.provenance import sha256_file
from scripts.export_nist_ambench_2018_02_optical_metrology_bundle import (
    DEFAULT_CONFIG,
    export_bundle,
    load_json,
    resolve_source,
    validate_measurements,
)


def test_tracked_nist_measurements_validate_and_reproduce_case_summary() -> None:
    config = load_json(DEFAULT_CONFIG)
    source = resolve_source(DEFAULT_CONFIG, config)
    validated = validate_measurements(pd.read_csv(source), config)

    assert len(validated) == 10
    assert validated["trace_number"].tolist() == list(range(1, 11))
    assert validated.groupby("case_id").size().to_dict() == {"A": 3, "B": 3, "C": 4}
    assert validated["melt_pool_width_mean_um"].min() > 0
    assert validated["melt_pool_depth_mean_um"].min() > 0
    assert (validated[["melt_pool_width_std_dev_um", "melt_pool_depth_std_dev_um"]] >= 0).all().all()


def test_export_bundle_writes_complete_provenance_bound_contract(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    paths = export_bundle(DEFAULT_CONFIG, output)

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    features = pd.read_csv(paths["feature_table"])
    context = pd.read_csv(paths["sample_context"])
    analysis = json.loads(paths["analysis_manifest"].read_text(encoding="utf-8"))

    assert manifest["case_id"] == "nist-ambench-2018-02-optical-metrology-v1"
    assert manifest["producer"]["repository"] == (
        "jhin0410-lgtm/materials-characterization-analyzer"
    )
    assert manifest["feature_table"]["row_count"] == 40
    assert manifest["feature_table"]["sample_count"] == 10
    assert manifest["feature_table"]["measurement_count"] == 10
    assert manifest["feature_table"]["instruments"] == [
        "optical_microscopy_metrology"
    ]
    assert manifest["feature_table"]["quality_flag_counts"] == {
        "source_reported": 40
    }
    assert manifest["feature_table"]["source_sha256_record_count"] == 40
    assert manifest["feature_table"]["preprocessing_id_record_count"] == 40
    assert manifest["scientific_closeout"]["evidence_level"] == "Diagnostic"
    assert manifest["scientific_closeout"]["result"] == (
        "nist_ambench_trace_optical_metrology_exported"
    )

    assert len(features) == 40
    assert features["sample_id"].nunique() == 10
    assert features["measurement_id"].nunique() == 10
    assert set(features["feature_name"]) == {
        "melt_pool_width_mean",
        "melt_pool_width_std_dev",
        "melt_pool_depth_mean",
        "melt_pool_depth_std_dev",
    }
    assert set(features["source_sha256"]) == {
        summary["source_measurement_sha256"]
    }
    assert set(features["preprocessing_id"]) == {"nist_reported_table_values_v1"}
    assert set(features["quality_flag"]) == {"source_reported"}

    assert len(context) == 10
    assert set(context["case_id"]) == {"A", "B", "C"}
    assert set(context["material"]) == {"IN625"}
    assert set(context["system"]) == {"AMMT"}
    assert context["trace_to_cross_section_mapping_confirmed"].astype(bool).all()
    assert not context["raw_image_parsed"].astype(bool).any()
    assert not context["process_conditions_included_in_bundle"].astype(bool).any()

    assert analysis["analysis_count"] == 10
    assert all(item["acquisition_metadata"]["raw_image_parsed"] is False for item in analysis["analyses"])
    assert all(len(item["features"]) == 4 for item in analysis["analyses"])

    for section in ("feature_table", "sample_context"):
        record = manifest[section]
        assert sha256_file(output / record["path"]) == record["sha256"]
    for record in manifest["evidence_references"].values():
        assert sha256_file(output / record["path"]) == record["sha256"]

    assert summary["sample_count"] == 10
    assert summary["measurement_count"] == 10
    assert summary["feature_record_count"] == 40
    assert summary["raw_image_parsed"] is False
    assert summary["process_conditions_included"] is False
    assert summary["software_validation"]["model_trained"] is False
    assert summary["software_validation"]["optimization_performed"] is False


def test_export_is_deterministic_across_output_directories(tmp_path: Path) -> None:
    first = export_bundle(DEFAULT_CONFIG, tmp_path / "first")
    second = export_bundle(DEFAULT_CONFIG, tmp_path / "second")

    for key in (
        "feature_table",
        "sample_context",
        "manifest",
        "source_manifest",
        "analysis_manifest",
        "comparability_matrix",
        "summary",
        "report",
    ):
        assert first[key].read_bytes() == second[key].read_bytes()


def test_nonempty_output_is_rejected_without_deleting_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        export_bundle(DEFAULT_CONFIG, output)

    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_tampered_measurement_value_fails_nist_summary_check() -> None:
    config = load_json(DEFAULT_CONFIG)
    source = resolve_source(DEFAULT_CONFIG, config)
    table = pd.read_csv(source)
    table.loc[0, "melt_pool_width_mean_um"] = 999.0

    with pytest.raises(ValueError, match="does not reproduce the NIST rounded summary"):
        validate_measurements(table, config)
