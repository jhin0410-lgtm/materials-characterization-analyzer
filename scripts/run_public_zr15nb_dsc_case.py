"""Run the checksum-bound public Zr15Nb DSC case end to end.

The runner transiently downloads and verifies the pinned Zenodo files, adapts
only the DSC columns using the exact source header contract, and executes the
existing conservative DSC analyzer for one primary and two predeclared
smoothing settings. Source bytes are never persisted in the case output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from mca.contracts import write_analysis_manifest
from mca.thermal import analyze_thermal

try:
    from . import audit_public_zr15nb_dsc_source as source_audit
except ImportError:  # Direct ``python scripts/...py`` execution.
    import audit_public_zr15nb_dsc_source as source_audit

CASE_ID = "public_zr15nb_dsc_real_data_case"
ANALYSIS_RUNS = (
    ("primary", "primary_smoothing_span_c"),
    ("sensitivity_1c", None),
    ("sensitivity_5c", None),
)


class CaseError(RuntimeError):
    """Raised when source or adapter evidence violates the pinned case contract."""


def _prepare_output(path: Path) -> Path:
    if path.exists():
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise FileExistsError("output directory must be absent or empty")
    else:
        path.mkdir(parents=True)
    return path


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseError("case config must contain a JSON object")
    if payload.get("analysis_case_id") != CASE_ID:
        raise CaseError("analysis_case_id mismatch")
    return payload


def _download_verified_sources(config: Mapping[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    record_id = config["dataset"]["record_id"]
    metadata_payload = source_audit._request_bytes(source_audit.API_URL.format(record_id=record_id))
    metadata = json.loads(metadata_payload.decode("utf-8"))
    inventory = source_audit._record_files(metadata)
    by_name = {record["filename"]: record for record in inventory}
    payloads: dict[str, bytes] = {}
    verified: list[dict[str, Any]] = []
    for configured in config["files"]:
        name = configured["filename"]
        repository_record = by_name.get(name)
        if repository_record is None:
            raise CaseError(f"pinned file missing from Zenodo inventory: {name}")
        content_url = repository_record.get("content_url")
        if not isinstance(content_url, str) or not content_url.startswith("https://"):
            raise CaseError(f"pinned file has no downloadable HTTPS URL: {name}")
        payload = source_audit._request_bytes(content_url)
        try:
            record = source_audit._verify_bytes(
                payload,
                configured=configured,
                repository_record=repository_record,
            )
        except source_audit.SourceAuditError as exc:
            raise CaseError(str(exc)) from exc
        expected_sha256 = configured.get("verified_sha256")
        if expected_sha256 is not None and record["downloaded_sha256"] != expected_sha256:
            raise CaseError(f"verified SHA-256 drift for {name}")
        payloads[name] = payload
        verified.append(record)
    return payloads, verified


def _parse_source_rows(text: str) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(text), delimiter=","))
    if len(rows) < 4:
        raise CaseError("combined source table has fewer than four rows")
    width = max(len(row) for row in rows)
    return [row + [""] * (width - len(row)) for row in rows]


def adapt_dsc_source(payload: bytes, config: Mapping[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Adapt the exact DSC columns without sorting, interpolation, or exclusion."""
    text, encoding = source_audit._decode_text(payload)
    rows = _parse_source_rows(text)
    binding = config["column_binding"]
    header_count = int(binding["header_row_count"])
    observed_headers = rows[:header_count]
    expected_headers = binding["expected_headers"]
    if observed_headers != expected_headers:
        raise CaseError("source header contract changed")
    if binding.get("sorting_allowed") or binding.get("interpolation_allowed") or binding.get("exclusion_allowed"):
        raise CaseError("case contract must prohibit sorting, interpolation, and exclusion")

    temperature_index = int(binding["temperature_column_index"])
    signal_index = int(binding["signal_column_index"])
    data_rows = rows[header_count:]
    temperature: list[float] = []
    signal: list[float] = []
    for row_number, row in enumerate(data_rows, start=header_count + 1):
        try:
            current_temperature = float(row[temperature_index].strip())
            current_signal = float(row[signal_index].strip())
        except (ValueError, IndexError) as exc:
            raise CaseError(f"non-numeric DSC source row at line {row_number}") from exc
        if not math.isfinite(current_temperature) or not math.isfinite(current_signal):
            raise CaseError(f"non-finite DSC source row at line {row_number}")
        temperature.append(current_temperature)
        signal.append(current_signal)
    if len(temperature) < 7:
        raise CaseError("DSC source contains fewer than seven data rows")
    differences = np.diff(np.asarray(temperature, dtype=float))
    if not np.all(differences > 0):
        raise CaseError("DSC source temperature is not one strictly increasing segment")

    factor = float(binding["source_to_canonical_factor"])
    if binding["source_signal_unit"] != "mW/mg" or binding["canonical_signal_type"] != "heat_flow_w_g":
        raise CaseError("unsupported pinned DSC signal conversion")
    if not math.isclose(factor, 1.0, rel_tol=0.0, abs_tol=0.0):
        raise CaseError("1 mW/mg to W/g conversion must use factor 1.0")
    canonical = pd.DataFrame(
        {
            "temperature_c": np.asarray(temperature, dtype=float),
            "signal": np.asarray(signal, dtype=float) * factor,
        }
    )
    step = float(np.median(differences))
    adapter = {
        "source_encoding": encoding,
        "source_header_rows": observed_headers,
        "source_data_row_count": len(data_rows),
        "canonical_row_count": len(canonical),
        "temperature_column_index": temperature_index,
        "signal_column_index": signal_index,
        "source_signal_unit": binding["source_signal_unit"],
        "canonical_signal_type": binding["canonical_signal_type"],
        "source_to_canonical_factor": factor,
        "conversion_basis": binding["conversion_basis"],
        "temperature_strictly_increasing": True,
        "source_rows_sorted": False,
        "source_rows_interpolated": False,
        "source_rows_excluded": 0,
        "temperature_start_c": float(canonical["temperature_c"].iloc[0]),
        "temperature_end_c": float(canonical["temperature_c"].iloc[-1]),
        "median_temperature_step_c": step,
    }
    return canonical, adapter


