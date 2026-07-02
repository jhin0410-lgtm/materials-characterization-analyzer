from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from mca.cli import main
from mca.features import (
    build_sample_features_table,
    combine_sample_features,
    extract_eds_features,
    extract_sem_features,
    extract_xrd_features,
    save_sample_features,
)


DATA = Path(__file__).resolve().parents[1] / "data" / "demo"


def test_extract_xrd_features_from_peak_table() -> None:
    peak_table = pd.DataFrame(
        {
            "two_theta_deg": [20.0, 35.0, 50.0],
            "intensity": [100.0, 250.0, 150.0],
            "fwhm_deg_2theta": [0.2, 0.3, 0.4],
        }
    )

    features = extract_xrd_features(peak_table)

    assert features["xrd_number_of_peaks"] == 3
    assert features["xrd_main_peak_two_theta"] == 35.0
    assert features["xrd_main_peak_intensity"] == 250.0
    assert features["xrd_mean_fwhm_deg_2theta"] == pytest.approx(0.3)
    assert features["xrd_median_fwhm_deg_2theta"] == pytest.approx(0.3)
    assert features["xrd_min_two_theta"] == 20.0
    assert features["xrd_max_two_theta"] == 50.0


def test_extract_xrd_features_without_crystallite_size_returns_nan() -> None:
    peak_table = pd.DataFrame({"two_theta_deg": [20.0], "intensity": [100.0], "fwhm_deg_2theta": [0.2]})

    features = extract_xrd_features(peak_table)

    assert math.isnan(features["xrd_estimated_crystallite_size_mean_nm"])


def test_extract_xrd_features_with_crystallite_size_calculates_mean() -> None:
    peak_table = pd.DataFrame(
        {
            "two_theta_deg": [20.0, 30.0],
            "intensity": [100.0, 200.0],
            "fwhm_deg_2theta": [0.2, 0.4],
            "crystallite_size_estimate_nm": [12.0, 18.0],
        }
    )

    features = extract_xrd_features(peak_table)

    assert features["xrd_estimated_crystallite_size_mean_nm"] == pytest.approx(15.0)


def test_extract_sem_features_from_measurements() -> None:
    measurements = pd.DataFrame(
        {
            "area_microns2": [10.0, 20.0, 30.0],
            "equivalent_diameter_microns": [2.0, 4.0, 6.0],
            "area_fraction": [0.25, 0.25, 0.25],
        }
    )

    features = extract_sem_features(measurements)

    assert features["sem_detected_region_count"] == 3
    assert features["sem_particle_count"] == 3
    assert features["sem_mean_equivalent_diameter_um"] == pytest.approx(4.0)
    assert features["sem_median_equivalent_diameter_um"] == pytest.approx(4.0)
    assert features["sem_area_fraction"] == pytest.approx(0.25)
    assert features["sem_total_detected_area_um2"] == pytest.approx(60.0)


def test_extract_sem_features_handles_empty_table() -> None:
    features = extract_sem_features(pd.DataFrame())

    assert features["sem_detected_region_count"] == 0
    assert features["sem_particle_count"] == 0
    assert math.isnan(features["sem_mean_equivalent_diameter_um"])
    assert features["sem_total_detected_area_um2"] == 0.0


def test_extract_eds_features_creates_element_columns() -> None:
    composition = pd.DataFrame(
        {
            "element": ["Fe", "O"],
            "weight_percent": [70.0, 30.0],
            "atomic_percent": [60.0, 40.0],
        }
    )

    features = extract_eds_features(composition)

    assert features["eds_number_of_elements"] == 2
    assert features["eds_top_element"] == "Fe"
    assert features["eds_top_element_weight_percent"] == pytest.approx(70.0)
    assert features["eds_total_weight_percent"] == pytest.approx(100.0)
    assert features["eds_total_atomic_percent"] == pytest.approx(100.0)
    assert features["eds_wt_Fe"] == pytest.approx(70.0)
    assert features["eds_at_O"] == pytest.approx(40.0)


def test_combine_sample_features_returns_single_row_values() -> None:
    xrd = pd.DataFrame({"two_theta_deg": [20.0], "intensity": [100.0], "fwhm_deg_2theta": [0.2]})
    sem = pd.DataFrame({"area_microns2": [5.0], "equivalent_diameter_microns": [2.5], "area_fraction": [0.1]})
    eds = pd.DataFrame({"element": ["Al"], "weight_percent": [100.0], "atomic_percent": [100.0]})

    features = combine_sample_features("sample_a", xrd, sem, eds)

    assert features["sample_id"] == "sample_a"
    assert features["xrd_number_of_peaks"] == 1
    assert features["sem_detected_region_count"] == 1
    assert features["eds_wt_Al"] == pytest.approx(100.0)


def test_save_sample_features_writes_csv(tmp_path: Path) -> None:
    table = build_sample_features_table(sample_id="sample_a", eds_composition_table=pd.DataFrame())

    path = save_sample_features(table, tmp_path)

    assert path.exists()
    saved = pd.read_csv(path)
    assert saved.loc[0, "sample_id"] == "sample_a"


def test_analyze_all_extract_features_smoke_test(tmp_path: Path) -> None:
    exit_code = main(
        [
            "analyze-all",
            "--xrd",
            str(DATA / "synthetic_xrd.csv"),
            "--sem",
            str(DATA / "synthetic_sem.png"),
            "--eds",
            str(DATA / "synthetic_eds.csv"),
            "--microns-per-pixel",
            "0.05",
            "--output",
            str(tmp_path),
            "--extract-features",
            "--sample-id",
            "demo_synthetic_sample",
        ]
    )

    feature_path = tmp_path / "sample_features.csv"
    assert exit_code == 0
    assert feature_path.exists()
    features = pd.read_csv(feature_path)
    assert features.loc[0, "sample_id"] == "demo_synthetic_sample"
    assert "xrd_number_of_peaks" in features.columns
    assert "sem_detected_region_count" in features.columns
    assert "eds_number_of_elements" in features.columns
