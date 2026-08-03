from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from mca.cli_entry import main as cli_main
from mca.tem_external_validation_candidate_registry import (
    EXCLUDED_REPRESENTATION,
    PROCESSED_IN_DOMAIN,
    RESULT,
    WRONG_MODALITY,
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
        "candidate_count": 9,
        "in_domain_external_validation_ready_count": 0,
        "metadata_resolution_candidate_count": 0,
        "annotation_pilot_candidate_count": 0,
        "processed_in_domain_diagnostic_count": 1,
        "rendered_representation_exclusion_count": 1,
        "cross_phase_candidate_count": 1,
        "diagnostic_cross_material_candidate_count": 1,
        "excluded_control_count": 5,
    }
    assert summary["readiness"]["recommended_candidate_id"] == (
        "zenodo_17336678_phaset3m_co3o4_processed_tilt_series"
    )
    assert summary["readiness"]["recommended_candidate_status"] == (
        PROCESSED_IN_DOMAIN
    )
    assert "Request raw detector frames" in summary["readiness"]["recommended_next_action"]


def test_resolved_mendeley_rendered_files_are_explicitly_excluded(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    inventory = (output / "tem_external_validation_candidate_inventory.csv").read_text(
        encoding="utf-8"
    )
    row = next(
        line
        for line in inventory.splitlines()
        if line.startswith("mendeley_8w66synjmx_cop_co2p_co3o4,")
    )
    assert f",{EXCLUDED_REPRESENTATION}," in row
    assert "rendered_figure_representation_not_raw_validation_data" in row
    assert "db3204100545fe3a152c0a545d29ab7f" in row


def test_new_co3o4_public_records_are_wrong_modality_exclusions(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "tem_external_validation_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}

    zenodo = rows["zenodo_14160831_co3o4_nio_replication_package"]
    assert zenodo["candidate_status"] == WRONG_MODALITY
    assert zenodo["reported_tem_file_count"] == "0"
    assert zenodo["raw_or_lossless_tem_images_available"] == "False"
    assert "replication_package.xlsx" in zenodo["source_evidence"]
    assert "862e64d9ebeba6fb34da16e89d5c19c4" in zenodo["source_evidence"]

    mendeley = rows["mendeley_kkk76z8g8z_current_public_archive"]
    assert mendeley["candidate_status"] == WRONG_MODALITY
    assert mendeley["reported_tem_file_count"] == "0"
    assert mendeley["raw_or_lossless_tem_images_available"] == "False"
    assert "download-routing metadata" in mendeley["source_evidence"]
    assert "e3af684f7892877ee073e54e54a230d969d661193c807703a3b083fbdc4e42e9" in mendeley["source_evidence"]
    assert "760 file members" in mendeley["source_evidence"]
    assert "Data/SEM/2.png" in mendeley["source_evidence"]



def test_phaset3m_processed_exact_material_is_diagnostic_only(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "tem_external_validation_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    candidate = next(
        row
        for row in rows
        if row["candidate_id"]
        == "zenodo_17336678_phaset3m_co3o4_processed_tilt_series"
    )
    assert candidate["candidate_status"] == PROCESSED_IN_DOMAIN
    assert candidate["in_domain_external_validation_ready"] == "False"
    assert candidate["evaluation_ready"] == "False"
    assert "raw_or_lossless_tem_images_unavailable" in candidate["blockers"]
    assert "target_creator_overlap" in candidate["blockers"]
    assert "reuse_license_unverified" in candidate["blockers"]


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
    assert any(
        "rendered publication figures" in item
        for item in protocol["prohibited_shortcuts"]
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
    assert printed["candidate_count"] == 9
    assert printed["in_domain_external_validation_ready_count"] == 0
    assert printed["recommended_candidate_id"] == (
        "zenodo_17336678_phaset3m_co3o4_processed_tilt_series"
    )
    assert (output / "tem_external_validation_candidate_report.md").is_file()



def test_candidate_inventory_preserves_versioned_provenance_columns(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "tem_external_validation_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    expected = {
        "label_origin",
        "labeler_count",
        "target_training_source",
        "in_domain_external_validation_ready",
        "evaluation_ready",
    }
    assert expected.issubset(rows[0])
    target = next(
        row
        for row in rows
        if row["candidate_id"] == "zenodo_14927582_target_training_source"
    )
    assert target["target_training_source"] == "True"
    assert target["in_domain_external_validation_ready"] == "False"
    assert target["evaluation_ready"] == "False"


def test_mutually_exclusive_candidate_status_counts_reconcile(
    tmp_path: Path,
) -> None:
    counts = run_candidate_registry(
        load_registry_config(CONFIG), tmp_path / "out"
    )["result_counts"]
    bucket_total = sum(
        counts[key]
        for key in (
            "in_domain_external_validation_ready_count",
            "metadata_resolution_candidate_count",
            "annotation_pilot_candidate_count",
            "processed_in_domain_diagnostic_count",
            "rendered_representation_exclusion_count",
            "cross_phase_candidate_count",
            "diagnostic_cross_material_candidate_count",
            "excluded_control_count",
        )
    )
    assert bucket_total == counts["candidate_count"]



def _ready_candidate_payload() -> dict:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    candidate = payload["candidates"][0].copy()
    candidate.update(
        {
            "candidate_id": "independent_ready_candidate",
            "repository": "Independent Repository",
            "doi": "10.0000/independent-ready",
            "record_url": "https://example.org/independent-ready",
            "title": "Independent cobalt oxide HRTEM validation set",
            "file_inventory_status": "exact",
            "file_checksums_available": True,
            "raw_or_lossless_tem_images_available": True,
            "reported_tem_file_count": 8,
            "independent_segmentation_labels_available": True,
            "label_origin": "two blinded experts plus adjudicated consensus",
            "labeler_count": 2,
            "blinded_labeling_verified": True,
            "adjudicated_consensus_available": True,
            "immutable_sample_ids_available": True,
            "immutable_acquisition_ids_available": True,
            "verified_not_used_for_target_training_or_model_selection": True,
            "target_creator_name_overlap": False,
            "target_training_source": False,
            "source_evidence": ["checksum-bound independent source"],
            "next_validation_step": "Run the dedicated frozen candidate audit.",
        }
    )
    payload["candidates"].append(candidate)
    return payload


def _load_payload(tmp_path: Path, payload: dict):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_registry_config(path)


def test_ready_candidate_requires_two_blinded_labelers_and_adjudication(
    tmp_path: Path,
) -> None:
    payload = _ready_candidate_payload()
    candidate = payload["candidates"][-1]
    candidate["labeler_count"] = 1
    candidate["blinded_labeling_verified"] = False
    candidate["adjudicated_consensus_available"] = False
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 0


def test_ready_candidate_requires_resolved_file_inventory(tmp_path: Path) -> None:
    payload = _ready_candidate_payload()
    payload["candidates"][-1]["file_inventory_status"] = "unresolved"
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 0
    assert summary["result_counts"]["metadata_resolution_candidate_count"] == 1


def test_ready_summary_is_derived_from_candidate_rows(tmp_path: Path) -> None:
    summary = run_candidate_registry(
        _load_payload(tmp_path, _ready_candidate_payload()), tmp_path / "out"
    )
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 1
    assert summary["readiness"]["independent_in_domain_external_validation_available"]
    assert summary["readiness"]["public_search_supports_model_evaluation_now"]
    assert summary["readiness"]["recommended_candidate_status"] == (
        "in_domain_external_validation_ready"
    )


def test_stem_only_candidate_does_not_match_tem_token(tmp_path: Path) -> None:
    payload = _ready_candidate_payload()
    payload["candidates"][-1]["modalities"] = ["STEM"]
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 0


def test_registry_without_metadata_resolution_candidate_still_recommends(
    tmp_path: Path,
) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert all(
        item["file_inventory_status"] in {"exact", "record_metadata_verified"}
        for item in payload["candidates"]
    )
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["readiness"]["recommended_candidate_id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task", "binary segmentation for gold SEM"),
        ("material", "gold"),
        ("modalities", ["SEM"]),
    ],
)
def test_unsupported_target_contract_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["target_contract"][field] = value
    with pytest.raises(CandidateContractError, match="unsupported target|target modalities"):
        _load_payload(tmp_path, payload)
