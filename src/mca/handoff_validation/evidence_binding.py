"""Semantic identity binding across checksum-bound handoff evidence files.

File digests prove that the referenced files are unchanged. This module adds the
separate proof that those exact files describe the exported feature records: the
analysis manifest must reproduce the feature table through the writer's real CSV
serialization path, feature source digests must occur in the source manifest, and
the comparability matrix must cover an explicit sample or modality identity axis
used by the exported features.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from ..handoff_bundle import HandoffBundleContractError, _features_from_analysis_manifest
from .common import HandoffBundleValidationError, _load_json_object

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _csv_roundtrip(table: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the bundle writer's pandas CSV serialization boundary in memory."""
    buffer = StringIO()
    table.to_csv(buffer, index=False)
    buffer.seek(0)
    return pd.read_csv(buffer)


def _normalized_feature_rows(table: pd.DataFrame) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for raw in table.itertuples(index=False, name=None):
        normalized: list[object] = []
        for index, value in enumerate(raw):
            if index == 5:  # value
                normalized.append(float(value))
            elif pd.isna(value):
                normalized.append(None)
            else:
                normalized.append(str(value).strip())
        rows.append(tuple(normalized))
    return sorted(rows, key=repr)


def _collect_sha256_values(value: object) -> set[str]:
    digests: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).strip().lower()
            if (
                isinstance(item, str)
                and (key_text == "sha256" or key_text.endswith("_sha256"))
                and _SHA256.fullmatch(item.strip())
            ):
                digests.add(item.strip())
            digests.update(_collect_sha256_values(item))
    elif isinstance(value, list):
        for item in value:
            digests.update(_collect_sha256_values(item))
    return digests


def _analysis_binding(
    analysis_manifest_path: Path,
    feature_table: pd.DataFrame,
) -> dict[str, Any]:
    try:
        analysis_features, _software_versions, _schemas = _features_from_analysis_manifest(
            analysis_manifest_path
        )
    except (OSError, HandoffBundleContractError) as exc:
        raise HandoffBundleValidationError(
            f"analysis_manifest cannot reproduce handoff features: {exc}"
        ) from exc
    # The handoff writer serializes the reconstructed DataFrame through pandas CSV.
    # Compare against that exact serialization boundary rather than pre-CSV binary
    # floats, which may differ by a harmless final representation bit on round-trip.
    serialized_features = _csv_roundtrip(analysis_features)
    if _normalized_feature_rows(serialized_features) != _normalized_feature_rows(feature_table):
        raise HandoffBundleValidationError(
            "analysis_manifest feature records do not reproduce feature_table through the writer CSV boundary"
        )
    return {
        "analysis_manifest_features_reproduced": True,
        "analysis_manifest_feature_count": int(len(analysis_features)),
        "analysis_manifest_csv_boundary_replayed": True,
    }


def _source_binding(
    source_manifest_path: Path,
    feature_table: pd.DataFrame,
    *,
    case_id: str,
) -> dict[str, Any]:
    source = _load_json_object(source_manifest_path, "source manifest")
    source_case_id = source.get("case_id")
    case_id_checked = source_case_id is not None
    if case_id_checked:
        if not isinstance(source_case_id, str) or source_case_id.strip() != case_id:
            raise HandoffBundleValidationError(
                "source_manifest case_id does not match bundle case_id"
            )

    feature_digests = {
        str(value).strip()
        for value in feature_table["source_sha256"].dropna()
        if str(value).strip()
    }
    if not feature_digests:
        raise HandoffBundleValidationError(
            "feature_table has no source_sha256 values for source-manifest identity binding"
        )
    source_digests = _collect_sha256_values(source)
    missing = sorted(feature_digests - source_digests)
    if missing:
        raise HandoffBundleValidationError(
            "source_manifest does not checksum-bind every feature source_sha256; "
            f"missing={missing}"
        )
    return {
        "source_sha256_coverage_verified": True,
        "feature_source_sha256_count": len(feature_digests),
        "source_manifest_sha256_value_count": len(source_digests),
        "source_manifest_case_id_checked": case_id_checked,
    }


def _read_comparability(path: Path) -> pd.DataFrame:
    try:
        table = pd.read_csv(path, dtype="string")
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise HandoffBundleValidationError(
            f"could not read comparability_matrix: {path}"
        ) from exc
    if table.empty:
        raise HandoffBundleValidationError("comparability_matrix must not be empty")
    return table


def _text_set(series: pd.Series, *, label: str, casefold: bool = False) -> set[str]:
    values = series.astype("string")
    if values.isna().any() or values.str.strip().eq("").any():
        raise HandoffBundleValidationError(
            f"comparability_matrix contains blank {label} values"
        )
    normalized = {str(value).strip() for value in values}
    if casefold:
        normalized = {value.casefold() for value in normalized}
    return normalized


def _comparability_binding(
    comparability_matrix_path: Path,
    feature_table: pd.DataFrame,
) -> dict[str, Any]:
    table = _read_comparability(comparability_matrix_path)
    axes: list[str] = []

    if "sample_id" in table.columns:
        observed = _text_set(table["sample_id"], label="sample_id")
        required = {str(value).strip() for value in feature_table["sample_id"]}
        missing = sorted(required - observed)
        if missing:
            raise HandoffBundleValidationError(
                "comparability_matrix does not cover every feature sample_id; "
                f"missing={missing}"
            )
        axes.append("sample_id")

    modality_column = None
    if "modality" in table.columns:
        modality_column = "modality"
    elif "instrument" in table.columns:
        modality_column = "instrument"
    if modality_column is not None:
        observed = _text_set(
            table[modality_column], label=modality_column, casefold=True
        )
        required = {
            str(value).strip().casefold() for value in feature_table["instrument"]
        }
        missing = sorted(required - observed)
        if missing:
            raise HandoffBundleValidationError(
                "comparability_matrix does not cover every feature instrument; "
                f"missing={missing}"
            )
        axes.append(modality_column)

    if not axes:
        raise HandoffBundleValidationError(
            "comparability_matrix must expose sample_id, modality, or instrument "
            "to bind it to exported features"
        )
    return {
        "comparability_identity_coverage_verified": True,
        "comparability_binding_axes": axes,
    }


def validate_evidence_identity_binding(
    *,
    case_id: str,
    feature_table: pd.DataFrame,
    source_manifest_path: Path,
    analysis_manifest_path: Path,
    comparability_matrix_path: Path,
) -> dict[str, Any]:
    """Fail closed unless all three evidence files identify the exported features."""
    return {
        **_analysis_binding(analysis_manifest_path, feature_table),
        **_source_binding(source_manifest_path, feature_table, case_id=case_id),
        **_comparability_binding(comparability_matrix_path, feature_table),
        "scientific_comparability_established": False,
    }


__all__ = ["validate_evidence_identity_binding"]
