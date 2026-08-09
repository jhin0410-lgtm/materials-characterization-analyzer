from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "case_studies"
    / "tm_fe_si_public_excel_source_audit"
    / "source_audit_snapshot.json"
)


def _load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_source_identity_and_uploaded_subset_are_pinned() -> None:
    data = _load()
    source = data["source"]
    assert data["schema_version"] == "1.0"
    assert source["article_doi"] == "10.1016/j.dib.2022.108868"
    assert source["dataset_doi"] == "10.17632/gp8rkw2k6v.2"
    assert source["dataset_version"] == 2
    assert source["dataset_license"] == "CC BY 4.0"
    assert source["uploaded_subset_file_count"] == 13
    assert source["uploaded_subset_contains_sem_eds_files"] is False


def test_workbook_identity_and_actual_ranges_are_unique() -> None:
    data = _load()
    workbooks = data["workbooks"]
    assert len(workbooks) == 13
    assert len({row["file"] for row in workbooks}) == 13
    assert len({row["sha256"] for row in workbooks}) == 13
    assert all(len(row["sha256"]) == 64 for row in workbooks)
    assert all(row["formulas_present"] is False for row in workbooks)

    by_file = {row["file"]: row for row in workbooks}
    assert by_file["Fig.2-XRD data.xlsx"]["actual_nonempty_range"] == "A1:L3503"
    assert by_file["Fig.3a-dc magnetization Ti7Fe52Si41-ver2.xlsx"]["actual_nonempty_range"] == "A1:B353"
    assert by_file["Fig.3c-dc magnetization Zr7Fe52Si41-ver2.xlsx"]["actual_nonempty_range"] == "A1:C667"
    assert by_file["Fig.3e-dc magnetization Hf7Fe52Si41-ver2.xlsx"]["actual_nonempty_range"] == "A1:C685"


def test_scientific_boundary_stays_fail_closed() -> None:
    data = _load()
    findings = data["scientific_findings"]
    assert findings["xlsx_access_and_schema"] == "Supported"
    assert findings["exact_cross_modality_specimen_identity"] == "Inconclusive"
    assert findings["safe_cross_modality_identity_level"] == "nominal_composition_and_preparation_batch_family"
    assert findings["absolute_xrd_intensity_cross_composition_comparability"] == "Unsupported"
    assert findings["xrd_peak_position_descriptive_use"] == "Diagnostic"
    assert findings["magnetic_property_descriptive_use"] == "Diagnostic"
    assert findings["predictive_use"] == "Unsupported"
    assert findings["causal_use"] == "Unsupported"
    assert findings["engineering_decision_use"] == "Unsupported"


def test_measurement_provenance_preserves_instrument_split_and_xrd_offset() -> None:
    data = _load()
    context = data["measurement_context"]
    assert context["xrd"]["publication_plot_offset"] == (
        "origin_of_each_pattern_shifted_by_integer_value_for_clarity"
    )
    dc = context["dc_magnetization"]
    assert dc["field_oe"] == 100
    assert dc["low_temperature_instrument"] == "Quantum Design VersaLab VSM"
    assert dc["high_temperature_instrument"] == "Tamakawa TM-VSM33483-HGC"
    assert dc["high_temperature_data_present_for_uploaded_subset"] == [
        "Zr7Fe52Si41",
        "Hf7Fe52Si41",
    ]


def test_next_action_does_not_authorize_modeling() -> None:
    data = _load()
    assert data["next_action"] == (
        "freeze_a_descriptive_xrd_handoff_contract_before_feature_extraction_and_"
        "consume_it_in_mda_with_nominal_composition_level_identity"
    )
