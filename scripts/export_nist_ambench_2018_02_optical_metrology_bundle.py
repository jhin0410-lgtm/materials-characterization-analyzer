"""Export NIST AM-Bench 2018-02 optical-metrology values as a handoff bundle."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from mca import __version__
from mca.handoff_bundle import write_characterization_handoff_bundle
from mca.provenance import sha256_file

DEFAULT_CONFIG = Path("case_studies/nist_ambench_2018_02/case_config.json")
PRODUCER_REPOSITORY = "jhin0410-lgtm/materials-characterization-analyzer"
EXPECTED_COLUMNS = [
    "sample_id",
    "case_id",
    "trace_number",
    "melt_pool_width_mean_um",
    "melt_pool_width_std_dev_um",
    "melt_pool_depth_mean_um",
    "melt_pool_depth_std_dev_um",
]
FEATURE_SPECS = [
    ("melt_pool_width_mean_um", "melt_pool_width_mean", "um"),
    ("melt_pool_width_std_dev_um", "melt_pool_width_std_dev", "um"),
    ("melt_pool_depth_mean_um", "melt_pool_depth_mean", "um"),
    ("melt_pool_depth_std_dev_um", "melt_pool_depth_std_dev", "um"),
]
EXPECTED_CASE_SUMMARY = {
    "A": (147.9, 3.7, 42.5, 1.7),
    "B": (123.5, 6.5, 36.0, 1.9),
    "C": (106.0, 1.4, 29.6, 0.6),
}
REPORT_TEXT = """# NIST AM-Bench 2018-02 Optical-Metrology Handoff

## Result

**Evidence level: Diagnostic.** Ten NIST AMMT trace-level transverse-cross-section measurements were exported as 40 checksum-bound optical-metrology feature records.

## Strongest Evidence

- Ten explicit trace sample IDs and case/trace mappings.
- Source-reported width/depth means and within-measurement standard deviations.
- Reproduction of the rounded NIST case-level width/depth summary.
- Complete source-hash and preprocessing provenance coverage.

## Primary Limitation

The values were transcribed from the official NIST results table and were not independently re-extracted from raw optical micrographs. Process conditions are deliberately excluded from this producer bundle and must be supplied by the consumer.

## Supported Use

- Cross-repository process-characterization contract validation.
- Descriptive integration of NIST trace-level process and metrology records.
- Provenance and sample-identity auditing.

## Unsupported Use

