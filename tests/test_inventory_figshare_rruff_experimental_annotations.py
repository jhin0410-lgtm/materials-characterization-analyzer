from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import inventory_figshare_rruff_experimental_annotations as inventory


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "case_studies" / "figshare_rruff_experimental_annotation_inventory" / "evidence_contract.json"


def _contract_payload() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _record(rruff_id: str, peaks: list[float]) -> dict:
    return {
        "type": ["oxide"],
        "formula": f"Mineral {rruff_id}",
        "RRUFF_id": rruff_id,
        "noise": 0.2,
        "start": 100.0,
        "wavenumbers": peaks,
        "intensities": [float(index + 1) for index in range(len(peaks))],
        "mp_id": "mp-1",
    }


def test_contract_authorizes_only_annotation_inventory_operations() -> None:
    config = inventory._validate_contract(_contract_payload())
    operations = config["authorized_operations"]

    assert operations["download_exact_experimental_json"] is True
    assert operations["verify_size_and_md5_before_parse"] is True
    assert operations["parse_json_structure"] is True
    assert operations["inventory_rruff_ids"] is True
    assert operations["inventory_peak_counts_and_wavenumber_ranges"] is True
    assert operations["retain_raw_experimental_json"] is False
    assert operations["download_rruff_spectrum_files"] is False
    assert operations["download_any_other_figshare_file"] is False
    assert operations["use_materials_project_matches_for_selection"] is False
    assert operations["use_computed_raman_modes_for_selection"] is False
    assert operations["run_mca_raman_analyzer"] is False
    assert operations["tune_mca_raman_parameters"] is False
    assert operations["select_final_validation_subset"] is False
    assert operations["claim_authoritative_peak_truth"] is False
    assert operations["claim_external_validation"] is False


def test_upstream_metadata_pins_cc_by_and_exact_experimental_file() -> None:
    config = inventory._validate_contract(_contract_payload())
    evidence = inventory._validate_upstream_evidence(config)

    assert evidence["dataset_license"] == "CC BY 4.0"
    assert evidence["target_file_id"] == 13752833
    assert evidence["target_file_md5"] == "5397f81312a454f6255b65a1d6d9529e"
    assert len(evidence["metadata_snapshot_sha256"]) == 64
    assert len(evidence["publication_evidence_sha256"]) == 64


def test_recursive_record_inventory_is_independent_of_container_layout() -> None:
    payload = {
        "outer": {
            "a": _record("R000001", [100.0, 200.0]),
            "nested": [_record("R000002", [150.0, 250.0, 350.0])],
        }
    }
    records = inventory._find_rruff_records(payload)
    summary = inventory._summarize_records(records)

    assert summary["record_count"] == 2
    assert summary["unique_rruff_id_count"] == 2
    assert summary["rruff_ids"] == ["R000001", "R000002"]
    assert summary["duplicate_rruff_id_count"] == 0
    assert summary["peak_count"]["total_peaks"] == 5
    assert summary["peak_count"]["min"] == 2
    assert summary["peak_count"]["max"] == 3
    assert summary["wavenumber_cm_1"] == {"min": 100.0, "max": 350.0}
    assert all(value == 0 for value in summary["required_field_missing_counts"].values())
    assert summary["invalid_record_count"] == 0


def test_inventory_reports_duplicates_missing_fields_and_length_mismatch() -> None:
    first = _record("R000001", [100.0, 200.0])
    second = _record("R000001", [120.0, 220.0])
    second.pop("mp_id")
    second["intensities"] = [1.0]
    summary = inventory._summarize_records([("$.a", first), ("$.b", second)])

    assert summary["duplicate_rruff_ids"] == ["R000001"]
    assert summary["duplicate_rruff_id_count"] == 1
    assert summary["required_field_missing_counts"]["mp_id"] == 1
    assert summary["peak_intensity_length_mismatch_count"] == 1


def test_run_inventory_retains_no_raw_payload_and_never_authorizes_analyzer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"records": [_record("R000001", [100.0, 200.0])]}).encode("utf-8")
    md5 = hashlib.md5(payload).hexdigest()
    config = _contract_payload()
    config["target_file"]["expected_bytes"] = len(payload)
    config["target_file"]["maximum_response_bytes"] = len(payload)
    config["target_file"]["expected_md5"] = md5
    config_path = tmp_path / "contract.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(
        inventory,
        "_validate_upstream_evidence",
        lambda _: {
            "metadata_snapshot_sha256": "a" * 64,
            "publication_evidence_sha256": "b" * 64,
            "dataset_license": "CC BY 4.0",
            "target_file_id": 13752833,
            "target_file_md5": md5,
        },
    )
    monkeypatch.setattr(
        inventory,
        "_download_exact_file",
        lambda target: (
            payload,
            {
                "status": 200,
                "final_url": target["download_url"],
                "content_type": "application/json",
                "bytes": len(payload),
                "md5": md5,
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        ),
    )
    monkeypatch.setattr(inventory, "_validate_contract", lambda value: value)

    output = tmp_path / "inventory.json"
    result = inventory.run_inventory(config_path=config_path, output_path=output)

    assert result["source_file"]["raw_payload_retained"] is False
    assert result["annotation_inventory"]["record_count"] == 1
    assert result["evidence_assessment"]["published_peak_annotation_inventory"] == "Diagnostic"
    assert result["evidence_assessment"]["independent_authoritative_peak_position_truth"] == "Inconclusive"
    readiness = result["readiness"]
    assert readiness["rruff_spectrum_download_authorized"] is False
    assert readiness["final_validation_subset_selection_authorized"] is False
    assert readiness["raman_analyzer_execution_authorized"] is False
    assert readiness["parameter_tuning_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert output.is_file()


def test_no_rruff_records_fails_closed() -> None:
    with pytest.raises(inventory.FigshareRruffAnnotationInventoryError, match="no RRUFF_id"):
        inventory._summarize_records([])
