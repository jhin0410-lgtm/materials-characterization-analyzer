"""Long-format thermal feature records without reaction or phase assignment."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file


def build_thermal_feature_records(
    *,
    mode: str,
    processed_table: pd.DataFrame,
    candidate_table: pd.DataFrame,
    sample_id: str,
    measurement_id: str | None = None,
    source_file: str | Path | None = None,
    preprocessing_id: str | None = None,
) -> list[FeatureRecord]:
    """Build review-required TGA or DSC descriptive features."""
    if mode not in {"tga", "dsc"}:
        raise ValueError("mode must be 'tga' or 'dsc'.")
    measurement_id = measurement_id or f"{sample_id}-{mode}"
    source_path, source_hash = _source_context(source_file)
    method = (
        "savgol_gradient_find_peaks"
        if mode == "tga"
        else "endotherm_oriented_baseline_corrected_bidirectional_find_peaks"
    )
    records: list[FeatureRecord] = []
    _append(
        records,
        mode,
        sample_id,
        measurement_id,
        "detected_candidate_count",
        len(candidate_table),
        "count",
        method,
        source_path,
        source_hash,
        preprocessing_id,
    )
    if mode == "tga":
        retention = _numeric_column(processed_table, "mass_retention_percent")
        loss_rate = _numeric_column(processed_table, "mass_loss_rate_percent_per_c")
        temperature = _numeric_column(processed_table, "temperature_c")
        if retention.notna().any():
            _append(
                records,
                mode,
                sample_id,
                measurement_id,
                "initial_mass_retention",
                retention.iloc[0],
                "%",
                "input_or_explicit_mass_reference",
                source_path,
                source_hash,
                preprocessing_id,
            )
            _append(
                records,
                mode,
                sample_id,
                measurement_id,
                "final_mass_retention",
                retention.iloc[-1],
                "%",
                "input_or_explicit_mass_reference",
                source_path,
                source_hash,
                preprocessing_id,
            )
            _append(
                records,
                mode,
                sample_id,
                measurement_id,
                "total_mass_change",
                retention.iloc[0] - retention.iloc[-1],
                "%",
                "initial_minus_final_mass_retention",
                source_path,
                source_hash,
                preprocessing_id,
            )
        valid = loss_rate.notna() & temperature.notna()
        if valid.any():
            index = loss_rate[valid].idxmax()
            _append(
                records,
                mode,
                sample_id,
                measurement_id,
                "maximum_mass_loss_rate",
                loss_rate.loc[index],
                "%/degC",
                method,
                source_path,
                source_hash,
                preprocessing_id,
            )
            _append(
                records,
                mode,
                sample_id,
                measurement_id,
                "temperature_at_maximum_mass_loss_rate",
                temperature.loc[index],
                "degC",
                method,
                source_path,
                source_hash,
                preprocessing_id,
            )
    else:
        types = candidate_table.get("candidate_type", pd.Series(dtype=str))
        for candidate_type in ("endothermic", "exothermic"):
            _append(
                records,
                mode,
                sample_id,
                measurement_id,
                f"{candidate_type}_candidate_count",
                int((types == candidate_type).sum()),
                "count",
                method,
                source_path,
                source_hash,
                preprocessing_id,
            )
        if not candidate_table.empty:
            prominence = _numeric_column(candidate_table, "prominence")
            temperature = _numeric_column(candidate_table, "temperature_c")
            valid = prominence.notna() & temperature.notna()
            if valid.any():
                index = prominence[valid].idxmax()
                _append(
                    records,
                    mode,
                    sample_id,
                    measurement_id,
                    "main_candidate_temperature",
                    temperature.loc[index],
                    "degC",
                    "maximum_candidate_prominence",
                    source_path,
                    source_hash,
                    preprocessing_id,
                )
                _append(
                    records,
                    mode,
                    sample_id,
                    measurement_id,
                    "main_candidate_prominence",
                    prominence.loc[index],
                    "signal",
                    "maximum_candidate_prominence",
                    source_path,
                    source_hash,
                    preprocessing_id,
                )
    if candidate_table.empty:
        return records
    for row in candidate_table.itertuples(index=False):
        candidate_id = int(row.candidate_id)
        candidate_type = str(row.candidate_type)
        label = f"{candidate_type}_candidate_{candidate_id}"
        if mode == "tga":
            values = (
                ("candidate_temperature", row.temperature_c, "degC"),
                ("candidate_mass_loss_rate", row.mass_loss_rate_percent_per_c, "%/degC"),
                ("candidate_prominence", row.prominence_percent_per_c, "%/degC"),
                ("candidate_fwhm", row.fwhm_c, "degC"),
                ("candidate_mass_change_within_fwhm", row.mass_change_within_fwhm_percent, "%"),
            )
        else:
            values = (
                ("candidate_temperature", row.temperature_c, "degC"),
                ("candidate_prominence", row.prominence, "signal"),
                ("candidate_fwhm", row.fwhm_c, "degC"),
                ("candidate_area_within_fwhm", row.area_within_fwhm_signal_c, "signal*degC"),
                ("candidate_enthalpy_within_fwhm", row.enthalpy_within_fwhm_j_g, "J/g"),
            )
        for name, value, unit in values:
            _append(
                records,
                mode,
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
    instrument: str,
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
) -> None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return
    records.append(
        FeatureRecord(
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
            quality_flag="review_required",
        )
    )
