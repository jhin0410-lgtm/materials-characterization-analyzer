"""XPS spectrum baseline analysis with explicit energy referencing and provenance.

The workflow extracts descriptive candidates only. It does not assign elements,
chemical states, oxidation states, components, or quantitative composition.
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
from .utils import ensure_output_dir
from .xps_features import build_xps_feature_records

SUPPORTED_XPS_EXTENSIONS = {".csv", ".txt", ".tsv"}
XPS_COLUMNS = ("binding_energy_ev", "intensity")
XPS_LIMITATIONS = [
    "Automatically detected candidates do not identify elements, orbitals, compounds, chemical states, or oxidation states.",
    "Energy referencing is applied only from explicit user input and is not independently validated by the software.",
    "Shirley and linear backgrounds are descriptive preprocessing choices and are not peak-fit components.",
    "Candidate FWHM and within-FWHM area are descriptive outputs, not fitted line-shape or quantified component parameters.",
    "Charging, differential charging, satellites, multiplets, spin-orbit structure, overlap, transmission function, sensitivity factors, and instrument response require expert review.",
    "The workflow does not calculate atomic percentages or perform quantitative XPS composition.",
]


def load_xps_file(path: str | Path) -> pd.DataFrame:
    """Load a monotonic two-column XPS spectrum and standardize it to ascending energy."""
    input_path = _validate_input_path(path)
    source_name = f"XPS file '{input_path}'"

    for header in (0, None):
        for separator in _separators(input_path):
            try:
                table = _read_table(input_path, separator, header, source_name)
            except ParserError:
                continue
            if header is None:
                if table.shape[1] != 2:
                    continue
                table = table.copy()
                table.columns = list(XPS_COLUMNS)
            else:
                try:
                    table = _normalize_columns(table)
                except ValueError:
                    continue
            try:
                return _validate_dataframe(table, source_name)
            except ValueError:
                continue

    raise ValueError(
        f"{source_name} could not be interpreted as supported two-column XPS data. "
        "Expected binding energy in eV and intensity."
    )


def resolve_energy_reference(
    *,
    energy_shift_ev: float | None = None,
    reference_observed_ev: float | None = None,
    reference_target_ev: float | None = None,
) -> tuple[float, str, dict[str, float]]:
    """Resolve one explicit energy-reference route without inferring a reference."""
    pair_supplied = reference_observed_ev is not None or reference_target_ev is not None
    if energy_shift_ev is not None and pair_supplied:
        raise ValueError("Use either energy_shift_ev or an observed/target reference pair, not both.")
    if pair_supplied and (reference_observed_ev is None or reference_target_ev is None):
        raise ValueError("reference_observed_ev and reference_target_ev must be provided together.")

    if energy_shift_ev is not None:
        shift = float(energy_shift_ev)
        if not np.isfinite(shift):
            raise ValueError("energy_shift_ev must be finite.")
        return shift, "explicit_energy_shift", {"energy_shift_ev": shift}

    if reference_observed_ev is not None and reference_target_ev is not None:
        observed = float(reference_observed_ev)
        target = float(reference_target_ev)
        if not np.isfinite(observed) or not np.isfinite(target):
            raise ValueError("Reference energies must be finite.")
        shift = target - observed
        return shift, "observed_to_target_reference", {
            "reference_observed_ev": observed,
            "reference_target_ev": target,
            "energy_shift_ev": shift,
        }

    return 0.0, "no_energy_reference", {"energy_shift_ev": 0.0}


def linear_background(intensity: pd.Series | np.ndarray) -> np.ndarray:
    """Return a line between the first and final intensity values."""
    values = _validate_intensity_array(intensity)
    return np.linspace(values[0], values[-1], len(values), dtype=float)


def shirley_background(
    binding_energy_ev: pd.Series | np.ndarray,
    intensity: pd.Series | np.ndarray,
    *,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> tuple[np.ndarray, bool, int]:
    """Estimate an iterative Shirley background on an ascending energy axis."""
    energy = np.asarray(binding_energy_ev, dtype=float)
    values = _validate_intensity_array(intensity)
    if len(energy) != len(values):
        raise ValueError("Binding energy and intensity must have the same length.")
    if len(energy) < 3 or not np.isfinite(energy).all() or not np.all(np.diff(energy) > 0):
        raise ValueError("Shirley background requires at least 3 finite, strictly ascending energies.")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least one.")
    if tolerance <= 0 or not np.isfinite(tolerance):
        raise ValueError("tolerance must be a finite positive value.")

    background = linear_background(values)
    intensity_scale = max(float(np.ptp(values)), 1.0)
    converged = False
    used_iterations = 0

    for used_iterations in range(1, int(max_iterations) + 1):
        residual = np.clip(values - background, 0.0, None)
        segments = 0.5 * (residual[:-1] + residual[1:]) * np.diff(energy)
        cumulative_from_right = np.concatenate(
            (np.cumsum(segments[::-1])[::-1], np.array([0.0], dtype=float))
        )
        total = float(cumulative_from_right[0])
        if not np.isfinite(total) or total <= np.finfo(float).eps:
            return linear_background(values), False, used_iterations
        updated = values[-1] + (values[0] - values[-1]) * (cumulative_from_right / total)
        delta = float(np.max(np.abs(updated - background)))
        background = updated
        if delta <= tolerance * intensity_scale:
            converged = True
            break

    return background, converged, used_iterations


def calculate_xps_background(
    binding_energy_ev: pd.Series | np.ndarray,
    intensity: pd.Series | np.ndarray,
    *,
    method: str,
    shirley_iterations: int = 100,
    shirley_tolerance: float = 1e-6,
) -> tuple[np.ndarray, bool | None, int | None]:
    """Calculate the requested background and return convergence metadata."""
    values = _validate_intensity_array(intensity)
    if method == "none":
        return np.zeros_like(values), None, None
    if method == "linear":
        return linear_background(values), None, None
    if method == "shirley":
        return shirley_background(
            binding_energy_ev,
            values,
            max_iterations=shirley_iterations,
            tolerance=shirley_tolerance,
        )
    raise ValueError("background_method must be 'none', 'linear', or 'shirley'.")


def smooth_xps_intensity(
    intensity: pd.Series | np.ndarray,
    *,
    window_length: int = 0,
    polyorder: int = 3,
) -> np.ndarray:
    """Apply optional Savitzky-Golay smoothing; zero window disables smoothing."""
    values = _validate_intensity_array(intensity)
    if window_length == 0:
        return values.copy()
    if window_length < 0 or polyorder < 0:
        raise ValueError("smoothing parameters must be non-negative.")
    window = _valid_savgol_window(len(values), int(window_length), int(polyorder))
    return values.copy() if window is None else savgol_filter(values, window, polyorder)


def detect_xps_candidates(
    corrected_binding_energy_ev: pd.Series | np.ndarray,
    raw_intensity: pd.Series | np.ndarray,
    background: pd.Series | np.ndarray,
    processed_intensity: pd.Series | np.ndarray,
    *,
    energy_shift_ev: float = 0.0,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    edge_margin: int = 2,
) -> pd.DataFrame:
    """Detect descriptive XPS candidates and calculate FWHM and within-FWHM area."""
    energy = np.asarray(corrected_binding_energy_ev, dtype=float)
    raw = np.asarray(raw_intensity, dtype=float)
    base = np.asarray(background, dtype=float)
    processed = np.asarray(processed_intensity, dtype=float)
    if not (len(energy) == len(raw) == len(base) == len(processed)):
        raise ValueError("XPS arrays must have the same length.")
    if not np.all(np.diff(energy) > 0):
        raise ValueError("Candidate detection requires strictly ascending binding energy.")
    if prominence_fraction <= 0 or not np.isfinite(prominence_fraction):
        raise ValueError("prominence_fraction must be a finite positive value.")
    if min_distance < 1:
        raise ValueError("min_distance must be at least one sample.")

    corrected = raw - base
    dynamic_range = float(np.ptp(processed))
    if len(energy) < 3 or not np.isfinite(dynamic_range) or dynamic_range <= 0:
        return _empty_candidate_table()

    peaks, properties = find_peaks(
        processed,
        prominence=max(dynamic_range * prominence_fraction, np.finfo(float).eps),
        distance=int(min_distance),
    )
    if edge_margin > 0 and len(peaks):
        valid = (peaks >= edge_margin) & (peaks <= len(energy) - 1 - edge_margin)
        peaks = peaks[valid]
        properties = {key: np.asarray(value)[valid] for key, value in properties.items()}
    if len(peaks) == 0:
        return _empty_candidate_table()

    _, half_height, left_ips, right_ips = peak_widths(processed, peaks, rel_height=0.5)
    sample_index = np.arange(len(energy), dtype=float)
    left = np.interp(left_ips, sample_index, energy)
    right = np.interp(right_ips, sample_index, energy)

    table = pd.DataFrame(
        {
            "candidate_id": np.arange(1, len(peaks) + 1),
            "binding_energy_raw_ev": energy[peaks] - float(energy_shift_ev),
            "binding_energy_corrected_ev": energy[peaks],
            "raw_intensity": raw[peaks],
            "background_intensity": base[peaks],
            "background_corrected_intensity": corrected[peaks],
            "processed_intensity": processed[peaks],
            "prominence": properties["prominences"],
            "fwhm_ev": right - left,
            "left_fwhm_ev": left,
            "right_fwhm_ev": right,
            "half_height_processed_intensity": half_height,
            "area_within_fwhm_intensity_ev": [
                _integrate_within_bounds(energy, corrected, lower, upper)
                for lower, upper in zip(left, right)
            ],
        }
    )
    return table.sort_values("binding_energy_corrected_ev").reset_index(drop=True)


def analyze_xps(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    background_method: str = "shirley",
    shirley_iterations: int = 100,
    shirley_tolerance: float = 1e-6,
    smoothing_window: int = 0,
    smoothing_polyorder: int = 3,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    energy_shift_ev: float | None = None,
    reference_observed_ev: float | None = None,
    reference_target_ev: float | None = None,
    acquisition_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Run XPS referencing, background, candidate extraction, and provenance export."""
    if not sample_id.strip():
        raise ValueError("sample_id must not be empty.")
    metadata = _validate_acquisition_metadata(acquisition_metadata)
    shift, reference_method, reference_parameters = resolve_energy_reference(
        energy_shift_ev=energy_shift_ev,
        reference_observed_ev=reference_observed_ev,
        reference_target_ev=reference_target_ev,
    )

    output_dir = ensure_output_dir(output_dir)
    spectrum = load_xps_file(input_path)
    input_axis_direction = str(spectrum.attrs.get("input_axis_direction", "unknown"))
    raw_energy = spectrum["binding_energy_ev"].to_numpy(dtype=float)
    corrected_energy = raw_energy + shift
    raw_intensity = spectrum["intensity"].to_numpy(dtype=float)
    steps = [
        PreprocessingStep(
            "xps-import",
            "two_column_xps_validation",
            {
                "input_axis_direction": input_axis_direction,
                "stored_axis_direction": "ascending",
            },
        ),
        PreprocessingStep("xps-energy-reference", reference_method, reference_parameters),
    ]

    background, background_converged, background_iterations_used = calculate_xps_background(
        corrected_energy,
        raw_intensity,
        method=background_method,
        shirley_iterations=shirley_iterations,
        shirley_tolerance=shirley_tolerance,
    )
    background_parameters: dict[str, Any] = {"method": background_method}
    if background_method == "shirley":
        background_parameters.update(
            {
                "maximum_iterations": shirley_iterations,
                "tolerance": shirley_tolerance,
                "converged": bool(background_converged),
                "iterations_used": int(background_iterations_used or 0),
                "negative_residual_handling": "clipped_to_zero_during_iteration",
            }
        )
    steps.append(PreprocessingStep("xps-background", f"{background_method}_background", background_parameters))

    corrected_intensity = raw_intensity - background
    processed_intensity = smooth_xps_intensity(
        corrected_intensity,
        window_length=smoothing_window,
        polyorder=smoothing_polyorder,
    )
    steps.append(
        PreprocessingStep(
            "xps-smoothing",
            "savgol_smoothing" if smoothing_window else "no_smoothing",
            {
                "requested_window_length": smoothing_window,
                "polyorder": smoothing_polyorder,
                "application": "conditional_on_data_length",
            },
        )
    )

    candidate_table = detect_xps_candidates(
        corrected_energy,
        raw_intensity,
        background,
        processed_intensity,
        energy_shift_ev=shift,
        prominence_fraction=prominence_fraction,
        min_distance=min_distance,
    )
    steps.append(
        PreprocessingStep(
            "xps-candidates",
            "scipy_find_peaks_and_peak_widths",
            {
                "prominence_fraction": prominence_fraction,
                "minimum_distance_samples": min_distance,
                "relative_height": 0.5,
                "area_definition": "nonnegative_background_corrected_signal_within_fwhm",
            },
        )
    )

    measurement_id = measurement_id or f"{sample_id}-xps"
    preprocessing_id = preprocessing_fingerprint("xps", steps)
    features = build_xps_feature_records(
        candidate_table,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=input_path,
        preprocessing_id=preprocessing_id,
    )
    processed_table = pd.DataFrame(
        {
            "binding_energy_raw_ev": raw_energy,
            "binding_energy_corrected_ev": corrected_energy,
            "raw_intensity": raw_intensity,
            "background_intensity": background,
            "background_corrected_intensity": corrected_intensity,
            "processed_intensity": processed_intensity,
        }
    )

    processed_path = output_dir / "xps_processed_spectrum.csv"
    candidate_path = output_dir / "xps_peak_candidates.csv"
    feature_path = output_dir / "xps_features_long.csv"
    plot_path = output_dir / "xps_spectrum_with_candidates.png"
    processed_table.to_csv(processed_path, index=False)
    candidate_table.to_csv(candidate_path, index=False)
    records_to_frame(features).to_csv(feature_path, index=False)
    plot_xps_spectrum(processed_table, candidate_table, plot_path)

    metadata.update(
        {
            "energy_reference_method": reference_method,
            "energy_shift_ev": shift,
            "input_axis_direction": input_axis_direction,
        }
    )
    warnings = _xps_warnings(
        spectrum,
        raw_intensity,
        metadata,
        reference_method=reference_method,
        shift=shift,
        background_method=background_method,
        background_converged=background_converged,
    )
    result = build_analysis_result(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument="xps",
        source_file=input_path,
        acquisition_metadata=metadata,
        preprocessing_steps=steps,
        tables={
            "processed_spectrum": processed_path,
            "peak_candidates": candidate_path,
            "long_format_features": feature_path,
        },
        figures={"spectrum_with_candidates": plot_path},
        features=features,
        warnings=warnings,
        limitations=XPS_LIMITATIONS,
    )
    return {
        "spectrum": spectrum,
        "processed_spectrum": processed_table,
        "candidate_table": candidate_table,
        "features": features,
        "analysis_result": result,
        "processed_spectrum_path": processed_path,
        "candidate_table_path": candidate_path,
        "feature_path": feature_path,
        "plot_path": plot_path,
    }


