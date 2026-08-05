from __future__ import annotations

import json
from datetime import date
from pathlib import Path


SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "case_studies"
    / "zenodo_silver_tem_saed_metadata_audit"
    / "verified_snapshot.json"
)


def test_zenodo_silver_snapshot_is_exact_and_fail_closed() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    source = payload["source"]
    assert source["record_id"] == 18942976
    assert source["doi"] == "10.5281/zenodo.18942976"
    assert source["status"] == "published"
    assert source["resource_type_id"] == "image"
    assert source["license_id"] == "cc-by-4.0"
    assert source["file_count"] == 3

    by_key = {row["key"]: row for row in payload["files"]}
    target = by_key["TEM_SAED.zip"]
    assert target["bytes"] == 1417789651
    assert target["checksum"] == "md5:c7bda9d495dd0fd657a8fe0332db4f9c"

    plan = payload["bounded_plan"]
    assert plan["exact_bytes"] == target["bytes"]
    assert plan["source_archive_download_authorized"] is False
    assert plan["source_artifact_upload_authorized"] is False
    assert plan["model_inference_authorized"] is False
    assert plan["annotation_authorized"] is False
    assert plan["parameter_tuning_authorized"] is False

    closeout = payload["closeout"]
    assert closeout["record_identity_and_file_inventory"] == "Supported"
    assert closeout["temporal_metadata_consistency"] == "Inconclusive"
    assert closeout["archive_member_inventory"] == "Inconclusive"
    assert closeout["analyzer_scientific_evidence_level"] == "Inconclusive"
    assert closeout["external_validation_ready"] is False
    assert closeout["engineering_decision_ready"] is False
    assert closeout["source_archive_downloaded"] is False


def test_future_publication_date_is_preserved_as_quality_flag() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    publication_date = date.fromisoformat(payload["source"]["publication_date"])
    audit_date = date.fromisoformat("2026-08-05")
    assert publication_date > audit_date

    flags = {row["code"]: row for row in payload["quality_flags"]}
    assert "publication_date_after_audit_date" in flags
    assert flags["publication_date_after_audit_date"]["severity"] == "warning"
    assert "resource_type_image_for_multifile_raw_data_record" in flags
