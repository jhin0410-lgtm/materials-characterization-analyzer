"""Command-line interface for conservative TGA and DSC baseline workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import write_analysis_manifest
from .thermal import analyze_thermal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca thermal",
        description=(
            "Analyze one monotonic TGA or DSC heating segment with explicit signal units "
            "and without reaction, phase-transition, or quantitative-composition assignment."
        ),
    )
    parser.add_argument("--input", required=True, help="Thermal CSV/TXT/TSV input.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--sample-id", default=None, help="Stable sample identifier; defaults to input stem.")
    parser.add_argument("--measurement-id", default=None, help="Optional stable measurement identifier.")
    parser.add_argument("--mode", choices=("tga", "dsc"), required=True)
    parser.add_argument(
        "--signal-type",
        choices=(
            "mass_percent",
            "mass_fraction",
            "mass_mg",
            "heat_flow_mw",
            "heat_flow_w_g",
        ),
        required=True,
        help="Explicit signal semantics; compatibility with --mode is validated.",
    )
    parser.add_argument("--initial-mass-mg", type=float, default=None, help="Optional TGA mass reference.")
    parser.add_argument(
        "--endotherm-direction",
        choices=("up", "down"),
        default="up",
        help="Required DSC plotting convention; ignored by TGA.",
    )
    parser.add_argument(
        "--baseline-method",
        choices=("none", "linear"),
        default=None,
        help="DSC baseline; defaults to linear for DSC and none for TGA.",
    )
    parser.add_argument("--smoothing-window", type=int, default=11)
    parser.add_argument("--smoothing-polyorder", type=int, default=3)
    parser.add_argument("--prominence-fraction", type=float, default=0.08)
    parser.add_argument("--min-distance", type=int, default=5, help="Minimum candidate distance in samples.")

    metadata = parser.add_argument_group("optional thermal-program and acquisition metadata")
    metadata.add_argument("--atmosphere", default=None)
    metadata.add_argument("--heating-rate-c-min", type=float, default=None)
    metadata.add_argument("--gas-flow-ml-min", type=float, default=None)
    metadata.add_argument("--sample-mass-mg", type=float, default=None)
    metadata.add_argument("--crucible-material", default=None)
    metadata.add_argument("--instrument-model", default=None)
    metadata.add_argument("--calibration-reference", default=None)
    metadata.add_argument("--sample-preparation", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_id = args.sample_id or Path(args.input).stem
    baseline_method = args.baseline_method or ("none" if args.mode == "tga" else "linear")
    metadata = {
        "atmosphere": args.atmosphere,
        "heating_rate_c_min": args.heating_rate_c_min,
        "gas_flow_ml_min": args.gas_flow_ml_min,
        "sample_mass_mg": args.sample_mass_mg,
        "crucible_material": args.crucible_material,
        "instrument_model": args.instrument_model,
        "calibration_reference": args.calibration_reference,
        "sample_preparation": args.sample_preparation,
    }
    result = analyze_thermal(
        args.input,
        args.output,
        sample_id=sample_id,
        measurement_id=args.measurement_id,
        mode=args.mode,
        signal_type=args.signal_type,
        initial_mass_mg=args.initial_mass_mg,
        endotherm_direction=args.endotherm_direction,
        baseline_method=baseline_method,
        smoothing_window=args.smoothing_window,
        smoothing_polyorder=args.smoothing_polyorder,
        prominence_fraction=args.prominence_fraction,
        min_distance=args.min_distance,
        acquisition_metadata=metadata,
    )
    manifest_path = write_analysis_manifest(
        [result["analysis_result"]],
        Path(args.output) / "thermal_analysis_manifest.json",
    )
    print(f"Saved thermal plot: {result['plot_path']}")
    print(f"Saved thermal processed data: {result['processed_data_path']}")
    print(f"Saved thermal event candidates: {result['candidate_table_path']}")
    print(f"Saved thermal long-format features: {result['feature_path']}")
    print(f"Saved thermal analysis manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
