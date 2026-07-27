"""Generate an explicitly synthetic SAED-like image for software demonstrations."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def generate_synthetic_saed(
    output_path: str | Path,
    *,
    size: int = 257,
    center_x_px: float = 128.0,
    center_y_px: float = 128.0,
) -> Path:
    if size < 64:
        raise ValueError("size must be at least 64 pixels.")
    yy, xx = np.indices((size, size), dtype=float)
    radius = np.hypot(xx - center_x_px, yy - center_y_px)

    image = np.full((size, size), 1200.0)
    image += 9000.0 * np.exp(-0.5 * (radius / 2.5) ** 2)
    for ring_radius, amplitude, width in (
        (35.0, 15000.0, 1.8),
        (70.0, 11000.0, 2.2),
        (105.0, 8000.0, 2.8),
    ):
        image += amplitude * np.exp(-0.5 * ((radius - ring_radius) / width) ** 2)

    rng = np.random.default_rng(42)
    image += rng.normal(0.0, 120.0, image.shape)
    image = np.clip(image, 0, np.iinfo(np.uint16).max).astype(np.uint16)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise OSError(f"Failed to save synthetic SAED image: {output_path}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, default=257)
    parser.add_argument("--center-x-px", type=float, default=128.0)
    parser.add_argument("--center-y-px", type=float, default=128.0)
    args = parser.parse_args()
    path = generate_synthetic_saed(
        args.output,
        size=args.size,
        center_x_px=args.center_x_px,
        center_y_px=args.center_y_px,
    )
    print(f"Saved synthetic SAED-like image: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
