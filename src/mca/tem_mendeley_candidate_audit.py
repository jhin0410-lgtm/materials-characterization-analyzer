"""Backward-compatible facade for the public Mendeley candidate audit."""

from .tem_mendeley_candidate_audit_engine import (
    CASE_ID,
    PRIMARY_DATASET_ID,
    PRIMARY_DOI,
    PUBLIC_API_BASE,
    SCHEMA_VERSION,
    STATUS_API_BLOCKED,
    STATUS_INVENTORY_RESOLVED,
    STATUS_NO_FILES,
    STATUS_TEM_CANDIDATE_FOUND,
    AuditConfig,
    DatasetSpec,
    Transport,
    load_config,
    run_mendeley_candidate_audit,
)

API_BASE = PUBLIC_API_BASE

__all__ = [
    "API_BASE",
    "CASE_ID",
    "PRIMARY_DATASET_ID",
    "PRIMARY_DOI",
    "PUBLIC_API_BASE",
    "SCHEMA_VERSION",
    "STATUS_API_BLOCKED",
    "STATUS_INVENTORY_RESOLVED",
    "STATUS_NO_FILES",
    "STATUS_TEM_CANDIDATE_FOUND",
    "AuditConfig",
    "DatasetSpec",
    "Transport",
    "load_config",
    "run_mendeley_candidate_audit",
]
