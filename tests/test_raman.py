from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mca.cli_entry import main as console_main
from mca.raman import (
    analyze_raman,
    asymmetric_least_squares_baseline,
    detect_raman_peaks,
    load_raman_file,
    smooth_raman_intensity,
)


DATA = Path(__file__).resolve().parents[1] / "data" / "demo"


def _synthetic_spectrum() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    shift = np.arange(200.0, 1800.1, 10.0)
    baseline = 30.0 + 0.015 * (shift - 200.0) + 0.000015 * (shift - 950.0) ** 2
    intensity = (
        baseline
        + 160.0 * np.exp(-0.5 * ((shift - 520.0) / 18.0) ** 2)
        + 120.0 * np.exp(-0.5 * ((shift - 1350.0) / 30.0) ** 2)
        + 180.0 * np.exp(-0.5 * ((shift - 1580.0) / 26.0) ** 2)
        + 2.0 * np.sin(shift / 37.0)
    )
    return shift, intensity, baseline


def test_load_raman_file_normalizes_aliases_and_sorts(tmp_path: Path) -> None:
    path = tmp_path / "raman.csv"
    pd.DataFrame(
        {
            "Raman Shift (cm-1)": [300.0, 100.0, 200.0, 400.0, 500.0, 600.0, 700.0],
            "Counts": [3.0, 1.0, 2.0, 4.0, 5.0, 6.0, 7.0],
        }
    ).to_csv(path, index=False)

    spectrum = load_raman_file(path)

    assert list(spectrum.columns) == ["raman_shift_cm_1", "intensity"]
    assert spectrum["raman_shift_cm_1"].tolist() == sorted(spectrum["raman_shift_cm_1"].tolist())


def test_load_raman_file_rejects_duplicate_shift(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.csv"
    pd.DataFrame(
        {
            "raman_shift_cm_1": [100, 200, 200, 300, 400, 500, 600],
            "intensity": [1, 2, 3, 4, 5, 6, 7],
        }
    ).to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_raman_file(path)


def test_asls_baseline_and_peak_detection_on_synthetic_spectrum() -> None:
    shift, intensity, expected_baseline = _synthetic_spectrum()

    baseline = asymmetric_least_squares_baseline(intensity)
    corrected = intensity - baseline
    processed = smooth_raman_intensity(corrected, window_length=11, polyorder=3)
    peaks = detect_raman_peaks(
        shift,
        intensity,
        baseline,
        processed,
        prominence_fraction=0.05,
        min_distance=5,
    )

    assert np.mean(np.abs(baseline - expected_baseline)) < 8.0
    assert peaks["raman_shift_cm_1"].tolist() == pytest.approx([520.0, 1350.0, 1580.0])
    assert (peaks["fwhm_cm_1"] > 0).all()
    assert (peaks["area_within_fwhm_intensity_cm_1"] > 0).all()


def test_analyze_raman_writes_provenance_outputs(tmp_path: Path) -> None:
    result = analyze_raman(
        DATA / "synthetic_raman.csv",
        tmp_path,
        sample_id="demo_raman",
        min_distance=5,
        acquisition_metadata={
            "laser_wavelength_nm": 532.0,
            "laser_power_mw": 1.0,
            "exposure_time_s": 10.0,
            "accumulation_count": 3,
            "spectral_resolution_cm_1": 2.0,
        },
    )

    assert len(result["peak_table"]) == 3
    assert result["processed_spectrum_path"].exists()
    assert result["peak_table_path"].exists()
    assert result["feature_path"].exists()
    assert result["plot_path"].exists()

    analysis = result["analysis_result"]
    assert analysis.instrument == "raman"
    assert analysis.source_sha256 is not None
    assert "automatic_peak_detection_requires_manual_review" in analysis.warnings
    assert "laser_wavelength_not_provided" not in analysis.warnings
    assert all(record.quality_flag == "review_required" for record in analysis.features)
    assert "assignment" not in " ".join(result["peak_table"].columns).lower()


def test_analyze_raman_rejects_invalid_acquisition_metadata(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="laser_wavelength_nm"):
        analyze_raman(
            DATA / "synthetic_raman.csv",
            tmp_path,
            sample_id="invalid_metadata",
            acquisition_metadata={"laser_wavelength_nm": -532.0},
        )


def test_console_raman_command_writes_manifest(tmp_path: Path) -> None:
    exit_code = console_main(
        [
            "raman",
            "--input",
            str(DATA / "synthetic_raman.csv"),
            "--output",
            str(tmp_path),
            "--sample-id",
            "cli_raman",
            "--min-distance",
            "5",
            "--laser-wavelength-nm",
            "532",
            "--laser-power-mw",
            "1",
            "--exposure-time-s",
            "10",
            "--accumulation-count",
            "3",
            "--spectral-resolution-cm-1",
            "2",
        ]
    )

    manifest_path = tmp_path / "raman_analysis_manifest.json"
    assert exit_code == 0
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["analysis_count"] == 1
    assert manifest["analyses"][0]["instrument"] == "raman"
    assert manifest["analyses"][0]["sample_id"] == "cli_raman"


def test_console_entry_preserves_existing_xrd_command(tmp_path: Path) -> None:
    exit_code = console_main(
        [
            "xrd",
            "--input",
            str(DATA / "synthetic_xrd.csv"),
            "--output",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "xrd_peak_table.csv").exists()
