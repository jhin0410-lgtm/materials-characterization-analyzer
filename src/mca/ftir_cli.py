"""Command-line interface for the conservative FTIR spectrum baseline workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import write_analysis_manifest
from .ftir import analyze_ftir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca ftir",
        description=(
            "Analyze a two-column FTIR spectrum with explicit signal semantics and "
            "without functional-group, compound, phase, or quantitative assignment."
        ),
    )
    parser.add_argument("--input", required=True, help="FTIR CSV/TXT/TSV with wavenumber in cm^-1 and signal.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--sample-id", default=None, help="Stable sample identifier; defaults to the input stem.")
    parser.add_argument("--measurement-id", default=None, help="Optional stable measurement identifier.")
    parser.add_argument(
        "--signal-type",
        required=True,
        choices=("absorbance", "transmittance_percent", "transmittance_fraction"),
        help="Explicit semantics of the input signal column.",
    )
    parser.add_argument("--baseline-method", choices=("none", "linear", "asls"), default="none")
    parser.add_argument("--baseline-smoothness", type=float, default=1_000_000.0)
    parser.add_argument("--baseline-asymmetry", type=float, default=0.01)
    parser.add_argument("--baseline-iterations", type=int, default=15)
    parser.add_argument("--smoothing-window", type=int, default=0, help="Savitzky-Golay window; 0 disables smoothing.")
    parser.add_argument("--smoothing-polyorder", type=int, default=3)
    parser.add_argument("--prominence-fraction", type=float, default=0.05)
    parser.add_argument("--min-distance", type=int, default=3, help="Minimum candidate distance in samples.")

    metadata = parser.add_argument_group("optional acquisition metadata")
    metadata.add_argument(
        "--sampling-mode",
        choices=("transmission", "atr", "diffuse_reflectance", "specular_reflectance", "unknown"),
        default="unknown",
    )
    metadata.add_argument("--spectral-resolution-cm-1", type=float, default=None)
    metadata.add_argument("--scan-count", type=int, default=None)
    metadata.add_argument("--detector", default=None)
    metadata.add_argument("--beamsplitter", default=None)
    metadata.add_argument("--apodization", default=None)
    metadata.add_argument("--atr-crystal", default=None)
    metadata.add_argument("--path-length-um", type=float, default=None)
    metadata.add_argument("--background-description", default=None)
    metadata.add_argument("--sample-preparation", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_id = args.sample_id or Path(args.input).stem
    metadata = {
        "sampling_mode": args.sampling_mode,
        "spectral_resolution_cm_1": args.spectral_resolution_cm_1,
        "scan_count": args.scan_count,
        "detector": args.detector,
        "beamsplitter": args.beamsplitter,
        "apodization": args.apodization,
        "atr_crystal": args.atr_crystal,
        "path_length_um": args.path_length_um,
        "background_description": args.background_description,
        "sample_preparation": args.sample_preparation,
    }
    result = analyze_ftir(
        args.input,
        args.output,
        sample_id=sample_id,
        measurement_id=args.measurement_id,
        signal_type=args.signal_type,
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
        Path(args.output) / "ftir_analysis_manifest.json",
    )
    print(f"Saved FTIR plot: {result['plot_path']}")
    print(f"Saved FTIR processed spectrum: {result['processed_spectrum_path']}")
    print(f"Saved FTIR band candidates: {result['candidate_table_path']}")
    print(f"Saved FTIR long-format features: {result['feature_path']}")
    print(f"Saved FTIR analysis manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
