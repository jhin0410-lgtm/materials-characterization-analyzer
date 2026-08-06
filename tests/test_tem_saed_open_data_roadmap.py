from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "TEM_SAED_OPEN_DATA_ROADMAP.md"
STATUS = (
    ROOT
    / "case_studies"
    / "open_tem_saed_candidates"
    / "audit_status_2026-08-06.json"
)


def test_tem_saed_open_data_roadmap_matches_latest_audit_status() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert "Status date: **2026-08-06**" in roadmap
    assert str(STATUS.relative_to(ROOT)).replace("\\", "/") in roadmap
    assert "Four public sources have reached level 3. None has reached level 4." in roadmap
    assert "Bounded source audits completed for diagnostic use only: **4**." in roadmap
    assert "Sources blocked at access or file-inventory resolution: **3**." in roadmap
    assert "External-validation-ready analyzers: **0**." in roadmap
    assert "Engineering-decision-ready analyzers: **0**." in roadmap

    for snapshot in (
        "case_studies/repod_cofeni_tem_saed_source_audit/verified_snapshot.json",
        "case_studies/zenodo_silver_tem_saed_archive_audit/verified_snapshot.json",
        "case_studies/zenodo_wtacrv_tem_saed_source_audit/verified_workflow_snapshot.json",
        "case_studies/zenodo_ge_dm3_tem_saed_source_audit/verified_snapshot.json",
        "case_studies/mendeley_lunar_tem_saed_source_audit/verified_expanded_registry_snapshot.json",
        "case_studies/dryad_tise2_saed_source_audit/verified_snapshot.json",
        "case_studies/fhi_co3o4_tem_saed_source_audit/verified_snapshot.json",
    ):
        assert snapshot in roadmap
        assert (ROOT / snapshot).is_file()

    assert "Two public sources have now reached level 3" not in roadmap
    assert "exact linked record versions, files, and checksums unresolved" not in roadmap
