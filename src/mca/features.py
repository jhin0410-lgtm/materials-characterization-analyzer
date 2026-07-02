"""Sample-level feature extraction helpers for XRD, SEM, and EDS outputs.

The functions in this module summarize existing analysis result tables into a
single row that can be used later for comparison or modeling workflows. They do
not train models, assign phases, or make material-property conclusions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .utils import ensure_output_dir


CRYSTALLITE_SIZE_COLUMNS = (
    "crystallite_size_estimate_nm",
    "estimated_crystallite_size_nm",
    "crystallite_size_estimate_same_unit_as_wavelength",
)


def extract_xrd_features(peak_table: pd.DataFrame | None) -> dict[str, Any]:
    """Extract sample-level XRD features from a peak table."""
    features: dict[str, Any] = {
        "xrd_number_of_peaks": 0,
        "xrd_main_peak_two_theta": np.nan,
        "xrd_main_peak_intensity": np.nan,
        "xrd_mean_fwhm_deg_2theta": np.nan,
        "xrd_median_fwhm_deg_2theta": np.nan,
        "xrd_min_two_theta": np.nan,
        "xrd_max_two_theta": np.nan,
        "xrd_estimated_crystallite_size_mean_nm": np.nan,
    }

    if peak_table is None or peak_table.empty:
        return features

    table = peak_table.copy()
    features["xrd_number_of_peaks"] = int(len(table))

    if "two_theta_deg" in table:
        two_theta = pd.to_numeric(table["two_theta_deg"], errors="coerce")
        features["xrd_min_two_theta"] = _mean_or_nan(two_theta, reducer="min")
        features["xrd_max_two_theta"] = _mean_or_nan(two_theta, reducer="max")

    if "intensity" in table and "two_theta_deg" in table:
        intensities = pd.to_numeric(table["intensity"], errors="coerce")
        if intensities.notna().any():
            main_index = intensities.idxmax()
            features["xrd_main_peak_intensity"] = float(intensities.loc[main_index])
            features["xrd_main_peak_two_theta"] = float(pd.to_numeric(table.loc[[main_index], "two_theta_deg"], errors="coerce").iloc[0])

    if "fwhm_deg_2theta" in table:
        fwhm = pd.to_numeric(table["fwhm_deg_2theta"], errors="coerce")
        features["xrd_mean_fwhm_deg_2theta"] = _mean_or_nan(fwhm)
        features["xrd_median_fwhm_deg_2theta"] = _median_or_nan(fwhm)

    crystallite_column = _first_existing_column(table, CRYSTALLITE_SIZE_COLUMNS)
    if crystallite_column:
        crystallite_sizes = pd.to_numeric(table[crystallite_column], errors="coerce")
        features["xrd_estimated_crystallite_size_mean_nm"] = _mean_or_nan(crystallite_sizes)

    return features


def extract_sem_features(measurements: pd.DataFrame | None) -> dict[str, Any]:
    """Extract sample-level SEM features from threshold-based measurements."""
    features: dict[str, Any] = {
        "sem_detected_region_count": 0,
        "sem_particle_count": 0,
        "sem_mean_equivalent_diameter_um": np.nan,
        "sem_median_equivalent_diameter_um": np.nan,
        "sem_std_equivalent_diameter_um": np.nan,
        "sem_area_fraction": np.nan,
        "sem_total_detected_area_um2": 0.0,
    }

    if measurements is None or measurements.empty:
        return features

    table = measurements.copy()
    count = int(len(table))
    features["sem_detected_region_count"] = count
    features["sem_particle_count"] = count

    if "equivalent_diameter_microns" in table:
        diameters = pd.to_numeric(table["equivalent_diameter_microns"], errors="coerce")
        features["sem_mean_equivalent_diameter_um"] = _mean_or_nan(diameters)
        features["sem_median_equivalent_diameter_um"] = _median_or_nan(diameters)
        features["sem_std_equivalent_diameter_um"] = _std_or_nan(diameters)

    if "area_fraction" in table:
        area_fraction = pd.to_numeric(table["area_fraction"], errors="coerce")
        features["sem_area_fraction"] = _mean_or_nan(area_fraction)

    if "area_microns2" in table:
        areas = pd.to_numeric(table["area_microns2"], errors="coerce")
        features["sem_total_detected_area_um2"] = float(areas.sum(skipna=True))

    return features


def extract_eds_features(composition_table: pd.DataFrame | None) -> dict[str, Any]:
    """Extract sample-level EDS composition features."""
    features: dict[str, Any] = {
        "eds_number_of_elements": 0,
        "eds_top_element": "",
        "eds_top_element_weight_percent": np.nan,
        "eds_total_weight_percent": np.nan,
        "eds_total_atomic_percent": np.nan,
    }

    if composition_table is None or composition_table.empty:
        return features

    table = composition_table.copy()
    table["element"] = table.get("element", pd.Series(dtype=object)).astype(str).str.strip()
    table["weight_percent"] = pd.to_numeric(table.get("weight_percent"), errors="coerce")
    table["atomic_percent"] = pd.to_numeric(table.get("atomic_percent"), errors="coerce")
    table = table[(table["element"] != "") & (table["weight_percent"].notna() | table["atomic_percent"].notna())]

    if table.empty:
        return features

    grouped = (
        table.groupby("element", as_index=False)[["weight_percent", "atomic_percent"]]
        .sum(min_count=1)
        .sort_values("weight_percent", ascending=False, na_position="last")
        .reset_index(drop=True)
    )

    features["eds_number_of_elements"] = int(len(grouped))
    top = grouped.iloc[0]
    features["eds_top_element"] = str(top["element"])
    features["eds_top_element_weight_percent"] = _float_or_nan(top["weight_percent"])
    features["eds_total_weight_percent"] = _float_or_nan(grouped["weight_percent"].sum(skipna=True))
    features["eds_total_atomic_percent"] = _float_or_nan(grouped["atomic_percent"].sum(skipna=True))

    for row in grouped.itertuples(index=False):
        label = _safe_feature_label(str(row.element))
        features[f"eds_wt_{label}"] = _float_or_nan(row.weight_percent)
        features[f"eds_at_{label}"] = _float_or_nan(row.atomic_percent)

    return features


def combine_sample_features(
    sample_id: str,
    xrd_peak_table: pd.DataFrame | None = None,
    sem_measurements: pd.DataFrame | None = None,
    eds_composition_table: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Combine XRD, SEM, and EDS features into one sample-level row."""
    features: dict[str, Any] = {"sample_id": sample_id}
    features.update(extract_xrd_features(xrd_peak_table))
    features.update(extract_sem_features(sem_measurements))
    features.update(extract_eds_features(eds_composition_table))
    return features


