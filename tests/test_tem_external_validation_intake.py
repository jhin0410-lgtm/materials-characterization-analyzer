from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mca.cli_entry import main as cli_main
from mca.tem_external_validation_intake import (
    ANNOTATION_INCOMPLETE,
    ANNOTATION_READY,
    BLOCKED,
    EVALUATION_READY,
    IntakeContractError,
    load_intake_manifest,
    run_external_validation_intake,
)


def _write_file(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _image(
    image_id: str,
    path: str,
    sha256: str,
    sample_id: str,
    acquisition_id: str,
    *,
    representation: str = "raw_detector",
    original_intensity: bool = True,
) -> dict:
    return {
        "image_id": image_id,
        "relative_path": path,
        "sha256": sha256,
        "sample_id": sample_id,
        "acquisition_id": acquisition_id,
        "modality": "HRTEM",
        "representation": representation,
        "original_detector_intensity_available": original_intensity,
        "nm_per_pixel": None,
        "calibration_source": None,
        "used_for_training": False,
        "used_for_threshold_selection": False,
        "used_for_hyperparameter_tuning": False,
        "used_for_model_selection": False,
        "excluded": False,
        "exclusion_reason": None,
    }


def _annotation(
    annotation_id: str,
    image_id: str,
    path: str,
    sha256: str,
    labeler_id: str,
    role: str,
    *,
    blinded: bool = True,
    used_for_model_selection: bool = False,
) -> dict:
    return {
        "annotation_id": annotation_id,
        "image_id": image_id,
        "relative_path": path,
        "sha256": sha256,
        "labeler_id": labeler_id,
        "annotation_role": role,
        "blinded_to_model_predictions": blinded,
        "label_definition_version": "particle-mask-v1",
        "used_for_training": False,
        "used_for_threshold_selection": False,
        "used_for_hyperparameter_tuning": False,
        "used_for_model_selection": used_for_model_selection,
    }


def _protocol(*, complete: bool = False) -> dict:
    return {
        "source_metadata_review_status": "passed" if complete else "not_run",
        "image_content_audit_status": "passed" if complete else "not_run",
        "label_content_audit_status": "passed" if complete else "not_run",
        "content_overlap_audit_status": "passed" if complete else "not_run",
        "test_manifest_checksum_frozen": complete,
        "metrics_frozen": complete,
        "confidence_interval_method_frozen": complete,
        "exclusion_rules_frozen": complete,
        "frozen_protocol_id": "tem-eval-v1" if complete else None,
    }


def _manifest(images: list[dict], annotations: list[dict], *, protocol_complete: bool = False) -> dict:
    return {
        "schema_version": "1.0",
        "case_id": "tem_external_validation_intake",
        "dataset": {
            "dataset_id": "external-cobalt-oxide-001",
            "dataset_version": "v1",
            "source_type": "new_acquisition",
            "material_domain": "cobalt oxide",
            "license": "institution-approved research use",
            "reuse_authorized": True,
            "identity_provenance": "operator_assigned_at_acquisition",
            "target_training_nonuse_attested": True,
            "target_creator_overlap": False,
            "cross_dataset_lineage_independence_attested": True,
            "minimum_independent_blinded_labelers": 2,
        },
        "images": images,
        "annotations": annotations,
        "evaluation_protocol": _protocol(complete=protocol_complete),
    }


def _write_manifest(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _two_images(root: Path) -> list[dict]:
    first = _write_file(root, "images/sample-a.tif", b"synthetic-image-a")
    second = _write_file(root, "images/sample-b.tif", b"synthetic-image-b")
    return [
        _image("image-a", "images/sample-a.tif", first, "sample-a", "acq-a"),
        _image("image-b", "images/sample-b.tif", second, "sample-b", "acq-b"),
    ]


def _complete_annotations(root: Path) -> list[dict]:
    records: list[dict] = []
    for image_id in ("image-a", "image-b"):
        for labeler in ("expert-1", "expert-2"):
            relative = f"labels/{image_id}-{labeler}.png"
            digest = _write_file(root, relative, f"{image_id}-{labeler}".encode())
            records.append(
                _annotation(
                    f"{image_id}-{labeler}",
                    image_id,
                    relative,
                    digest,
                    labeler,
                    "independent",
                )
            )
        relative = f"labels/{image_id}-consensus.png"
        digest = _write_file(root, relative, f"{image_id}-consensus".encode())
        records.append(
            _annotation(
                f"{image_id}-consensus",
                image_id,
                relative,
                digest,
                "adjudicator",
                "adjudicated_consensus",
            )
        )
    return records


def test_checksum_bound_independent_images_are_ready_for_blinded_annotation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        _manifest(_two_images(root), []),
    )
    output = tmp_path / "out"
    summary = run_external_validation_intake(
        load_intake_manifest(manifest_path), root, output
    )

    assert summary["decision"]["status"] == ANNOTATION_READY
    assert summary["decision"]["blinded_annotation_pilot_ready"]
    assert not summary["decision"][
        "predeclared_external_model_evaluation_ready"
    ]
    assert not summary["decision"]["independent_performance_claim_ready"]
    assert summary["result_counts"]["sample_count"] == 2
    assert summary["result_counts"]["acquisition_count"] == 2
    assert summary["result_counts"]["duplicate_active_image_content_count"] == 0

    manifest = json.loads(
        (output / "tem_validation_intake_artifact_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 3
    for record in manifest["artifacts"]:
        path = output / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_rendered_figures_are_blocked_before_annotation(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    for image in images:
        image["representation"] = "rendered_figure"
        image["original_detector_intensity_available"] = False
    manifest = load_intake_manifest(
        _write_manifest(tmp_path / "manifest.json", _manifest(images, []))
    )
    summary = run_external_validation_intake(manifest, root, tmp_path / "out")
    assert summary["decision"]["status"] == BLOCKED
    assert not summary["decision"]["blinded_annotation_pilot_ready"]
    assert "raw_or_lossless_original_intensity_images" in summary[
        "evidence_gates"
    ]["unresolved_evidence"]


def test_exact_duplicate_active_images_are_blocked(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    digest_a = _write_file(root, "images/a.tif", b"same-content")
    digest_b = _write_file(root, "images/b.tif", b"same-content")
    images = [
        _image("image-a", "images/a.tif", digest_a, "sample-a", "acq-a"),
        _image("image-b", "images/b.tif", digest_b, "sample-b", "acq-b"),
    ]
    summary = run_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(images, []))
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == BLOCKED
    assert summary["result_counts"]["duplicate_active_image_content_count"] == 1
    assert not summary["evidence_gates"][
        "no_exact_duplicate_active_image_content"
    ]


def test_incomplete_or_prediction_exposed_labels_do_not_unlock_evaluation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    digest = _write_file(root, "labels/image-a-expert-1.png", b"label")
    annotations = [
        _annotation(
            "image-a-expert-1",
            "image-a",
            "labels/image-a-expert-1.png",
            digest,
            "expert-1",
            "independent",
            blinded=False,
            used_for_model_selection=True,
        )
    ]
    summary = run_external_validation_intake(
        load_intake_manifest(
            _write_manifest(
                tmp_path / "manifest.json",
                _manifest(images, annotations),
            )
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == ANNOTATION_INCOMPLETE
    assert summary["decision"]["blinded_annotation_pilot_ready"]
    assert not summary["evidence_gates"]["independent_annotations_complete"]
    assert not summary["decision"]["model_inference_allowed_now"]


def test_complete_labels_and_frozen_audits_allow_only_predeclared_evaluation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    annotations = _complete_annotations(root)
    summary = run_external_validation_intake(
        load_intake_manifest(
            _write_manifest(
                tmp_path / "manifest.json",
                _manifest(images, annotations, protocol_complete=True),
            )
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == EVALUATION_READY
    assert summary["decision"]["model_inference_allowed_now"]
    assert summary["decision"][
        "predeclared_external_model_evaluation_ready"
    ]
    assert not summary["decision"]["independent_performance_claim_ready"]
    assert not summary["decision"]["engineering_release_ready"]


def test_hash_mismatch_fails_before_outputs(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    images[0]["sha256"] = "0" * 64
    manifest = load_intake_manifest(
        _write_manifest(tmp_path / "manifest.json", _manifest(images, []))
    )
    output = tmp_path / "out"
    with pytest.raises(IntakeContractError, match="SHA-256 mismatch"):
        run_external_validation_intake(manifest, root, output)
    assert not output.exists()


def test_unsafe_path_is_rejected_during_manifest_load(tmp_path: Path) -> None:
    payload = _manifest(
        [
            _image(
                "image-a",
                "images/a.tif",
                "a" * 64,
                "sample-a",
                "acq-a",
            )
        ],
        [],
    )
    payload["images"][0]["relative_path"] = "../outside.tif"
    with pytest.raises(IntakeContractError, match="safe relative path"):
        load_intake_manifest(_write_manifest(tmp_path / "manifest.json", payload))


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    manifest = load_intake_manifest(
        _write_manifest(
            tmp_path / "manifest.json", _manifest(_two_images(root), [])
        )
    )
    output = tmp_path / "out"
    run_external_validation_intake(manifest, root, output)
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_external_validation_intake(manifest, root, output)


def test_cli_dispatches_and_writes_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    manifest = _write_manifest(
        tmp_path / "manifest.json", _manifest(_two_images(root), [])
    )
    output = tmp_path / "cli-out"
    result = cli_main(
        [
            "tem-validation-intake",
            "--manifest",
            str(manifest),
            "--data-root",
            str(root),
            "--output",
            str(output),
        ]
    )
    assert result == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == ANNOTATION_READY
    assert printed["active_image_count"] == 2
    assert (output / "tem_validation_intake_report.md").is_file()
