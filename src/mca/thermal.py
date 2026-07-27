"""Conservative TGA and DSC baseline analysis with explicit units and provenance.

The workflow extracts descriptive thermal-event candidates only. It does not
assign reactions, decomposition mechanisms, phase transitions, glass
transitions, melting, crystallization, or quantitative composition.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mca_matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError, ParserError
from scipy.integrate import trapezoid
from scipy.signal import find_peaks, peak_widths, savgol_filter

from .contracts import PreprocessingStep
from .feature_records import records_to_frame
from .provenance import build_analysis_result, preprocessing_fingerprint
from .thermal_features import build_thermal_feature_records
from .utils import ensure_output_dir

SUPPORTED_THERMAL_EXTENSIONS = {".csv", ".txt", ".tsv"}
TGA_SIGNAL_TYPES = {"mass_percent", "mass_fraction", "mass_mg"}
DSC_SIGNAL_TYPES = {"heat_flow_mw", "heat_flow_w_g"}
THERMAL_MODES = {"tga", "dsc"}
THERMAL_LIMITATIONS = [
    "Automatically detected thermal candidates do not identify reactions, mechanisms, phases, or chemical species.",
    "TGA derivative candidates depend on temperature sampling, smoothing, mass normalization, drift, buoyancy, and threshold settings.",
    "DSC candidate direction depends on the user-supplied endotherm convention and selected baseline.",
    "Candidate FWHM and within-FWHM area are descriptive values, not validated onset, peak-fit, or deconvoluted parameters.",
    "Calculated DSC enthalpy is diagnostic and requires validated heat-flow calibration, sample mass, and time or heating-rate information.",
    "Glass-transition analysis, extrapolated onset, kinetic modeling, evolved-gas analysis, and quantitative composition are not implemented.",
    "Atmosphere, purge flow, crucible, sample mass, geometry, calibration, thermal history, and temperature program require expert review.",
]


def load_thermal_file(path: str | Path) -> pd.DataFrame:
    """Load temperature, optional time, and one thermal signal column.

    Headerless files may contain either temperature/signal or
    temperature/time/signal. This release accepts one strictly increasing
    heating segment only.
    """
    input_path = _validate_input_path(path)
    source_name = f"Thermal file '{input_path}'"
    for header in (0, None):
        for separator in _separators(input_path):
            try:
                table = _read_table(input_path, separator, header, source_name)
            except ParserError:
                continue
            try:
                standardized = (
                    _standardize_headerless(table) if header is None else _normalize_columns(table)
                )
                return _validate_dataframe(standardized, source_name)
            except ValueError:
                continue
    raise ValueError(
        f"{source_name} could not be interpreted as supported thermal data. "
        "Expected temperature in degC, one signal column, and optional time in seconds."
    )


def validate_mode_and_signal_type(mode: str, signal_type: str) -> None:
    """Validate explicit mode/signal semantics."""
    if mode not in THERMAL_MODES:
        raise ValueError("mode must be 'tga' or 'dsc'.")
    allowed = TGA_SIGNAL_TYPES if mode == "tga" else DSC_SIGNAL_TYPES
    if signal_type not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"signal_type for {mode} must be one of: {allowed_text}.")


def convert_tga_signal(
    signal: pd.Series | np.ndarray,
    *,
    signal_type: str,
    initial_mass_mg: float | None = None,
) -> tuple[pd.DataFrame, str, list[str]]:
    """Convert an explicit TGA signal to mass-retention percent."""
    if signal_type not in TGA_SIGNAL_TYPES:
        raise ValueError("Unsupported TGA signal_type.")
    values = _validate_signal_array(signal, name="TGA signal")
    warnings: list[str] = []
    mass_mg = np.full(len(values), np.nan, dtype=float)
    if signal_type == "mass_percent":
        mass_retention = values.copy()
        reference_method = "input_mass_percent"
    elif signal_type == "mass_fraction":
        mass_retention = 100.0 * values
        reference_method = "input_mass_fraction_times_100"
    else:
        if np.any(values <= 0):
            raise ValueError("mass_mg values must be greater than zero.")
        mass_mg = values.copy()
        if initial_mass_mg is None:
            reference = float(values[0])
            reference_method = "first_signal_value_as_mass_reference"
            warnings.append("tga_first_point_used_as_mass_reference")
        else:
            reference = _validate_positive_optional(initial_mass_mg, "initial_mass_mg")
            reference_method = "explicit_initial_mass_mg"
            if abs(reference - float(values[0])) / reference > 0.05:
                warnings.append("tga_initial_mass_differs_from_first_signal_by_more_than_5_percent")
        mass_retention = 100.0 * values / reference
    if np.nanmax(mass_retention) > 102.0:
        warnings.append("tga_mass_retention_exceeds_102_percent")
    if np.nanmin(mass_retention) < 0.0:
        warnings.append("tga_mass_retention_below_zero")
    return (
        pd.DataFrame(
            {
                "raw_signal": values,
                "mass_mg": mass_mg,
                "mass_retention_percent": mass_retention,
            }
        ),
        reference_method,
        warnings,
    )


def convert_dsc_signal(
    signal: pd.Series | np.ndarray,
    *,
    signal_type: str,
    sample_mass_mg: float | None = None,
) -> tuple[pd.DataFrame, str, list[str]]:
    """Convert an explicit DSC signal while preserving raw and normalized units."""
    if signal_type not in DSC_SIGNAL_TYPES:
        raise ValueError("Unsupported DSC signal_type.")
    values = _validate_signal_array(signal, name="DSC signal")
    warnings: list[str] = []
    heat_flow_mw = np.full(len(values), np.nan, dtype=float)
    heat_flow_w_g = np.full(len(values), np.nan, dtype=float)
    if signal_type == "heat_flow_w_g":
        heat_flow_w_g = values.copy()
        reference_method = "input_heat_flow_w_g"
        if sample_mass_mg is not None:
            mass = _validate_positive_optional(sample_mass_mg, "sample_mass_mg")
            heat_flow_mw = values * mass
    else:
        heat_flow_mw = values.copy()
        if sample_mass_mg is None:
            reference_method = "input_heat_flow_mw_without_mass_normalization"
            warnings.append("dsc_sample_mass_missing_heat_flow_not_normalized")
        else:
            mass = _validate_positive_optional(sample_mass_mg, "sample_mass_mg")
            heat_flow_w_g = values / mass
            reference_method = "input_heat_flow_mw_divided_by_sample_mass_mg"
    return (
        pd.DataFrame(
            {
                "raw_signal": values,
                "heat_flow_mw": heat_flow_mw,
                "heat_flow_w_g": heat_flow_w_g,
            }
        ),
        reference_method,
        warnings,
    )


def smooth_thermal_signal(
    signal: pd.Series | np.ndarray,
    *,
    window_length: int = 11,
    polyorder: int = 3,
) -> np.ndarray:
    """Apply optional Savitzky-Golay smoothing; zero disables smoothing."""
    values = _validate_signal_array(signal, name="Thermal signal")
    if window_length == 0:
        return values.copy()
    if window_length < 0 or polyorder < 0:
        raise ValueError("smoothing parameters must be non-negative.")
    window = _valid_savgol_window(len(values), int(window_length), int(polyorder))
    return values.copy() if window is None else savgol_filter(values, window, polyorder)


def calculate_tga_profile(
    temperature_c: pd.Series | np.ndarray,
    mass_retention_percent: pd.Series | np.ndarray,
    *,
    smoothing_window: int = 11,
    smoothing_polyorder: int = 3,
) -> pd.DataFrame:
    """Calculate smoothed mass retention and positive mass-loss rate."""
    temperature = _validate_temperature_array(temperature_c)
    retention = _validate_signal_array(mass_retention_percent, name="Mass retention")
    if len(temperature) != len(retention):
        raise ValueError("Temperature and mass-retention arrays must have the same length.")
    smoothed = smooth_thermal_signal(
        retention,
        window_length=smoothing_window,
        polyorder=smoothing_polyorder,
    )
    derivative = np.gradient(smoothed, temperature)
    return pd.DataFrame(
        {
            "mass_retention_smoothed_percent": smoothed,
            "mass_loss_rate_percent_per_c": -derivative,
        }
    )


def detect_tga_candidates(
    temperature_c: pd.Series | np.ndarray,
    mass_retention_percent: pd.Series | np.ndarray,
    mass_loss_rate_percent_per_c: pd.Series | np.ndarray,
    *,
    prominence_fraction: float = 0.08,
    min_distance: int = 5,
    edge_margin: int = 2,
) -> pd.DataFrame:
    """Detect descriptive DTG-like mass-loss candidates."""
    temperature = _validate_temperature_array(temperature_c)
    retention = _validate_signal_array(mass_retention_percent, name="Mass retention")
    loss_rate = _validate_signal_array(mass_loss_rate_percent_per_c, name="Mass-loss rate")
    if not (len(temperature) == len(retention) == len(loss_rate)):
        raise ValueError("TGA arrays must have the same length.")
    _validate_candidate_parameters(prominence_fraction, min_distance)
    positive_rate = np.clip(loss_rate, 0.0, None)
    dynamic_range = float(np.ptp(positive_rate))
    if dynamic_range <= 0 or len(temperature) < 3:
        return _empty_tga_candidate_table()
    peaks, properties = find_peaks(
        positive_rate,
        prominence=max(dynamic_range * prominence_fraction, np.finfo(float).eps),
        distance=int(min_distance),
    )
    peaks, properties = _apply_edge_margin(peaks, properties, len(temperature), edge_margin)
    if len(peaks) == 0:
        return _empty_tga_candidate_table()
    _, half_height, left_ips, right_ips = peak_widths(positive_rate, peaks, rel_height=0.5)
    sample_index = np.arange(len(temperature), dtype=float)
    left_temp = np.interp(left_ips, sample_index, temperature)
    right_temp = np.interp(right_ips, sample_index, temperature)
    left_mass = np.interp(left_temp, temperature, retention)
    right_mass = np.interp(right_temp, temperature, retention)
    return pd.DataFrame(
        {
            "candidate_id": np.arange(1, len(peaks) + 1),
            "candidate_type": "mass_loss_rate",
            "temperature_c": temperature[peaks],
            "mass_retention_percent": retention[peaks],
            "mass_loss_rate_percent_per_c": positive_rate[peaks],
            "prominence_percent_per_c": properties["prominences"],
            "fwhm_c": right_temp - left_temp,
            "left_fwhm_c": left_temp,
            "right_fwhm_c": right_temp,
            "half_height_percent_per_c": half_height,
            "mass_change_within_fwhm_percent": left_mass - right_mass,
        }
    ).sort_values("temperature_c").reset_index(drop=True)


def calculate_dsc_baseline(
    signal: pd.Series | np.ndarray,
    *,
    method: str,
) -> np.ndarray:
    """Calculate a simple selected DSC baseline."""
    values = _validate_signal_array(signal, name="DSC oriented heat flow")
    if method == "none":
        return np.zeros_like(values)
    if method == "linear":
        return np.linspace(values[0], values[-1], len(values), dtype=float)
    raise ValueError("baseline_method must be 'none' or 'linear'.")


def detect_dsc_candidates(
    temperature_c: pd.Series | np.ndarray,
    processed_signal: pd.Series | np.ndarray,
    corrected_signal: pd.Series | np.ndarray,
    *,
    time_s: pd.Series | np.ndarray | None = None,
    heating_rate_c_min: float | None = None,
    signal_is_w_g: bool = False,
    prominence_fraction: float = 0.08,
    min_distance: int = 5,
    edge_margin: int = 2,
) -> pd.DataFrame:
    """Detect descriptive endothermic and exothermic DSC candidates.

    The processed signal must use the convention endotherm-positive.
    """
    temperature = _validate_temperature_array(temperature_c)
    processed = _validate_signal_array(processed_signal, name="Processed DSC signal")
    corrected = _validate_signal_array(corrected_signal, name="Corrected DSC signal")
    if not (len(temperature) == len(processed) == len(corrected)):
        raise ValueError("DSC arrays must have the same length.")
    _validate_candidate_parameters(prominence_fraction, min_distance)
    time_values = None if time_s is None else _validate_time_array(time_s, expected_length=len(temperature))
    rate = None if heating_rate_c_min is None else _validate_positive_optional(
        heating_rate_c_min, "heating_rate_c_min"
    )
    rows: list[dict[str, object]] = []
    for candidate_type, candidate_signal, sign in (
        ("endothermic", processed, 1.0),
        ("exothermic", -processed, -1.0),
    ):
        dynamic_range = float(np.ptp(candidate_signal))
        if dynamic_range <= 0:
            continue
        peaks, properties = find_peaks(
            candidate_signal,
            prominence=max(dynamic_range * prominence_fraction, np.finfo(float).eps),
            distance=int(min_distance),
        )
        peaks, properties = _apply_edge_margin(peaks, properties, len(temperature), edge_margin)
        if len(peaks) == 0:
            continue
        _, half_height, left_ips, right_ips = peak_widths(candidate_signal, peaks, rel_height=0.5)
        sample_index = np.arange(len(temperature), dtype=float)
        left_temp = np.interp(left_ips, sample_index, temperature)
        right_temp = np.interp(right_ips, sample_index, temperature)
        for index, peak in enumerate(peaks):
            lower = float(left_temp[index])
            upper = float(right_temp[index])
            area_signal_c = _integrate_within_bounds(temperature, corrected, lower, upper)
            enthalpy_j_g = np.nan
            if signal_is_w_g:
                if time_values is not None:
                    enthalpy_j_g = _integrate_with_time_bounds(
                        temperature, time_values, corrected, lower, upper
                    )
                elif rate is not None:
                    enthalpy_j_g = area_signal_c * 60.0 / rate
            rows.append(
                {
                    "candidate_type": candidate_type,
                    "temperature_c": temperature[peak],
                    "processed_signal": processed[peak],
                    "corrected_signal": corrected[peak],
                    "prominence": properties["prominences"][index],
                    "fwhm_c": upper - lower,
                    "left_fwhm_c": lower,
                    "right_fwhm_c": upper,
                    "half_height_directional_signal": half_height[index],
                    "area_within_fwhm_signal_c": area_signal_c,
                    "enthalpy_within_fwhm_j_g": enthalpy_j_g,
                    "direction_sign": sign,
                }
            )
    if not rows:
        return _empty_dsc_candidate_table()
    table = pd.DataFrame(rows).sort_values(["temperature_c", "candidate_type"]).reset_index(drop=True)
    table.insert(0, "candidate_id", np.arange(1, len(table) + 1))
    return table


def analyze_thermal(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    sample_id: str,
    mode: str,
    signal_type: str,
    measurement_id: str | None = None,
    initial_mass_mg: float | None = None,
    endotherm_direction: str = "up",
    baseline_method: str = "linear",
    smoothing_window: int = 11,
    smoothing_polyorder: int = 3,
    prominence_fraction: float = 0.08,
    min_distance: int = 5,
    acquisition_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Run one conservative TGA or DSC baseline workflow."""
    if not sample_id.strip():
        raise ValueError("sample_id must not be empty.")
    validate_mode_and_signal_type(mode, signal_type)
    if endotherm_direction not in {"up", "down"}:
        raise ValueError("endotherm_direction must be 'up' or 'down'.")
    if mode == "tga" and baseline_method != "none":
        raise ValueError("TGA mode requires baseline_method='none'.")
    if mode == "dsc" and baseline_method not in {"none", "linear"}:
        raise ValueError("DSC baseline_method must be 'none' or 'linear'.")
    metadata = _validate_acquisition_metadata(acquisition_metadata)
    if initial_mass_mg is not None:
        _validate_positive_optional(initial_mass_mg, "initial_mass_mg")
    spectrum = load_thermal_file(input_path)
    temperature = spectrum["temperature_c"].to_numpy(dtype=float)
    raw_signal = spectrum["signal"].to_numpy(dtype=float)
    time_values = spectrum["time_s"].to_numpy(dtype=float) if "time_s" in spectrum.columns else None
    output_dir = ensure_output_dir(output_dir)
    steps = [
        PreprocessingStep(
            "thermal-import",
            "thermal_temperature_signal_validation",
            {
                "mode": mode,
                "signal_type": signal_type,
                "temperature_requirement": "strictly_increasing_single_segment",
                "time_axis_present": time_values is not None,
            },
        )
    ]
    warnings: list[str] = []
    if mode == "tga":
        converted, reference_method, conversion_warnings = convert_tga_signal(
            raw_signal, signal_type=signal_type, initial_mass_mg=initial_mass_mg
        )
        warnings.extend(conversion_warnings)
        steps.append(
            PreprocessingStep(
                "thermal-signal-conversion",
                reference_method,
                {"signal_type": signal_type, "initial_mass_mg": initial_mass_mg},
            )
        )
        profile = calculate_tga_profile(
            temperature,
            converted["mass_retention_percent"],
            smoothing_window=smoothing_window,
            smoothing_polyorder=smoothing_polyorder,
        )
        processed_table = pd.concat(
            [spectrum.reset_index(drop=True), converted.reset_index(drop=True), profile.reset_index(drop=True)],
            axis=1,
        )
        steps.append(
            PreprocessingStep(
                "thermal-smoothing-and-derivative",
                "savgol_then_negative_temperature_gradient"
                if smoothing_window
                else "negative_temperature_gradient_without_smoothing",
                {
                    "requested_window_length": smoothing_window,
                    "polyorder": smoothing_polyorder,
                    "derivative_unit": "mass_retention_percent_per_degC",
                },
            )
        )
        candidate_table = detect_tga_candidates(
            temperature,
            converted["mass_retention_percent"],
            profile["mass_loss_rate_percent_per_c"],
            prominence_fraction=prominence_fraction,
            min_distance=min_distance,
        )
        plot_signal_unit = "Mass retention (%)"
    else:
        sample_mass_mg = metadata.get("sample_mass_mg")
        converted, reference_method, conversion_warnings = convert_dsc_signal(
            raw_signal, signal_type=signal_type, sample_mass_mg=sample_mass_mg
        )
        warnings.extend(conversion_warnings)
        steps.append(
            PreprocessingStep(
                "thermal-signal-conversion",
                reference_method,
                {"signal_type": signal_type, "sample_mass_mg": sample_mass_mg},
            )
        )
        normalized_available = converted["heat_flow_w_g"].notna().all()
        base_signal = (
            converted["heat_flow_w_g"].to_numpy(dtype=float)
            if normalized_available
            else converted["heat_flow_mw"].to_numpy(dtype=float)
        )
        orientation = 1.0 if endotherm_direction == "up" else -1.0
        oriented = orientation * base_signal
        baseline = calculate_dsc_baseline(oriented, method=baseline_method)
        corrected = oriented - baseline
        processed = smooth_thermal_signal(
            corrected, window_length=smoothing_window, polyorder=smoothing_polyorder
        )
        processed_table = pd.concat(
            [
                spectrum.reset_index(drop=True),
                converted.reset_index(drop=True),
                pd.DataFrame(
                    {
                        "endotherm_positive_signal": oriented,
                        "baseline_signal": baseline,
                        "baseline_corrected_signal": corrected,
                        "processed_signal": processed,
                    }
                ),
            ],
            axis=1,
        )
        steps.extend(
            [
                PreprocessingStep(
                    "thermal-direction",
                    "endotherm_positive_orientation",
                    {"user_supplied_endotherm_direction": endotherm_direction},
                ),
                PreprocessingStep(
                    "thermal-baseline", f"{baseline_method}_baseline", {"method": baseline_method}
                ),
                PreprocessingStep(
                    "thermal-smoothing",
                    "savgol_smoothing" if smoothing_window else "no_smoothing",
                    {"requested_window_length": smoothing_window, "polyorder": smoothing_polyorder},
                ),
            ]
        )
        candidate_table = detect_dsc_candidates(
            temperature,
            processed,
            corrected,
            time_s=time_values,
            heating_rate_c_min=metadata.get("heating_rate_c_min"),
            signal_is_w_g=normalized_available,
            prominence_fraction=prominence_fraction,
            min_distance=min_distance,
        )
        plot_signal_unit = "Heat flow (W/g)" if normalized_available else "Heat flow (mW)"
    steps.append(
        PreprocessingStep(
            "thermal-candidates",
            "scipy_find_peaks_and_peak_widths",
            {
                "mode": mode,
                "prominence_fraction": prominence_fraction,
                "minimum_distance_samples": min_distance,
                "relative_height": 0.5,
                "candidate_scope": (
                    "positive_mass_loss_rate"
                    if mode == "tga"
                    else "endothermic_and_exothermic_on_endotherm_positive_signal"
                ),
            },
        )
    )
    measurement_id = measurement_id or f"{sample_id}-{mode}"
    preprocessing_id = preprocessing_fingerprint(mode, steps)
    features = build_thermal_feature_records(
        mode=mode,
        processed_table=processed_table,
        candidate_table=candidate_table,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=input_path,
        preprocessing_id=preprocessing_id,
    )
    processed_path = output_dir / "thermal_processed_data.csv"
    candidate_path = output_dir / "thermal_event_candidates.csv"
    feature_path = output_dir / "thermal_features_long.csv"
    plot_path = output_dir / "thermal_curve_with_candidates.png"
    processed_table.to_csv(processed_path, index=False)
    candidate_table.to_csv(candidate_path, index=False)
    records_to_frame(features).to_csv(feature_path, index=False)
    plot_thermal_data(
        mode=mode,
        processed_table=processed_table,
        candidate_table=candidate_table,
        output_path=plot_path,
        signal_unit=plot_signal_unit,
    )
    metadata.update(
        {"thermal_mode": mode, "signal_type": signal_type, "time_axis_present": time_values is not None}
    )
    warnings.extend(
        _thermal_warnings(
            mode=mode,
            processed_table=processed_table,
            candidate_table=candidate_table,
            metadata=metadata,
            time_s=time_values,
            endotherm_direction=endotherm_direction,
        )
    )
    result = build_analysis_result(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument=mode,
        source_file=input_path,
        acquisition_metadata=metadata,
        preprocessing_steps=steps,
        tables={
            "processed_data": processed_path,
            "event_candidates": candidate_path,
            "long_format_features": feature_path,
        },
        figures={"thermal_curve_with_candidates": plot_path},
        features=features,
        warnings=warnings,
        limitations=THERMAL_LIMITATIONS,
    )
    return {
        "mode": mode,
        "processed_data": processed_table,
        "candidate_table": candidate_table,
        "features": features,
        "analysis_result": result,
        "processed_data_path": processed_path,
        "candidate_table_path": candidate_path,
        "feature_path": feature_path,
        "plot_path": plot_path,
    }


