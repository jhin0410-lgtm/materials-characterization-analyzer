from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mca.feature_records import LONG_FEATURE_COLUMNS
from mca.handoff_bundle import HandoffBundleContractError, _features_from_analysis_manifest
from mca.handoff_validation.common import HandoffBundleValidationError
from mca.handoff_validation.evidence_binding import validate_evidence_identity_binding


SOURCE_DIGEST = "a" * 64


def _feature(*, value: object = 1.0) -> dict[str, object]:
    return {
        "sample_id": "sample-a",
        "measurement_id": "sample-a-xrd",
        "instrument": "xrd",
        "feature_name": "detected_peak_count",
        "feature_label": None,
        "value": value,
        "unit": "count",
        "method": "diagnostic_peak_detection",
        "source_file": "producer-local/source.csv",
        "source_sha256": SOURCE_DIGEST,
        "preprocessing_id": "xrd-preprocessing-v1",
        "quality_flag": "review_required",
    }


def _analysis(path: Path, *, value: object = 1.0) -> Path:
    path.write_text(
        json.dumps(
            {
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "producer-consumer-parity",
                        "features": [_feature(value=value)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _comparability(path: Path) -> Path:
    pd.DataFrame(
        [
            {
                "sample_id": "sample-a",
                "modality": "xrd",
                "comparability_status": "not_established",
            }
        ]
    ).to_csv(path, index=False)
    return path


def test_analysis_manifest_boolean_value_is_not_coerced_to_numeric(tmp_path: Path) -> None:
    analysis_path = _analysis(tmp_path / "analysis.json", value=True)

    with pytest.raises(HandoffBundleContractError, match="finite JSON number"):
        _features_from_analysis_manifest(analysis_path)


def test_unrelated_explicit_source_digest_does_not_bind_feature(tmp_path: Path) -> None:
    analysis_path = _analysis(tmp_path / "analysis.json")
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps({"audit": {"source_sha256": SOURCE_DIGEST}}),
        encoding="utf-8",
    )
    feature_table = pd.DataFrame([_feature()], columns=LONG_FEATURE_COLUMNS)

    with pytest.raises(
        HandoffBundleValidationError,
        match="does not checksum-bind every feature source_sha256",
    ):
        validate_evidence_identity_binding(
            case_id="producer-consumer-parity",
            feature_table=feature_table,
            source_manifest_path=source_path,
            analysis_manifest_path=analysis_path,
            comparability_matrix_path=_comparability(tmp_path / "comparability.csv"),
        )