def plot_xps_spectrum(
    processed_table: pd.DataFrame,
    candidate_table: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Save raw/background and corrected/processed XPS diagnostic plots."""
    output_path = Path(output_path)
    energy = processed_table["binding_energy_corrected_ev"]
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)

    axes[0].plot(energy, processed_table["raw_intensity"], linewidth=1.0, label="raw")
    axes[0].plot(energy, processed_table["background_intensity"], linewidth=1.2, label="background")
    axes[0].set_ylabel("Intensity")
    axes[0].set_title("XPS Raw Spectrum and Selected Background")
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(
        energy,
        processed_table["background_corrected_intensity"],
        linewidth=1.0,
        label="background-corrected",
    )
    axes[1].plot(energy, processed_table["processed_intensity"], linewidth=1.2, label="processed")
    if not candidate_table.empty:
        axes[1].scatter(
            candidate_table["binding_energy_corrected_ev"],
            candidate_table["processed_intensity"],
            s=28,
            label="detected candidates",
            zorder=3,
        )
    axes[1].set_xlabel("Binding energy (eV)")
    axes[1].set_ylabel("Corrected intensity")
    axes[1].set_title("Processed XPS Spectrum")
    axes[1].legend()
    axes[1].grid(alpha=0.25)
    axes[1].invert_xaxis()

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def _validate_input_path(path: str | Path) -> Path:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"XPS file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"XPS path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_XPS_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_XPS_EXTENSIONS))
        raise ValueError(
            f"XPS file has unsupported extension '{input_path.suffix.lower()}'. "
            f"Supported extensions: {supported}."
        )
    return input_path


def _normalize_columns(table: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "binding_energy_ev": {
            "binding_energy_ev",
            "binding energy",
            "binding energy (ev)",
            "binding_energy",
            "be",
            "be_ev",
            "energy_ev",
        },
        "intensity": {
            "intensity",
            "counts",
            "count",
            "cps",
            "counts_per_second",
            "signal",
        },
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
        raise ValueError("Duplicate XPS column aliases were found.")
    if any(name not in matches for name in XPS_COLUMNS):
        raise ValueError("XPS headers must identify binding energy in eV and intensity.")
    return table.rename(columns={values[0]: name for name, values in matches.items()})


def _validate_dataframe(table: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if table.shape[1] != 2:
        raise ValueError(f"{source_name} must contain exactly two columns.")
    spectrum = table.loc[:, XPS_COLUMNS].copy()
    for column in XPS_COLUMNS:
        numeric = pd.to_numeric(spectrum[column], errors="coerce")
        invalid = numeric.isna() & spectrum[column].notna() & (spectrum[column].astype(str).str.strip() != "")
        if invalid.any():
            bad = spectrum.loc[invalid, column].iloc[0]
            raise ValueError(f"{source_name} column '{column}' contains non-numeric value {bad!r}.")
        spectrum[column] = numeric
    spectrum = spectrum.dropna(subset=list(XPS_COLUMNS))
    if not np.isfinite(spectrum[list(XPS_COLUMNS)].to_numpy(dtype=float)).all():
        raise ValueError(f"{source_name} contains non-finite XPS values.")
    if spectrum["binding_energy_ev"].duplicated().any():
        duplicate = spectrum.loc[spectrum["binding_energy_ev"].duplicated(), "binding_energy_ev"].iloc[0]
        raise ValueError(f"{source_name} contains duplicate binding energy value {duplicate}.")
    if len(spectrum) < 7:
        raise ValueError(f"{source_name} must contain at least 7 valid XPS rows.")

    differences = np.diff(spectrum["binding_energy_ev"].to_numpy(dtype=float))
    if np.all(differences > 0):
        direction = "ascending"
    elif np.all(differences < 0):
        direction = "descending"
        spectrum = spectrum.iloc[::-1].reset_index(drop=True)
    else:
        raise ValueError(f"{source_name} binding energy must be strictly monotonic.")
    spectrum.attrs["input_axis_direction"] = direction
    return spectrum.reset_index(drop=True)


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


def _validate_intensity_array(intensity: pd.Series | np.ndarray) -> np.ndarray:
    values = np.asarray(intensity, dtype=float)
    if values.ndim != 1 or len(values) < 3:
        raise ValueError("At least 3 one-dimensional intensity values are required.")
    if not np.isfinite(values).all():
        raise ValueError("XPS intensity contains non-finite values.")
    return values


def _valid_savgol_window(length: int, requested: int, polyorder: int) -> int | None:
    if length < 5:
        return None
    window = min(requested, length if length % 2 else length - 1)
    if window % 2 == 0:
        window -= 1
    if window <= polyorder:
        window = polyorder + 2
        if window % 2 == 0:
            window += 1
    return window if 5 <= window <= length else None


def _integrate_within_bounds(
    x: np.ndarray,
    y: np.ndarray,
    left: float,
    right: float,
) -> float:
    mask = (x > left) & (x < right)
    segment_x = np.concatenate(([left], x[mask], [right]))
    segment_y = np.clip(np.interp(segment_x, x, y), 0.0, None)
    return float(trapezoid(segment_y, segment_x))


def _empty_candidate_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "candidate_id",
            "binding_energy_raw_ev",
            "binding_energy_corrected_ev",
            "raw_intensity",
            "background_intensity",
            "background_corrected_intensity",
            "processed_intensity",
            "prominence",
            "fwhm_ev",
            "left_fwhm_ev",
            "right_fwhm_ev",
            "half_height_processed_intensity",
            "area_within_fwhm_intensity_ev",
        ]
    )


def _validate_acquisition_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    values = dict(metadata or {})
    spectrum_type = values.get("spectrum_type", "unknown")
    if spectrum_type not in {"survey", "high_resolution", "unknown"}:
        raise ValueError("spectrum_type must be 'survey', 'high_resolution', or 'unknown'.")
    values["spectrum_type"] = spectrum_type

    charge_neutralization = values.get("charge_neutralization", "unknown")
    if charge_neutralization not in {"on", "off", "unknown"}:
        raise ValueError("charge_neutralization must be 'on', 'off', or 'unknown'.")
    values["charge_neutralization"] = charge_neutralization

    positive_fields = (
        "photon_energy_ev",
        "pass_energy_ev",
        "step_size_ev",
        "dwell_time_s",
    )
    for field in positive_fields:
        value = values.get(field)
        if value is not None:
            numeric = float(value)
            if not np.isfinite(numeric) or numeric <= 0:
                raise ValueError(f"{field} must be a finite positive value when provided.")
            values[field] = numeric

    scan_count = values.get("scan_count")
    if scan_count is not None:
        if int(scan_count) != scan_count or int(scan_count) < 1:
            raise ValueError("scan_count must be a positive integer when provided.")
        values["scan_count"] = int(scan_count)

    takeoff = values.get("takeoff_angle_deg")
    if takeoff is not None:
        takeoff = float(takeoff)
        if not np.isfinite(takeoff) or not 0 < takeoff <= 90:
            raise ValueError("takeoff_angle_deg must be greater than 0 and at most 90.")
        values["takeoff_angle_deg"] = takeoff

    for field in ("xray_source", "region_label"):
        value = values.get(field)
        if value is not None and not str(value).strip():
            raise ValueError(f"{field} must not be empty when provided.")
    return values


def _xps_warnings(
    spectrum: pd.DataFrame,
    raw_intensity: np.ndarray,
    metadata: dict[str, Any],
    *,
    reference_method: str,
    shift: float,
    background_method: str,
    background_converged: bool | None,
) -> list[str]:
    warnings = ["automatic_xps_candidates_require_manual_review"]
    if spectrum.attrs.get("input_axis_direction") == "descending":
        warnings.append("binding_energy_axis_reordered_to_ascending_for_processing")
    if reference_method == "no_energy_reference":
        warnings.append("energy_reference_not_provided")
    if abs(float(shift)) > 10:
        warnings.append("large_energy_shift_requires_review")
    if background_method == "shirley" and background_converged is False:
        warnings.append("shirley_background_not_converged")

    recommended = {
        "xray_source": "xray_source_not_provided",
        "photon_energy_ev": "photon_energy_not_provided",
        "pass_energy_ev": "pass_energy_not_provided",
        "step_size_ev": "step_size_not_provided",
    }
    warnings.extend(message for field, message in recommended.items() if metadata.get(field) is None)
    if metadata.get("spectrum_type") == "unknown":
        warnings.append("spectrum_type_unknown")
    if metadata.get("charge_neutralization") == "unknown":
        warnings.append("charge_neutralization_unknown")

    spacing = np.diff(spectrum["binding_energy_ev"].to_numpy(dtype=float))
    if len(spacing) and not np.allclose(spacing, np.median(spacing), rtol=1e-3, atol=1e-9):
        warnings.append("nonuniform_binding_energy_spacing")
    if np.any(raw_intensity < 0):
        warnings.append("negative_raw_intensity_present")

    reported_step = metadata.get("step_size_ev")
    if reported_step is not None and len(spacing):
        median_step = float(np.median(spacing))
        if not np.isclose(float(reported_step), median_step, rtol=0.05, atol=1e-9):
            warnings.append("reported_step_size_differs_from_axis")
    return warnings
