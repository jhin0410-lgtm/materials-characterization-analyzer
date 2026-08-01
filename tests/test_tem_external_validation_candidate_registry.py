from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mca.cli_entry import main as cli_main
from mca.tem_external_validation_candidate_registry import (
    METADATA_RESOLUTION,
    RESULT,
    CandidateContractError,
    load_registry_config,
    run_candidate_registry,
)

CONFIG = (
    Path(__file__).parents[1]
    / "case_studies"
    / "tem_external_validation_candidate_registry"
    / "case_config.json"
)


def test_pinned_registry_has_no_evaluation_ready_candidate(tmp_path: Path) -> None:
    output = tmp_path / "out"
    summary = run_candidate_registry(load_registry_config(CONFIG), output)

    assert summary["readiness"]["status"] == RESULT
    assert not summary["readiness"][
        "independent_in_domain_external_validation_available"
    ]
    assert not summary["readiness"]["public_search_supports_model_evaluation_now"]
    assert summary["result_counts"] == {
        "candidate_count": 6,
        "in_domain_external_validation_ready_count": 0,
        "metadata_resolution_candidate_count": 1,
        "annotation_pilot_candidate_count": 0,
        "cross_phase_candidate_count": 2,
        "diagnostic_cross_material_candidate_count": 1,
        "excluded_control_count": 2,
    }
    assert summary["readiness"]["recommended_candidate_id"] == (
        "mendeley_8w66synjmx_cop_co2p_co3o4"
    )
    assert summary["readiness"]["recommended_candidate_status"] == METADATA_RESOLUTION
    assert "file inventory" in summary["readiness"]["recommended_next_action"]


def test_training_source_is_explicitly_excluded(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    inventory = (output / "tem_external_validation_candidate_inventory.csv").read_text(
        encoding="utf-8"
    )
    row = next(
        line
        for line in inventory.splitlines()
        if line.startswith("zenodo_14927582_target_training_source,")
    )
    assert ",target_training_source," in row
    assert "same_source_as_target_training_data" in row


def test_annotation_protocol_prevents_test_set_contamination(tmp_path: Path) -> None:
    summary = run_candidate_registry(load_registry_config(CONFIG), tmp_path / "out")
    protocol = summary["annotation_protocol"]
    assert protocol["annotation_requirements"][
        "minimum_independent_blinded_labelers"
    ] == 2
    assert protocol["annotation_requirements"]["adjudication_required"]
    assert protocol["independence_requirements"]["not_used_for_model_selection"]
    assert protocol["independence_requirements"][
        "content_overlap_audit_completed_before_inference"
    ]
    assert protocol["evaluation_freeze_requirements"][
        "test_manifest_checksum_frozen"
    ]
    assert any(
        "model predictions" in item for item in protocol["prohibited_shortcuts"]
    )


def test_manifest_records_all_artifact_hashes(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    manifest = json.loads(
        (output / "tem_external_validation_candidate_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 4
    for record in manifest["artifacts"]:
        path = output / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_unknown_config_key_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["candidates"][0]["invented_field"] = "not allowed"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CandidateContractError, match="unknown candidates"):
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
    result = cli_main(
        [
            "tem-candidates",
            "--config",
            str(CONFIG),
            "--output",
            str(output),
        ]
    )
    assert result == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == RESULT
    assert printed["candidate_count"] == 6
    assert printed["in_domain_external_validation_ready_count"] == 0
    assert (output / "tem_external_validation_candidate_report.md").is_file()
