"""Semantic identity binding across checksum-bound handoff evidence files.

File digests prove that the referenced files are unchanged. This module adds the
separate proof that those exact files describe the exported feature records: the
analysis manifest must reproduce the feature table through the writer's real CSV
serialization path, every feature row must carry a source digest found in the
source manifest, and the comparability matrix must cover explicit feature identity.
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

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_SOURCE_RECORD_CONTAINER_KEYS = {
    "sources",
    "source_files",
    "source_records",
    "files",
    "input_files",
    "raw_files",
    "archive_members",
    "raw_archive_members",
}
_SOURCE_RECORD_KEYS = {
    "source",
    "source_file",
    "source_record",
    "measurement_source",
    "raw_source",
    "raw_file",
    "input_file",
    "archive_member",
    "workbook",
}
_SOURCE_IDENTITY_FIELDS = {
    "path",
    "filename",
    "source_file",
    "url",
    "download_url",
    "record_url",
    "member_path",
    "archive_member",
    "doi",
    "provenance_type",
    "source_type",
}
_EXPLICIT_SOURCE_DIGEST_KEYS = {"source_sha256", "file_sha256", "member_sha256"}


def _csv_roundtrip(table: pd.DataFrame) -> pd.DataFrame:
    buffer = StringIO()
    table.to_csv(buffer, index=False, lineterminator="\n")
    buffer.seek(0)
    return pd.read_csv(buffer)


def _normalized_feature_rows(table: pd.DataFrame) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for raw in table.itertuples(index=False, name=None):
        normalized: list[object] = []
        for index, value in enumerate(raw):
            if index == 5:
                normalized.append(float(value))
            elif pd.isna(value):
                normalized.append(None)
            else:
                normalized.append(str(value).strip())
        rows.append(tuple(normalized))
    return sorted(rows, key=repr)


def _collect_source_record_sha256_values(source: Mapping[str, Any]) -> set[str]:
    """Collect digests only from the source-record mapping that owns them.

    Source-container membership marks only immediate records. It is deliberately not
    inherited by arbitrary nested metadata, so an ``audit`` or ``expected`` subtree
    inside a real source record cannot substitute its checksum for the source bytes.
    """
    digests: set[str] = set()

    def visit(
        value: object,
        *,
        is_source_record: bool,
        members_are_source_records: bool,
        record_key: str | None,
        is_root: bool,
    ) -> None:
        if isinstance(value, Mapping):
            keys = {str(key).strip().lower() for key in value}
            current_source_record = (
                is_source_record
                or record_key in _SOURCE_RECORD_KEYS
                or bool(keys & _SOURCE_IDENTITY_FIELDS)
                or (is_root and "source" in keys)
            )
            for key, item in value.items():
                key_text = str(key).strip().lower()
                valid_digest = (
                    isinstance(item, str)
                    and _SHA256.fullmatch(item.strip()) is not None
                )
                if (
                    key_text in _EXPLICIT_SOURCE_DIGEST_KEYS
                    and valid_digest
                    and (current_source_record or is_root)
                ):
                    digests.add(item.strip().lower())
                elif key_text == "sha256" and valid_digest and current_source_record:
                    digests.add(item.strip().lower())

                child_members_are_records = key_text in _SOURCE_RECORD_CONTAINER_KEYS
                if isinstance(item, Mapping):
                    visit(
                        item,
                        is_source_record=members_are_source_records,
                        members_are_source_records=child_members_are_records,
                        record_key=key_text,
                        is_root=False,
                    )
                elif isinstance(item, list):
                    visit(
                        item,
                        is_source_record=False,
                        members_are_source_records=child_members_are_records,
                        record_key=key_text,
                        is_root=False,
                    )
        elif isinstance(value, list):
            for item in value:
                visit(
                    item,
                    is_source_record=members_are_source_records,
                    members_are_source_records=False,
                    record_key=None,
                    is_root=False,
                )

    visit(
        source,
        is_source_record=False,
        members_are_source_records=False,
        record_key=None,
        is_root=True,
    )
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

    raw_feature_digests = feature_table["source_sha256"].astype("string")
    missing_digest_rows = raw_feature_digests.isna() | raw_feature_digests.str.strip().eq("")
    if missing_digest_rows.any():
        raise HandoffBundleValidationError(
            "every feature row must carry source_sha256 for evidence identity binding"
        )
    invalid_digest_rows = ~raw_feature_digests.str.strip().str.fullmatch(_SHA256)
    if invalid_digest_rows.any():
        raise HandoffBundleValidationError(
            "every feature row source_sha256 must be a SHA-256 hex digest"
        )
    feature_digests = {str(value).strip().lower() for value in raw_feature_digests}
    source_digests = _collect_source_record_sha256_values(source)
    missing = sorted(feature_digests - source_digests)
    if missing:
        raise HandoffBundleValidationError(
            "source_manifest does not checksum-bind every feature source_sha256; "
            f"missing={missing}"
        )
    return {
        "source_sha256_coverage_verified": True,
        "every_feature_row_source_sha256_bound": True,
        "feature_source_sha256_count": len(feature_digests),
        "source_manifest_sha256_value_count": len(source_digests),
        "source_manifest_case_id_checked": case_id_checked,
        "source_digest_scope": "recognized_source_records_only",
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


def _normalized_text_series(series: pd.Series, *, label: str) -> pd.Series:
    values = series.astype("string")
    if values.isna().any() or values.str.strip().eq("").any():
        raise HandoffBundleValidationError(
            f"comparability_matrix contains blank {label} values"
        )
    return values.str.strip()


def _comparability_binding(
    comparability_matrix_path: Path,
    feature_table: pd.DataFrame,
) -> dict[str, Any]:
    table = _read_comparability(comparability_matrix_path)
    axes: list[str] = []
    sample_values: pd.Series | None = None
    modality_values: pd.Series | None = None

    if "sample_id" in table.columns:
        sample_values = _normalized_text_series(table["sample_id"], label="sample_id")
        observed = set(sample_values)
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
        modality_values = _normalized_text_series(
            table[modality_column], label=modality_column
        ).str.casefold()
        observed = set(modality_values)
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

    pair_binding = False
    if sample_values is not None and modality_values is not None:
        observed_pairs = set(zip(sample_values, modality_values, strict=True))
        required_pairs = {
            (str(row.sample_id).strip(), str(row.instrument).strip().casefold())
            for row in feature_table[["sample_id", "instrument"]].itertuples(index=False)
        }
        missing_pairs = sorted(required_pairs - observed_pairs)
        if missing_pairs:
            raise HandoffBundleValidationError(
                "comparability_matrix does not cover every feature sample_id/instrument pair; "
                f"missing={missing_pairs}"
            )
        pair_binding = True

    if not axes:
        raise HandoffBundleValidationError(
            "comparability_matrix must expose sample_id, modality, or instrument "
            "to bind it to exported features"
        )
    return {
        "comparability_identity_coverage_verified": True,
        "comparability_binding_axes": axes,
        "comparability_sample_instrument_pair_coverage_verified": pair_binding,
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