def plot_thermal_data(
    *,
    mode: str,
    processed_table: pd.DataFrame,
    candidate_table: pd.DataFrame,
    output_path: str | Path,
    signal_unit: str,
) -> Path:
    """Save mode-specific thermal diagnostic plots."""
    output_path = Path(output_path)
    temperature = processed_table["temperature_c"]
    if mode == "tga":
        fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)
        axes[0].plot(
            temperature, processed_table["mass_retention_percent"], linewidth=1.0, label="mass retention"
        )
        axes[0].plot(
            temperature,
            processed_table["mass_retention_smoothed_percent"],
            linewidth=1.2,
            label="smoothed",
        )
        axes[0].set_ylabel(signal_unit)
        axes[0].set_title("TGA Mass-Retention Baseline")
        axes[0].legend()
        axes[0].grid(alpha=0.25)
        axes[1].plot(
            temperature,
            processed_table["mass_loss_rate_percent_per_c"],
            linewidth=1.2,
            label="positive mass-loss rate",
        )
        if not candidate_table.empty:
            axes[1].scatter(
                candidate_table["temperature_c"],
                candidate_table["mass_loss_rate_percent_per_c"],
                s=28,
                label="detected candidates",
                zorder=3,
            )
        axes[1].set_ylabel("Mass loss rate (%/degC)")
        axes[1].set_xlabel("Temperature (degC)")
        axes[1].set_title("Descriptive DTG-like Candidates")
        axes[1].legend()
        axes[1].grid(alpha=0.25)
    else:
        fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)
        axes[0].plot(
            temperature,
            processed_table["endotherm_positive_signal"],
            linewidth=1.0,
            label="endotherm-positive signal",
        )
        axes[0].plot(
            temperature, processed_table["baseline_signal"], linewidth=1.2, label="selected baseline"
        )
        axes[0].set_ylabel(signal_unit)
        axes[0].set_title("DSC Signal and Selected Baseline")
        axes[0].legend()
        axes[0].grid(alpha=0.25)
        axes[1].plot(
            temperature,
            processed_table["baseline_corrected_signal"],
            linewidth=1.0,
            label="baseline-corrected",
        )
        axes[1].plot(
            temperature, processed_table["processed_signal"], linewidth=1.2, label="processed"
        )
        if not candidate_table.empty:
            for candidate_type, marker in (("endothermic", "^"), ("exothermic", "v")):
                selected = candidate_table[candidate_table["candidate_type"] == candidate_type]
                if not selected.empty:
                    axes[1].scatter(
                        selected["temperature_c"],
                        selected["processed_signal"],
                        s=32,
                        marker=marker,
                        label=f"{candidate_type} candidates",
                        zorder=3,
                    )
        axes[1].set_ylabel(signal_unit)
        axes[1].set_xlabel("Temperature (degC)")
        axes[1].set_title("Descriptive DSC Candidates")
        axes[1].legend()
        axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def _thermal_warnings(
    *,
    mode: str,
    processed_table: pd.DataFrame,
    candidate_table: pd.DataFrame,
    metadata: dict[str, Any],
    time_s: np.ndarray | None,
    endotherm_direction: str,
) -> list[str]:
    warnings = [
        "thermal_candidates_require_manual_review",
        "thermal_candidates_are_not_reaction_or_phase_assignments",
    ]
    if not metadata.get("atmosphere"):
        warnings.append("thermal_atmosphere_not_provided")
    if metadata.get("heating_rate_c_min") is None:
        warnings.append("thermal_heating_rate_not_provided")
    if metadata.get("sample_mass_mg") is None:
        warnings.append("thermal_sample_mass_not_provided")
    if not metadata.get("crucible_material"):
        warnings.append("thermal_crucible_material_not_provided")
    if time_s is None:
        warnings.append("thermal_time_axis_not_provided")
    else:
        derived_rate = _median_heating_rate(processed_table["temperature_c"].to_numpy(dtype=float), time_s)
        metadata["derived_median_heating_rate_c_min"] = derived_rate
        supplied_rate = metadata.get("heating_rate_c_min")
        if supplied_rate is not None and derived_rate > 0:
            mismatch = abs(float(supplied_rate) - derived_rate) / derived_rate
            if mismatch > 0.10:
                warnings.append(
                    "thermal_supplied_heating_rate_differs_from_time_axis_by_more_than_10_percent"
                )
    if candidate_table.empty:
        warnings.append("thermal_no_event_candidates_detected")
    if mode == "tga":
        retention = processed_table["mass_retention_percent"].to_numpy(dtype=float)
        if np.nanmax(retention) - retention[0] > 2.0:
            warnings.append("tga_mass_gain_exceeds_2_percent")
        if retention[-1] > retention[0]:
            warnings.append("tga_final_mass_exceeds_initial_reference")
    else:
        warnings.append(f"dsc_endotherm_direction_user_supplied_{endotherm_direction}")
        normalized_available = processed_table["heat_flow_w_g"].notna().all()
        if not normalized_available:
            warnings.append("dsc_heat_flow_not_mass_normalized")
        if not normalized_available or (
            time_s is None and metadata.get("heating_rate_c_min") is None
        ):
            warnings.append(
                "dsc_enthalpy_not_calculated_without_normalized_heat_flow_and_time_or_heating_rate"
            )
    return warnings


