"""Fail-closed scientific-use contract for characterization handoff bundles."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0"
USE_LEVELS = (
    "display",
    "descriptive",
    "association",
    "predictive",
    "causal",
    "engineering",
)
FEATURE_STAGES = ("observable", "derived", "interpreted")
REVIEW_STATUSES = ("reviewed", "review_required", "unreviewed")
MEASUREMENT_TIMINGS = (
    "pre_outcome",
    "concurrent",
    "post_outcome",
    "unknown",
    "not_applicable",
)
EVIDENCE_LEVELS = ("Supported", "Diagnostic", "Inconclusive", "Unsupported")
_FIELDS = {
    "schema_version",
    "maximum_allowed_use",
    "feature_stage",
    "evidence_level",
    "review_status",
    "independence_group_field",
    "measurement_timing",
    "causal_design_validated",
    "operational_validation_validated",
    "limitations",
}


class DownstreamUsePolicyError(ValueError):
    """Raised when a policy is malformed or authorizes an unsafe use."""


def use_rank(value: str) -> int:
    try:
        return USE_LEVELS.index(value)
    except ValueError as exc:
        raise DownstreamUsePolicyError(
            f"unsupported downstream use: {value!r}"
        ) from exc


def _text(policy: Mapping[str, object], field: str) -> str:
    value = policy.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DownstreamUsePolicyError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(policy: Mapping[str, object], field: str) -> str | None:
    value = policy.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DownstreamUsePolicyError(f"{field} must be null or a non-empty string")
    return value.strip()


def _boolean(policy: Mapping[str, object], field: str) -> bool:
    value = policy.get(field)
    if not isinstance(value, bool):
        raise DownstreamUsePolicyError(f"{field} must be a boolean")
    return value


def _limitations(policy: Mapping[str, object]) -> list[str]:
    value = policy.get("limitations")
    if not isinstance(value, list):
        raise DownstreamUsePolicyError("limitations must be a list of non-empty strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DownstreamUsePolicyError(
                "limitations must contain only non-empty strings"
            )
        text = item.strip()
        if text in normalized:
            raise DownstreamUsePolicyError("limitations must not contain duplicates")
        normalized.append(text)
    return normalized


def default_descriptive_policy(evidence_level: str) -> dict[str, Any]:
    """Return the conservative policy used when a producer gives no stronger evidence."""
    return validate_downstream_use_policy(
        {
            "schema_version": SCHEMA_VERSION,
            "maximum_allowed_use": "descriptive",
            "feature_stage": "derived",
            "evidence_level": evidence_level,
            "review_status": "review_required",
            "independence_group_field": None,
            "measurement_timing": "unknown",
            "causal_design_validated": False,
            "operational_validation_validated": False,
            "limitations": [
                "No independent grouping or outcome-timing evidence was declared; use is limited to display and descriptive analysis."
            ],
        },
        scientific_evidence_level=evidence_level,
    )


def validate_downstream_use_policy(
    policy: Mapping[str, object],
    *,
    scientific_evidence_level: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize a policy without promoting evidence."""
    if not isinstance(policy, Mapping):
        raise DownstreamUsePolicyError("downstream_use_policy must be an object")
    unknown = sorted(set(policy) - _FIELDS)
    missing = sorted(_FIELDS - set(policy))
    if unknown:
        raise DownstreamUsePolicyError(
            f"downstream_use_policy contains unknown field: {unknown[0]}"
        )
    if missing:
        raise DownstreamUsePolicyError(
            f"downstream_use_policy is missing field: {missing[0]}"
        )

    schema_version = _text(policy, "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise DownstreamUsePolicyError("unsupported downstream_use_policy schema_version")
    maximum_allowed_use = _text(policy, "maximum_allowed_use")
    maximum_rank = use_rank(maximum_allowed_use)
    feature_stage = _text(policy, "feature_stage")
    if feature_stage not in FEATURE_STAGES:
        raise DownstreamUsePolicyError(f"unsupported feature_stage: {feature_stage!r}")
    evidence_level = _text(policy, "evidence_level")
    if evidence_level not in EVIDENCE_LEVELS:
        raise DownstreamUsePolicyError(f"unsupported evidence_level: {evidence_level!r}")
    if scientific_evidence_level is not None and evidence_level != scientific_evidence_level:
        raise DownstreamUsePolicyError(
            "downstream_use_policy evidence_level must match scientific_closeout evidence_level"
        )
    review_status = _text(policy, "review_status")
    if review_status not in REVIEW_STATUSES:
        raise DownstreamUsePolicyError(f"unsupported review_status: {review_status!r}")
    independence_group_field = _optional_text(policy, "independence_group_field")
    measurement_timing = _text(policy, "measurement_timing")
    if measurement_timing not in MEASUREMENT_TIMINGS:
        raise DownstreamUsePolicyError(
            f"unsupported measurement_timing: {measurement_timing!r}"
        )
    causal_design_validated = _boolean(policy, "causal_design_validated")
    operational_validation_validated = _boolean(
        policy, "operational_validation_validated"
    )
    limitations = _limitations(policy)

    descriptive_rank = use_rank("descriptive")
    association_rank = use_rank("association")
    predictive_rank = use_rank("predictive")
    causal_rank = use_rank("causal")
    engineering_rank = use_rank("engineering")

    if evidence_level in {"Inconclusive", "Unsupported"} and maximum_rank > descriptive_rank:
        raise DownstreamUsePolicyError(
            f"{evidence_level} evidence cannot authorize use above descriptive"
        )
    if evidence_level == "Diagnostic" and maximum_rank > association_rank:
        raise DownstreamUsePolicyError(
            "Diagnostic evidence cannot authorize use above association"
        )
    if feature_stage == "interpreted" and review_status != "reviewed" and maximum_rank > descriptive_rank:
        raise DownstreamUsePolicyError(
            "unreviewed interpreted features cannot authorize use above descriptive"
        )
    if maximum_rank >= association_rank and independence_group_field is None:
        raise DownstreamUsePolicyError(
            "association or stronger use requires independence_group_field"
        )
    if maximum_rank >= predictive_rank and measurement_timing != "pre_outcome":
        raise DownstreamUsePolicyError(
            "predictive or stronger use requires pre_outcome measurement_timing"
        )
    if maximum_rank >= causal_rank and not causal_design_validated:
        raise DownstreamUsePolicyError(
            "causal or stronger use requires causal_design_validated=true"
        )
    if maximum_rank >= engineering_rank and not operational_validation_validated:
        raise DownstreamUsePolicyError(
            "engineering use requires operational_validation_validated=true"
        )

    return {
        "schema_version": schema_version,
        "maximum_allowed_use": maximum_allowed_use,
        "feature_stage": feature_stage,
        "evidence_level": evidence_level,
        "review_status": review_status,
        "independence_group_field": independence_group_field,
        "measurement_timing": measurement_timing,
        "causal_design_validated": causal_design_validated,
        "operational_validation_validated": operational_validation_validated,
        "limitations": limitations,
    }
