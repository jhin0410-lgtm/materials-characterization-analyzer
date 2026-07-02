"""Command line interface for Materials Characterization Analyzer."""

from __future__ import annotations

import argparse

from .eds import analyze_eds
from .report import generate_report
from .sem import analyze_sem
from .xrd import analyze_xrd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca",
        description="Analyze XRD, SEM, and EDS data and generate cautious materials characterization summaries.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    xrd_parser = subparsers.add_parser("xrd", help="Analyze an XRD 2-column file.")
    xrd_parser.add_argument("--input", required=True, help="Input XRD file (.csv, .txt, .xy) with 2theta/intensity columns.")
    xrd_parser.add_argument("--output", required=True, help="Output directory.")
    xrd_parser.add_argument("--smoothing-window", type=int, default=11, help="Savitzky-Golay smoothing window.")
    xrd_parser.add_argument("--smoothing-polyorder", type=int, default=3, help="Savitzky-Golay polynomial order.")
    xrd_parser.add_argument("--prominence-fraction", type=float, default=0.05, help="Peak prominence as a fraction of intensity range.")
    xrd_parser.add_argument("--min-distance", type=int, default=3, help="Minimum peak distance in samples.")
    xrd_parser.add_argument("--wavelength", type=float, default=None, help="Optional X-ray wavelength for Scherrer estimates.")
    xrd_parser.add_argument("--shape-factor", type=float, default=0.9, help="Scherrer shape factor.")
    xrd_parser.add_argument(
        "--instrumental-broadening",
        type=float,
        default=0.0,
        help="Optional instrumental broadening in degrees 2theta.",
    )
    xrd_parser.set_defaults(func=_run_xrd)

    sem_parser = subparsers.add_parser("sem", help="Analyze an SEM image with threshold-based segmentation.")
    sem_parser.add_argument("--input", required=True, help="Input SEM image path.")
    sem_parser.add_argument("--microns-per-pixel", type=float, required=True, help="Manual image scale.")
    sem_parser.add_argument("--output", required=True, help="Output directory.")
    sem_parser.add_argument("--min-area-pixels", type=float, default=5.0, help="Minimum contour area in pixels.")
    sem_parser.add_argument("--invert", action="store_true", help="Detect dark regions instead of bright regions.")
    sem_parser.set_defaults(func=_run_sem)

    eds_parser = subparsers.add_parser("eds", help="Analyze an EDS composition CSV file.")
    eds_parser.add_argument("--input", required=True, help="Input EDS CSV with element, weight percent, and atomic percent columns.")
    eds_parser.add_argument("--output", required=True, help="Output directory.")
    eds_parser.set_defaults(func=_run_eds)

    report_parser = subparsers.add_parser("report", help="Generate an integrated Markdown report.")
    report_parser.add_argument("--xrd", required=True, help="XRD peak table CSV.")
    report_parser.add_argument("--sem", required=True, help="SEM measurements CSV.")
    report_parser.add_argument("--eds", required=True, help="EDS composition table CSV.")
    report_parser.add_argument("--output", required=True, help="Output directory.")
    report_parser.add_argument("--sample-name", default="Demo or user-provided sample", help="Sample name for the report.")
    report_parser.set_defaults(func=_run_report)

    all_parser = subparsers.add_parser("analyze-all", help="Run XRD, SEM, EDS, and report generation.")
    all_parser.add_argument("--xrd", required=True, help="Input XRD file (.csv, .txt, .xy).")
    all_parser.add_argument("--sem", required=True, help="Input SEM image.")
    all_parser.add_argument("--eds", required=True, help="Input EDS composition CSV.")
    all_parser.add_argument("--microns-per-pixel", type=float, required=True, help="Manual SEM image scale.")
    all_parser.add_argument("--output", required=True, help="Output directory.")
    all_parser.add_argument("--sample-name", default="Demo or user-provided sample", help="Sample name for the report.")
    all_parser.add_argument("--invert-sem", action="store_true", help="Detect dark SEM regions instead of bright regions.")
    all_parser.add_argument("--xrd-wavelength", type=float, default=None, help="Optional X-ray wavelength for Scherrer estimates.")
    all_parser.add_argument("--shape-factor", type=float, default=0.9, help="Scherrer shape factor.")
    all_parser.set_defaults(func=_run_analyze_all)

    return parser


def _run_xrd(args: argparse.Namespace) -> int:
    result = analyze_xrd(
        args.input,
        args.output,
        smoothing_window=args.smoothing_window,
        smoothing_polyorder=args.smoothing_polyorder,
        prominence_fraction=args.prominence_fraction,
        min_distance=args.min_distance,
        wavelength=args.wavelength,
        shape_factor=args.shape_factor,
        instrumental_broadening_deg=args.instrumental_broadening,
    )
    print(f"Saved XRD plot: {result['plot_path']}")
    print(f"Saved XRD peak table: {result['peak_table_path']}")
    return 0


def _run_sem(args: argparse.Namespace) -> int:
    result = analyze_sem(
        args.input,
        args.output,
        microns_per_pixel=args.microns_per_pixel,
        min_area_pixels=args.min_area_pixels,
        invert=args.invert,
    )
    print(f"Saved SEM overlay: {result['overlay_path']}")
    print(f"Saved SEM histogram: {result['histogram_path']}")
    print(f"Saved SEM measurements: {result['measurements_path']}")
    return 0


def _run_eds(args: argparse.Namespace) -> int:
    result = analyze_eds(args.input, args.output)
    print(f"Saved EDS table: {result['table_path']}")
    print(f"Saved EDS chart: {result['chart_path']}")
    return 0


def _run_report(args: argparse.Namespace) -> int:
    report_path = generate_report(args.xrd, args.sem, args.eds, args.output, sample_name=args.sample_name)
    print(f"Saved report: {report_path}")
    return 0


def _run_analyze_all(args: argparse.Namespace) -> int:
    xrd_result = analyze_xrd(
        args.xrd,
        args.output,
        wavelength=args.xrd_wavelength,
        shape_factor=args.shape_factor,
    )
    sem_result = analyze_sem(
        args.sem,
        args.output,
        microns_per_pixel=args.microns_per_pixel,
        invert=args.invert_sem,
    )
    eds_result = analyze_eds(args.eds, args.output)
    report_path = generate_report(
        xrd_result["peak_table_path"],
        sem_result["measurements_path"],
        eds_result["table_path"],
        args.output,
        sample_name=args.sample_name,
    )

    print(f"Saved XRD plot: {xrd_result['plot_path']}")
    print(f"Saved SEM overlay: {sem_result['overlay_path']}")
    print(f"Saved EDS chart: {eds_result['chart_path']}")
    print(f"Saved report: {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
