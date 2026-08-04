"""Tabular checks for characterization handoff bundles."""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ..feature_records import LONG_FEATURE_COLUMNS
from .common import (
    HandoffBundleValidationError,
    _REQUIRED_FEATURE_TEXT_COLUMNS,
    _SHA256,
    _nonnegative_int,
    _positive_int,
    _sha256,
    _string_int_mapping,
    _unique_text_list,
)

def _validate_feature_table(path: Path, record: Mapping[str, Any]) -> pd.DataFrame:
    try:
        table = pd.read_csv(path, dtype={column: "string" for column in LONG_FEATURE_COLUMNS if column != "value"})
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise HandoffBundleValidationError(f"could not read feature_table: {path}") from exc
    if table.columns.tolist() != LONG_FEATURE_COLUMNS:
        raise HandoffBundleValidationError("feature_table columns do not match LONG_FEATURE_COLUMNS")
    if len(table) != _nonnegative_int(record, "row_count"):
        raise HandoffBundleValidationError("feature_table row_count mismatch")
    if table.empty:
        raise HandoffBundleValidationError("feature_table must not be empty")

    for column in _REQUIRED_FEATURE_TEXT_COLUMNS:
        values = table[column].astype("string")
        if values.isna().any() or values.str.strip().eq("").any():
            raise HandoffBundleValidationError(f"feature_table contains blank {column}")
        table[column] = values.str.strip()

    numeric = pd.to_numeric(table["value"], errors="coerce")
    if numeric.isna().any() or not all(math.isfinite(float(value)) for value in numeric):
        raise HandoffBundleValidationError("feature_table value must be finite numeric")
    table["value"] = numeric.astype(float)
    if table.duplicated().any():
        raise HandoffBundleValidationError("feature_table contains duplicate rows")

    for value in table["source_sha256"].dropna().astype(str):
        if value.strip() and not _SHA256.fullmatch(value.strip()):
            raise HandoffBundleValidationError("feature_table contains invalid source_sha256")

    expected_instruments = _unique_text_list(record, "instruments")
    observed_instruments = sorted(set(table["instrument"].astype(str)))
    if expected_instruments != observed_instruments:
        raise HandoffBundleValidationError("feature_table instruments mismatch")
    if _nonnegative_int(record, "sample_count") != table["sample_id"].nunique():
        raise HandoffBundleValidationError("feature_table sample_count mismatch")
    if _nonnegative_int(record, "measurement_count") != table["measurement_id"].nunique():
        raise HandoffBundleValidationError("feature_table measurement_count mismatch")

    expected_quality = _string_int_mapping(record.get("quality_flag_counts"), "quality_flag_counts")
    observed_quality = dict(sorted(Counter(table["quality_flag"].astype(str)).items()))
    if expected_quality != observed_quality:
        raise HandoffBundleValidationError("feature_table quality_flag_counts mismatch")
    if _nonnegative_int(record, "source_sha256_record_count") != int(table["source_sha256"].notna().sum()):
        raise HandoffBundleValidationError("feature_table source_sha256_record_count mismatch")
    if _nonnegative_int(record, "preprocessing_id_record_count") != int(table["preprocessing_id"].notna().sum()):
        raise HandoffBundleValidationError("feature_table preprocessing_id_record_count mismatch")
    columns = record.get("columns")
    if columns != LONG_FEATURE_COLUMNS:
        raise HandoffBundleValidationError("feature_table manifest columns mismatch")
    return table


def _validate_context_table(path: Path, record: Mapping[str, Any]) -> pd.DataFrame:
    try:
        table = pd.read_csv(path, dtype="string")
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise HandoffBundleValidationError(f"could not read sample_context: {path}") from exc
    columns = record.get("columns")
    if not isinstance(columns, list) or table.columns.tolist() != columns:
        raise HandoffBundleValidationError("sample_context columns mismatch")
    if len(table) != _nonnegative_int(record, "row_count"):
        raise HandoffBundleValidationError("sample_context row_count mismatch")
    if "sample_id" not in table.columns:
        raise HandoffBundleValidationError("sample_context requires sample_id")
    sample_ids = table["sample_id"].astype("string")
    if sample_ids.isna().any() or sample_ids.str.strip().eq("").any():
        raise HandoffBundleValidationError("sample_context contains blank sample_id")
    table["sample_id"] = sample_ids.str.strip()
    if table["sample_id"].duplicated().any():
        raise HandoffBundleValidationError("sample_context sample_id values must be unique")
    return table