def _validate_acquisition_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    values = dict(metadata or {})
    for name in ("heating_rate_c_min", "gas_flow_ml_min", "sample_mass_mg"):
        if values.get(name) is not None:
            values[name] = _validate_positive_optional(values[name], name)
    for name in (
        "atmosphere",
        "crucible_material",
        "instrument_model",
        "calibration_reference",
        "sample_preparation",
    ):
        if values.get(name) is not None:
            text = str(values[name]).strip()
            if not text:
                raise ValueError(f"{name} must not be empty when provided.")
            values[name] = text
    return values


def _validate_input_path(path: str | Path) -> Path:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Thermal file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"Thermal path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_THERMAL_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_THERMAL_EXTENSIONS))
        raise ValueError(
            f"Thermal file has unsupported extension '{input_path.suffix.lower()}'. "
            f"Supported extensions: {supported}."
        )
    return input_path


def _standardize_headerless(table: pd.DataFrame) -> pd.DataFrame:
    if table.shape[1] == 2:
        result = table.copy()
        result.columns = ["temperature_c", "signal"]
        return result
    if table.shape[1] == 3:
        result = table.copy()
        result.columns = ["temperature_c", "time_s", "signal"]
        return result
    raise ValueError("Headerless thermal files must contain two or three columns.")


