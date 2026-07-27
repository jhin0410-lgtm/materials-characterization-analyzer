"""Command-line interface for the Raman baseline workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import write_analysis_manifest
from .raman import analyze_raman


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca raman",
        description="Analyze a two-column Raman spectrum without automatic band or material assignment.",
    )
    parser.add_argument("--input", required=True, help="Raman CSV/TXT/TSV with shift in cm^-1 and intensity.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--sample-id", default=None, help="Stable sample identifier; defaults to the input stem.")
    parser.add_argument("--measurement-id", default=None, help="Optional stable measurement identifier.")
    parser.add_argument("--baseline-method", choices=("asls", "none"), default="asls")
    parser.add_argument("--baseline-smoothness", type=float, default=1_000_000.0)
    parser.add_argument("--baseline-asymmetry", type=float, default=0.01)
    parser.add_argument("--baseline-iterations", type=int, default=15)
    parser.add_argument("--smoothing-window", type=int, default=11, help="Savitzky-Golay window; 0 disables smoothing.")
    parser.add_argument("--smoothing-polyorder", type=int, default=3)
    parser.add_argument("--prominence-fraction", type=float, default=0.05)
    parser.add_argument("--min-distance", type=int, default=3, help="Minimum detected-peak distance in samples.")
    parser.add_argument("--laser-wavelength-nm", type=float, default=None)
    parser.add_argument("--laser-power-mw", type=float, default=None)
    parser.add_argument("--exposure-time-s", type=float, default=None)
    parser.add_argument("--accumulation-count", type=int, default=None)
    parser.add_argument("--spectral-resolution-cm-1", type=float, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_id = args.sample_id or Path(args.input).stem
    metadata = {
        "laser_wavelength_nm": args.laser_wavelength_nm,
        "laser_power_mw": args.laser_power_mw,
        "exposure_time_s": args.exposure_time_s,
        "accumulation_count": args.accumulation_count,
        "spectral_resolution_cm_1": args.spectral_resolution_cm_1,
    }
    result = analyze_raman(
        args.input,
        args.output,
        sample_id=sample_id,
        measurement_id=args.measurement_id,
        baseline_method=args.baseline_method,
        baseline_smoothness=args.baseline_smoothness,
        baseline_asymmetry=args.baseline_asymmetry,
        baseline_iterations=args.baseline_iterations,
        smoothing_window=args.smoothing_window,
        smoothing_polyorder=args.smoothing_polyorder,
        prominence_fraction=args.prominence_fraction,
        min_distance=args.min_distance,
        acquisition_metadata=metadata,
    )
    manifest_path = write_analysis_manifest(
        [result["analysis_result"]],
        Path(args.output) / "raman_analysis_manifest.json",
    )
    print(f"Saved Raman plot: {result['plot_path']}")
    print(f"Saved Raman processed spectrum: {result['processed_spectrum_path']}")
    print(f"Saved Raman peak table: {result['peak_table_path']}")
    print(f"Saved Raman long-format features: {result['feature_path']}")
    print(f"Saved Raman analysis manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
