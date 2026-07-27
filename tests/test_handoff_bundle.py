from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.feature_records import LONG_FEATURE_COLUMNS
from mca.handoff_bundle import (
    BUNDLE_TYPE,
    write_characterization_handoff_bundle,
)
from mca.provenance import sha256_file
from scripts.export_public_carbon_handoff_bundle import export_bundle


def _feature(
    *,
    instrument: str = "raman",
    feature_name: str = "candidate_count",
    measurement_id: str = "public-dwcnt-raman-public",
) -> dict[str, object]:
    return {
        "sample_id": "public-dwcnt",
        "measurement_id": measurement_id,
        "instrument": instrument,
        "feature_name": feature_name,
        "feature_label": None,
        "value": 2.0,
        "unit": "count",
        "method": "diagnostic_test_method",
        "source_file": "producer-local/raw-source.tab",
        "source_sha256": "a" * 64,
        "preprocessing_id": f"{instrument}-preprocessing-v1",
        "quality_flag": "review_required",
    }


def _write_case_evidence(root: Path) -> tuple[Path, Path, Path]:
    source_manifest = root / "case_source_manifest.json"
    source_manifest.write_text('{"source": "public"}\n', encoding="utf-8")
    analysis_manifest = root / "case_analysis_manifest.json"
    analysis_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 2,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.8.3",
                        "features": [_feature()],
                    },
                    {
                        "schema_version": "1.0",
                        "software_version": "0.8.3",
                        "features": [
                            _feature(
                                instrument="ftir",
                                feature_name="band_candidate_count",
                                measurement_id="public-dwcnt-ftir-public",
                            )
                        ],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {
            "modality": ["raman", "ftir"],
            "comparability_status": [
                "conditionally_comparable",
                "conditionally_comparable",
            ],
        }
    ).to_csv(comparability, index=False)
    return source_manifest, analysis_manifest, comparability


def test_handoff_bundle_writes_versioned_feature_context_and_evidence_contract(
    tmp_path: Path,
) -> None:
    source_manifest, analysis_manifest, comparability = _write_case_evidence(tmp_path)

    paths = write_characterization_handoff_bundle(
        tmp_path,
        case_id="public-carbon-dwcnt-multimodal-v1",
        sample_context_rows=[
            {
                "sample_id": "public-dwcnt",
                "material_class": "double-walled carbon nanotubes",
                "identical_physical_aliquot_confirmed": False,
            }
        ],
        source_manifest_path=source_manifest,
        analysis_manifest_path=analysis_manifest,
        comparability_matrix_path=comparability,
        producer_repository="jhin0410-lgtm/materials-characterization-analyzer",
        evidence_level="Diagnostic",
        scientific_boundary={"primary_limitation": "aliquot identity is not confirmed"},
    )

    features = pd.read_csv(paths["feature_table"])
    context = pd.read_csv(paths["sample_context"])
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert features.columns.tolist() == LONG_FEATURE_COLUMNS
    assert features["instrument"].tolist() == ["ftir", "raman"]
    assert context["sample_id"].tolist() == ["public-dwcnt"]
    assert manifest["bundle_type"] == BUNDLE_TYPE
    assert manifest["schema_version"] == "1.0"
    assert manifest["join_contract"] == {
        "join_key": "sample_id",
        "row_order_join_allowed": False,
        "aggregation_performed": False,
        "missing_metadata_inferred": False,
    }
    assert manifest["feature_table"]["row_count"] == 2
    assert manifest["feature_table"]["measurement_count"] == 2
    assert manifest["feature_table"]["instruments"] == ["ftir", "raman"]
    assert manifest["feature_table"]["source_sha256_record_count"] == 2
    assert manifest["feature_table"]["sha256"] == sha256_file(paths["feature_table"])
    assert manifest["sample_context"]["sha256"] == sha256_file(paths["sample_context"])
    assert manifest["evidence_references"]["analysis_manifest"]["path"] == analysis_manifest.name
    assert not any(Path(record["path"]).is_absolute() for record in manifest["evidence_references"].values())


def test_handoff_bundle_rejects_sample_identity_mismatch(tmp_path: Path) -> None:
    source_manifest, analysis_manifest, comparability = _write_case_evidence(tmp_path)

    with pytest.raises(ValueError, match="sample_id sets must match exactly"):
        write_characterization_handoff_bundle(
            tmp_path,
            case_id="case",
            sample_context_rows=[{"sample_id": "different-sample"}],
            source_manifest_path=source_manifest,
            analysis_manifest_path=analysis_manifest,
            comparability_matrix_path=comparability,
            producer_repository="producer/repository",
            evidence_level="Diagnostic",
            scientific_boundary={},
        )


def test_handoff_bundle_refuses_to_overwrite_existing_artifact(tmp_path: Path) -> None:
    source_manifest, analysis_manifest, comparability = _write_case_evidence(tmp_path)
    (tmp_path / "characterization_features_long.csv").write_text("do not replace\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_characterization_handoff_bundle(
            tmp_path,
            case_id="case",
            sample_context_rows=[{"sample_id": "public-dwcnt"}],
            source_manifest_path=source_manifest,
            analysis_manifest_path=analysis_manifest,
            comparability_matrix_path=comparability,
            producer_repository="producer/repository",
            evidence_level="Diagnostic",
            scientific_boundary={},
        )
    assert (tmp_path / "characterization_features_long.csv").read_text(encoding="utf-8") == "do not replace\n"


def test_public_case_exporter_adds_bundle_to_persisted_case_summary(tmp_path: Path) -> None:
    result = tmp_path / "result"
    result.mkdir()
    _write_case_evidence(result)
    (result / "case_summary.json").write_text(
        json.dumps({"case_id": "public-carbon-dwcnt-multimodal-v1"}),
        encoding="utf-8",
    )
    config = tmp_path / "case_config.json"
    config.write_text(
        json.dumps(
            {
                "case_id": "public-carbon-dwcnt-multimodal-v1",
                "primary_sample": {
                    "sample_id": "public-dwcnt",
                    "source_label": "DWCNT",
                    "material_class": "double-walled carbon nanotubes",
                    "source_description": "CCVD-synthesized DWCNT using Co and Mo catalysts",
                },
                "dataset": {
                    "persistent_id": "doi:10.57745/7KA2UG",
                    "version": "1.0",
                    "license": "Etalab Open License 2.0",
                },
            }
        ),
        encoding="utf-8",
    )

    paths = export_bundle(config, result)

    summary = json.loads((result / "case_summary.json").read_text(encoding="utf-8"))
    assert summary["cross_repository_handoff"]["manifest"] == paths["manifest"].name
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["case_id"] == "public-carbon-dwcnt-multimodal-v1"
    assert manifest["scientific_closeout"]["evidence_level"] == "Diagnostic"
    assert "process-response modeling" in manifest["scientific_closeout"]["unsuitable_for"]
