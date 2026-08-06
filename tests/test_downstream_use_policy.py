from __future__ import annotations

import pytest

from mca.downstream_use_policy import (
    DownstreamUsePolicyError,
    default_descriptive_policy,
    validate_downstream_use_policy,
)


def _policy(**overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "schema_version": "1.0",
        "maximum_allowed_use": "descriptive",
        "feature_stage": "derived",
        "evidence_level": "Diagnostic",
        "review_status": "reviewed",
        "independence_group_field": None,
        "measurement_timing": "unknown",
        "causal_design_validated": False,
        "operational_validation_validated": False,
        "limitations": ["No independent external validation."],
    }
    policy.update(overrides)
    return policy


def test_default_policy_is_descriptive_only() -> None:
    policy = default_descriptive_policy("Diagnostic")
    assert policy["maximum_allowed_use"] == "descriptive"
    assert policy["measurement_timing"] == "unknown"
    assert policy["independence_group_field"] is None


def test_diagnostic_descriptive_policy_is_valid() -> None:
    result = validate_downstream_use_policy(
        _policy(), scientific_evidence_level="Diagnostic"
    )
    assert result["maximum_allowed_use"] == "descriptive"
    assert result["independence_group_field"] is None


def test_association_requires_explicit_independence_group() -> None:
    with pytest.raises(DownstreamUsePolicyError, match="association or stronger"):
        validate_downstream_use_policy(
            _policy(maximum_allowed_use="association")
        )

    result = validate_downstream_use_policy(
        _policy(
            maximum_allowed_use="association",
            independence_group_field="specimen_id",
        )
    )
    assert result["independence_group_field"] == "specimen_id"


def test_diagnostic_policy_cannot_authorize_predictive_use() -> None:
    with pytest.raises(DownstreamUsePolicyError, match="Diagnostic evidence"):
        validate_downstream_use_policy(
            _policy(
                maximum_allowed_use="predictive",
                independence_group_field="batch_id",
                measurement_timing="pre_outcome",
            )
        )


def test_predictive_policy_requires_independence_and_pre_outcome_timing() -> None:
    supported = _policy(
        evidence_level="Supported",
        maximum_allowed_use="predictive",
        measurement_timing="pre_outcome",
    )
    with pytest.raises(DownstreamUsePolicyError, match="independence_group_field"):
        validate_downstream_use_policy(supported)

    supported["independence_group_field"] = "specimen_id"
    supported["measurement_timing"] = "post_outcome"
    with pytest.raises(DownstreamUsePolicyError, match="pre_outcome"):
        validate_downstream_use_policy(supported)


def test_causal_and_engineering_require_explicit_validation() -> None:
    causal = _policy(
        evidence_level="Supported",
        maximum_allowed_use="causal",
        independence_group_field="batch_id",
        measurement_timing="pre_outcome",
    )
    with pytest.raises(DownstreamUsePolicyError, match="causal_design_validated"):
        validate_downstream_use_policy(causal)

    engineering = dict(causal)
    engineering.update(
        maximum_allowed_use="engineering",
        causal_design_validated=True,
    )
    with pytest.raises(
        DownstreamUsePolicyError, match="operational_validation_validated"
    ):
        validate_downstream_use_policy(engineering)


def test_interpreted_features_require_review_above_descriptive() -> None:
    with pytest.raises(DownstreamUsePolicyError, match="interpreted features"):
        validate_downstream_use_policy(
            _policy(
                maximum_allowed_use="association",
                feature_stage="interpreted",
                review_status="review_required",
                independence_group_field="specimen_id",
            )
        )


def test_policy_evidence_must_match_scientific_closeout() -> None:
    with pytest.raises(DownstreamUsePolicyError, match="must match"):
        validate_downstream_use_policy(
            _policy(), scientific_evidence_level="Supported"
        )
