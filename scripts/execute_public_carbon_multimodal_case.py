"""Execute the public carbon case with source-specific decoding and TGA segmentation.

The dataset TGA-air export is CP1252/ISO-8859 text and includes a short initial
temperature-stabilization interval before the strictly increasing heating ramp.
This entry point patches only the case-study source adapter; instrument analyzers
and their public contracts remain unchanged.
"""

from __future__ import annotations

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
            except Exception as exc:  # noqa: BLE001 - report every attempted source format.
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


case._read_delimited_table = read_public_table
case.adapt_tga_air_source = adapt_public_tga_air_source


def main(argv: list[str] | None = None) -> int:
    return case.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