- Independent validation of the NIST image-measurement procedure.
- Causal attribution to power, speed, or line energy independently.
- Predictive generalization, optimization, or engineering release decisions.
"""


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return payload


def resolve_source(config_path: Path, config: dict[str, Any]) -> Path:
    source = config.get("source_table")
    if not isinstance(source, dict):
        raise ValueError("Case config requires a source_table object.")
    name = source.get("path")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("source_table.path must be a non-empty filename.")
    relative = Path(name)
    if relative.is_absolute() or len(relative.parts) != 1:
        raise ValueError("source_table.path must name one file beside the case config.")
    path = config_path.parent / relative
    if not path.is_file():
        raise FileNotFoundError(f"NIST measurement source not found: {path}")
    return path


def validate_measurements(table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    missing = [column for column in EXPECTED_COLUMNS if column not in table.columns]
    extra = [column for column in table.columns if column not in EXPECTED_COLUMNS]
    if missing or extra:
        raise ValueError(f"Measurement schema mismatch; missing={missing}, extra={extra}.")

    validated = table.loc[:, EXPECTED_COLUMNS].copy()
    for column in ("sample_id", "case_id"):
        validated[column] = validated[column].astype("string").str.strip()
        if validated[column].isna().any() or validated[column].eq("").any():
            raise ValueError(f"Measurement source contains blank {column} values.")
    if validated["sample_id"].duplicated().any():
        raise ValueError("Measurement source sample_id values must be unique.")

    numeric_columns = EXPECTED_COLUMNS[2:]
    for column in numeric_columns:
        numeric = pd.to_numeric(validated[column], errors="coerce")
        if numeric.isna().any() or not numeric.map(
            lambda value: math.isfinite(float(value))
        ).all():
            raise ValueError(f"Measurement source contains invalid numeric values in {column}.")
        validated[column] = numeric
    validated["trace_number"] = validated["trace_number"].astype(int)

    if sorted(validated["trace_number"].tolist()) != list(range(1, 11)):
        raise ValueError("Measurement source must contain trace numbers 1 through 10 exactly once.")
    expected_ids = [f"amb2018_02_ammt_trace_{trace:02d}" for trace in range(1, 11)]
    if sorted(validated["sample_id"].tolist()) != expected_ids:
        raise ValueError("Measurement source sample_id values do not match the ten AMMT traces.")

    expected_cases = config.get("expected_cases")
    if not isinstance(expected_cases, dict) or set(expected_cases) != {"A", "B", "C"}:
        raise ValueError("Case config must define expected cases A, B, and C.")
    for case_id, expected in expected_cases.items():
        if not isinstance(expected, dict):
            raise ValueError(f"expected_cases.{case_id} must be an object.")
        traces = expected.get("trace_numbers")
        count = expected.get("trace_count")
        if not isinstance(traces, list) or count != len(traces):
            raise ValueError(f"expected_cases.{case_id} has inconsistent trace metadata.")
        observed = validated.loc[validated["case_id"].eq(case_id), "trace_number"].tolist()
        if len(observed) != count or sorted(observed) != sorted(int(value) for value in traces):
            raise ValueError(f"Case {case_id} trace mapping does not match the case config.")

    mean_columns = ["melt_pool_width_mean_um", "melt_pool_depth_mean_um"]
    std_columns = ["melt_pool_width_std_dev_um", "melt_pool_depth_std_dev_um"]
    if (validated[mean_columns] <= 0).any().any():
        raise ValueError("Melt-pool width and depth means must be positive.")
    if (validated[std_columns] < 0).any().any():
        raise ValueError("Reported standard deviations must be non-negative.")

    summary = (
        validated.groupby("case_id", sort=True)
        .agg(
            width_mean=("melt_pool_width_mean_um", "mean"),
            width_std=("melt_pool_width_mean_um", "std"),
            depth_mean=("melt_pool_depth_mean_um", "mean"),
            depth_std=("melt_pool_depth_mean_um", "std"),
        )
        .reset_index()
    )
    for row in summary.itertuples(index=False):
        actual = tuple(round(float(value), 1) for value in row[1:])
        if actual != EXPECTED_CASE_SUMMARY[row.case_id]:
            raise ValueError(
                f"Case {row.case_id} does not reproduce the NIST rounded summary: "
                f"actual={actual}, expected={EXPECTED_CASE_SUMMARY[row.case_id]}."
            )
    return validated.sort_values("trace_number").reset_index(drop=True)


def build_analysis_manifest(
    measurements: pd.DataFrame,
    config: dict[str, Any],
    source_path: Path,
    output: Path,
) -> Path:
    measurement = config.get("measurement")
    if not isinstance(measurement, dict):
        raise ValueError("Case config requires a measurement object.")
    instrument = str(measurement.get("instrument") or "").strip()
    method = str(measurement.get("method") or "").strip()
    preprocessing_id = str(measurement.get("preprocessing_id") or "").strip()
    quality_flag = str(measurement.get("quality_flag") or "").strip()
    if not all((instrument, method, preprocessing_id, quality_flag)):
        raise ValueError("Measurement config is incomplete.")

    source_sha256 = sha256_file(source_path)
    analyses: list[dict[str, Any]] = []
    for row in measurements.itertuples(index=False):
        measurement_id = f"{row.sample_id}_xsection"
        features = [
            {
                "sample_id": row.sample_id,
                "measurement_id": measurement_id,
                "instrument": instrument,
                "feature_name": feature_name,
                "feature_label": None,
                "value": float(getattr(row, source_column)),
                "unit": unit,
                "method": method,
                "source_file": source_path.name,
                "source_sha256": source_sha256,
                "preprocessing_id": preprocessing_id,
                "quality_flag": quality_flag,
            }
            for source_column, feature_name, unit in FEATURE_SPECS
        ]
        analyses.append(
            {
                "schema_version": "1.0",
                "measurement_id": measurement_id,
                "sample_id": row.sample_id,
                "instrument": instrument,
                "source_file": source_path.name,
                "source_sha256": source_sha256,
                "acquisition_metadata": {
                    "source_type": "source_reported_table",
                    "measurement_mode": "NIST microscope-control metrology mode",
                    "reported_individual_measurement_uncertainty_um": measurement.get(
                        "reported_individual_measurement_uncertainty_um"
                    ),
                    "raw_image_parsed": False,
                    "case_id": row.case_id,
                    "trace_number": int(row.trace_number),
                },
                "preprocessing_steps": [
                    {
                        "step": "manual_transcription_from_official_nist_results_page",
                        "value_modification": False,
                        "rounding_or_aggregation": False,
                    }
                ],
                "tables": {},
                "figures": {},
                "features": features,
                "warnings": ["source_reported_table_not_raw_image_feature_extraction"],
                "limitations": [
                    "Raw optical micrographs were not independently remeasured.",
                    "No additional uncertainty propagation was performed.",
                ],
                "software_version": __version__,
            }
        )

    path = output / "case_analysis_manifest.json"
    path.write_text(
        json.dumps(
            {"schema_version": "1.0", "analysis_count": 10, "analyses": analyses},
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def build_source_manifest(
    config_path: Path,
    config: dict[str, Any],
    source_path: Path,
    output: Path,
) -> Path:
    dataset = config.get("dataset")
    source_table = config.get("source_table")
    if not isinstance(dataset, dict) or not isinstance(source_table, dict):
        raise ValueError("Case config requires dataset and source_table objects.")
    payload = {
        "case_id": config.get("case_id"),
        "dataset": dataset,
        "tracked_inputs": {
            "case_config": {"path": config_path.name, "sha256": sha256_file(config_path)},
            "measurement_source": {
                "path": source_path.name,
                "sha256": sha256_file(source_path),
                "row_count": 10,
                "provenance_type": source_table.get("provenance_type"),
                "raw_image_parsed": bool(source_table.get("raw_image_parsed", False)),
                "redistributes_raw_images": bool(source_table.get("redistributes_raw_images", False)),
            },
        },
        "identity_basis": {
            "join_key": "sample_id",
            "sample_id_definition": "one NIST AMMT trace and its reported transverse cross section",
            "case_and_trace_mapping_preserved": True,
            "row_order_join_allowed": False,
        },
        "missing_metadata_inferred": False,
    }
    path = output / "case_source_manifest.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def build_comparability_matrix(output: Path) -> Path:
    path = output / "comparability_matrix.csv"
    pd.DataFrame(
        [
            {
                "instrument": "optical_microscopy_metrology",
                "availability_status": "available_source_reported_table",
                "comparability_status": "trace_mapping_confirmed_within_benchmark",
                "raw_data_reanalysis_status": "not_performed",
                "primary_limitation": "source-reported values were not independently remeasured from raw images",
            }
        ]
    ).to_csv(path, index=False)
    return path


def sample_context_rows(measurements: pd.DataFrame, config: dict[str, Any]) -> list[dict[str, Any]]:
    dataset = config.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("Case config requires a dataset object.")
    return [
        {
            "sample_id": row.sample_id,
            "case_id": row.case_id,
            "trace_number": int(row.trace_number),
            "material": dataset.get("material"),
            "system": dataset.get("system"),
            "dataset_doi": dataset.get("public_data_repository_doi"),
            "dataset_version": dataset.get("public_data_repository_version"),
            "measurement_source_type": "source_reported_table",
            "trace_to_cross_section_mapping_confirmed": True,
            "same_material_confirmed": True,
            "raw_image_parsed": False,
            "process_conditions_included_in_bundle": False,
        }
        for row in measurements.itertuples(index=False)
    ]


def export_bundle(config_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    config_path = Path(config_path)
    config = load_json(config_path)
    source_path = resolve_source(config_path, config)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; existing files were preserved: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    measurements = validate_measurements(pd.read_csv(source_path), config)
    source_manifest = build_source_manifest(config_path, config, source_path, output)
    analysis_manifest = build_analysis_manifest(measurements, config, source_path, output)
    comparability = build_comparability_matrix(output)
    paths = write_characterization_handoff_bundle(
        output,
        case_id=str(config.get("case_id") or ""),
        sample_context_rows=sample_context_rows(measurements, config),
        source_manifest_path=source_manifest,
        analysis_manifest_path=analysis_manifest,
        comparability_matrix_path=comparability,
        producer_repository=PRODUCER_REPOSITORY,
        evidence_level="Diagnostic",
        scientific_boundary={
            "result": "nist_ambench_trace_optical_metrology_exported",
            "strongest_evidence": (
                "Ten explicit NIST AMMT trace IDs, 40 source-reported optical-metrology "
                "records, NIST case-summary reproduction, and complete provenance coverage."
            ),
            "primary_limitation": (
                "Values were transcribed from the official NIST results table rather than "
                "independently re-extracted from raw optical micrographs; process conditions "
                "are intentionally absent from the producer bundle."
            ),
            "suitable_for": [
                "cross-repository process-characterization contract validation",
                "descriptive NIST trace-level integration",
                "sample identity and provenance auditing",
            ],
            "unsuitable_for": [
                "independent validation of the NIST image-metrology procedure",
                "causal attribution to power, speed, or line energy independently",
                "predictive generalization",
                "process optimization",
                "engineering release decisions",
            ],
        },
    )

    summary = {
        "case_id": config.get("case_id"),
        "status": "completed",
        "evidence_level": "Diagnostic",
        "sample_count": 10,
        "measurement_count": 10,
        "feature_record_count": 40,
        "instruments": ["optical_microscopy_metrology"],
        "source_measurement_sha256": sha256_file(source_path),
        "source_reported_values": True,
        "raw_image_parsed": False,
        "process_conditions_included": False,
        "software_validation": {
            "stable_feature_contract_written": True,
            "all_source_hashes_populated": True,
            "all_preprocessing_ids_populated": True,
            "row_order_join_used": False,
            "aggregation_performed": False,
            "model_trained": False,
            "optimization_performed": False,
        },
        "scientific_closeout": load_json(paths["manifest"])["scientific_closeout"],
    }
    summary_path = output / "case_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = output / "case_report.md"
    report_path.write_text(REPORT_TEXT, encoding="utf-8")
    return {
        **paths,
        "source_manifest": source_manifest,
        "analysis_manifest": analysis_manifest,
        "comparability_matrix": comparability,
        "summary": summary_path,
        "report": report_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = export_bundle(args.config, args.output)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"NIST AM-Bench optical-metrology export failed: {exc}", file=sys.stderr)
        return 1
    print("NIST AM-Bench optical-metrology handoff bundle exported.")
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
