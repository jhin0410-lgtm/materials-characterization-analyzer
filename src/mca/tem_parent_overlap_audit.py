"""Audit public HRTEM source frames against reconstructed training parents.

Scientific guardrails retained by the implementation include:
    "model_training_performed": False
    "segmentation_accuracy_computed": False
    "source_predicted_masks_used_as_ground_truth": False
"""
from .tem_parent_overlap_contract import (
    PUBLIC_CASE_ID, PUBLIC_DOI, PUBLIC_DATASET_VERSION, PUBLIC_LICENSE,
    PUBLIC_TRAINING_NAME, PUBLIC_TRAINING_MD5, PUBLIC_TRAINING_SHA256,
    PUBLIC_ARCHIVE_NAME, PUBLIC_ARCHIVE_MD5, PUBLIC_ARCHIVE_SHA256,
    PUBLIC_PREFIXES, OVERLAP_EQUIVALENT, OVERLAP_REVIEW, OVERLAP_NOT_DETECTED,
    CLOSEOUT_RESULT, LABEL_STATUS, LIMITATIONS, FileSpec, ArchiveSpec,
    SourceMemberSpec, ParentOverlapAuditConfig, load_config, validate_public_config,
)
from .tem_parent_overlap_engine import run_parent_overlap_audit

__all__ = [
    "PUBLIC_CASE_ID", "PUBLIC_DOI", "PUBLIC_DATASET_VERSION", "PUBLIC_LICENSE",
    "PUBLIC_TRAINING_NAME", "PUBLIC_TRAINING_MD5", "PUBLIC_TRAINING_SHA256",
    "PUBLIC_ARCHIVE_NAME", "PUBLIC_ARCHIVE_MD5", "PUBLIC_ARCHIVE_SHA256",
    "PUBLIC_PREFIXES", "OVERLAP_EQUIVALENT", "OVERLAP_REVIEW",
    "OVERLAP_NOT_DETECTED", "CLOSEOUT_RESULT", "LABEL_STATUS", "LIMITATIONS",
    "FileSpec", "ArchiveSpec", "SourceMemberSpec", "ParentOverlapAuditConfig",
    "load_config", "validate_public_config", "run_parent_overlap_audit",
]
