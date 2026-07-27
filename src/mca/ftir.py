"""FTIR spectrum baseline analysis with explicit signal semantics and provenance.

The workflow extracts descriptive band candidates only. It does not assign
functional groups, compounds, phases, bonding mechanisms, or quantitative composition.
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
from scipy import sparse
from scipy.integrate import trapezoid
from scipy.signal import find_peaks, peak_widths, savgol_filter
from scipy.sparse.linalg import spsolve

from .contracts import PreprocessingStep
from .feature_records import records_to_frame
from .ftir_features import build_ftir_feature_records
from .provenance import build_analysis_result, preprocessing_fingerprint
from .utils import ensure_output_dir

SUPPORTED_FTIR_EXTENSIONS = {".csv", ".txt", ".tsv"}
FTIR_COLUMNS = ("wavenumber_cm_1", "signal")
SIGNAL_TYPES = {"absorbance", "transmittance_percent", "transmittance_fraction"}
FTIR_LIMITATIONS = [
    "Automatically detected candidates do not identify functional groups, compounds, phases, or bonding mechanisms.",
    "Transmittance-to-absorbance conversion is mathematical and does not correct reference, scattering, saturation, path-length, or sampling-mode artifacts.",
    "Linear and asymmetric least-squares baselines are preprocessing choices and are not physical component models.",
    "Candidate FWHM and within-FWHM area are descriptive outputs, not fitted or deconvoluted band parameters.",
    "ATR, transmission, diffuse-reflectance, and specular-reflectance spectra are not directly interchangeable without suitable corrections and metadata.",
    "Water vapor, carbon dioxide, detector response, apodization, resolution, purge, sample thickness, contact, and preparation require expert review.",
    "The workflow does not perform atmospheric correction, ATR correction, normalization, derivative spectroscopy, spectral subtraction, library matching, or quantitative concentration analysis.",
]


def load_ftir_file(path: str | Path) -> pd.DataFrame:
    """Load a monotonic two-column FTIR spectrum and standardize to ascending wavenumber."""
    input_path = _validate_input_path(path)
    source_name = f"FTIR file '{input_path}'"

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
                table.columns = list(FTIR_COLUMNS)
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
        f"{source_name} could not be interpreted as supported two-column FTIR data. "
        "Expected wavenumber in cm^-1 and one signal column."
    )


def convert_ftir_signal_to_absorbance(
    signal: pd.Series | np.ndarray,
    *,
    signal_type: str,
) -> tuple[np.ndarray, str]:
    """Convert an explicitly declared FTIR signal to absorbance without clipping."""
    if signal_type not in SIGNAL_TYPES:
        allowed = ", ".join(sorted(SIGNAL_TYPES))
        raise ValueError(f"signal_type must be one of: {allowed}.")
    values = _validate_signal_array(signal)

    if signal_type == "absorbance":
        return values.copy(), "identity_absorbance"

    if np.any(values <= 0):
        raise ValueError("Transmittance values must be greater than zero for logarithmic conversion.")
    if signal_type == "transmittance_percent":
        fraction = values / 100.0
        method = "negative_log10_transmittance_percent_over_100"
    else:
        fraction = values
        method = "negative_log10_transmittance_fraction"

    absorbance = -np.log10(fraction)
    if not np.isfinite(absorbance).all():
        raise ValueError("FTIR transmittance conversion produced non-finite absorbance.")
    return absorbance, method


def linear_ftir_baseline(absorbance: pd.Series | np.ndarray) -> np.ndarray:
    """Return a line between first and final absorbance values."""
    values = _validate_signal_array(absorbance)
    return np.linspace(values[0], values[-1], len(values), dtype=float)


def asymmetric_least_squares_ftir_baseline(
    absorbance: pd.Series | np.ndarray,
    *,
    smoothness: float = 1_000_000.0,
    asymmetry: float = 0.01,
    iterations: int = 15,
) -> np.ndarray:
    """Estimate an asymmetric least-squares baseline on absorbance."""
    values = _validate_signal_array(absorbance)
    if smoothness <= 0 or not np.isfinite(smoothness):
        raise ValueError("baseline smoothness must be a finite positive value.")
    if not 0 < asymmetry < 1:
        raise ValueError("baseline asymmetry must be between zero and one.")
    if iterations < 1:
        raise ValueError("baseline iterations must be at least one.")

    length = len(values)
    difference = sparse.diags(
        (np.ones(length - 2), -2.0 * np.ones(length - 2), np.ones(length - 2)),
        (0, 1, 2),
        shape=(length - 2, length),
        format="csc",
    )
    penalty = float(smoothness) * (difference.T @ difference)
    weights = np.ones(length, dtype=float)
    baseline = values.copy()

    for _ in range(int(iterations)):
        weight_matrix = sparse.spdiags(weights, 0, length, length)
        baseline = np.asarray(spsolve(weight_matrix + penalty, weights * values), dtype=float)
        weights = np.where(values > baseline, asymmetry, 1.0 - asymmetry)
    return baseline


def calculate_ftir_baseline(
    absorbance: pd.Series | np.ndarray,
    *,
    method: str,
    smoothness: float = 1_000_000.0,
    asymmetry: float = 0.01,
    iterations: int = 15,
) -> np.ndarray:
    """Calculate the requested FTIR absorbance baseline."""
    values = _validate_signal_array(absorbance)
    if method == "none":
        return np.zeros_like(values)
    if method == "linear":
        return linear_ftir_baseline(values)
    if method == "asls":
        return asymmetric_least_squares_ftir_baseline(
            values,
            smoothness=smoothness,
            asymmetry=asymmetry,
            iterations=iterations,
        )
    raise ValueError("baseline_method must be 'none', 'linear', or 'asls'.")


def smooth_ftir_absorbance(
    absorbance: pd.Series | np.ndarray,
    *,
    window_length: int = 0,
    polyorder: int = 3,
) -> np.ndarray:
    """Apply optional Savitzky-Golay smoothing; zero window disables smoothing."""
    values = _validate_signal_array(absorbance)
    if window_length == 0:
        return values.copy()
    if window_length < 0 or polyorder < 0:
        raise ValueError("smoothing parameters must be non-negative.")
    window = _valid_savgol_window(len(values), int(window_length), int(polyorder))
    return values.copy() if window is None else savgol_filter(values, window, polyorder)


def detect_ftir_band_candidates(
    wavenumber_cm_1: pd.Series | np.ndarray,
    raw_signal: pd.Series | np.ndarray,
    absorbance: pd.Series | np.ndarray,
    baseline: pd.Series | np.ndarray,
    processed_absorbance: pd.Series | np.ndarray,
    *,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    edge_margin: int = 2,
) -> pd.DataFrame:
    """Detect descriptive absorbance candidates with FWHM and within-FWHM area."""
    wavenumber = np.asarray(wavenumber_cm_1, dtype=float)
    raw = np.asarray(raw_signal, dtype=float)
    converted = np.asarray(absorbance, dtype=float)
    base = np.asarray(baseline, dtype=float)
    processed = np.asarray(processed_absorbance, dtype=float)
    if not (len(wavenumber) == len(raw) == len(converted) == len(base) == len(processed)):
        raise ValueError("FTIR arrays must have the same length.")
    if not np.all(np.diff(wavenumber) > 0):
        raise ValueError("Candidate detection requires strictly ascending wavenumber.")
    if prominence_fraction <= 0 or not np.isfinite(prominence_fraction):
        raise ValueError("prominence_fraction must be a finite positive value.")
    if min_distance < 1:
        raise ValueError("min_distance must be at least one sample.")

    corrected = converted - base
    dynamic_range = float(np.ptp(processed))
    if len(wavenumber) < 3 or not np.isfinite(dynamic_range) or dynamic_range <= 0:
        return _empty_candidate_table()

    peaks, properties = find_peaks(
        processed,
        prominence=max(dynamic_range * prominence_fraction, np.finfo(float).eps),
        distance=int(min_distance),
    )
    if edge_margin > 0 and len(peaks):
        valid = (peaks >= edge_margin) & (peaks <= len(wavenumber) - 1 - edge_margin)
        peaks = peaks[valid]
        properties = {key: np.asarray(value)[valid] for key, value in properties.items()}
    if len(peaks) == 0:
        return _empty_candidate_table()

    _, half_height, left_ips, right_ips = peak_widths(processed, peaks, rel_height=0.5)
    sample_index = np.arange(len(wavenumber), dtype=float)
    left = np.interp(left_ips, sample_index, wavenumber)
    right = np.interp(right_ips, sample_index, wavenumber)

    table = pd.DataFrame(
        {
            "candidate_id": np.arange(1, len(peaks) + 1),
            "wavenumber_cm_1": wavenumber[peaks],
            "raw_signal": raw[peaks],
            "converted_absorbance": converted[peaks],
            "baseline_absorbance": base[peaks],
            "baseline_corrected_absorbance": corrected[peaks],
            "processed_absorbance": processed[peaks],
            "prominence_absorbance": properties["prominences"],
            "fwhm_cm_1": right - left,
            "left_fwhm_cm_1": left,
            "right_fwhm_cm_1": right,
            "half_height_processed_absorbance": half_height,
            "area_within_fwhm_absorbance_cm_1": [
                _integrate_within_bounds(wavenumber, corrected, lower, upper)
                for lower, upper in zip(left, right)
            ],
        }
    )
    return table.sort_values("wavenumber_cm_1", ascending=False).reset_index(drop=True)


def analyze_ftir(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    sample_id: str,
    signal_type: str,
    measurement_id: str | None = None,
    baseline_method: str = "none",
    baseline_smoothness: float = 1_000_000.0,
    baseline_asymmetry: float = 0.01,
    baseline_iterations: int = 15,
    smoothing_window: int = 0,
    smoothing_polyorder: int = 3,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    acquisition_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Run FTIR conversion, baseline processing, candidate extraction, and provenance."""
    if not sample_id.strip():
        raise ValueError("sample_id must not be empty.")
    if signal_type not in SIGNAL_TYPES:
        allowed = ", ".join(sorted(SIGNAL_TYPES))
        raise ValueError(f"signal_type must be one of: {allowed}.")
    metadata = _validate_acquisition_metadata(acquisition_metadata)

    output_dir = ensure_output_dir(output_dir)
    spectrum = load_ftir_file(input_path)
    input_axis_direction = str(spectrum.attrs.get("input_axis_direction", "unknown"))
    wavenumber = spectrum["wavenumber_cm_1"].to_numpy(dtype=float)
    raw_signal = spectrum["signal"].to_numpy(dtype=float)
    absorbance, conversion_method = convert_ftir_signal_to_absorbance(
        raw_signal,
        signal_type=signal_type,
    )
    steps = [
        PreprocessingStep(
            "ftir-import",
            "two_column_ftir_validation",
            {
                "input_axis_direction": input_axis_direction,
                "stored_axis_direction": "ascending",
                "signal_type": signal_type,
            },
        ),
        PreprocessingStep(
            "ftir-signal-conversion",
            conversion_method,
            {
                "input_signal_type": signal_type,
                "output_signal_type": "absorbance",
                "clipping_applied": False,
            },
        ),
    ]

    baseline = calculate_ftir_baseline(
        absorbance,
        method=baseline_method,
        smoothness=baseline_smoothness,
        asymmetry=baseline_asymmetry,
        iterations=baseline_iterations,
    )
    baseline_parameters: dict[str, Any] = {"method": baseline_method}
    if baseline_method == "asls":
        baseline_parameters.update(
            {
                "smoothness": baseline_smoothness,
                "asymmetry": baseline_asymmetry,
                "iterations": baseline_iterations,
            }
        )
    steps.append(
        PreprocessingStep(
            "ftir-baseline",
            f"{baseline_method}_baseline",
            baseline_parameters,
        )
    )

    corrected_absorbance = absorbance - baseline
    processed_absorbance = smooth_ftir_absorbance(
        corrected_absorbance,
        window_length=smoothing_window,
        polyorder=smoothing_polyorder,
    )
    steps.append(
        PreprocessingStep(
            "ftir-smoothing",
            "savgol_smoothing" if smoothing_window else "no_smoothing",
            {
                "requested_window_length": smoothing_window,
                "polyorder": smoothing_polyorder,
                "application": "conditional_on_data_length",
            },
        )
    )

    candidate_table = detect_ftir_band_candidates(
        wavenumber,
        raw_signal,
        absorbance,
        baseline,
        processed_absorbance,
        prominence_fraction=prominence_fraction,
        min_distance=min_distance,
    )
    steps.append(
        PreprocessingStep(
            "ftir-candidates",
            "scipy_find_peaks_and_peak_widths",
            {
                "prominence_fraction": prominence_fraction,
                "minimum_distance_samples": min_distance,
                "relative_height": 0.5,
                "area_definition": "nonnegative_baseline_corrected_absorbance_within_fwhm",
                "automatic_band_assignment": False,
            },
        )
    )

    measurement_id = measurement_id or f"{sample_id}-ftir"
    preprocessing_id = preprocessing_fingerprint("ftir", steps)
    features = build_ftir_feature_records(
        candidate_table,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=input_path,
        preprocessing_id=preprocessing_id,
    )
    processed_table = pd.DataFrame(
        {
            "wavenumber_cm_1": wavenumber,
            "raw_signal": raw_signal,
            "converted_absorbance": absorbance,
            "baseline_absorbance": baseline,
            "baseline_corrected_absorbance": corrected_absorbance,
            "processed_absorbance": processed_absorbance,
        }
    )

    processed_path = output_dir / "ftir_processed_spectrum.csv"
    candidate_path = output_dir / "ftir_band_candidates.csv"
    feature_path = output_dir / "ftir_features_long.csv"
    plot_path = output_dir / "ftir_spectrum_with_candidates.png"
    processed_table.to_csv(processed_path, index=False)
    candidate_table.to_csv(candidate_path, index=False)
    records_to_frame(features).to_csv(feature_path, index=False)
    plot_ftir_spectrum(processed_table, candidate_table, plot_path, signal_type=signal_type)

    metadata.update(
        {
            "signal_type": signal_type,
            "signal_conversion_method": conversion_method,
            "input_axis_direction": input_axis_direction,
            "stored_axis_direction": "ascending",
        }
    )
    warnings = _ftir_warnings(
        spectrum,
        raw_signal,
        absorbance,
        metadata,
        signal_type=signal_type,
        baseline_method=baseline_method,
        candidate_table=candidate_table,
    )
    result = build_analysis_result(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument="ftir",
        source_file=input_path,
        acquisition_metadata=metadata,
        preprocessing_steps=steps,
        tables={
            "processed_spectrum": processed_path,
            "band_candidates": candidate_path,
            "long_format_features": feature_path,
        },
        figures={"spectrum_with_candidates": plot_path},
        features=features,
        warnings=warnings,
        limitations=FTIR_LIMITATIONS,
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


def plot_ftir_spectrum(
    processed_table: pd.DataFrame,
    candidate_table: pd.DataFrame,
    output_path: str | Path,
    *,
    signal_type: str,
) -> Path:
    """Save raw-signal and absorbance diagnostic FTIR plots."""
    output_path = Path(output_path)
    wavenumber = processed_table["wavenumber_cm_1"]
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)

    axes[0].plot(wavenumber, processed_table["raw_signal"], linewidth=1.0, label="raw signal")
    axes[0].set_ylabel(signal_type.replace("_", " "))
    axes[0].set_title("FTIR Raw Input Signal")
    axes[0].grid(alpha=0.25)

    axes[1].plot(
        wavenumber,
        processed_table["converted_absorbance"],
        linewidth=1.0,
        label="converted absorbance",
    )
    axes[1].plot(
        wavenumber,
        processed_table["baseline_absorbance"],
        linewidth=1.1,
        label="selected baseline",
    )
    axes[1].plot(
        wavenumber,
        processed_table["processed_absorbance"],
        linewidth=1.2,
        label="processed absorbance",
    )
    if not candidate_table.empty:
        axes[1].scatter(
            candidate_table["wavenumber_cm_1"],
            candidate_table["processed_absorbance"],
            s=28,
            label="detected candidates",
            zorder=3,
        )
    axes[1].set_xlabel(r"Wavenumber (cm$^{-1}$)")
    axes[1].set_ylabel("Absorbance")
    axes[1].set_title("Processed FTIR Absorbance")
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
        raise FileNotFoundError(f"FTIR file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"FTIR path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_FTIR_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_FTIR_EXTENSIONS))
        raise ValueError(
            f"FTIR file has unsupported extension '{input_path.suffix.lower()}'. "
            f"Supported extensions: {supported}."
        )
    return input_path


