"""Build the frozen public TM-Fe-Si XRD bundle for descriptive MDA use only."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

from mca import __version__
from mca.contracts import AnalysisResult, FeatureRecord, PreprocessingStep, write_analysis_manifest
from mca.feature_records import build_xrd_feature_records
from mca.handoff_bundle_builder import build_characterization_handoff_bundle_from_config
from mca.provenance import preprocessing_fingerprint, sha256_file
from mca.xrd import detect_peaks, smooth_intensity

CASE_ID = "tm-fe-si-public-xrd-descriptive-v1"
PRODUCER_REPOSITORY = "jhin0410-lgtm/materials-characterization-analyzer"
CONSUMER_REPOSITORY = "jhin0410-lgtm/materials-data-analyzer"
DATASET_DOI = "10.17632/gp8rkw2k6v.2"
PUBLICATION_DOI = "10.1016/j.dib.2022.108868"
EXPECTED_WORKBOOK_NAME = "Fig.2-XRD data.xlsx"
EXPECTED_WORKBOOK_SHA256 = "7138e2e2d6dbf422c7b534af38810bfe963969cd3f8e8b3a7e8daf7ddb17ac20"
EXPECTED_WORKBOOK_BYTES = 218_303
EXPECTED_X_HEADER = "2θ (degree)"
EXPECTED_Y_HEADER = "Intensity (arb. units)"
EXPECTED_POINT_COUNT = 3_501
EXPECTED_TWO_THETA_MIN = 20.0
EXPECTED_TWO_THETA_MAX = 90.0
EXPECTED_TWO_THETA_STEP = 0.02
SMOOTHING_WINDOW = 11
SMOOTHING_POLYORDER = 3
PROMINENCE_FRACTION = 0.05
MIN_DISTANCE = 3
EDGE_MARGIN = 3
PREPARATION_FAMILY_ID = "tm-fe-si-arc-melt-remelt-1050c-1d-air-cool"
ALLOWED_FEATURES = {
    "detected_peak_count",
    "main_peak_two_theta",
    "mean_fwhm",
    "median_fwhm",
    "minimum_two_theta",
    "maximum_two_theta",
}
FORBIDDEN_FEATURES = {"main_peak_intensity", "mean_scherrer_crystallite_size_estimate"}
TRACE_CONTRACTS = (
    ("Ti", "A", "B", "Fig. 2(a) Ti7Fe52Si41"),
    ("Zr", "C", "D", "Fig. 2(b) Zr7Fe52Si41"),
    ("Hf", "E", "F", "Fig. 2(c) Hf7Fe52Si41"),
    ("V", "G", "H", "Fig. 2(d) V7Fe52Si41"),
    ("Nb", "I", "J", "Fig. 2(e) Nb7Fe52Si41"),
    ("Ta", "K", "L", "Fig. 2(f) Ta7Fe52Si41"),
)
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class TMFeSiXRDHandoffError(ValueError):
    pass


def sample_id(tm_element: str) -> str:
    return f"tm-fe-si-{tm_element.lower()}7fe52si41-1050c-1d"


def _validate_workbook_identity(workbook: Path) -> str:
    if not workbook.is_file() or workbook.is_symlink():
        raise TMFeSiXRDHandoffError("XRD source must be a regular non-symlink file")
    if workbook.name != EXPECTED_WORKBOOK_NAME:
        raise TMFeSiXRDHandoffError(f"expected source filename {EXPECTED_WORKBOOK_NAME!r}")
    if workbook.stat().st_size != EXPECTED_WORKBOOK_BYTES:
        raise TMFeSiXRDHandoffError("XRD workbook size differs from the frozen source audit")
    digest = sha256_file(workbook)
    if digest != EXPECTED_WORKBOOK_SHA256:
        raise TMFeSiXRDHandoffError("XRD workbook SHA-256 differs from the frozen source audit")
    return digest


def _worksheet_cells(workbook: Path) -> dict[str, str | float]:
    try:
        with zipfile.ZipFile(workbook) as archive:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise TMFeSiXRDHandoffError("published source is not the expected readable XLSX structure") from exc
    if sheet_root.find(f".//{_NS}f") is not None:
        raise TMFeSiXRDHandoffError("formulas are not allowed in the frozen XRD workbook")
    shared = ["".join(t.text or "" for t in item.iter(f"{_NS}t")) for item in shared_root.findall(f"{_NS}si")]
    cells: dict[str, str | float] = {}
    for cell in sheet_root.findall(f".//{_NS}c"):
        ref = cell.attrib.get("r")
        node = cell.find(f"{_NS}v")
        if not ref or node is None or node.text is None:
            continue
        if cell.attrib.get("t") == "s":
            try:
                cells[ref] = shared[int(node.text)]
            except (ValueError, IndexError) as exc:
                raise TMFeSiXRDHandoffError(f"invalid shared string at {ref}") from exc
        else:
            try:
                cells[ref] = float(node.text)
            except ValueError as exc:
                raise TMFeSiXRDHandoffError(f"non-numeric source value at {ref}") from exc
    return cells


def _traces_from_cells(cells: dict[str, str | float]) -> dict[str, pd.DataFrame]:
    axis = EXPECTED_TWO_THETA_MIN + EXPECTED_TWO_THETA_STEP * np.arange(EXPECTED_POINT_COUNT)
    traces: dict[str, pd.DataFrame] = {}
    for tm, x_col, y_col, title in TRACE_CONTRACTS:
        if cells.get(f"{x_col}1") != title:
            raise TMFeSiXRDHandoffError(f"unexpected trace title in {x_col}1")
        if cells.get(f"{x_col}2") != EXPECTED_X_HEADER or cells.get(f"{y_col}2") != EXPECTED_Y_HEADER:
            raise TMFeSiXRDHandoffError(f"unexpected XRD headers for {tm}")
        pairs = [(cells.get(f"{x_col}{r}"), cells.get(f"{y_col}{r}")) for r in range(3, 3 + EXPECTED_POINT_COUNT)]
        if any(not isinstance(x, float) or not isinstance(y, float) for x, y in pairs):
            raise TMFeSiXRDHandoffError(f"missing or non-numeric XRD values for {tm}")
        x = np.asarray([x for x, _ in pairs], dtype=float)
        y = np.asarray([y for _, y in pairs], dtype=float)
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise TMFeSiXRDHandoffError(f"non-finite XRD values for {tm}")
        if not np.allclose(x, axis, rtol=0.0, atol=1e-10):
            raise TMFeSiXRDHandoffError(f"unexpected 2theta grid for {tm}")
        if not math.isclose(float(x[-1]), EXPECTED_TWO_THETA_MAX, abs_tol=1e-10):
            raise TMFeSiXRDHandoffError(f"unexpected 2theta endpoint for {tm}")
        traces[tm] = pd.DataFrame({"two_theta": x, "intensity": y})
    return traces


def extract_xrd_traces(workbook_path: str | Path) -> dict[str, pd.DataFrame]:
    workbook = Path(workbook_path)
    _validate_workbook_identity(workbook)
    return _traces_from_cells(_worksheet_cells(workbook))


def _steps(tm: str) -> list[PreprocessingStep]:
    title = next(row[3] for row in TRACE_CONTRACTS if row[0] == tm)
    return [
        PreprocessingStep(
            "xlsx-trace-extraction",
            "extract_explicit_xrd_column_pair",
            {"trace_title": title, "point_count": EXPECTED_POINT_COUNT, "offset_correction": False, "interpolation": False},
            "Raw public intensities are retained unchanged despite publication plotting offsets.",
        ),
        PreprocessingStep("savgol-smoothing", "savitzky_golay_smoothing", {"window_length": 11, "polyorder": 3}),
        PreprocessingStep(
            "peak-localization",
            "scipy_find_peaks_and_half_height_widths",
            {"prominence_fraction": 0.05, "minimum_distance_samples": 3, "edge_margin_samples": 3, "width_relative_height": 0.5},
            "Existing MCA defaults; not tuned to peak labels or magnetic outcomes.",
        ),
    ]


def _restricted_features(peaks: pd.DataFrame, tm: str, sha: str, preprocessing_id: str) -> list[FeatureRecord]:
    sid = sample_id(tm)
    generated = build_xrd_feature_records(peaks, sample_id=sid, measurement_id=f"{sid}-xrd", preprocessing_id=preprocessing_id)
    names = {record.feature_name for record in generated}
    if "main_peak_intensity" not in names:
        raise TMFeSiXRDHandoffError("expected generic intensity feature is unavailable for explicit exclusion")
    selected = [
        replace(record, source_file=EXPECTED_WORKBOOK_NAME, source_sha256=sha, quality_flag="review_required")
        for record in generated
        if record.feature_name in ALLOWED_FEATURES
    ]
    if {record.feature_name for record in selected} != ALLOWED_FEATURES:
        raise TMFeSiXRDHandoffError("restricted XRD feature contract is incomplete")
    return selected


def _sample_context() -> list[dict[str, object]]:
    return [
        {
            "sample_id": sample_id(tm),
            "nominal_composition": f"{tm}7Fe52Si41",
            "tm_element": tm,
            "nominal_atomic_ratio_tm_fe_si": "7:52:41",
            "preparation_family_id": PREPARATION_FAMILY_ID,
            "xrd_physical_form": "powdered_portion",
            "cross_modal_identity_level": "nominal_composition_plus_preparation_family",
            "exact_xrd_vsm_specimen_identity_confirmed": False,
            "dataset_persistent_id": f"doi:{DATASET_DOI}",
            "dataset_version": "2",
            "dataset_license": "CC BY 4.0",
        }
        for tm, *_ in TRACE_CONTRACTS
    ]


def _write_case_evidence(stage: Path, workbook: Path, traces: dict[str, pd.DataFrame], results: list[AnalysisResult]) -> Path:
    source = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "dataset": {"doi": DATASET_DOI, "publication_doi": PUBLICATION_DOI, "version": "2", "license": "CC BY 4.0"},
        "workbook": {"name": EXPECTED_WORKBOOK_NAME, "size_bytes": workbook.stat().st_size, "sha256": EXPECTED_WORKBOOK_SHA256, "raw_committed": False},
        "trace_headers": {tm: title for tm, _x, _y, title in TRACE_CONTRACTS},
        "point_count_per_trace": EXPECTED_POINT_COUNT,
        "two_theta_grid_deg": {"min": 20.0, "max": 90.0, "step": 0.02},
        "transformations": {"offset_correction": False, "normalization": False, "interpolation": False, "outlier_removal": False},
    }
    (stage / "source_manifest.json").write_text(json.dumps(source, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    write_analysis_manifest(results, stage / "characterization_manifest.json")
    pd.DataFrame(
        [
            {
                "sample_id": sample_id(tm),
                "nominal_composition": f"{tm}7Fe52Si41",
                "identity_level": "nominal_composition_plus_preparation_family",
                "exact_xrd_vsm_specimen_identity_confirmed": False,
                "absolute_xrd_intensity_cross_composition_comparable": False,
                "xrd_peak_position_descriptive_use_allowed": True,
                "phase_assignment_allowed": False,
                "association_or_stronger_use_allowed": False,
            }
            for tm, *_ in TRACE_CONTRACTS
        ]
    ).to_csv(stage / "comparability_matrix.csv", index=False, lineterminator="\n")
    config = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "producer_repository": PRODUCER_REPOSITORY,
        "evidence_level": "Diagnostic",
        "sample_context_rows": _sample_context(),
        "scientific_boundary": {
            "result": "diagnostic_offset_invariant_xrd_descriptive_features_exported",
            "strongest_evidence": "Six checksum-bound explicitly headed traces share an identical 20-90 degree 2theta grid; exported peak features are invariant to additive plotting offsets.",
            "primary_limitation": "Publication plotting offsets, no independent peak truth, omitted SEM/EDS in the uploaded subset, and unconfirmed exact XRD/VSM specimen identity.",
            "suitable_for": ["descriptive XRD peak-location and width summaries", "cross-repository provenance validation"],
            "unsuitable_for": ["absolute XRD intensity comparison", "phase assignment", "Scherrer-size claims", "association testing", "predictive modeling", "causal attribution", "engineering release decisions"],
        },
        "evidence": {"source_manifest": "source_manifest.json", "analysis_manifest": "characterization_manifest.json", "comparability_matrix": "comparability_matrix.csv"},
        "downstream_use_policy": {
            "schema_version": "1.0",
            "maximum_allowed_use": "descriptive",
            "feature_stage": "derived",
            "evidence_level": "Diagnostic",
            "review_status": "review_required",
            "independence_group_field": None,
            "measurement_timing": "not_applicable",
            "causal_design_validated": False,
            "operational_validation_validated": False,
            "limitations": [
                "Publication plotting offsets block absolute cross-composition intensity comparison.",
                "Exact XRD/VSM physical specimen identity is not confirmed.",
                "Peak locations and widths lack independent peak-truth validation for this source.",
            ],
        },
    }
    config_path = stage / "handoff_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return config_path


def build_tm_fe_si_xrd_handoff(workbook_path: str | Path, output_dir: str | Path) -> dict[str, object]:
    workbook = Path(workbook_path)
    sha = _validate_workbook_identity(workbook)
    traces = extract_xrd_traces(workbook)
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / f".{output.name}.building"
    if stage.exists():
        raise FileExistsError(f"staging directory already exists: {stage}")
    stage.mkdir()
    try:
        peak_dir = stage / "peak_tables"
        peak_dir.mkdir()
        results: list[AnalysisResult] = []
        for tm, *_ in TRACE_CONTRACTS:
            steps = _steps(tm)
            preprocessing_id = preprocessing_fingerprint("xrd", steps)
            trace = traces[tm]
            smoothed = smooth_intensity(trace["intensity"], window_length=11, polyorder=3)
            peaks = detect_peaks(trace["two_theta"], trace["intensity"], smoothed, prominence_fraction=0.05, min_distance=3, edge_margin=3)
            peak_path = peak_dir / f"{sample_id(tm)}-xrd-peaks.csv"
            peaks.to_csv(peak_path, index=False, lineterminator="\n")
            sid = sample_id(tm)
            results.append(
                AnalysisResult(
                    measurement_id=f"{sid}-xrd",
                    sample_id=sid,
                    instrument="xrd",
                    source_file=EXPECTED_WORKBOOK_NAME,
                    source_sha256=sha,
                    acquisition_metadata={"instrument_model": "Shimadzu XRD-7000L", "radiation": "Cu-Kalpha", "geometry": "Bragg-Brentano", "measurement_temperature": "room_temperature", "two_theta_step_deg": 0.02},
                    preprocessing_steps=steps,
                    tables={"peak_table": str(peak_path.relative_to(stage))},
                    features=_restricted_features(peaks, tm, sha, preprocessing_id),
                    warnings=["publication_plotting_offset_present_in_source_intensity", "independent_peak_truth_not_available", "exact_xrd_vsm_specimen_identity_unconfirmed"],
                    limitations=["Absolute XRD intensity is not comparable across compositions.", "No phase assignment or Scherrer size is reported.", "Peak localization and FWHM remain Diagnostic algorithm-derived quantities."],
                    software_version=__version__,
                )
            )
        config_path = _write_case_evidence(stage, workbook, traces, results)
        bundle = build_characterization_handoff_bundle_from_config(config_path, stage / "handoff_bundle")
        summary = {
            "schema_version": "1.0",
            "case_id": CASE_ID,
            "status": "diagnostic_descriptive_handoff_built",
            "source_sha256": sha,
            "sample_ids": [sample_id(tm) for tm, *_ in TRACE_CONTRACTS],
            "feature_names": sorted(ALLOWED_FEATURES),
            "excluded_feature_names": sorted(FORBIDDEN_FEATURES),
            "downstream_maximum_allowed_use": "descriptive",
            "consumer_repository": CONSUMER_REPOSITORY,
            "raw_workbook_committed": False,
            "scientific_validation": "Diagnostic",
            "software_validation": "bundle_builder_and_validation_completed",
        }
        (stage / "case_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        stage.replace(output)
        return {"status": summary["status"], "output": str(output), "bundle": str(output / "handoff_bundle"), "bundle_validation": bundle["validation"], "sample_count": 6, "feature_names": sorted(ALLOWED_FEATURES)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_tm_fe_si_xrd_handoff(args.workbook, args.output)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print(f"TM-Fe-Si XRD handoff failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
