"""Export NIST AM-Bench 2018-02 optical-metrology measurements as a handoff bundle."""
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
EXPECTED_ROUNDED_CASE_SUMMARY = {
    "A": {"width_mean": 147.9, "width_std": 3.7, "depth_mean": 42.5, "depth_std": 1.7},
    "B": {"width_mean": 123.5, "width_std": 6.5, "depth_mean": 36.0, "depth_std": 1.9},
    "C": {"width_mean": 106.0, "width_std": 1.4, "depth_mean": 29.6, "depth_std": 0.6},
}


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return payload


def _resolve_source_path(config_path: Path, config: dict[str, Any]) -> Path:
    source = config.get("source_table")
    if not isinstance(source, dict):
        raise ValueError("Case config requires a source_table object.")
    relative = source.get("path")
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("source_table.path must be a non-empty relative path.")
    candidate = Path(relative)
    if candidate.is_absolute() or len(candidate.parts) != 1:
        raise ValueError("source_table.path must name one file beside the case config.")
    path = config_path.parent / candidate
    if not path.is_file():
        raise FileNotFoundError(f"NIST measurement source not found: {path}")
    return path


def validate_measurements(
    table: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Validate schema, identifiers, expected trace mapping, and physical ranges."""
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

    numeric_columns = [
        "trace_number",
        "melt_pool_width_mean_um",
        "melt_pool_width_std_dev_um",
        "melt_pool_depth_mean_um",
        "melt_pool_depth_std_dev_um",
    ]
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
        group = validated.loc[validated["case_id"].eq(case_id)]
        trace_numbers = expected.get("trace_numbers")
        trace_count = expected.get("trace_count")
        if not isinstance(trace_numbers, list) or trace_count != len(trace_numbers):
            raise ValueError(f"expected_cases.{case_id} has inconsistent trace metadata.")
        if len(group) != trace_count or sorted(group["trace_number"].tolist()) != sorted(
            int(value) for value in trace_numbers
        ):
            raise ValueError(f"Case {case_id} trace mapping does not match the case config.")

    means = ["melt_pool_width_mean_um", "melt_pool_depth_mean_um"]
    standard_deviations = [
        "melt_pool_width_std_dev_um",
        "melt_pool_depth_std_dev_um",
    ]
    if (validated[means] <= 0).any().any():
        raise ValueError("Melt-pool width and depth means must be positive.")
    if (validated[standard_deviations] < 0).any().any():
        raise ValueError("Reported standard deviations must be non-negative.")

    _validate_case_summary(validated)
    return validated.sort_values("trace_number").reset_index(drop=True)


def _validate_case_summary(measurements: pd.DataFrame) -> None:
    summary = (
        measurements.groupby("case_id", sort=True)
        .agg(
            width_mean=("melt_pool_width_mean_um", "mean"),
            width_std=("melt_pool_width_mean_um", "std"),
            depth_mean=("melt_pool_depth_mean_um", "mean"),
            depth_std=("melt_pool_depth_mean_um", "std"),
        )
        .reset_index()
    )
    for row in summary.itertuples(index=False):
        actual = {
            "width_mean": round(float(row.width_mean), 1),
            "width_std": round(float(row.width_std), 1),
            "depth_mean": round(float(row.depth_mean), 1),
            "depth_std": round(float(row.depth_std), 1),
        }
        if actual != EXPECTED_ROUNDED_CASE_SUMMARY[row.case_id]:
            raise ValueError(
                f"Case {row.case_id} does not reproduce the NIST rounded summary: "
                f"actual={actual}, expected={EXPECTED_ROUNDED_CASE_SUMMARY[row.case_id]}."
            )


def _build_analysis_manifest(
    measurements: pd.DataFrame,
    config: dict[str, Any],
    source_path: Path,
    source_sha256: str,
    output: Path,
) -> Path:
    measurement_config = config.get("measurement")
    if not isinstance(measurement_config, dict):
        raise ValueError("Case config requires a measurement object.")
    instrument = str(measurement_config.get("instrument") or "").strip()
    method = str(measurement_config.get("method") or "").strip()
    preprocessing_id = str(measurement_config.get("preprocessing_id") or "").strip()
    quality_flag = str(measurement_config.get("quality_flag") or "").strip()
    if not all((instrument, method, preprocessing_id, quality_flag)):
        raise ValueError("Measurement config requires instrument, method, preprocessing_id, and quality_flag.")

    analyses: list[dict[str, Any]] = []
    for row in measurements.itertuples(index=False):
        features = [
            {
                "sample_id": row.sample_id,
                "measurement_id": f"{row.sample_id}_xsection",
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
                "measurement_id": f"{row.sample_id}_xsection",
                "sample_id": row.sample_id,
                "instrument": instrument,
                "source_file": source_path.name,
                "source_sha256": source_sha256,
                "acquisition_metadata": {
                    "source_type": "source_reported_table",
                    "measurement_mode": "NIST microscope-control metrology mode",
                    "reported_individual_measurement_uncertainty_um": measurement_config.get(
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
                    "The exporter does not independently remeasure the raw optical micrograph.",
                    "Reported within-measurement standard deviations are preserved without additional uncertainty propagation.",
                ],
                "software_version": __version__,
            }
        )

    path = output / "case_analysis_manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": len(analyses),
                "analyses": analyses,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _build_source_manifest(
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
            "case_config": {
                "path": config_path.name,
                "sha256": sha256_file(config_path),
            },
            "measurement_source": {
                "path": source_path.name,
                "sha256": sha256_file(source_path),
                "row_count": 10,
                "provenance_type": source_table.get("provenance_type"),
                "raw_image_parsed": bool(source_table.get("raw_image_parsed", False)),
                "redistributes_raw_images": bool(
                    source_table.get("redistributes_raw_images", False)
                ),
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


def _build_comparability_matrix(output: Path) -> Path:
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


def _sample_context_rows(
    measurements: pd.DataFrame,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
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


def _write_summary_and_report(
    config: dict[str, Any],
    output: Path,
    bundle_path: Path,
    source_path: Path,
) -> dict[str, Path]:
    bundle = load_json(bundle_path)
    summary = {
        "case_id": config.get("case_id"),
        "status": "completed",
        "evidence_level": "Diagnostic",
        "sample_count": bundle["feature_table"]["sample_count"],
        "measurement_count": bundle["feature_table"]["measurement_count"],
        "feature_record_count": bundle["feature_table"]["row_count"],
        "instruments": bundle["feature_table"]["instruments"],
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
        "scientific_closeout": bundle["scientific_closeout"],
    }
    summary_path = output / "case_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = output / "case_report.md"
    report_path.write_text(
        """# NIST AM-Bench 2018-02 Optical-Metrology Handoff\n\n"
        "## Result\n\n"
        "**Evidence level: Diagnostic.** Ten NIST AMMT trace-level transverse-cross-section "
        "measurements were exported as 40 checksum-bound optical-metrology feature records.\n\n"
        "## Strongest Evidence\n\n"
        "- Ten explicit trace sample IDs and case/trace mappings.\n"
        "- Source-reported width/depth means and within-measurement standard deviations.\n"
        "- Reproduction of the rounded NIST case-level width/depth summary.\n"
        "- Complete source-hash and preprocessing provenance coverage.\n\n"
        "## Primary Limitation\n\n"
        "The values were transcribed from the official NIST results table and were not "
        "independently re-extracted from raw optical micrographs. Process conditions are "
        "deliberately excluded from this producer bundle and must be supplied by the consumer.\n\n"
        "## Supported Use\n\n"
        "- Cross-repository process-characterization contract validation.\n"
        "- Descriptive integration of NIST trace-level process and metrology records.\n"
        "- Provenance and sample-identity auditing.\n\n"
        "## Unsupported Use\n\n"
        "- Independent validation of the NIST image-measurement procedure.\n"
        "- Causal attribution to power, speed, or line energy independently.\n"
        "- Predictive generalization, optimization, or engineering release decisions.\n",
        encoding="utf-8",
    )
    return {"summary": summary_path, "report": report_path}


