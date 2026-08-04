from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .common import (
    SOURCE_PLAN_READY,
    SOURCE_REQUEST_CASE_ID,
    SOURCE_RESPONSE_READY,
    SAEDTransferVerificationError,
    _boolean,
    _hash,
    _load_json,
    _object,
    _only,
    _positive_int,
    _relative,
    _sha256,
)


def load_response_bundle(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    if not root.is_dir() or root.is_symlink():
        raise SAEDTransferVerificationError(
            "response-bundle must be a real directory"
        )
    required = {
        "saed_independent_source_author_response_normalized.json",
        "saed_independent_source_response_assessment.json",
        "saed_independent_source_response_assessment.md",
        "saed_bounded_source_verification_plan.json",
        "saed_independent_source_response_manifest.json",
    }
    for name in required:
        candidate = root / name
        if not candidate.is_file() or candidate.is_symlink():
            raise SAEDTransferVerificationError(
                f"response bundle is missing required file: {name}"
            )

    artifact_manifest_path = root / "saed_independent_source_response_manifest.json"
    artifact_manifest = _load_json(artifact_manifest_path, "response artifact manifest")
    _only(
        artifact_manifest,
        {"schema_version", "case_id", "artifact_count", "artifacts"},
        "response artifact manifest",
    )
    if artifact_manifest.get("case_id") != SOURCE_REQUEST_CASE_ID:
        raise SAEDTransferVerificationError(
            "response artifact manifest case_id mismatch"
        )
    artifacts = artifact_manifest.get("artifacts")
    if not isinstance(artifacts, list) or artifact_manifest.get("artifact_count") != len(artifacts):
        raise SAEDTransferVerificationError(
            "response artifact manifest count mismatch"
        )
    bound: set[str] = set()
    for index, raw in enumerate(artifacts):
        item = _object(raw, f"response artifacts[{index}]")
        _only(item, {"path", "bytes", "sha256"}, f"response artifacts[{index}]")
        relative = _relative(item, "path")
        if relative in bound:
            raise SAEDTransferVerificationError(
                "response artifact paths must be unique"
            )
        bound.add(relative)
        file_path = root / PurePosixPath(relative)
        if not file_path.is_file() or file_path.is_symlink():
            raise SAEDTransferVerificationError(
                f"response artifact missing or unsafe: {relative}"
            )
        if file_path.stat().st_size != _positive_int(item, "bytes"):
            raise SAEDTransferVerificationError(
                f"response artifact byte mismatch: {relative}"
            )
        if _hash(file_path) != _sha256(item, "sha256"):
            raise SAEDTransferVerificationError(
                f"response artifact SHA-256 mismatch: {relative}"
            )
    expected_bound = required - {"saed_independent_source_response_manifest.json"}
    missing_bound = sorted(expected_bound - bound)
    if missing_bound:
        raise SAEDTransferVerificationError(
            f"response manifest does not bind required file: {missing_bound[0]}"
        )

    normalized = _load_json(
        root / "saed_independent_source_author_response_normalized.json",
        "normalized response",
    )
    assessment = _load_json(
        root / "saed_independent_source_response_assessment.json",
        "response assessment",
    )
    plan = _load_json(
        root / "saed_bounded_source_verification_plan.json",
        "bounded verification plan",
    )
    if normalized.get("request_case_id") != SOURCE_REQUEST_CASE_ID:
        raise SAEDTransferVerificationError(
            "normalized response request_case_id mismatch"
        )
    if normalized.get("response_status") != "candidate_available":
        raise SAEDTransferVerificationError(
            "normalized response does not declare a candidate"
        )
    if assessment.get("status") != SOURCE_RESPONSE_READY:
        raise SAEDTransferVerificationError(
            "response assessment is not ready for bounded verification"
        )
    if assessment.get("ready_for_bounded_source_verification") is not True:
        raise SAEDTransferVerificationError(
            "response assessment readiness flag is false"
        )
    prohibited_assessment = {
        "source_download_authorized": False,
        "saed_validation_intake_ready": False,
        "external_evaluation_ready": False,
        "saed_analyzer_execution_authorized": False,
        "phase_or_reflection_indexing_authorized": False,
    }
    for key, expected in prohibited_assessment.items():
        if assessment.get(key) is not expected:
            raise SAEDTransferVerificationError(
                f"response assessment decision boundary mismatch: {key}"
            )
    if plan.get("status") != SOURCE_PLAN_READY:
        raise SAEDTransferVerificationError(
            "bounded verification plan status mismatch"
        )
    if plan.get("source_download_authorized") is not False:
        raise SAEDTransferVerificationError(
            "bounded verification plan unexpectedly authorizes download"
        )

    candidate = _object(normalized.get("candidate"), "normalized candidate")
    if plan.get("dataset_id") != candidate.get("dataset_id"):
        raise SAEDTransferVerificationError("plan dataset_id mismatch")
    if plan.get("dataset_version") != candidate.get("dataset_version"):
        raise SAEDTransferVerificationError("plan dataset_version mismatch")
    if plan.get("collection_manifest_sha256") != candidate.get(
        "collection_manifest_sha256"
    ):
        raise SAEDTransferVerificationError(
            "plan collection_manifest_sha256 mismatch"
        )
    plan_patterns = plan.get("declared_patterns")
    if not isinstance(plan_patterns, list):
        raise SAEDTransferVerificationError(
            "plan declared_patterns must be a list"
        )
    normalized_patterns = candidate.get("patterns")
    if not isinstance(normalized_patterns, list):
        raise SAEDTransferVerificationError(
            "normalized candidate patterns must be a list"
        )
    normalized_projection = [
        {
            key: item[key]
            for key in (
                "pattern_id",
                "relative_path",
                "bytes",
                "sha256",
                "sample_id",
                "acquisition_id",
            )
        }
        for item in normalized_patterns
    ]
    if plan_patterns != normalized_projection:
        raise SAEDTransferVerificationError(
            "bounded verification plan does not match normalized patterns"
        )
    return {
        "root": root,
        "normalized": normalized,
        "assessment": assessment,
        "plan": plan,
        "artifact_manifest_sha256": _hash(artifact_manifest_path),
    }
