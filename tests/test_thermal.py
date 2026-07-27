from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mca.thermal import (
    analyze_thermal,
    calculate_dsc_baseline,
    calculate_tga_profile,
    convert_dsc_signal,
    convert_tga_signal,
    detect_dsc_candidates,
    detect_tga_candidates,
    load_thermal_file,
    validate_mode_and_signal_type,
)
from mca.thermal_cli import main as thermal_main


def _tga_frame() -> pd.DataFrame:
    temperature = np.linspace(30.0, 800.0, 1200)
    time_s = (temperature - 30.0) / 10.0 * 60.0
    mass = 100.0
    mass -= 8.0 / (1.0 + np.exp(-(temperature - 180.0) / 8.0))
    mass -= 22.0 / (1.0 + np.exp(-(temperature - 420.0) / 12.0))
    mass -= 15.0 / (1.0 + np.exp(-(temperature - 650.0) / 10.0))
    return pd.DataFrame({"temperature_c": temperature, "time_s": time_s, "signal": mass})


def _dsc_frame(direction: str = "up") -> pd.DataFrame:
    temperature = np.linspace(30.0, 450.0, 1000)
    time_s = (temperature - 30.0) / 10.0 * 60.0
    signal = 0.0007 * (temperature - 30.0)
    signal += 2.4 * np.exp(-0.5 * ((temperature - 155.0) / 8.0) ** 2)
    signal -= 1.8 * np.exp(-0.5 * ((temperature - 305.0) / 11.0) ** 2)
    if direction == "down":
        signal = -signal
    return pd.DataFrame({"temperature_c": temperature, "time_s": time_s, "signal": signal})


def test_load_headerless_two_columns(tmp_path: Path) -> None:
    path = tmp_path / "thermal.csv"
    pd.DataFrame({0: np.arange(10.0), 1: np.linspace(100, 90, 10)}).to_csv(
        path, index=False, header=False
    )
    result = load_thermal_file(path)
    assert list(result.columns) == ["temperature_c", "signal"]


