"""Bridge a candidate-registry summary into the consolidated TEM readiness view.

The registry can refine the next acquisition action, but it cannot itself prove
sample/acquisition independence or authorize model evaluation. A candidate must
still pass a dedicated checksum, lineage, label, non-use, and overlap audit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .tem_external_validation_candidate_registry import CASE_ID as REGISTRY_CASE_ID
from .tem_segmentation_readiness import (
    NOT_READY,
    EvidenceContractError,
    _build_manifest,
    _build_report,
    _write_json,
    build_tem_segmentation_readiness,
)

SCHEMA_VERSION = "1.0"


def build_tem_segmentation_readiness_with_registry(
    *,
    training_summary_path: str | Path,
    parent_overlap_summary_path: str | Path,
    output_dir: str | Path,
    external_candidate_summary_path: str | Path | None = None,
    pilot_readiness_path: str | Path | None = None,
    pilot_summary_path: str | Path | None = None,
    candidate_registry_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build readiness and optionally attach a fail-closed candidate registry."""
    registry: Mapping[str, Any] | None = None
    registry_record: dict[str, Any] | None = None
    if candidate_registry_summary_path is not None:
        registry, registry_record = _load_registry(candidate_registry_summary_path)

    summary = build_tem_segmentation_readiness(
        training_summary_path=training_summary_path,
        parent_overlap_summary_path=parent_overlap_summary_path,
        external_candidate_summary_path=external_candidate_summary_path,
        pilot_readiness_path=pilot_readiness_path,
        pilot_summary_path=pilot_summary_path,
        output_dir=output_dir,
    )
    if registry is None or registry_record is None:
        return summary

    counts = _mapping(registry, "result_counts")
    readiness = _mapping(registry, "readiness")
    ready_count = _integer(counts, "in_domain_external_validation_ready_count")
    search_completed = _boolean(
        readiness, "candidate_search_completed_for_snapshot"
    )
    supports_evaluation = _boolean(
        readiness, "public_search_supports_model_evaluation_now"
    )
    recommended_id = _text(readiness, "recommended_candidate_id")
    recommended_status = _text(readiness, "recommended_candidate_status")
    recommended_action = _text(readiness, "recommended_next_action")

    evidence = summary.get("evidence_inputs")
    gates = summary.get("evidence_gates")
    decision = summary.get("decision")
    if not isinstance(evidence, list):
        raise EvidenceContractError("evidence_inputs must be a list")
    if not isinstance(gates, dict) or not isinstance(decision, dict):
        raise EvidenceContractError("readiness summary lacks mutable gate objects")
    evidence.append(registry_record)
    gates.update(
        {
            "candidate_registry_supplied": True,
            "candidate_registry_search_completed_for_snapshot": search_completed,
            "candidate_registry_in_domain_ready_count": ready_count,
            "candidate_registry_supports_model_evaluation_now": supports_evaluation,
            "candidate_registry_recommended_candidate_id": recommended_id,
            "candidate_registry_recommended_candidate_status": recommended_status,
        }
    )
    unresolved = gates.get("unresolved_evidence")
    if not isinstance(unresolved, list) or not all(
        isinstance(item, str) for item in unresolved
    ):
        raise EvidenceContractError("unresolved_evidence must be a list of strings")
    if ready_count == 0 or not supports_evaluation:
        unresolved.append("public_candidate_registry_has_no_evaluation_ready_set")
    else:
        unresolved.append("candidate_registry_requires_dedicated_candidate_audit")

    # Registry triage never grants evaluation readiness. It only narrows the next
    # evidence-acquisition step while the core decision remains fail closed.
    if decision.get("status") == NOT_READY:
        decision["next_action"] = recommended_action

    output = Path(output_dir)
    summary_path = output / "tem_segmentation_readiness_summary.json"
    report_path = output / "tem_segmentation_readiness_report.md"
    manifest_path = output / "tem_segmentation_readiness_manifest.json"
    _write_json(summary_path, summary)
    report_path.write_text(_build_report(summary), encoding="utf-8")
    _write_json(
        manifest_path,
        _build_manifest(
            output=output,
            generated=[summary_path, report_path],
            evidence=evidence,
        ),
    )
    return summary


def _load_registry(
    path: str | Path,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    raw = source.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceContractError(
            f"candidate registry must be valid UTF-8 JSON: {source}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise EvidenceContractError("candidate registry must contain a JSON object")
    if _text(payload, "schema_version") != SCHEMA_VERSION:
        raise EvidenceContractError("unsupported candidate registry schema_version")
    if _text(payload, "case_id") != REGISTRY_CASE_ID:
        raise EvidenceContractError("candidate registry case_id mismatch")
    software_version = _text(payload, "software_version")
    return payload, {
        "role": "external_validation_candidate_registry",
        "path": source.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "case_id": REGISTRY_CASE_ID,
        "schema_version": SCHEMA_VERSION,
        "software_version": software_version,
    }


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{key} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceContractError(f"{key} must be non-empty text")
    return value.strip()


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceContractError(f"{key} must be an integer")
    return value


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise EvidenceContractError(f"{key} must be a boolean")
    return value
