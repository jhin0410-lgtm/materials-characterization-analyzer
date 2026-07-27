"""Long-format SAED candidate features without diffraction indexing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .contracts import FeatureRecord
from .provenance import sha256_file


def build_saed_feature_records(
    candidates: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str,
    source_file: str | Path,
    preprocessing_id: str,
    center_x_px: float,
    center_y_px: float,
    analyzed_max_radius_px: float,
) -> list[FeatureRecord]:
    """Build review-required SAED radial candidate features."""
    source_path = str(Path(source_file))
    source_hash = sha256_file(source_file)
    records: list[FeatureRecord] = []
    common = {
        "sample_id": sample_id,
        "measurement_id": measurement_id,
        "instrument": "saed",
        "source_file": source_path,
        "source_sha256": source_hash,
        "preprocessing_id": preprocessing_id,
        "quality_flag": "review_required",
    }

    _append(records, common, "ring_candidate_count", len(candidates), "count", "radial_profile_find_peaks")
    _append(records, common, "center_x", center_x_px, "pixel", "selected_diffraction_center")
    _append(records, common, "center_y", center_y_px, "pixel", "selected_diffraction_center")
    _append(records, common, "analyzed_max_radius", analyzed_max_radius_px, "pixel", "complete_annulus_limit")

    for row in candidates.itertuples(index=False):
        label = f"ring_{int(row.ring_id)}"
        _append(records, common, "candidate_radius", row.radius_px, "pixel", "radial_profile_find_peaks", label)
        _append(records, common, "candidate_fwhm", row.fwhm_px, "pixel", "scipy_peak_widths_half_height", label)
        _append(records, common, "candidate_prominence", row.prominence, "intensity", "scipy_find_peaks", label)
        _append(records, common, "candidate_radial_mean_intensity", row.radial_mean_intensity, "intensity", "complete_annulus_mean", label)
        if _finite(row.reciprocal_g_nm_inv):
            _append(
                records,
                common,
                "candidate_reciprocal_g",
                row.reciprocal_g_nm_inv,
                "nm^-1",
                "calibrated_g_equals_1_over_d",
                label,
            )
        if _finite(row.d_spacing_nm):
            _append(
                records,
                common,
                "candidate_d_spacing",
                row.d_spacing_nm,
                "nm",
                "calibrated_d_equals_1_over_g",
                label,
            )
    return records


def _append(
    records: list[FeatureRecord],
    common: dict[str, object],
    feature_name: str,
    value: object,
    unit: str,
    method: str,
    feature_label: str | None = None,
) -> None:
    if not _finite(value):
        return
    records.append(
        FeatureRecord(
            **common,
            feature_name=feature_name,
            feature_label=feature_label,
            value=float(value),
            unit=unit,
            method=method,
        )
    )


def _finite(value: object) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
