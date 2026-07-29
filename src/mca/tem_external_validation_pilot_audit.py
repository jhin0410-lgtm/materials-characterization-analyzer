"""Public facade for the Dryad HRTEM pilot-pair audit.

The implementation is split into a provenance/I/O layer and a scientific
comparison engine. Importing this module preserves the original callable path.
"""
from .tem_external_validation_pilot_engine import run_pilot_pair_audit

__all__ = ["run_pilot_pair_audit"]
