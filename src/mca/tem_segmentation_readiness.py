"""Consolidate existing TEM segmentation audits into one fail-closed readiness view.

This module consumes checksum-bound summary artifacts produced by existing audits.
It does not download source arrays, train a model, run inference, compute
segmentation metrics, or turn diagnostic evidence into a performance claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import __version__

CASE_ID = "tem_segmentation_model_readiness"
SCHEMA_VERSION = "1.0"

TRAINING_CASE_ID = "public_cobalt_oxide_tem_training_data_audit"
PARENT_OVERLAP_CASE_ID = "public_cobalt_oxide_tem_parent_overlap_audit"
EXTERNAL_CANDIDATE_CASE_ID = "dryad_hrtem_external_validation_candidate_assessment"
PILOT_CASE_ID = "dryad_hrtem_pilot_pair_audit"

NOT_READY = "not_ready_for_scientific_model_performance_evaluation"
TRAINING_BLOCKED = "blocked_training_data_integrity"
CROSS_MATERIAL_READY = (
    "ready_to_freeze_diagnostic_cross_material_stress_test_protocol"
)
IN_DOMAIN_PROTOCOL_READY = "ready_to_freeze_predeclared_in_domain_evaluation_protocol"


class EvidenceContractError(ValueError):
    """Raised when an input summary does not satisfy its declared contract."""


def build_tem_segmentation_readiness(
    *,
    training_summary_path: str | Path,
    parent_overlap_summary_path: str | Path,
    output_dir: str | Path,
    external_candidate_summary_path: str | Path | None = None,
    pilot_readiness_path: str | Path | None = None,
    pilot_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build one readiness decision from existing audit summaries.

    Required inputs establish the integrity and leakage state of the target
    cobalt-oxide training data. Optional external-source inputs refine the
    external-validation and cross-material diagnostic gates. Missing optional
    evidence remains unresolved; it never becomes a passed gate.
    """

    output, output_created_by_call = _prepare_output(output_dir)
    try:
        training, training_record = _load_evidence(
            training_summary_path,
            role="training_data_audit",
            expected_case_id=TRAINING_CASE_ID,
        )
        parent, parent_record = _load_evidence(
            parent_overlap_summary_path,
            role="training_parent_overlap_audit",
            expected_case_id=PARENT_OVERLAP_CASE_ID,
        )
        candidate: Mapping[str, Any] | None = None
        candidate_record: dict[str, Any] | None = None
        if external_candidate_summary_path is not None:
            candidate, candidate_record = _load_evidence(
                external_candidate_summary_path,
                role="external_candidate_assessment",
                expected_case_id=EXTERNAL_CANDIDATE_CASE_ID,
            )
        pilot_readiness: Mapping[str, Any] | None = None
        pilot_readiness_record: dict[str, Any] | None = None
        if pilot_readiness_path is not None:
            pilot_readiness, pilot_readiness_record = _load_evidence(
                pilot_readiness_path,
                role="external_pilot_acquisition_readiness",
                expected_case_id=PILOT_CASE_ID,
                require_software_version=False,
            )
        pilot_summary: Mapping[str, Any] | None = None
        pilot_summary_record: dict[str, Any] | None = None
        if pilot_summary_path is not None:
            pilot_summary, pilot_summary_record = _load_evidence(
                pilot_summary_path,
                role="external_pilot_hdf5_overlap_audit",
                expected_case_id=PILOT_CASE_ID,
            )

        gates = _evaluate_gates(
            training=training,
            parent=parent,
            candidate=candidate,
            pilot_readiness=pilot_readiness,
            pilot_summary=pilot_summary,
        )
        decision = _make_decision(gates)
        evidence_records = [training_record, parent_record]
        evidence_records.extend(
            record
            for record in (
                candidate_record,
                pilot_readiness_record,
                pilot_summary_record,
            )
            if record is not None
        )

        training_patch_count = _integer(
            _mapping(training, "result_counts"), "patch_pair_count"
        )
        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "evidence_inputs": evidence_records,
            "evidence_gates": gates,
            "decision": decision,
            "processing": {
                "source_arrays_downloaded": False,
                "source_arrays_modified": False,
                "labels_remapped": False,
                "model_training_performed": False,
                "model_inference_performed": False,
                "segmentation_metrics_computed": False,
                "physical_conversion_performed": False,
            },
            "scientific_closeout": _scientific_closeout(
                decision=decision,
                gates=gates,
                training_patch_count=training_patch_count,
            ),
        }

        summary_path = output / "tem_segmentation_readiness_summary.json"
        report_path = output / "tem_segmentation_readiness_report.md"
        manifest_path = output / "tem_segmentation_readiness_manifest.json"
        _write_json(summary_path, summary)
        report_path.write_text(_build_report(summary), encoding="utf-8")
        manifest = _build_manifest(
            output=output,
            generated=[summary_path, report_path],
            evidence=evidence_records,
        )
        _write_json(manifest_path, manifest)
        return summary
    except Exception:
        if output_created_by_call and output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise


