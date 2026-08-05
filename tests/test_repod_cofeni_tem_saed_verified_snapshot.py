from __future__ import annotations

import json
from pathlib import Path


SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "case_studies"
    / "repod_cofeni_tem_saed_source_audit"
    / "verified_snapshot.json"
)


def test_repod_cofeni_snapshot_is_checksum_bound_and_fail_closed() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert payload["source"]["doi"] == "10.18150/SIOWH6"
    assert payload["source"]["version"] == "1.0"
    assert payload["source"]["record_file_count"] == 12
    assert len(payload["audited_targets"]) == 3
    assert len(payload["members"]) == 7
    assert all(len(row["sha256"]) == 64 for row in payload["audited_targets"])
    assert all(len(row["sha256"]) == 64 for row in payload["members"])

    member_summary = payload["member_summary"]
    assert member_summary["audited_member_count"] == 7
    assert member_summary["lossless_raster_member_count"] == 7
    assert member_summary["native_microscopy_member_count"] == 0
    assert member_summary["rendered_raster_member_count"] == 0
    assert member_summary["saed_named_member_count"] == 3

    metadata = payload["metadata_observation"]
    assert metadata["raw_detector_status_resolved"] is False
    assert metadata["sample_acquisition_lineage_resolved"] is False
    assert metadata["independent_tem_labels_available"] is False
    assert metadata["saed_pattern_center_resolved"] is False
    assert metadata["saed_reciprocal_calibration_resolved"] is False

    closeout = payload["closeout"]
    assert closeout["source_identity_and_archive_integrity"] == "Supported"
    assert closeout["analyzer_scientific_evidence_level"] == "Inconclusive"
    assert closeout["intake_decision"] == "accepted_for_bounded_diagnostic_only"
    assert closeout["external_validation_ready"] is False
    assert closeout["engineering_decision_ready"] is False
    assert closeout["model_inference_performed"] is False
    assert closeout["annotation_performed"] is False
    assert closeout["parameter_tuning_performed"] is False
