"""Checksum-bound evidence contract for SAED candidate readiness claims.

This module does not decide scientific validity.  It only prevents the SAED
candidate registry from promoting a candidate to source-audit readiness from
unstructured prose and self-declared booleans alone.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class SAEDSourceEvidenceBindingError(ValueError):
    """Raised when a source-evidence artifact contract is malformed or unsafe."""


_EVIDENCE_TYPES = {
    "repository_snapshot",
    "publication_snapshot",
    "reference_structure_snapshot",
    "license_snapshot",
    "project_provenance_snapshot",
}

_COMMON_READY_CLAIMS = {
    "acquisition_mode",
    "file_inventory",
    "downloadability",
    "file_checksums",
    "raw_lossless_patterns",
    "series_count",
    "sample_identity",
    "acquisition_identity",
    "accelerating_voltage",
    "detector_metadata",
    "pattern_center",
    "reciprocal_calibration",
    "reuse_license",
    "analyzer_development_nonuse",
}
_REFERENCE_CLAIMS = {
    "source_reference_assignments",
    "independent_reference_structures",
}
_ALL_CLAIMS = _COMMON_READY_CLAIMS | _REFERENCE_CLAIMS

_REPOSITORY_OR_PUBLICATION = {"repository_snapshot", "publication_snapshot"}
_ALLOWED_TYPES_BY_CLAIM = {
    "acquisition_mode": _REPOSITORY_OR_PUBLICATION,
    "file_inventory": {"repository_snapshot"},
    "downloadability": {"repository_snapshot"},
    "file_checksums": {"repository_snapshot"},
    "raw_lossless_patterns": _REPOSITORY_OR_PUBLICATION,
    "series_count": _REPOSITORY_OR_PUBLICATION,
    "sample_identity": _REPOSITORY_OR_PUBLICATION,
    "acquisition_identity": _REPOSITORY_OR_PUBLICATION,
    "accelerating_voltage": _REPOSITORY_OR_PUBLICATION,
    "detector_metadata": _REPOSITORY_OR_PUBLICATION,
    "pattern_center": _REPOSITORY_OR_PUBLICATION,
    "reciprocal_calibration": _REPOSITORY_OR_PUBLICATION,
    "source_reference_assignments": _REPOSITORY_OR_PUBLICATION,
    "independent_reference_structures": {
        "repository_snapshot",
        "publication_snapshot",
        "reference_structure_snapshot",
    },
    "reuse_license": {"repository_snapshot", "license_snapshot"},
    "analyzer_development_nonuse": {"project_provenance_snapshot"},
}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class SourceEvidenceArtifact:
    evidence_id: str
    path: str
    sha256: str
    source_url: str
    source_type: str
    claims: tuple[str, ...]


def parse_source_evidence_artifacts(
    raw: Any,
    *,
    base_dir: Path,
    candidate_record_url: str,
) -> tuple[SourceEvidenceArtifact, ...]:
    """Parse and checksum-verify optional candidate evidence snapshots."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or not raw:
        raise SAEDSourceEvidenceBindingError(
            "source_evidence_artifacts must be a non-empty array when provided"
        )

    root = base_dir.resolve()
    artifacts: list[SourceEvidenceArtifact] = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        context = f"source_evidence_artifacts[{index}]"
        if not isinstance(item, Mapping):
            raise SAEDSourceEvidenceBindingError(f"{context} must be an object")
        allowed = {"evidence_id", "path", "sha256", "source_url", "source_type", "claims"}
        unknown = sorted(set(item) - allowed)
        if unknown:
            raise SAEDSourceEvidenceBindingError(
                f"{context} contains unknown field: {unknown[0]}"
            )

        evidence_id = _text(item, "evidence_id", context)
        if not _IDENTIFIER.fullmatch(evidence_id):
            raise SAEDSourceEvidenceBindingError(
                f"{context}.evidence_id contains unsupported characters"
            )
        if evidence_id in ids:
            raise SAEDSourceEvidenceBindingError(
                "source_evidence_artifacts evidence_id values must be unique"
            )
        ids.add(evidence_id)

        relative = _safe_relative_path(_text(item, "path", context), context)
        candidate = (root / Path(*PurePosixPath(relative).parts)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise SAEDSourceEvidenceBindingError(
                f"{context}.path escapes the registry config directory"
            ) from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise SAEDSourceEvidenceBindingError(
                f"{context}.path must reference a regular non-symlink file"
            )

        sha256 = _text(item, "sha256", context).lower()
        if not _SHA256.fullmatch(sha256):
            raise SAEDSourceEvidenceBindingError(
                f"{context}.sha256 must be a SHA-256 hex digest"
            )
        observed = _hash_file(candidate)
        if observed != sha256:
            raise SAEDSourceEvidenceBindingError(
                f"{context}.sha256 does not match evidence snapshot bytes"
            )

        source_url = _text(item, "source_url", context)
        if not source_url.startswith("https://"):
            raise SAEDSourceEvidenceBindingError(
                f"{context}.source_url must be an HTTPS URL"
            )
        source_type = _text(item, "source_type", context)
        if source_type not in _EVIDENCE_TYPES:
            raise SAEDSourceEvidenceBindingError(
                f"{context}.source_type is unsupported"
            )
        if source_type == "repository_snapshot" and source_url != candidate_record_url:
            raise SAEDSourceEvidenceBindingError(
                f"{context} repository_snapshot source_url must equal candidate record_url"
            )

        claims = _claims(item.get("claims"), context)
        artifacts.append(
            SourceEvidenceArtifact(
                evidence_id=evidence_id,
                path=relative,
                sha256=sha256,
                source_url=source_url,
                source_type=source_type,
                claims=claims,
            )
        )
    return tuple(artifacts)


def evaluate_ready_claim_binding(
    artifacts: Sequence[SourceEvidenceArtifact],
    *,
    reference_claim: str,
) -> dict[str, Any]:
    """Return whether checksum-bound artifacts cover every readiness claim."""
    if reference_claim not in _REFERENCE_CLAIMS:
        raise SAEDSourceEvidenceBindingError("unsupported reference readiness claim")
    required = set(_COMMON_READY_CLAIMS)
    required.add(reference_claim)

    bound_claims: set[str] = set()
    for artifact in artifacts:
        for claim in artifact.claims:
            if artifact.source_type in _ALLOWED_TYPES_BY_CLAIM[claim]:
                bound_claims.add(claim)

    missing = sorted(required - bound_claims)
    return {
        "verified": not missing,
        "artifact_count": len(artifacts),
        "required_claims": sorted(required),
        "bound_claims": sorted(bound_claims),
        "missing_claims": missing,
        "checksum_bound": bool(artifacts),
        "scientific_validity_established": False,
    }


def _claims(raw: Any, context: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise SAEDSourceEvidenceBindingError(
            f"{context}.claims must be a non-empty array"
        )
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise SAEDSourceEvidenceBindingError(
                f"{context}.claims must contain non-empty strings"
            )
        claim = item.strip()
        if claim not in _ALL_CLAIMS:
            raise SAEDSourceEvidenceBindingError(
                f"{context}.claims contains unsupported claim: {claim}"
            )
        values.append(claim)
    if len(values) != len(set(values)):
        raise SAEDSourceEvidenceBindingError(
            f"{context}.claims must not contain duplicates"
        )
    return tuple(values)


def _safe_relative_path(value: str, context: str) -> str:
    pure = PurePosixPath(value.replace("\\", "/"))
    if pure.is_absolute() or value in {"", "."} or ".." in pure.parts:
        raise SAEDSourceEvidenceBindingError(
            f"{context}.path must be a safe relative path"
        )
    return pure.as_posix()


def _text(payload: Mapping[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SAEDSourceEvidenceBindingError(
            f"{context}.{key} must be a non-empty string"
        )
    return value.strip()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "SAEDSourceEvidenceBindingError",
    "SourceEvidenceArtifact",
    "evaluate_ready_claim_binding",
    "parse_source_evidence_artifacts",
]
