"""Command line interface for Materials Characterization Analyzer."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .contracts import PreprocessingStep, write_analysis_manifest
from .eds import analyze_eds
from .feature_records import build_characterization_feature_records, save_feature_records
from .features import build_sample_features_table, default_sample_id_from_inputs, save_sample_features
from .provenance import build_analysis_result, preprocessing_fingerprint
from .report import generate_report
from .sem import analyze_sem
from .xrd import analyze_xrd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca",
        description="Analyze materials characterization data and generate cautious, provenance-aware outputs.",
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

    feature_parser = subparsers.add_parser(
        "feature-records",
        help="Export available XRD/SEM/EDS result tables to the stable long-format feature contract.",
    )
    feature_parser.add_argument("--sample-id", required=True, help="Stable sample identifier.")
    feature_parser.add_argument("--output", required=True, help="Output directory.")
    feature_parser.add_argument("--xrd-peaks", default=None, help="Optional XRD peak table CSV.")
    feature_parser.add_argument("--sem-measurements", default=None, help="Optional SEM measurements CSV.")
    feature_parser.add_argument("--eds-composition", default=None, help="Optional EDS composition table CSV.")
    feature_parser.add_argument("--xrd-source", default=None, help="Optional original XRD source file for SHA-256 provenance.")
    feature_parser.add_argument("--sem-source", default=None, help="Optional original SEM source file for SHA-256 provenance.")
    feature_parser.add_argument("--eds-source", default=None, help="Optional original EDS source file for SHA-256 provenance.")
    feature_parser.set_defaults(func=_run_feature_records)

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
    all_parser.add_argument(
        "--extract-features",
        action="store_true",
        help="Save the backward-compatible one-row sample_features.csv table.",
    )
    all_parser.add_argument(
        "--export-feature-records",
        action="store_true",
        help="Save long-format features and a provenance-aware characterization manifest.",
    )
    all_parser.add_argument("--sample-id", default=None, help="Stable sample ID used by feature exports.")
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


def _run_feature_records(args: argparse.Namespace) -> int:
    xrd_peaks = _read_optional_csv(args.xrd_peaks)
    sem_measurements = _read_optional_csv(args.sem_measurements)
    eds_composition = _read_optional_csv(args.eds_composition)
    if xrd_peaks is None and sem_measurements is None and eds_composition is None:
        raise ValueError("At least one result table must be provided for feature-records.")

    records = build_characterization_feature_records(
        sample_id=args.sample_id,
        xrd_peak_table=xrd_peaks,
        sem_measurements=sem_measurements,
        eds_composition_table=eds_composition,
        source_files={"xrd": args.xrd_source, "sem": args.sem_source, "eds": args.eds_source},
    )
    feature_path = save_feature_records(records, args.output)

    results = []
    table_inputs = {
        "xrd": (args.xrd_peaks, args.xrd_source),
        "sem": (args.sem_measurements, args.sem_source),
        "eds": (args.eds_composition, args.eds_source),
    }
    for instrument, (table_path, source_path) in table_inputs.items():
        if table_path is None:
            continue
        instrument_records = [record for record in records if record.instrument == instrument]
        results.append(
            build_analysis_result(
                measurement_id=f"{args.sample_id}-{instrument}",
                sample_id=args.sample_id,
                instrument=instrument,
                source_file=source_path,
                tables={"provided_result_table": table_path},
                features=instrument_records,
                warnings=["preprocessing_history_not_provided"],
                limitations=_instrument_limitations(instrument),
            )
        )

    manifest_path = write_analysis_manifest(results, Path(args.output) / "characterization_manifest.json")
    print(f"Saved long-format feature records: {feature_path}")
    print(f"Saved characterization manifest: {manifest_path}")
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

    sample_id = args.sample_id or default_sample_id_from_inputs(args.xrd, args.sem, args.eds)
    if args.extract_features:
        feature_table = build_sample_features_table(
            sample_id=sample_id,
            xrd_peak_table=xrd_result["peak_table"],
            sem_measurements=sem_result["measurements"],
            eds_composition_table=eds_result["composition_table"],
        )
        feature_path = save_sample_features(feature_table, args.output)
        print(f"Saved sample features: {feature_path}")

    if args.export_feature_records:
        feature_path, manifest_path = _export_contract_outputs(
            args=args,
            sample_id=sample_id,
            xrd_result=xrd_result,
            sem_result=sem_result,
            eds_result=eds_result,
        )
        print(f"Saved long-format feature records: {feature_path}")
        print(f"Saved characterization manifest: {manifest_path}")

    return 0


def _export_contract_outputs(
    *,
    args: argparse.Namespace,
    sample_id: str,
    xrd_result: dict[str, object],
    sem_result: dict[str, object],
    eds_result: dict[str, object],
) -> tuple[Path, Path]:
    xrd_steps = [
        PreprocessingStep(
            step_id="xrd-savgol-smoothing",
            operation="savgol_smoothing",
            parameters={"window_length": 11, "polyorder": 3, "application": "conditional_on_data_length"},
        ),
        PreprocessingStep(
            step_id="xrd-peak-detection",
            operation="scipy_find_peaks",
            parameters={"prominence_fraction": 0.05, "minimum_distance_samples": 3},
        ),
    ]
    if args.xrd_wavelength is not None:
        xrd_steps.append(
            PreprocessingStep(
                step_id="xrd-scherrer-estimate",
                operation="scherrer_crystallite_size_estimate",
                parameters={"wavelength": args.xrd_wavelength, "shape_factor": args.shape_factor},
                notes="The wavelength unit is not encoded by the current CLI.",
            )
        )
    sem_steps = [
        PreprocessingStep("sem-grayscale", "bgr_to_grayscale"),
        PreprocessingStep(
            "sem-threshold",
            "otsu_threshold",
            {"gaussian_blur_kernel": [5, 5], "invert": bool(args.invert_sem)},
        ),
        PreprocessingStep(
            "sem-contours",
            "external_contour_measurement",
            {"minimum_area_pixels": 5.0, "microns_per_pixel": args.microns_per_pixel},
        ),
    ]
    eds_steps = [
        PreprocessingStep("eds-import", "composition_table_validation"),
        PreprocessingStep("eds-sort", "sort_by_weight_percent", {"ascending": False}),
    ]
    steps_by_instrument = {"xrd": xrd_steps, "sem": sem_steps, "eds": eds_steps}
    preprocessing_ids = {
        instrument: preprocessing_fingerprint(instrument, steps)
        for instrument, steps in steps_by_instrument.items()
    }
    measurement_ids = {instrument: f"{sample_id}-{instrument}" for instrument in steps_by_instrument}

    records = build_characterization_feature_records(
        sample_id=sample_id,
        xrd_peak_table=xrd_result["peak_table"],
        sem_measurements=sem_result["measurements"],
        eds_composition_table=eds_result["composition_table"],
        source_files={"xrd": args.xrd, "sem": args.sem, "eds": args.eds},
        measurement_ids=measurement_ids,
        preprocessing_ids=preprocessing_ids,
    )
    feature_path = save_feature_records(records, args.output)

    xrd_warnings = []
    xrd_metadata = {}
    if args.xrd_wavelength is not None:
        xrd_metadata = {"xray_wavelength": args.xrd_wavelength, "xray_wavelength_unit": None}
        xrd_warnings.append("xrd_wavelength_unit_not_recorded")

    analyses = [
        build_analysis_result(
            measurement_id=measurement_ids["xrd"],
            sample_id=sample_id,
            instrument="xrd",
            source_file=args.xrd,
            acquisition_metadata=xrd_metadata,
            preprocessing_steps=xrd_steps,
            tables={"peak_table": xrd_result["peak_table_path"]},
            figures={"pattern_with_peaks": xrd_result["plot_path"]},
            features=[record for record in records if record.instrument == "xrd"],
            warnings=xrd_warnings,
            limitations=_instrument_limitations("xrd"),
        ),
        build_analysis_result(
            measurement_id=measurement_ids["sem"],
            sample_id=sample_id,
            instrument="sem",
            source_file=args.sem,
            acquisition_metadata={
                "microns_per_pixel": args.microns_per_pixel,
                "scale_source": "user_supplied_cli",
            },
            preprocessing_steps=sem_steps,
            tables={"measurements": sem_result["measurements_path"]},
            figures={
                "segmentation_overlay": sem_result["overlay_path"],
                "size_distribution": sem_result["histogram_path"],
            },
            features=[record for record in records if record.instrument == "sem"],
            warnings=["threshold_segmentation_requires_manual_review"],
            limitations=_instrument_limitations("sem"),
        ),
        build_analysis_result(
            measurement_id=measurement_ids["eds"],
            sample_id=sample_id,
            instrument="eds",
            source_file=args.eds,
            preprocessing_steps=eds_steps,
            tables={"composition_table": eds_result["table_path"]},
            figures={"composition_chart": eds_result["chart_path"]},
            features=[record for record in records if record.instrument == "eds"],
            warnings=["acquisition_metadata_not_provided"],
            limitations=_instrument_limitations("eds"),
        ),
    ]
    manifest_path = write_analysis_manifest(analyses, Path(args.output) / "characterization_manifest.json")
    return feature_path, manifest_path


def _instrument_limitations(instrument: str) -> list[str]:
    limitations = {
        "xrd": [
            "Detected peaks and FWHM values do not confirm crystal phases.",
            "Scherrer outputs are approximate crystallite-size estimates and are not particle-size measurements.",
        ],
        "sem": [
            "Threshold-derived regions depend on contrast, preparation, scale calibration, and segmentation settings.",
            "Detected regions require manual review before formal scientific use.",
        ],
        "eds": [
            "EDS composition does not confirm crystalline phases or chemical states.",
            "Quantification depends on acquisition conditions, corrections, geometry, and sample preparation.",
        ],
    }
    return list(limitations.get(instrument, []))


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    return pd.read_csv(path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
