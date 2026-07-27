"""Conservative TEM image region analysis with explicit scale and provenance.

The workflow segments user-selected bright or dark contrast regions. It does not
claim that those regions are particles, pores, phases, defects, or lattice
features, and it does not perform SAED or HRTEM lattice analysis.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mca_matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .contracts import PreprocessingStep
from .feature_records import records_to_frame
from .provenance import build_analysis_result, preprocessing_fingerprint
from .tem_features import build_tem_feature_records
from .utils import ensure_output_dir

SUPPORTED_TEM_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".pgm"}
TEM_LIMITATIONS = [
    "Threshold-detected contrast regions are not automatically identified as particles, pores, phases, defects, or lattice features.",
    "TEM contrast depends on imaging mode, thickness, diffraction, focus, orientation, detector geometry, dose, and sample preparation.",
    "Equivalent diameter is a two-dimensional region descriptor and is not a validated particle-size distribution without representative sampling and manual review.",
    "This workflow does not perform SAED indexing, HRTEM lattice-spacing measurement, FFT interpretation, or phase assignment.",
]


def read_tem_image(path: str | Path) -> np.ndarray:
    """Read an 8-bit or 16-bit TEM image without changing stored pixel depth."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"TEM image does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"TEM path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_TEM_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_TEM_EXTENSIONS))
        raise ValueError(
            f"TEM image has unsupported extension '{input_path.suffix.lower()}'. "
            f"Supported extensions: {supported}."
        )
    encoded = np.fromfile(input_path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Could not decode TEM image: {input_path}")
    if image.dtype not in (np.uint8, np.uint16):
        raise ValueError(
            f"TEM image dtype {image.dtype} is unsupported; provide an 8-bit or 16-bit integer image."
        )
    if image.ndim not in (2, 3):
        raise ValueError(f"TEM image must be grayscale, BGR, or BGRA. Found shape {image.shape}.")
    if image.ndim == 3 and image.shape[2] not in (3, 4):
        raise ValueError(
            f"TEM color image must have 3 or 4 channels. Found {image.shape[2]} channels."
        )
    return image


def to_grayscale_preserve_dtype(image: np.ndarray) -> np.ndarray:
    """Convert BGR/BGRA input to grayscale while preserving uint8/uint16 dtype."""
    if image.ndim == 2:
        return image.copy()
    conversion = cv2.COLOR_BGR2GRAY if image.shape[2] == 3 else cv2.COLOR_BGRA2GRAY
    return cv2.cvtColor(image, conversion)


def crop_tem_roi(image: np.ndarray, roi: tuple[int, int, int, int] | None) -> np.ndarray:
    """Return an explicitly requested x, y, width, height ROI or the full image."""
    if roi is None:
        return image.copy()
    x, y, width, height = (int(value) for value in roi)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("TEM ROI must use non-negative x/y and positive width/height.")
    image_height, image_width = image.shape[:2]
    if x + width > image_width or y + height > image_height:
        raise ValueError(
            f"TEM ROI {(x, y, width, height)} exceeds image bounds {(image_width, image_height)}."
        )
    return image[y : y + height, x : x + width].copy()


def prepare_tem_segmentation_image(
    gray: np.ndarray,
    gaussian_blur_kernel: int = 0,
) -> np.ndarray:
    """Optionally blur the segmentation input; zero preserves the grayscale data."""
    kernel = int(gaussian_blur_kernel)
    if kernel == 0:
        return gray.copy()
    if kernel < 3 or kernel % 2 == 0:
        raise ValueError("gaussian_blur_kernel must be 0 or an odd integer of at least 3.")
    return cv2.GaussianBlur(gray, (kernel, kernel), 0)


def threshold_tem_regions(
    gray: np.ndarray,
    contrast_target: str,
) -> tuple[float, np.ndarray]:
    """Apply Otsu thresholding to explicitly selected bright or dark contrast."""
    if contrast_target not in {"bright", "dark"}:
        raise ValueError("contrast_target must be 'bright' or 'dark'.")
    threshold_type = (
        cv2.THRESH_BINARY if contrast_target == "bright" else cv2.THRESH_BINARY_INV
    )
    threshold_value, mask = cv2.threshold(
        gray,
        0,
        _mask_max_value(gray.dtype),
        threshold_type | cv2.THRESH_OTSU,
    )
    mask_uint8 = (mask > 0).astype(np.uint8) * 255
    return float(threshold_value), mask_uint8


def find_tem_regions(
    mask: np.ndarray,
    *,
    min_area_pixels: float = 5.0,
    exclude_border_regions: bool = False,
) -> tuple[list[np.ndarray], int]:
    """Find external contours and optionally exclude regions touching image borders."""
    if min_area_pixels <= 0:
        raise ValueError("min_area_pixels must be greater than zero.")
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    selected: list[np.ndarray] = []
    excluded_border_count = 0
    for contour in contours:
        if cv2.contourArea(contour) < float(min_area_pixels):
            continue
        touches = contour_touches_border(contour, mask.shape)
        if exclude_border_regions and touches:
            excluded_border_count += 1
            continue
        selected.append(contour)
    return selected, excluded_border_count


def contour_touches_border(
    contour: np.ndarray,
    image_shape: tuple[int, ...],
) -> bool:
    x, y, width, height = cv2.boundingRect(contour)
    image_height, image_width = image_shape[:2]
    return (
        x <= 0
        or y <= 0
        or x + width >= image_width
        or y + height >= image_height
    )


def measure_tem_regions(
    contours: list[np.ndarray],
    gray: np.ndarray,
    *,
    nm_per_pixel: float,
    contrast_target: str,
) -> pd.DataFrame:
    """Measure geometric and raw-intensity descriptors for detected regions."""
    if nm_per_pixel <= 0:
        raise ValueError("nm_per_pixel must be greater than zero.")
    height, width = gray.shape[:2]
    image_area_pixels = float(height * width)
    total_area_pixels = float(sum(cv2.contourArea(contour) for contour in contours))
    area_fraction = (
        total_area_pixels / image_area_pixels if image_area_pixels else float("nan")
    )
    rows: list[dict[str, object]] = []

    for object_id, contour in enumerate(contours, start=1):
        area_pixels = float(cv2.contourArea(contour))
        area_nm2 = area_pixels * nm_per_pixel**2
        equivalent_diameter_nm = (
            np.sqrt(4.0 * area_nm2 / np.pi) if area_nm2 > 0 else 0.0
        )
        perimeter_pixels = float(cv2.arcLength(contour, True))
        moments = cv2.moments(contour)
        centroid_x = (
            float(moments["m10"] / moments["m00"])
            if moments["m00"]
            else float("nan")
        )
        centroid_y = (
            float(moments["m01"] / moments["m00"])
            if moments["m00"]
            else float("nan")
        )
        region_mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.drawContours(region_mask, [contour], -1, 255, thickness=-1)
        mean_intensity = float(cv2.mean(gray, mask=region_mask)[0])
        rows.append(
            {
                "object_id": object_id,
                "area_pixels": area_pixels,
                "area_nm2": area_nm2,
                "equivalent_diameter_nm": equivalent_diameter_nm,
                "perimeter_pixels": perimeter_pixels,
                "perimeter_nm": perimeter_pixels * nm_per_pixel,
                "centroid_x_pixels": centroid_x,
                "centroid_y_pixels": centroid_y,
                "centroid_x_nm": centroid_x * nm_per_pixel,
                "centroid_y_nm": centroid_y * nm_per_pixel,
                "mean_intensity_raw": mean_intensity,
                "area_fraction": area_fraction,
                "nm_per_pixel": nm_per_pixel,
                "contrast_target": contrast_target,
                "touches_border": contour_touches_border(contour, gray.shape),
            }
        )
    return pd.DataFrame(rows, columns=_measurement_columns())


def analyze_tem(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    sample_id: str,
    nm_per_pixel: float,
    contrast_target: str,
    measurement_id: str | None = None,
    min_area_pixels: float = 5.0,
    gaussian_blur_kernel: int = 0,
    exclude_border_regions: bool = False,
    roi: tuple[int, int, int, int] | None = None,
    acquisition_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Run the conservative TEM contrast-region baseline workflow."""
    if not sample_id.strip():
        raise ValueError("sample_id must not be empty.")
    if nm_per_pixel <= 0:
        raise ValueError("nm_per_pixel must be greater than zero.")
    metadata = validate_tem_acquisition_metadata(acquisition_metadata)

    image = read_tem_image(input_path)
    gray = to_grayscale_preserve_dtype(image)
    roi_gray = crop_tem_roi(gray, roi)
    segmentation_image = prepare_tem_segmentation_image(
        roi_gray,
        gaussian_blur_kernel,
    )
    threshold_value, mask = threshold_tem_regions(
        segmentation_image,
        contrast_target,
    )
    contours, excluded_border_count = find_tem_regions(
        mask,
        min_area_pixels=min_area_pixels,
        exclude_border_regions=exclude_border_regions,
    )
    measurements = measure_tem_regions(
        contours,
        roi_gray,
        nm_per_pixel=nm_per_pixel,
        contrast_target=contrast_target,
    )

    steps = [
        PreprocessingStep(
            "tem-import",
            "image_decode_preserve_bit_depth",
            {"dtype": str(image.dtype), "shape": list(image.shape)},
        )
    ]
    if image.ndim == 3:
        steps.append(
            PreprocessingStep(
                "tem-grayscale",
                "bgr_or_bgra_to_grayscale",
                {"dtype_preserved": True},
            )
        )
    if roi is not None:
        steps.append(
            PreprocessingStep(
                "tem-roi",
                "explicit_roi_crop",
                {
                    "x": roi[0],
                    "y": roi[1],
                    "width": roi[2],
                    "height": roi[3],
                },
            )
        )
    steps.append(
        PreprocessingStep(
            "tem-segmentation-input",
            "gaussian_blur" if gaussian_blur_kernel else "no_blur",
            {"kernel": gaussian_blur_kernel},
        )
    )
    steps.append(
        PreprocessingStep(
            "tem-threshold",
            "otsu_threshold",
            {
                "contrast_target": contrast_target,
                "threshold_value_raw_units": threshold_value,
            },
        )
    )
    steps.append(
        PreprocessingStep(
            "tem-contours",
            "external_contour_measurement",
            {
                "minimum_area_pixels": min_area_pixels,
                "nm_per_pixel": nm_per_pixel,
                "exclude_border_regions": exclude_border_regions,
                "excluded_border_region_count": excluded_border_count,
            },
        )
    )

    measurement_id = measurement_id or f"{sample_id}-tem"
    preprocessing_id = preprocessing_fingerprint("tem", steps)
    features = build_tem_feature_records(
        measurements,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=input_path,
        preprocessing_id=preprocessing_id,
    )

    output_dir = ensure_output_dir(output_dir)
    measurements_path = output_dir / "tem_measurements.csv"
    mask_path = output_dir / "tem_segmentation_mask.png"
    overlay_path = output_dir / "tem_overlay.png"
    size_path = output_dir / "tem_region_size_distribution.png"
    intensity_path = output_dir / "tem_intensity_histogram.png"
    feature_path = output_dir / "tem_features_long.csv"

    measurements.to_csv(measurements_path, index=False)
    records_to_frame(features).to_csv(feature_path, index=False)
    save_tem_mask(mask, mask_path)
    save_tem_overlay(roi_gray, contours, overlay_path)
    save_tem_size_distribution(measurements, size_path)
    save_tem_intensity_histogram(roi_gray, intensity_path)

    metadata.update(
        {
            "nm_per_pixel": nm_per_pixel,
            "scale_source": "user_supplied_cli",
            "contrast_target": contrast_target,
            "roi": list(roi) if roi is not None else None,
            "image_dtype": str(image.dtype),
            "original_image_shape": list(image.shape),
            "analyzed_image_shape": list(roi_gray.shape),
        }
    )
    warnings = tem_warnings(
        metadata,
        exclude_border_regions=exclude_border_regions,
        excluded_border_count=excluded_border_count,
        detected_region_count=len(contours),
    )
    result = build_analysis_result(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument="tem",
        source_file=input_path,
        acquisition_metadata=metadata,
        preprocessing_steps=steps,
        tables={
            "measurements": measurements_path,
            "long_format_features": feature_path,
        },
        figures={
            "segmentation_mask": mask_path,
            "segmentation_overlay": overlay_path,
            "region_size_distribution": size_path,
            "intensity_histogram": intensity_path,
        },
        features=features,
        warnings=warnings,
        limitations=TEM_LIMITATIONS,
    )
    return {
        "image": image,
        "grayscale_image": gray,
        "analyzed_image": roi_gray,
        "mask": mask,
        "contours": contours,
        "measurements": measurements,
        "threshold_value": threshold_value,
        "excluded_border_region_count": excluded_border_count,
        "features": features,
        "analysis_result": result,
        "measurements_path": measurements_path,
        "mask_path": mask_path,
        "overlay_path": overlay_path,
        "size_distribution_path": size_path,
        "intensity_histogram_path": intensity_path,
        "feature_path": feature_path,
    }


def save_tem_mask(mask: np.ndarray, output_path: str | Path) -> Path:
    return _write_image(mask, output_path)


def save_tem_overlay(
    gray: np.ndarray,
    contours: list[np.ndarray],
    output_path: str | Path,
) -> Path:
    display = cv2.cvtColor(_display_uint8(gray), cv2.COLOR_GRAY2BGR)
    cv2.drawContours(display, contours, -1, (0, 255, 0), 1)
    return _write_image(display, output_path)


def save_tem_size_distribution(
    measurements: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    if measurements.empty:
        ax.text(0.5, 0.5, "No regions detected", ha="center", va="center")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        values = measurements["equivalent_diameter_nm"]
        ax.hist(values, bins=min(12, max(3, len(values))))
        ax.set_xlabel("Equivalent diameter (nm)")
        ax.set_ylabel("Detected region count")
    ax.set_title("TEM Threshold-Detected Region Size Distribution")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def save_tem_intensity_histogram(
    gray: np.ndarray,
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(gray.ravel(), bins=256)
    ax.set_xlabel("Raw digital intensity")
    ax.set_ylabel("Pixel count")
    ax.set_title("TEM Image Intensity Histogram")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def validate_tem_acquisition_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    values = dict(metadata or {})
    positive_fields = (
        "accelerating_voltage_kv",
        "magnification",
        "specimen_thickness_nm",
    )
    for field in positive_fields:
        value = values.get(field)
        if value is not None and float(value) <= 0:
            raise ValueError(f"{field} must be greater than zero when provided.")
    defocus_nm = values.get("defocus_nm")
    if defocus_nm is not None and not np.isfinite(float(defocus_nm)):
        raise ValueError("defocus_nm must be finite when provided.")
    imaging_mode = values.get("imaging_mode")
    allowed_modes = {
        None,
        "bf_tem",
        "df_tem",
        "stem",
        "haadf_stem",
        "hrtem",
        "other",
    }
    if imaging_mode not in allowed_modes:
        allowed_text = sorted(value for value in allowed_modes if value is not None)
        raise ValueError(f"imaging_mode must be one of {allowed_text}.")
    return values


def tem_warnings(
    metadata: dict[str, Any],
    *,
    exclude_border_regions: bool,
    excluded_border_count: int,
    detected_region_count: int,
) -> list[str]:
    warnings = [
        "automatic_threshold_segmentation_requires_manual_review",
        "contrast_regions_are_not_structural_assignments",
        "scale_is_user_supplied",
        "embedded_instrument_metadata_not_parsed",
    ]
    recommended = {
        "imaging_mode": "imaging_mode_not_provided",
        "accelerating_voltage_kv": "accelerating_voltage_not_provided",
        "magnification": "magnification_not_provided",
        "specimen_thickness_nm": "specimen_thickness_not_provided",
    }
    warnings.extend(
        message for field, message in recommended.items() if metadata.get(field) is None
    )
    if metadata.get("imaging_mode") == "hrtem":
        warnings.append("hrtem_lattice_information_not_analyzed")
    if exclude_border_regions and excluded_border_count:
        warnings.append("border_touching_regions_excluded")
    if detected_region_count == 0:
        warnings.append("no_regions_detected_with_current_parameters")
    return warnings


def _display_uint8(gray: np.ndarray) -> np.ndarray:
    if gray.dtype == np.uint8:
        return gray.copy()
    minimum = float(gray.min())
    maximum = float(gray.max())
    if maximum <= minimum:
        return np.zeros(gray.shape, dtype=np.uint8)
    return np.rint(
        (gray.astype(np.float64) - minimum) * 255.0 / (maximum - minimum)
    ).astype(np.uint8)


def _write_image(image: np.ndarray, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    success, encoded = cv2.imencode(output_path.suffix or ".png", image)
    if not success:
        raise ValueError(f"Could not encode image: {output_path}")
    encoded.tofile(output_path)
    return output_path


def _mask_max_value(dtype: np.dtype) -> int:
    return int(np.iinfo(dtype).max)


def _measurement_columns() -> list[str]:
    return [
        "object_id",
        "area_pixels",
        "area_nm2",
        "equivalent_diameter_nm",
        "perimeter_pixels",
        "perimeter_nm",
        "centroid_x_pixels",
        "centroid_y_pixels",
        "centroid_x_nm",
        "centroid_y_nm",
        "mean_intensity_raw",
        "area_fraction",
        "nm_per_pixel",
        "contrast_target",
        "touches_border",
    ]
