from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_figshare_rruff_peak_reference_readiness as audit


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "case_studies" / "figshare_rruff_peak_reference_readiness" / "case_config.json"


def _config_payload() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _metadata_payload(*, license_name: str = "CC BY 4.0") -> bytes:
    payload = {
        "id": 7427393,
        "title": "High-throughput Computation and Evaluation of Raman Spectra",
        "doi": "10.6084/m9.figshare.7427393.v2",
        "version": 2,
        "published_date": "2018-12-05T20:08:00Z",
        "modified_date": "2018-12-05T20:08:00Z",
        "defined_type": 3,
        "defined_type_name": "dataset",
        "is_active": True,
        "license": {
            "id": 1,
            "name": license_name,
            "url": "https://creativecommons.org/licenses/by/4.0/",
        },
        "files": [
            {
                "id": 14000001,
                "name": "ExperimentalData.json",
                "size": 12345,
                "is_link_only": False,
                "download_url": "https://ndownloader.figshare.com/files/14000001",
                "supplied_md5": "0123456789abcdef0123456789abcdef",
                "computed_md5": "0123456789abcdef0123456789abcdef",
            },
            {
                "id": 14000002,
                "name": "ComputationalData.json",
                "size": 67890,
                "is_link_only": False,
                "download_url": "https://ndownloader.figshare.com/files/14000002",
                "supplied_md5": "fedcba9876543210fedcba9876543210",
                "computed_md5": "fedcba9876543210fedcba9876543210",
            },
        ],
    }
    return json.dumps(payload).encode("utf-8")


def test_contract_authorizes_metadata_only() -> None:
    config = audit._validate_config(_config_payload())
    operations = config["authorized_operations"]

    assert operations["request_exact_figshare_article_metadata"] is True
    assert operations["record_license_metadata"] is True
    assert operations["record_file_inventory_metadata"] is True
    assert operations["record_file_hash_metadata"] is True
    assert operations["download_any_dataset_file"] is False
    assert operations["read_experimental_json_payload"] is False
    assert operations["read_rruff_spectrum_payload"] is False
    assert operations["run_raman_analyzer"] is False
    assert operations["tune_raman_parameters"] is False
    assert operations["claim_independent_peak_ground_truth"] is False
    assert operations["claim_external_validation"] is False


def test_publication_evidence_keeps_peak_truth_inconclusive() -> None:
    _, evidence = audit._validate_publication_evidence()
    unresolved = evidence["unresolved_reference_provenance"]

    assert unresolved[
        "exact_algorithm_or_manual_protocol_used_to_extract_experimental_peak_locations"
    ] == "Inconclusive"
    assert unresolved["suitability_as_authoritative_physical_peak_truth"] == "Inconclusive"
    assert evidence["scientific_interpretation"]["current_evidence_level"] == "Diagnostic"


def test_metadata_parser_records_license_files_and_experimental_candidate() -> None:
    config = audit._validate_config(_config_payload())
    result = audit._parse_metadata(_metadata_payload(), config["source"])

    assert result["article"]["id"] == 7427393
    assert result["article"]["version"] == 2
    assert result["license"]["metadata_present"] is True
    assert result["license"]["name"] == "CC BY 4.0"
    assert len(result["files"]) == 2
    assert result["experimental_json_candidates"][0]["name"] == "ExperimentalData.json"
    assert result["experimental_json_candidates"][0]["supplied_md5"] is not None


def test_metadata_parser_rejects_wrong_article_or_version() -> None:
    config = audit._validate_config(_config_payload())
    payload = json.loads(_metadata_payload().decode("utf-8"))
    payload["version"] = 1

    with pytest.raises(audit.FigshareRruffReadinessError, match="current version"):
        audit._parse_metadata(json.dumps(payload).encode("utf-8"), config["source"])


def test_license_disposition_does_not_infer_missing_metadata() -> None:
    assert audit._license_disposition({"metadata_present": False}) == "Inconclusive"
    assert audit._license_disposition(
        {"metadata_present": True, "name": "CC BY 4.0"}
    ) == "Supported"
    assert audit._license_disposition(
        {"metadata_present": True, "name": "Custom restricted license"}
    ) == "Diagnostic"


def test_run_audit_never_downloads_dataset_files_or_promotes_peak_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _metadata_payload()
    monkeypatch.setattr(
        audit,
        "_download_metadata",
        lambda url, maximum_bytes, timeout_seconds, allowed_hosts: (
            payload,
            {
                "status": 200,
                "final_url": "https://api.figshare.com/v2/articles/7427393",
                "content_type": "application/json",
            },
        ),
    )

    output = tmp_path / "readiness.json"
    result = audit.run_audit(config_path=CONFIG, output_path=output)

    assert result["execution_status"] == "figshare_rruff_peak_reference_metadata_audit_completed"
    assert result["license"]["reuse_metadata_disposition"] == "Supported"
    assert result["file_inventory_summary"]["experimental_json_candidate_count"] == 1
    assert result["file_inventory_summary"]["dataset_file_payload_bytes_read"] == 0
    evidence = result["evidence_assessment"]
    assert evidence["experimental_peak_annotation_provenance"] == "Diagnostic"
    assert evidence["independent_authoritative_peak_position_truth"] == "Inconclusive"
    readiness = result["readiness"]
    assert readiness["dataset_file_download_authorized"] is False
    assert readiness["experimental_json_download_authorized"] is False
    assert readiness["raman_analyzer_execution_authorized"] is False
    assert readiness["parameter_tuning_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert output.is_file()


def test_paper_license_cannot_substitute_for_missing_figshare_license(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_obj = json.loads(_metadata_payload().decode("utf-8"))
    payload_obj["license"] = None
    payload = json.dumps(payload_obj).encode("utf-8")
    monkeypatch.setattr(
        audit,
        "_download_metadata",
        lambda url, maximum_bytes, timeout_seconds, allowed_hosts: (
            payload,
            {
                "status": 200,
                "final_url": "https://api.figshare.com/v2/articles/7427393",
                "content_type": "application/json",
            },
        ),
    )

    result = audit.run_audit(
        config_path=CONFIG,
        output_path=tmp_path / "readiness.json",
    )
    assert result["license"]["reuse_metadata_disposition"] == "Inconclusive"
    assert result["license"]["paper_license_inferred_for_dataset"] is False
    assert result["readiness"]["dataset_file_download_authorized"] is False


def test_output_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _metadata_payload()
    monkeypatch.setattr(
        audit,
        "_download_metadata",
        lambda url, maximum_bytes, timeout_seconds, allowed_hosts: (
            payload,
            {
                "status": 200,
                "final_url": "https://api.figshare.com/v2/articles/7427393",
                "content_type": "application/json",
            },
        ),
    )
    output = tmp_path / "readiness.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(audit.FigshareRruffReadinessError, match="overwrite"):
        audit.run_audit(config_path=CONFIG, output_path=output)
