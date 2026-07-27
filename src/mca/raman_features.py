"""Long-format Raman feature records without spectral band assignment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file


def build_raman_feature_records(
    peak_table: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str,
    source_file: str | Path,
    preprocessing_id: str,
) -> list[FeatureRecord]:
    """Create review-required Raman peak features from an automatic peak table."""
    source_path = str(Path(source_file))
    source_hash = sha256_file(source_file)
    records: list[FeatureRecord] = []

    def add(
        name: str,
        value: Any,
        unit: str,
        *,
        label: str | None = None,
        method: str = "automatic_raman_peak_detection",
    ) -> None:
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(numeric) or not np.isfinite(float(numeric)):
            return
        records.append(
            FeatureRecord(
                sample_id=sample_id,
                measurement_id=measurement_id,
                instrument="raman",
                feature_name=name,
                feature_label=label,
                value=float(numeric),
                unit=unit,
                method=method,
                source_file=source_path,
                source_sha256=source_hash,
                preprocessing_id=preprocessing_id,
                quality_flag="review_required",
            )
        )

    add("detected_peak_count", len(peak_table), "count")
    if peak_table.empty:
        return records

    processed = pd.to_numeric(peak_table["processed_intensity"], errors="coerce")
    if processed.notna().any():
        main_index = processed.idxmax()
        add("main_peak_raman_shift", peak_table.loc[main_index, "raman_shift_cm_1"], "cm^-1")
        add("main_peak_corrected_intensity", peak_table.loc[main_index, "corrected_intensity"], "a.u.")

    fwhm = pd.to_numeric(peak_table["fwhm_cm_1"], errors="coerce")
    add("mean_fwhm", fwhm.mean(), "cm^-1", method="scipy_peak_widths_half_prominence")
    add("median_fwhm", fwhm.median(), "cm^-1", method="scipy_peak_widths_half_prominence")

    for row in peak_table.itertuples(index=False):
        label = f"peak_{int(row.peak_id)}"
        add("peak_raman_shift", row.raman_shift_cm_1, "cm^-1", label=label)
        add("peak_corrected_intensity", row.corrected_intensity, "a.u.", label=label)
        add("peak_prominence", row.prominence, "a.u.", label=label)
        add(
            "peak_fwhm",
            row.fwhm_cm_1,
            "cm^-1",
            label=label,
            method="scipy_peak_widths_half_prominence",
        )
        add(
            "peak_area_within_fwhm",
            row.area_within_fwhm_intensity_cm_1,
            "a.u.*cm^-1",
            label=label,
            method="trapezoidal_integration_within_fwhm",
        )
    return records
