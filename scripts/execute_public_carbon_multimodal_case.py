"""Execute the public carbon case with source decoding and case-level QC.

The TGA-air export is CP1252/ISO-8859 text and contains a short initial
stabilization interval. This module patches only case-study adapters and adds a
review layer that preserves analyzer candidates while separating startup-boundary
artifacts from retained diagnostic candidates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import run_public_carbon_multimodal_case as case
except ImportError:  # Direct `python scripts/...py` execution.
    import run_public_carbon_multimodal_case as case


def read_public_table(path: str | Path) -> tuple[pd.DataFrame, str]:
    source = Path(path)
    failures: list[str] = []
    for encoding in ("utf-8-sig", "cp1252"):
        for separator, delimiter_name in ((";", "semicolon"), ("\t", "tab"), (",", "comma")):
            try:
                frame = pd.read_csv(
                    source,
                    sep=separator,
                    engine="python",
                    encoding=encoding,
                )
            except Exception as exc:  # noqa: BLE001 - report attempted source formats.
                failures.append(f"{encoding}/{delimiter_name}: {exc}")
                continue
            if frame.shape[1] >= 2:
                frame.attrs["source_encoding"] = encoding
                return frame, delimiter_name
    raise ValueError(
        f"Could not parse {source} with supported encodings and delimiters: "
        + " | ".join(failures)
    )


def adapt_public_tga_air_source(
    source_path: str | Path,
    destination: str | Path,
) -> dict[str, object]:
    """Map documented TGA columns and exclude only bounded initial stabilization."""
    source, destination = Path(source_path), Path(destination)
    frame, delimiter = read_public_table(source)
    if frame.shape[1] < 7:
        raise ValueError(f"Documented TGA-air table requires >=7 columns; found {frame.shape[1]}.")

    temperature = case._numeric_column(frame, 0, "temperature")
    time_s = case._numeric_column(frame, 1, "time")
    retention = case._numeric_column(frame, 5, "mass retention percent")
    valid = temperature.notna() & time_s.notna() & retention.notna()
    canonical = pd.DataFrame(
        {
            "temperature_c": temperature[valid],
            "time_s": time_s[valid],
            "signal": retention[valid],
        }
    ).reset_index(drop=True)
    if len(canonical) < 7:
        raise ValueError("Canonical TGA table contains fewer than 7 rows.")

    temperature_diff = np.diff(canonical["temperature_c"].to_numpy(dtype=float))
    stabilization_rows = 0
    if not np.all(temperature_diff > 0):
        last_violation = int(np.flatnonzero(temperature_diff <= 0)[-1])
        candidate_start = last_violation + 1
        excluded = canonical.iloc[:candidate_start]
        remaining = canonical.iloc[candidate_start:].reset_index(drop=True)
        allowed_rows = max(100, int(np.ceil(len(canonical) * 0.05)))
        excluded_span_c = float(
            excluded["temperature_c"].max() - excluded["temperature_c"].min()
        )
        if (
            candidate_start > allowed_rows
            or excluded_span_c > 5.0
            or len(remaining) < 7
            or not np.all(np.diff(remaining["temperature_c"]) > 0)
        ):
            raise ValueError(
                "TGA source contains non-initial nonmonotonic temperature behavior; "
                "cooling, holds, or multisegment programs require explicit segmentation."
            )
        canonical = remaining
        stabilization_rows = candidate_start
    if not np.all(np.diff(canonical["time_s"].to_numpy(dtype=float)) > 0):
        raise ValueError("Selected TGA source time is not strictly increasing.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(destination, index=False)
    record = case._adapter_record(
        source,
        destination,
        frame,
        canonical,
        delimiter,
        {
            str(frame.columns[0]): "temperature_c",
            str(frame.columns[1]): "time_s",
            str(frame.columns[5]): "signal_mass_retention_percent",
        },
        "documented_tga_air_mapping_with_bounded_initial_stabilization_exclusion",
        int((~valid).sum()) + stabilization_rows,
    )
    record.update(
        {
            "source_encoding": frame.attrs.get("source_encoding"),
            "mapping_basis": "Dataset_Raw/ReadMe_Raw.pdf seven-column TGA-air definition",
            "heating_segment_rule": (
                "earliest suffix after <=5 degC initial stabilization, bounded to "
                "max(100 rows, 5 percent), with no sorting or interpolation"
            ),
            "initial_stabilization_rows_excluded": stabilization_rows,
            "canonical_start_temperature_c": float(canonical["temperature_c"].iloc[0]),
            "canonical_end_temperature_c": float(canonical["temperature_c"].iloc[-1]),
        }
    )
    return record


def review_tga_case_candidates(output_dir: str | Path) -> dict[str, int]:
    """Classify, but never delete, TGA candidates using explicit boundary-artifact rules."""
    root = Path(output_dir)
    candidate_path = root / "analyses" / "tga" / "thermal_event_candidates.csv"
    processed_path = root / "analyses" / "tga" / "thermal_processed_data.csv"
    candidates = pd.read_csv(candidate_path)
    processed = pd.read_csv(processed_path)
    temperature = pd.to_numeric(processed["temperature_c"], errors="raise").to_numpy(dtype=float)
    start, end = float(temperature[0]), float(temperature[-1])
    span = end - start
    median_step = float(np.median(np.diff(temperature)))
    boundary_limit = start + max(1.0, 0.005 * span)
    minimum_width_c = max(0.1, 2.0 * median_step)

    reviewed = candidates.copy()
    statuses: list[str] = []
    reasons: list[str] = []
    for row in reviewed.itertuples(index=False):
        near_start = float(row.temperature_c) <= boundary_limit
        tiny_mass_change = abs(float(row.mass_change_within_fwhm_percent)) < 0.1
        subresolution_width = float(row.fwhm_c) < minimum_width_c
        if near_start and (tiny_mass_change or subresolution_width):
            statuses.append("rejected_startup_boundary_artifact")
            reasons.append(
                "candidate lies in the initial boundary zone and has <0.1 percent mass change "
                "or sub-resolution FWHM"
            )
        else:
            statuses.append("retained_review_required")
            reasons.append("not rejected by the explicit startup-boundary artifact rule")
    reviewed["case_review_status"] = statuses
    reviewed["case_review_reason"] = reasons
    reviewed["boundary_limit_c"] = boundary_limit
    reviewed["minimum_width_c"] = minimum_width_c
    review_path = root / "analyses" / "tga" / "tga_case_candidate_review.csv"
    reviewed.to_csv(review_path, index=False)

    retained = reviewed[reviewed["case_review_status"] == "retained_review_required"]
    rejected = reviewed[reviewed["case_review_status"] != "retained_review_required"]
    retained_text = ", ".join(f"{value:.3g} degC" for value in retained["temperature_c"])
    rejected_text = ", ".join(f"{value:.3g} degC" for value in rejected["temperature_c"])
    report_path = root / "case_validation_report.md"
    report = report_path.read_text(encoding="utf-8")
    replacement = (
        f"- **TGA-air:** {len(retained)} retained review-required candidate(s): "
        f"{retained_text or 'none'}. Raw analyzer candidates remain preserved in the source table."
    )
    lines = [replacement if line.startswith("- **TGA-air:**") else line for line in report.splitlines()]
    lines.extend(
        [
            "",
            "## TGA case-level candidate review",
            "",
            f"- Retained: `{len(retained)}` candidate(s) at {retained_text or 'none'}.",
            f"- Rejected as startup-boundary artifacts: `{len(rejected)}` candidate(s) at "
            f"{rejected_text or 'none'}.",
            f"- Boundary zone ended at `{boundary_limit:.3f} degC`; minimum descriptive width was "
            f"`{minimum_width_c:.3f} degC`.",
            "- The original analyzer candidate table was not edited or overwritten; the decision is "
            "stored separately in `analyses/tga/tga_case_candidate_review.csv`.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_path = root / "case_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    counts = {
        "raw_candidate_count": int(len(reviewed)),
        "retained_review_required_count": int(len(retained)),
        "rejected_startup_boundary_artifact_count": int(len(rejected)),
    }
    summary["tga_case_candidate_review"] = counts
    summary["tga_case_candidate_review_path"] = str(review_path)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return counts


case._read_delimited_table = read_public_table
case.adapt_tga_air_source = adapt_public_tga_air_source


def main(argv: list[str] | None = None) -> int:
    args = case.build_parser().parse_args(argv)
    try:
        summary = case.run_case(args.config, args.discovery, args.output)
        summary["tga_case_candidate_review"] = review_tga_case_candidates(args.output)
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports actionable context.
        print(f"public carbon case failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
