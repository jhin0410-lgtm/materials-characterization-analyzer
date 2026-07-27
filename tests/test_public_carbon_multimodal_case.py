from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from mca.contracts import AnalysisResult, FeatureRecord, PreprocessingStep
from mca.provenance import sha256_file
from scripts.discover_public_carbon_multimodal import score_record
from scripts.run_public_carbon_multimodal_case import (
    adapt_tga_air_source,
    adapt_two_column_source,
    build_comparability_matrix,
    candidate_summary,
    inspect_tem_source,
    load_json,
    rebind_result_to_original_source,
    run_case,
    write_case_report,
)


CONFIG_PATH = Path("case_studies/public_carbon_multimodal/case_config.json")


def test_case_config_records_source_and_scientific_gates() -> None:
    config = load_json(CONFIG_PATH)
    assert config["dataset"]["persistent_id"] == "doi:10.57745/7KA2UG"
    assert config["dataset"]["license"] == "Etalab Open License 2.0"
    assert config["primary_sample"]["source_label"] == "DWCNT"
    assert config["availability_contract"]["saed"] == "not_provided_by_dataset"
    assert config["availability_contract"]["dsc"] == "not_provided_by_dataset"
    gate = config["suitability_gates"]["tem_quantitative_segmentation"]
    assert gate["allowed"] is False
    assert gate["status"] == "blocked_method_mismatch"


def test_updated_tga_discovery_rule_selects_raw_tga_air() -> None:
    config = load_json(CONFIG_PATH)
    record = {
        "filename": "20210511_TGAair_DWCNT.tab",
        "directory_label": "Dataset_Raw/Series_Raw_TGA and TGAMS/Raw_TGAair",
        "path": "Dataset_Raw/Series_Raw_TGA and TGAMS/Raw_TGAair/20210511_TGAair_DWCNT.tab",
        "description": "",
        "content_type": "text/tab-separated-values",
        "restricted": False,
        "datafile_id": 184435,
    }
    assert score_record(record, config["modalities"]["tga"]) is not None


def test_two_column_adapter_preserves_numeric_values_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "raman.tab"
    source.write_text(
        "Raman shift (cm-1);Intensity (cps)\n"
        + "\n".join(f"{1200 + index};{index - 3.5}" for index in range(10)),
        encoding="utf-8",
    )
    destination = tmp_path / "raman.csv"
    record = adapt_two_column_source(
        source,
        destination,
        x_name="raman_shift_cm_1",
        y_name="intensity",
    )
    canonical = pd.read_csv(destination)
    assert canonical.columns.tolist() == ["raman_shift_cm_1", "intensity"]
    assert canonical.iloc[0].tolist() == [1200.0, -3.5]
    assert record["numeric_values_modified"] is False
    assert record["source_delimiter"] == "semicolon"
    assert record["source_sha256"] == sha256_file(source)
    assert record["canonical_sha256"] == sha256_file(destination)


