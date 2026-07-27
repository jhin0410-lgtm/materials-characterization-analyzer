from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.feature_records import LONG_FEATURE_COLUMNS
from mca.provenance import sha256_file
from scripts.export_public_rwgs_handoff_bundle import BUNDLE_DIRECTORY_NAME, export_bundle


SAMPLE_ID = "rwgs-5wt-cu-al2o3"


def _feature(
    instrument: str,
    feature_name: str,
    value: float,
    *,
    unit: str,
    quality_flag: str = "review_required",
) -> dict[str, object]:
    return {
        "sample_id": SAMPLE_ID,
        "measurement_id": f"{SAMPLE_ID}-{instrument}",
        "instrument": instrument,
        "feature_name": feature_name,
        "feature_label": None,
        "value": value,
        "unit": unit,
        "method": "public_rwgs_test_method",
        "source_file": f"producer-local/{instrument}-source",
        "source_sha256": ("a" if instrument == "xrd" else "b") * 64,
        "preprocessing_id": f"rwgs-{instrument}-preprocessing-v1",
        "quality_flag": quality_flag,
    }


def _write_persisted_case(result: Path) -> None:
    result.mkdir()
    (result / "selected_source_manifest.json").write_text(
        json.dumps({"xrd": {"sha256": "a" * 64}, "sem": {}, "eds": {"sha256": "b" * 64}}),
        encoding="utf-8",
    )
    (result / "characterization_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 3,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.8.5",
                        "instrument": "xrd",
                        "features": [
                            _feature("xrd", "detected_peak_count", 4.0, unit="count")
                        ],
                    },
                    {
                        "schema_version": "1.0",
                        "software_version": "0.8.5",
                        "instrument": "sem",
                        "features": [],
                    },
                    {
                        "schema_version": "1.0",
                        "software_version": "0.8.5",
                        "instrument": "eds",
                        "features": [
                            _feature(
                                "eds",
                                "element_weight_percent",
                                21.49,
                                unit="percent",
                            )
                        ],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "modality": ["xrd", "sem", "eds"],
            "comparability_status": [
                "conditionally_comparable",
                "source_available_analysis_blocked",
                "conditionally_comparable_with_conflict",
            ],
        }
    ).to_csv(result / "comparability_matrix.csv", index=False)
    (result / "case_summary.json").write_text(
        json.dumps({"case_id": "public-rwgs-5cu-al2o3-xrd-sem-eds"}),
        encoding="utf-8",
    )
    (result / "characterization_features_long.csv").write_text(
        "legacy_case_feature_output_must_remain_unchanged\n",
        encoding="utf-8",
    )


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "case_id": "public-rwgs-5cu-al2o3-xrd-sem-eds",
                "primary_sample": {
                    "sample_id": SAMPLE_ID,
                    "source_label": "5%Cu/Al2O3",
                    "nominal_material": "5 wt% Cu on gamma-Al2O3",
                    "preparation": {
                        "method": "incipient wetness impregnation",
                        "support": "gamma-alumina",
                    },
                    "same_study_confirmed": True,
                    "same_nominal_sample_label_confirmed": True,
                    "same_physical_aliquot_confirmed": False,
                },
                "dataset": {
                    "doi": "10.5281/zenodo.13474908",
                    "version": "v1",
                    "license": "CC-BY-4.0",
                },
                "sem": {
                    "quantitative_segmentation_gate": {
                        "status": "blocked_method_mismatch",
                        "allowed": False,
                    }
                },
                "eds": {
                    "unexpected_element_review": {
                        "elements": ["Ni"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_rwgs_export_writes_isolated_checksum_bound_bundle(tmp_path: Path) -> None:
    result = tmp_path / "result"
    _write_persisted_case(result)
    config = tmp_path / "case_config.json"
    _write_config(config)

    paths = export_bundle(config, result)

    bundle_dir = result / BUNDLE_DIRECTORY_NAME
    assert all(path.parent == bundle_dir for path in paths.values())
    assert (result / "characterization_features_long.csv").read_text(encoding="utf-8") == (
        "legacy_case_feature_output_must_remain_unchanged\n"
    )

    features = pd.read_csv(paths["feature_table"])
    context = pd.read_csv(paths["sample_context"])
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    summary = json.loads((result / "case_summary.json").read_text(encoding="utf-8"))

    assert features.columns.tolist() == LONG_FEATURE_COLUMNS
    assert features["instrument"].tolist() == ["eds", "xrd"]
    assert context.loc[0, "sample_id"] == SAMPLE_ID
    assert context.loc[0, "sem_quantitative_segmentation_status"] == "blocked_method_mismatch"
    assert context.loc[0, "eds_unexpected_elements"] == "Ni"
    assert not bool(context.loc[0, "identical_physical_aliquot_confirmed"])
    assert not bool(context.loc[0, "nominal_composition_confirmed"])

    assert manifest["case_id"] == "public-rwgs-5cu-al2o3-xrd-sem-eds"
    assert manifest["feature_table"]["instruments"] == ["eds", "xrd"]
    assert manifest["feature_table"]["row_count"] == 2
    assert manifest["scientific_closeout"]["evidence_level"] == "Diagnostic"
    assert "process-response modeling" in manifest["scientific_closeout"]["unsuitable_for"]
    assert manifest["feature_table"]["sha256"] == sha256_file(paths["feature_table"])
    assert manifest["sample_context"]["sha256"] == sha256_file(paths["sample_context"])
    assert all(
        Path(record["path"]).parent == Path(".")
        for record in manifest["evidence_references"].values()
    )

    handoff = summary["cross_repository_handoff"]
    assert handoff["manifest"] == "handoff_bundle/characterization_handoff_bundle.json"
    assert handoff["exported_instruments"] == ["eds", "xrd"]
    assert handoff["sem_quantitative_segmentation_status"] == "blocked_method_mismatch"


def test_rwgs_export_refuses_to_replace_existing_bundle_directory(tmp_path: Path) -> None:
    result = tmp_path / "result"
    _write_persisted_case(result)
    config = tmp_path / "case_config.json"
    _write_config(config)
    (result / BUNDLE_DIRECTORY_NAME).mkdir()

    with pytest.raises(FileExistsError):
        export_bundle(config, result)