def smoothing_span_to_window(
    temperature_c: Sequence[float],
    *,
    span_c: float,
    polyorder: int,
) -> tuple[int, float]:
    """Convert a temperature span to a valid odd Savitzky-Golay window."""
    values = np.asarray(temperature_c, dtype=float)
    if len(values) < 3 or not np.all(np.diff(values) > 0):
        raise CaseError("temperature axis must be strictly increasing")
    if not math.isfinite(span_c) or span_c <= 0:
        raise CaseError("smoothing span must be positive")
    if polyorder < 0:
        raise CaseError("smoothing polyorder must be non-negative")
    median_step = float(np.median(np.diff(values)))
    requested = max(int(round(span_c / median_step)), polyorder + 2)
    if requested % 2 == 0:
        requested += 1
    maximum = len(values) if len(values) % 2 == 1 else len(values) - 1
    window = min(requested, maximum)
    if window <= polyorder:
        raise CaseError("data are too short for requested smoothing configuration")
    actual_span = float((window - 1) * median_step)
    return window, actual_span


def distance_c_to_samples(temperature_c: Sequence[float], distance_c: float) -> int:
    values = np.asarray(temperature_c, dtype=float)
    if len(values) < 2 or not np.all(np.diff(values) > 0):
        raise CaseError("temperature axis must be strictly increasing")
    if not math.isfinite(distance_c) or distance_c <= 0:
        raise CaseError("candidate separation must be positive")
    median_step = float(np.median(np.diff(values)))
    return max(1, int(math.ceil(distance_c / median_step)))


def _analysis_spans(config: Mapping[str, Any]) -> list[tuple[str, float]]:
    analysis = config["analysis"]
    sensitivity = list(analysis["sensitivity_smoothing_spans_c"])
    if len(sensitivity) != 2:
        raise CaseError("case requires exactly two sensitivity smoothing spans")
    return [
        ("primary", float(analysis["primary_smoothing_span_c"])),
        ("sensitivity_1c", float(sensitivity[0])),
        ("sensitivity_5c", float(sensitivity[1])),
    ]


