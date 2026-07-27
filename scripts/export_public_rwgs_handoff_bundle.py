"""Export the persisted public RWGS XRD/SEM/EDS case as a handoff bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mca.handoff_bundle import write_characterization_handoff_bundle

DEFAULT_CONFIG = Path("case_studies/public_rwgs_xrd_sem_eds/case_config.json")
PRODUCER_REPOSITORY = "jhin0410-lgtm/materials-characterization-analyzer"
CONSUMER_REPOSITORY = "jhin0410-lgtm/materials-data-analyzer"


def load_json(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def export_bundle(config_path: str | Path, result_dir: str | Path) -> dict[str, Path]:
    config = load_json(config_path)
    result = Path(result_dir)
    if not result.is_dir():
        raise FileNotFoundError(f"Public RWGS result directory not found: {result}")

    primary_sample = config.get("primary_sample")
    dataset = config.get("dataset")
    sem = config.get("sem")
    eds = config.get("eds")
    if not all(isinstance(value, dict) for value in (primary_sample, dataset, sem, eds)):
        raise ValueError("Case config must contain primary_sample, dataset, sem, and eds objects.")

    primary_sample = dict(primary_sample)
    dataset = dict(dataset)
    sem = dict(sem)
    eds = dict(eds)
    preparation = primary_sample.get("preparation")
    gate = sem.get("quantitative_segmentation_gate")
    unexpected_review = eds.get("unexpected_element_review")
    if not isinstance(preparation, dict) or not isinstance(gate, dict) or not isinstance(
        unexpected_review, dict
    ):
        raise ValueError("RWGS config is missing preparation or quality-gate metadata.")

    unexpected_elements = unexpected_review.get("elements")
    if not isinstance(unexpected_elements, list):
        raise ValueError("RWGS unexpected-element review must provide an elements list.")

    sample_context = {
        "sample_id": primary_sample.get("sample_id"),
        "source_label": primary_sample.get("source_label"),
        "nominal_material": primary_sample.get("nominal_material"),
        "preparation_method": preparation.get("method"),
        "support": preparation.get("support"),
        "dataset_persistent_id": f"doi:{dataset.get('doi')}",
        "dataset_version": dataset.get("version"),
        "dataset_license": dataset.get("license"),
        "same_study_confirmed": bool(primary_sample.get("same_study_confirmed", False)),
        "same_nominal_sample_label_confirmed": bool(
            primary_sample.get("same_nominal_sample_label_confirmed", False)
        ),
        "identical_physical_aliquot_confirmed": bool(
            primary_sample.get("same_physical_aliquot_confirmed", False)
        ),
        "sem_quantitative_segmentation_status": gate.get("status"),
        "eds_unexpected_elements": ",".join(str(value) for value in unexpected_elements),
        "nominal_composition_confirmed": False,
    }

    paths = write_characterization_handoff_bundle(
        result,
        case_id=str(config.get("case_id", "")),
        sample_context_rows=[sample_context],
        source_manifest_path=result / "selected_source_manifest.json",
        analysis_manifest_path=result / "characterization_manifest.json",
        comparability_matrix_path=result / "comparability_matrix.csv",
        producer_repository=PRODUCER_REPOSITORY,
        evidence_level="Diagnostic",
        scientific_boundary={
            "result": "public_rwgs_xrd_eds_features_exported_sem_block_preserved",
            "strongest_evidence": (
                "Checksum-bound XRD and EDS feature records retain source hashes, methods, "
                "quality flags, preprocessing identifiers, and one explicit sample ID; the "
                "SEM method-mismatch block remains part of the evidence package."
            ),
            "primary_limitation": (
                "The three techniques are linked only by a common nominal sample label, SEM "
                "quantitative segmentation is unsuitable, EDS reports unresolved Ni, and "
                "key XRD and EDS acquisition metadata are absent."
            ),
            "suitable_for": [
                "cross-repository contract validation",
                "provenance demonstration",
                "descriptive XRD and EDS feature integration",
                "data-quality and comparability diagnostics",
            ],
            "unsuitable_for": [
                "process-response modeling",
                "causal attribution",
                "phase confirmation",
                "quantitative particle-size claims",
                "nominal-composition confirmation",
                "catalytic mechanism claims",
                "engineering release decisions",
            ],
        },
    )

    summary_path = result / "case_summary.json"
    summary = load_json(summary_path)
    summary["cross_repository_handoff"] = {
        "feature_table": paths["feature_table"].name,
        "sample_context": paths["sample_context"].name,
        "manifest": paths["manifest"].name,
        "consumer_repository": CONSUMER_REPOSITORY,
        "exported_instruments": ["eds", "xrd"],
        "sem_quantitative_segmentation_status": gate.get("status"),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--result", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = export_bundle(args.config, args.result)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"public RWGS handoff export failed: {exc}", file=sys.stderr)
        return 1
    print("Public RWGS cross-repository handoff bundle exported.")
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
