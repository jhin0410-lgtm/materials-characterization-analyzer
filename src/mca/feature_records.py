"""Long-format feature export for characterization result tables.

The exported rows are numeric, unit-aware, and provenance-aware. They summarize
existing analysis outputs without assigning phases, compounds, or mechanisms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file
from .utils import ensure_output_dir

LONG_FEATURE_COLUMNS = [
    "sample_id",
    "measurement_id",
    "instrument",
    "feature_name",
    "feature_label",
    "value",
    "unit",
    "method",
    "source_file",
    "source_sha256",
    "preprocessing_id",
    "quality_flag",
]


def build_xrd_feature_records(
    peak_table: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build sample-level XRD peak features without phase assignment."""
    measurement_id = measurement_id or f"{sample_id}-xrd"
    source_path, source_hash = _source_context(source_file)
    records: list[FeatureRecord] = []

    _append_record(
        records,
        sample_id=sample_id,
        measurement_id=measurement_id,
        instrument="xrd",
        feature_name="detected_peak_count",
        value=int(len(peak_table)),
        unit="count",
        method="scipy_find_peaks",
        source_file=source_path,
        source_sha256=source_hash,
        preprocessing_id=preprocessing_id,
    )
    if peak_table.empty:
        return records

    two_theta = _numeric_column(peak_table, "two_theta_deg")
    intensity = _numeric_column(peak_table, "intensity")
    fwhm = _numeric_column(peak_table, "fwhm_deg_2theta")

    valid_main = intensity.notna() & two_theta.notna()
    if valid_main.any():
        main_index = intensity[valid_main].idxmax()
        _append_record(
            records,
            sample_id=sample_id,
            measurement_id=measurement_id,
            instrument="xrd",
            feature_name="main_peak_two_theta",
            value=float(two_theta.loc[main_index]),
            unit="deg_2theta",
            method="maximum_detected_peak_intensity",
            source_file=source_path,
            source_sha256=source_hash,
            preprocessing_id=preprocessing_id,
        )
        _append_record(
            records,
            sample_id=sample_id,
            measurement_id=measurement_id,
            instrument="xrd",
            feature_name="main_peak_intensity",
            value=float(intensity.loc[main_index]),
            unit="a.u.",
            method="maximum_detected_peak_intensity",
            source_file=source_path,
            source_sha256=source_hash,
            preprocessing_id=preprocessing_id,
        )

    _append_statistic(records, sample_id, measurement_id, "xrd", "mean_fwhm", fwhm.mean(), "deg_2theta", "peak_widths_half_height", source_path, source_hash, preprocessing_id)
    _append_statistic(records, sample_id, measurement_id, "xrd", "median_fwhm", fwhm.median(), "deg_2theta", "peak_widths_half_height", source_path, source_hash, preprocessing_id)
    _append_statistic(records, sample_id, measurement_id, "xrd", "minimum_two_theta", two_theta.min(), "deg_2theta", "detected_peak_range", source_path, source_hash, preprocessing_id)
    _append_statistic(records, sample_id, measurement_id, "xrd", "maximum_two_theta", two_theta.max(), "deg_2theta", "detected_peak_range", source_path, source_hash, preprocessing_id)

    crystallite_columns = (
        ("crystallite_size_estimate_nm", "nm", "review_required"),
        ("estimated_crystallite_size_nm", "nm", "review_required"),
        (
            "crystallite_size_estimate_same_unit_as_wavelength",
            "same_as_wavelength",
            "unit_unresolved",
        ),
    )
    for column, unit, quality_flag in crystallite_columns:
        if column in peak_table.columns:
            values = _numeric_column(peak_table, column)
            _append_statistic(
                records,
                sample_id,
                measurement_id,
                "xrd",
                "mean_scherrer_crystallite_size_estimate",
                values.mean(),
                unit,
                "scherrer_estimate",
                source_path,
                source_hash,
                preprocessing_id,
                quality_flag=quality_flag,
            )
            break

    return records


