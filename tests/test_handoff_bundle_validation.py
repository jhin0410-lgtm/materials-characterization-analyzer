from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from mca.feature_records import LONG_FEATURE_COLUMNS
from mca.handoff_bundle import write_characterization_handoff_bundle
from mca.handoff_bundle_cli import main as validation_cli_main
from mca.handoff_bundle_validation import (
    HandoffBundleValidationError,
    VALIDATION_STATUS,
    validate_characterization_handoff_bundle,
    write_handoff_bundle_validation,
)


def _feature() -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-xrd",
        "instrument": "xrd",
        "feature_name": "detected_peak_count",
        "feature_label": None,
        "value": 3.0,
        "unit": "count",
        "method": "scipy_find_peaks",
        "source_file": "producer-local/source.csv",
        "source_sha256": "a" * 64,
        "preprocessing_id": "xrd-preprocessing-v1",
        "quality_flag": "review_required",
    }


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    root.mkdir()
    source_manifest = root / "source_manifest.json"
    source_manifest.write_text('{"source": "public"}\n', encoding="utf-8")
    analysis_manifest = root / "analysis_manifest.json"
    analysis_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.10.0",
                        "features": [_feature()],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {
            "modality": ["xrd"],
            "comparability_status": ["not_established"],
        }
    ).to_csv(comparability, index=False)

    write_characterization_handoff_bundle(
        root,
        case_id="handoff-validation-test",
        sample_context_rows=[
            {
                "sample_id": "sample-a",
                "identical_physical_aliquot_confirmed": False,
            }
        ],
        source_manifest_path=source_manifest,
        analysis_manifest_path=analysis_manifest,
        comparability_matrix_path=comparability,
        producer_repository="jhin0410-lgtm/materials-characterization-analyzer",
        evidence_level="Diagnostic",
        scientific_boundary={
            "primary_limitation": "identical physical aliquot is not confirmed"
        },
    )
    return root


def test_validate_handoff_bundle_recomputes_contract_counts(tmp_path: Path) -> None:
    root = _bundle(tmp_path)

    summary = validate_characterization_handoff_bundle(root)

    assert summary["status"] == VALIDATION_STATUS
    assert summary["sample_count"] == 1
    assert summary["measurement_count"] == 1
    assert summary["feature_count"] == 1
    assert summary["instruments"] == ["xrd"]
    assert summary["quality_flag_counts"] == {"review_required": 1}
    assert summary["sample_identity_consistent"] is True
    assert summary["scientific_comparability_established"] is False
    assert summary["engineering_release_ready"] is False


def test_feature_table_tampering_fails_closed(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    (root / "characterization_features_long.csv").write_text(
        "tampered\n", encoding="utf-8"
    )

    with pytest.raises(
        HandoffBundleValidationError,
        match="size_bytes mismatch|SHA-256 mismatch",
    ):
        validate_characterization_handoff_bundle(root)


def test_evidence_reference_tampering_fails_closed(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    (root / "comparability_matrix.csv").write_text(
        "modality,comparability_status\nxrd,changed\n", encoding="utf-8"
    )

    with pytest.raises(
        HandoffBundleValidationError,
        match="size_bytes mismatch|SHA-256 mismatch",
    ):
        validate_characterization_handoff_bundle(root)


def test_duplicate_manifest_key_is_rejected(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    manifest = root / "characterization_handoff_bundle.json"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace(
        '{\n  "bundle_type"',
        '{\n  "case_id": "duplicate",\n  "bundle_type"',
        1,
    )
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(HandoffBundleValidationError, match="duplicate JSON key"):
        validate_characterization_handoff_bundle(root)


def test_context_sample_identity_drift_is_detected_even_with_updated_hash(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    context_path = root / "sample_context.csv"
    context = pd.read_csv(context_path)
    context.loc[0, "sample_id"] = "different-sample"
    context.to_csv(context_path, index=False)

    manifest_path = root / "characterization_handoff_bundle.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sample_context"]["size_bytes"] = context_path.stat().st_size
    manifest["sample_context"]["sha256"] = hashlib.sha256(
        context_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        HandoffBundleValidationError,
        match="sample_id sets must match exactly",
    ):
        validate_characterization_handoff_bundle(root)


def test_validation_evidence_is_checksum_bound(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    output = tmp_path / "validation"

    paths = write_handoff_bundle_validation(root, output)

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["status"] == VALIDATION_STATUS
    artifact_manifest = json.loads(
        paths["artifact_manifest"].read_text(encoding="utf-8")
    )
    assert artifact_manifest["artifact_count"] == 2
    for record in artifact_manifest["artifacts"]:
        path = output / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_writer_preflight_failure_leaves_no_partial_bundle_artifacts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    analysis_manifest = root / "analysis_manifest.json"
    analysis_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.10.0",
                        "features": [_feature()],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame({"modality": ["xrd"]}).to_csv(comparability, index=False)

    with pytest.raises(FileNotFoundError, match="source manifest"):
        write_characterization_handoff_bundle(
            root,
            case_id="case",
            sample_context_rows=[{"sample_id": "sample-a"}],
            source_manifest_path=root / "missing_source_manifest.json",
            analysis_manifest_path=analysis_manifest,
            comparability_matrix_path=comparability,
            producer_repository="producer/repository",
            evidence_level="Diagnostic",
            scientific_boundary={},
        )

    assert not (root / "characterization_features_long.csv").exists()
    assert not (root / "sample_context.csv").exists()
    assert not (root / "characterization_handoff_bundle.json").exists()


def test_validate_handoff_cli_writes_evidence(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    output = tmp_path / "validation"

    exit_code = validation_cli_main(
        ["--bundle", str(root), "--output", str(output)]
    )

    assert exit_code == 0
    assert (output / "handoff_bundle_validation_summary.json").is_file()
    assert (output / "handoff_bundle_validation_report.md").is_file()
