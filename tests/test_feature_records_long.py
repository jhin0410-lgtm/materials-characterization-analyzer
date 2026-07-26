from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mca.cli import main
from mca.feature_records import (
    LONG_FEATURE_COLUMNS,
    build_characterization_feature_records,
    build_xrd_feature_records,
    records_to_frame,
)


def test_build_characterization_feature_records_uses_stable_long_schema(tmp_path: Path) -> None:
    xrd_source = tmp_path / "raw_xrd.csv"
    xrd_source.write_text("two_theta,intensity\n20,100\n", encoding="utf-8")
    xrd = pd.DataFrame(
        {
            "two_theta_deg": [20.0, 35.0],
            "intensity": [100.0, 250.0],
            "fwhm_deg_2theta": [0.2, 0.4],
        }
    )
    sem = pd.DataFrame(
        {
            "area_microns2": [1.0, 3.0],
            "equivalent_diameter_microns": [1.1, 1.9],
            "area_fraction": [0.2, 0.2],
        }
    )
    eds = pd.DataFrame(
        {
            "element": ["Fe", "O"],
            "weight_percent": [70.0, 30.0],
            "atomic_percent": [60.0, 40.0],
        }
    )

    records = build_characterization_feature_records(
        sample_id="sample-a",
        xrd_peak_table=xrd,
        sem_measurements=sem,
        eds_composition_table=eds,
        source_files={"xrd": xrd_source},
        preprocessing_ids={"xrd": "xrd-prep"},
    )
    frame = records_to_frame(records)

    assert list(frame.columns) == LONG_FEATURE_COLUMNS
    assert set(frame["instrument"]) == {"xrd", "sem", "eds"}
    main_peak = frame[(frame["instrument"] == "xrd") & (frame["feature_name"] == "main_peak_two_theta")].iloc[0]
    assert main_peak["value"] == 35.0
    assert main_peak["unit"] == "deg_2theta"
    assert main_peak["source_sha256"]
    assert main_peak["preprocessing_id"] == "xrd-prep"

    fe_weight = frame[
        (frame["instrument"] == "eds")
        & (frame["feature_name"] == "element_weight_percent")
        & (frame["feature_label"] == "Fe")
    ].iloc[0]
    assert fe_weight["value"] == 70.0
    assert fe_weight["quality_flag"] == "review_required"


def test_xrd_generic_scherrer_unit_is_not_relabelled_as_nm() -> None:
    xrd = pd.DataFrame(
        {
            "two_theta_deg": [20.0],
            "intensity": [100.0],
            "fwhm_deg_2theta": [0.2],
            "crystallite_size_estimate_same_unit_as_wavelength": [12.0],
        }
    )

    records = build_xrd_feature_records(xrd, sample_id="sample-a")
    scherrer = next(record for record in records if record.feature_name == "mean_scherrer_crystallite_size_estimate")

    assert scherrer.unit == "same_as_wavelength"
    assert scherrer.quality_flag == "unit_unresolved"


def test_feature_records_cli_writes_csv_and_manifest(tmp_path: Path) -> None:
    xrd_table = tmp_path / "xrd_peaks.csv"
    pd.DataFrame(
        {
            "two_theta_deg": [20.0],
            "intensity": [100.0],
            "fwhm_deg_2theta": [0.2],
        }
    ).to_csv(xrd_table, index=False)
    raw_source = tmp_path / "raw_xrd.xy"
    raw_source.write_text("20 100\n", encoding="utf-8")
    output = tmp_path / "output"

    exit_code = main(
        [
            "feature-records",
            "--sample-id",
            "sample-a",
            "--xrd-peaks",
            str(xrd_table),
            "--xrd-source",
            str(raw_source),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    feature_path = output / "characterization_features_long.csv"
    manifest_path = output / "characterization_manifest.json"
    assert feature_path.exists()
    assert manifest_path.exists()
    feature_table = pd.read_csv(feature_path)
    assert set(feature_table["instrument"]) == {"xrd"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["analysis_count"] == 1
    assert manifest["analyses"][0]["source_sha256"]
    assert "preprocessing_history_not_provided" in manifest["analyses"][0]["warnings"]
