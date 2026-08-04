"""Shared validation primitives for characterization handoff bundles."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..provenance import sha256_file


BUNDLE_SCHEMA_VERSION = "1.0"
BUNDLE_TYPE = "materials_characterization_feature_handoff"
FEATURE_FILE_NAME = "characterization_features_long.csv"
SAMPLE_CONTEXT_FILE_NAME = "sample_context.csv"
MANIFEST_FILE_NAME = "characterization_handoff_bundle.json"
VALIDATION_STATUS = "valid_characterization_handoff_bundle"
SUPPORTED_EVIDENCE_LEVELS = {
    "Supported",
    "Diagnostic",
    "Inconclusive",
    "Unsupported",
}
_REQUIRED_EVIDENCE_REFERENCES = {
    "source_manifest",
    "analysis_manifest",
    "comparability_matrix",
}
_REQUIRED_FEATURE_TEXT_COLUMNS = {
    "sample_id",
    "measurement_id",
    "instrument",
    "feature_name",
    "unit",
    "method",
    "quality_flag",
}
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


class HandoffBundleValidationError(ValueError):
    """Raised when a characterization handoff bundle fails closed."""

def _file_record(value: Any, label: str) -> dict[str, Any]:
    record = _object(value, label)
    allowed = {"path", "sha256", "size_bytes"}
    if label == "feature_table":
        allowed |= {
            "columns",
            "row_count",
            "sample_count",
            "measurement_count",
            "instruments",
            "quality_flag_counts",
            "source_sha256_record_count",
            "preprocessing_id_record_count",
        }
    elif label == "sample_context":
        allowed |= {"columns", "row_count"}
    _reject_unknown(record, allowed, label)
    path = _safe_relative_name(record, "path")
    sha256 = _sha256(record, "sha256")
    size_bytes = _positive_int(record, "size_bytes")
    return {**record, "path": path, "sha256": sha256, "size_bytes": size_bytes}


def _verify_file_record(root: Path, record: Mapping[str, Any], label: str) -> Path:
    path = _safe_direct_file(root, str(record["path"]), label)
    if path.stat().st_size != record["size_bytes"]:
        raise HandoffBundleValidationError(f"{label} size_bytes mismatch")
    if sha256_file(path) != record["sha256"]:
        raise HandoffBundleValidationError(f"{label} SHA-256 mismatch")
    return path


def _safe_direct_file(root: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative.replace("\\", "/"))
    if pure.is_absolute() or len(pure.parts) != 1 or ".." in pure.parts or relative in {"", "."}:
        raise HandoffBundleValidationError(f"{label} path must be a direct safe relative file")
    candidate = root / pure
    if not candidate.is_file() or candidate.is_symlink():
        raise HandoffBundleValidationError(f"{label} must be a regular non-symlink file")
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise HandoffBundleValidationError(f"{label} escapes bundle directory") from exc
    return candidate


def _safe_relative_name(payload: Mapping[str, Any], key: str) -> str:
    value = _nonempty_text(payload, key).replace("\\", "/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or len(pure.parts) != 1 or ".." in pure.parts or value in {"", "."}:
        raise HandoffBundleValidationError(f"{key} must be a direct safe relative file")
    return pure.as_posix()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffBundleValidationError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise HandoffBundleValidationError(f"{label} must contain a JSON object")
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HandoffBundleValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise HandoffBundleValidationError(f"{label} contains unknown field: {unknown[0]}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffBundleValidationError(f"{label} must be an object")
    return dict(value)


def _nonempty_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HandoffBundleValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _unique_text_list(payload: Mapping[str, Any], key: str, allow_empty: bool = False) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or (not value and not allow_empty):
        raise HandoffBundleValidationError(f"{key} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HandoffBundleValidationError(f"{key} entries must be non-empty strings")
        result.append(item.strip())
    if len(result) != len(set(result)):
        raise HandoffBundleValidationError(f"{key} must not contain duplicates")
    return sorted(result)


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise HandoffBundleValidationError(f"{key} must be a SHA-256 hex digest")
    return value.lower()


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HandoffBundleValidationError(f"{key} must be a positive integer")
    return value


def _nonnegative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HandoffBundleValidationError(f"{key} must be a non-negative integer")
    return value


def _string_int_mapping(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise HandoffBundleValidationError(f"{label} must be an object")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key.strip():
            raise HandoffBundleValidationError(f"{label} keys must be non-empty strings")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise HandoffBundleValidationError(f"{label} values must be non-negative integers")
        result[key] = count
    return dict(sorted(result.items()))


