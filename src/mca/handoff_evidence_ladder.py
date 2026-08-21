"""Fail-closed binding of L0-L8 evidence-ladder assessments into handoff bundles."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .evidence_ladder import EvidenceLadderError, evaluate_evidence_ladder
from .provenance import sha256_file

CONTRACT = "materials-characterization-scientific-evidence-ladder"
RECORD_SCHEMA_VERSION = "1.0"
_RECORD_FIELDS = {
    "contract",
    "schema_version",
    "policy_version",
    "assessment",
    "declaration_id",
    "declaration_sha256",
    "assessment_sha256",
    "subject",
    "source_bindings",
    "highest_contiguous_supported_level",
    "first_blocking_level",
    "readiness",
    "scientific_status_promoted",
    "downstream_use_authorized",
    "lower_level_evidence_preserved",
}
_FILE_RECORD_FIELDS = {"path", "sha256", "size_bytes"}


class EvidenceLadderHandoffError(ValueError):
    """Raised when an evidence-ladder handoff binding cannot be independently replayed."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceLadderHandoffError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise EvidenceLadderHandoffError(f"{label} must be a regular non-symlink file")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceLadderHandoffError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise EvidenceLadderHandoffError(f"{label} root must be an object")
    return payload


def _exact_mapping(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceLadderHandoffError(f"{label} must be an object")
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        raise EvidenceLadderHandoffError(f"{label} is missing field: {missing[0]}")
    if unknown:
        raise EvidenceLadderHandoffError(f"{label} contains unknown field: {unknown[0]}")
    return value


def _validated_assessment(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path, "scientific evidence-ladder assessment")
    declaration = payload.get("declaration")
    if not isinstance(declaration, dict):
        raise EvidenceLadderHandoffError(
            "scientific evidence-ladder assessment must contain a declaration object"
        )
    try:
        replayed = evaluate_evidence_ladder(declaration)
    except EvidenceLadderError as exc:
        raise EvidenceLadderHandoffError(
            f"scientific evidence-ladder declaration is invalid: {exc}"
        ) from exc
    if payload != replayed:
        raise EvidenceLadderHandoffError(
            "scientific evidence-ladder assessment does not exactly match deterministic replay"
        )
    handoff = replayed.get("handoff")
    if not isinstance(handoff, dict):
        raise EvidenceLadderHandoffError("replayed evidence-ladder handoff is missing")
    if handoff.get("contract") != CONTRACT:
        raise EvidenceLadderHandoffError("evidence-ladder handoff contract mismatch")
    if handoff.get("scientific_status_promoted") is not False:
        raise EvidenceLadderHandoffError("evidence ladder must not promote scientific status")
    if handoff.get("downstream_use_authorized") is not False:
        raise EvidenceLadderHandoffError("evidence ladder must not authorize downstream use")
    if handoff.get("lower_level_evidence_preserved") is not True:
        raise EvidenceLadderHandoffError("evidence ladder must preserve lower-level evidence")
    return replayed


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def build_scientific_evidence_ladder_record(
    assessment_path: str | Path,
) -> dict[str, Any]:
    """Build a manifest record only after deterministic assessment replay succeeds."""
    path = Path(assessment_path)
    assessment = _validated_assessment(path)
    declaration = assessment["declaration"]
    handoff = assessment["handoff"]
    return {
        "contract": CONTRACT,
        "schema_version": RECORD_SCHEMA_VERSION,
        "policy_version": assessment["policy_version"],
        "assessment": _file_record(path),
        "declaration_id": declaration["declaration_id"],
        "declaration_sha256": assessment["declaration_sha256"],
        "assessment_sha256": assessment["assessment_sha256"],
        "subject": handoff["subject"],
        "source_bindings": handoff["source_bindings"],
        "highest_contiguous_supported_level": assessment[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": assessment["first_blocking_level"],
        "readiness": assessment["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }


def validate_scientific_evidence_ladder_record(
    bundle_root: str | Path,
    value: object,
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Verify file identity then reconstruct the entire producer-authored summary."""
    root = Path(bundle_root).resolve()
    record = _exact_mapping(value, _RECORD_FIELDS, "scientific_evidence_ladder")
    if record.get("contract") != CONTRACT:
        raise EvidenceLadderHandoffError("scientific_evidence_ladder contract mismatch")
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise EvidenceLadderHandoffError(
            "unsupported scientific_evidence_ladder schema_version"
        )

    file_record = _exact_mapping(
        record.get("assessment"),
        _FILE_RECORD_FIELDS,
        "scientific_evidence_ladder.assessment",
    )
    recorded_path = file_record.get("path")
    if not isinstance(recorded_path, str) or not recorded_path.strip():
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder.assessment.path must be a non-empty string"
        )
    relative = Path(recorded_path)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != recorded_path:
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder assessment must be one direct sibling file"
        )
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder assessment file is missing or unsafe"
        )
    expected_sha = file_record.get("sha256")
    if not isinstance(expected_sha, str) or expected_sha != sha256_file(path):
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder assessment checksum mismatch"
        )
    expected_size = file_record.get("size_bytes")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int):
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder assessment size_bytes must be an integer"
        )
    if expected_size != path.stat().st_size:
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder assessment size_bytes mismatch"
        )

    assessment = _validated_assessment(path)
    expected_record = build_scientific_evidence_ladder_record(path)
    if dict(record) != expected_record:
        raise EvidenceLadderHandoffError(
            "scientific_evidence_ladder manifest summary does not match the replayed assessment"
        )
    return expected_record, path, assessment


__all__ = [
    "CONTRACT",
    "RECORD_SCHEMA_VERSION",
    "EvidenceLadderHandoffError",
    "build_scientific_evidence_ladder_record",
    "validate_scientific_evidence_ladder_record",
]
