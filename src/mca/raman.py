"""Raman spectrum analysis with explicit preprocessing and provenance.

The workflow extracts descriptive peaks only. It does not assign Raman bands,
compounds, phases, bonds, or mechanisms.
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
from .provenance import build_analysis_result, preprocessing_fingerprint
from .raman_features import build_raman_feature_records
from .utils import ensure_output_dir

SUPPORTED_RAMAN_EXTENSIONS = {".csv", ".txt", ".tsv"}
RAMAN_COLUMNS = ("raman_shift_cm_1", "intensity")
RAMAN_LIMITATIONS = [
    "Automatically detected peaks do not identify compounds, phases, bonds, or vibrational modes.",
    "Baseline correction and smoothing can change peak height, width, area, and detectability.",
    "FWHM and within-FWHM area are descriptive outputs, not fitted line-shape parameters.",
    "Peak overlap, fluorescence, cosmic rays, saturation, calibration, and spectral resolution require expert review.",
]


def load_raman_file(path: str | Path) -> pd.DataFrame:
    """Load two-column Raman shift/intensity data from CSV, TXT, or TSV."""
    input_path = _validate_input_path(path)
    source_name = f"Raman file '{input_path}'"

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
                table.columns = list(RAMAN_COLUMNS)
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
        f"{source_name} could not be interpreted as supported two-column Raman data. "
        "Expected Raman shift in cm^-1 and intensity."
    )


def asymmetric_least_squares_baseline(
    intensity: pd.Series | np.ndarray,
    *,
    smoothness: float = 1_000_000.0,
    asymmetry: float = 0.01,
    iterations: int = 15,
) -> np.ndarray:
    """Estimate a smooth asymmetric least-squares baseline."""
    values = np.asarray(intensity, dtype=float)
    if values.ndim != 1 or len(values) < 3:
        raise ValueError("At least 3 one-dimensional intensity values are required.")
    if not np.isfinite(values).all():
        raise ValueError("Raman intensity contains non-finite values.")
    if smoothness <= 0:
        raise ValueError("baseline smoothness must be greater than zero.")
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
    penalty = smoothness * (difference.T @ difference)
    weights = np.ones(length)
    baseline = values.copy()

    for _ in range(int(iterations)):
        weight_matrix = sparse.spdiags(weights, 0, length, length)
        baseline = np.asarray(spsolve(weight_matrix + penalty, weights * values), dtype=float)
        weights = np.where(values > baseline, asymmetry, 1.0 - asymmetry)
    return baseline


def smooth_raman_intensity(
    intensity: pd.Series | np.ndarray,
    *,
    window_length: int = 11,
    polyorder: int = 3,
) -> np.ndarray:
    """Apply Savitzky-Golay smoothing; zero window disables smoothing."""
    values = np.asarray(intensity, dtype=float)
    if window_length == 0:
        return values.copy()
    if window_length < 0 or polyorder < 0:
        raise ValueError("smoothing parameters must be non-negative.")
    window = _valid_savgol_window(len(values), int(window_length), int(polyorder))
    return values.copy() if window is None else savgol_filter(values, window, polyorder)


def detect_raman_peaks(
    shift: pd.Series | np.ndarray,
    raw_intensity: pd.Series | np.ndarray,
    baseline: pd.Series | np.ndarray,
    processed_intensity: pd.Series | np.ndarray,
    *,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    edge_margin: int = 2,
) -> pd.DataFrame:
    """Detect peaks and calculate descriptive FWHM and within-FWHM area."""
    x = np.asarray(shift, dtype=float)
    raw = np.asarray(raw_intensity, dtype=float)
    base = np.asarray(baseline, dtype=float)
    processed = np.asarray(processed_intensity, dtype=float)
    if not (len(x) == len(raw) == len(base) == len(processed)):
        raise ValueError("Raman arrays must have the same length.")
    if prominence_fraction <= 0 or min_distance < 1:
        raise ValueError("Peak prominence must be positive and distance at least one sample.")

    corrected = raw - base
    dynamic_range = float(np.ptp(processed))
    if len(x) < 3 or not np.isfinite(dynamic_range) or dynamic_range <= 0:
        return _empty_peak_table()

    peaks, properties = find_peaks(
        processed,
        prominence=max(dynamic_range * prominence_fraction, np.finfo(float).eps),
        distance=int(min_distance),
    )
    if edge_margin > 0 and len(peaks):
        valid = (peaks >= edge_margin) & (peaks <= len(x) - 1 - edge_margin)
        peaks = peaks[valid]
        properties = {key: np.asarray(value)[valid] for key, value in properties.items()}
    if len(peaks) == 0:
        return _empty_peak_table()

    _, half_height, left_ips, right_ips = peak_widths(processed, peaks, rel_height=0.5)
    sample_index = np.arange(len(x), dtype=float)
    left = np.interp(left_ips, sample_index, x)
    right = np.interp(right_ips, sample_index, x)

    return pd.DataFrame(
        {
            "peak_id": np.arange(1, len(peaks) + 1),
            "raman_shift_cm_1": x[peaks],
            "raw_intensity": raw[peaks],
            "baseline_intensity": base[peaks],
            "corrected_intensity": corrected[peaks],
            "processed_intensity": processed[peaks],
            "prominence": properties["prominences"],
            "fwhm_cm_1": right - left,
            "left_fwhm_cm_1": left,
            "right_fwhm_cm_1": right,
            "half_height_processed_intensity": half_height,
            "area_within_fwhm_intensity_cm_1": [
                _integrate_within_bounds(x, corrected, lower, upper)
                for lower, upper in zip(left, right)
            ],
        }
    ).sort_values("raman_shift_cm_1").reset_index(drop=True)


def analyze_raman(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    baseline_method: str = "asls",
    baseline_smoothness: float = 1_000_000.0,
    baseline_asymmetry: float = 0.01,
    baseline_iterations: int = 15,
    smoothing_window: int = 11,
    smoothing_polyorder: int = 3,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    acquisition_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Run Raman preprocessing, peak extraction, artifacts, and result contract."""
    if not sample_id.strip():
        raise ValueError("sample_id must not be empty.")
    if baseline_method not in {"none", "asls"}:
        raise ValueError("baseline_method must be 'none' or 'asls'.")
    metadata = _validate_acquisition_metadata(acquisition_metadata)

    output_dir = ensure_output_dir(output_dir)
    spectrum = load_raman_file(input_path)
    raw = spectrum["intensity"].to_numpy(dtype=float)
    steps = [PreprocessingStep("raman-import", "two_column_raman_validation")]

    if baseline_method == "asls":
        baseline = asymmetric_least_squares_baseline(
            raw,
            smoothness=baseline_smoothness,
            asymmetry=baseline_asymmetry,
            iterations=baseline_iterations,
        )
        steps.append(
            PreprocessingStep(
                "raman-baseline",
                "asymmetric_least_squares_baseline",
                {
                    "smoothness": baseline_smoothness,
                    "asymmetry": baseline_asymmetry,
                    "iterations": baseline_iterations,
                },
            )
        )
    else:
        baseline = np.zeros_like(raw)
        steps.append(PreprocessingStep("raman-baseline", "no_baseline_correction"))

    corrected = raw - baseline
    processed = smooth_raman_intensity(
        corrected,
        window_length=smoothing_window,
        polyorder=smoothing_polyorder,
    )
    steps.append(
        PreprocessingStep(
            "raman-smoothing",
            "savgol_smoothing" if smoothing_window else "no_smoothing",
            {
                "requested_window_length": smoothing_window,
                "polyorder": smoothing_polyorder,
                "application": "conditional_on_data_length",
            },
        )
    )
    peak_table = detect_raman_peaks(
        spectrum["raman_shift_cm_1"],
        raw,
        baseline,
        processed,
        prominence_fraction=prominence_fraction,
        min_distance=min_distance,
    )
    steps.append(
        PreprocessingStep(
            "raman-peaks",
            "scipy_find_peaks_and_peak_widths",
            {
                "prominence_fraction": prominence_fraction,
                "minimum_distance_samples": min_distance,
                "relative_height": 0.5,
                "area_definition": "nonnegative_baseline_corrected_signal_within_fwhm",
            },
        )
    )

    measurement_id = measurement_id or f"{sample_id}-raman"
    preprocessing_id = preprocessing_fingerprint("raman", steps)
    features = build_raman_feature_records(
        peak_table,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=input_path,
        preprocessing_id=preprocessing_id,
    )
    processed_table = pd.DataFrame(
        {
            "raman_shift_cm_1": spectrum["raman_shift_cm_1"],
            "raw_intensity": raw,
            "baseline_intensity": baseline,
            "corrected_intensity": corrected,
            "processed_intensity": processed,
        }
    )

    processed_path = output_dir / "raman_processed_spectrum.csv"
    peak_path = output_dir / "raman_peak_table.csv"
    feature_path = output_dir / "raman_features_long.csv"
    plot_path = output_dir / "raman_spectrum_with_peaks.png"
    processed_table.to_csv(processed_path, index=False)
    peak_table.to_csv(peak_path, index=False)
    records_to_frame(features).to_csv(feature_path, index=False)
    plot_raman_spectrum(processed_table, peak_table, plot_path)

    result = build_analysis_result(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument="raman",
        source_file=input_path,
        acquisition_metadata=metadata,
        preprocessing_steps=steps,
        tables={
            "processed_spectrum": processed_path,
            "peak_table": peak_path,
            "long_format_features": feature_path,
        },
        figures={"spectrum_with_peaks": plot_path},
        features=features,
        warnings=_raman_warnings(spectrum, raw, metadata),
        limitations=RAMAN_LIMITATIONS,
    )
    return {
        "spectrum": spectrum,
        "processed_spectrum": processed_table,
        "peak_table": peak_table,
        "features": features,
        "analysis_result": result,
        "processed_spectrum_path": processed_path,
        "peak_table_path": peak_path,
        "feature_path": feature_path,
        "plot_path": plot_path,
    }


