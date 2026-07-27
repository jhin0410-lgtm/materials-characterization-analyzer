"""Conservative SAED radial-profile and calibrated ring-candidate analysis.

The workflow detects radial intensity candidates. It does not index diffraction
patterns, assign phases, identify zone axes, or validate crystallography.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mca_matplotlib"))

import cv2
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths, savgol_filter

from .contracts import PreprocessingStep
from .feature_records import records_to_frame
from .provenance import build_analysis_result, preprocessing_fingerprint
from .saed_features import build_saed_feature_records
from .utils import ensure_output_dir

SUPPORTED_SAED_EXTENSIONS = {".png", ".tif", ".tiff", ".bmp"}
SAED_LIMITATIONS = [
    "Detected radial candidates do not identify phases, zone axes, reflections, or crystal structures.",
    "Radial averaging assumes approximately circular diffraction features and can hide spots, arcs, ellipticity, texture, and detector distortion.",
    "Center position, central-beam masking, calibration, saturation, background, and peak-detection settings can materially change candidate radii and d-spacing.",
    "Calibrated d-spacing values are candidate measurements requiring reference calibration and expert review; they are not phase confirmation.",
    "The workflow uses g = 1/d. It does not use the alternative scattering-vector convention q = 2*pi/d.",
]


def load_saed_image(path: str | Path) -> np.ndarray:
    """Load an 8-bit or 16-bit SAED image while preserving stored intensity depth."""
    input_path = Path(path)
    if not input_path.is_file():
        raise FileNotFoundError(f"SAED image does not exist: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_SAED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_SAED_EXTENSIONS))
        raise ValueError(
            f"SAED image has unsupported extension '{input_path.suffix.lower()}'. "
            f"Supported extensions: {supported}."
        )

    image = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"SAED image could not be read: {input_path}")

    if image.ndim == 3:
        if image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        elif image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            raise ValueError(f"SAED image has unsupported channel count: {image.shape[2]}")
    if image.ndim != 2:
        raise ValueError("SAED image must be two-dimensional after grayscale conversion.")
    if image.dtype not in (np.uint8, np.uint16):
        raise ValueError(
            f"SAED image dtype must be uint8 or uint16; found {image.dtype}."
        )
    if min(image.shape) < 16:
        raise ValueError("SAED image must be at least 16 x 16 pixels.")
    return image


def resolve_center(
    image_shape: tuple[int, int],
    *,
    center_x_px: float | None = None,
    center_y_px: float | None = None,
) -> tuple[float, float, str]:
    """Return a validated manual center or the image midpoint with an explicit method."""
    height, width = image_shape
    if (center_x_px is None) != (center_y_px is None):
        raise ValueError("center_x_px and center_y_px must be supplied together.")
    if center_x_px is None:
        return (width - 1) / 2.0, (height - 1) / 2.0, "image_midpoint"

    center_x = float(center_x_px)
    center_y = float(center_y_px)
    if not (0.0 <= center_x <= width - 1 and 0.0 <= center_y <= height - 1):
        raise ValueError("SAED center must lie within the image bounds.")
    return center_x, center_y, "user_supplied"


def resolve_calibration(
    *,
    reciprocal_nm_inv_per_pixel: float | None = None,
    camera_constant_nm_pixel: float | None = None,
    reference_d_nm: float | None = None,
    reference_radius_px: float | None = None,
) -> dict[str, float | str] | None:
    """Resolve one explicit g=1/d calibration route."""
    pair_present = reference_d_nm is not None or reference_radius_px is not None
    if pair_present and (reference_d_nm is None or reference_radius_px is None):
        raise ValueError("reference_d_nm and reference_radius_px must be supplied together.")

    route_count = sum(
        value is not None
        for value in (
            reciprocal_nm_inv_per_pixel,
            camera_constant_nm_pixel,
            reference_d_nm if pair_present else None,
        )
    )
    if route_count > 1:
        raise ValueError("Provide only one SAED calibration route.")
    if route_count == 0:
        return None

    if reciprocal_nm_inv_per_pixel is not None:
        value = float(reciprocal_nm_inv_per_pixel)
        if value <= 0:
            raise ValueError("reciprocal_nm_inv_per_pixel must be greater than zero.")
        return {
            "method": "direct_reciprocal_g_equals_1_over_d",
            "reciprocal_nm_inv_per_pixel": value,
        }

    if camera_constant_nm_pixel is not None:
        constant = float(camera_constant_nm_pixel)
        if constant <= 0:
            raise ValueError("camera_constant_nm_pixel must be greater than zero.")
        return {
            "method": "camera_constant_d_equals_k_over_radius",
            "camera_constant_nm_pixel": constant,
            "reciprocal_nm_inv_per_pixel": 1.0 / constant,
        }

    reference_d = float(reference_d_nm)
    reference_radius = float(reference_radius_px)
    if reference_d <= 0 or reference_radius <= 0:
        raise ValueError("Reference d-spacing and radius must be greater than zero.")
    constant = reference_d * reference_radius
    return {
        "method": "single_reference_ring",
        "reference_d_nm": reference_d,
        "reference_radius_px": reference_radius,
        "camera_constant_nm_pixel": constant,
        "reciprocal_nm_inv_per_pixel": 1.0 / constant,
    }


def calculate_radial_profile(
    image: np.ndarray,
    *,
    center_x_px: float,
    center_y_px: float,
    bin_width_px: float = 1.0,
    max_radius_px: float | None = None,
) -> pd.DataFrame:
    """Calculate an annular mean-intensity profile around a supplied center."""
    if bin_width_px <= 0:
        raise ValueError("bin_width_px must be greater than zero.")
    height, width = image.shape
    max_full_radius = min(
        center_x_px,
        center_y_px,
        width - 1 - center_x_px,
        height - 1 - center_y_px,
    )
    if max_full_radius < bin_width_px:
        raise ValueError("SAED center leaves no complete annulus for radial analysis.")
    radius_limit = max_full_radius if max_radius_px is None else float(max_radius_px)
    if radius_limit <= 0:
        raise ValueError("max_radius_px must be greater than zero.")
    if radius_limit > max_full_radius + 1e-9:
        raise ValueError(
            "max_radius_px exceeds the largest complete annulus around the selected center."
        )

    yy, xx = np.indices(image.shape, dtype=float)
    radius = np.hypot(xx - center_x_px, yy - center_y_px)
    valid = radius <= radius_limit
    bin_index = np.floor(radius[valid] / bin_width_px).astype(int)
    values = image[valid].astype(float)
    bin_count = int(np.floor(radius_limit / bin_width_px)) + 1

    counts = np.bincount(bin_index, minlength=bin_count)
    sums = np.bincount(bin_index, weights=values, minlength=bin_count)
    radius_sums = np.bincount(bin_index, weights=radius[valid], minlength=bin_count)
    with np.errstate(divide="ignore", invalid="ignore"):
        means = sums / counts
        mean_radius = radius_sums / counts

    profile = pd.DataFrame(
        {
            "radius_px": mean_radius,
            "radial_mean_intensity": means,
            "pixel_count": counts,
        }
    )
    profile = profile[(profile["pixel_count"] > 0) & (profile["radius_px"] <= radius_limit)]
    return profile.reset_index(drop=True)


def smooth_radial_signal(
    signal: pd.Series | np.ndarray,
    *,
    window_length: int = 7,
    polyorder: int = 2,
) -> np.ndarray:
    """Apply optional Savitzky-Golay smoothing to the detection signal."""
    values = np.asarray(signal, dtype=float)
    if window_length == 0:
        return values.copy()
    if window_length < 0 or polyorder < 0:
        raise ValueError("Smoothing parameters must be non-negative.")
    window = _valid_savgol_window(len(values), int(window_length), int(polyorder))
    return values.copy() if window is None else savgol_filter(values, window, polyorder)


def detect_ring_candidates(
    profile: pd.DataFrame,
    *,
    ring_contrast: str = "bright",
    min_radius_px: float = 5.0,
    prominence_fraction: float = 0.05,
    min_distance_px: float = 5.0,
    smoothing_window: int = 7,
    smoothing_polyorder: int = 2,
    calibration: dict[str, float | str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detect descriptive radial candidates without indexing reflections."""
    if ring_contrast not in {"bright", "dark"}:
        raise ValueError("ring_contrast must be 'bright' or 'dark'.")
    if min_radius_px < 0:
        raise ValueError("min_radius_px must be non-negative.")
    if prominence_fraction <= 0:
        raise ValueError("prominence_fraction must be greater than zero.")
    if min_distance_px <= 0:
        raise ValueError("min_distance_px must be greater than zero.")
    if profile.empty:
        return profile.copy(), _empty_candidate_table()

    result_profile = profile.copy()
    raw_signal = result_profile["radial_mean_intensity"].to_numpy(dtype=float)
    detection_signal = raw_signal if ring_contrast == "bright" else -raw_signal
    processed = smooth_radial_signal(
        detection_signal,
        window_length=smoothing_window,
        polyorder=smoothing_polyorder,
    )
    result_profile["detection_signal"] = detection_signal
    result_profile["processed_detection_signal"] = processed

    search_mask = result_profile["radius_px"].to_numpy(dtype=float) >= min_radius_px
    search_indices = np.flatnonzero(search_mask)
    if len(search_indices) < 3:
        return result_profile, _empty_candidate_table()

    search_signal = processed[search_indices]
    dynamic_range = float(np.ptp(search_signal))
    if not np.isfinite(dynamic_range) or dynamic_range <= 0:
        return result_profile, _empty_candidate_table()

    radius_values = result_profile["radius_px"].to_numpy(dtype=float)
    typical_step = float(np.median(np.diff(radius_values))) if len(radius_values) > 1 else 1.0
    distance_bins = max(1, int(np.ceil(min_distance_px / typical_step)))
    local_peaks, properties = find_peaks(
        search_signal,
        prominence=max(dynamic_range * prominence_fraction, np.finfo(float).eps),
        distance=distance_bins,
    )
    if len(local_peaks) == 0:
        return result_profile, _empty_candidate_table()

    global_peaks = search_indices[local_peaks]
    _, half_height, left_ips_local, right_ips_local = peak_widths(
        search_signal, local_peaks, rel_height=0.5
    )
    search_positions = np.arange(len(search_indices), dtype=float)
    search_radii = radius_values[search_indices]
    left_radius = np.interp(left_ips_local, search_positions, search_radii)
    right_radius = np.interp(right_ips_local, search_positions, search_radii)

    table = pd.DataFrame(
        {
            "ring_id": np.arange(1, len(global_peaks) + 1),
            "radius_px": radius_values[global_peaks],
            "radial_mean_intensity": raw_signal[global_peaks],
            "processed_detection_signal": processed[global_peaks],
            "prominence": properties["prominences"],
            "fwhm_px": right_radius - left_radius,
            "left_fwhm_radius_px": left_radius,
            "right_fwhm_radius_px": right_radius,
            "half_height_processed_signal": half_height,
            "pixel_count": result_profile["pixel_count"].to_numpy()[global_peaks],
        }
    )
    if calibration is None:
        table["reciprocal_g_nm_inv"] = np.nan
        table["d_spacing_nm"] = np.nan
    else:
        reciprocal_per_pixel = float(calibration["reciprocal_nm_inv_per_pixel"])
        reciprocal_g = table["radius_px"] * reciprocal_per_pixel
        table["reciprocal_g_nm_inv"] = reciprocal_g
        table["d_spacing_nm"] = 1.0 / reciprocal_g

    table = table.sort_values("radius_px").reset_index(drop=True)
    table["ring_id"] = np.arange(1, len(table) + 1)
    return result_profile, table


