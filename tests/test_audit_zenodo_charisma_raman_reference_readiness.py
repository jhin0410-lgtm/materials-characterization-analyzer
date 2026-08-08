from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_charisma_raman_reference_readiness as audit


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "case_studies" / "charisma_raman_reference_readiness" / "case_config.json"


def _config_payload() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _record(*, license_id: str | None = "cc-by-4.0") -> dict:
    metadata = {
        "title": "An analysis of peak fitting in reference material spectra for calibration of Raman spectroscopy instruments",
        "resource_type": {"id": "other", "title": {"en": "Other"}},
        "publication_date": "2024-08-28",
        "version": "v1",
    }
    if license_id is not None:
        metadata["rights"] = [
            {
                "id": license_id,
                "title": {"en": "Creative Commons Attribution 4.0 International"},
                "link": "https://creativecommons.org/licenses/by/4.0/legalcode",
            }
        ]
    return {
        "id": 13387413,
        "status": "published",
        "created": "2024-10-14T00:00:00+00:00",
        "updated": "2024-10-14T00:00:00+00:00",
        "metadata": metadata,
        "files": [
            {
                "id": "fixture-file-id",
                "key": "peak_fitting_spectra.nxs",
                "size": 9000000,
                "checksum": "md5:88485671e56662b00aaad9303dc653d6",
                "links": {
                    "content": "https://zenodo.org/api/records/13387413/files/peak_fitting_spectra.nxs/content"
                },
            }
        ],
    }


def test_contract_keeps_nexus_and_analyzer_actions_disabled() -> None:
    config = audit._validate_config(_config_payload())
    boundary = config["scientific_boundary"]

    assert config["source"]["expected_resource_type"] == "other"
    assert boundary["metadata_api_request_authorized"] is True
    assert boundary["record_license_and_version_metadata_authorized"] is True
    assert boundary["record_file_identity_and_checksum_metadata_authorized"] is True
    assert boundary["download_nexus_file_authorized"] is False
    assert boundary["inspect_nexus_structure_authorized"] is False
    assert boundary["read_spectrum_arrays_authorized"] is False
    assert boundary["run_mca_raman_authorized"] is False
    assert boundary["tune_mca_raman_parameters_authorized"] is False
    assert boundary["select_validation_subset_authorized"] is False
    assert boundary["select_matching_tolerance_authorized"] is False
    assert boundary["claim_external_validation_authorized"] is False


def test_publication_evidence_preserves_narrow_raman_question() -> None:
    path = audit._resolve_repo_path(_config_payload()["publication_evidence"])
    evidence = audit._validate_publication_evidence(path)

    assert evidence["publication"]["doi"] == "10.1177/00037028251330654"
    assert evidence["publication"]["zenodo_dataset_doi"] == "10.5281/zenodo.13387413"
    assert evidence["supported_publication_facts"]["ten_raman_instruments_reported"] is True
    assert evidence["supported_publication_facts"]["silicon_reference_material_used"] is True
    assert evidence["current_evidence_assessment"]["exact_nexus_internal_structure"] == "Inconclusive"
    assert evidence["current_evidence_assessment"]["exact_reference_peak_truth_available_in_dataset"] == "Inconclusive"


def test_record_validation_pins_nexus_identity_and_license_metadata() -> None:
    config = audit._validate_config(_config_payload())
    verified = audit._validate_record(config, _record())

    assert verified["resource_type"] == "other"
    assert verified["version_api"] == "v1"
    assert len(verified["inventory"]) == 1
    nexus = verified["inventory"][0]
    assert nexus["key"] == "peak_fitting_spectra.nxs"
    assert nexus["bytes"] == 9000000
    assert nexus["md5"] == "88485671e56662b00aaad9303dc653d6"
    assert verified["license_records"][0]["id"] == "cc-by-4.0"
    assert audit._license_disposition(verified["license_records"]) == "Supported"


def test_missing_zenodo_license_remains_inconclusive() -> None:
    config = audit._validate_config(_config_payload())
    verified = audit._validate_record(config, _record(license_id=None))

    assert verified["license_records"] == []
    assert audit._license_disposition(verified["license_records"]) == "Inconclusive"


def test_wrong_file_checksum_fails_closed() -> None:
    config = audit._validate_config(_config_payload())
    record = _record()
    record["files"][0]["checksum"] = "md5:00000000000000000000000000000000"

    with pytest.raises(audit.CharismaRamanReadinessError, match="file inventory/MD5 drifted"):
        audit._validate_record(config, record)


def test_run_audit_never_authorizes_nexus_or_mca_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit,
        "_fetch_record",
        lambda url: (
            _record(),
            {
                "status": 200,
                "final_url": "https://zenodo.org/api/records/13387413",
                "content_type": "application/json",
                "response_bytes": 1234,
                "response_sha256": "a" * 64,
            },
        ),
    )
    output = tmp_path / "readiness.json"
    result = audit.run_audit(config_path=CONFIG, output_path=output)

    assert result["execution_status"] == "charisma_raman_reference_metadata_audit_completed"
    assert result["source"]["resource_type"] == "other"
    assert result["source"]["license_metadata_disposition"] == "Supported"
    assert result["nexus_candidate"]["payload_bytes_read"] == 0
    assert result["nexus_candidate"]["downloaded"] is False
    assert result["nexus_candidate"]["structure_inspected"] is False
    evidence = result["evidence_assessment"]
    assert evidence["interlaboratory_reference_material_context"] == "Supported"
    assert evidence["nexus_internal_structure"] == "Inconclusive"
    assert evidence["exact_reference_peak_truth_in_nexus"] == "Inconclusive"
    readiness = result["readiness"]
    assert readiness["nexus_download_authorized"] is False
    assert readiness["nexus_structure_inspection_authorized"] is False
    assert readiness["spectrum_array_access_authorized"] is False
    assert readiness["raman_analyzer_execution_authorized"] is False
    assert readiness["parameter_tuning_authorized"] is False
    assert readiness["matching_tolerance_selection_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert output.is_file()


def test_output_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audit,
        "_fetch_record",
        lambda url: (
            _record(),
            {
                "status": 200,
                "final_url": "https://zenodo.org/api/records/13387413",
                "content_type": "application/json",
                "response_bytes": 1234,
                "response_sha256": "a" * 64,
            },
        ),
    )
    output = tmp_path / "readiness.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(audit.CharismaRamanReadinessError, match="overwrite"):
        audit.run_audit(config_path=CONFIG, output_path=output)
