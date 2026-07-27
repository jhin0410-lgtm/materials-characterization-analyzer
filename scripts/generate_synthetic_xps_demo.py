"""Generate a deterministic synthetic XPS-like survey spectrum for software demos.

The output is artificial and must not be described as experimental or instrument data.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a synthetic XPS-like two-column CSV.")
    parser.add_argument("--output", required=True, help="Destination CSV path.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--points", type=int, default=1601)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.points < 101:
        raise ValueError("points must be at least 101.")

    energy = np.linspace(0.0, 800.0, args.points)
    background = 40.0 + 0.03 * energy
    candidates = (
        80.0 * np.exp(-0.5 * ((energy - 74.0) / 2.5) ** 2)
        + 150.0 * np.exp(-0.5 * ((energy - 285.0) / 3.5) ** 2)
        + 120.0 * np.exp(-0.5 * ((energy - 532.0) / 4.5) ** 2)
    )
    noise = np.random.default_rng(args.seed).normal(0.0, 0.8, len(energy))
    intensity = background + candidates + noise

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "binding_energy_ev": energy[::-1],
            "intensity": intensity[::-1],
        }
    ).to_csv(output, index=False)
    print(f"Saved synthetic XPS-like spectrum: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
