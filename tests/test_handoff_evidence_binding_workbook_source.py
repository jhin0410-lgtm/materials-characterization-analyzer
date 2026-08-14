from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mca.feature_records import LONG_FEATURE_COLUMNS
from mca.handoff_validation.evidence_binding import validate_evidence_identity_binding


SOURCE_DIGEST = "a" * 64
CASE_ID = "workbook-source-record"


def _feature() -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-xrd",
        "instrument": "xrd",
        "feature_name": "detected_peak_count",
        "feature_label": None,
        "value": 1.0,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "source.xlsx",
        "source_sha256": SOURCE_DIGEST,
        "preprocessing_id": "xrd-preprocessing-v1",
        "quality_flag": "review_required",
    }


def test_workbook_record_with_generic_sha256_binds_feature_source(tmp_path: Path) -> None:
    feature = _feature()
    feature_table = pd.DataFrame([feature], columns=LONG_FEATURE_COLUMNS)

    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "case_id": CASE_ID,
                "workbook": {
                    "name": "source.xlsx",
                    "size_bytes": 123,
                    "sha256": SOURCE_DIGEST,
                    "raw_committed": False,
                },
            }
        ),
        encoding="utf-8",
    )

    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(
        json.dumps(
            {
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "workbook-source-regression",
                        "features": [feature],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    comparability_path = tmp_path / "comparability.csv"
    pd.DataFrame(
        [
            {
                "sample_id": "sample-a",
                "modality": "xrd",
                "comparability_status": "not_established",
            }
        ]
    ).to_csv(comparability_path, index=False)

    binding = validate_evidence_identity_binding(
        case_id=CASE_ID,
        feature_table=feature_table,
        source_manifest_path=source_path,
        analysis_manifest_path=analysis_path,
        comparability_matrix_path=comparability_path,
    )

    assert binding["source_sha256_coverage_verified"] is True
    assert binding["source_manifest_sha256_value_count"] == 1
    assert binding["source_digest_scope"] == "recognized_source_records_only"
