from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import assess_zenodo_bir_300kev_saed_calibration_readiness as assess


def test_repository_contract_is_fail_closed() -> None:
    path = Path(
        "case_studies/zenodo_bir_300kev_saed_calibration_readiness/evidence_contract.json"
    )
    contract = assess.validate_contract(json.loads(path.read_text(encoding="utf-8")))
    assert contract["current_evidence_state"]["quantitative_saed_indexing_readiness"] == "Unsupported"
    assert contract["current_evidence_state"]["pattern_center"] == "Inconclusive"
    assert contract["current_evidence_state"]["reciprocal_scale"] == "Inconclusive"
    assert contract["next_evidence_requirement"]["source_bytes_required_now"] is False
    assert contract["decision_rules"][
        "do_not_read_frame_or_pixel_payload_when_published_methods_already_answer_detector_or_diffraction_mode"
    ] is True


def test_repository_snapshots_produce_blocked_calibration_closeout(tmp_path: Path) -> None:
    result = assess.assess(
        contract_path=Path(
            "case_studies/zenodo_bir_300kev_saed_calibration_readiness/evidence_contract.json"
        ),
        output_path=tmp_path / "assessment.json",
    )
    assert result["execution_status"] == "calibration_readiness_assessed"
    assert result["supported_context"]["tvips_internal_header_structure"] is True
    assert result["supported_context"]["published_300kv_microscope_detector_diffraction_mode"] is True
    assert result["quantitative_saed_indexing_ready"] is False
    assert result["source_bytes_required_now"] is False
    assert "pattern_center" in result["blocking_evidence"]
    assert "reciprocal_scale" in result["blocking_evidence"]
    assert (tmp_path / "assessment.json").is_file()


def test_contract_rejects_premature_calibration_promotion() -> None:
    path = Path(
        "case_studies/zenodo_bir_300kev_saed_calibration_readiness/evidence_contract.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["current_evidence_state"]["pattern_center"] = "Supported"
    with pytest.raises(assess.Bir300CalibrationReadinessError, match="prematurely promoted"):
        assess.validate_contract(payload)


def test_contract_rejects_new_source_bytes_as_current_requirement() -> None:
    path = Path(
        "case_studies/zenodo_bir_300kev_saed_calibration_readiness/evidence_contract.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["next_evidence_requirement"]["source_bytes_required_now"] = True
    with pytest.raises(assess.Bir300CalibrationReadinessError, match="must not be required"):
        assess.validate_contract(payload)
