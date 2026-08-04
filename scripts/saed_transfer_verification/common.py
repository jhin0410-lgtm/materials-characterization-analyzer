from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

CASE_ID = "saed_independent_source_transfer_verification"
SCHEMA_VERSION = "1.0"
SOURCE_REQUEST_CASE_ID = "saed_independent_validation_source_request"
SOURCE_RESPONSE_READY = "candidate_response_ready_for_bounded_saed_source_verification"
SOURCE_PLAN_READY = "bounded_saed_source_verification_plan_draft"
INTAKE_CASE_ID = "saed_external_validation_intake"
READY = "ready_to_run_saed_validation_intake"
BLOCKED = "transfer_verified_but_saed_intake_blocked"
_ALLOWED_INTAKE_SOURCE_TYPES = {
    "external_public",
    "new_acquisition",
    "private_acquisition",
}
_ALLOWED_IDENTITY_PROVENANCE = {
    "source_assigned",
    "operator_assigned_at_acquisition",
}
_ALLOWED_REPRESENTATIONS = {"raw_detector", "lossless_export"}
_RESPONSE_REFERENCE_TO_INTAKE = {
    "source_assignments": "source_author_assignments",
    "predeclared_reference_structures": "curated_structures",
}
_SELECTION_FLAGS = (
    "used_for_center_selection",
    "used_for_smoothing_selection",
    "used_for_prominence_selection",
    "used_for_radius_bound_selection",
    "used_for_candidate_count_selection",
)
_INVENTORY_COLUMNS = (
    "pattern_id",
    "relative_path",
    "declared_bytes",
    "observed_bytes",
    "declared_sha256",
    "observed_sha256",
    "size_matches",
    "sha256_matches",
    "sample_id",
    "acquisition_id",
    "material_id",
    "representation",
    "file_format",
    "excluded",
    "parameter_selection_reuse",
)
_PLACEHOLDER = re.compile(
    r"(replace[-_/ ]?with|\bunresolved\b|\bunknown\b|\bnot provided\b|"
    r"\bnot available\b|\btbd\b|\btodo\b|^n/?a$)",
    re.IGNORECASE,
)


class SAEDTransferVerificationError(ValueError):
    """Raised when the transfer-verification contract fails closed."""


def _safe_root(path: str | Path) -> Path:
    root = Path(path)
    if not root.is_dir() or root.is_symlink():
        raise SAEDTransferVerificationError("data-root must be a real directory")
    return root.resolve()


def _safe_file(root: Path, relative: str) -> Path:
    path = root / PurePosixPath(relative)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SAEDTransferVerificationError(
            f"declared file is missing: {relative}"
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SAEDTransferVerificationError(
            f"declared file escapes data-root: {relative}"
        ) from exc
    if not resolved.is_file() or resolved.is_symlink() or path.is_symlink():
        raise SAEDTransferVerificationError(
            f"declared file must be a regular non-symlink file: {relative}"
        )
    return resolved


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output must be absent or an empty directory")
        return output, False
    output.mkdir(parents=True)
    return output, True


def _cleanup_output(output: Path, created: bool) -> None:
    if created:
        shutil.rmtree(output, ignore_errors=True)
    elif output.is_dir():
        for child in output.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)


def _artifact_manifest(output: Path, paths: Sequence[Path]) -> dict[str, Any]:
    records = sorted(
        (
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _hash(path),
            }
            for path in paths
        ),
        key=lambda item: item["path"],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_INVENTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise SAEDTransferVerificationError(f"{label} must be a regular file")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SAEDTransferVerificationError(
            f"could not read {label}: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise SAEDTransferVerificationError(f"{label} root must be an object")
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SAEDTransferVerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _only(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise SAEDTransferVerificationError(
            f"{label} contains unknown field: {unknown[0]}"
        )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SAEDTransferVerificationError(f"{label} must be an object")
    return dict(value)


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SAEDTransferVerificationError(f"{key} must be a non-empty string")
    value = value.strip()
    if _PLACEHOLDER.search(value):
        raise SAEDTransferVerificationError(
            f"{key} contains unresolved placeholder text"
        )
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SAEDTransferVerificationError(
            f"{label} must be null or a non-empty string"
        )
    result = value.strip()
    if _PLACEHOLDER.search(result):
        raise SAEDTransferVerificationError(
            f"{label} contains unresolved placeholder text"
        )
    return result


def _identifier(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise SAEDTransferVerificationError(
            f"{key} must be a stable identifier"
        )
    return value


def _text_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise SAEDTransferVerificationError(
            f"{key} must be a non-empty list"
        )
    result = [_text({"item": item}, "item") for item in value]
    if len(result) != len(set(result)):
        raise SAEDTransferVerificationError(f"{key} must not contain duplicates")
    return result


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise SAEDTransferVerificationError(f"{key} must be boolean")
    return value


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SAEDTransferVerificationError(f"{key} must be a positive integer")
    return value


def _at_least_two(payload: Mapping[str, Any], key: str) -> int:
    value = _positive_int(payload, key)
    if value < 2:
        raise SAEDTransferVerificationError(f"{key} must be at least 2")
    return value


def _positive_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise SAEDTransferVerificationError(f"{key} must be a positive number")
    return float(value)


def _nonnegative_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
        raise SAEDTransferVerificationError(
            f"{key} must be a non-negative number"
        )
    return float(value)


def _optional_positive_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise SAEDTransferVerificationError(
            f"{label} must be null or a positive number"
        )
    return float(value)


def _relative(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key).replace("\\", "/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or value in {"", "."}:
        raise SAEDTransferVerificationError(f"{key} must be a safe relative path")
    return pure.as_posix()


def _sha256(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise SAEDTransferVerificationError(f"{key} must be a SHA-256 hex digest")
    return value.lower()


def _date(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise SAEDTransferVerificationError(f"{key} must be YYYY-MM-DD") from exc
    return value


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
