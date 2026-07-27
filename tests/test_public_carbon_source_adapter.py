from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.execute_public_carbon_multimodal_case import (
    adapt_public_tga_air_source,
    review_tga_case_candidates,
)


def test_cp1252_tga_adapter_excludes_only_initial_stabilization(tmp_path: Path) -> None:
    source = tmp_path / "tga_cp1252.tab"
    frame = pd.DataFrame(
        {
            "Temperature (°C)": [20.90, 20.91, 20.88, 20.89, 21.00, 21.20, 21.40, 21.60, 21.80, 22.00],
            "Time (s)": [0, 3, 6, 9, 12, 15, 18, 21, 24, 27],
            "TG (mg)": [0] * 10,
            "TG blank (mg)": [0] * 10,
            "TG Corb (mg)": [0] * 10,
            "TG DWCNT (%)": [100, 100, 100, 100, 99.9, 99.8, 99.7, 99.6, 99.5, 99.4],
            "dTG DWCNT (% min-1)": [0] * 10,
        }
    )
    frame.to_csv(source, sep=";", index=False, encoding="cp1252")
    destination = tmp_path / "canonical.csv"
    record = adapt_public_tga_air_source(source, destination)
    canonical = pd.read_csv(destination)
    assert record["source_encoding"] == "cp1252"
    assert record["initial_stabilization_rows_excluded"] == 2
    assert canonical["temperature_c"].is_monotonic_increasing
    assert canonical.iloc[0]["temperature_c"] == 20.88
    assert "no sorting or interpolation" in record["heating_segment_rule"]


def test_tga_case_review_preserves_raw_candidates_and_rejects_startup_artifact(
    tmp_path: Path,
) -> None:
    tga_dir = tmp_path / "analyses" / "tga"
    tga_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "temperature_c": [21.0, 21.05, 21.1, 100.0, 300.0, 471.0, 700.0, 900.0],
            "signal": [100, 99.99, 99.98, 99, 90, 42, 20, 10],
        }
    ).to_csv(tga_dir / "thermal_processed_data.csv", index=False)
    raw_candidates = pd.DataFrame(
        {
            "candidate_id": [1, 2],
            "candidate_type": ["mass_loss_rate", "mass_loss_rate"],
            "temperature_c": [21.06, 471.0],
            "fwhm_c": [0.02, 29.0],
            "mass_change_within_fwhm_percent": [0.01, 48.8],
        }
    )
    raw_candidates.to_csv(tga_dir / "thermal_event_candidates.csv", index=False)
    (tmp_path / "case_validation_report.md").write_text(
        "# Report\n\n- **TGA-air:** 2 review-required candidates: 21.1 degC, 471 degC.\n",
        encoding="utf-8",
    )
    (tmp_path / "case_summary.json").write_text(
        json.dumps({"evidence_level": "Diagnostic"}), encoding="utf-8"
    )

    counts = review_tga_case_candidates(tmp_path)

    assert counts == {
        "raw_candidate_count": 2,
        "retained_review_required_count": 1,
        "rejected_startup_boundary_artifact_count": 1,
    }
    review = pd.read_csv(tga_dir / "tga_case_candidate_review.csv")
    assert review.loc[0, "case_review_status"] == "rejected_startup_boundary_artifact"
    assert review.loc[1, "case_review_status"] == "retained_review_required"
    preserved = pd.read_csv(tga_dir / "thermal_event_candidates.csv")
    pd.testing.assert_frame_equal(preserved, raw_candidates)
    report = (tmp_path / "case_validation_report.md").read_text(encoding="utf-8")
    assert "1 retained review-required candidate(s): 471 degC" in report
    assert "Raw analyzer candidates remain preserved" in report