def analyze_saed(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    center_x_px: float | None = None,
    center_y_px: float | None = None,
    bin_width_px: float = 1.0,
    min_radius_px: float = 5.0,
    max_radius_px: float | None = None,
    ring_contrast: str = "bright",
    smoothing_window: int = 7,
    smoothing_polyorder: int = 2,
    prominence_fraction: float = 0.05,
    min_distance_px: float = 5.0,
    reciprocal_nm_inv_per_pixel: float | None = None,
    camera_constant_nm_pixel: float | None = None,
    reference_d_nm: float | None = None,
    reference_radius_px: float | None = None,
    acquisition_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Run conservative SAED radial analysis and build a result contract."""
    if not sample_id.strip():
        raise ValueError("sample_id must not be empty.")

    metadata = _validate_acquisition_metadata(acquisition_metadata)
    calibration = resolve_calibration(
        reciprocal_nm_inv_per_pixel=reciprocal_nm_inv_per_pixel,
        camera_constant_nm_pixel=camera_constant_nm_pixel,
        reference_d_nm=reference_d_nm,
        reference_radius_px=reference_radius_px,
    )
    image = load_saed_image(input_path)
    center_x, center_y, center_method = resolve_center(
        image.shape,
        center_x_px=center_x_px,
        center_y_px=center_y_px,
    )
    profile = calculate_radial_profile(
        image,
        center_x_px=center_x,
        center_y_px=center_y,
        bin_width_px=bin_width_px,
        max_radius_px=max_radius_px,
    )
    processed_profile, candidates = detect_ring_candidates(
        profile,
        ring_contrast=ring_contrast,
        min_radius_px=min_radius_px,
        prominence_fraction=prominence_fraction,
        min_distance_px=min_distance_px,
        smoothing_window=smoothing_window,
        smoothing_polyorder=smoothing_polyorder,
        calibration=calibration,
    )

    steps = [
        PreprocessingStep(
            "saed-import",
            "preserve_grayscale_pixel_depth",
            {"dtype": str(image.dtype), "shape_pixels": list(image.shape)},
        ),
        PreprocessingStep(
            "saed-center",
            center_method,
            {"center_x_px": center_x, "center_y_px": center_y},
        ),
        PreprocessingStep(
            "saed-radial-profile",
            "complete_annulus_mean",
            {
                "bin_width_px": bin_width_px,
                "minimum_radius_px": min_radius_px,
                "maximum_radius_px": float(processed_profile["radius_px"].max()),
            },
        ),
        PreprocessingStep(
            "saed-smoothing",
            "savgol_smoothing" if smoothing_window else "no_smoothing",
            {
                "requested_window_length": smoothing_window,
                "polyorder": smoothing_polyorder,
            },
        ),
        PreprocessingStep(
            "saed-ring-candidates",
            "scipy_find_peaks_and_peak_widths",
            {
                "ring_contrast": ring_contrast,
                "prominence_fraction": prominence_fraction,
                "minimum_distance_px": min_distance_px,
                "relative_height": 0.5,
            },
        ),
    ]
    if calibration is not None:
        steps.append(
            PreprocessingStep(
                "saed-calibration",
                str(calibration["method"]),
                {key: value for key, value in calibration.items() if key != "method"},
                notes="Reciprocal-space convention is g = 1/d, not q = 2*pi/d.",
            )
        )

    measurement_id = measurement_id or f"{sample_id}-saed"
    preprocessing_id = preprocessing_fingerprint("saed", steps)
    features = build_saed_feature_records(
        candidates,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=input_path,
        preprocessing_id=preprocessing_id,
        center_x_px=center_x,
        center_y_px=center_y,
        analyzed_max_radius_px=float(processed_profile["radius_px"].max()),
    )

    output_dir = ensure_output_dir(output_dir)
    profile_path = output_dir / "saed_radial_profile.csv"
    candidate_path = output_dir / "saed_ring_candidates.csv"
    feature_path = output_dir / "saed_features_long.csv"
    profile_plot_path = output_dir / "saed_radial_profile.png"
    overlay_path = output_dir / "saed_ring_overlay.png"

    processed_profile.to_csv(profile_path, index=False)
    candidates.to_csv(candidate_path, index=False)
    records_to_frame(features).to_csv(feature_path, index=False)
    plot_radial_profile(processed_profile, candidates, profile_plot_path)
    plot_ring_overlay(image, candidates, center_x, center_y, overlay_path)

    result_metadata = dict(metadata)
    result_metadata.update(
        {
            "image_dtype": str(image.dtype),
            "image_height_px": int(image.shape[0]),
            "image_width_px": int(image.shape[1]),
            "center_x_px": center_x,
            "center_y_px": center_y,
            "center_method": center_method,
            "reciprocal_space_convention": "g_equals_1_over_d",
            "calibration": calibration,
        }
    )
    warnings = ["automatic_ring_candidates_require_manual_review"]
    if center_method == "image_midpoint":
        warnings.append("saed_center_assumed_image_midpoint")
    if calibration is None:
        warnings.append("saed_reciprocal_calibration_not_provided")
    if _has_saturated_pixels(image):
        warnings.append("saturated_pixels_present")

    analysis_result = build_analysis_result(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument="saed",
        source_file=input_path,
        acquisition_metadata=result_metadata,
        preprocessing_steps=steps,
        tables={
            "radial_profile": profile_path,
            "ring_candidates": candidate_path,
            "long_format_features": feature_path,
        },
        figures={
            "radial_profile": profile_plot_path,
            "ring_overlay": overlay_path,
        },
        features=features,
        warnings=warnings,
        limitations=SAED_LIMITATIONS,
    )
    return {
        "image": image,
        "radial_profile": processed_profile,
        "ring_candidates": candidates,
        "features": features,
        "analysis_result": analysis_result,
        "radial_profile_path": profile_path,
        "ring_candidates_path": candidate_path,
        "feature_path": feature_path,
        "radial_profile_plot_path": profile_plot_path,
        "overlay_path": overlay_path,
    }


def plot_radial_profile(
    profile: pd.DataFrame,
    candidates: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Save raw radial intensity and processed candidate-detection signals."""
    output_path = Path(output_path)
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)
    axes[0].plot(profile["radius_px"], profile["radial_mean_intensity"], linewidth=1.2)
    axes[0].set_ylabel("Mean intensity")
    axes[0].set_title("SAED Radial Mean Intensity")
    axes[0].grid(alpha=0.25)

    axes[1].plot(
        profile["radius_px"],
        profile["processed_detection_signal"],
        linewidth=1.2,
        label="processed detection signal",
    )
    if not candidates.empty:
        axes[1].scatter(
            candidates["radius_px"],
            candidates["processed_detection_signal"],
            s=30,
            zorder=3,
            label="ring candidates",
        )
    axes[1].set_xlabel("Radius (pixels)")
    axes[1].set_ylabel("Detection signal")
    axes[1].set_title("SAED Radial Candidate Detection")
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def plot_ring_overlay(
    image: np.ndarray,
    candidates: pd.DataFrame,
    center_x_px: float,
    center_y_px: float,
    output_path: str | Path,
) -> Path:
    """Save an 8-bit display overlay without changing measurement intensities."""
    output_path = Path(output_path)
    display = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    overlay = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
    center = (int(round(center_x_px)), int(round(center_y_px)))
    cv2.drawMarker(overlay, center, (0, 0, 255), cv2.MARKER_CROSS, 14, 1)
    for row in candidates.itertuples(index=False):
        radius = max(1, int(round(float(row.radius_px))))
        cv2.circle(overlay, center, radius, (0, 255, 0), 1)
    if not cv2.imwrite(str(output_path), overlay):
        raise OSError(f"Failed to save SAED overlay: {output_path}")
    return output_path


def _empty_candidate_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ring_id",
            "radius_px",
            "radial_mean_intensity",
            "processed_detection_signal",
            "prominence",
            "fwhm_px",
            "left_fwhm_radius_px",
            "right_fwhm_radius_px",
            "half_height_processed_signal",
            "pixel_count",
            "reciprocal_g_nm_inv",
            "d_spacing_nm",
        ]
    )


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


def _validate_acquisition_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    values = {key: value for key, value in dict(metadata or {}).items() if value is not None}
    for field in ("accelerating_voltage_kv", "camera_length_mm", "detector_pixel_size_um"):
        value = values.get(field)
        if value is not None and float(value) <= 0:
            raise ValueError(f"{field} must be greater than zero when provided.")
    return values


def _has_saturated_pixels(image: np.ndarray) -> bool:
    return bool(np.any(image == np.iinfo(image.dtype).max))
