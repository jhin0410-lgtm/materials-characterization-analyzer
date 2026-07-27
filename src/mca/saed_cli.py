"""Command-line interface for the conservative SAED baseline workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import write_analysis_manifest
from .saed import analyze_saed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca saed",
        description=(
            "Analyze a SAED image using radial candidate detection without phase "
            "indexing or automatic crystallographic assignment."
        ),
    )
    parser.add_argument("--input", required=True, help="SAED image (.png, .tif, .tiff, .bmp).")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--sample-id", default=None, help="Stable sample identifier; defaults to input stem.")
    parser.add_argument("--measurement-id", default=None, help="Optional stable measurement identifier.")
    parser.add_argument("--center-x-px", type=float, default=None)
    parser.add_argument("--center-y-px", type=float, default=None)
    parser.add_argument("--bin-width-px", type=float, default=1.0)
    parser.add_argument("--min-radius-px", type=float, default=5.0)
    parser.add_argument("--max-radius-px", type=float, default=None)
    parser.add_argument("--ring-contrast", choices=("bright", "dark"), default="bright")
    parser.add_argument("--smoothing-window", type=int, default=7, help="Savitzky-Golay window; 0 disables smoothing.")
    parser.add_argument("--smoothing-polyorder", type=int, default=2)
    parser.add_argument("--prominence-fraction", type=float, default=0.05)
    parser.add_argument("--min-distance-px", type=float, default=5.0)

    calibration = parser.add_argument_group("calibration")
    calibration.add_argument(
        "--reciprocal-nm-inv-per-pixel",
        type=float,
        default=None,
        help="Direct reciprocal calibration using g=1/d in nm^-1 per pixel.",
    )
    calibration.add_argument(
        "--camera-constant-nm-pixel",
        type=float,
        default=None,
        help="Calibrated K in nm*pixel, where d_nm = K / radius_px.",
    )
    calibration.add_argument("--reference-d-nm", type=float, default=None)
    calibration.add_argument("--reference-radius-px", type=float, default=None)

    metadata = parser.add_argument_group("optional acquisition metadata")
    metadata.add_argument("--accelerating-voltage-kv", type=float, default=None)
    metadata.add_argument("--camera-length-mm", type=float, default=None)
    metadata.add_argument("--detector-pixel-size-um", type=float, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_id = args.sample_id or Path(args.input).stem
    result = analyze_saed(
        args.input,
        args.output,
        sample_id=sample_id,
        measurement_id=args.measurement_id,
        center_x_px=args.center_x_px,
        center_y_px=args.center_y_px,
        bin_width_px=args.bin_width_px,
        min_radius_px=args.min_radius_px,
        max_radius_px=args.max_radius_px,
        ring_contrast=args.ring_contrast,
        smoothing_window=args.smoothing_window,
        smoothing_polyorder=args.smoothing_polyorder,
        prominence_fraction=args.prominence_fraction,
        min_distance_px=args.min_distance_px,
        reciprocal_nm_inv_per_pixel=args.reciprocal_nm_inv_per_pixel,
        camera_constant_nm_pixel=args.camera_constant_nm_pixel,
        reference_d_nm=args.reference_d_nm,
        reference_radius_px=args.reference_radius_px,
        acquisition_metadata={
            "accelerating_voltage_kv": args.accelerating_voltage_kv,
            "camera_length_mm": args.camera_length_mm,
            "detector_pixel_size_um": args.detector_pixel_size_um,
        },
    )
    manifest_path = write_analysis_manifest(
        [result["analysis_result"]],
        Path(args.output) / "saed_analysis_manifest.json",
    )
    print(f"Saved SAED radial profile: {result['radial_profile_path']}")
    print(f"Saved SAED ring candidates: {result['ring_candidates_path']}")
    print(f"Saved SAED long-format features: {result['feature_path']}")
    print(f"Saved SAED radial profile plot: {result['radial_profile_plot_path']}")
    print(f"Saved SAED ring overlay: {result['overlay_path']}")
    print(f"Saved SAED analysis manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
