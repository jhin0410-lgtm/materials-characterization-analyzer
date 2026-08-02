from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from mca.cli_entry import main as cli_main
from mca.saed_external_validation_candidate_registry import (
    ARCHIVED,
    CALIBRATION_RESOLUTION,
    MODE_SHIFT,
    READY,
    RENDERED,
    RESULT,
    SAEDCandidateContractError,
    load_registry_config,
    run_candidate_registry,
)

CONFIG = (
    Path(__file__).parents[1]
    / "case_studies"
    / "saed_public_candidate_registry"
    / "case_config.json"
)


def test_pinned_registry_preserves_fail_closed_result(tmp_path: Path) -> None:
    summary = run_candidate_registry(
        load_registry_config(CONFIG), tmp_path / "out"
    )

    assert summary["readiness"]["status"] == RESULT
    assert not summary["readiness"][
        "public_candidate_ready_for_dedicated_source_audit"
    ]
    assert not summary["readiness"]["public_search_supports_saed_evaluation_now"]
    assert summary["result_counts"] == {
        "candidate_count": 7,
        "dedicated_source_audit_ready_count": 0,
        "calibration_or_center_resolution_count": 2,
        "metadata_or_file_inventory_resolution_count": 1,
        "acquisition_mode_shift_diagnostic_count": 2,
        "source_unavailable_or_archived_count": 1,
        "rendered_or_software_example_exclusion_count": 1,
    }
    assert summary["readiness"]["recommended_candidate_id"] == (
        "bir_microed_200kev_zenodo_10999587"
    )
    assert summary["readiness"]["recommended_candidate_status"] == (
        CALIBRATION_RESOLUTION
    )
    assert not summary["readiness"]["analyzer_execution_is_current_priority"]


def test_bir_static_candidate_exposes_calibration_and_lineage_blockers(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "saed_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    candidate = next(
        row
        for row in rows
        if row["candidate_id"] == "bir_microed_200kev_zenodo_10999587"
    )
    assert candidate["candidate_status"] == CALIBRATION_RESOLUTION
    assert candidate["dedicated_source_audit_ready"] == "False"
    assert "immutable_sample_ids_unavailable" in candidate["blockers"]
    assert "pattern_center_untraceable" in candidate["blockers"]
    assert "reciprocal_calibration_untraceable" in candidate["blockers"]
    assert "reuse_license_unverified" in candidate["blockers"]


def test_3ded_records_are_mode_shift_diagnostics(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "saed_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    statuses = {
        row["candidate_id"]: row["candidate_status"] for row in rows
    }
    assert statuses["lhistidine_3ded_zenodo_10974780"] == MODE_SHIFT
    assert statuses["carmine_3ded_zenodo_14278562"] == MODE_SHIFT


def test_archived_and_software_candidates_remain_separate(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "saed_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    statuses = {
        row["candidate_id"]: row["candidate_status"] for row in rows
    }
    assert statuses["datacore_diffraction_pattern_ct7n8275"] == ARCHIVED
    assert statuses["finds_software_zenodo_21114966"] == RENDERED


def test_registry_never_promotes_candidate_to_evaluation_ready(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "saed_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(
        row["predeclared_external_evaluation_ready"] == "False"
        for row in rows
    )


def test_source_audit_protocol_blocks_posthoc_selection(tmp_path: Path) -> None:
    summary = run_candidate_registry(
        load_registry_config(CONFIG), tmp_path / "out"
    )
    protocol = summary["source_audit_protocol"]
    assert protocol["subset_requirements"][
        "minimum_independent_pattern_series"
    ] == 2
    assert protocol["subset_requirements"][
        "record_archive_and_member_checksums"
    ]
    assert protocol["instrument_and_calibration_requirements"][
        "traceable_reciprocal_calibration_required"
    ]
    assert protocol["evaluation_freeze_requirements"][
        "canonical_manifest_checksum_frozen"
    ]
    assert any(
        "selecting files after viewing" in item
        for item in protocol["prohibited_shortcuts"]
    )