def export_bundle(config_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    config_path = Path(config_path)
    config = load_json(config_path)
    source_path = _resolve_source_path(config_path, config)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; existing files were preserved: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    measurements = validate_measurements(pd.read_csv(source_path), config)
    source_sha256 = sha256_file(source_path)
    source_manifest = _build_source_manifest(
        config_path, config, source_path, output
    )
    analysis_manifest = _build_analysis_manifest(
        measurements, config, source_path, source_sha256, output
    )
    comparability = _build_comparability_matrix(output)
    paths = write_characterization_handoff_bundle(
        output,
        case_id=str(config.get("case_id") or ""),
        sample_context_rows=_sample_context_rows(measurements, config),
        source_manifest_path=source_manifest,
        analysis_manifest_path=analysis_manifest,
        comparability_matrix_path=comparability,
        producer_repository=PRODUCER_REPOSITORY,
        evidence_level="Diagnostic",
        scientific_boundary={
            "result": "nist_ambench_trace_optical_metrology_exported",
            "strongest_evidence": (
                "Ten explicit NIST AMMT trace IDs, 40 source-reported optical-metrology "
                "records, official case-summary reproduction, and complete checksum and "
                "preprocessing provenance coverage."
            ),
            "primary_limitation": (
                "The values were transcribed from the official NIST results table rather "
                "than independently re-extracted from raw optical micrographs; process "
                "conditions are intentionally absent from the producer bundle."
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
    paths.update(
        {
            "source_manifest": source_manifest,
            "analysis_manifest": analysis_manifest,
            "comparability_matrix": comparability,
        }
    )
    paths.update(
        _write_summary_and_report(
            config, output, paths["manifest"], source_path
        )
    )
    return paths


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
