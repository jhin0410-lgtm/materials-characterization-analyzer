"""Backward-compatible facade for the downstream-use contract."""
from .downstream_use_contract import (
    EVIDENCE_LEVELS,
    FEATURE_STAGES,
    MEASUREMENT_TIMINGS,
    REVIEW_STATUSES,
    SCHEMA_VERSION as DOWNSTREAM_USE_POLICY_SCHEMA_VERSION,
    USE_LEVELS as DOWNSTREAM_USE_LEVELS,
    DownstreamUsePolicyError,
    default_descriptive_policy,
    use_rank,
    validate_downstream_use_policy,
)

__all__ = [
    "DOWNSTREAM_USE_POLICY_SCHEMA_VERSION",
    "DOWNSTREAM_USE_LEVELS",
    "EVIDENCE_LEVELS",
    "FEATURE_STAGES",
    "MEASUREMENT_TIMINGS",
    "REVIEW_STATUSES",
    "DownstreamUsePolicyError",
    "default_descriptive_policy",
    "use_rank",
    "validate_downstream_use_policy",
]
