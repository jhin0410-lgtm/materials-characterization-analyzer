from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.audit_fhi_co3o4_tem_saed import (
    FhiCo3O4AuditError,
    inspect_zip,
    load_config,
    parse_record_html,
    verify_record,
)


LIMITS = {
    "max_members_per_archive": 20,
    "max_total_uncompressed_bytes_per_archive": 1_000_000,
    "max_single_member_bytes": 500_000,
    "max_compression_ratio": 500,
}


def _config() -> dict[str, object]:
    return {
        "case_id": "fhi_co3o4_tem_saed_source_audit",
        "audit_date": "2026-08-05",
        "source": {
            "repository": "Fritz Haber Institute AC/CATLAB Archive",
            "record_id": "D63268",
            "record_url": "https://ac.archive.fhi.mpg.de/D63268",
            "expected_title": "Data to: Local Solid-State Processes Adjust the Selectivity in Catalytic Oxidation Reactions on Cobalt Oxides",
            "expected_document_type": "RAW DATA",
            "expected_sample_number": "S32564",
            "required_methods": ["OTEM", "SAED"],
            "target_files": [
                {
                    "name": "TEM.zip",
                    "declared_role": "General TEM characterization",
                    "declared_size": "5.6 MB",
                    "max_download_bytes": 20_000_000,
                },
                {
                    "name": "OTEM_2.zip",
                    "declared_role": "HRTEM and SAED",
                    "declared_size": "175.6 MB",
                    "max_download_bytes": 400_000_000,
                },
            ],
        },
        "limits": LIMITS,
        "scientific_boundary": {
            "record_is_exact_material": True,
            "repository_checksum_is_publicly_available": False,
        },
    }


def test_record_parser_resolves_pinned_download_links() -> None:
    html = """
    <html><body>
    Open Access D63268 RAW DATA S32564 OTEM SAED
    Data to: Local Solid-State Processes Adjust the Selectivity in Catalytic Oxidation Reactions on Cobalt Oxides
    <a href="/send/tem-token">TEM.zip</a>
    <a href="/send/otem-token">OTEM_2.zip</a>
    </body></html>
    """
    text, links = parse_record_html(html, "https://ac.archive.fhi.mpg.de/D63268")
    assert "D63268" in text
    assert links == {
        "TEM.zip": "https://ac.archive.fhi.mpg.de/send/tem-token",
        "OTEM_2.zip": "https://ac.archive.fhi.mpg.de/send/otem-token",
    }
    resolved, record = verify_record(_config(), html)
    assert resolved == links
    assert record["sample_number"] == "S32564"
    assert record["open_access_marker_confirmed"] is True


def test_record_verification_fails_when_target_link_leaves_host() -> None:
    html = """
    Open Access D63268 RAW DATA S32564 OTEM SAED
    Data to: Local Solid-State Processes Adjust the Selectivity in Catalytic Oxidation Reactions on Cobalt Oxides
    <a href="https://example.org/send/tem">TEM.zip</a>
    <a href="/send/otem">OTEM_2.zip</a>
    """
    with pytest.raises(FhiCo3O4AuditError, match="leaves pinned host"):
        verify_record(_config(), html)


def test_zip_inventory_hashes_native_and_saed_members(tmp_path: Path) -> None:
    archive = tmp_path / "OTEM_2.zip"
    dm4 = b"native-microscopy-placeholder"
    tif = b"lossless-raster-placeholder"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("HRTEM/sample_01.dm4", dm4)
        handle.writestr("SAED/pattern_01.tif", tif)
        handle.writestr("metadata/readme.txt", b"instrument metadata")

    rows, stats = inspect_zip(archive, archive.name, LIMITS)
    assert stats["member_count"] == 3
    assert stats["member_hashing_complete"] is True
    assert stats["crc_verification_complete"] is True
    by_path = {row["member_path"]: row for row in rows}
    assert by_path["HRTEM/sample_01.dm4"]["representation_class"] == (
        "native_microscopy_container"
    )
    assert by_path["HRTEM/sample_01.dm4"]["sha256"] == hashlib.sha256(dm4).hexdigest()
    assert "hrtem_name_cue" in by_path["HRTEM/sample_01.dm4"]["role_cues"]
    assert "saed_or_diffraction_name_cue" in by_path["SAED/pattern_01.tif"]["role_cues"]


def test_zip_inventory_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.dm4", b"unsafe")
    with pytest.raises(FhiCo3O4AuditError, match="unsafe archive member path"):
        inspect_zip(archive, archive.name, LIMITS)


def test_live_config_and_trusted_snapshot_remain_fail_closed() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(
        root / "case_studies/fhi_co3o4_tem_saed_source_audit/case_config.json"
    )
    assert config["source"]["record_id"] == "D63268"
    assert [item["name"] for item in config["source"]["target_files"]] == [
        "TEM.zip",
        "OTEM_2.zip",
    ]
    assert config["scientific_boundary"]["model_inference_authorized"] is False
    assert config["scientific_boundary"]["model_retraining_authorized"] is False

    snapshot = json.loads(
        (
            root
            / "case_studies/open_tem_saed_candidates/trusted_search_snapshot_2026-08-05.json"
        ).read_text(encoding="utf-8")
    )
    candidates = snapshot["candidates"]
    assert len(candidates) >= 10
    assert len({item["candidate_id"] for item in candidates}) == len(candidates)
    assert all(item["external_validation_ready"] is False for item in candidates)
    assert candidates[0]["candidate_id"] == "fhi_ac_catlab_d63268_co3o4_otem_saed"
    assert snapshot["scientific_closeout"]["evidence_level"] == "Diagnostic"
