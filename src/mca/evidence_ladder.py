"""Scientific evidence-ladder contract for characterization sources and results.

The ladder preserves useful lower-level evidence without promoting it into stronger
material, independent-validation, replication, or engineering claims. A higher level can
be Supported only when every lower level is also Supported.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"
ASSESSMENTS = ("Supported", "Diagnostic", "Inconclusive", "Unsupported")
LEVELS = (
    "L0_software_integration",
    "L1_raw_representation_identity",
    "L2_acquisition_provenance_integrity",
    "L3_instrument_calibration_validity",
    "L4_method_algorithm_validation",
    "L5_material_domain_validation",
    "L6_independent_external_validation",
    "L7_replicated_multisource_support",
    "L8_engineering_decision_readiness",
)
LEVEL_DESCRIPTIONS = {
    "L0_software_integration": "The source/result exercises the intended software path without establishing measurement truth.",
    "L1_raw_representation_identity": "Raw/lossless representation, stable byte identity, and source version are verified.",
    "L2_acquisition_provenance_integrity": "Sample/acquisition identity and relevant processing lineage are traceable without inference.",
    "L3_instrument_calibration_validity": "Instrument/detector/calibration metadata required for the claim are traceable and valid.",
    "L4_method_algorithm_validation": "The analysis method is validated under a predeclared protocol within the represented measurement scope.",
    "L5_material_domain_validation": "Evidence directly supports the declared target material/composition/domain rather than a cross-material proxy.",
    "L6_independent_external_validation": "Evidence is independent of model/method development under the declared independence contract.",
    "L7_replicated_multisource_support": "The result is replicated across explicitly provenance-disjoint sources, samples, acquisitions, or facilities as required.",
    "L8_engineering_decision_readiness": "Operational validation, decision thresholds, and engineering-use conditions are independently supported.",
}
_REQUIRED_ROOT_FIELDS = {
    "schema_version",
    "declaration_id",
    "subject",
    "source_bindings",
    "levels",
    "limitations",
}
_REQUIRED_SUBJECT_FIELDS = {
    "modality",
    "source_material_domain",
    "target_material_domain",
    "claim_scope",
}
_REQUIRED_LEVEL_FIELDS = {"assessment", "evidence", "limitations"}
_REQUIRED_BINDING_FIELDS = {"role", "sha256"}


class EvidenceLadderError(ValueError):
    """Raised when an evidence-ladder declaration is malformed or promotes evidence."""


def _canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceLadderError("evidence ladder must be canonical-JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest()


def _exact_mapping(
    value: object,
    *,
    required: set[str],
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceLadderError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise EvidenceLadderError(f"{field} is missing field: {missing[0]}")
    if unknown:
        raise EvidenceLadderError(f"{field} contains unknown field: {unknown[0]}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceLadderError(f"{field} must be a non-empty string")
    return value.strip()


def _text_list(value: object, field: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise EvidenceLadderError(f"{field} must be a list")
    if not allow_empty and not value:
        raise EvidenceLadderError(f"{field} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{field}[{index}]")
        if text in result:
            raise EvidenceLadderError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _sha256(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise EvidenceLadderError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _normalize_subject(value: object) -> dict[str, str]:
    subject = _exact_mapping(value, required=_REQUIRED_SUBJECT_FIELDS, field="subject")
    return {
        field: _text(subject[field], f"subject.{field}")
        for field in sorted(_REQUIRED_SUBJECT_FIELDS)
    }


def _normalize_bindings(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise EvidenceLadderError("source_bindings must be a non-empty list")
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact_mapping(
            raw,
            required=_REQUIRED_BINDING_FIELDS,
            field=f"source_bindings[{index}]",
        )
        role = _text(item["role"], f"source_bindings[{index}].role")
        if role in roles:
            raise EvidenceLadderError(f"duplicate source binding role: {role}")
        roles.add(role)
        result.append(
            {
                "role": role,
                "sha256": _sha256(item["sha256"], f"source_bindings[{index}].sha256"),
            }
        )
    return result


def _normalize_levels(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise EvidenceLadderError("levels must be an object")
    missing = sorted(set(LEVELS) - set(value))
    unknown = sorted(set(value) - set(LEVELS))
    if missing:
        raise EvidenceLadderError(f"levels is missing required level: {missing[0]}")
    if unknown:
        raise EvidenceLadderError(f"levels contains unknown level: {unknown[0]}")

    result: dict[str, dict[str, Any]] = {}
    prior_supported = True
    for level in LEVELS:
        raw = _exact_mapping(
            value[level],
            required=_REQUIRED_LEVEL_FIELDS,
            field=f"levels.{level}",
        )
        assessment = _text(raw["assessment"], f"levels.{level}.assessment")
        if assessment not in ASSESSMENTS:
            raise EvidenceLadderError(
                f"levels.{level}.assessment must be one of: {', '.join(ASSESSMENTS)}"
            )
        evidence = _text_list(
            raw["evidence"],
            f"levels.{level}.evidence",
            allow_empty=assessment != "Supported",
        )
        limitations = _text_list(
            raw["limitations"],
            f"levels.{level}.limitations",
            allow_empty=True,
        )
        if assessment == "Supported" and not prior_supported:
            raise EvidenceLadderError(
                f"{level} cannot be Supported when a lower evidence level is not Supported"
            )
        result[level] = {
            "assessment": assessment,
            "evidence": evidence,
            "limitations": limitations,
            "description": LEVEL_DESCRIPTIONS[level],
        }
        prior_supported = prior_supported and assessment == "Supported"
    return result


def validate_evidence_ladder_declaration(value: object) -> dict[str, Any]:
    """Validate a complete source/result evidence declaration without promotion."""
    root = _exact_mapping(
        value,
        required=_REQUIRED_ROOT_FIELDS,
        field="evidence ladder declaration",
    )
    if _text(root["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise EvidenceLadderError("unsupported evidence ladder schema_version")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "declaration_id": _text(root["declaration_id"], "declaration_id"),
        "subject": _normalize_subject(root["subject"]),
        "source_bindings": _normalize_bindings(root["source_bindings"]),
        "levels": _normalize_levels(root["levels"]),
        "limitations": _text_list(root["limitations"], "limitations", allow_empty=True),
    }
    return normalized


def evaluate_evidence_ladder(value: object) -> dict[str, Any]:
    """Return the highest contiguous Supported level and fail-closed readiness flags."""
    declaration = validate_evidence_ladder_declaration(value)
    highest_index = -1
    for index, level in enumerate(LEVELS):
        if declaration["levels"][level]["assessment"] != "Supported":
            break
        highest_index = index

    highest = LEVELS[highest_index] if highest_index >= 0 else None
    first_blocking = LEVELS[highest_index + 1] if highest_index + 1 < len(LEVELS) else None
    non_supported = [
        {
            "level": level,
            "assessment": declaration["levels"][level]["assessment"],
            "limitations": declaration["levels"][level]["limitations"],
        }
        for level in LEVELS
        if declaration["levels"][level]["assessment"] != "Supported"
    ]
    result = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "declaration": declaration,
        "declaration_sha256": _canonical_sha256(declaration),
        "highest_contiguous_supported_level": highest,
        "highest_contiguous_supported_index": highest_index,
        "first_blocking_level": first_blocking,
        "non_supported_levels": non_supported,
        "readiness": {
            "raw_representation_ready": highest_index >= 1,
            "acquisition_provenance_ready": highest_index >= 2,
            "instrument_calibration_ready": highest_index >= 3,
            "method_validation_ready": highest_index >= 4,
            "material_domain_validation_ready": highest_index >= 5,
            "independent_external_validation_ready": highest_index >= 6,
            "replicated_multisource_support_ready": highest_index >= 7,
            "engineering_decision_ready": highest_index >= 8,
        },
        "handoff": {
            "contract": "materials-characterization-scientific-evidence-ladder",
            "schema_version": SCHEMA_VERSION,
            "subject": declaration["subject"],
            "source_bindings": declaration["source_bindings"],
            "highest_supported_level": highest,
            "first_blocking_level": first_blocking,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "lower_level_evidence_preserved": True,
        },
        "policy_boundary": {
            "cross_material_proxy_promoted_to_target_material_validation": False,
            "software_validation_promoted_to_measurement_truth": False,
            "simulation_promoted_to_empirical_truth": False,
            "independence_inferred_from_file_count": False,
            "engineering_readiness_inferred": False,
        },
    }
    result["assessment_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "ASSESSMENTS",
    "LEVELS",
    "LEVEL_DESCRIPTIONS",
    "POLICY_VERSION",
    "SCHEMA_VERSION",
    "EvidenceLadderError",
    "evaluate_evidence_ladder",
    "validate_evidence_ladder_declaration",
]