def _run_analyses(
    *,
    canonical_path: Path,
    canonical: pd.DataFrame,
    config: Mapping[str, Any],
    output: Path,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    analysis_config = config["analysis"]
    polyorder = int(analysis_config["smoothing_polyorder"])
    min_distance = distance_c_to_samples(
        canonical["temperature_c"],
        float(analysis_config["minimum_candidate_separation_c"]),
    )
    run_records: list[dict[str, Any]] = []
    sensitivity_tables: list[pd.DataFrame] = []
    for run_id, span_c in _analysis_spans(config):
        run_output = output / "analyses" / run_id
        window, actual_span_c = smoothing_span_to_window(
            canonical["temperature_c"], span_c=span_c, polyorder=polyorder
        )
        result = analyze_thermal(
            canonical_path,
            run_output,
            sample_id=analysis_config["sample_id"],
            measurement_id=f"{analysis_config['measurement_id']}__{run_id}",
            mode="dsc",
            signal_type=config["column_binding"]["canonical_signal_type"],
            endotherm_direction=config["column_binding"]["endotherm_direction"],
            baseline_method=analysis_config["baseline_method"],
            smoothing_window=window,
            smoothing_polyorder=polyorder,
            prominence_fraction=float(analysis_config["prominence_fraction"]),
            min_distance=min_distance,
            acquisition_metadata={
                "atmosphere": config["article"]["atmosphere"],
                "heating_rate_c_min": config["article"]["heating_rate_c_min"],
                "gas_flow_ml_min": config["unresolved_metadata"]["gas_flow_ml_min"],
                "sample_mass_mg": config["unresolved_metadata"]["sample_mass_mg"],
                "crucible_material": config["unresolved_metadata"]["crucible_material"],
                "instrument_model": config["article"]["instrument_model"],
                "calibration_reference": config["unresolved_metadata"][
                    "calibration_reference"
                ],
                "sample_preparation": None,
            },
        )
        manifest_path = write_analysis_manifest(
            [result["analysis_result"]], run_output / "thermal_analysis_manifest.json"
        )
        candidates = result["candidate_table"].copy()
        candidates.insert(0, "run_id", run_id)
        candidates.insert(1, "requested_smoothing_span_c", span_c)
        candidates.insert(2, "smoothing_window_samples", window)
        candidates.insert(3, "actual_smoothing_span_c", actual_span_c)
        sensitivity_tables.append(candidates)
        run_records.append(
            {
                "run_id": run_id,
                "requested_smoothing_span_c": span_c,
                "smoothing_window_samples": window,
                "actual_smoothing_span_c": actual_span_c,
                "minimum_candidate_distance_samples": min_distance,
                "candidate_count": int(len(candidates)),
                "endothermic_candidate_count": int(
                    (candidates["candidate_type"] == "endothermic").sum()
                ),
                "exothermic_candidate_count": int(
                    (candidates["candidate_type"] == "exothermic").sum()
                ),
                "analysis_manifest": str(manifest_path.relative_to(output)),
                "warnings": list(result["analysis_result"].warnings),
            }
        )
    combined = pd.concat(sensitivity_tables, ignore_index=True)
    return run_records, combined


def _write_artifact_manifest(output: Path) -> Path:
    manifest_path = output / "case_artifact_manifest.json"
    records = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        payload = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "artifact_count": len(records),
        "artifacts": records,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def run(config_path: Path, output_dir: Path) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    try:
        config = _load_config(config_path)
        payloads, verified_files = _download_verified_sources(config)
        source_name = "DSC_ElResistance_ThExpansion.csv"
        canonical, adapter = adapt_dsc_source(payloads[source_name], config)
        canonical_dir = output / "canonical"
        canonical_dir.mkdir()
        canonical_path = canonical_dir / "zr15nb_dsc_heating.csv"
        canonical.to_csv(canonical_path, index=False)
        canonical_sha256 = hashlib.sha256(canonical_path.read_bytes()).hexdigest()

        run_records, sensitivity = _run_analyses(
            canonical_path=canonical_path,
            canonical=canonical,
            config=config,
            output=output,
        )
        sensitivity_path = output / "dsc_sensitivity_candidates.csv"
        sensitivity.to_csv(sensitivity_path, index=False)

        summary = {
            "schema_version": "1.0",
            "case_id": CASE_ID,
            "source": {
                "repository": config["dataset"]["repository"],
                "record_id": config["dataset"]["record_id"],
                "doi": config["dataset"]["doi"],
                "version": config["dataset"]["version"],
                "license": config["dataset"]["license"],
                "article_doi": config["article"]["doi"],
                "verified_files": verified_files,
                "raw_source_files_persisted": False,
            },
            "canonical_adapter": {
                **adapter,
                "canonical_path": canonical_path.relative_to(output).as_posix(),
                "canonical_sha256": canonical_sha256,
            },
            "analysis_contract": {
                "mode": "dsc",
                "signal_type": config["column_binding"]["canonical_signal_type"],
                "source_signal_unit": config["column_binding"]["source_signal_unit"],
                "endotherm_direction": config["column_binding"]["endotherm_direction"],
                "baseline_method": config["analysis"]["baseline_method"],
                "prominence_fraction": config["analysis"]["prominence_fraction"],
                "minimum_candidate_separation_c": config["analysis"][
                    "minimum_candidate_separation_c"
                ],
                "parameter_selection_status": config["analysis"][
                    "parameter_selection_status"
                ],
                "article_intervals_used_as_detection_labels": False,
            },
            "analysis_runs": run_records,
            "unresolved_metadata": config["unresolved_metadata"],
            "readiness": {
                "status": "diagnostic_real_dsc_case_completed",
                "source_checksums_verified": True,
                "single_strictly_increasing_heating_segment_verified": True,
                "thermal_analyzer_executed": True,
                "sensitivity_analysis_completed": True,
                "phase_or_reaction_assignment_performed": False,
                "quantitative_enthalpy_validated": False,
                "engineering_release_ready": False,
            },
            "scientific_closeout": {
                "status": "Diagnostic",
                "result": "diagnostic_real_dsc_case_completed",
                "strongest_evidence": (
                    "A checksum-bound public DSC file was adapted through an exact three-row "
                    "header and unit contract, preserved in original order, and analyzed under "
                    "one primary and two predeclared smoothing spans."
                ),
                "primary_limitation": (
                    "The source file is not bound to one of the two reported DSC replicates, and "
                    "sample mass, crucible, gas flow, and calibration reference remain unresolved."
                ),
                "evidence_that_would_change_conclusion": (
                    "Replicate-level acquisition identity, complete calibration and crucible "
                    "metadata, independent event review, and a validated onset or enthalpy protocol."
                ),
                "suitable_for": [
                    "real-data software integration validation",
                    "provenance demonstration",
                    "diagnostic candidate sensitivity review",
                ],
                "not_suitable_for": [
                    "phase identification from DSC alone",
                    "reaction or mechanism assignment",
                    "validated onset or quantitative enthalpy claims",
                    "engineering release decisions",
                ],
            },
        }
        summary_path = output / "case_summary.json"
        report_path = output / "case_validation_report.md"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        report_path.write_text(_build_report(summary, config), encoding="utf-8")
        _write_artifact_manifest(output)
        return summary
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


def _build_report(summary: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    adapter = summary["canonical_adapter"]
    lines = [
        "# Public Zr15Nb DSC Real-Data Case",
        "",
        "**Evidence level:** Diagnostic",
        "",
        f"**Result:** `{summary['readiness']['status']}`",
        "",
        "## Source and adapter",
        "",
        f"- Dataset DOI: `{summary['source']['doi']}`",
        f"- Article DOI: `{summary['source']['article_doi']}`",
        f"- Canonical rows: `{adapter['canonical_row_count']}`",
        f"- Temperature range: `{adapter['temperature_start_c']:.5f}` to "
        f"`{adapter['temperature_end_c']:.5f}` degC",
        f"- Source signal: `{adapter['source_signal_unit']}`",
        "- Canonical signal: `W/g` using the exact identity `1 mW/mg = 1 W/g`",
        "- Source sorting, interpolation, and row exclusion: `none`",
        "- Raw external source files persisted: `false`",
        "",
        "## Analysis runs",
        "",
        "| Run | Requested smoothing span (degC) | Window (samples) | Candidate count |",
        "|---|---:|---:|---:|",
    ]
    for run_record in summary["analysis_runs"]:
        lines.append(
            f"| {run_record['run_id']} | {run_record['requested_smoothing_span_c']:.3g} | "
            f"{run_record['smoothing_window_samples']} | {run_record['candidate_count']} |"
        )
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "The source publication's temperature intervals are retained as contextual literature "
            "information only. They were not used to tune smoothing, prominence, candidate distance, "
            "baseline, candidate type, or candidate acceptance.",
            "",
            "Automatic candidates remain review-required and do not identify phases, reactions, "
            "mechanisms, validated onsets, or quantitative enthalpies. The source file's exact "
            "replicate identity and several acquisition metadata fields remain unresolved.",
            "",
            "## Reported contextual intervals not used as labels",
            "",
        ]
    )
    for interval in config["article"]["thermal_context_intervals_not_detection_labels"]:
        lines.append(
            f"- {interval['process_direction']}: {interval['temperature_start_c']:.0f}–"
            f"{interval['temperature_end_c']:.0f} degC — {interval['description']}"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/public_zr15nb_dsc/case_config.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = run(args.config, args.output)
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports actionable context.
        print(f"public Zr15Nb DSC case failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": summary["readiness"]["status"],
                "canonical_row_count": summary["canonical_adapter"]["canonical_row_count"],
                "candidate_counts": {
                    record["run_id"]: record["candidate_count"]
                    for record in summary["analysis_runs"]
                },
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