def _normalize_columns(table: pd.DataFrame) -> pd.DataFrame:
    if table.shape[1] not in {2, 3}:
        raise ValueError("Thermal files must contain two or three columns.")
    aliases = {
        "temperature_c": {
            "temperature_c",
            "temperature",
            "temperature (c)",
            "temperature (degc)",
            "temp_c",
            "temp",
            "degc",
        },
        "time_s": {"time_s", "time", "time (s)", "seconds", "elapsed_time_s"},
    }
    lookup = {
        str(alias).strip().casefold(): standard
        for standard, values in aliases.items()
        for alias in values
    }
    matches: dict[str, list[object]] = {}
    for column in table.columns:
        standard = lookup.get(str(column).strip().casefold())
        if standard:
            matches.setdefault(standard, []).append(column)
    if any(len(values) > 1 for values in matches.values()):
        raise ValueError("Duplicate thermal column aliases were found.")
    if "temperature_c" not in matches:
        raise ValueError("Thermal headers must identify temperature in degC.")
    used = {values[0] for values in matches.values()}
    signal_columns = [column for column in table.columns if column not in used]
    if len(signal_columns) != 1:
        raise ValueError("Thermal data must contain exactly one non-temperature signal column.")
    rename = {matches["temperature_c"][0]: "temperature_c", signal_columns[0]: "signal"}
    if "time_s" in matches:
        rename[matches["time_s"][0]] = "time_s"
    ordered = [name for name in ("temperature_c", "time_s", "signal") if name in rename.values()]
    return table.rename(columns=rename).loc[:, ordered]


