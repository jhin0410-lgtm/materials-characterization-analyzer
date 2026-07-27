"""Generate a deterministic synthetic TEM-like image for software demonstration only."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="outputs/synthetic_tem_demo.png",
        help="Output image path.",
    )
    args = parser.parse_args()

    height, width = 256, 320
    y, x = np.mgrid[0:height, 0:width]
    image = (900 + 0.8 * x + 0.4 * y).astype(np.uint16)
    cv2.circle(image, (80, 80), 24, 5000, -1)
    cv2.ellipse(image, (210, 150), (38, 20), 25, 0, 360, 3800, -1)
    cv2.circle(image, (280, 55), 14, 4300, -1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(output.suffix or ".png", image)
    if not success:
        raise ValueError(f"Could not encode synthetic image: {output}")
    encoded.tofile(output)
    print(f"Saved synthetic TEM-like demo image: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
