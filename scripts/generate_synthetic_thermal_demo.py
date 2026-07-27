"""Generate deterministic synthetic TGA or DSC data for software demonstration only."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("tga", "dsc"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--heating-rate-c-min", type=float, default=10.0)
    return parser


def generate(mode: str, heating_rate_c_min: float) -> pd.DataFrame:
    if heating_rate_c_min <= 0:
        raise ValueError("heating_rate_c_min must be positive.")
    if mode == "tga":
        temperature = np.linspace(30.0, 800.0, 1200)
        signal = 100.0
        signal -= 8.0 / (1.0 + np.exp(-(temperature - 180.0) / 8.0))
        signal -= 22.0 / (1.0 + np.exp(-(temperature - 420.0) / 12.0))
        signal -= 15.0 / (1.0 + np.exp(-(temperature - 650.0) / 10.0))
    else:
        temperature = np.linspace(30.0, 450.0, 1000)
        signal = 0.0007 * (temperature - 30.0)
        signal += 2.4 * np.exp(-0.5 * ((temperature - 155.0) / 8.0) ** 2)
        signal -= 1.8 * np.exp(-0.5 * ((temperature - 305.0) / 11.0) ** 2)
    time_s = (temperature - temperature[0]) / heating_rate_c_min * 60.0
    return pd.DataFrame({"temperature_c": temperature, "time_s": time_s, "signal": signal})


def main() -> int:
    args = build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    generate(args.mode, args.heating_rate_c_min).to_csv(output, index=False)
    print(f"Saved synthetic {args.mode.upper()}-like data: {output}")
    print("Synthetic data validate software behavior only; they are not experimental evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