def test_artifact_manifest_records_all_output_hashes(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    manifest = json.loads(
        (output / "saed_candidate_artifact_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 4
    for record in manifest["artifacts"]:
        path = output / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_unknown_candidate_field_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["candidates"][0]["invented_field"] = "not allowed"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SAEDCandidateContractError, match="unknown candidates"):
        load_registry_config(path)


def test_duplicate_json_key_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"case_id":"a","case_id":"b"}', encoding="utf-8"
    )
    with pytest.raises(SAEDCandidateContractError, match="duplicate JSON"):
        load_registry_config(path)


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    config = load_registry_config(CONFIG)
    output = tmp_path / "out"
    run_candidate_registry(config, output)
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_candidate_registry(config, output)


def test_cli_writes_registry_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli-out"
    assert (
        cli_main(
            [
                "saed-candidates",
                "--config",
                str(CONFIG),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == RESULT
    assert printed["candidate_count"] == 7
    assert printed["dedicated_source_audit_ready_count"] == 0
    assert printed["recommended_candidate_id"] == (
        "bir_microed_200kev_zenodo_10999587"
    )
    assert (output / "saed_candidate_report.md").is_file()


def _ready_payload() -> dict:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    candidate = dict(payload["candidates"][0])
    candidate.update(
        {
            "candidate_id": "independent_static_saed_ready",
            "reported_pattern_series_count": 2,
            "immutable_sample_ids_available": True,
            "immutable_acquisition_ids_available": True,
            "detector_metadata_available": True,
            "detector_pixel_size_available": True,
            "pattern_center_traceable": True,
            "reciprocal_calibration_traceable": True,
            "reuse_license": "CC BY 4.0",
            "reuse_license_verified": True,
            "analyzer_development_nonuse_verified": True,
            "source_evidence": ["checksum-bound independent static SAED source"],
            "next_validation_step": "Run the dedicated bounded source audit.",
        }
    )
    payload["candidates"].append(candidate)
    return payload


def _load_payload(tmp_path: Path, payload: dict):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_registry_config(path)


def test_ready_status_is_derived_from_all_candidate_gates(
    tmp_path: Path,
) -> None:
    summary = run_candidate_registry(
        _load_payload(tmp_path, _ready_payload()), tmp_path / "out"
    )
    assert summary["result_counts"]["dedicated_source_audit_ready_count"] == 1
    assert summary["readiness"][
        "public_candidate_ready_for_dedicated_source_audit"
    ]
    assert summary["readiness"]["recommended_candidate_status"] == READY
    assert not summary["readiness"]["public_search_supports_saed_evaluation_now"]


def test_traceable_reciprocal_calibration_does_not_require_pixel_size(
    tmp_path: Path,
) -> None:
    payload = _ready_payload()
    payload["candidates"][-1]["detector_pixel_size_available"] = False
    output = tmp_path / "out"
    summary = run_candidate_registry(
        _load_payload(tmp_path, payload), output
    )
    assert summary["result_counts"]["dedicated_source_audit_ready_count"] == 1
    with (output / "saed_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    candidate = next(
        row
        for row in rows
        if row["candidate_id"] == "independent_static_saed_ready"
    )
    assert candidate["dedicated_source_audit_ready"] == "True"
    assert "detector_pixel_size_unavailable" not in candidate["blockers"]


def test_ready_candidate_requires_minimum_independent_series(
    tmp_path: Path,
) -> None:
    payload = _ready_payload()
    payload["candidates"][-1]["reported_pattern_series_count"] = 1
    summary = run_candidate_registry(
        _load_payload(tmp_path, payload), tmp_path / "out"
    )
    assert summary["result_counts"]["dedicated_source_audit_ready_count"] == 0


def test_candidate_status_counts_reconcile(tmp_path: Path) -> None:
    counts = run_candidate_registry(
        load_registry_config(CONFIG), tmp_path / "out"
    )["result_counts"]
    bucket_total = sum(
        counts[key]
        for key in (
            "dedicated_source_audit_ready_count",
            "calibration_or_center_resolution_count",
            "metadata_or_file_inventory_resolution_count",
            "acquisition_mode_shift_diagnostic_count",
            "source_unavailable_or_archived_count",
            "rendered_or_software_example_exclusion_count",
        )
    )
    assert bucket_total == counts["candidate_count"]