def test_load_rejects_nonincreasing_temperature(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    pd.DataFrame(
        {"temperature_c": [1, 2, 3, 2, 5, 6, 7], "signal": range(7)}
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="could not be interpreted"):
        load_thermal_file(path)


def test_load_rejects_nonincreasing_time(tmp_path: Path) -> None:
    path = tmp_path / "bad_time.csv"
    pd.DataFrame(
        {
            "temperature_c": range(7),
            "time_s": [0, 1, 2, 2, 4, 5, 6],
            "signal": range(7),
        }
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="could not be interpreted"):
        load_thermal_file(path)


def test_mode_signal_compatibility() -> None:
    validate_mode_and_signal_type("tga", "mass_percent")
    validate_mode_and_signal_type("dsc", "heat_flow_w_g")
    with pytest.raises(ValueError):
        validate_mode_and_signal_type("tga", "heat_flow_mw")


def test_tga_signal_conversions() -> None:
    percent, method, _ = convert_tga_signal([100, 90, 80], signal_type="mass_percent")
    assert method == "input_mass_percent"
    assert percent["mass_retention_percent"].tolist() == [100, 90, 80]
    fraction, _, _ = convert_tga_signal([1.0, 0.9, 0.8], signal_type="mass_fraction")
    assert fraction["mass_retention_percent"].tolist() == [100, 90, 80]
    mg, method, warnings = convert_tga_signal([10, 9, 8], signal_type="mass_mg")
    assert method == "first_signal_value_as_mass_reference"
    assert "tga_first_point_used_as_mass_reference" in warnings
    assert mg["mass_retention_percent"].tolist() == [100, 90, 80]


def test_dsc_signal_conversion_requires_mass_for_normalization() -> None:
    result, method, warnings = convert_dsc_signal(
        [10, 20, 30], signal_type="heat_flow_mw"
    )
    assert method.endswith("without_mass_normalization")
    assert result["heat_flow_w_g"].isna().all()
    assert "dsc_sample_mass_missing_heat_flow_not_normalized" in warnings
    normalized, method, _ = convert_dsc_signal(
        [10, 20, 30], signal_type="heat_flow_mw", sample_mass_mg=10
    )
    assert method.endswith("divided_by_sample_mass_mg")
    assert normalized["heat_flow_w_g"].tolist() == [1, 2, 3]


def test_tga_profile_and_candidates_detect_steps() -> None:
    frame = _tga_frame()
    profile = calculate_tga_profile(
        frame.temperature_c, frame.signal, smoothing_window=15, smoothing_polyorder=3
    )
    candidates = detect_tga_candidates(
        frame.temperature_c,
        frame.signal,
        profile.mass_loss_rate_percent_per_c,
        prominence_fraction=0.05,
        min_distance=100,
    )
    assert len(candidates) >= 3
    observed = candidates.temperature_c.to_numpy()
    for expected in (180, 420, 650):
        assert np.min(np.abs(observed - expected)) < 12


def test_dsc_baseline_and_bidirectional_candidates() -> None:
    frame = _dsc_frame("up")
    baseline = calculate_dsc_baseline(frame.signal, method="linear")
    corrected = frame.signal.to_numpy() - baseline
    candidates = detect_dsc_candidates(
        frame.temperature_c,
        corrected,
        corrected,
        time_s=frame.time_s,
        signal_is_w_g=True,
        prominence_fraction=0.05,
        min_distance=100,
    )
    assert {"endothermic", "exothermic"}.issubset(set(candidates.candidate_type))
    assert candidates.enthalpy_within_fwhm_j_g.notna().all()
    observed = candidates.temperature_c.to_numpy()
    assert np.min(np.abs(observed - 155)) < 10
    assert np.min(np.abs(observed - 305)) < 12


def test_endotherm_down_can_be_oriented_by_caller() -> None:
    frame = _dsc_frame("down")
    oriented = -frame.signal.to_numpy()
    baseline = calculate_dsc_baseline(oriented, method="linear")
    corrected = oriented - baseline
    candidates = detect_dsc_candidates(
        frame.temperature_c,
        corrected,
        corrected,
        prominence_fraction=0.05,
        min_distance=100,
    )
    endo = candidates[candidates.candidate_type == "endothermic"]
    assert np.min(np.abs(endo.temperature_c.to_numpy() - 155)) < 10


def test_enthalpy_requires_normalized_signal_and_time_or_rate() -> None:
    frame = _dsc_frame("up")
    baseline = calculate_dsc_baseline(frame.signal, method="linear")
    corrected = frame.signal.to_numpy() - baseline
    without = detect_dsc_candidates(
        frame.temperature_c,
        corrected,
        corrected,
        signal_is_w_g=True,
        prominence_fraction=0.05,
        min_distance=100,
    )
    assert without.enthalpy_within_fwhm_j_g.isna().all()
    with_rate = detect_dsc_candidates(
        frame.temperature_c,
        corrected,
        corrected,
        signal_is_w_g=True,
        heating_rate_c_min=10,
        prominence_fraction=0.05,
        min_distance=100,
    )
    assert with_rate.enthalpy_within_fwhm_j_g.notna().all()


def test_analyze_tga_outputs_and_provenance(tmp_path: Path) -> None:
    input_path = tmp_path / "tga.csv"
    _tga_frame().to_csv(input_path, index=False)
    output = tmp_path / "out"
    result = analyze_thermal(
        input_path,
        output,
        sample_id="s1",
        mode="tga",
        signal_type="mass_percent",
        baseline_method="none",
        smoothing_window=15,
        prominence_fraction=0.05,
        min_distance=100,
        acquisition_metadata={
            "atmosphere": "N2",
            "heating_rate_c_min": 10,
            "sample_mass_mg": 12,
            "crucible_material": "alumina",
        },
    )
    for key in (
        "processed_data_path",
        "candidate_table_path",
        "feature_path",
        "plot_path",
    ):
        assert Path(result[key]).exists()
    analysis = result["analysis_result"]
    assert analysis.instrument == "tga"
    assert len(analysis.source_sha256) == 64
    assert all(feature.quality_flag == "review_required" for feature in analysis.features)
    assert not any("reaction" in feature.feature_name for feature in analysis.features)


def test_analyze_dsc_warns_without_normalization(tmp_path: Path) -> None:
    input_path = tmp_path / "dsc.csv"
    _dsc_frame().to_csv(input_path, index=False)
    result = analyze_thermal(
        input_path,
        tmp_path / "out",
        sample_id="s2",
        mode="dsc",
        signal_type="heat_flow_mw",
        endotherm_direction="up",
        baseline_method="linear",
        smoothing_window=0,
        prominence_fraction=0.05,
        min_distance=100,
        acquisition_metadata={
            "atmosphere": "N2",
            "heating_rate_c_min": 10,
            "crucible_material": "aluminum",
        },
    )
    warnings = result["analysis_result"].warnings
    assert "dsc_heat_flow_not_mass_normalized" in warnings
    assert (
        "dsc_enthalpy_not_calculated_without_normalized_heat_flow_and_time_or_heating_rate"
        in warnings
    )


def test_metadata_validation_happens_before_output(tmp_path: Path) -> None:
    input_path = tmp_path / "tga.csv"
    _tga_frame().to_csv(input_path, index=False)
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="heating_rate_c_min"):
        analyze_thermal(
            input_path,
            output,
            sample_id="s",
            mode="tga",
            signal_type="mass_percent",
            baseline_method="none",
            acquisition_metadata={"heating_rate_c_min": 0},
        )
    assert not output.exists()


def test_heating_rate_mismatch_warning(tmp_path: Path) -> None:
    input_path = tmp_path / "tga.csv"
    _tga_frame().to_csv(input_path, index=False)
    result = analyze_thermal(
        input_path,
        tmp_path / "out",
        sample_id="s",
        mode="tga",
        signal_type="mass_percent",
        baseline_method="none",
        acquisition_metadata={
            "heating_rate_c_min": 20,
            "atmosphere": "N2",
            "sample_mass_mg": 10,
            "crucible_material": "alumina",
        },
    )
    assert (
        "thermal_supplied_heating_rate_differs_from_time_axis_by_more_than_10_percent"
        in result["analysis_result"].warnings
    )


def test_cli_writes_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "tga.csv"
    _tga_frame().to_csv(input_path, index=False)
    output = tmp_path / "out"
    code = thermal_main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output),
            "--sample-id",
            "cli",
            "--mode",
            "tga",
            "--signal-type",
            "mass_percent",
            "--atmosphere",
            "N2",
            "--heating-rate-c-min",
            "10",
            "--sample-mass-mg",
            "10",
            "--crucible-material",
            "alumina",
        ]
    )
    assert code == 0
    manifest = json.loads((output / "thermal_analysis_manifest.json").read_text())
    assert manifest["analyses"][0]["instrument"] == "tga"
