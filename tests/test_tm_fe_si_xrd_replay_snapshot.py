from __future__ import annotations

import json
from pathlib import Path


SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "case_studies"
    / "tm_fe_si_xrd_descriptive_handoff"
    / "source_replay_snapshot.json"
)


def test_tm_fe_si_real_source_replay_snapshot_preserves_scientific_boundary() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["source"]["sha256"] == (
        "7138e2e2d6dbf422c7b534af38810bfe963969cd3f8e8b3a7e8daf7ddb17ac20"
    )
    assert payload["result"]["sample_count"] == 6
    assert payload["result"]["measurement_count"] == 6
    assert payload["result"]["feature_count"] == 36
    assert payload["result"]["quality_flag_counts"] == {"review_required": 36}
    assert payload["result"]["maximum_allowed_use"] == "descriptive"
    assert payload["result"]["evidence_level"] == "Diagnostic"
    assert payload["result"]["engineering_release_ready"] is False
    assert payload["result"]["scientific_comparability_established"] is False
    assert payload["result"]["row_order_join_allowed"] is False

    assert len(payload["features"]) == 6
    expected_features = {
        "detected_peak_count",
        "main_peak_two_theta",
        "maximum_two_theta",
        "mean_fwhm",
        "median_fwhm",
        "minimum_two_theta",
    }
    assert all(set(features) == expected_features for features in payload["features"].values())
    assert payload["scientific_boundary"]["absolute_xrd_intensity_cross_composition"] == "Unsupported"
    assert payload["scientific_boundary"]["phase_assignment"] == "Unsupported"
    assert payload["scientific_boundary"]["scherrer_size"] == "Unsupported"
    assert payload["scientific_boundary"]["predictive_causal_engineering"] == "Unsupported"