def build_sample_features_table(
    sample_id: str,
    xrd_peak_table: pd.DataFrame | None = None,
    sem_measurements: pd.DataFrame | None = None,
    eds_composition_table: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a single-row DataFrame of sample-level features."""
    return pd.DataFrame(
        [
            combine_sample_features(
                sample_id=sample_id,
                xrd_peak_table=xrd_peak_table,
                sem_measurements=sem_measurements,
                eds_composition_table=eds_composition_table,
            )
        ]
    )


def save_sample_features(features: dict[str, Any] | pd.DataFrame, output_dir: str | Path) -> Path:
    """Save sample-level features to ``sample_features.csv``."""
    output_path = ensure_output_dir(output_dir) / "sample_features.csv"
    feature_table = features if isinstance(features, pd.DataFrame) else pd.DataFrame([features])
    feature_table.to_csv(output_path, index=False)
    return output_path


def default_sample_id_from_inputs(*paths: str | Path | None) -> str:
    """Return a conservative sample id derived from the first provided input path."""
    for path in paths:
        if path:
            stem = Path(path).stem.strip()
            if stem:
                return stem
    return "sample"


def _first_existing_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _mean_or_nan(series: pd.Series, reducer: str = "mean") -> float:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return float("nan")
    if reducer == "min":
        return float(numeric.min())
    if reducer == "max":
        return float(numeric.max())
    return float(numeric.mean())


def _median_or_nan(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    return float(numeric.median()) if not numeric.empty else float("nan")


def _std_or_nan(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    return float(numeric.std(ddof=1)) if len(numeric) > 1 else float("nan")


def _float_or_nan(value: Any) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else float("nan")


def _safe_feature_label(label: str) -> str:
    safe = re.sub(r"\W+", "_", label.strip()).strip("_")
    if not safe:
        return "unknown"
    if safe[0].isdigit():
        return f"el_{safe}"
    return safe
