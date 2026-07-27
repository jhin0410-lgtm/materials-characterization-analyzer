"""Long-format TEM image features without particle, phase, or mechanism assignment."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file


def build_tem_feature_records(
    measurements: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build review-required summary features for threshold-detected TEM regions."""
    measurement_id = measurement_id or f"{sample_id}-tem"
    source_path = str(source_file) if source_file is not None else None
    source_hash = sha256_file(source_file) if source_file is not None else None
    method = "otsu_threshold_external_contours"
    quality_flag = "review_required"
    records: list[FeatureRecord] = []

    _append(
        records,
        sample_id,
        measurement_id,
        "detected_region_count",
        len(measurements),
        "count",
        method,
        source_path,
        source_hash,
        preprocessing_id,
        quality_flag,
    )
    if measurements.empty:
        return records

    statistics = (
        ("mean_equivalent_diameter", measurements.get("equivalent_diameter_nm"), "nm", "mean"),
        ("median_equivalent_diameter", measurements.get("equivalent_diameter_nm"), "nm", "median"),
        ("standard_deviation_equivalent_diameter", measurements.get("equivalent_diameter_nm"), "nm", "std"),
        ("detected_area_fraction", measurements.get("area_fraction"), "fraction", "mean"),
        ("total_detected_area", measurements.get("area_nm2"), "nm^2", "sum"),
        ("mean_detected_region_intensity", measurements.get("mean_intensity_raw"), "digital_number", "mean"),
        ("border_touching_region_count", measurements.get("touches_border"), "count", "sum"),
    )
    for feature_name, series, unit, reducer in statistics:
        if series is None:
            continue
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if numeric.empty:
            continue
        if reducer == "mean":
            value = numeric.mean()
        elif reducer == "median":
            value = numeric.median()
        elif reducer == "std":
            value = numeric.std(ddof=1)
        else:
            value = numeric.sum()
        if np.isfinite(float(value)):
            _append(
                records,
                sample_id,
                measurement_id,
                feature_name,
                float(value),
                unit,
                method,
                source_path,
                source_hash,
                preprocessing_id,
                quality_flag,
            )
    return records


def _append(
    records: list[FeatureRecord],
    sample_id: str,
    measurement_id: str,
    feature_name: str,
    value: int | float,
    unit: str,
    method: str,
    source_file: str | None,
    source_sha256: str | None,
    preprocessing_id: str | None,
    quality_flag: str,
) -> None:
    records.append(
        FeatureRecord(
            sample_id=sample_id,
            measurement_id=measurement_id,
            instrument="tem",
            feature_name=feature_name,
            value=value,
            unit=unit,
            method=method,
            source_file=source_file,
            source_sha256=source_sha256,
            preprocessing_id=preprocessing_id,
            quality_flag=quality_flag,
        )
    )
