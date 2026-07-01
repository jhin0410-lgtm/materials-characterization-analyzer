"""XRD CSV analysis helpers.

This module intentionally avoids phase assignment. It extracts basic peak
features that can support later interpretation by a materials engineer.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mca_matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths, savgol_filter

from .utils import ensure_output_dir, validate_columns

REQUIRED_XRD_COLUMNS = ("two_theta", "intensity")


def read_xrd_csv(path: str | Path) -> pd.DataFrame:
    """Read an XRD CSV file with two_theta and intensity columns."""
    df = pd.read_csv(path)
    validate_columns(df, REQUIRED_XRD_COLUMNS, "XRD CSV")

    xrd = df.loc[:, REQUIRED_XRD_COLUMNS].copy()
    xrd["two_theta"] = pd.to_numeric(xrd["two_theta"], errors="coerce")
    xrd["intensity"] = pd.to_numeric(xrd["intensity"], errors="coerce")
    xrd = xrd.dropna().sort_values("two_theta").reset_index(drop=True)

    if xrd.empty:
        raise ValueError("XRD CSV did not contain any valid numeric rows.")
    return xrd


def _valid_savgol_window(length: int, requested_window: int, polyorder: int) -> int | None:
    if length < 5:
        return None

    window = min(int(requested_window), length if length % 2 else length - 1)
    if window % 2 == 0:
        window -= 1
    if window <= polyorder:
        window = polyorder + 2
        if window % 2 == 0:
            window += 1
    if window > length:
        return None
    return window if window >= 5 else None


def smooth_intensity(
    intensity: pd.Series | np.ndarray,
    window_length: int = 11,
    polyorder: int = 3,
) -> np.ndarray:
    """Smooth intensity with a Savitzky-Golay filter when enough points exist."""
    values = np.asarray(intensity, dtype=float)
    window = _valid_savgol_window(len(values), window_length, polyorder)
    if window is None:
        return values.copy()
    return savgol_filter(values, window_length=window, polyorder=polyorder)


def scherrer_crystallite_size_estimate(
    fwhm_deg_2theta: float,
    two_theta_deg: float,
    wavelength: float,
    shape_factor: float = 0.9,
    instrumental_broadening_deg: float = 0.0,
) -> float:
    """Estimate crystallite size with the Scherrer equation.

    The returned value has the same length unit as the wavelength argument.
    The result is a crystallite size estimate, not a particle size.
    """
    if fwhm_deg_2theta <= 0 or wavelength <= 0 or shape_factor <= 0:
        return float("nan")

    measured_beta = np.deg2rad(fwhm_deg_2theta)
    instrumental_beta = np.deg2rad(max(instrumental_broadening_deg, 0.0))
    corrected_beta_sq = measured_beta**2 - instrumental_beta**2
    if corrected_beta_sq <= 0:
        return float("nan")

    theta = np.deg2rad(two_theta_deg / 2.0)
    denominator = np.sqrt(corrected_beta_sq) * np.cos(theta)
    if denominator <= 0:
        return float("nan")
    return float(shape_factor * wavelength / denominator)


def detect_peaks(
    two_theta: pd.Series | np.ndarray,
    raw_intensity: pd.Series | np.ndarray,
    smoothed_intensity: pd.Series | np.ndarray | None = None,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    edge_margin: int = 3,
) -> pd.DataFrame:
    """Detect XRD peaks and estimate FWHM in degrees 2theta."""
    x = np.asarray(two_theta, dtype=float)
    raw_y = np.asarray(raw_intensity, dtype=float)
    y = np.asarray(smoothed_intensity if smoothed_intensity is not None else raw_y, dtype=float)

    if len(x) != len(y) or len(x) != len(raw_y):
        raise ValueError("two_theta and intensity arrays must have the same length.")
    if len(x) < 3:
        return _empty_peak_table()

    dynamic_range = float(np.nanmax(y) - np.nanmin(y))
    prominence = max(dynamic_range * prominence_fraction, np.finfo(float).eps)
    peaks, properties = find_peaks(y, prominence=prominence, distance=max(1, int(min_distance)))

    if edge_margin > 0 and len(peaks) > 0:
        valid = (peaks >= edge_margin) & (peaks <= len(x) - 1 - edge_margin)
        peaks = peaks[valid]
        properties = {key: np.asarray(value)[valid] for key, value in properties.items()}

    if len(peaks) == 0:
        return _empty_peak_table()

    widths, width_heights, left_ips, right_ips = peak_widths(y, peaks, rel_height=0.5)
    sample_index = np.arange(len(x), dtype=float)
    left_two_theta = np.interp(left_ips, sample_index, x)
    right_two_theta = np.interp(right_ips, sample_index, x)
    fwhm = right_two_theta - left_two_theta

    peak_table = pd.DataFrame(
        {
            "peak_id": np.arange(1, len(peaks) + 1),
            "two_theta_deg": x[peaks],
            "intensity": raw_y[peaks],
            "smoothed_intensity": y[peaks],
            "prominence": properties.get("prominences", np.full(len(peaks), np.nan)),
            "fwhm_deg_2theta": fwhm,
            "half_max_intensity": width_heights,
        }
    )
    return peak_table.sort_values("two_theta_deg").reset_index(drop=True)


def _empty_peak_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "peak_id",
            "two_theta_deg",
            "intensity",
            "smoothed_intensity",
            "prominence",
            "fwhm_deg_2theta",
            "half_max_intensity",
        ]
    )


def add_scherrer_estimates(
    peak_table: pd.DataFrame,
    wavelength: float | None,
    shape_factor: float = 0.9,
    instrumental_broadening_deg: float = 0.0,
) -> pd.DataFrame:
    """Add Scherrer crystallite size estimates when a wavelength is provided."""
    output = peak_table.copy()
    if wavelength is None:
        return output

    output["crystallite_size_estimate_same_unit_as_wavelength"] = [
        scherrer_crystallite_size_estimate(
            fwhm_deg_2theta=float(row["fwhm_deg_2theta"]),
            two_theta_deg=float(row["two_theta_deg"]),
            wavelength=float(wavelength),
            shape_factor=float(shape_factor),
            instrumental_broadening_deg=float(instrumental_broadening_deg),
        )
        for _, row in output.iterrows()
    ]
    return output


def plot_xrd_pattern(
    xrd: pd.DataFrame,
    smoothed: np.ndarray,
    peak_table: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Save an XRD pattern plot with detected peak markers."""
    output_path = Path(output_path)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(xrd["two_theta"], xrd["intensity"], color="#4c566a", linewidth=1.0, label="raw")
    ax.plot(xrd["two_theta"], smoothed, color="#0077b6", linewidth=1.4, label="smoothed")

    if not peak_table.empty:
        ax.scatter(
            peak_table["two_theta_deg"],
            peak_table["smoothed_intensity"],
            color="#d62828",
            s=28,
            label="detected peaks",
            zorder=3,
        )

    ax.set_xlabel("2theta (degrees)")
    ax.set_ylabel("Intensity (a.u.)")
    ax.set_title("XRD Pattern with Detected Peaks")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def analyze_xrd(
    input_path: str | Path,
    output_dir: str | Path,
    smoothing_window: int = 11,
    smoothing_polyorder: int = 3,
    prominence_fraction: float = 0.05,
    min_distance: int = 3,
    wavelength: float | None = None,
    shape_factor: float = 0.9,
    instrumental_broadening_deg: float = 0.0,
) -> dict[str, object]:
    """Run the v0.1 XRD workflow and save plot/table outputs."""
    output_dir = ensure_output_dir(output_dir)
    xrd = read_xrd_csv(input_path)
    smoothed = smooth_intensity(xrd["intensity"], smoothing_window, smoothing_polyorder)
    peak_table = detect_peaks(
        xrd["two_theta"],
        xrd["intensity"],
        smoothed,
        prominence_fraction=prominence_fraction,
        min_distance=min_distance,
    )
    peak_table = add_scherrer_estimates(
        peak_table,
        wavelength=wavelength,
        shape_factor=shape_factor,
        instrumental_broadening_deg=instrumental_broadening_deg,
    )

    peak_table_path = output_dir / "xrd_peak_table.csv"
    pattern_path = output_dir / "xrd_pattern_with_peaks.png"
    peak_table.to_csv(peak_table_path, index=False)
    plot_xrd_pattern(xrd, smoothed, peak_table, pattern_path)

    return {
        "xrd": xrd,
        "smoothed_intensity": smoothed,
        "peak_table": peak_table,
        "peak_table_path": peak_table_path,
        "plot_path": pattern_path,
    }


