from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.evidence_ladder import LEVELS, evaluate_evidence_ladder
from mca.handoff_bundle import write_characterization_handoff_bundle
from mca.handoff_bundle_validation import validate_characterization_handoff_bundle
from mca.handoff_evidence_ladder import (
    EvidenceLadderHandoffError,
    validate_scientific_evidence_ladder_record,
)
from mca.provenance import sha256_file

CASE_ID = "direct-writer-ladder-case"


def _feature() -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-raman",
        "instrument": "raman",
        "feature_name": "candidate_count",
        "feature_label": None,
        "value": 2.0,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "producer-local/raman.txt",
        "source_sha256": "a" * 64,
        "preprocessing_id": "raman-preprocessing-v1",
        "quality_flag": "review_required",
    }


def _prepare_direct_inputs(
    root: Path,
    *,
    declaration_id: str = CASE_ID,
    modality: str = "raman",
) -> dict[str, Path]:
    root.mkdir()
    source = root / "source_manifest.json"
    source.write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    analysis = root / "analysis_manifest.json"
    analysis.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.11.0",
                        "features": [_feature()],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(comparability, index=False)
    bindings = {
        "source_manifest": sha256_file(source),
        "analysis_manifest": sha256_file(analysis),
        "comparability_matrix": sha256_file(comparability),
    }
    declaration = {
        "schema_version": "1.0",
        "declaration_id": declaration_id,
        "subject": {
            "modality": modality,
            "source_material_domain": "reference-material",
            "target_material_domain": "target-material",
            "claim_scope": "method_validation",
        },
        "source_bindings": [
            {"role": role, "sha256": bindings[role]} for role in sorted(bindings)
        ],
        "levels": {
            level: {
                "assessment": "Supported" if index <= 4 else "Unsupported",
                "evidence": [f"verified {level}"] if index <= 4 else [],
                "limitations": [] if index <= 4 else [f"open {level}"],
            }
            for index, level in enumerate(LEVELS)
        },
        "limitations": ["Higher maturity remains open."],
    }
    assessment = root / "evidence_ladder_assessment.json"
    assessment.write_text(
        json.dumps(evaluate_evidence_ladder(declaration), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "source": source,
        "analysis": analysis,
        "comparability": comparability,
        "assessment": assessment,
    }


def _write(root: Path, paths: dict[str, Path]) -> dict[str, Path]:
    return write_characterization_handoff_bundle(
        root,
        case_id=CASE_ID,
        sample_context_rows=[{"sample_id": "sample-a"}],
        source_manifest_path=paths["source"],
        analysis_manifest_path=paths["analysis"],
        comparability_matrix_path=paths["comparability"],
        producer_repository="jhin0410-lgtm/materials-characterization-analyzer",
        evidence_level="Diagnostic",
        scientific_boundary={
            "suitable_for": ["descriptive evidence integration"],
            "unsuitable_for": ["engineering release"],
        },
        scientific_evidence_ladder_assessment_path=paths["assessment"],
    )


def test_direct_writer_validates_cross_bundle_binding_before_output_write(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    paths = _prepare_direct_inputs(root, declaration_id="different-case")

    with pytest.raises(EvidenceLadderHandoffError, match="declaration_id"):
        _write(root, paths)

    assert not (root / "characterization_features_long.csv").exists()
    assert not (root / "sample_context.csv").exists()
    assert not (root / "characterization_handoff_bundle.json").exists()


def test_ladder_enabled_bundle_uses_schema_1_1_and_validates(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    paths = _prepare_direct_inputs(root)
    outputs = _write(root, paths)

    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.1"
    validation = validate_characterization_handoff_bundle(root)
    assert validation["schema_version"] == "1.1"
    assert validation["scientific_evidence_ladder_present"] is True


def test_backslash_parent_path_is_rejected_portably(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    paths = _prepare_direct_inputs(root)
    outputs = _write(root, paths)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    record = manifest["scientific_evidence_ladder"]
    record["assessment"]["path"] = "..\\evidence_ladder_assessment.json"

    with pytest.raises(EvidenceLadderHandoffError, match="direct safe sibling"):
        validate_scientific_evidence_ladder_record(root, record)
