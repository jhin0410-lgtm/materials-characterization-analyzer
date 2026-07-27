"""Versioned file bundle for cross-repository characterization handoff."""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import AnalysisResult
from .feature_records import LONG_FEATURE_COLUMNS, records_to_frame
from .provenance import sha256_file

BUNDLE_SCHEMA_VERSION = "1.0"
BUNDLE_TYPE = "materials_characterization_feature_handoff"
FEATURE_FILE_NAME = "characterization_features_long.csv"
SAMPLE_CONTEXT_FILE_NAME = "sample_context.csv"
MANIFEST_FILE_NAME = "characterization_handoff_bundle.json"


def _relative_reference(output_dir: Path, path: str | Path, label: str) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(f"{label} not found: {candidate}")
    resolved_output = output_dir.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_output != resolved_candidate.parent:
        raise ValueError(f"{label} must be stored directly in the bundle output directory.")
    return {
        "path": candidate.name,
        "sha256": sha256_file(candidate),
        "size_bytes": candidate.stat().st_size,
    }


def write_characterization_handoff_bundle(
    results: Iterable[AnalysisResult],
    output_dir: str | Path,
    *,
    case_id: str,
    sample_context_rows: Iterable[Mapping[str, object]],
    source_manifest_path: str | Path,
    analysis_manifest_path: str | Path,
    comparability_matrix_path: str | Path,
    producer_repository: str,
    evidence_level: str,
    scientific_boundary: Mapping[str, object],
) -> dict[str, Path]:
    """Write a portable feature/context bundle without importing a consumer project."""
    result_list = list(results)
    if not result_list:
        raise ValueError("At least one AnalysisResult is required for a handoff bundle.")
    if not case_id.strip():
        raise ValueError("case_id must not be empty.")
    if not producer_repository.strip():
        raise ValueError("producer_repository must not be empty.")

    feature_records = [feature for result in result_list for feature in result.features]
    if not feature_records:
        raise ValueError("Handoff bundle requires at least one numeric feature record.")
    feature_table = records_to_frame(feature_records).loc[:, LONG_FEATURE_COLUMNS]
    if feature_table.duplicated().any():
        raise ValueError("Handoff feature table contains duplicate rows.")

    context_table = pd.DataFrame([dict(row) for row in sample_context_rows])
    if "sample_id" not in context_table.columns:
        raise ValueError("sample context requires a sample_id column.")
    context_table = context_table.copy()
    context_table["sample_id"] = context_table["sample_id"].astype("string").str.strip()
    if context_table["sample_id"].isna().any() or context_table["sample_id"].eq("").any():
        raise ValueError("sample context contains blank sample_id values.")
    if context_table["sample_id"].duplicated().any():
        raise ValueError("sample context sample_id values must be unique.")

    feature_sample_ids = sorted(set(feature_table["sample_id"].astype(str)))
    context_sample_ids = sorted(set(context_table["sample_id"].astype(str)))
    if feature_sample_ids != context_sample_ids:
        raise ValueError(
            "Feature and sample-context sample_id sets must match exactly; "
            f"features={feature_sample_ids}, context={context_sample_ids}."
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    feature_path = output / FEATURE_FILE_NAME
    context_path = output / SAMPLE_CONTEXT_FILE_NAME
    manifest_path = output / MANIFEST_FILE_NAME
    for path in (feature_path, context_path, manifest_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing handoff artifact: {path}")

    feature_table.sort_values(
        ["sample_id", "instrument", "feature_name", "feature_label", "measurement_id"],
        na_position="last",
    ).to_csv(feature_path, index=False)
    context_table.sort_values("sample_id").to_csv(context_path, index=False)

    software_versions = sorted({result.software_version for result in result_list})
    result_schema_versions = sorted({result.schema_version for result in result_list})
    quality_counts = Counter(str(value) for value in feature_table["quality_flag"])
    source_hash_coverage = int(feature_table["source_sha256"].notna().sum())
    preprocessing_coverage = int(feature_table["preprocessing_id"].notna().sum())

    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_type": BUNDLE_TYPE,
        "case_id": case_id,
        "producer": {
            "repository": producer_repository,
            "software_versions": software_versions,
            "analysis_result_schema_versions": result_schema_versions,
        },
        "join_contract": {
            "join_key": "sample_id",
            "row_order_join_allowed": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
        },
        "feature_table": {
            "path": feature_path.name,
            "sha256": sha256_file(feature_path),
            "size_bytes": feature_path.stat().st_size,
            "columns": LONG_FEATURE_COLUMNS,
            "row_count": int(len(feature_table)),
            "sample_count": int(feature_table["sample_id"].nunique()),
            "measurement_count": int(feature_table["measurement_id"].nunique()),
            "instruments": sorted(set(feature_table["instrument"].astype(str))),
            "quality_flag_counts": dict(sorted(quality_counts.items())),
            "source_sha256_record_count": source_hash_coverage,
            "preprocessing_id_record_count": preprocessing_coverage,
        },
        "sample_context": {
            "path": context_path.name,
            "sha256": sha256_file(context_path),
            "size_bytes": context_path.stat().st_size,
            "columns": list(context_table.columns),
            "row_count": int(len(context_table)),
        },
        "evidence_references": {
            "source_manifest": _relative_reference(output, source_manifest_path, "source manifest"),
            "analysis_manifest": _relative_reference(output, analysis_manifest_path, "analysis manifest"),
            "comparability_matrix": _relative_reference(
                output, comparability_matrix_path, "comparability matrix"
            ),
        },
        "scientific_closeout": {
            "evidence_level": evidence_level,
            **dict(scientific_boundary),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "feature_table": feature_path,
        "sample_context": context_path,
        "manifest": manifest_path,
    }