def _validate_dataframe(table: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if not {"temperature_c", "signal"}.issubset(table.columns):
        raise ValueError(f"{source_name} must contain temperature_c and signal.")
    columns = ["temperature_c"] + (["time_s"] if "time_s" in table.columns else []) + ["signal"]
    result = table.loc[:, columns].copy()
    for column in columns:
        numeric = pd.to_numeric(result[column], errors="coerce")
        invalid = numeric.isna() & result[column].notna() & (result[column].astype(str).str.strip() != "")
        if invalid.any():
            bad = result.loc[invalid, column].iloc[0]
            raise ValueError(f"{source_name} column '{column}' contains non-numeric value {bad!r}.")
        result[column] = numeric
    result = result.dropna(subset=columns)
    if len(result) < 7:
        raise ValueError(f"{source_name} must contain at least 7 valid rows.")
    if not np.isfinite(result[columns].to_numpy(dtype=float)).all():
        raise ValueError(f"{source_name} contains non-finite thermal values.")
    temperature = result["temperature_c"].to_numpy(dtype=float)
    if not np.all(np.diff(temperature) > 0):
        raise ValueError(
            f"{source_name} temperature must be strictly increasing. "
            "Cooling scans, holds, and multisegment programs require explicit segmentation and are outside this baseline."
        )
    if "time_s" in result.columns:
        time_values = result["time_s"].to_numpy(dtype=float)
        if not np.all(np.diff(time_values) > 0):
            raise ValueError(f"{source_name} time_s must be strictly increasing.")
    return result.reset_index(drop=True)


def _read_table(path: Path, separator: str, header: int | None, source_name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            sep=separator,
            header=header,
            engine="python",
            comment="#",
            skip_blank_lines=True,
        )
    except EmptyDataError as exc:
        raise ValueError(f"{source_name} is empty.") from exc


def _separators(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return [","]
    if path.suffix.lower() == ".tsv":
        return ["\t"]
    return [",", "\t", r"\s+"]


def _validate_temperature_array(values: pd.Series | np.ndarray) -> np.ndarray:
    temperature = np.asarray(values, dtype=float)
    if temperature.ndim != 1 or len(temperature) < 3:
        raise ValueError("At least 3 one-dimensional temperature values are required.")
    if not np.isfinite(temperature).all() or not np.all(np.diff(temperature) > 0):
        raise ValueError("Temperature must be finite and strictly increasing.")
    return temperature


def _validate_time_array(values: pd.Series | np.ndarray, *, expected_length: int) -> np.ndarray:
    time_s = np.asarray(values, dtype=float)
    if time_s.ndim != 1 or len(time_s) != expected_length:
        raise ValueError("time_s must be one-dimensional and match temperature length.")
    if not np.isfinite(time_s).all() or not np.all(np.diff(time_s) > 0):
        raise ValueError("time_s must be finite and strictly increasing.")
    return time_s


def _validate_signal_array(values: pd.Series | np.ndarray, *, name: str) -> np.ndarray:
    signal = np.asarray(values, dtype=float)
    if signal.ndim != 1 or len(signal) < 3:
        raise ValueError(f"At least 3 one-dimensional {name} values are required.")
    if not np.isfinite(signal).all():
        raise ValueError(f"{name} contains non-finite values.")
    return signal


def _validate_positive_optional(value: object, name: str) -> float:
    numeric = float(value)
    if not np.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be a finite positive value.")
    return numeric


def _validate_candidate_parameters(prominence_fraction: float, min_distance: int) -> None:
    if not np.isfinite(prominence_fraction) or prominence_fraction <= 0:
        raise ValueError("prominence_fraction must be a finite positive value.")
    if min_distance < 1:
        raise ValueError("min_distance must be at least one sample.")


def _valid_savgol_window(length: int, requested: int, polyorder: int) -> int | None:
    if length < 5:
        return None
    window = min(requested, length if length % 2 else length - 1)
    if window % 2 == 0:
        window -= 1
    if window <= polyorder:
        return None
    return window if window >= 3 else None


def _apply_edge_margin(
    peaks: np.ndarray,
    properties: dict[str, np.ndarray],
    length: int,
    edge_margin: int,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if edge_margin > 0 and len(peaks):
        valid = (peaks >= edge_margin) & (peaks <= length - 1 - edge_margin)
        return peaks[valid], {key: np.asarray(value)[valid] for key, value in properties.items()}
    return peaks, properties


def _integrate_within_bounds(x: np.ndarray, y: np.ndarray, lower: float, upper: float) -> float:
    mask = (x >= lower) & (x <= upper)
    selected_x = x[mask]
    selected_y = y[mask]
    boundary_x = np.array([lower, upper], dtype=float)
    boundary_y = np.interp(boundary_x, x, y)
    combined_x = np.concatenate((selected_x, boundary_x))
    combined_y = np.concatenate((selected_y, boundary_y))
    order = np.argsort(combined_x)
    unique_x, unique_indices = np.unique(combined_x[order], return_index=True)
    unique_y = combined_y[order][unique_indices]
    return float(trapezoid(unique_y, unique_x))


def _integrate_with_time_bounds(
    temperature: np.ndarray,
    time_s: np.ndarray,
    signal_w_g: np.ndarray,
    lower: float,
    upper: float,
) -> float:
    mask = (temperature >= lower) & (temperature <= upper)
    selected_temp = temperature[mask]
    selected_time = time_s[mask]
    selected_signal = signal_w_g[mask]
    boundary_temp = np.array([lower, upper], dtype=float)
    boundary_time = np.interp(boundary_temp, temperature, time_s)
    boundary_signal = np.interp(boundary_temp, temperature, signal_w_g)
    combined_temp = np.concatenate((selected_temp, boundary_temp))
    combined_time = np.concatenate((selected_time, boundary_time))
    combined_signal = np.concatenate((selected_signal, boundary_signal))
    order = np.argsort(combined_temp)
    sorted_time = combined_time[order]
    sorted_signal = combined_signal[order]
    unique_time, unique_indices = np.unique(sorted_time, return_index=True)
    unique_signal = sorted_signal[unique_indices]
    return float(trapezoid(unique_signal, unique_time))


def _median_heating_rate(temperature_c: np.ndarray, time_s: np.ndarray) -> float:
    local = np.diff(temperature_c) / np.diff(time_s) * 60.0
    finite_positive = local[np.isfinite(local) & (local > 0)]
    return float(np.median(finite_positive)) if len(finite_positive) else float("nan")


def _empty_tga_candidate_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "candidate_id",
            "candidate_type",
            "temperature_c",
            "mass_retention_percent",
            "mass_loss_rate_percent_per_c",
            "prominence_percent_per_c",
            "fwhm_c",
            "left_fwhm_c",
            "right_fwhm_c",
            "half_height_percent_per_c",
            "mass_change_within_fwhm_percent",
        ]
    )


def _empty_dsc_candidate_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "candidate_id",
            "candidate_type",
            "temperature_c",
            "processed_signal",
            "corrected_signal",
            "prominence",
            "fwhm_c",
            "left_fwhm_c",
            "right_fwhm_c",
            "half_height_directional_signal",
            "area_within_fwhm_signal_c",
            "enthalpy_within_fwhm_j_g",
            "direction_sign",
        ]
    )
