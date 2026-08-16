from __future__ import annotations

import copy

import pytest

from mca.evidence_ladder import (
    EvidenceLadderError,
    LEVELS,
    evaluate_evidence_ladder,
)


def _sha(char: str) -> str:
    return char * 64


def _level(assessment: str, evidence: list[str] | None = None) -> dict[str, object]:
    return {
        "assessment": assessment,
        "evidence": evidence if evidence is not None else (["verified evidence"] if assessment == "Supported" else []),
        "limitations": [],
    }


def _declaration(*, supported_through: int = 8, blocker: str = "Unsupported") -> dict[str, object]:
    levels: dict[str, dict[str, object]] = {}
    for index, level in enumerate(LEVELS):
        levels[level] = _level("Supported" if index <= supported_through else blocker)
    return {
        "schema_version": "1.0",
        "declaration_id": "case-1",
        "subject": {
            "modality": "SAED",
            "source_material_domain": "reference-material",
            "target_material_domain": "Co3O4",
            "claim_scope": "method_validation",
        },
        "source_bindings": [
            {"role": "source_manifest", "sha256": _sha("a")},
            {"role": "analysis_report", "sha256": _sha("b")},
        ],
        "levels": levels,
        "limitations": [],
    }


def test_complete_ladder_reaches_engineering_readiness() -> None:
    result = evaluate_evidence_ladder(_declaration())

    assert result["highest_contiguous_supported_level"] == LEVELS[-1]
    assert result["first_blocking_level"] is None
    assert result["readiness"]["engineering_decision_ready"] is True
    assert result["handoff"]["scientific_status_promoted"] is False
    assert result["handoff"]["downstream_use_authorized"] is False


def test_software_only_case_cannot_be_promoted_to_raw_or_scientific_validation() -> None:
    result = evaluate_evidence_ladder(_declaration(supported_through=0))

    assert result["highest_contiguous_supported_level"] == "L0_software_integration"
    assert result["first_blocking_level"] == "L1_raw_representation_identity"
    assert result["readiness"]["raw_representation_ready"] is False
    assert result["readiness"]["method_validation_ready"] is False
    assert result["readiness"]["independent_external_validation_ready"] is False


def test_cross_material_dataset_can_stop_after_method_validation() -> None:
    result = evaluate_evidence_ladder(_declaration(supported_through=4))

    assert result["highest_contiguous_supported_level"] == "L4_method_algorithm_validation"
    assert result["readiness"]["method_validation_ready"] is True
    assert result["readiness"]["material_domain_validation_ready"] is False
    assert result["readiness"]["independent_external_validation_ready"] is False
    assert result["policy_boundary"]["cross_material_proxy_promoted_to_target_material_validation"] is False


def test_exact_material_case_can_stop_at_independence_boundary() -> None:
    declaration = _declaration(supported_through=5, blocker="Inconclusive")
    declaration["subject"]["source_material_domain"] = "Co3O4"
    declaration["subject"]["claim_scope"] = "material_validation"
    result = evaluate_evidence_ladder(declaration)

    assert result["highest_contiguous_supported_level"] == "L5_material_domain_validation"
    assert result["first_blocking_level"] == "L6_independent_external_validation"
    assert result["readiness"]["material_domain_validation_ready"] is True
    assert result["readiness"]["independent_external_validation_ready"] is False


def test_supported_level_cannot_skip_an_unsupported_lower_level() -> None:
    declaration = _declaration(supported_through=3)
    declaration["levels"]["L5_material_domain_validation"] = _level("Supported")

    with pytest.raises(EvidenceLadderError, match="cannot be Supported"):
        evaluate_evidence_ladder(declaration)


def test_supported_level_requires_nonempty_evidence() -> None:
    declaration = _declaration(supported_through=2)
    declaration["levels"]["L1_raw_representation_identity"]["evidence"] = []

    with pytest.raises(EvidenceLadderError, match="must not be empty"):
        evaluate_evidence_ladder(declaration)


def test_invalid_checksum_and_duplicate_binding_roles_are_rejected() -> None:
    invalid = _declaration(supported_through=0)
    invalid["source_bindings"][0]["sha256"] = "not-a-sha"
    with pytest.raises(EvidenceLadderError, match="SHA-256"):
        evaluate_evidence_ladder(invalid)

    duplicate = _declaration(supported_through=0)
    duplicate["source_bindings"][1]["role"] = "source_manifest"
    with pytest.raises(EvidenceLadderError, match="duplicate source binding role"):
        evaluate_evidence_ladder(duplicate)


def test_unknown_fields_fail_closed() -> None:
    declaration = _declaration(supported_through=0)
    declaration["levels"]["L0_software_integration"]["confidence"] = 0.99

    with pytest.raises(EvidenceLadderError, match="unknown field"):
        evaluate_evidence_ladder(declaration)


def test_assessment_hash_is_deterministic_and_binds_changes() -> None:
    first = evaluate_evidence_ladder(_declaration(supported_through=4))
    second = evaluate_evidence_ladder(_declaration(supported_through=4))
    changed = copy.deepcopy(_declaration(supported_through=4))
    changed["limitations"].append("A newly declared limitation")
    third = evaluate_evidence_ladder(changed)

    assert first["assessment_sha256"] == second["assessment_sha256"]
    assert first["assessment_sha256"] != third["assessment_sha256"]
