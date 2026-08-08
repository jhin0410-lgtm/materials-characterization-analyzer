from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_rruff_raman_reference_readiness as audit


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "case_studies" / "rruff_raman_reference_readiness" / "case_config.json"


def _config_payload() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _index_html(*, include_candidate: bool = True) -> bytes:
    candidate = (
        '<a href="excellent_unoriented.zip">excellent_unoriented.zip</a> 2026-06-23 19:54 229M'
        if include_candidate
        else '<a href="fair_unoriented.zip">fair_unoriented.zip</a> 2026-06-23 19:54 59M'
    )
    return f"""<!doctype html>
    <html><body>
    <h1>Index of /zipped_data_files/raman</h1>
    {candidate}
    <script>excellent_unoriented.zip should not count from script text</script>
    </body></html>""".encode("utf-8")


def test_contract_keeps_archive_and_analyzer_actions_disabled() -> None:
    config = audit._validate_config(_config_payload())
    operations = config["authorized_operations"]

    assert operations["request_official_raman_index_html"] is True
    assert operations["parse_candidate_link_from_index"] is True
    assert operations["record_index_hash_and_listing_metadata"] is True
    assert operations["download_candidate_archive"] is False
    assert operations["read_candidate_archive_payload"] is False
    assert operations["extract_spectrum_files"] is False
    assert operations["run_raman_analyzer"] is False
    assert operations["tune_raman_parameters"] is False
    assert operations["fit_or_train_model"] is False
    assert operations["claim_external_validation"] is False


def test_source_claims_preserve_rights_version_and_peak_truth_gaps() -> None:
    config = audit._validate_config(_config_payload())
    snapshot = audit._load_json(audit._resolve_repo_path(config["source_claims_snapshot"]))
    claims = audit._validate_source_claims(snapshot)

    assert claims["rights_status"] == "Inconclusive"
    assert claims["immutable_archive_identity_status"] == "Inconclusive"
    assert claims["independent_peak_truth_status"] == "Inconclusive"
    assert claims["reference_context_status"] == "Diagnostic"


def test_index_parser_finds_only_visible_candidate_link_and_metadata() -> None:
    result = audit._inspect_index(_index_html(), "excellent_unoriented.zip")

    assert result["listed"] is True
    assert result["link"] == {
        "href": "excellent_unoriented.zip",
        "text": "excellent_unoriented.zip",
    }
    assert result["observed_last_modified_text"] == "2026-06-23 19:54"
    assert result["observed_size_text"] == "229M"


def test_index_parser_marks_missing_candidate_unsupported() -> None:
    result = audit._inspect_index(
        _index_html(include_candidate=False),
        "excellent_unoriented.zip",
    )

    assert result["listed"] is False
    assert result["link"] is None


def test_run_audit_never_authorizes_download_or_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _index_html()
    monkeypatch.setattr(
        audit,
        "_download_index",
        lambda url, maximum_bytes, timeout_seconds, allowed_hosts: (
            payload,
            {
                "status": 200,
                "final_url": "https://www.rruff.net/zipped_data_files/raman/",
                "content_type": "text/html",
                "last_modified": None,
                "etag": None,
            },
        ),
    )

    output = tmp_path / "rruff_readiness.json"
    result = audit.run_audit(config_path=CONFIG, output_path=output)

    assert result["execution_status"] == "rruff_raman_reference_readiness_audit_completed"
    assert result["candidate_archive"]["listing_status"] == "Supported"
    assert result["candidate_archive"]["payload_bytes_read"] == 0
    assert result["candidate_archive"]["archive_downloaded"] is False
    assert result["candidate_archive"]["checksum_verified"] is False
    evidence = result["evidence_assessment"]
    assert evidence["explicit_reuse_rights_for_automated_acquisition_and_redistribution"] == "Inconclusive"
    assert evidence["independent_peak_position_truth"] == "Inconclusive"
    readiness = result["readiness"]
    assert readiness["automatic_acquisition_authorized"] is False
    assert readiness["candidate_archive_download_authorized"] is False
    assert readiness["raman_analyzer_execution_authorized"] is False
    assert readiness["parameter_tuning_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert output.is_file()


def test_missing_candidate_is_structured_unsupported_not_download_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _index_html(include_candidate=False)
    monkeypatch.setattr(
        audit,
        "_download_index",
        lambda url, maximum_bytes, timeout_seconds, allowed_hosts: (
            payload,
            {
                "status": 200,
                "final_url": "https://www.rruff.net/zipped_data_files/raman/",
                "content_type": "text/html",
                "last_modified": None,
                "etag": None,
            },
        ),
    )

    result = audit.run_audit(
        config_path=CONFIG,
        output_path=tmp_path / "rruff_readiness.json",
    )
    assert result["candidate_archive"]["listing_status"] == "Unsupported"
    assert result["candidate_archive"]["payload_bytes_read"] == 0
    assert result["readiness"]["automatic_acquisition_authorized"] is False


def test_untrusted_index_host_is_rejected(tmp_path: Path) -> None:
    config = _config_payload()
    config["source_system"]["official_index_url"] = "https://example.com/zipped_data_files/raman/"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(audit.RruffRamanReadinessError, match="index URL drifted"):
        audit._validate_config(audit._load_json(path))


def test_output_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _index_html()
    monkeypatch.setattr(
        audit,
        "_download_index",
        lambda url, maximum_bytes, timeout_seconds, allowed_hosts: (
            payload,
            {
                "status": 200,
                "final_url": "https://www.rruff.net/zipped_data_files/raman/",
                "content_type": "text/html",
                "last_modified": None,
                "etag": None,
            },
        ),
    )
    output = tmp_path / "rruff_readiness.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(audit.RruffRamanReadinessError, match="overwrite"):
        audit.run_audit(config_path=CONFIG, output_path=output)
