from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mca.cli_entry import main as cli_entry_main
from mca.ftir import (
    analyze_ftir,
    asymmetric_least_squares_ftir_baseline,
    convert_ftir_signal_to_absorbance,
    detect_ftir_band_candidates,
    linear_ftir_baseline,
    load_ftir_file,
    smooth_ftir_absorbance,
)
from mca.ftir_cli import main as ftir_main


def _synthetic_absorbance() -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(400.0, 4000.0, 1801)
    baseline = 0.04 + 0.00001 * (x - 400.0)
    y = baseline.copy()
    for center, amplitude, sigma in (
        (1100.0, 0.50, 38.0),
        (1715.0, 0.75, 28.0),
        (3300.0, 0.40, 95.0),
    ):
        y += amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)
    return x, y


def _write_descending_transmittance(path: Path) -> Path:
    x, absorbance = _synthetic_absorbance()
    transmittance = 100.0 * np.power(10.0, -absorbance)
    pd.DataFrame(
        {"wavenumber_cm_1": x[::-1], "transmittance_percent": transmittance[::-1]}
    ).to_csv(path, index=False)
    return path


def test_load_descending_axis_records_provenance(tmp_path: Path) -> None:
    path = _write_descending_transmittance(tmp_path / "ftir.csv")
    table = load_ftir_file(path)
    assert table.attrs["input_axis_direction"] == "descending"
    assert np.all(np.diff(table["wavenumber_cm_1"]) > 0)


def test_load_rejects_nonmonotonic_axis(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    pd.DataFrame(
        {
            "wavenumber_cm_1": [400, 500, 450, 600, 700, 800, 900],
            "signal": range(7),
        }
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="could not be interpreted"):
        load_ftir_file(path)


@pytest.mark.parametrize(
    ("signal_type", "values", "expected"),
    [
        ("absorbance", np.array([0.1, 0.2, 0.3]), np.array([0.1, 0.2, 0.3])),
        (
            "transmittance_percent",
            np.array([100.0, 10.0, 1.0]),
            np.array([0.0, 1.0, 2.0]),
        ),
        (
            "transmittance_fraction",
            np.array([1.0, 0.1, 0.01]),
            np.array([0.0, 1.0, 2.0]),
        ),
    ],
)
def test_signal_conversion(
    signal_type: str,
    values: np.ndarray,
    expected: np.ndarray,
) -> None:
    converted, _ = convert_ftir_signal_to_absorbance(values, signal_type=signal_type)
    assert np.allclose(converted, expected)


def test_transmittance_conversion_rejects_nonpositive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        convert_ftir_signal_to_absorbance(
            np.array([100.0, 0.0, 50.0]),
            signal_type="transmittance_percent",
        )


def test_linear_baseline_matches_endpoints() -> None:
    values = np.array([2.0, 3.0, 4.0, 6.0])
    baseline = linear_ftir_baseline(values)
    assert baseline[0] == pytest.approx(2.0)
    assert baseline[-1] == pytest.approx(6.0)


def test_asls_baseline_is_finite_and_below_main_peak() -> None:
    x, y = _synthetic_absorbance()
    baseline = asymmetric_least_squares_ftir_baseline(
        y,
        smoothness=1e7,
        asymmetry=0.01,
        iterations=10,
    )
    assert np.isfinite(baseline).all()
    peak_index = np.argmin(np.abs(x - 1715.0))
    assert baseline[peak_index] < y[peak_index]


def test_candidate_detection_finds_expected_bands() -> None:
    x, absorbance = _synthetic_absorbance()
    baseline = np.zeros_like(absorbance)
    candidates = detect_ftir_band_candidates(
        x,
        absorbance,
        absorbance,
        baseline,
        absorbance,
        prominence_fraction=0.08,
        min_distance=25,
    )
    found = candidates["wavenumber_cm_1"].to_numpy()
    for target in (1100.0, 1715.0, 3300.0):
        assert np.min(np.abs(found - target)) < 8.0
    assert (candidates["fwhm_cm_1"] > 0).all()


def test_smoothing_zero_is_identity() -> None:
    values = np.linspace(0.0, 1.0, 11)
    assert np.array_equal(smooth_ftir_absorbance(values, window_length=0), values)


def test_analyze_generates_outputs_and_provenance(tmp_path: Path) -> None:
    source = _write_descending_transmittance(tmp_path / "source.csv")
    output = tmp_path / "out"
    result = analyze_ftir(
        source,
        output,
        sample_id="sample-1",
        signal_type="transmittance_percent",
        baseline_method="linear",
        smoothing_window=0,
        acquisition_metadata={
            "sampling_mode": "transmission",
            "spectral_resolution_cm_1": 4.0,
            "scan_count": 16,
            "detector": "DTGS",
            "background_description": "synthetic background",
        },
    )
    for key in (
        "processed_spectrum_path",
        "candidate_table_path",
        "feature_path",
        "plot_path",
    ):
        assert Path(result[key]).is_file()
    analysis = result["analysis_result"]
    assert analysis.instrument == "ftir"
    assert len(analysis.source_sha256) == 64
    assert analysis.acquisition_metadata["signal_type"] == "transmittance_percent"
    assert all(record.quality_flag == "review_required" for record in analysis.features)


def test_warnings_preserve_above_100_transmittance(tmp_path: Path) -> None:
    x = np.linspace(400.0, 4000.0, 101)
    signal = np.full_like(x, 101.0)
    signal[50] = 50.0
    source = tmp_path / "above.csv"
    pd.DataFrame({"wavenumber_cm_1": x, "signal": signal}).to_csv(source, index=False)
    result = analyze_ftir(
        source,
        tmp_path / "out",
        sample_id="sample",
        signal_type="transmittance_percent",
        baseline_method="none",
    )
    warnings = result["analysis_result"].warnings
    assert "transmittance_percent_above_100_not_clipped" in warnings
    assert "negative_absorbance_present" in warnings


def test_metadata_validation_happens_before_output_creation(tmp_path: Path) -> None:
    source = _write_descending_transmittance(tmp_path / "source.csv")
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="spectral_resolution_cm_1"):
        analyze_ftir(
            source,
            output,
            sample_id="sample",
            signal_type="transmittance_percent",
            acquisition_metadata={"spectral_resolution_cm_1": 0.0},
        )
    assert not output.exists()


def test_cli_writes_manifest(tmp_path: Path) -> None:
    source = _write_descending_transmittance(tmp_path / "source.csv")
    output = tmp_path / "out"
    exit_code = ftir_main(
        [
            "--input",
            str(source),
            "--output",
            str(output),
            "--sample-id",
            "cli-sample",
            "--signal-type",
            "transmittance_percent",
            "--baseline-method",
            "linear",
            "--sampling-mode",
            "transmission",
            "--spectral-resolution-cm-1",
            "4",
            "--scan-count",
            "8",
            "--detector",
            "DTGS",
            "--background-description",
            "synthetic",
        ]
    )
    assert exit_code == 0
    manifest = json.loads((output / "ftir_analysis_manifest.json").read_text())
    assert manifest["analysis_count"] == 1
    assert manifest["analyses"][0]["instrument"] == "ftir"


def test_console_dispatches_ftir(tmp_path: Path) -> None:
    source = _write_descending_transmittance(tmp_path / "source.csv")
    output = tmp_path / "dispatch"
    exit_code = cli_entry_main(
        [
            "ftir",
            "--input",
            str(source),
            "--output",
            str(output),
            "--signal-type",
            "transmittance_percent",
            "--baseline-method",
            "none",
        ]
    )
    assert exit_code == 0
    assert (output / "ftir_analysis_manifest.json").is_file()
