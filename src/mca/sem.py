"""Threshold-based SEM image analysis helpers for v0.1."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mca_matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .utils import ensure_output_dir


def read_sem_image(path: str | Path) -> np.ndarray:
    """Read an SEM image using OpenCV."""
    path = Path(path)
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read SEM image: {path}")
    return image


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR or grayscale image to grayscale."""
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def threshold_image(gray: np.ndarray, invert: bool = False) -> np.ndarray:
    """Apply Otsu thresholding for simple particle or pore segmentation."""
    blur = gray
    if min(gray.shape[:2]) >= 5:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
    threshold_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _, binary = cv2.threshold(blur, 0, 255, threshold_type | cv2.THRESH_OTSU)
    return binary


def find_sem_regions(binary: np.ndarray, min_area_pixels: float = 5.0) -> list[np.ndarray]:
    """Find external contours above a minimum pixel area."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [contour for contour in contours if cv2.contourArea(contour) >= min_area_pixels]


def measure_regions(
    contours: list[np.ndarray],
    image_shape: tuple[int, ...],
    microns_per_pixel: float,
) -> pd.DataFrame:
    """Measure area fraction and equivalent diameter for detected regions."""
    if microns_per_pixel <= 0:
        raise ValueError("microns_per_pixel must be greater than zero.")

    height, width = image_shape[:2]
    image_area_pixels = float(height * width)
    total_area_pixels = float(sum(cv2.contourArea(contour) for contour in contours))
    area_fraction = total_area_pixels / image_area_pixels if image_area_pixels else float("nan")

    rows = []
    for index, contour in enumerate(contours, start=1):
        area_pixels = float(cv2.contourArea(contour))
        area_microns2 = area_pixels * microns_per_pixel**2
        equivalent_diameter = np.sqrt(4.0 * area_microns2 / np.pi) if area_microns2 > 0 else 0.0
        rows.append(
            {
                "object_id": index,
                "area_pixels": area_pixels,
                "area_microns2": area_microns2,
                "equivalent_diameter_microns": equivalent_diameter,
                "perimeter_pixels": float(cv2.arcLength(contour, True)),
                "area_fraction": area_fraction,
                "microns_per_pixel": microns_per_pixel,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "object_id",
            "area_pixels",
            "area_microns2",
            "equivalent_diameter_microns",
            "perimeter_pixels",
            "area_fraction",
            "microns_per_pixel",
        ],
    )


def save_overlay(image: np.ndarray, contours: list[np.ndarray], output_path: str | Path) -> Path:
    """Save a contour overlay on top of the original SEM image."""
    output_path = Path(output_path)
    overlay = image.copy()
    cv2.drawContours(overlay, contours, contourIdx=-1, color=(0, 255, 0), thickness=1)
    success, encoded = cv2.imencode(output_path.suffix or ".png", overlay)
    if not success:
        raise ValueError(f"Could not encode SEM overlay image: {output_path}")
    encoded.tofile(output_path)
    return output_path


def save_size_distribution(measurements: pd.DataFrame, output_path: str | Path) -> Path:
    """Save a histogram of equivalent diameter values."""
    output_path = Path(output_path)
    fig, ax = plt.subplots(figsize=(7, 4.5))

    if measurements.empty:
        ax.text(0.5, 0.5, "No regions detected", ha="center", va="center")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        values = measurements["equivalent_diameter_microns"]
        bins = min(12, max(3, len(values)))
        ax.hist(values, bins=bins, color="#457b9d", edgecolor="white")
        ax.set_xlabel("Equivalent diameter (microns)")
        ax.set_ylabel("Count")

    ax.set_title("SEM Particle/Pore Size Distribution")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def analyze_sem(
    input_path: str | Path,
    output_dir: str | Path,
    microns_per_pixel: float,
    min_area_pixels: float = 5.0,
    invert: bool = False,
) -> dict[str, object]:
    """Run the v0.1 threshold-based SEM workflow."""
    output_dir = ensure_output_dir(output_dir)
    image = read_sem_image(input_path)
    gray = to_grayscale(image)
    binary = threshold_image(gray, invert=invert)
    contours = find_sem_regions(binary, min_area_pixels=min_area_pixels)
    measurements = measure_regions(contours, gray.shape, microns_per_pixel)

    overlay_path = output_dir / "sem_overlay.png"
    histogram_path = output_dir / "sem_particle_size_distribution.png"
    measurements_path = output_dir / "sem_measurements.csv"

    save_overlay(image, contours, overlay_path)
    save_size_distribution(measurements, histogram_path)
    measurements.to_csv(measurements_path, index=False)

    return {
        "measurements": measurements,
        "contours": contours,
        "overlay_path": overlay_path,
        "histogram_path": histogram_path,
        "measurements_path": measurements_path,
    }

