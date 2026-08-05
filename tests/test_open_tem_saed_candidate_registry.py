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
    assert payload["snapshot_status"] == (
        "updated_after_repod_source_audit_and_zenodo_silver_metadata_audit"
    )
    assert payload["current_decision"]["scientific_evidence_level"] == "Inconclusive"
    assert payload["current_decision"]["external_validation_ready_count"] == 0
    assert payload["current_decision"]["download_now"] == []

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
    assert repod["status"] == "bounded_source_audit_complete_diagnostic_only"
    assert repod["priority"] == "diagnostic_audit_complete"
    assert repod["source_audit"]["source_identity_and_archive_integrity"] == "Supported"
    assert repod["source_audit"]["audited_member_count"] == 7
    assert repod["source_audit"]["lossless_raster_member_count"] == 7
    assert repod["source_audit"]["native_microscopy_member_count"] == 0
    assert repod["external_validation_ready"] is False
    assert "TEM segmentation performance" in repod["prohibited_claims"]

    silver = by_id["zenodo_18942976_silver_tem_saed"]
    assert silver["status"] == (
        "metadata_audit_complete_archive_download_not_yet_authorized"
    )
    assert silver["priority"] == "metadata_audit_complete_archive_inventory_pending"
    assert silver["metadata_audit"]["record_identity_and_file_inventory"] == "Supported"
    assert silver["metadata_audit"]["temporal_metadata_consistency"] == "Inconclusive"
    assert silver["metadata_audit"]["target_archive_bytes"] == 1417789651
    assert silver["metadata_audit"]["resource_type_id"] == "image"
    assert silver["external_validation_ready"] is False
    assert silver["metadata_quality_flags"]

    current = payload["current_decision"]
    assert current["source_audit_complete_diagnostic_only"] == [
        "repod_siowh6_cofeni_tem_saed"
    ]
    assert current["metadata_audit_complete_archive_inventory_pending"] == [
        "zenodo_18942976_silver_tem_saed"
    ]
    assert current["archive_inventory_authorization_pending_review"] == [
        "zenodo_18942976_silver_tem_saed"
    ]
