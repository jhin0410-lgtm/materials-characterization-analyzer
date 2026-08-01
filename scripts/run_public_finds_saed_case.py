"""Run a calibrated diagnostic SAED case from the public FINDS example.

The case verifies the pinned Zenodo archive, decodes the selected JPEG once,
converts its decoded grayscale array to a lossless PNG container without
normalization or resizing, and runs the conservative SAED analyzer under one
primary and six predeclared sensitivity settings. It does not identify material,
phase, reflection, or zone axis.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
import pandas as pd

from mca.contracts import write_analysis_manifest
from mca.saed import analyze_saed

try:
    from . import audit_public_finds_saed_source as source_audit
except ImportError:  # Direct execution from the repository root.
    import audit_public_finds_saed_source as source_audit

CASE_ID = "public_finds_saed_diagnostic_case"


class CaseError(RuntimeError):
    """Raised when the selected source or case contract changes."""


def _prepare_output(path: Path) -> Path:
    if path.exists():
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        path.mkdir(parents=True)
    return path


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("analysis_case_id") != CASE_ID:
        raise CaseError("invalid FINDS SAED analysis config")
    return payload


def _download_archive(config: Mapping[str, Any]) -> tuple[bytes, dict[str, Any], str | None]:
    metadata_payload = source_audit._request_bytes(
        source_audit.API_URL.format(record_id=config["dataset"]["record_id"])
    )
    metadata = json.loads(metadata_payload.decode("utf-8"))
    records = source_audit._record_files(metadata)
    repository_record = next(
        (record for record in records if record["filename"] == config["archive"]["filename"]),
        None,
    )
    if repository_record is None:
        raise CaseError("pinned FINDS archive is missing")
    content_url = repository_record.get("content_url")
    if not isinstance(content_url, str) or not content_url.startswith("https://"):
        raise CaseError("pinned FINDS archive has no HTTPS content URL")
    payload = source_audit._request_bytes(content_url)
    try:
        verified = source_audit._verify_archive(payload, config["archive"], repository_record)
    except source_audit.SourceAuditError as exc:
        raise CaseError(str(exc)) from exc
    expected_sha256 = config["archive"].get("verified_sha256")
    if expected_sha256 and verified["downloaded_sha256"] != expected_sha256:
        raise CaseError("FINDS archive SHA-256 drift")
    license_id = source_audit._license_identifier(metadata)
    if license_id != config["dataset"]["license"]:
        raise CaseError("FINDS record licence differs from pinned contract")
    return payload, verified, license_id


def _selected_members(archive_payload: bytes, config: Mapping[str, Any]) -> dict[str, bytes]:
    selected = config["selected_project"]
    required = {
        selected["project_path"],
        selected["image_path"],
        selected["d_values_path"],
    }
    with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
        members = source_audit._safe_members(archive)
        available = {PurePosixPath(info.filename).as_posix(): info for info in members}
        missing = sorted(required.difference(available))
        if missing:
            raise CaseError(f"selected FINDS members are missing: {missing}")
        payloads = {path: archive.read(available[path]) for path in required}
    checks = {
        selected["project_path"]: (None, selected["project_sha256"]),
        selected["image_path"]: (selected["image_bytes"], selected["image_sha256"]),
        selected["d_values_path"]: (None, selected["d_values_sha256"]),
    }
    for path, payload in payloads.items():
        expected_size, expected_sha256 = checks[path]
        if expected_size is not None and len(payload) != expected_size:
            raise CaseError(f"selected member byte-size drift: {path}")
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise CaseError(f"selected member SHA-256 drift: {path}")
    return payloads


def _parse_selected_project(payload: bytes, config: Mapping[str, Any]) -> dict[str, Any]:
    text, encoding = source_audit._decode_text(payload)
    lines = [line.strip() for line in text.splitlines()]
    if len(lines) < 5:
        raise CaseError("selected FINDS project has fewer than five lines")
    selected = config["selected_project"]
    expected = [
        selected["image_path"],
        str(selected["camera_constant_angstrom_pixel"]),
        str(selected["center_x_px"]).rstrip("0").rstrip("."),
        str(selected["center_y_px"]).rstrip("0").rstrip("."),
        selected["d_values_path"],
    ]
    observed_numeric = [
        lines[0],
        lines[1],
        lines[2],
        lines[3],
        lines[4],
    ]
    if observed_numeric[0] != expected[0] or observed_numeric[4] != expected[4]:
        raise CaseError("selected FINDS project file references changed")
    numeric = [float(lines[index]) for index in (1, 2, 3)]
    pinned = [
        float(selected["camera_constant_angstrom_pixel"]),
        float(selected["center_x_px"]),
        float(selected["center_y_px"]),
    ]
    if not all(math.isclose(value, target, rel_tol=0.0, abs_tol=1e-12) for value, target in zip(numeric, pinned)):
        raise CaseError("selected FINDS calibration or center changed")
    return {
        "encoding": encoding,
        "image_path": lines[0],
        "camera_constant_angstrom_pixel": numeric[0],
        "camera_constant_nm_pixel": numeric[0] * 0.1,
        "reciprocal_nm_inv_per_pixel": 10.0 / numeric[0],
        "center_x_px": numeric[1],
        "center_y_px": numeric[2],
        "d_values_path": lines[4],
    }


def _parse_source_d_values(payload: bytes) -> dict[str, Any]:
    text, encoding = source_audit._decode_text(payload)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise CaseError("source d-value file contains no numeric values")
    values_angstrom: list[float] = []
    for line_number, line in enumerate(lines[1:], start=2):
        try:
            value = float(line)
        except ValueError as exc:
            raise CaseError(f"non-numeric source d-value at line {line_number}") from exc
        if not math.isfinite(value) or value <= 0:
            raise CaseError(f"invalid source d-value at line {line_number}")
        values_angstrom.append(value)
    return {
        "encoding": encoding,
        "header": lines[0],
        "d_spacing_angstrom": values_angstrom,
        "d_spacing_nm": [value * 0.1 for value in values_angstrom],
    }


def decode_to_canonical_png(
    source_payload: bytes,
    destination: Path,
    config: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    array = np.frombuffer(source_payload, dtype=np.uint8)
    source = cv2.imdecode(array, cv2.IMREAD_UNCHANGED)
    if source is None:
        raise CaseError("selected SAED JPEG could not be decoded")
    if source.ndim == 3 and source.shape[2] == 3:
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        conversion = "opencv_bgr_to_grayscale"
    elif source.ndim == 3 and source.shape[2] == 4:
        gray = cv2.cvtColor(source, cv2.COLOR_BGRA2GRAY)
        conversion = "opencv_bgra_to_grayscale"
    elif source.ndim == 2:
        gray = source.copy()
        conversion = "already_grayscale"
    else:
        raise CaseError("selected SAED image has unsupported decoded shape")
    selected = config["selected_project"]
    if list(gray.shape) != [selected["source_image_height_px"], selected["source_image_width_px"]]:
        raise CaseError("selected SAED decoded dimensions changed")
    if str(gray.dtype) != selected["source_image_dtype"]:
        raise CaseError("selected SAED decoded dtype changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), gray):
        raise OSError(f"failed to write canonical SAED PNG: {destination}")
    roundtrip = cv2.imread(str(destination), cv2.IMREAD_UNCHANGED)
    if roundtrip is None or not np.array_equal(gray, roundtrip):
        raise CaseError("canonical PNG roundtrip changed decoded grayscale values")
    return gray, {
        "operation": config["canonical_adapter"]["operation"],
        "color_conversion": conversion,
        "source_representation": selected["source_representation"],
        "canonical_container": "png",
        "decoded_dtype": str(gray.dtype),
        "decoded_shape": list(gray.shape),
        "decoded_minimum_intensity": int(gray.min()),
        "decoded_maximum_intensity": int(gray.max()),
        "normalization_applied": False,
        "contrast_adjustment_applied": False,
        "cropping_applied": False,
        "resizing_applied": False,
        "denoising_applied": False,
        "png_roundtrip_pixel_equal": True,
        "canonical_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }


def _run_contracts(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    analysis = config["analysis"]
    primary_window = int(analysis["primary_smoothing_window"])
    center_x = float(config["selected_project"]["center_x_px"])
    center_y = float(config["selected_project"]["center_y_px"])
    records = [
        {
            "run_id": "primary",
            "center_x_px": center_x,
            "center_y_px": center_y,
            "smoothing_window": primary_window,
            "sensitivity_dimension": "primary",
        }
    ]
    for window in analysis["sensitivity_smoothing_windows"]:
        records.append(
            {
                "run_id": f"smoothing_{int(window)}",
                "center_x_px": center_x,
                "center_y_px": center_y,
                "smoothing_window": int(window),
                "sensitivity_dimension": "smoothing_window",
            }
        )
    for offset_x, offset_y in analysis["center_sensitivity_offsets_px"]:
        records.append(
            {
                "run_id": f"center_{offset_x:+g}_{offset_y:+g}".replace("+", "p").replace("-", "m"),
                "center_x_px": center_x + float(offset_x),
                "center_y_px": center_y + float(offset_y),
                "smoothing_window": primary_window,
                "sensitivity_dimension": "center_position",
            }
        )
    return records


def _run_analyses(
    canonical_path: Path,
    config: Mapping[str, Any],
    output: Path,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    analysis = config["analysis"]
    project = config["selected_project"]
    records: list[dict[str, Any]] = []
    tables: list[pd.DataFrame] = []
    for contract in _run_contracts(config):
        run_output = output / "analyses" / contract["run_id"]
        result = analyze_saed(
            canonical_path,
            run_output,
            sample_id=analysis["sample_id"],
            measurement_id=f"{analysis['measurement_id']}__{contract['run_id']}",
            center_x_px=contract["center_x_px"],
            center_y_px=contract["center_y_px"],
            bin_width_px=float(analysis["bin_width_px"]),
            min_radius_px=float(analysis["minimum_radius_px"]),
            max_radius_px=float(analysis["maximum_radius_px"]),
            ring_contrast=analysis["ring_contrast"],
            smoothing_window=int(contract["smoothing_window"]),
            smoothing_polyorder=int(analysis["smoothing_polyorder"]),
            prominence_fraction=float(analysis["prominence_fraction"]),
            min_distance_px=float(analysis["minimum_candidate_distance_px"]),
            camera_constant_nm_pixel=float(project["camera_constant_nm_pixel"]),
            acquisition_metadata={
                "accelerating_voltage_kv": config["unresolved_metadata"]["accelerating_voltage_kv"],
                "camera_length_mm": config["unresolved_metadata"]["camera_length_mm"],
                "detector_pixel_size_um": config["unresolved_metadata"]["detector_pixel_size_um"],
                "source_project_file": project["project_path"],
                "source_image_representation": project["source_representation"],
                "material_identity": config["unresolved_metadata"]["material_identity"],
            },
        )
        manifest_path = write_analysis_manifest(
            [result["analysis_result"]], run_output / "saed_analysis_manifest.json"
        )
        candidates = result["ring_candidates"].copy()
        candidates.insert(0, "run_id", contract["run_id"])
        candidates.insert(1, "sensitivity_dimension", contract["sensitivity_dimension"])
        candidates.insert(2, "center_x_px", contract["center_x_px"])
        candidates.insert(3, "center_y_px", contract["center_y_px"])
        candidates.insert(4, "smoothing_window", contract["smoothing_window"])
        tables.append(candidates)
        records.append(
            {
                **contract,
                "candidate_count": int(len(candidates)),
                "analysis_manifest": manifest_path.relative_to(output).as_posix(),
                "warnings": list(result["analysis_result"].warnings),
            }
        )
    return records, pd.concat(tables, ignore_index=True)


def review_candidate_sensitivity(
    candidates: pd.DataFrame,
    *,
    tolerance_px: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if tolerance_px <= 0:
        raise CaseError("candidate match tolerance must be positive")
    primary = candidates[candidates["run_id"] == "primary"].sort_values("radius_px")
    other_runs = sorted(set(candidates["run_id"]) - {"primary"})
    used: dict[str, set[int]] = {run_id: set() for run_id in other_runs}
    rows: list[dict[str, Any]] = []
    for primary_row in primary.itertuples(index=False):
        radii = [float(primary_row.radius_px)]
        record: dict[str, Any] = {
            "primary_ring_id": int(primary_row.ring_id),
            "primary_radius_px": float(primary_row.radius_px),
            "primary_d_spacing_nm": float(primary_row.d_spacing_nm),
        }
        matched = 1
        for run_id in other_runs:
            subset = candidates[
                (candidates["run_id"] == run_id)
                & (~candidates.index.isin(used[run_id]))
            ].copy()
            if subset.empty:
                nearest = None
            else:
                subset["delta"] = (
                    subset["radius_px"].astype(float) - float(primary_row.radius_px)
                ).abs()
                index = int(subset["delta"].idxmin())
                nearest = subset.loc[index] if float(subset.loc[index, "delta"]) <= tolerance_px else None
            if nearest is None:
                record[f"{run_id}_radius_px"] = None
                record[f"{run_id}_delta_px"] = None
                continue
            used[run_id].add(int(nearest.name))
            radius = float(nearest["radius_px"])
            radii.append(radius)
            matched += 1
            record[f"{run_id}_radius_px"] = radius
            record[f"{run_id}_delta_px"] = radius - float(primary_row.radius_px)
        record["matched_run_count"] = matched
        record["total_run_count"] = len(other_runs) + 1
        record["all_runs_matched"] = matched == len(other_runs) + 1
        record["maximum_radius_spread_px"] = max(radii) - min(radii)
        record["review_status"] = (
            "stable_radius_review_required"
            if record["all_runs_matched"]
            else "parameter_sensitive_review_required"
        )
        rows.append(record)
    unmatched_tables = []
    for run_id in other_runs:
        subset = candidates[
            (candidates["run_id"] == run_id) & (~candidates.index.isin(used[run_id]))
        ].copy()
        if not subset.empty:
            unmatched_tables.append(subset)
    unmatched = (
        pd.concat(unmatched_tables, ignore_index=True)
        if unmatched_tables
        else candidates.iloc[0:0].copy()
    )
    return pd.DataFrame(rows), unmatched


def compare_source_d_values(
    primary_candidates: pd.DataFrame,
    source_d_values: Mapping[str, Any],
    *,
    camera_constant_nm_pixel: float,
    max_radius_px: float,
) -> pd.DataFrame:
    rows = []
    for index, d_nm in enumerate(source_d_values["d_spacing_nm"], start=1):
        expected_radius = camera_constant_nm_pixel / float(d_nm)
        inside = expected_radius <= max_radius_px
        if primary_candidates.empty:
            nearest = None
        else:
            differences = (primary_candidates["d_spacing_nm"].astype(float) - float(d_nm)).abs()
            nearest = primary_candidates.loc[int(differences.idxmin())]
        rows.append(
            {
                "source_reference_id": index,
                "source_d_spacing_nm": float(d_nm),
                "expected_radius_from_project_calibration_px": expected_radius,
                "inside_analyzed_radius": inside,
                "nearest_detected_ring_id": int(nearest["ring_id"]) if nearest is not None else None,
                "nearest_detected_radius_px": float(nearest["radius_px"]) if nearest is not None else None,
                "nearest_detected_d_spacing_nm": float(nearest["d_spacing_nm"]) if nearest is not None else None,
                "relative_d_spacing_difference": (
                    abs(float(nearest["d_spacing_nm"]) - float(d_nm)) / float(d_nm)
                    if nearest is not None
                    else None
                ),
                "reference_used_for_detection_tuning": False,
                "material_or_phase_identity_assigned": False,
            }
        )
    return pd.DataFrame(rows)


def _write_manifest(output: Path) -> Path:
    path = output / "case_artifact_manifest.json"
    records = []
    for artifact in sorted(output.rglob("*")):
        if not artifact.is_file() or artifact == path:
            continue
        payload = artifact.read_bytes()
        records.append(
            {
                "path": artifact.relative_to(output).as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": CASE_ID,
                "artifact_count": len(records),
                "artifacts": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    try:
        config = _load_config(config_path)
        archive_payload, archive_record, license_id = _download_archive(config)
        members = _selected_members(archive_payload, config)
        selected = config["selected_project"]
        project = _parse_selected_project(members[selected["project_path"]], config)
        source_d_values = _parse_source_d_values(members[selected["d_values_path"]])
        canonical_path = output / "canonical" / "saed_a_decoded_grayscale.png"
        _, adapter = decode_to_canonical_png(
            members[selected["image_path"]], canonical_path, config
        )
        run_records, candidates = _run_analyses(canonical_path, config, output)
        candidates_path = output / "saed_sensitivity_candidates.csv"
        candidates.to_csv(candidates_path, index=False)
        robustness, unmatched = review_candidate_sensitivity(
            candidates,
            tolerance_px=float(config["analysis"]["candidate_match_tolerance_px"]),
        )
        robustness_path = output / "saed_candidate_robustness.csv"
        unmatched_path = output / "saed_unmatched_sensitivity_candidates.csv"
        robustness.to_csv(robustness_path, index=False)
        unmatched.to_csv(unmatched_path, index=False)
        primary = candidates[candidates["run_id"] == "primary"].copy()
        reference_comparison = compare_source_d_values(
            primary,
            source_d_values,
            camera_constant_nm_pixel=float(project["camera_constant_nm_pixel"]),
            max_radius_px=float(config["analysis"]["maximum_radius_px"]),
        )
        reference_path = output / "source_d_value_comparison.csv"
        reference_comparison.to_csv(reference_path, index=False)

        summary = {
            "schema_version": "1.0",
            "case_id": CASE_ID,
            "source": {
                "repository": config["dataset"]["repository"],
                "record_id": config["dataset"]["record_id"],
                "doi": config["dataset"]["doi"],
                "version": config["dataset"]["version"],
                "license": license_id,
                "archive": archive_record,
                "project": project,
                "source_image_sha256": selected["image_sha256"],
                "source_image_representation": selected["source_representation"],
                "source_images_persisted": False,
            },
            "canonical_adapter": {
                **adapter,
                "canonical_path": canonical_path.relative_to(output).as_posix(),
            },
            "analysis_contract": {
                **config["analysis"],
                "camera_constant_nm_pixel": project["camera_constant_nm_pixel"],
                "reciprocal_space_convention": "g_equals_1_over_d",
                "source_d_values_used_to_tune_detection": False,
            },
            "analysis_runs": run_records,
            "candidate_robustness": {
                "primary_candidate_count": int(len(robustness)),
                "all_runs_matched_count": int(robustness["all_runs_matched"].sum()) if not robustness.empty else 0,
                "unmatched_sensitivity_candidate_count": int(len(unmatched)),
                "raw_analyzer_candidate_tables_modified": False,
                "candidate_acceptance_or_rejection_performed": False,
            },
            "source_d_value_context": {
                **source_d_values,
                "used_for_detection_tuning": False,
                "used_for_phase_or_material_assignment": False,
                "comparison_table": reference_path.name,
            },
            "unresolved_metadata": config["unresolved_metadata"],
            "readiness": {
                "status": "diagnostic_calibrated_saed_case_completed",
                "archive_and_member_checksums_verified": True,
                "project_center_and_camera_constant_verified": True,
                "decoded_jpeg_to_png_pixel_roundtrip_verified": True,
                "saed_analyzer_executed": True,
                "center_and_smoothing_sensitivity_completed": True,
                "material_identity_resolved": False,
                "raw_detector_provenance_resolved": False,
                "phase_reflection_or_zone_axis_assignment_performed": False,
                "engineering_release_ready": False,
            },
            "scientific_closeout": {
                "status": "Diagnostic",
                "result": "diagnostic_calibrated_saed_case_completed",
                "strongest_evidence": (
                    "A checksum-bound public SAED example was linked to an explicit FINDS project center and camera constant, converted without decoded-pixel changes to a supported PNG container, and analyzed under predeclared center and smoothing sensitivities."
                ),
                "primary_limitation": (
                    "The source is a lossy JPEG software example without material, sample, acquisition, accelerating-voltage, detector, or raw-intensity provenance."
                ),
                "evidence_that_would_change_conclusion": (
                    "A raw or lossless calibrated SAED export with material and acquisition identity, detector metadata, independent center verification, and crystallographic reference review."
                ),
                "suitable_for": [
                    "real-image software integration validation",
                    "camera-constant conversion validation",
                    "center and smoothing sensitivity diagnostics",
                ],
                "not_suitable_for": [
                    "material identification",
                    "phase or reflection indexing",
                    "zone-axis assignment",
                    "validated crystallographic claims",
                    "engineering release decisions",
                ],
            },
        }
        summary_path = output / "case_summary.json"
        report_path = output / "case_validation_report.md"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        report_path.write_text(_report(summary, robustness), encoding="utf-8")
        _write_manifest(output)
        return summary
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


def _report(summary: Mapping[str, Any], robustness: pd.DataFrame) -> str:
    lines = [
        "# Public FINDS SAED Diagnostic Case",
        "",
        "**Evidence level:** Diagnostic",
        "",
        f"**Result:** `{summary['readiness']['status']}`",
        "",
        "## Source and calibration",
        "",
        f"- Source DOI: `{summary['source']['doi']}`",
        f"- Source image representation: `{summary['source']['source_image_representation']}`",
        f"- Project center: `({summary['source']['project']['center_x_px']}, {summary['source']['project']['center_y_px']}) px`",
        f"- Camera constant: `{summary['source']['project']['camera_constant_angstrom_pixel']} Å·px` = `{summary['source']['project']['camera_constant_nm_pixel']} nm·px`",
        "- Reciprocal convention: `g = 1/d`",
        "- Material identity: `unresolved`",
        "- Raw detector provenance: `unresolved`",
        "",
        "## Sensitivity runs",
        "",
        "| Run | Center x | Center y | Smoothing window | Candidates |",
        "|---|---:|---:|---:|---:|",
    ]
    for record in summary["analysis_runs"]:
        lines.append(
            f"| {record['run_id']} | {record['center_x_px']:.3f} | {record['center_y_px']:.3f} | {record['smoothing_window']} | {record['candidate_count']} |"
        )
    lines.extend(
        [
            "",
            "## Candidate robustness",
            "",
            f"- Primary candidates: `{summary['candidate_robustness']['primary_candidate_count']}`",
            f"- Matched in all seven runs: `{summary['candidate_robustness']['all_runs_matched_count']}`",
            f"- Unmatched sensitivity candidates: `{summary['candidate_robustness']['unmatched_sensitivity_candidate_count']}`",
            "- Analyzer candidate tables modified: `false`",
            "- Candidate acceptance or rejection performed: `false`",
            "",
            "| Primary ring | Radius (px) | d spacing (nm) | Maximum radius spread (px) | Status |",
            "|---:|---:|---:|---:|---|",
        ]
    )
    for row in robustness.itertuples(index=False):
        lines.append(
            f"| {row.primary_ring_id} | {row.primary_radius_px:.5g} | {row.primary_d_spacing_nm:.6g} | {row.maximum_radius_spread_px:.5g} | `{row.review_status}` |"
        )
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "The source d-values were compared only after detection and were not used to tune center, smoothing, prominence, distance, or radius bounds. No source d-value or detected ring is assigned to a material, phase, reflection, or zone axis.",
            "",
            "The canonical PNG preserves the decoded grayscale JPEG array, but it cannot restore information already lost in the source JPEG or establish raw detector intensity provenance.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("case_studies/public_finds_saed/case_config.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = run(args.config, args.output)
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports actionable context.
        print(f"public FINDS SAED case failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": summary["readiness"]["status"],
                "analysis_run_count": len(summary["analysis_runs"]),
                "primary_candidate_count": summary["candidate_robustness"]["primary_candidate_count"],
                "all_runs_matched_count": summary["candidate_robustness"]["all_runs_matched_count"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
