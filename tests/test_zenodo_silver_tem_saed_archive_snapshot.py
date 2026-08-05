from __future__ import annotations

import json
from pathlib import Path


SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "case_studies"
    / "zenodo_silver_tem_saed_archive_audit"
    / "verified_snapshot.json"
)


def _load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_archive_identity_and_inventory_are_pinned() -> None:
    payload = _load()
    archive = payload["archive"]
    assert payload["source"]["record_id"] == 18942976
    assert archive["bytes"] == 1417789651
    assert archive["md5"] == "c7bda9d495dd0fd657a8fe0332db4f9c"
    assert archive["sha256"] == (
        "4569a878be7053c2e84867a5693e9483fd9b937b765ce5e3be15e3f154b5fa12"
    )
    assert archive["member_count"] == 241
    assert archive["total_uncompressed_bytes"] == 1732391068
    assert archive["member_hashing_complete"] is True
    assert archive["crc_verification_complete"] is True


def test_representation_snapshot_is_exact() -> None:
    members = _load()["member_summary"]
    assert members["top_level_directories"] == {"MET": 241}
    assert members["suffix_counts"] == {
        ".tif": 212,
        ".txt": 19,
        ".docx": 9,
        ".xlsx": 1,
    }
    representations = members["representation_counts"]
    assert representations["native_microscopy_container"] == 0
    assert representations["lossless_or_lossless-capable_raster_export"] == 212
    assert representations["rendered_raster"] == 0
    assert len(members["explicit_saed_named_members"]) == 2
    assert members["name_cue_counts"]["calibration"] == 0


def test_scientific_readiness_remains_closed() -> None:
    payload = _load()
    boundaries = payload["scientific_boundaries"]
    assert boundaries["raw_detector_status_resolved"] is False
    assert boundaries["sample_acquisition_lineage_resolved"] is False
    assert boundaries["tem_independent_segmentation_labels_available"] is False
    assert boundaries["saed_pattern_center_resolved"] is False
    assert boundaries["saed_reciprocal_calibration_resolved"] is False
    assert boundaries["source_archive_retained"] is False
    assert boundaries["model_inference_performed"] is False
    assert boundaries["parameter_tuning_performed"] is False

    closeout = payload["closeout"]
    assert closeout["source_identity_archive_integrity_and_member_hashing"] == "Supported"
    assert closeout["representation_and_filename_inventory"] == "Supported"
    assert closeout["tem_external_validation"] == "Inconclusive"
    assert closeout["saed_external_validation"] == "Inconclusive"
    assert closeout["analyzer_scientific_evidence_level"] == "Inconclusive"
    assert closeout["external_validation_ready"] is False
    assert closeout["engineering_decision_ready"] is False
