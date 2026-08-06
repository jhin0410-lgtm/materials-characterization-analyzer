from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = (
    ROOT
    / "case_studies"
    / "open_tem_saed_candidates"
    / "audit_status_2026-08-06.json"
)


def _load_status() -> dict[str, object]:
    return json.loads(STATUS.read_text(encoding="utf-8"))


def test_tem_saed_audit_status_is_fail_closed_and_internally_consistent() -> None:
    payload = _load_status()

    assert payload["schema_version"] == "1.0"
    assert payload["status_date"] == "2026-08-06"

    decision = payload["current_decision"]
    assert decision["scientific_evidence_level"] == "Inconclusive"
    assert decision["external_validation_ready_count"] == 0
    assert decision["engineering_decision_ready_count"] == 0
    assert decision["performance_evaluation_authorized"] is False
    assert decision["parameter_tuning_authorized"] is False
    assert decision["model_retraining_authorized"] is False

    sources = payload["sources"]
    candidate_ids = [source["candidate_id"] for source in sources]
    assert len(candidate_ids) == len(set(candidate_ids))

    bounded = [
        source
        for source in sources
        if source["audit_level"] == "bounded_source_audit_complete"
    ]
    access_or_inventory_blocked = [
        source
        for source in sources
        if source["audit_level"] != "bounded_source_audit_complete"
    ]
    assert len(bounded) == decision[
        "bounded_source_audit_complete_diagnostic_only_count"
    ]
    assert len(access_or_inventory_blocked) == decision[
        "access_or_file_inventory_blocked_count"
    ]

    for source in sources:
        assert source["confirmed_evidence"]
        assert source["blocking_gates"]
        assert source["external_validation_ready"] is False
        assert source["engineering_decision_ready"] is False
        assert (ROOT / source["verified_snapshot"]).is_file()


def test_tem_saed_audit_status_preserves_source_audit_boundaries() -> None:
    payload = _load_status()
    by_id = {source["candidate_id"]: source for source in payload["sources"]}

    assert {
        source["candidate_id"]
        for source in payload["sources"]
        if source["audit_level"] == "bounded_source_audit_complete"
    } == {
        "repod_siowh6_cofeni_tem_saed",
        "zenodo_18942976_silver_tem_saed",
        "zenodo_10512357_wtacrv_tem_saed",
        "zenodo_15082448_ge_dm3_tem_saed",
    }

    wtacrv = by_id["zenodo_10512357_wtacrv_tem_saed"]
    assert wtacrv["source_identity"] == "10.5281/zenodo.10512463"
    assert wtacrv["parent_record_identity"] == "10.5281/zenodo.10512357"
    assert "target-domain comparability" in wtacrv["blocking_gates"]

    mendeley = by_id["mendeley_lunar_tem_saed_registry"]
    assert mendeley["audit_level"] == "public_landing_audit_complete"
    assert mendeley["status"] == "file_inventory_blocked_by_oauth"

    dryad = by_id["dryad_6djh9w1hw_tise2_saed"]
    assert dryad["status"] == "anonymous_download_blocked"
    assert "source archive acquisition" in dryad["blocking_gates"]

    fhi = by_id["fhi_d63268_co3o4_tem_saed"]
    assert fhi["material_domain"] == "Co3O4 exact-material TEM source"
    assert fhi["status"] == "anonymous_download_requires_authentication"