def build_sem_feature_records(
    measurements: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build threshold-derived SEM summary features requiring manual review."""
    measurement_id = measurement_id or f"{sample_id}-sem"
    source_path, source_hash = _source_context(source_file)
    records: list[FeatureRecord] = []
    method = "otsu_threshold_external_contours"
    quality_flag = "review_required"

    _append_record(
        records,
        sample_id=sample_id,
        measurement_id=measurement_id,
        instrument="sem",
        feature_name="detected_region_count",
        value=int(len(measurements)),
        unit="count",
        method=method,
        source_file=source_path,
        source_sha256=source_hash,
        preprocessing_id=preprocessing_id,
        quality_flag=quality_flag,
    )
    if measurements.empty:
        return records

    diameter = _numeric_column(measurements, "equivalent_diameter_microns")
    area = _numeric_column(measurements, "area_microns2")
    area_fraction = _numeric_column(measurements, "area_fraction")

    _append_statistic(records, sample_id, measurement_id, "sem", "mean_equivalent_diameter", diameter.mean(), "um", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
    _append_statistic(records, sample_id, measurement_id, "sem", "median_equivalent_diameter", diameter.median(), "um", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
    _append_statistic(records, sample_id, measurement_id, "sem", "standard_deviation_equivalent_diameter", diameter.std(ddof=1), "um", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
    _append_statistic(records, sample_id, measurement_id, "sem", "detected_area_fraction", area_fraction.mean(), "fraction", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
    _append_statistic(records, sample_id, measurement_id, "sem", "total_detected_area", area.sum(min_count=1), "um^2", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
    return records


def build_eds_feature_records(
    composition_table: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build numeric EDS composition features without phase interpretation."""
    measurement_id = measurement_id or f"{sample_id}-eds"
    source_path, source_hash = _source_context(source_file)
    records: list[FeatureRecord] = []
    method = "reported_eds_composition"
    quality_flag = "review_required"

    table = composition_table.copy()
    table["element"] = table.get("element", pd.Series(index=table.index, dtype=object)).astype(str).str.strip()
    table["weight_percent"] = _numeric_column(table, "weight_percent")
    table["atomic_percent"] = _numeric_column(table, "atomic_percent")
    table = table[(table["element"] != "") & (table["weight_percent"].notna() | table["atomic_percent"].notna())]
    grouped = (
        table.groupby("element", as_index=False)[["weight_percent", "atomic_percent"]]
        .sum(min_count=1)
        .sort_values("weight_percent", ascending=False, na_position="last")
        .reset_index(drop=True)
    )

    _append_record(
        records,
        sample_id=sample_id,
        measurement_id=measurement_id,
        instrument="eds",
        feature_name="reported_element_count",
        value=int(len(grouped)),
        unit="count",
        method=method,
        source_file=source_path,
        source_sha256=source_hash,
        preprocessing_id=preprocessing_id,
        quality_flag=quality_flag,
    )

    for rank, row in enumerate(grouped.itertuples(index=False), start=1):
        element = str(row.element)
        _append_record(
            records,
            sample_id=sample_id,
            measurement_id=measurement_id,
            instrument="eds",
            feature_name="rank_by_weight_percent",
            feature_label=element,
            value=rank,
            unit="rank",
            method=method,
            source_file=source_path,
            source_sha256=source_hash,
            preprocessing_id=preprocessing_id,
            quality_flag=quality_flag,
        )
        _append_statistic(records, sample_id, measurement_id, "eds", "element_weight_percent", row.weight_percent, "percent", method, source_path, source_hash, preprocessing_id, feature_label=element, quality_flag=quality_flag)
        _append_statistic(records, sample_id, measurement_id, "eds", "element_atomic_percent", row.atomic_percent, "percent", method, source_path, source_hash, preprocessing_id, feature_label=element, quality_flag=quality_flag)

    if not grouped.empty:
        _append_statistic(records, sample_id, measurement_id, "eds", "total_reported_weight_percent", grouped["weight_percent"].sum(min_count=1), "percent", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
        _append_statistic(records, sample_id, measurement_id, "eds", "total_reported_atomic_percent", grouped["atomic_percent"].sum(min_count=1), "percent", method, source_path, source_hash, preprocessing_id, quality_flag=quality_flag)
    return records


def build_characterization_feature_records(
    *,
    sample_id: str,
    xrd_peak_table: pd.DataFrame | None = None,
    sem_measurements: pd.DataFrame | None = None,
    eds_composition_table: pd.DataFrame | None = None,
    source_files: Mapping[str, str | Path | None] | None = None,
    measurement_ids: Mapping[str, str] | None = None,
    preprocessing_ids: Mapping[str, str] | None = None,
) -> list[FeatureRecord]:
    """Combine available instrument summaries into one stable long-format list."""
    source_files = source_files or {}
    measurement_ids = measurement_ids or {}
    preprocessing_ids = preprocessing_ids or {}
    records: list[FeatureRecord] = []

    if xrd_peak_table is not None:
        records.extend(
            build_xrd_feature_records(
                xrd_peak_table,
                sample_id=sample_id,
                measurement_id=measurement_ids.get("xrd"),
                source_file=source_files.get("xrd"),
                preprocessing_id=preprocessing_ids.get("xrd"),
            )
        )
    if sem_measurements is not None:
        records.extend(
            build_sem_feature_records(
                sem_measurements,
                sample_id=sample_id,
                measurement_id=measurement_ids.get("sem"),
                source_file=source_files.get("sem"),
                preprocessing_id=preprocessing_ids.get("sem"),
            )
        )
    if eds_composition_table is not None:
        records.extend(
            build_eds_feature_records(
                eds_composition_table,
                sample_id=sample_id,
                measurement_id=measurement_ids.get("eds"),
                source_file=source_files.get("eds"),
                preprocessing_id=preprocessing_ids.get("eds"),
            )
        )
    return records


def records_to_frame(records: list[FeatureRecord]) -> pd.DataFrame:
    """Convert feature records into a DataFrame with a stable column order."""
    return pd.DataFrame([record.to_dict() for record in records], columns=LONG_FEATURE_COLUMNS)


def save_feature_records(
    records: list[FeatureRecord],
    output_dir: str | Path,
    filename: str = "characterization_features_long.csv",
) -> Path:
    """Save long-format feature records to CSV."""
    output_path = ensure_output_dir(output_dir) / filename
    records_to_frame(records).to_csv(output_path, index=False)
    return output_path


def _source_context(source_file: str | Path | None) -> tuple[str | None, str | None]:
    if source_file is None:
        return None, None
    path = Path(source_file)
    return str(path), sha256_file(path)


def _numeric_column(table: pd.DataFrame, column: str) -> pd.Series:
    if column not in table.columns:
        return pd.Series(np.nan, index=table.index, dtype=float)
    return pd.to_numeric(table[column], errors="coerce")


def _append_statistic(
    records: list[FeatureRecord],
    sample_id: str,
    measurement_id: str,
    instrument: str,
    feature_name: str,
    value: object,
    unit: str,
    method: str,
    source_file: str | None,
    source_sha256: str | None,
    preprocessing_id: str | None,
    *,
    feature_label: str | None = None,
    quality_flag: str = "ok",
) -> None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or not np.isfinite(float(numeric)):
        return
    _append_record(
        records,
        sample_id=sample_id,
        measurement_id=measurement_id,
        instrument=instrument,
        feature_name=feature_name,
        feature_label=feature_label,
        value=float(numeric),
        unit=unit,
        method=method,
        source_file=source_file,
        source_sha256=source_sha256,
        preprocessing_id=preprocessing_id,
        quality_flag=quality_flag,
    )


def _append_record(records: list[FeatureRecord], **kwargs: object) -> None:
    records.append(FeatureRecord(**kwargs))
