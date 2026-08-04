from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tem_independent_validation_source_request.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "tem_independent_validation_source_request", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _registry_bundle(root: Path) -> Path:
    root.mkdir()
    inventory = root / "tem_external_validation_candidate_inventory.csv"
    columns = ["candidate_id", "evaluation_ready"]
    with inventory.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for index in range(11):
            writer.writerow(
                {"candidate_id": f"candidate_{index}", "evaluation_ready": "False"}
            )
    summary = {
        "schema_version": "1.0",
        "case_id": "tem_external_validation_candidate_registry",
        "target_contract": {
            "task": "binary nanoparticle segmentation for cobalt-oxide TEM or HRTEM images",
            "material": "cobalt oxide",
            "modalities": ["TEM", "HRTEM"],
            "target_training_creators": ["Mary Scott", "Training Author"],
        },
        "result_counts": {
            "candidate_count": 11,
            "in_domain_external_validation_ready_count": 0,
        },
        "readiness": {
            "status": "no_public_candidate_ready_for_in_domain_external_validation",
            "independent_in_domain_external_validation_available": False,
        },
        "processing": {
            "source_arrays_downloaded_by_registry": False,
            "source_arrays_modified": False,
            "labels_created": False,
            "model_training_performed": False,
            "model_inference_performed": False,
            "segmentation_metrics_computed": False,
        },
    }
    summary_path = root / "tem_external_validation_candidate_summary.json"
    _write_json(summary_path, summary)
    report = root / "tem_external_validation_candidate_report.md"
    report.write_text("# registry\n", encoding="utf-8")
    protocol = {
        "schema_version": "1.0",
        "annotation_requirements": {
            "minimum_independent_blinded_labelers": 2,
        },
        "independence_requirements": {
            "immutable_sample_ids_required": True,
        },
    }
    protocol_path = root / "tem_external_validation_annotation_protocol.json"
    _write_json(protocol_path, protocol)
    artifacts = []
    for path in (inventory, summary_path, report, protocol_path):
        artifacts.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "case_id": "tem_external_validation_candidate_registry",
        "software_version": "0.10.0",
        "search_date": "2026-08-03",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    _write_json(
        root / "tem_external_validation_candidate_manifest.json", manifest
    )
    return root


def _positive_response() -> dict:
    def image(index: int) -> dict:
        return {
            "image_id": f"img_{index}",
            "relative_path": f"sample_{index}/image_{index}.tif",
            "bytes": 1000 + index,
            "sha256": f"{index + 1:064x}",
            "sample_id": f"sample_{index}",
            "acquisition_id": f"acq_{index}",
            "identity_provenance": "source_assigned",
            "modality": "HRTEM" if index == 2 else "TEM",
            "representation": "lossless_export",
            "original_detector_intensity_available": True,
            "instrument": "JEOL JEM-2100F",
            "detector": "Gatan OneView",
            "accelerating_voltage_kv": 200.0,
            "nm_per_pixel": 0.04,
            "calibration_source": "instrument metadata and calibration certificate",
            "acquisition_date": f"2025-01-0{index}",
            "acquisition_conditions": "low-dose acquisition; no smoothing or contrast remapping",
            "used_for_training": False,
            "used_for_threshold_selection": False,
            "used_for_hyperparameter_tuning": False,
            "used_for_model_selection": False,
        }

    return {
        "schema_version": "1.0",
        "request_case_id": "tem_independent_validation_source_request",
        "response_status": "candidate_available",
        "respondent": {
            "name": "Dr. Independent Custodian",
            "affiliation": "Independent Microscopy Facility",
            "email": "custodian@example.org",
            "authority": "data_collector",
            "authority_basis": "Principal operator and data custodian",
        },
        "candidate": {
            "dataset_id": "independent_co_oxide_tem_2025",
            "dataset_version": "1.0",
            "source_type": "private_transfer",
            "repository_or_transfer_method": "checksum-bound institutional transfer",
            "persistent_identifier": "facility-accession-2025-001",
            "collection_manifest_sha256": "a" * 64,
            "license": "written research reuse authorization",
            "reuse_authorized": True,
            "material": {
                "composition": "Co3O4",
                "phase": "spinel Co3O4",
                "purity_scope": "pure_cobalt_oxide",
                "processing_history": "hydrothermal synthesis and calcination",
                "comparability_notes": "independent preparation route and acquisition laboratory",
            },
            "creator_names": ["Independent Custodian", "Independent Operator"],
            "target_creator_overlap": False,
            "target_training_nonuse_attested": True,
            "cross_dataset_lineage_independence_attested": True,
            "images": [image(1), image(2)],
            "labels": {
                "available": False,
                "label_definition_version": None,
                "independent_labeler_count": 0,
                "blinded_to_model_predictions": False,
                "adjudicated_consensus_available": False,
                "file_manifest_sha256": None,
            },
        },
        "referrals": [],
        "notes": "Candidate metadata supplied for bounded verification only.",
    }


