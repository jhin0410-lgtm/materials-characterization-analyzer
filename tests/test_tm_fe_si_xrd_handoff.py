from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mca.xrd import detect_peaks, smooth_intensity
from scripts import build_tm_fe_si_xrd_handoff as tm_case


def _cells() -> dict[str, str | float]:
    cells: dict[str, str | float] = {}
    for tm_element, x_col, y_col, title in tm_case.TRACE_CONTRACTS:
        cells[f"{x_col}1"] = title
        cells[f"{x_col}2"] = tm_case.EXPECTED_X_HEADER
        cells[f"{y_col}2"] = tm_case.EXPECTED_Y_HEADER
        for index in range(tm_case.EXPECTED_POINT_COUNT):
            row = index + 3
            x = tm_case.EXPECTED_TWO_THETA_MIN + tm_case.EXPECTED_TWO_THETA_STEP * index
            cells[f"{x_col}{row}"] = float(x)
            cells[f"{y_col}{row}"] = float(1.0 + np.sin(x / 4.0) ** 2)
    return cells


def _synthetic_traces() -> dict[str, pd.DataFrame]:
    x = np.linspace(
        tm_case.EXPECTED_TWO_THETA_MIN,
        tm_case.EXPECTED_TWO_THETA_MAX,
        tm_case.EXPECTED_POINT_COUNT,
    )
    traces: dict[str, pd.DataFrame] = {}
    for offset, (tm_element, *_rest) in enumerate(tm_case.TRACE_CONTRACTS):
        y = (
            1.0
            + offset
            + 2.0 * np.exp(-0.5 * ((x - 35.0) / 0.18) ** 2)
            + 4.0 * np.exp(-0.5 * ((x - (45.0 + 0.03 * offset)) / 0.22) ** 2)
            + 1.5 * np.exp(-0.5 * ((x - 70.0) / 0.25) ** 2)
        )
        traces[tm_element] = pd.DataFrame({"two_theta": x, "intensity": y})
    return traces


def _feature_values(trace: pd.DataFrame) -> dict[str, float]:
    smoothed = smooth_intensity(
        trace["intensity"],
        window_length=tm_case.SMOOTHING_WINDOW,
        polyorder=tm_case.SMOOTHING_POLYORDER,
    )
    peaks = detect_peaks(
        trace["two_theta"],
        trace["intensity"],
        smoothed,
        prominence_fraction=tm_case.PROMINENCE_FRACTION,
        min_distance=tm_case.MIN_DISTANCE,
        edge_margin=tm_case.EDGE_MARGIN,
    )
    features = tm_case._restricted_features(
        peaks, "Ti", "a" * 64, "test-preprocessing"
    )
    return {record.feature_name: float(record.value) for record in features}


def test_frozen_header_mapping_requires_explicit_composition_titles() -> None:
    traces = tm_case._traces_from_cells(_cells())

    assert list(traces) == ["Ti", "Zr", "Hf", "V", "Nb", "Ta"]
    assert all(len(trace) == tm_case.EXPECTED_POINT_COUNT for trace in traces.values())
    assert traces["Ti"].iloc[0]["two_theta"] == pytest.approx(20.0)
    assert traces["Ta"].iloc[-1]["two_theta"] == pytest.approx(90.0)

    broken = _cells()
    broken["C1"] = "Fig. 2(b) Ti7Fe52Si41"
    with pytest.raises(tm_case.TMFeSiXRDHandoffError, match="unexpected trace title"):
        tm_case._traces_from_cells(broken)


def test_restricted_features_are_invariant_to_additive_plot_offset() -> None:
    trace = _synthetic_traces()["Ti"]
    shifted = trace.copy()
    shifted["intensity"] = shifted["intensity"] + 17.0

    original = _feature_values(trace)
    offset = _feature_values(shifted)

    assert set(original) == tm_case.ALLOWED_FEATURES
    assert set(offset) == tm_case.ALLOWED_FEATURES
    assert original == pytest.approx(offset, rel=0.0, abs=1e-10)
    assert "main_peak_intensity" not in original
    assert "mean_scherrer_crystallite_size_estimate" not in original


def test_source_identity_guard_rejects_unpinned_workbook(tmp_path: Path) -> None:
    workbook = tmp_path / tm_case.EXPECTED_WORKBOOK_NAME
    workbook.write_bytes(b"not-the-published-workbook")

    with pytest.raises(tm_case.TMFeSiXRDHandoffError):
        tm_case._validate_workbook_identity(workbook)


def test_build_writes_six_sample_descriptive_bundle_without_raw_intensity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / tm_case.EXPECTED_WORKBOOK_NAME
    workbook.write_bytes(b"software-fixture-only")
    monkeypatch.setattr(
        tm_case,
        "_validate_workbook_identity",
        lambda _path: tm_case.EXPECTED_WORKBOOK_SHA256,
    )
    monkeypatch.setattr(tm_case, "extract_xrd_traces", lambda _path: _synthetic_traces())

    output = tmp_path / "tm-fe-si-xrd-handoff"
    result = tm_case.build_tm_fe_si_xrd_handoff(workbook, output)

    assert result["sample_count"] == 6
    bundle = output / "handoff_bundle"
    features = pd.read_csv(bundle / "characterization_features_long.csv")
    context = pd.read_csv(bundle / "sample_context.csv")
    manifest = json.loads((bundle / "characterization_handoff_bundle.json").read_text(encoding="utf-8"))

    assert len(features) == 6 * len(tm_case.ALLOWED_FEATURES)
    assert set(features["feature_name"]) == tm_case.ALLOWED_FEATURES
    assert set(features["quality_flag"]) == {"review_required"}
    assert set(features["source_sha256"]) == {tm_case.EXPECTED_WORKBOOK_SHA256}
    assert "main_peak_intensity" not in set(features["feature_name"])
    assert "mean_scherrer_crystallite_size_estimate" not in set(features["feature_name"])

    assert len(context) == 6
    assert set(context["sample_id"]) == {
        tm_case.sample_id(tm_element) for tm_element, *_rest in tm_case.TRACE_CONTRACTS
    }
    assert set(
        context["exact_xrd_vsm_specimen_identity_confirmed"].astype(str).str.lower()
    ) == {"false"}

    assert manifest["downstream_use_policy"]["maximum_allowed_use"] == "descriptive"
    assert manifest["downstream_use_policy"]["evidence_level"] == "Diagnostic"
    assert manifest["join_contract"]["join_key"] == "sample_id"
    assert manifest["join_contract"]["row_order_join_allowed"] is False
    assert "predictive modeling" in manifest["scientific_closeout"]["unsuitable_for"]

    summary = json.loads((output / "case_summary.json").read_text(encoding="utf-8"))
    assert summary["scientific_validation"] == "Diagnostic"
    assert summary["downstream_maximum_allowed_use"] == "descriptive"
    assert summary["raw_workbook_committed"] is False


def test_build_refuses_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = tmp_path / tm_case.EXPECTED_WORKBOOK_NAME
    workbook.write_bytes(b"irrelevant")
    monkeypatch.setattr(
        tm_case,
        "_validate_workbook_identity",
        lambda _path: tm_case.EXPECTED_WORKBOOK_SHA256,
    )
    monkeypatch.setattr(tm_case, "extract_xrd_traces", lambda _path: _synthetic_traces())
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(FileExistsError):
        tm_case.build_tm_fe_si_xrd_handoff(workbook, output)