def test_two_column_adapter_rejects_extra_columns(tmp_path: Path) -> None:
    source = tmp_path / "bad.tab"
    source.write_text("a;b;c\n1;2;3\n" * 8, encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 2 columns"):
        adapt_two_column_source(source, tmp_path / "out.csv", x_name="x", y_name="y")


def test_tga_adapter_uses_documented_columns_1_2_and_6(tmp_path: Path) -> None:
    source = tmp_path / "tga.tab"
    headers = ["temperature", "time", "sample_mg", "crucible_mg", "variation_mg", "mass_pct", "dm_dt"]
    rows = []
    for index in range(10):
        rows.append(
            ";".join(
                str(value)
                for value in (
                    25 + index * 5,
                    index * 60,
                    3.5 - index * 0.02,
                    0.02,
                    -index * 0.02,
                    100 - index * 0.7,
                    -0.01 * index,
                )
            )
        )
    source.write_text(";".join(headers) + "\n" + "\n".join(rows), encoding="utf-8")
    destination = tmp_path / "tga.csv"
    record = adapt_tga_air_source(source, destination)
    canonical = pd.read_csv(destination)
    assert canonical.columns.tolist() == ["temperature_c", "time_s", "signal"]
    assert canonical.iloc[3].tolist() == pytest.approx([40.0, 180.0, 97.9])
    assert record["column_mapping"]["mass_pct"] == "signal_mass_retention_percent"
    assert "ReadMe_Raw.pdf" in record["mapping_basis"]


def test_tga_adapter_rejects_non_increasing_program(tmp_path: Path) -> None:
    source = tmp_path / "tga.tab"
    frame = pd.DataFrame(
        {
            "temperature": [25, 30, 35, 35, 40, 45, 50],
            "time": [0, 60, 120, 180, 240, 300, 360],
            "sample": [1] * 7,
            "crucible": [1] * 7,
            "variation": [0] * 7,
            "mass_pct": [100, 99, 98, 97, 96, 95, 94],
            "derivative": [0] * 7,
        }
    )
    frame.to_csv(source, sep=";", index=False)
    with pytest.raises(ValueError, match="strictly increasing heating segment"):
        adapt_tga_air_source(source, tmp_path / "out.csv")


def test_candidate_summary_handles_dataframe_without_truth_value_error() -> None:
    table = pd.DataFrame({"temperature_c": [300.0, 550.0]})
    summary = candidate_summary({"candidate_table": table}, "temperature_c", "degC")
    assert "2 review-required candidates" in summary
    assert "300 degC" in summary


def test_rebind_result_uses_original_source_for_result_and_features(tmp_path: Path) -> None:
    raw = tmp_path / "raw.tab"
    raw.write_text("x;y\n1;2\n", encoding="utf-8")
    canonical = tmp_path / "canonical.csv"
    canonical.write_text("x,y\n1,2\n", encoding="utf-8")
    feature_path = tmp_path / "features.csv"
    feature = FeatureRecord(
        sample_id="s1",
        measurement_id="m1",
        instrument="raman",
        feature_name="candidate_count",
        value=1,
        unit="count",
        method="test",
        source_file=str(canonical),
        source_sha256=sha256_file(canonical),
        preprocessing_id="old",
        quality_flag="review_required",
    )
    result = AnalysisResult(
        measurement_id="m1",
        sample_id="s1",
        instrument="raman",
        source_file=str(canonical),
        source_sha256=sha256_file(canonical),
        preprocessing_steps=[PreprocessingStep("existing", "test")],
        features=[feature],
        software_version="test",
    )
    analysis: dict[str, object] = {"analysis_result": result, "feature_path": feature_path}
    adapter = {
        "adapter": "test_adapter",
        "source_path": str(raw),
        "source_sha256": sha256_file(raw),
        "canonical_path": str(canonical),
        "canonical_sha256": sha256_file(canonical),
        "source_delimiter": "semicolon",
        "column_mapping": {"x": "x", "y": "y"},
        "incomplete_rows_removed": 0,
    }
    rebound = rebind_result_to_original_source(analysis, raw, adapter)
    assert rebound.source_file == str(raw)
    assert rebound.source_sha256 == sha256_file(raw)
    assert rebound.preprocessing_steps[0].step_id == "public-source-adapter"
    assert rebound.features[0].source_file == str(raw)
    assert rebound.features[0].source_sha256 == sha256_file(raw)
    exported = pd.read_csv(feature_path)
    assert exported.loc[0, "source_file"] == str(raw)


def test_tem_suitability_gate_records_metadata_without_segmentation(tmp_path: Path) -> None:
    source = tmp_path / "tem.tif"
    image = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64)
    assert cv2.imwrite(str(source), image)
    config = load_json(CONFIG_PATH)
    output = tmp_path / "tem_readiness.json"
    record = inspect_tem_source(
        source,
        config["acquisition_metadata"]["tem"],
        config["suitability_gates"]["tem_quantitative_segmentation"],
        output,
    )
    assert record["quantitative_segmentation_executed"] is False
    assert record["quantitative_segmentation_allowed"] is False
    assert record["image_shape"] == [64, 64]
    assert record["image_dtype"] == "uint16"
    assert record["scale_review"]["used_for_segmentation"] is False
    assert output.exists()


def test_comparability_matrix_has_explicit_conditional_blocked_and_unavailable_states(
    tmp_path: Path,
) -> None:
    config = load_json(CONFIG_PATH)
    execution = {
        "raman": "executed_real_data",
        "ftir": "executed_real_data",
        "xps": "executed_real_data",
        "tga": "executed_real_data",
        "tem": "blocked_by_suitability_gate",
        "saed": "not_available",
        "dsc": "not_available",
    }
    frame = build_comparability_matrix(config, execution, tmp_path / "matrix.csv")
    statuses = frame.set_index("modality")["comparability_status"].to_dict()
    assert statuses["raman"] == "conditionally_comparable"
    assert statuses["tem"] == "source_available_analysis_blocked"
    assert statuses["saed"] == "not_available_not_comparable"
    assert statuses["dsc"] == "not_available_not_comparable"
    assert not frame["identical_physical_aliquot_confirmed"].any()


def _fake_analysis(instrument: str, table_key: str, table: pd.DataFrame) -> dict[str, object]:
    result = AnalysisResult(
        measurement_id=f"m-{instrument}",
        sample_id="public-dwcnt",
        instrument=instrument,
        warnings=["review_required"],
        software_version="test",
    )
    return {table_key: table, "analysis_result": result}


def test_case_report_closes_scientific_claim_as_diagnostic(tmp_path: Path) -> None:
    config = load_json(CONFIG_PATH)
    analyses = {
        "raman": _fake_analysis("raman", "peak_table", pd.DataFrame({"raman_shift_cm_1": [1350.0]})),
        "ftir": _fake_analysis("ftir", "candidate_table", pd.DataFrame({"wavenumber_cm_1": [1600.0]})),
        "xps": _fake_analysis("xps", "candidate_table", pd.DataFrame({"binding_energy_corrected_ev": [285.0]})),
        "tga": _fake_analysis("tga", "candidate_table", pd.DataFrame({"temperature_c": [600.0]})),
    }
    output = tmp_path / "report.md"
    write_case_report(
        output,
        config,
        tmp_path / "source.json",
        tmp_path / "matrix.csv",
        analyses,
        {"image_shape": [2048, 2048], "image_dtype": "uint16"},
    )
    text = output.read_text(encoding="utf-8")
    assert "Evidence level: Diagnostic" in text
    assert "identical physical aliquots" in text
    assert "no substitute source was mixed in" in text
    assert "Not suitable for" in text


def test_run_case_fails_before_analysis_when_required_downloads_are_missing(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    discovery.mkdir()
    (discovery / "downloads.json").write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required public sources"):
        run_case(CONFIG_PATH, discovery, tmp_path / "out")
