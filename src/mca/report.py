"""Markdown report generation for integrated XRD, SEM, and EDS summaries."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import ensure_output_dir, write_markdown


def _read_csv_or_empty(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def _format_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 5) -> str:
    if df.empty:
        return "No rows available."

    available_columns = [column for column in columns if column in df.columns]
    if not available_columns:
        return "No matching columns available."

    subset = df.loc[:, available_columns].head(max_rows)
    header = "| " + " | ".join(available_columns) + " |"
    divider = "| " + " | ".join(["---"] * len(available_columns)) + " |"
    rows = [
        "| " + " | ".join(_format_value(value) for value in row) + " |"
        for row in subset.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *rows])


def _xrd_summary(xrd_peaks: pd.DataFrame) -> str:
    if xrd_peaks.empty:
        return "No XRD peaks were detected or no XRD peak table was provided."

    strongest = xrd_peaks.sort_values("intensity", ascending=False).head(3)
    table = _markdown_table(
        strongest,
        ["peak_id", "two_theta_deg", "intensity", "fwhm_deg_2theta"],
        max_rows=3,
    )
    return (
        f"Detected peak count: {len(xrd_peaks)}.\n\n"
        "Strongest detected peaks:\n\n"
        f"{table}\n\n"
        "These peak features can support crystallinity and peak-position review. "
        "No reference database is used here, so phase labels are not assigned."
    )


def _sem_summary(sem_measurements: pd.DataFrame) -> str:
    if sem_measurements.empty:
        return "No SEM regions were detected or no SEM measurements table was provided."

    mean_diameter = sem_measurements["equivalent_diameter_microns"].mean()
    median_diameter = sem_measurements["equivalent_diameter_microns"].median()
    area_fraction = sem_measurements["area_fraction"].iloc[0]
    return (
        f"Detected region count: {len(sem_measurements)}.\n\n"
        f"Mean equivalent diameter: {mean_diameter:.3f} microns.\n\n"
        f"Median equivalent diameter: {median_diameter:.3f} microns.\n\n"
        f"Estimated area fraction: {area_fraction:.3%}.\n\n"
        "The SEM result is threshold-based and should be reviewed against image quality, "
        "contrast, polishing condition, magnification, and segmentation settings."
    )


def _eds_summary(eds_table: pd.DataFrame) -> str:
    if eds_table.empty:
        return "No EDS composition table was provided."

    table = _markdown_table(
        eds_table,
        ["rank_by_weight_percent", "element", "weight_percent", "atomic_percent"],
        max_rows=6,
    )
    return (
        "Composition table sorted by weight percent:\n\n"
        f"{table}\n\n"
        "EDS is used here for elemental composition review. It does not confirm crystal phases by itself."
    )


def generate_report(
    xrd_peak_table_path: str | Path | None,
    sem_measurements_path: str | Path | None,
    eds_composition_table_path: str | Path | None,
    output_dir: str | Path,
    sample_name: str = "Demo or user-provided sample",
) -> Path:
    """Generate a Markdown report from saved XRD, SEM, and EDS result tables."""
    output_dir = ensure_output_dir(output_dir)
    xrd_peaks = _read_csv_or_empty(xrd_peak_table_path)
    sem_measurements = _read_csv_or_empty(sem_measurements_path)
    eds_table = _read_csv_or_empty(eds_composition_table_path)

    content = f"""# Material Characterization Report

## 1. Sample Information

- Sample name: {sample_name}
- Report type: XRD-SEM-EDS integrated analysis support report
- Data note: Demo files in this repository are clearly labeled synthetic/demo data and are not presented as real experimental data.

## 2. XRD Analysis Summary

{_xrd_summary(xrd_peaks)}

## 3. SEM Image Analysis Summary

{_sem_summary(sem_measurements)}

## 4. EDS Composition Summary

{_eds_summary(eds_table)}

## 5. Integrated Interpretation

- XRD is used to review crystallinity, peak positions, peak widths, and optional crystallite size estimates.
- SEM is used to review particle or pore size, cracks, morphology, and microstructure features.
- EDS is used to summarize elemental composition and possible local composition differences.
- Even when EDS reports the presence of elements, crystal phases should be interpreted together with XRD results and appropriate reference information.
- SEM particle size and XRD crystallite size estimate can differ because they describe different physical length scales.

## 6. Limitations

- This v0.1 tool does not assign reference-database phase labels.
- Peak positions alone are not used to assert possible phases.
- Scherrer outputs, when enabled, are crystallite size estimates rather than particle size measurements.
- SEM segmentation is based on simple thresholding, so image quality and threshold conditions can change the result.
- EDS quantification can be affected by light elements, peak overlap, surface roughness, accelerating voltage, detector settings, and sample preparation.
- EDS is for elemental composition analysis and should not be used alone to confirm a crystalline phase.

## 7. Generated Files

- `xrd_pattern_with_peaks.png`
- `xrd_peak_table.csv`
- `sem_overlay.png`
- `sem_particle_size_distribution.png`
- `sem_measurements.csv`
- `eds_composition_table.csv`
- `eds_composition_bar_chart.png`
- `material_characterization_report.md`
"""

    return write_markdown(output_dir / "material_characterization_report.md", content)


