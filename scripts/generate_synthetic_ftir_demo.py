"""Generate a deterministic synthetic FTIR transmittance spectrum for software tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def build_synthetic_ftir() -> pd.DataFrame:
    wavenumber = np.linspace(4000.0, 400.0, 1801)
    baseline = 0.035 + 0.000008 * (4000.0 - wavenumber)
    absorbance = baseline.copy()
    for center, amplitude, sigma in (
        (3300.0, 0.40, 95.0),
        (1715.0, 0.75, 28.0),
        (1100.0, 0.50, 38.0),
    ):
        absorbance += amplitude * np.exp(-0.5 * ((wavenumber - center) / sigma) ** 2)
    transmittance_percent = 100.0 * np.power(10.0, -absorbance)
    return pd.DataFrame(
        {
            "wavenumber_cm_1": wavenumber,
            "transmittance_percent": transmittance_percent,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    build_synthetic_ftir().to_csv(output, index=False)
    print(f"Saved synthetic FTIR fixture: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