def _normalize_columns(table: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "wavenumber_cm_1": {
            "wavenumber_cm_1",
            "wavenumber",
            "wavenumber (cm-1)",
            "wavenumber (cm^-1)",
            "wave number",
            "wave_number",
            "cm-1",
            "cm^-1",
        },
        "signal": {
            "signal",
            "intensity",
            "absorbance",
            "transmittance",
            "transmittance_percent",
            "transmittance_fraction",
            "%t",
            "t",
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
        raise ValueError("Duplicate FTIR column aliases were found.")
    if any(name not in matches for name in FTIR_COLUMNS):
        raise ValueError("FTIR headers must identify wavenumber in cm^-1 and one signal column.")
    return table.rename(columns={values[0]: name for name, values in matches.items()})


def _validate_dataframe(table: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if table.shape[1] != 2:
        raise ValueError(f"{source_name} must contain exactly two columns.")
    spectrum = table.loc[:, FTIR_COLUMNS].copy()
    for column in FTIR_COLUMNS:
        numeric = pd.to_numeric(spectrum[column], errors="coerce")
        invalid = numeric.isna() & spectrum[column].notna() & (spectrum[column].astype(str).str.strip() != "")
        if invalid.any():
            bad = spectrum.loc[invalid, column].iloc[0]
            raise ValueError(f"{source_name} column '{column}' contains non-numeric value {bad!r}.")
        spectrum[column] = numeric
    spectrum = spectrum.dropna(subset=list(FTIR_COLUMNS))
    if not np.isfinite(spectrum[list(FTIR_COLUMNS)].to_numpy(dtype=float)).all():
        raise ValueError(f"{source_name} contains non-finite FTIR values.")
    if (spectrum["wavenumber_cm_1"] <= 0).any():
        raise ValueError(f"{source_name} wavenumber values must be greater than zero.")
    if spectrum["wavenumber_cm_1"].duplicated().any():
        duplicate = spectrum.loc[spectrum["wavenumber_cm_1"].duplicated(), "wavenumber_cm_1"].iloc[0]
        raise ValueError(f"{source_name} contains duplicate wavenumber value {duplicate}.")
    if len(spectrum) < 7:
        raise ValueError(f"{source_name} must contain at least 7 valid FTIR rows.")

    differences = np.diff(spectrum["wavenumber_cm_1"].to_numpy(dtype=float))
    if np.all(differences > 0):
        direction = "ascending"
    elif np.all(differences < 0):
        direction = "descending"
        spectrum = spectrum.iloc[::-1]
    else:
        raise ValueError(f"{source_name} wavenumber must be strictly monotonic.")
    spectrum = spectrum.reset_index(drop=True)
    spectrum.attrs["input_axis_direction"] = direction
    return spectrum


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


def _validate_signal_array(signal: pd.Series | np.ndarray) -> np.ndarray:
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or len(values) < 3:
        raise ValueError("At least 3 one-dimensional FTIR signal values are required.")
    if not np.isfinite(values).all():
        raise ValueError("FTIR signal contains non-finite values.")
    return values


def _valid_savgol_window(length: int, requested: int, polyorder: int) -> int | None:
    if length < 5:
        return None
    window = min(requested, length if length % 2 else length - 1)
    if window % 2 == 0:
        window -= 1
    if window <= polyorder:
        return None
    return window


def _integrate_within_bounds(
    x: np.ndarray,
    y: np.ndarray,
    lower: float,
    upper: float,
) -> float:
    lo, hi = sorted((float(lower), float(upper)))
    inside = (x >= lo) & (x <= hi)
    x_segment = np.concatenate(([lo], x[inside], [hi]))
    y_segment = np.concatenate(
        (
            [float(np.interp(lo, x, y))],
            y[inside],
            [float(np.interp(hi, x, y))],
        )
    )
    order = np.argsort(x_segment)
    x_segment = x_segment[order]
    y_segment = np.clip(y_segment[order], 0.0, None)
    unique_x, unique_indices = np.unique(x_segment, return_index=True)
    unique_y = y_segment[unique_indices]
    if len(unique_x) < 2:
        return 0.0
    return float(trapezoid(unique_y, unique_x))


def _empty_candidate_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "candidate_id",
            "wavenumber_cm_1",
            "raw_signal",
            "converted_absorbance",
            "baseline_absorbance",
            "baseline_corrected_absorbance",
            "processed_absorbance",
            "prominence_absorbance",
            "fwhm_cm_1",
            "left_fwhm_cm_1",
            "right_fwhm_cm_1",
            "half_height_processed_absorbance",
            "area_within_fwhm_absorbance_cm_1",
        ]
    )


def _validate_acquisition_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    values = dict(metadata or {})
    sampling_mode = values.get("sampling_mode", "unknown")
    allowed_modes = {
        "transmission",
        "atr",
        "diffuse_reflectance",
        "specular_reflectance",
        "unknown",
    }
    if sampling_mode not in allowed_modes:
        raise ValueError(f"sampling_mode must be one of: {', '.join(sorted(allowed_modes))}.")
    values["sampling_mode"] = sampling_mode

    for field in ("spectral_resolution_cm_1", "path_length_um"):
        value = values.get(field)
        if value is not None and (not np.isfinite(float(value)) or float(value) <= 0):
            raise ValueError(f"{field} must be a finite positive value.")
    scan_count = values.get("scan_count")
    if scan_count is not None and (isinstance(scan_count, bool) or int(scan_count) < 1):
        raise ValueError("scan_count must be an integer of at least one.")
    if scan_count is not None:
        values["scan_count"] = int(scan_count)

    for field in (
        "detector",
        "beamsplitter",
        "apodization",
        "atr_crystal",
        "background_description",
        "sample_preparation",
    ):
        value = values.get(field)
        if value is not None and not str(value).strip():
            raise ValueError(f"{field} must not be blank when provided.")
    return values


def _ftir_warnings(
    spectrum: pd.DataFrame,
    raw_signal: np.ndarray,
    absorbance: np.ndarray,
    metadata: dict[str, Any],
    *,
    signal_type: str,
    baseline_method: str,
    candidate_table: pd.DataFrame,
) -> list[str]:
    warnings: list[str] = []
    if spectrum.attrs.get("input_axis_direction") == "descending":
        warnings.append("input_wavenumber_axis_descending_reordered_for_processing")

    differences = np.diff(spectrum["wavenumber_cm_1"].to_numpy(dtype=float))
    median_spacing = float(np.median(differences))
    if not np.allclose(
        differences,
        median_spacing,
        rtol=0.05,
        atol=max(abs(median_spacing) * 1e-6, 1e-12),
    ):
        warnings.append("nonuniform_wavenumber_spacing")

    if signal_type == "transmittance_percent" and np.any(raw_signal > 100):
        warnings.append("transmittance_percent_above_100_not_clipped")
    if signal_type == "transmittance_fraction" and np.any(raw_signal > 1):
        warnings.append("transmittance_fraction_above_1_not_clipped")
    if np.any(absorbance < 0):
        warnings.append("negative_absorbance_present")
    if baseline_method == "none":
        warnings.append("baseline_correction_not_applied")
    if candidate_table.empty:
        warnings.append("no_band_candidates_detected")

    if metadata.get("sampling_mode") in (None, "unknown"):
        warnings.append("missing_sampling_mode_metadata")
    for field in ("spectral_resolution_cm_1", "scan_count", "detector", "background_description"):
        if metadata.get(field) is None:
            warnings.append(f"missing_{field}_metadata")
    if metadata.get("sampling_mode") == "atr" and metadata.get("atr_crystal") is None:
        warnings.append("missing_atr_crystal_metadata")
    return list(dict.fromkeys(warnings))