def plot_raman_spectrum(
    processed_table: pd.DataFrame,
    peak_table: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Save raw/baseline and processed Raman views."""
    output_path = Path(output_path)
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)
    x = processed_table["raman_shift_cm_1"]

    axes[0].plot(x, processed_table["raw_intensity"], linewidth=1.0, label="raw")
    axes[0].plot(x, processed_table["baseline_intensity"], linewidth=1.2, label="baseline")
    axes[0].set_ylabel("Intensity (a.u.)")
    axes[0].set_title("Raman Raw Spectrum and Estimated Baseline")
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(x, processed_table["corrected_intensity"], linewidth=1.0, label="baseline-corrected")
    axes[1].plot(x, processed_table["processed_intensity"], linewidth=1.3, label="processed")
    if not peak_table.empty:
        axes[1].scatter(
            peak_table["raman_shift_cm_1"],
            peak_table["processed_intensity"],
            s=28,
            label="detected peaks",
            zorder=3,
        )
    axes[1].set_xlabel("Raman shift (cm$^{-1}$)")
    axes[1].set_ylabel("Corrected intensity (a.u.)")
    axes[1].set_title("Processed Raman Spectrum")
    axes[1].legend()
    axes[1].grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def _validate_input_path(path: str | Path) -> Path:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Raman file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"Raman path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_RAMAN_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_RAMAN_EXTENSIONS))
        raise ValueError(
            f"Raman file has unsupported extension '{input_path.suffix.lower()}'. "
            f"Supported extensions: {supported}."
        )
    return input_path


def _normalize_columns(table: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "raman_shift_cm_1": {
            "raman_shift_cm_1",
            "raman_shift_cm-1",
            "raman shift",
            "raman shift (cm-1)",
            "raman shift (cm^-1)",
            "shift_cm_1",
            "shift_cm-1",
        },
        "intensity": {"intensity", "counts", "signal", "intensity_a.u.", "intensity (a.u.)"},
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
        raise ValueError("Duplicate Raman column aliases were found.")
    if any(name not in matches for name in RAMAN_COLUMNS):
        raise ValueError("Raman headers must identify Raman shift in cm^-1 and intensity.")
    return table.rename(columns={values[0]: name for name, values in matches.items()})


def _validate_dataframe(table: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if table.shape[1] != 2:
        raise ValueError(f"{source_name} must contain exactly two columns.")
    spectrum = table.loc[:, RAMAN_COLUMNS].copy()
    for column in RAMAN_COLUMNS:
        numeric = pd.to_numeric(spectrum[column], errors="coerce")
        invalid = numeric.isna() & spectrum[column].notna() & (spectrum[column].astype(str).str.strip() != "")
        if invalid.any():
            bad = spectrum.loc[invalid, column].iloc[0]
            raise ValueError(f"{source_name} column '{column}' contains non-numeric value {bad!r}.")
        spectrum[column] = numeric
    spectrum = spectrum.dropna(subset=list(RAMAN_COLUMNS))
    if not np.isfinite(spectrum[list(RAMAN_COLUMNS)].to_numpy(dtype=float)).all():
        raise ValueError(f"{source_name} contains non-finite Raman values.")
    if spectrum["raman_shift_cm_1"].duplicated().any():
        duplicate = spectrum.loc[spectrum["raman_shift_cm_1"].duplicated(), "raman_shift_cm_1"].iloc[0]
        raise ValueError(f"{source_name} contains duplicate Raman shift value {duplicate}.")
    spectrum = spectrum.sort_values("raman_shift_cm_1").reset_index(drop=True)
    if len(spectrum) < 7:
        raise ValueError(f"{source_name} must contain at least 7 valid Raman rows.")
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


def _integrate_within_bounds(x: np.ndarray, y: np.ndarray, left: float, right: float) -> float:
    mask = (x > left) & (x < right)
    segment_x = np.concatenate(([left], x[mask], [right]))
    segment_y = np.clip(np.interp(segment_x, x, y), 0.0, None)
    return float(trapezoid(segment_y, segment_x))


def _empty_peak_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "peak_id",
            "raman_shift_cm_1",
            "raw_intensity",
            "baseline_intensity",
            "corrected_intensity",
            "processed_intensity",
            "prominence",
            "fwhm_cm_1",
            "left_fwhm_cm_1",
            "right_fwhm_cm_1",
            "half_height_processed_intensity",
            "area_within_fwhm_intensity_cm_1",
        ]
    )


def _validate_acquisition_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    values = dict(metadata or {})
    positive_fields = (
        "laser_wavelength_nm",
        "laser_power_mw",
        "exposure_time_s",
        "spectral_resolution_cm_1",
    )
    for field in positive_fields:
        value = values.get(field)
        if value is not None and float(value) <= 0:
            raise ValueError(f"{field} must be greater than zero when provided.")
    accumulation_count = values.get("accumulation_count")
    if accumulation_count is not None:
        if int(accumulation_count) != accumulation_count or int(accumulation_count) < 1:
            raise ValueError("accumulation_count must be a positive integer when provided.")
        values["accumulation_count"] = int(accumulation_count)
    return values


def _raman_warnings(
    spectrum: pd.DataFrame,
    raw_intensity: np.ndarray,
    metadata: dict[str, Any],
) -> list[str]:
    warnings = ["automatic_peak_detection_requires_manual_review"]
    recommended = {
        "laser_wavelength_nm": "laser_wavelength_not_provided",
        "laser_power_mw": "laser_power_not_provided",
        "exposure_time_s": "exposure_time_not_provided",
        "accumulation_count": "accumulation_count_not_provided",
        "spectral_resolution_cm_1": "spectral_resolution_not_provided",
    }
    warnings.extend(message for field, message in recommended.items() if metadata.get(field) is None)
    spacing = np.diff(spectrum["raman_shift_cm_1"].to_numpy(dtype=float))
    if len(spacing) and not np.allclose(spacing, np.median(spacing), rtol=1e-3, atol=1e-9):
        warnings.append("nonuniform_raman_shift_spacing")
    if np.any(raw_intensity < 0):
        warnings.append("negative_raw_intensity_present")
    return warnings
