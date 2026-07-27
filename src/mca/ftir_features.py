"""Long-format FTIR feature records without functional-group or material assignment."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file


def build_ftir_feature_records(
    candidate_table: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build review-required descriptive FTIR candidate features."""
    measurement_id = measurement_id or f"{sample_id}-ftir"
    source_path, source_hash = _source_context(source_file)
    method = "baseline_corrected_absorbance_scipy_find_peaks"
    quality_flag = "review_required"
    records: list[FeatureRecord] = []

    _append(
        records,
        sample_id,
        measurement_id,
        "detected_candidate_count",
        len(candidate_table),
        "count",
        method,
        source_path,
        source_hash,
        preprocessing_id,
        quality_flag=quality_flag,
    )
    if candidate_table.empty:
        return records

    wavenumber = _numeric_column(candidate_table, "wavenumber_cm_1")
    intensity = _numeric_column(candidate_table, "processed_absorbance")
    fwhm = _numeric_column(candidate_table, "fwhm_cm_1")
    area = _numeric_column(candidate_table, "area_within_fwhm_absorbance_cm_1")

    valid_main = wavenumber.notna() & intensity.notna()
    if valid_main.any():
        main_index = intensity[valid_main].idxmax()
        _append(
            records,
            sample_id,
            measurement_id,
            "main_candidate_wavenumber",
            wavenumber.loc[main_index],
            "cm^-1",
            "maximum_processed_candidate_absorbance",
            source_path,
            source_hash,
            preprocessing_id,
            quality_flag=quality_flag,
        )
        _append(
            records,
            sample_id,
            measurement_id,
            "main_candidate_processed_absorbance",
            intensity.loc[main_index],
            "absorbance",
            "maximum_processed_candidate_absorbance",
            source_path,
            source_hash,
            preprocessing_id,
            quality_flag=quality_flag,
        )

    for name, statistic, unit in (
        ("mean_candidate_fwhm", fwhm.mean(), "cm^-1"),
        ("median_candidate_fwhm", fwhm.median(), "cm^-1"),
        ("total_within_fwhm_area", area.sum(min_count=1), "absorbance*cm^-1"),
    ):
        _append(
            records,
            sample_id,
            measurement_id,
            name,
            statistic,
            unit,
            method,
            source_path,
            source_hash,
            preprocessing_id,
            quality_flag=quality_flag,
        )

    for row in candidate_table.itertuples(index=False):
        label = f"candidate_{int(row.candidate_id)}"
        for name, value, unit in (
            ("candidate_wavenumber", row.wavenumber_cm_1, "cm^-1"),
            ("candidate_prominence", row.prominence_absorbance, "absorbance"),
            ("candidate_fwhm", row.fwhm_cm_1, "cm^-1"),
            (
                "candidate_area_within_fwhm",
                row.area_within_fwhm_absorbance_cm_1,
                "absorbance*cm^-1",
            ),
        ):
            _append(
                records,
                sample_id,
                measurement_id,
                name,
                value,
                unit,
                method,
                source_path,
                source_hash,
                preprocessing_id,
                feature_label=label,
                quality_flag=quality_flag,
            )
    return records


def _source_context(source_file: str | Path | None) -> tuple[str | None, str | None]:
    if source_file is None:
        return None, None
    path = Path(source_file)
    return str(path), sha256_file(path)


def _numeric_column(table: pd.DataFrame, column: str) -> pd.Series:
    if column not in table.columns:
        return pd.Series(float("nan"), index=table.index, dtype=float)
    return pd.to_numeric(table[column], errors="coerce")


def _append(
    records: list[FeatureRecord],
    sample_id: str,
    measurement_id: str,
    feature_name: str,
    value: object,
    unit: str,
    method: str,
    source_file: str | None,
    source_sha256: str | None,
    preprocessing_id: str | None,
    *,
    feature_label: str | None = None,
    quality_flag: str = "review_required",
) -> None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return
    records.append(
        FeatureRecord(
            sample_id=sample_id,
            measurement_id=measurement_id,
            instrument="ftir",
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
    )
