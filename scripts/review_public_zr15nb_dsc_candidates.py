"""Review public Zr15Nb DSC candidates across predeclared smoothing spans.

The review never edits analyzer candidate tables. Primary candidates are matched
one-to-one to same-direction candidates from the two sensitivity runs using the
configured temperature tolerance. Temperature robustness and diagnostic-area
sign consistency are reported separately; no candidate is assigned to a phase
or reaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

REQUIRED_RUNS = ("primary", "sensitivity_1c", "sensitivity_5c")


class ReviewError(RuntimeError):
    """Raised when sensitivity evidence does not satisfy the review contract."""


def _directional_area_consistent(candidate_type: str, enthalpy: Any) -> bool:
    if enthalpy is None or not math.isfinite(float(enthalpy)):
        return False
    value = float(enthalpy)
    return value > 0 if candidate_type == "endothermic" else value < 0


def review_candidates(table: pd.DataFrame, *, tolerance_c: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "run_id",
        "candidate_id",
        "candidate_type",
        "temperature_c",
        "enthalpy_within_fwhm_j_g",
    }
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ReviewError(f"candidate table is missing columns: {', '.join(missing)}")
    if not math.isfinite(tolerance_c) or tolerance_c <= 0:
        raise ReviewError("temperature tolerance must be positive")
    observed_runs = set(table["run_id"].astype(str))
    if observed_runs != set(REQUIRED_RUNS):
        raise ReviewError("candidate table must contain exactly the three configured runs")
    if not set(table["candidate_type"].astype(str)).issubset({"endothermic", "exothermic"}):
        raise ReviewError("candidate_type contains unsupported values")

    primary = table[table["run_id"] == "primary"].copy().sort_values(
        ["temperature_c", "candidate_type"]
    )
    used: dict[str, set[int]] = {run_id: set() for run_id in REQUIRED_RUNS[1:]}
    review_rows: list[dict[str, Any]] = []
    for primary_row in primary.itertuples(index=False):
        candidate_type = str(primary_row.candidate_type)
        temperatures = [float(primary_row.temperature_c)]
        area_flags = [
            _directional_area_consistent(
                candidate_type, primary_row.enthalpy_within_fwhm_j_g
            )
        ]
        record: dict[str, Any] = {
            "primary_candidate_id": int(primary_row.candidate_id),
            "candidate_type": candidate_type,
            "primary_temperature_c": float(primary_row.temperature_c),
            "primary_diagnostic_area_direction_consistent": area_flags[0],
        }
        all_matched = True
        for run_id in REQUIRED_RUNS[1:]:
            subset = table[
                (table["run_id"] == run_id)
                & (table["candidate_type"] == candidate_type)
                & (~table.index.isin(used[run_id]))
            ].copy()
            if subset.empty:
                match = None
            else:
                subset["absolute_delta_c"] = (
                    subset["temperature_c"].astype(float) - float(primary_row.temperature_c)
                ).abs()
                nearest_index = int(subset["absolute_delta_c"].idxmin())
                nearest = subset.loc[nearest_index]
                match = nearest if float(nearest["absolute_delta_c"]) <= tolerance_c else None
            prefix = run_id
            if match is None:
                all_matched = False
                record[f"{prefix}_candidate_id"] = None
                record[f"{prefix}_temperature_c"] = None
                record[f"{prefix}_delta_from_primary_c"] = None
                record[f"{prefix}_diagnostic_area_direction_consistent"] = False
                continue
            used[run_id].add(int(match.name))
            match_temperature = float(match["temperature_c"])
            consistent = _directional_area_consistent(
                candidate_type, match["enthalpy_within_fwhm_j_g"]
            )
            temperatures.append(match_temperature)
            area_flags.append(consistent)
            record[f"{prefix}_candidate_id"] = int(match["candidate_id"])
            record[f"{prefix}_temperature_c"] = match_temperature
            record[f"{prefix}_delta_from_primary_c"] = (
                match_temperature - float(primary_row.temperature_c)
            )
            record[f"{prefix}_diagnostic_area_direction_consistent"] = consistent

        maximum_spread = max(temperatures) - min(temperatures)
        area_consistent = all(area_flags) and len(area_flags) == len(REQUIRED_RUNS)
        if not all_matched:
            status = "smoothing_sensitive_review_required"
        elif maximum_spread > tolerance_c:
            status = "temperature_spread_review_required"
        elif not area_consistent:
            status = "stable_temperature_area_direction_review_required"
        else:
            status = "stable_temperature_review_required"
        record.update(
            {
                "all_runs_matched": all_matched,
                "maximum_temperature_spread_c": maximum_spread,
                "all_runs_diagnostic_area_direction_consistent": area_consistent,
                "case_review_status": status,
            }
        )
        review_rows.append(record)

    unmatched_rows: list[pd.DataFrame] = []
    for run_id in REQUIRED_RUNS[1:]:
        subset = table[(table["run_id"] == run_id) & (~table.index.isin(used[run_id]))].copy()
        if not subset.empty:
            unmatched_rows.append(subset)
    unmatched = (
        pd.concat(unmatched_rows, ignore_index=True)
        if unmatched_rows
        else table.iloc[0:0].copy()
    )
    return pd.DataFrame(review_rows), unmatched


def _write_manifest(output: Path) -> Path:
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
        "case_id": "public_zr15nb_dsc_real_data_case",
        "artifact_count": len(records),
        "artifacts": records,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def run(config_path: Path, result_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tolerance = float(config["analysis"]["robustness_temperature_tolerance_c"])
    table_path = result_dir / "dsc_sensitivity_candidates.csv"
    summary_path = result_dir / "case_summary.json"
    report_path = result_dir / "case_validation_report.md"
    if not table_path.is_file() or not summary_path.is_file() or not report_path.is_file():
        raise FileNotFoundError("completed DSC case outputs are required")
    table = pd.read_csv(table_path)
    reviewed, unmatched = review_candidates(table, tolerance_c=tolerance)
    review_path = result_dir / "dsc_candidate_robustness.csv"
    unmatched_path = result_dir / "dsc_unmatched_sensitivity_candidates.csv"
    reviewed.to_csv(review_path, index=False)
    unmatched.to_csv(unmatched_path, index=False)

    status_counts = {
        str(key): int(value)
        for key, value in reviewed["case_review_status"].value_counts().sort_index().items()
    }
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidate_robustness"] = {
        "matching_basis": "primary-anchored one-to-one same-direction nearest-temperature matching",
        "temperature_tolerance_c": tolerance,
        "primary_candidate_count": int(len(reviewed)),
        "all_runs_matched_count": int(reviewed["all_runs_matched"].sum()),
        "all_runs_area_direction_consistent_count": int(
            reviewed["all_runs_diagnostic_area_direction_consistent"].sum()
        ),
        "unmatched_sensitivity_candidate_count": int(len(unmatched)),
        "status_counts": status_counts,
        "raw_analyzer_candidate_tables_modified": False,
        "candidate_acceptance_or_rejection_performed": False,
        "phase_or_reaction_labels_assigned": False,
        "review_table": review_path.name,
        "unmatched_table": unmatched_path.name,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    report = report_path.read_text(encoding="utf-8").rstrip()
    lines = [
        report,
        "",
        "## Candidate smoothing-sensitivity review",
        "",
        f"- Primary candidates: `{len(reviewed)}`",
        f"- Matched in both sensitivity runs: `{int(reviewed['all_runs_matched'].sum())}`",
        f"- Unmatched sensitivity candidates: `{len(unmatched)}`",
        f"- Matching tolerance: `{tolerance:.3g} degC`",
        "- Analyzer candidate tables modified: `false`",
        "- Candidate acceptance or rejection performed: `false`",
        "",
        "| Type | Primary temperature (degC) | Maximum three-run spread (degC) | Review status |",
        "|---|---:|---:|---|",
    ]
    for row in reviewed.itertuples(index=False):
        lines.append(
            f"| {row.candidate_type} | {row.primary_temperature_c:.5g} | "
            f"{row.maximum_temperature_spread_c:.5g} | `{row.case_review_status}` |"
        )
    lines.extend(
        [
            "",
            "Temperature stability across smoothing spans does not establish phase or reaction "
            "identity. A directionally inconsistent diagnostic within-FWHM area is retained as a "
            "quality flag rather than silently relabelled or removed.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    _write_manifest(result_dir)
    return summary["candidate_robustness"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/public_zr15nb_dsc/case_config.json"),
    )
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = run(args.config, args.result)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