def _evaluate_gates(
    *,
    training: Mapping[str, Any],
    parent: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    pilot_readiness: Mapping[str, Any] | None,
    pilot_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    training_sha256 = _training_images_sha256(
        training, role="training_data_audit"
    )
    parent_training_sha256 = _training_images_sha256(
        parent, role="training_parent_overlap_audit"
    )
    if training_sha256 != parent_training_sha256:
        raise EvidenceContractError(
            "training and parent-overlap summaries reference different training images"
        )

    values = _mapping(training, "value_contract")
    split = _mapping(training, "notebook_split_audit")
    grouping = _mapping(training, "candidate_parent_grouping")
    training_counts = _mapping(training, "result_counts")
    training_integrity = all(
        _boolean(values, key)
        for key in (
            "all_images_finite",
            "all_labels_finite",
            "labels_binary",
            "label_channels_complementary_one_hot",
        )
    ) and _integer(training_counts, "patch_pair_count") > 0

    parent_readiness = _mapping(parent, "external_validation_readiness")
    parent_counts = _mapping(parent, "result_counts")
    parent_source_independent_labels = _boolean(
        parent_readiness, "source_masks_are_independent_ground_truth"
    )
    parent_disjointness = _boolean(
        parent_readiness, "parent_disjointness_proven_for_nonmatching_frames"
    )
    parent_external_count = _integer(
        parent_counts, "independent_external_validation_candidate_count"
    )

    candidate_present = candidate is not None
    candidate_in_domain_count = 0
    candidate_target_match = False
    candidate_lineage = False
    candidate_nonuse = False
    candidate_model_eval_allowed = False
    candidate_creator_overlap = False
    candidate_multi_labeler = False
    if candidate is not None:
        candidate_counts = _mapping(candidate, "result_counts")
        candidate_target = _mapping(candidate, "target_comparison")
        candidate_gates = _mapping(candidate_target, "gates")
        candidate_readiness = _mapping(candidate, "readiness")
        candidate_in_domain_count = _integer(
            candidate_counts, "independent_in_domain_external_validation_pair_count"
        )
        candidate_target_match = _boolean(candidate_gates, "target_material_match")
        candidate_lineage = _boolean(
            candidate_gates, "immutable_cross_dataset_lineage_manifest_available"
        )
        candidate_nonuse = _boolean(
            candidate_gates, "verified_not_used_for_target_model_training"
        )
        candidate_model_eval_allowed = _boolean(
            candidate_readiness, "model_evaluation_allowed_now"
        )
        candidate_creator_overlap = _boolean(
            candidate_gates, "creator_overlap_with_target_dataset"
        )
        candidate_multi_labeler = _boolean(
            candidate_gates, "multi_labeler_or_adjudication_evidence_available"
        )

    pilot_metadata_verified = False
    pilot_hdf5_complete = False
    pilot_overlap_complete = False
    pilot_status = "not_supplied"
    if pilot_readiness is not None:
        pilot_status = _text(pilot_readiness, "status")
        pilot_metadata_verified = _boolean(
            pilot_readiness, "live_metadata_and_source_version_verified"
        )
        pilot_hdf5_complete = _boolean(
            pilot_readiness, "real_hdf5_audit_performed"
        )
        pilot_overlap_complete = _boolean(
            pilot_readiness, "real_content_overlap_audit_performed"
        )

    pilot_overlap_gate_passed = False
    if pilot_summary is not None:
        pilot_ready = _mapping(pilot_summary, "readiness")
        pilot_metadata_verified = True
        pilot_hdf5_complete = True
        pilot_overlap_complete = True
        pilot_overlap_gate_passed = _boolean(
            pilot_ready, "content_overlap_gate_passed"
        )
        pilot_status = _text(pilot_ready, "next_status")

    authoritative_parent_ids = _boolean(
        grouping, "authoritative_parent_ids_available"
    )
    internal_parent_disjoint = _boolean(
        split, "independent_parent_image_validation"
    )
    parent_level_independence = (
        internal_parent_disjoint
        or parent_disjointness
        or (candidate_lineage and candidate_nonuse)
    )
    independent_in_domain_external = (
        (
            parent_external_count > 0
            and parent_source_independent_labels
            and parent_disjointness
        )
        or (
            candidate_in_domain_count > 0
            and candidate_target_match
            and candidate_lineage
            and candidate_nonuse
            and candidate_model_eval_allowed
        )
    )
    cross_material_protocol_freeze_ready = (
        training_integrity
        and pilot_summary is not None
        and pilot_hdf5_complete
        and pilot_overlap_complete
        and pilot_overlap_gate_passed
    )
    scientific_evaluation_ready = (
        training_integrity
        and parent_level_independence
        and independent_in_domain_external
    )

    unresolved: list[str] = []
    if not authoritative_parent_ids:
        unresolved.append("authoritative_training_patch_to_parent_mapping")
    if not parent_level_independence:
        unresolved.append("parent_or_acquisition_disjointness")
    if not independent_in_domain_external:
        unresolved.append("independent_in_domain_cobalt_oxide_validation_set")
    if not candidate_present:
        unresolved.append("external_candidate_assessment_not_supplied")
    if pilot_readiness is None and pilot_summary is None:
        unresolved.append("external_pilot_readiness_not_supplied")
    elif not pilot_hdf5_complete or not pilot_overlap_complete:
        unresolved.append("authenticated_external_pilot_hdf5_and_overlap_audit")

    return {
        "training_pair_integrity_validated": training_integrity,
        "training_artifact_identity_bound_across_audits": True,
        "training_images_sha256": training_sha256,
        "authoritative_training_parent_ids_available": authoritative_parent_ids,
        "parent_disjoint_internal_validation_available": internal_parent_disjoint,
        "parent_or_acquisition_disjointness_proven": parent_level_independence,
        "independent_in_domain_external_validation_available": independent_in_domain_external,
        "external_candidate_assessment_supplied": candidate_present,
        "external_candidate_target_material_match": candidate_target_match,
        "external_candidate_creator_overlap_reported": candidate_creator_overlap,
        "external_candidate_multi_labeler_or_adjudication_available": candidate_multi_labeler,
        "external_pilot_metadata_verified": pilot_metadata_verified,
        "external_pilot_hdf5_audit_complete": pilot_hdf5_complete,
        "external_pilot_content_overlap_audit_complete": pilot_overlap_complete,
        "external_pilot_content_overlap_gate_passed": pilot_overlap_gate_passed,
        "external_pilot_status": pilot_status,
        "diagnostic_cross_material_protocol_freeze_ready": (
            cross_material_protocol_freeze_ready
        ),
        "diagnostic_cross_material_stress_test_ready": False,
        "in_domain_protocol_freeze_ready": scientific_evaluation_ready,
        "scientific_in_domain_evaluation_ready": False,
        "unresolved_evidence": unresolved,
    }


def _make_decision(gates: Mapping[str, Any]) -> dict[str, Any]:
    training_integrity = bool(gates["training_pair_integrity_validated"])
    in_domain_protocol_ready = bool(gates["in_domain_protocol_freeze_ready"])
    cross_material_protocol_ready = bool(
        gates["diagnostic_cross_material_protocol_freeze_ready"]
    )
    if not training_integrity:
        status = TRAINING_BLOCKED
        next_action = (
            "Resolve training image-label integrity failures before any model training."
        )
    elif in_domain_protocol_ready:
        status = IN_DOMAIN_PROTOCOL_READY
        next_action = (
            "Freeze metrics, exclusions, confidence intervals, and the untouched "
            "evaluation manifest before running model inference once."
        )
    elif cross_material_protocol_ready:
        status = CROSS_MATERIAL_READY
        next_action = (
            "Freeze the diagnostic cross-material metrics, exclusions, uncertainty "
            "method, model version, and untouched evaluation manifest before any "
            "pilot inference, while continuing to seek an independent in-domain set."
        )
    else:
        status = NOT_READY
        next_action = (
            "Acquire and checksum-bind a predeclared parent-disjoint cobalt-oxide "
            "validation set with immutable acquisition lineage and independent expert labels."
        )

    return {
        "status": status,
        "software_experiment_training_allowed": training_integrity,
        "predeclared_in_domain_protocol_freeze_ready": (
            in_domain_protocol_ready
        ),
        "scientific_in_domain_performance_evaluation_ready": False,
        "independent_performance_claim_ready": False,
        "diagnostic_cross_material_protocol_freeze_ready": (
            cross_material_protocol_ready
        ),
        "diagnostic_cross_material_stress_test_ready": False,
        "engineering_release_ready": False,
        "model_retraining_is_current_priority": False,
        "next_action": next_action,
        "later_action": (
            "After a valid evaluation set and frozen protocol exist, run inference once, "
            "report predefined metrics with uncertainty, and preserve all exclusions and "
            "software/model versions."
        ),
    }


def _scientific_closeout(
    *,
    decision: Mapping[str, Any],
    gates: Mapping[str, Any],
    training_patch_count: int,
) -> dict[str, Any]:
    if not bool(gates["training_pair_integrity_validated"]):
        status = "Unsupported"
        strongest = (
            f"The supplied training audit covers {training_patch_count} paired patches, "
            "but one or more required finite/binary/complementary-label integrity gates fail."
        )
        limitation = (
            "Training image-label integrity is unresolved, so neither training nor any "
            "downstream in-domain or cross-material model test is supportable."
        )
    elif bool(gates["in_domain_protocol_freeze_ready"]):
        status = "Supported"
        strongest = (
            f"Training integrity is validated for {training_patch_count} paired patches, "
            "the parent/acquisition independence gate passes, and an independent in-domain "
            "candidate satisfies the supplied lineage and non-use gates."
        )
        limitation = (
            "The evaluation protocol has not yet been frozen or executed; no inference, "
            "segmentation metrics, uncertainty interval, or performance claim exists."
        )
    elif bool(gates["diagnostic_cross_material_protocol_freeze_ready"]):
        status = "Diagnostic"
        strongest = (
            f"Training integrity is validated for {training_patch_count} paired patches and "
            "the cross-material pilot HDF5/content-overlap gate passes."
        )
        limitation = (
            "The pilot is cross-material and its diagnostic protocol has not yet been frozen; "
            "it cannot establish cobalt-oxide in-domain performance."
        )
    else:
        status = "Supported"
        strongest = (
            f"The checksum-bound training audit validates integrity for {training_patch_count} "
            "paired patches, while the supplied evidence does not establish a usable "
            "independent in-domain external-validation set."
        )
        limitation = (
            "No immutable authoritative training patch-to-parent map and no predeclared "
            "parent-disjoint cobalt-oxide validation set with independent labels are available."
        )
    return {
        "status": status,
        "result": decision["status"],
        "strongest_evidence": strongest,
        "primary_limitation": limitation,
        "evidence_that_would_change_conclusion": (
            "A checksum-bound cobalt-oxide validation set with immutable sample/acquisition "
            "lineage, independent blinded expert labels and adjudication, documented non-use "
            "in model development, a frozen protocol, and the later one-time metric results."
        ),
        "suitable_for": [
            "deciding whether software-only training experiments may proceed",
            "blocking unsupported segmentation performance claims",
            "prioritizing the next evidence acquisition or protocol-freeze step",
        ],
        "not_suitable_for": [
            "estimating segmentation accuracy before evaluation results exist",
            "selecting a production model",
            "nanometre-scale physical measurement",
            "causal or mechanistic interpretation",
            "engineering release",
        ],
    }


def _training_images_sha256(
    payload: Mapping[str, Any], *, role: str
) -> str:
    source = _mapping(payload, "source")
    training_images = _mapping(source, "training_images")
    digest = _text(training_images, "sha256").lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EvidenceContractError(f"{role} training_images.sha256 is invalid")
    return digest


def _load_evidence(
    path: str | Path,
    *,
    role: str,
    expected_case_id: str,
    require_software_version: bool = True,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    raw = source.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceContractError(f"{role} must be valid UTF-8 JSON: {source}") from exc
    if not isinstance(payload, Mapping):
        raise EvidenceContractError(f"{role} must contain a JSON object.")
    if _text(payload, "schema_version") != SCHEMA_VERSION:
        raise EvidenceContractError(f"unsupported {role} schema_version.")
    case_id = _text(payload, "case_id")
    if case_id != expected_case_id:
        raise EvidenceContractError(
            f"{role} case_id mismatch: {case_id!r} != {expected_case_id!r}"
        )
    software_version = payload.get("software_version")
    if require_software_version and (
        not isinstance(software_version, str) or not software_version.strip()
    ):
        raise EvidenceContractError(f"{role} lacks software_version.")
    return payload, {
        "role": role,
        "path": source.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "case_id": case_id,
        "schema_version": SCHEMA_VERSION,
        "software_version": software_version if isinstance(software_version, str) else None,
    }


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    created_by_call = False
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise FileExistsError("output directory must be absent or empty.")
    else:
        output.mkdir(parents=True)
        created_by_call = True
    return output, created_by_call


def _build_manifest(
    *,
    output: Path,
    generated: list[Path],
    evidence: list[Mapping[str, Any]],
) -> dict[str, Any]:
    artifacts = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in generated
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "software_version": __version__,
        "input_count": len(evidence),
        "inputs": list(evidence),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def _build_report(summary: Mapping[str, Any]) -> str:
    decision = _mapping(summary, "decision")
    gates = _mapping(summary, "evidence_gates")
    unresolved = gates.get("unresolved_evidence")
    if not isinstance(unresolved, list) or not all(
        isinstance(item, str) for item in unresolved
    ):
        raise EvidenceContractError("unresolved_evidence must be a list of strings.")
    lines = [
        "# TEM Segmentation Model Readiness",
        "",
        "**Evidence conclusion:** Supported",
        "",
        f"**Readiness result:** `{decision['status']}`",
        "",
        "## Now",
        "",
        f"- Software-only training experiment allowed: `{str(decision['software_experiment_training_allowed']).lower()}`",
        f"- Scientific in-domain evaluation ready: `{str(decision['scientific_in_domain_performance_evaluation_ready']).lower()}`",
        f"- Independent performance claim ready: `{str(decision['independent_performance_claim_ready']).lower()}`",
        f"- Diagnostic cross-material stress test ready: `{str(decision['diagnostic_cross_material_stress_test_ready']).lower()}`",
        f"- Engineering release ready: `{str(decision['engineering_release_ready']).lower()}`",
        "",
        "## Evidence gates",
        "",
    ]
    for key, value in gates.items():
        if key == "unresolved_evidence":
            continue
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Unresolved evidence", ""])
    lines.extend(f"- {item}" for item in unresolved)
    lines.extend(
        [
            "",
            "## Next",
            "",
            f"{decision['next_action']}",
            "",
            "## Later",
            "",
            f"{decision['later_action']}",
            "",
            "## Scientific limitation",
            "",
            "This report consolidates prior audit evidence. It does not train or evaluate a model and does not estimate segmentation accuracy.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{key} must be an object.")
    return value


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise EvidenceContractError(f"{key} must be a boolean.")
    return value


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceContractError(f"{key} must be an integer.")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceContractError(f"{key} must be non-empty text.")
    return value
