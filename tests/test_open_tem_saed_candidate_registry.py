from __future__ import annotations

import json
from pathlib import Path


REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "case_studies"
    / "open_tem_saed_candidates"
    / "candidate_registry.json"
)


def test_open_tem_saed_candidate_registry_is_fail_closed() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["snapshot_date"] == "2026-08-05"
    assert payload["current_decision"]["scientific_evidence_level"] == "Inconclusive"
    assert payload["current_decision"]["external_validation_ready_count"] == 0

    candidates = payload["candidates"]
    candidate_ids = [candidate["candidate_id"] for candidate in candidates]
    assert len(candidate_ids) == len(set(candidate_ids))
    assert candidates

    required = {
        "candidate_id",
        "repository",
        "title",
        "modalities",
        "status",
        "allowed_use",
        "prohibited_claims",
        "next_action",
        "external_validation_ready",
    }
    for candidate in candidates:
        assert required <= candidate.keys()
        assert candidate["external_validation_ready"] is False
        assert candidate["allowed_use"]
        assert candidate["prohibited_claims"]
        assert candidate["next_action"]


def test_open_tem_saed_registry_preserves_mode_and_domain_boundaries() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {candidate["candidate_id"]: candidate for candidate in payload["candidates"]}

    nemi = by_id["zenodo_20411896_nemi_2026_workshop"]
    assert nemi["status"] == "diagnostic_only_mode_or_domain_shift"
    assert "static SAED validation" in nemi["prohibited_claims"]

    empiar = by_id["empiar_general_archive"]
    assert empiar["priority"] == "not_selected"
    assert "external validation based on unrelated cryo-EM data" in empiar[
        "prohibited_claims"
    ]

    repod = by_id["repod_siowh6_cofeni_tem_saed"]
    assert repod["status"] == "ready_for_bounded_source_audit"
    assert repod["external_validation_ready"] is False
