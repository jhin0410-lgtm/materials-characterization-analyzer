from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mca import cli_entry
from mca.xps import (
    analyze_xps,
    detect_xps_candidates,
    load_xps_file,
    resolve_energy_reference,
    shirley_background,
    smooth_xps_intensity,
)
from mca.xps_cli import main as xps_main


def _synthetic_xps() -> tuple[np.ndarray, np.ndarray]:
    energy = np.linspace(0.0, 800.0, 1601)
    background = 40.0 + 0.03 * energy
    peaks = (
        150.0 * np.exp(-0.5 * ((energy - 285.0) / 3.5) ** 2)
        + 120.0 * np.exp(-0.5 * ((energy - 532.0) / 4.5) ** 2)
        + 80.0 * np.exp(-0.5 * ((energy - 74.0) / 2.5) ** 2)
    )
    return energy, background + peaks


def _write_descending_xps(path: Path) -> None:
    energy, intensity = _synthetic_xps()
    pd.DataFrame(
        {
            "Binding Energy (eV)": energy[::-1],
            "Counts": intensity[::-1],
        }
    ).to_csv(path, index=False)


def test_load_xps_preserves_descending_input_context_and_standardizes_axis(tmp_path: Path) -> None:
    path = tmp_path / "survey.csv"
    _write_descending_xps(path)

    table = load_xps_file(path)

    assert table.attrs["input_axis_direction"] == "descending"
    assert np.all(np.diff(table["binding_energy_ev"]) > 0)


def test_load_xps_rejects_nonmonotonic_binding_energy(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    pd.DataFrame(
        {
            "binding_energy_ev": [0, 1, 2, 1.5, 3, 4, 5],
            "intensity": range(7),
        }
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="could not be interpreted"):
        load_xps_file(path)


def test_energy_reference_routes_are_explicit_and_mutually_exclusive() -> None:
    direct = resolve_energy_reference(energy_shift_ev=1.2)
    pair = resolve_energy_reference(reference_observed_ev=284.2, reference_target_ev=284.8)

    assert direct[0] == pytest.approx(1.2)
    assert direct[1] == "explicit_energy_shift"
    assert pair[0] == pytest.approx(0.6)
    assert pair[1] == "observed_to_target_reference"

    with pytest.raises(ValueError, match="either energy_shift_ev"):
        resolve_energy_reference(
            energy_shift_ev=1.0,
            reference_observed_ev=284.0,
            reference_target_ev=285.0,
        )


def test_energy_reference_requires_complete_observed_target_pair() -> None:
    with pytest.raises(ValueError, match="provided together"):
        resolve_energy_reference(reference_observed_ev=284.2)


def test_shirley_background_is_finite_and_matches_endpoints() -> None:
    energy, intensity = _synthetic_xps()

    background, converged, iterations = shirley_background(energy, intensity)

    assert np.isfinite(background).all()
    assert background[0] == pytest.approx(intensity[0])
    assert background[-1] == pytest.approx(intensity[-1])
    assert converged
    assert iterations >= 1


def test_detect_xps_candidates_finds_descriptive_synthetic_peaks() -> None:
    energy, intensity = _synthetic_xps()
    background = np.linspace(intensity[0], intensity[-1], len(intensity))
    processed = intensity - background

    candidates = detect_xps_candidates(
        energy,
        intensity,
        background,
        processed,
        prominence_fraction=0.05,
        min_distance=20,
    )
    positions = candidates["binding_energy_corrected_ev"].to_numpy()

    assert np.any(np.isclose(positions, 74.0, atol=1.0))
    assert np.any(np.isclose(positions, 285.0, atol=1.0))
    assert np.any(np.isclose(positions, 532.0, atol=1.0))
    assert (candidates["fwhm_ev"] > 0).all()


def test_zero_smoothing_window_preserves_values() -> None:
    values = np.arange(9, dtype=float)

    assert np.array_equal(smooth_xps_intensity(values, window_length=0), values)


def test_analyze_xps_writes_artifacts_and_provenance_features(tmp_path: Path) -> None:
    path = tmp_path / "survey.csv"
    output = tmp_path / "outputs"
    _write_descending_xps(path)

    result = analyze_xps(
        path,
        output,
        sample_id="sample-xps",
        background_method="linear",
        energy_shift_ev=0.5,
        acquisition_metadata={
            "spectrum_type": "survey",
            "charge_neutralization": "unknown",
        },
    )

    for key in (
        "processed_spectrum_path",
        "candidate_table_path",
        "feature_path",
        "plot_path",
    ):
        assert Path(result[key]).exists()
    assert result["processed_spectrum"]["binding_energy_corrected_ev"].iloc[0] == pytest.approx(0.5)
    assert result["analysis_result"].source_sha256 is not None
    assert all(feature.instrument == "xps" for feature in result["features"])
    assert all(feature.quality_flag == "review_required" for feature in result["features"])


def test_analyze_xps_records_missing_reference_and_axis_reorder_warnings(tmp_path: Path) -> None:
    path = tmp_path / "survey.csv"
    _write_descending_xps(path)

    result = analyze_xps(path, tmp_path / "outputs", sample_id="sample-xps", background_method="none")
    warnings = result["analysis_result"].warnings

    assert "energy_reference_not_provided" in warnings
    assert "binding_energy_axis_reordered_to_ascending_for_processing" in warnings


def test_analyze_xps_flags_large_explicit_shift(tmp_path: Path) -> None:
    path = tmp_path / "survey.csv"
    _write_descending_xps(path)

    result = analyze_xps(
        path,
        tmp_path / "outputs",
        sample_id="sample-xps",
        background_method="none",
        energy_shift_ev=12.0,
    )

    assert "large_energy_shift_requires_review" in result["analysis_result"].warnings


def test_xps_metadata_validation_happens_before_output_creation(tmp_path: Path) -> None:
    path = tmp_path / "survey.csv"
    output = tmp_path / "outputs"
    _write_descending_xps(path)

    with pytest.raises(ValueError, match="takeoff_angle_deg"):
        analyze_xps(
            path,
            output,
            sample_id="sample-xps",
            acquisition_metadata={"takeoff_angle_deg": 100.0},
        )

    assert not output.exists()


def test_xps_cli_writes_manifest(tmp_path: Path) -> None:
    path = tmp_path / "survey.csv"
    output = tmp_path / "outputs"
    _write_descending_xps(path)

    exit_code = xps_main(
        [
            "--input",
            str(path),
            "--output",
            str(output),
            "--sample-id",
            "sample-xps",
            "--background-method",
            "linear",
            "--spectrum-type",
            "survey",
        ]
    )
    payload = json.loads((output / "xps_analysis_manifest.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["analyses"][0]["instrument"] == "xps"


def test_cli_entry_dispatches_xps_without_changing_legacy_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_xps_main(arguments: list[str]) -> int:
        calls.append(arguments)
        return 17

    monkeypatch.setattr(cli_entry, "xps_main", fake_xps_main)

    assert cli_entry.main(["xps", "--help"]) == 17
    assert calls == [["--help"]]
