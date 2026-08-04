"""Backward-compatible facade for characterization handoff validation."""
from .handoff_validation import (
    HandoffBundleValidationError,
    validate_characterization_handoff_bundle,
    write_handoff_bundle_validation,
)
from .handoff_validation.common import VALIDATION_STATUS

__all__ = [
    "HandoffBundleValidationError",
    "VALIDATION_STATUS",
    "validate_characterization_handoff_bundle",
    "write_handoff_bundle_validation",
]
