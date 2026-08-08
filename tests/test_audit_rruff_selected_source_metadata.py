from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_rruff_selected_source_metadata as audit


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "case_studies" / "rruff_selected_source_metadata_readiness" / "evidence_contract.json"


def _contract_payload() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _page(rruff_id: str, *, processed: bool = True, raw: bool = True) -> bytes:
    downloads = []
    if processed:
        downloads.append("Raman Data (Processed)")
    if raw:
        downloads.append("Raman Data (RAW)")
    return f"""<!doctype html>
    <html><body>
      <h1>Example mineral {rruff_id}</h1>
      <section>RAMAN SPECTRUM Sample Description: Unoriented sample {' '.join(downloads)}</section>
      <section>BROAD SCAN WITH SPECTRAL ARTIFACTS RRUFF ID: {rruff_id}
      Sample Description: Unoriented sample Instrument settings: Thermo Almega XR 532nm @ 100% of 150mW
      {' '.join(downloads)}</section>
      <script>Raman Data (Processed) 785nm should not count</script>
    </body></html>""".encode("utf-8")


def _fetched(rruff_id: str, payload: bytes) -> dict:
    return {
        "request_url": f"https://rruff.info/{rruff_id}",
        "status": 200,
        "final_url": f"https://rruff.info/{rruff_id}",
        "content_type": "text/html",
        "payload": payload,
        "prefix_limit_bytes": 524288,
        "reported_content_length": "900000",
        "response_prefix_only": True,
        "network_error": None,
    }


def test_contract_pins_exact_target_blind_selected_ids_and_prefix_limit() -> None:
    config = audit._validate_contract(_contract_payload())
    assert config["expected_selected_ids"] == [
        "R060247",
        "R040073",
        "R110214",
        "R070417",
        "R040078",
        "R070307",
        "R040006",
        "X050046",
        "R060959",
        "R040040",
    ]
    assert config["page_access"]["maximum_prefix_bytes_per_id"] == 524288
    operations = config["authorized_operations"]
    assert operations["request_exact_selected_rruff_record_pages"] is True
    assert operations["read_bounded_html_prefix_only"] is True
    assert operations["read_record_page_beyond_prefix_limit"] is False
    assert operations["follow_raman_data_download_links"] is False
    assert operations["download_processed_spectrum_payload"] is False
    assert operations["download_raw_spectrum_payload"] is False
    assert operations["infer_exact_annotation_to_spectrum_binding"] is False
    assert operations["select_replacement_ids"] is False
    assert operations["run_mca_raman"] is False


def test_upstream_selection_remains_target_blind_and_rights_remain_inconclusive() -> None:
    config = audit._validate_contract(_contract_payload())
    upstream = audit._validate_upstream(config)

    assert upstream["selected_id_count"] == 10
    assert upstream["reuse_rights_status"] == "Inconclusive"
    assert len(upstream["selection_snapshot_sha256"]) == 64
    assert len(upstream["rruff_source_claims_sha256"]) == 64


def test_visible_prefix_inventory_records_discoverability_without_binding() -> None:
    result = audit._inspect_page("R060247", _fetched("R060247", _page("R060247")))

    assert result["response_prefix_only"] is True
    assert result["full_page_read"] is False
    assert result["reported_content_length"] == "900000"
    assert result["response_prefix_bytes"] == len(_page("R060247"))
    assert len(result["response_prefix_sha256"]) == 64
    assert result["record_identity_present"] is True
    assert result["raman_section_present"] is True
    assert result["broad_scan_section_present"] is True
    assert result["processed_download_label_count"] == 2
    assert result["raw_download_label_count"] == 2
    assert result["wavelengths_nm"] == [532]
    assert result["unoriented_text_present"] is True
    assert result["raman_source_discoverability"] == "Supported"
    assert result["acquisition_metadata_readiness"] == "Diagnostic"
    assert result["exact_annotation_to_spectrum_binding"] == "Inconclusive"
    assert result["html_retained"] is False


def test_script_and_style_text_do_not_create_false_spectrum_metadata() -> None:
    text, parts = audit._visible_text(
        b"<html><body>RRUFF ID R060247<script>Raman Data (Processed) 785nm</script></body></html>"
    )
    assert "Raman Data (Processed)" not in text
    assert "785nm" not in text
    assert all("Raman Data (Processed)" not in part for part in parts)


def test_missing_page_is_structured_inconclusive_not_spectrum_fallback() -> None:
    fetched = {
        "request_url": "https://rruff.info/R060247",
        "status": 404,
        "final_url": "https://rruff.info/R060247",
        "content_type": None,
        "payload": b"",
        "prefix_limit_bytes": 524288,
        "reported_content_length": None,
        "response_prefix_only": True,
        "network_error": "HTTPError:404",
    }
    result = audit._inspect_page("R060247", fetched)

    assert result["response_prefix_bytes"] == 0
    assert result["full_page_read"] is False
    assert result["raman_source_discoverability"] == "Inconclusive"
    assert result["exact_annotation_to_spectrum_binding"] == "Inconclusive"


def test_run_audit_records_only_bounded_prefixes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _page("R060247")
    monkeypatch.setattr(
        audit,
        "_fetch_page",
        lambda rruff_id, access: _fetched(
            rruff_id,
            payload.replace(b"R060247", rruff_id.encode("ascii")),
        ),
    )
    output = tmp_path / "audit.json"
    result = audit.run_audit(config_path=CONTRACT, output_path=output)

    assert result["summary"]["selected_id_count"] == 10
    assert result["summary"]["full_record_pages_read"] == 0
    assert result["summary"]["spectrum_payload_bytes_read"] == 0
    assert result["summary"]["record_page_prefix_bytes_read_total"] > 0
    assert all(record["response_prefix_only"] is True for record in result["records"])
    assert all(record["full_page_read"] is False for record in result["records"])
    assert result["readiness"]["rruff_spectrum_download_authorized"] is False


def test_output_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _page("R060247")
    monkeypatch.setattr(
        audit,
        "_fetch_page",
        lambda rruff_id, access: _fetched(
            rruff_id,
            payload.replace(b"R060247", rruff_id.encode("ascii")),
        ),
    )
    output = tmp_path / "audit.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(audit.RruffSelectedSourceMetadataError, match="overwrite"):
        audit.run_audit(config_path=CONTRACT, output_path=output)
