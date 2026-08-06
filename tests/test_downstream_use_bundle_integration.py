from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.handoff_bundle_builder import build_characterization_handoff_bundle_from_config


def _write_config(tmp_path: Path, policy: dict[str, object] | None = None) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "source.json").write_text('{"source":"public"}\n', encoding="utf-8")
    feature = {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-raman",
        "instrument": "raman",
        "feature_name": "candidate_count",
        "feature_label": None,
        "value": 2.0,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "raman.txt",
        "source_sha256": "a" * 64,
        "preprocessing_id": "raman-preprocessing-v1",
        "quality_flag": "review_required",
    }
    (evidence / "analysis.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.10.0",
                        "features": [feature],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(evidence / "comparability.csv", index=False)
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "case_id": "policy-integration",
        "producer_repository": "jhin0410-lgtm/materials-characterization-analyzer",
        "evidence_level": "Diagnostic",
        "sample_context_rows": [{"sample_id": "sample-a"}],
        "scientific_boundary": {
            "suitable_for": ["descriptive analysis"],
            "unsuitable_for": ["predictive use"],
        },
        "evidence": {
            "source_manifest": "evidence/source.json",
            "analysis_manifest": "evidence/analysis.json",
            "comparability_matrix": "evidence/comparability.csv",
        },
    }
    if policy is not None:
        payload["downstream_use_policy"] = policy
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def _association_policy(group_field: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "maximum_allowed_use": "association",
        "feature_stage": "derived",
        "evidence_level": "Diagnostic",
        "review_status": "reviewed",
        "independence_group_field": group_field,
        "measurement_timing": "unknown",
        "causal_design_validated": False,
        "operational_validation_validated": False,
        "limitations": ["Association is limited to declared independent samples."],
    }


def test_writer_emits_default_descriptive_policy(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    result = build_characterization_handoff_bundle_from_config(
        _write_config(tmp_path), output
    )
    manifest = json.loads((output / "characterization_handoff_bundle.json").read_text())

    assert result["validation"]["downstream_use_policy_present"] is True
    assert manifest["downstream_use_policy"]["maximum_allowed_use"] == "descriptive"
    assert manifest["downstream_use_policy"]["evidence_level"] == "Diagnostic"


def test_explicit_association_policy_requires_context_group(tmp_path: Path) -> None:
    config = _write_config(tmp_path, _association_policy("parent_specimen_id"))

    with pytest.raises(ValueError, match="absent from sample_context"):
        build_characterization_handoff_bundle_from_config(
            config, tmp_path / "bundle"
        )

    assert not (tmp_path / "bundle").exists()


def test_explicit_association_policy_accepts_sample_id_group(tmp_path: Path) -> None:
    config = _write_config(tmp_path, _association_policy("sample_id"))
    result = build_characterization_handoff_bundle_from_config(
        config, tmp_path / "bundle"
    )

    assert (
        result["validation"]["downstream_use_policy"]["maximum_allowed_use"]
        == "association"
    )