def test_load_registry_bundle_and_build_request(tmp_path: Path) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    assert bundle["candidate_count"] == 11
    assert bundle["target_modalities"] == ["TEM", "HRTEM"]
    output = tmp_path / "request"
    summary = module.build_request_package(bundle, output)
    assert summary["status"] == "independent_source_request_package_ready"
    assert summary["email_sent"] is False
    assert summary["source_download_authorized"] is False
    assert (output / "tem_independent_source_correspondence.md").is_file()
    template = json.loads(
        (output / "tem_independent_source_author_response_template.json").read_text(
            encoding="utf-8"
        )
    )
    assert template["response_status"] == "not_available"
    manifest = json.loads(
        (output / "tem_independent_source_request_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 4


def test_registry_manifest_detects_mutation(tmp_path: Path) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    path = registry / "tem_external_validation_candidate_summary.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(module.SourceRequestContractError, match="byte mismatch"):
        module.load_registry_bundle(registry)


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    response = tmp_path / "duplicate.json"
    response.write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8"
    )
    with pytest.raises(module.SourceRequestContractError, match="duplicate JSON key"):
        module.assess_author_response(bundle, response, tmp_path / "out")


def test_placeholder_identity_is_rejected(tmp_path: Path) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    payload = _positive_response()
    payload["respondent"]["name"] = "replace-with-name"
    response = tmp_path / "response.json"
    _write_json(response, payload)
    with pytest.raises(module.SourceRequestContractError, match="placeholder"):
        module.assess_author_response(bundle, response, tmp_path / "out")


def test_referral_response_remains_download_blocked(tmp_path: Path) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    payload = {
        "schema_version": "1.0",
        "request_case_id": "tem_independent_validation_source_request",
        "response_status": "referral_only",
        "respondent": {
            "name": "Repository Curator",
            "affiliation": "Microscopy Repository",
            "email": "curator@example.org",
            "authority": "repository_curator",
            "authority_basis": "Repository record custodian",
        },
        "candidate": None,
        "referrals": [
            {
                "name": "Independent Collector",
                "affiliation": "External Facility",
                "email": "collector@example.org",
                "reason": "Holds original detector exports",
            }
        ],
        "notes": "No candidate files are held by this repository.",
    }
    response = tmp_path / "response.json"
    _write_json(response, payload)
    assessment = module.assess_author_response(
        bundle, response, tmp_path / "assessment"
    )
    assert assessment["status"] == "no_candidate_source_declared"
    assert assessment["source_download_authorized"] is False
    assessment["ready_for_bounded_source_verification"] is False


def test_complete_candidate_response_only_authorizes_verification_plan(
    tmp_path: Path,
) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    response = tmp_path / "response.json"
    _write_json(response, _positive_response())
    output = tmp_path / "assessment"
    assessment = module.assess_author_response(bundle, response, output)
    assert (
        assessment["status"]
        == "candidate_response_ready_for_bounded_source_verification"
    )
    assert assessment["ready_for_bounded_source_verification"] is True
    assessment["source_download_authorized"] is False
    assessment["tem_validation_intake_ready"] is False
    assert assessment["external_evaluation_ready"] is False
    assert not assessment["source_blockers"]
    plan = json.loads(
        (output / "tem_bounded_source_verification_plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert plan["source_download_authorized"] is False
    assert len(plan["declared_files"]) == 2
    manifest = json.loads(
        (output / "tem_independent_source_response_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 4


@pytest.mark.parametrize(
    ("mutation", "blocker"),
    [
        (
            lambda payload: payload["candidate"].update(
                {"target_creator_overlap": True}
            ),
            "target_creator_disjoint",
        ),
        (
            lambda payload: payload["candidate"]["images"].__setitem__(
                slice(1, None), []
            ),
            "minimum_two_independent_samples",
        ),
        (
            lambda payload: payload["candidate"]["images"][0].update(
                {"representation": "rendered_figure"}
            ),
            "raw_or_lossless_representation",
        ),
        (
            lambda payload: payload["candidate"]["material"].update(
                {"purity_scope": "mixed_or_composite"}
            ),
            "pure_cobalt_oxide_scope",
        ),
    ],
)
def test_candidate_response_blocks_scientific_mismatch(
    tmp_path: Path, mutation, blocker: str
) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    payload = _positive_response()
    mutation(payload)
    response = tmp_path / "response.json"
    _write_json(response, payload)
    assessment = module.assess_author_response(
        bundle, response, tmp_path / "assessment"
    )
    assert assessment["status"] == "candidate_response_received_but_source_not_ready"
    assert blocker in assessment["source_blockers"]
    assert assessment["source_download_authorized"] is False
    assert not (
        tmp_path
        / "assessment"
        / "tem_bounded_source_verification_plan.json"
     ).exists()


def test_nonempty_output_is_rejected(tmp_path: Path) -> None:
    module = _load_module()
    registry = _registry_bundle(tmp_path / "registry")
    bundle = module.load_registry_bundle(registry)
    output = tmp_path / "request"
    output.mkdir()
    (output / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        module.build_request_package(bundle, output)
