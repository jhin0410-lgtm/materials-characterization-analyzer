from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_public_zr15nb_dsc_case as case  # noqa: E402


def _config() -> dict:
    return {
        "column_binding": {
            "header_row_count": 3,
            "expected_headers": [
                ["DSC", ""],
                ["Temperature", "DSC signal"],
                ["°C", "mW/mg"],
            ],
            "temperature_column_index": 0,
            "signal_column_index": 1,
            "source_signal_unit": "mW/mg",
            "canonical_signal_type": "heat_flow_w_g",
            "source_to_canonical_factor": 1.0,
            "conversion_basis": "1 mW/mg equals 1 W/g",
            "sorting_allowed": False,
            "interpolation_allowed": False,
            "exclusion_allowed": False,
        }
    }


def _payload(rows: list[tuple[float, float]]) -> bytes:
    lines = [
        "DSC,",
        "Temperature,DSC signal",
        "°C,mW/mg",
        *[f"{temperature},{signal}" for temperature, signal in rows],
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_adapter_preserves_order_and_identity_unit_conversion() -> None:
    rows = [(80.0 + index * 0.5, -0.01 + index * 0.001) for index in range(8)]
    canonical, record = case.adapt_dsc_source(_payload(rows), _config())

    assert canonical.columns.tolist() == ["temperature_c", "signal"]
    assert canonical["temperature_c"].tolist() == [row[0] for row in rows]
    assert canonical["signal"].tolist() == pytest.approx([row[1] for row in rows])
    assert record["source_to_canonical_factor"] == 1.0
    assert record["source_rows_sorted"] is False
    assert record["source_rows_interpolated"] is False
    assert record["source_rows_excluded"] == 0
    assert record["temperature_strictly_increasing"] is True


def test_adapter_rejects_header_drift() -> None:
    payload = _payload([(80.0 + index, 0.1 * index) for index in range(8)])
    config = copy.deepcopy(_config())
    config["column_binding"]["expected_headers"][2][1] = "mW"
    with pytest.raises(case.CaseError, match="header contract changed"):
        case.adapt_dsc_source(payload, config)


def test_adapter_rejects_nonmonotonic_temperature_without_sorting() -> None:
    rows = [
        (80.0, 0.0),
        (81.0, 0.1),
        (82.0, 0.2),
        (81.5, 0.3),
        (83.0, 0.4),
        (84.0, 0.5),
        (85.0, 0.6),
        (86.0, 0.7),
    ]
    with pytest.raises(case.CaseError, match="not one strictly increasing segment"):
        case.adapt_dsc_source(_payload(rows), _config())


def test_adapter_rejects_any_permission_to_modify_rows() -> None:
    payload = _payload([(80.0 + index, 0.1 * index) for index in range(8)])
    for key in ("sorting_allowed", "interpolation_allowed", "exclusion_allowed"):
        config = copy.deepcopy(_config())
        config["column_binding"][key] = True
        with pytest.raises(case.CaseError, match="must prohibit"):
            case.adapt_dsc_source(payload, config)


def test_smoothing_span_converts_to_odd_window_without_axis_mutation() -> None:
    temperature = np.arange(80.0, 90.01, 0.1)
    original = temperature.copy()
    window, actual_span = case.smoothing_span_to_window(
        temperature,
        span_c=2.0,
        polyorder=3,
    )
    assert window == 21
    assert actual_span == pytest.approx(2.0)
    assert np.array_equal(temperature, original)


def test_candidate_distance_uses_ceiling_in_samples() -> None:
    temperature = np.arange(80.0, 100.01, 0.25)
    assert case.distance_c_to_samples(temperature, 10.1) == 41


def test_smoothing_and_distance_require_strictly_increasing_axis() -> None:
    temperature = [80.0, 81.0, 80.5, 82.0]
    with pytest.raises(case.CaseError, match="strictly increasing"):
        case.smoothing_span_to_window(temperature, span_c=1.0, polyorder=2)
    with pytest.raises(case.CaseError, match="strictly increasing"):
        case.distance_c_to_samples(temperature, 1.0)
