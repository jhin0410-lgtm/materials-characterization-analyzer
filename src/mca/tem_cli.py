"""Command-line interface for the conservative TEM image baseline workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import write_analysis_manifest
from .tem import analyze_tem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca tem",
        description=(
            "Analyze explicitly selected bright or dark TEM contrast regions without "
            "automatic particle, phase, defect, SAED, or lattice assignment."
        ),
    )
    parser.add_argument("--input", required=True, help="TEM PNG/JPEG/TIFF/BMP/PGM image.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument(
        "--sample-id",
        default=None,
        help="Stable sample identifier; defaults to the input stem.",
    )
    parser.add_argument("--measurement-id", default=None)
    parser.add_argument(
        "--nm-per-pixel",
        required=True,
        type=float,
        help="User-verified image scale in nm per pixel.",
    )
    parser.add_argument("--contrast-target", required=True, choices=("bright", "dark"))
    parser.add_argument("--min-area-pixels", type=float, default=5.0)
    parser.add_argument(
        "--gaussian-blur-kernel",
        type=int,
        default=0,
        help="0 disables blur; otherwise use an odd integer >= 3.",
    )
    parser.add_argument("--exclude-border-regions", action="store_true")
    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        metavar=("X", "Y", "WIDTH", "HEIGHT"),
        default=None,
        help="Optional explicit pixel ROI.",
    )
    parser.add_argument(
        "--imaging-mode",
        choices=("bf_tem", "df_tem", "stem", "haadf_stem", "hrtem", "other"),
        default=None,
    )
    parser.add_argument("--accelerating-voltage-kv", type=float, default=None)
    parser.add_argument("--magnification", type=float, default=None)
    parser.add_argument("--specimen-thickness-nm", type=float, default=None)
    parser.add_argument(
        "--defocus-nm",
        type=float,
        default=None,
        help="Signed defocus value when known.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_id = args.sample_id or Path(args.input).stem
    metadata = {
        "imaging_mode": args.imaging_mode,
        "accelerating_voltage_kv": args.accelerating_voltage_kv,
        "magnification": args.magnification,
        "specimen_thickness_nm": args.specimen_thickness_nm,
        "defocus_nm": args.defocus_nm,
    }
    result = analyze_tem(
        args.input,
        args.output,
        sample_id=sample_id,
        measurement_id=args.measurement_id,
        nm_per_pixel=args.nm_per_pixel,
        contrast_target=args.contrast_target,
        min_area_pixels=args.min_area_pixels,
        gaussian_blur_kernel=args.gaussian_blur_kernel,
        exclude_border_regions=args.exclude_border_regions,
        roi=tuple(args.roi) if args.roi is not None else None,
        acquisition_metadata=metadata,
    )
    manifest_path = write_analysis_manifest(
        [result["analysis_result"]],
        Path(args.output) / "tem_analysis_manifest.json",
    )
    print(f"Saved TEM overlay: {result['overlay_path']}")
    print(f"Saved TEM segmentation mask: {result['mask_path']}")
    print(f"Saved TEM measurements: {result['measurements_path']}")
    print(f"Saved TEM size distribution: {result['size_distribution_path']}")
    print(f"Saved TEM intensity histogram: {result['intensity_histogram_path']}")
    print(f"Saved TEM long-format features: {result['feature_path']}")
    print(f"Saved TEM analysis manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
