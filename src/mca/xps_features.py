"""Long-format XPS feature records without elemental or chemical-state assignment."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file


def build_xps_feature_records(
    candidate_table: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build review-required descriptive XPS candidate features."""
    measurement_id = measurement_id or f"{sample_id}-xps"
    source_path, source_hash = _source_context(source_file)
    method = "background_corrected_scipy_find_peaks"
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

    energy = _numeric_column(candidate_table, "binding_energy_corrected_ev")
    intensity = _numeric_column(candidate_table, "processed_intensity")
    fwhm = _numeric_column(candidate_table, "fwhm_ev")
    area = _numeric_column(candidate_table, "area_within_fwhm_intensity_ev")

    valid_main = energy.notna() & intensity.notna()
    if valid_main.any():
        main_index = intensity[valid_main].idxmax()
        _append(
            records,
            sample_id,
            measurement_id,
            "main_candidate_binding_energy",
            energy.loc[main_index],
            "eV",
            "maximum_processed_candidate_intensity",
            source_path,
            source_hash,
            preprocessing_id,
            quality_flag=quality_flag,
        )
        _append(
            records,
            sample_id,
            measurement_id,
            "main_candidate_processed_intensity",
            intensity.loc[main_index],
            "intensity",
            "maximum_processed_candidate_intensity",
            source_path,
            source_hash,
            preprocessing_id,
            quality_flag=quality_flag,
        )

    for name, statistic, unit in (
        ("mean_candidate_fwhm", fwhm.mean(), "eV"),
        ("median_candidate_fwhm", fwhm.median(), "eV"),
        ("total_within_fwhm_area", area.sum(min_count=1), "intensity*eV"),
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
            ("candidate_binding_energy", row.binding_energy_corrected_ev, "eV"),
            ("candidate_prominence", row.prominence, "intensity"),
            ("candidate_fwhm", row.fwhm_ev, "eV"),
            ("candidate_area_within_fwhm", row.area_within_fwhm_intensity_ev, "intensity*eV"),
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
            instrument="xps",
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
