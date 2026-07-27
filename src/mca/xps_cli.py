"""Command-line interface for the conservative XPS spectrum baseline workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import write_analysis_manifest
from .xps import analyze_xps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca xps",
        description=(
            "Analyze a two-column XPS spectrum with explicit energy referencing and "
            "without elemental, chemical-state, or quantitative-composition assignment."
        ),
    )
    parser.add_argument("--input", required=True, help="XPS CSV/TXT/TSV with binding energy in eV and intensity.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--sample-id", default=None, help="Stable sample identifier; defaults to the input stem.")
    parser.add_argument("--measurement-id", default=None, help="Optional stable measurement identifier.")
    parser.add_argument("--spectrum-type", choices=("survey", "high_resolution", "unknown"), default="unknown")
    parser.add_argument("--region-label", default=None, help="Optional user-supplied region label such as survey or C 1s.")
    parser.add_argument("--background-method", choices=("shirley", "linear", "none"), default="shirley")
    parser.add_argument("--shirley-iterations", type=int, default=100)
    parser.add_argument("--shirley-tolerance", type=float, default=1e-6)
    parser.add_argument("--smoothing-window", type=int, default=0, help="Savitzky-Golay window; 0 disables smoothing.")
    parser.add_argument("--smoothing-polyorder", type=int, default=3)
    parser.add_argument("--prominence-fraction", type=float, default=0.05)
    parser.add_argument("--min-distance", type=int, default=3, help="Minimum candidate distance in samples.")

    reference = parser.add_argument_group("explicit energy referencing")
    reference.add_argument("--energy-shift-ev", type=float, default=None)
    reference.add_argument("--reference-observed-ev", type=float, default=None)
    reference.add_argument("--reference-target-ev", type=float, default=None)

    metadata = parser.add_argument_group("optional acquisition metadata")
    metadata.add_argument("--xray-source", default=None)
    metadata.add_argument("--photon-energy-ev", type=float, default=None)
    metadata.add_argument("--pass-energy-ev", type=float, default=None)
    metadata.add_argument("--step-size-ev", type=float, default=None)
    metadata.add_argument("--dwell-time-s", type=float, default=None)
    metadata.add_argument("--scan-count", type=int, default=None)
    metadata.add_argument("--takeoff-angle-deg", type=float, default=None)
    metadata.add_argument("--charge-neutralization", choices=("on", "off", "unknown"), default="unknown")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_id = args.sample_id or Path(args.input).stem
    metadata = {
        "spectrum_type": args.spectrum_type,
        "region_label": args.region_label,
        "xray_source": args.xray_source,
        "photon_energy_ev": args.photon_energy_ev,
        "pass_energy_ev": args.pass_energy_ev,
        "step_size_ev": args.step_size_ev,
        "dwell_time_s": args.dwell_time_s,
        "scan_count": args.scan_count,
        "takeoff_angle_deg": args.takeoff_angle_deg,
        "charge_neutralization": args.charge_neutralization,
    }
    result = analyze_xps(
        args.input,
        args.output,
        sample_id=sample_id,
        measurement_id=args.measurement_id,
        background_method=args.background_method,
        shirley_iterations=args.shirley_iterations,
        shirley_tolerance=args.shirley_tolerance,
        smoothing_window=args.smoothing_window,
        smoothing_polyorder=args.smoothing_polyorder,
        prominence_fraction=args.prominence_fraction,
        min_distance=args.min_distance,
        energy_shift_ev=args.energy_shift_ev,
        reference_observed_ev=args.reference_observed_ev,
        reference_target_ev=args.reference_target_ev,
        acquisition_metadata=metadata,
    )
    manifest_path = write_analysis_manifest(
        [result["analysis_result"]],
        Path(args.output) / "xps_analysis_manifest.json",
    )
    print(f"Saved XPS plot: {result['plot_path']}")
    print(f"Saved XPS processed spectrum: {result['processed_spectrum_path']}")
    print(f"Saved XPS peak candidates: {result['candidate_table_path']}")
    print(f"Saved XPS long-format features: {result['feature_path']}")
    print(f"Saved XPS analysis manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
